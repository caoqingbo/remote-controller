# -*- coding: utf-8 -*-
"""
Remote KeyMapper Lite 输入引擎。

只通过 Raw Input 的 RIDEV_INPUTSINK 被动监听输入，不注册 NOLEGACY，
不安装键盘钩子，也不调用任何驱动。所有原生按键都会继续交给 Windows。
"""
import ctypes
import queue
import threading
from ctypes import wintypes
from ctypes.wintypes import DWORD, HANDLE, HWND, INT, LONG, UINT, ULONG, USHORT

WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
LRESULT = ctypes.c_ssize_t

import actions
from vkdefs import vk_display

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
ULONG_PTR = ctypes.c_size_t

RIM_TYPEMOUSE, RIM_TYPEKEYBOARD, RIM_TYPEHID = 0, 1, 2
RID_INPUT = 0x10000003
RIDI_DEVICENAME = 0x20000007
RIDEV_INPUTSINK = 0x00000100
WM_INPUT = 0x00FF
WM_TIMER = 0x0113
WM_QUIT = 0x0012
RI_KEY_MAKE = 0
RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", HANDLE), ("dwType", DWORD)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", DWORD), ("dwSize", DWORD),
                ("hDevice", HANDLE), ("wParam", ULONG_PTR)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", USHORT), ("_pad", USHORT),
                ("usButtonFlags", USHORT), ("usButtonData", USHORT),
                ("ulRawButtons", ULONG), ("lLastX", LONG), ("lLastY", LONG),
                ("ulExtraInformation", ULONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", USHORT), ("Flags", USHORT), ("Reserved", USHORT),
                ("VKey", USHORT), ("Message", UINT), ("ExtraInformation", ULONG)]


class RAWHID(ctypes.Structure):
    _fields_ = [("dwSizeHid", DWORD), ("dwCount", DWORD)]


class _RAWDATA(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD), ("hid", RAWHID)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("data", _RAWDATA)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", USHORT), ("usUsage", USHORT),
                ("dwFlags", DWORD), ("hwndTarget", HWND)]


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", HWND), ("message", UINT), ("wParam", WPARAM),
                ("lParam", LPARAM), ("time", DWORD), ("pt", POINT)]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)


def _set_prototypes():
    user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.CreateWindowExW.argtypes = [DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                       DWORD, INT, INT, INT, INT,
                                       HANDLE, HANDLE, HANDLE, ctypes.c_void_p]
    user32.CreateWindowExW.restype = HWND
    user32.PostThreadMessageW.argtypes = [DWORD, UINT, WPARAM, LPARAM]
    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetModuleHandleW.restype = HANDLE


_set_prototypes()


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", UINT), ("style", UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", INT), ("cbWndExtra", INT),
                ("hInstance", HANDLE), ("hIcon", HANDLE), ("hCursor", HANDLE),
                ("hbrBackground", HANDLE), ("lpszMenuName", ctypes.c_wchar_p),
                ("lpszClassName", ctypes.c_wchar_p), ("hIconSm", HANDLE)]


def enumerate_devices():
    """返回 [(hDevice, dwType, name)]，仅枚举，不修改设备状态。"""
    n = UINT(0)
    user32.GetRawInputDeviceList(None, ctypes.byref(n), ctypes.sizeof(RAWINPUTDEVICELIST))
    arr = (RAWINPUTDEVICELIST * n.value)()
    got = user32.GetRawInputDeviceList(arr, ctypes.byref(n), ctypes.sizeof(RAWINPUTDEVICELIST))
    out = []
    for i in range(got):
        size = UINT(0)
        user32.GetRawInputDeviceInfoA(arr[i].hDevice, RIDI_DEVICENAME, None, ctypes.byref(size))
        buf = (ctypes.c_char * size.value)()
        user32.GetRawInputDeviceInfoA(arr[i].hDevice, RIDI_DEVICENAME, buf, ctypes.byref(size))
        out.append((arr[i].hDevice, arr[i].dwType, buf.value.decode("utf-8", "replace")))
    return out


def find_device_handle(match: str):
    for h, t, name in enumerate_devices():
        if match.lower() in name.lower():
            return h
    return None


class Engine:
    def __init__(self, device_match="", on_capture=None, on_log=None):
        self.device_match = device_match
        self.on_capture = on_capture or (lambda e: None)
        self.on_log = on_log or (lambda m: None)
        self.mappings = []
        self._lock = threading.Lock()
        self._thread = None
        self._thread_id = None
        self._hwnd = None
        self._running = threading.Event()
        self._action_q = queue.Queue()
        self._devname_cache = {}
        self._wndproc_ref = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True, name="T6LiteEngine")
        self._thread.start()

    def stop(self):
        self._running.clear()
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=3)

    def is_running(self):
        return bool(self._thread and self._thread.is_alive())

    def set_mappings(self, mappings):
        with self._lock:
            self.mappings = list(mappings)

    def set_device_match(self, match):
        self.device_match = match
        self._devname_cache.clear()

    def device_present(self):
        return find_device_handle(self.device_match) is not None

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        class_name = "RemoteKeyMapperLiteEngineWnd"
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        wndclass = WNDCLASSEXW()
        wndclass.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wndclass.lpfnWndProc = self._wndproc_ref
        wndclass.hInstance = kernel32.GetModuleHandleW(None)
        wndclass.lpszClassName = class_name
        if not user32.RegisterClassExW(ctypes.byref(wndclass)):
            err = kernel32.GetLastError()
            if err != 1410:
                self.on_log("注册窗口类失败: %s" % err)
                return
        hwnd_message = ctypes.c_void_p(-3)
        self._hwnd = user32.CreateWindowExW(0, class_name, "T6LiteEngine", 0,
                                            0, 0, 0, 0, hwnd_message, None,
                                            wndclass.hInstance, None)
        if not self._hwnd:
            self.on_log("创建消息窗口失败")
            return
        regs = [
            (0x01, 0x06),  # 键盘
            (0x01, 0x02),  # 鼠标
            (0x0C, 0x01),  # 消费控制
        ]
        for page, usage in regs:
            one = (RAWINPUTDEVICE * 1)(
                RAWINPUTDEVICE(page, usage, RIDEV_INPUTSINK, self._hwnd))
            if not user32.RegisterRawInputDevices(one, 1, ctypes.sizeof(RAWINPUTDEVICE)):
                self.on_log("注册 Raw Input 失败 page=0x%02X err=%s" %
                            (page, kernel32.GetLastError()))
                return
        user32.SetTimer(self._hwnd, 1, 25, None)
        self.on_log("轻量引擎已启动（无驱动、不屏蔽原键）")
        msg = MSG()
        while self._running.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.DestroyWindow(self._hwnd)
        self.on_log("轻量引擎已停止")

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_INPUT:
                self._handle_raw(lparam)
                return 0
            if msg == WM_TIMER:
                self._pump_actions()
                return 0
        except Exception as e:
            try:
                self.on_log("窗口回调异常: %s" % e)
            except Exception:
                pass
            if msg == WM_INPUT:
                return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _pump_actions(self):
        while True:
            try:
                action, label = self._action_q.get_nowait()
            except queue.Empty:
                return
            try:
                actions.execute_action(action)
                self.on_log("已执行: %s" % label)
            except Exception as e:
                self.on_log("动作执行失败 (%s): %s" % (label, e))

    def _dev_name(self, hdev):
        if hdev not in self._devname_cache:
            size = UINT(0)
            if not hdev:
                return ""
            user32.GetRawInputDeviceInfoA(hdev, RIDI_DEVICENAME, None, ctypes.byref(size))
            if size.value == 0 or size.value > 4096:
                return ""
            buf = (ctypes.c_char * size.value)()
            user32.GetRawInputDeviceInfoA(hdev, RIDI_DEVICENAME, buf, ctypes.byref(size))
            self._devname_cache[hdev] = buf.value.decode("utf-8", "replace")
        return self._devname_cache[hdev]

    def _is_target(self, hdev):
        return bool(self.device_match) and self.device_match.lower() in self._dev_name(hdev).lower()

    def _handle_raw(self, lparam):
        hraw = HANDLE(lparam)
        size = UINT(0)
        hdr_size = ctypes.sizeof(RAWINPUTHEADER)
        user32.GetRawInputData(hraw, RID_INPUT, None, ctypes.byref(size), hdr_size)
        if size.value == 0 or size.value > 65535:
            return
        buf = (ctypes.c_byte * size.value)()
        if user32.GetRawInputData(hraw, RID_INPUT, buf, ctypes.byref(size), hdr_size) != size.value:
            return
        raw = ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents
        hdev = raw.header.hDevice
        if not self._is_target(hdev):
            return
        if raw.header.dwType == RIM_TYPEKEYBOARD:
            kb = raw.data.keyboard
            down = (kb.Flags & 0x01) == RI_KEY_MAKE
            vk = kb.VKey
            if down:
                self._dispatch(("kbd", vk), vk_display(vk))
            self.on_capture({"kind": "kbd", "vk": vk, "name": vk_display(vk),
                             "down": down, "sig": ["kbd", vk]})
        elif raw.header.dwType == RIM_TYPEHID:
            hid = raw.data.hid
            off = hdr_size + 8
            n = hid.dwSizeHid * hid.dwCount
            if n > 0:
                hexstr = bytes(bytearray(buf[off:off + n])).hex(" ")
                self._dispatch(("hid", hexstr), "HID " + hexstr)
                self.on_capture({"kind": "hid", "bytes": hexstr,
                                 "down": True, "sig": ["hid", hexstr]})
        elif raw.header.dwType == RIM_TYPEMOUSE:
            ms = raw.data.mouse
            btn = None
            if ms.usButtonFlags & RI_MOUSE_LEFT_BUTTON_DOWN:
                btn = "left"
            elif ms.usButtonFlags & RI_MOUSE_RIGHT_BUTTON_DOWN:
                btn = "right"
            elif ms.usButtonFlags & RI_MOUSE_MIDDLE_BUTTON_DOWN:
                btn = "middle"
            if btn:
                self._dispatch(("mouse", btn), "鼠标" + btn)
                self.on_capture({"kind": "mouse", "button": btn,
                                 "down": True, "sig": ["mouse", btn]})

    def _dispatch(self, sig, label):
        with self._lock:
            maps = [m for m in self.mappings
                    if m.get("enabled", True)
                    and m.get("sig_kind") == sig[0] and m.get("sig") == sig[1]]
        for m in maps:
            self._action_q.put((m["action"], m.get("name") or label))

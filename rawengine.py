# -*- coding: utf-8 -*-
"""
T6 键位映射引擎
- 用 Raw Input (RIDEV_INPUTSINK) 接收全局输入，并按设备来源区分遥控器 / 本机键盘
- 用低级键盘钩子 (WH_KEYBOARD_LL) 在需要时屏蔽遥控器按键的原始行为
- 捕获到的遥控器按键通过回调抛给 GUI；映射动作在引擎线程内执行
"""
import ctypes
import queue
import threading
import time
from collections import deque
from ctypes import wintypes
from ctypes.wintypes import (DWORD, HANDLE, HWND, INT, LONG,
                             UINT, ULONG, USHORT, WORD)

# 注意：ctypes.wintypes 里的 WPARAM/LPARAM 是 32 位，64 位下必须自己定义
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
RIDEV_NOLEGACY = 0x00000030  # 禁止该通道生成系统默认行为（如 AC Search 打开搜索）

WM_INPUT = 0x00FF
WM_TIMER = 0x0113
WM_QUIT = 0x0012
WM_DESTROY = 0x0002

RI_KEY_MAKE = 0
RI_KEY_BREAK = 1

RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
LLKHF_INJECTED = 0x10

CORRELATE_MS = 200  # 钩子事件与 Raw Input 事件的关联时间窗


# ---------- 结构体 ----------
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


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", DWORD), ("scanCode", DWORD), ("flags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", HWND), ("message", UINT), ("wParam", WPARAM),
                ("lParam", LPARAM), ("time", DWORD), ("pt", POINT)]


WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, INT, WPARAM, LPARAM)


def _set_prototypes():
    """显式声明 64 位参数/返回值，避免 ctypes 默认 int 截断"""
    user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.CallNextHookEx.argtypes = [HANDLE, INT, WPARAM, LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    user32.SetWindowsHookExW.argtypes = [INT, HOOKPROC, HANDLE, DWORD]
    user32.SetWindowsHookExW.restype = HANDLE
    user32.UnhookWindowsHookEx.argtypes = [HANDLE]
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


def tick_ms():
    return kernel32.GetTickCount64() & 0xFFFFFFFF


def enumerate_devices():
    """返回 [(hDevice, dwType, name)]"""
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
    """按设备路径子串（如蓝牙 MAC）找设备句柄，找不到返回 None"""
    for h, t, name in enumerate_devices():
        if match.lower() in name.lower():
            return h
    return None


class Engine:
    def __init__(self, device_match="", on_capture=None, on_log=None):
        self.device_match = device_match
        self.on_capture = on_capture or (lambda e: None)
        self.on_log = on_log or (lambda m: None)
        self.mappings = []          # list[dict]: {sig_kind, sig, name, action, block, enabled}
        self._lock = threading.Lock()
        self._thread = None
        self._thread_id = None
        self._hwnd = None
        self._hook = None
        self._running = threading.Event()
        self._raw_events = deque(maxlen=64)   # (tick, hDevice, kind, vk_or_None)
        self._action_q = queue.Queue()
        self._devname_cache = {}
        self._wndproc_ref = None
        self._hookproc_ref = None

    # ---------- 生命周期 ----------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True, name="T6Engine")
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

    def device_present(self):
        return find_device_handle(self.device_match) is not None

    # ---------- 引擎线程 ----------
    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        class_name = "T6KeyMapperEngineWnd"
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        wndclass = WNDCLASSEXW()
        wndclass.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wndclass.lpfnWndProc = self._wndproc_ref
        wndclass.hInstance = kernel32.GetModuleHandleW(None)
        wndclass.lpszClassName = class_name
        if not user32.RegisterClassExW(ctypes.byref(wndclass)):
            err = kernel32.GetLastError()
            if err != 1410:  # 类已注册
                self.on_log("注册窗口类失败: %s" % err)
                return
        HWND_MESSAGE = ctypes.c_void_p(-3)
        self._hwnd = user32.CreateWindowExW(0, class_name, "T6Engine", 0,
                                            0, 0, 0, 0, HWND_MESSAGE, None,
                                            wndclass.hInstance, None)
        if not self._hwnd:
            self.on_log("创建消息窗口失败")
            return
        regs = [
            (0x01, 0x06, RIDEV_INPUTSINK),                  # 键盘
            (0x01, 0x02, RIDEV_INPUTSINK),                  # 鼠标
            (0x0C, 0x01, RIDEV_INPUTSINK | RIDEV_NOLEGACY), # 消费控制（音量/媒体/搜索等）
        ]
        for page, usage, flags in regs:
            one = (RAWINPUTDEVICE * 1)(RAWINPUTDEVICE(page, usage, flags, self._hwnd))
            if not user32.RegisterRawInputDevices(one, 1, ctypes.sizeof(RAWINPUTDEVICE)):
                err = kernel32.GetLastError()
                if flags & RIDEV_NOLEGACY:
                    # NOLEGACY 仅键鼠合法，其他通道回退为普通注册
                    one = (RAWINPUTDEVICE * 1)(
                        RAWINPUTDEVICE(page, usage, RIDEV_INPUTSINK, self._hwnd))
                    if user32.RegisterRawInputDevices(one, 1, ctypes.sizeof(RAWINPUTDEVICE)):
                        self.on_log("通道 0x%02X 已注册（NOLEGACY 不支持此通道，已回退）" % page)
                        continue
                self.on_log("注册 Raw Input 失败 page=0x%02X err=%s" % (page, err))
                return
            elif flags & RIDEV_NOLEGACY:
                self.on_log("通道 0x%02X 已注册（含 NOLEGACY 屏蔽）" % page)

        self._hookproc_ref = HOOKPROC(self._hook_proc)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hookproc_ref, None, 0)
        if not self._hook:
            self.on_log("安装键盘钩子失败（屏蔽原键功能不可用）")

        user32.SetTimer(self._hwnd, 1, 25, None)  # 动作队列泵
        self.on_log("引擎已启动")
        msg = MSG()
        while self._running.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        user32.DestroyWindow(self._hwnd)
        self.on_log("引擎已停止")

    # ---------- 窗口过程 ----------
    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            try:
                self._handle_raw(lparam)
            except Exception as e:
                self.on_log("Raw Input 处理异常: %s" % e)
            return 0
        if msg == WM_TIMER:
            self._pump_actions()
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

    # ---------- Raw Input ----------
    def _dev_name(self, hdev):
        if hdev not in self._devname_cache:
            size = UINT(0)
            user32.GetRawInputDeviceInfoA(hdev, RIDI_DEVICENAME, None, ctypes.byref(size))
            buf = (ctypes.c_char * size.value)()
            user32.GetRawInputDeviceInfoA(hdev, RIDI_DEVICENAME, buf, ctypes.byref(size))
            self._devname_cache[hdev] = buf.value.decode("utf-8", "replace")
        return self._devname_cache[hdev]

    def _is_target(self, hdev):
        return self.device_match.lower() in self._dev_name(hdev).lower()

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
        is_t6 = self._is_target(hdev)
        now = tick_ms()

        if raw.header.dwType == RIM_TYPEKEYBOARD:
            kb = raw.data.keyboard
            down = (kb.Flags & 0x01) == RI_KEY_MAKE
            vk = kb.VKey
            self._raw_events.append((now, hdev, "kbd", vk))
            if is_t6 and down:
                self._dispatch(("kbd", vk), vk_display(vk))
            if is_t6:
                self.on_capture({"kind": "kbd", "vk": vk, "name": vk_display(vk),
                                 "down": down, "sig": ["kbd", vk]})
        elif raw.header.dwType == RIM_TYPEHID:
            hid = raw.data.hid
            off = hdr_size + 8
            n = hid.dwSizeHid * hid.dwCount
            if n > 0:
                data = bytes(bytearray(buf[off:off + n]))
                hexstr = data.hex(" ")
                self._raw_events.append((now, hdev, "hid", None))
                if is_t6:
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
                self._raw_events.append((now, hdev, "mouse", None))
                if is_t6:
                    self._dispatch(("mouse", btn), "鼠标" + btn)
                    self.on_capture({"kind": "mouse", "button": btn,
                                     "down": True, "sig": ["mouse", btn]})

    # ---------- 键盘钩子（仅用于屏蔽原键） ----------
    def _hook_proc(self, ncode, wparam, lparam):
        if ncode == HC_ACTION and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not (info.flags & LLKHF_INJECTED):  # 不屏蔽自己 SendInput 出去的键
                with self._lock:
                    maps = [m for m in self.mappings
                            if m.get("enabled", True) and m.get("block")
                            and m.get("sig_kind") == "kbd"
                            and m.get("sig") == info.vkCode]
                if maps and self._came_from_target(info.time, info.vkCode):
                    return 1
        return user32.CallNextHookEx(None, ncode, wparam, lparam)

    def _came_from_target(self, hook_time, vk):
        now = tick_ms()
        for (t, hdev, kind, ev_vk) in reversed(self._raw_events):
            if abs(((now - t) & 0xFFFFFFFF)) > CORRELATE_MS:
                break
            if self._is_target(hdev) and (ev_vk == vk or kind == "hid"):
                return True
        return False

    # ---------- 映射派发 ----------
    def _dispatch(self, sig, label):
        with self._lock:
            maps = [m for m in self.mappings
                    if m.get("enabled", True)
                    and m.get("sig_kind") == sig[0] and m.get("sig") == sig[1]]
        for m in maps:
            self._action_q.put((m["action"], m.get("name") or label))
            if m.get("block") and sig[0] == "hid":
                # HID 消费控制键的系统默认行为（如打开搜索）：动作执行的同时监视并关闭
                threading.Thread(target=actions.suppress_search_window,
                                 daemon=True).start()

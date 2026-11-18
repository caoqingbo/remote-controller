# -*- coding: utf-8 -*-
"""动作执行：组合键 / 文本输入 / 启动程序 / 音量媒体 / 运行命令"""
import ctypes
import subprocess
from ctypes import wintypes
from ctypes.wintypes import DWORD, LONG, WORD, ULONG

from vkdefs import parse_combo

user32 = ctypes.windll.user32

ULONG_PTR = ctypes.c_size_t
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                ("dwFlags", DWORD), ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", DWORD), ("union", _INPUT_UNION)]


def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(arr), arr, ctypes.sizeof(INPUT))
    if sent != len(arr):
        raise ctypes.WinError()


def _kbd(vk=0, scan=0, flags=0):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def _mouse(dx=0, dy=0, data=0, flags=0):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi = MOUSEINPUT(dx, dy, data, flags, 0, 0)
    return inp


KEYEVENTF_EXTENDEDKEY = 0x0001
# 扩展键（右Alt/右Ctrl/方向键等），SendInput 需要 EXTENDEDKEY 标志才能被正确识别
_EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
                 0x2D, 0x2E, 0x5B, 0x5C, 0xA3, 0xA5, 0x6F, 0x90, 0xA6, 0xA7}

def send_combo(vks):
    """通过 Windows SendInput 发送组合键，不依赖任何第三方驱动。"""
    seq = []
    for v in vks:
        flags = KEYEVENTF_EXTENDEDKEY if v in _EXTENDED_VKS else 0
        seq.append(_kbd(vk=v, flags=flags))
    for v in reversed(vks):
        flags = KEYEVENTF_EXTENDEDKEY if v in _EXTENDED_VKS else 0
        seq.append(_kbd(vk=v, flags=flags | KEYEVENTF_KEYUP))
    _send(seq)


def send_text(text):
    seq = []
    for ch in text:
        code = ord(ch)
        seq.append(_kbd(scan=code, flags=KEYEVENTF_UNICODE))
        seq.append(_kbd(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    _send(seq)


def run_command(cmd):
    subprocess.Popen(cmd, shell=True,
                     creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)


def _proc_name(pid):
    """按 PID 取进程镜像名（不带路径则返回全路径，调用方自己小写比较）"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = DWORD(512)
        ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        return buf.value if ok else ""
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def suppress_search_window(timeout=1.8):
    """监视并关闭刚弹出的 Windows 搜索面板（SearchHost）。
    用于屏蔽 HID 消费控制键（如 AC Search）的系统默认行为。
    在 timeout 秒内轮询前台窗口，发现搜索面板即发送 Esc 关闭。"""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            pid = DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            name = _proc_name(pid.value).lower()
            if any(k in name for k in ("searchhost", "searchapp",
                                       "startmenuexperiencehost", "searchui")):
                send_combo([0x1B])  # Esc 关闭搜索面板
                return True
        time.sleep(0.03)
    return False


_CLICK_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def mouse_action(spec: str):
    """鼠标动作。语法：
    click_left / click_right / click_middle   单击
    double_left                               双击
    down_left / up_left（right/middle 同理）  按住/松开（可用于拖拽）
    scroll_up [格数] / scroll_down [格数]      垂直滚轮（默认 1）
    scroll_left [格数] / scroll_right [格数]   水平滚轮
    move dx dy                                相对移动光标（像素）
    moveto x y                                移动光标到绝对坐标
    """
    parts = spec.lower().split()
    if not parts:
        raise ValueError("鼠标动作为空")
    cmd = parts[0]

    if cmd.startswith("click_") or cmd.startswith("double_") or \
            cmd.startswith("down_") or cmd.startswith("up_"):
        op, _, btn = cmd.partition("_")
        if btn not in _CLICK_FLAGS:
            raise ValueError("未知鼠标键: %s" % btn)
        down, up = _CLICK_FLAGS[btn]
        if op == "click":
            _send([_mouse(flags=down), _mouse(flags=up)])
        elif op == "double":
            _send([_mouse(flags=down), _mouse(flags=up),
                   _mouse(flags=down), _mouse(flags=up)])
        elif op == "down":
            _send([_mouse(flags=down)])
        elif op == "up":
            _send([_mouse(flags=up)])
    elif cmd.startswith("scroll_"):
        n = int(parts[1]) if len(parts) > 1 else 1
        direction = cmd.split("_", 1)[1]
        if direction == "up":
            _send([_mouse(data=120 * n, flags=MOUSEEVENTF_WHEEL)])
        elif direction == "down":
            _send([_mouse(data=-120 * n, flags=MOUSEEVENTF_WHEEL)])
        elif direction == "left":
            _send([_mouse(data=-120 * n, flags=MOUSEEVENTF_HWHEEL)])
        elif direction == "right":
            _send([_mouse(data=120 * n, flags=MOUSEEVENTF_HWHEEL)])
        else:
            raise ValueError("未知滚轮方向: %s" % direction)
    elif cmd == "move":
        dx, dy = int(parts[1]), int(parts[2])
        _send([_mouse(dx=dx, dy=dy, flags=MOUSEEVENTF_MOVE)])
    elif cmd == "moveto":
        x, y = int(parts[1]), int(parts[2])
        if not user32.SetCursorPos(x, y):
            raise ctypes.WinError()
    else:
        raise ValueError("未知鼠标动作: %s" % cmd)


def execute_action(action: dict):
    """action = {"type": ..., "value": ...}"""
    t = action.get("type")
    v = action.get("value", "")
    if t == "combo":
        send_combo(parse_combo(v))
    elif t == "text":
        send_text(v)
    elif t == "run":
        run_command(v)
    elif t == "volume":
        send_combo(parse_combo(v))
    elif t == "media":
        send_combo(parse_combo(v))
    elif t == "mouse":
        mouse_action(v)
    else:
        raise ValueError("未知动作类型: %s" % t)


ACTION_TYPES = [
    ("combo", "组合键（如 ctrl+c、win+d）"),
    ("text", "输入一段文本"),
    ("run", "启动程序 / 运行命令"),
    ("volume", "音量控制（volumeup / volumedown / mute）"),
    ("media", "媒体键（playpause / nexttrack / prevtrack / stop）"),
    ("mouse", "鼠标（click_left / double_left / scroll_up / move 0 50 …）"),
]

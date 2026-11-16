# -*- coding: utf-8 -*-
import ctypes
import ctypes.wintypes
import os
import time
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import actions

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def kimi_windows():
    out = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            out.append((hwnd, pid.value, buf.value))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), None)
    return out


before = {h: t for h, p, t in kimi_windows()}
print("before windows:", len(before))
actions.send_combo([0xA4, ord('K')])   # 左Alt+K
time.sleep(1.5)
after = {h: t for h, p, t in kimi_windows()}
new = {h: t for h, t in after.items() if h not in before}
print("new windows after LAlt+K:", new if new else "(none)")

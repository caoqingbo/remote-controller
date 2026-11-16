# -*- coding: utf-8 -*-
"""
Interception 驱动级按键发送
通过 Interception 内核驱动生成与真实硬件无异的键盘输入，
可唤醒那些会忽略 SendInput 注入按键的程序（如 Kimi 启动器）。
需要 Interception 驱动已安装并重启过一次。
"""
import ctypes
import os

_DLL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "interception.dll")

INTERCEPTION_KEY_DOWN = 0x00
INTERCEPTION_KEY_UP = 0x01
INTERCEPTION_KEY_E0 = 0x02  # 扩展键标志（右Alt/右Ctrl/方向键等）


class InterceptionKeyStroke(ctypes.Structure):
    _fields_ = [("code", ctypes.c_ushort),
                ("state", ctypes.c_ushort),
                ("information", ctypes.c_uint)]


_ctx = None
_ic = None


def _get_ctx():
    global _ctx, _ic
    if _ic is None:
        if not os.path.exists(_DLL_PATH):
            raise RuntimeError("interception.dll 不存在")
        _ic = ctypes.CDLL(_DLL_PATH)
        _ic.interception_create_context.restype = ctypes.c_void_p
        _ic.interception_create_context.argtypes = []
        _ic.interception_send.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          ctypes.c_void_p, ctypes.c_uint]
        _ic.interception_send.restype = ctypes.c_int
        _ic.interception_destroy_context.argtypes = [ctypes.c_void_p]
        _ctx = _ic.interception_create_context()
        if not _ctx:
            raise RuntimeError("Interception 驱动未就绪（未安装或未重启）")
    return _ic, _ctx


def available():
    try:
        _get_ctx()
        return True
    except Exception:
        return False


# 需要 E0 扩展标志的虚拟键
_EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
                 0x2D, 0x2E, 0x5B, 0x5C, 0xA3, 0xA5, 0x6F, 0x90, 0xA6, 0xA7}


def _stroke(vk, up):
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0) & 0xFF
    state = INTERCEPTION_KEY_UP if up else INTERCEPTION_KEY_DOWN
    if vk in _EXTENDED_VKS:
        state |= INTERCEPTION_KEY_E0
    return InterceptionKeyStroke(scan, state, 0)


def send_combo(vks):
    """以驱动级方式发送组合键"""
    ic, ctx = _get_ctx()
    strokes = [_stroke(v, False) for v in vks]
    strokes += [_stroke(v, True) for v in reversed(vks)]
    arr = (InterceptionKeyStroke * len(strokes))(*strokes)
    sent = ic.interception_send(ctx, 1, arr, len(arr))  # 1 = 第一个键盘设备
    if sent != len(arr):
        raise RuntimeError("interception_send 发送不完整")

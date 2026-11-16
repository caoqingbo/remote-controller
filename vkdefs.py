# -*- coding: utf-8 -*-
"""虚拟键码与名称对照表（覆盖常用键，含媒体键）"""

VK_NAME = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x10: "Shift", 0x11: "Ctrl",
    0x12: "Alt", 0x13: "Pause", 0x14: "CapsLock", 0x1B: "Esc", 0x20: "Space",
    0x21: "PageUp", 0x22: "PageDown", 0x23: "End", 0x24: "Home",
    0x25: "左方向键", 0x26: "上方向键", 0x27: "右方向键", 0x28: "下方向键",
    0x2C: "PrintScreen", 0x2D: "Insert", 0x2E: "Delete",
    0x5B: "左Win", 0x5C: "右Win", 0x5D: "菜单键",
    0x6A: "小键盘*", 0x6B: "小键盘+", 0x6D: "小键盘-", 0x6E: "小键盘.", 0x6F: "小键盘/",
    0x90: "NumLock", 0x91: "ScrollLock",
    0xA0: "左Shift", 0xA1: "右Shift", 0xA2: "左Ctrl", 0xA3: "右Ctrl",
    0xA4: "左Alt", 0xA5: "右Alt",
    0xAD: "静音", 0xAE: "音量减", 0xAF: "音量加",
    0xB0: "下一曲", 0xB1: "上一曲", 0xB2: "停止播放", 0xB3: "播放/暂停",
    0xB4: "启动邮件", 0xB5: "启动媒体选择", 0xB6: "启动应用1", 0xB7: "启动应用2",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}
# 字母与数字
for _c in range(0x30, 0x3A):
    VK_NAME[_c] = chr(_c)
for _c in range(0x41, 0x5B):
    VK_NAME[_c] = chr(_c)
for _i in range(12):
    VK_NAME[0x70 + _i] = "F%d" % (_i + 1)
for _c in range(0x60, 0x6A):
    VK_NAME[_c] = "小键盘%d" % (_c - 0x60)

# 名称 → VK（用于解析用户输入的组合键）
VK_BY_NAME = {}
for _vk, _n in VK_NAME.items():
    VK_BY_NAME[_n.lower()] = _vk
VK_BY_NAME.update({
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
    "lctrl": 0xA2, "rctrl": 0xA3, "lshift": 0xA0, "rshift": 0xA1,
    "lalt": 0xA4, "ralt": 0xA5, "lwin": 0x5B, "rwin": 0x5C,
    "win": 0x5B, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "tab": 0x09, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "pgup": 0x21, "pgdn": 0x22, "insert": 0x2D, "ins": 0x2D,
    "volumeup": 0xAF, "volumedown": 0xAE, "mute": 0xAD,
    "playpause": 0xB3, "nexttrack": 0xB0, "prevtrack": 0xB1, "stop": 0xB2,
    "printscreen": 0x2C, "capslock": 0x14, "menu": 0x5D,
})
for _i in range(1, 13):
    VK_BY_NAME["f%d" % _i] = 0x6F + _i


def vk_display(vk: int) -> str:
    return VK_NAME.get(vk, "VK 0x%02X" % vk)


def parse_combo(text: str):
    """把 'ctrl+shift+s' 解析成 [0x11, 0x10, 0x53]，非法键名抛 ValueError"""
    parts = [p.strip() for p in text.replace(" ", "+").split("+") if p.strip()]
    if not parts:
        raise ValueError("组合键为空")
    vks = []
    for p in parts:
        key = p.lower()
        if len(p) == 1:
            vks.append(ord(p.upper()))
        elif key in VK_BY_NAME:
            vks.append(VK_BY_NAME[key])
        else:
            raise ValueError("无法识别的键名: %s" % p)
    return vks

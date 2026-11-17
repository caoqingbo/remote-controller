# -*- coding: utf-8 -*-
"""T6 KeyMapper — 图形界面"""
import json
import os
import queue
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import rawengine
from actions import ACTION_TYPES
from vkdefs import vk_display

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "T6KeyMapper"


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # device_match 为空表示尚未指定设备（学习时显示所有设备的按键）
        return {"device_match": "", "mappings": [], "autostart": False}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def set_autostart(enabled):
    import winreg
    supervisor = os.path.join(BASE_DIR, "tools", "supervisor.ps1")
    if os.path.exists(supervisor):
        # 走守护进程：开机启动后崩溃也能自动拉起
        target = ('powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
                  '-File "%s"' % supervisor)
    else:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        target = '"%s" "%s"' % (pythonw if os.path.exists(pythonw) else sys.executable,
                                os.path.join(BASE_DIR, "app.py"))
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, target)
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def get_autostart():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return bool(winreg.QueryValueEx(k, APP_NAME)[0])
    except Exception:
        return False


def sig_text(kind, sig):
    if kind == "kbd":
        return "键盘: " + vk_display(sig)
    if kind == "mouse":
        return "鼠标: " + {"left": "左键", "right": "右键", "middle": "中键"}.get(sig, sig)
    return "HID: " + str(sig)


# 每种动作类型的完整可选值说明（显示在动作类型下方）
ACTION_HINTS = {
    "combo": "用 + 连接：ctrl+c、alt+f4、win+d、shift+s、lalt+k、ralt、enter、esc、f5、tab、space、"
             "backspace、delete、home、end、pageup、pagedown、up/down/left/right…",
    "text": "直接输入要自动打出的文字（支持中文）",
    "run": "程序名或命令：notepad（记事本）、calc（计算器）、mspaint（画图）、"
           "explorer（资源管理器）、或程序完整路径",
    "volume": "volumeup（音量+）、volumedown（音量-）、mute（静音切换）",
    "media": "playpause（播放/暂停）、nexttrack（下一曲）、prevtrack（上一曲）、stop（停止）",
    "mouse": "click_left / click_right / click_middle（单击左/右/中键）、double_left（双击）、"
             "scroll_up / scroll_down（滚轮，可加格数如 scroll_up 3）、scroll_left / scroll_right（水平滚轮）、"
             "move 0 50（相对移动，像素）、moveto 960 540（移动到绝对坐标）、"
             "down_left / up_left（按住/松开，配合做拖拽）",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Remote KeyMapper — HID 遥控器键位映射（支持 T6 等任意 HID 遥控器）")
        self.geometry("780x600")
        self.cfg = load_config()
        self.ui_q = queue.Queue()
        self.learning = False
        self.learn_pending = None
        self.engine = rawengine.Engine(
            device_match=self.cfg.get("device_match", ""),
            on_capture=lambda e: self.ui_q.put(("capture", e)),
            on_log=lambda m: self.ui_q.put(("log", m)),
        )
        self.mappings = list(self.cfg.get("mappings", []))
        self._build_ui()
        self._refresh_device_status()
        self.after(50, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # 打开软件即自动启动映射引擎
        self.engine.set_mappings(self.mappings)
        self.engine.start()
        self.engine_btn.config(text="停止映射引擎")
        # 引擎看门狗：引擎线程异常退出时自动拉起（防止后台崩溃导致映射全失效）
        self._engine_wanted = True
        self.after(3000, self._watch_engine)

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.dev_var = tk.StringVar(value="设备检测中…")
        ttk.Label(top, textvariable=self.dev_var, font=("", 10, "bold")).pack(side="left")
        ttk.Button(top, text="刷新检测", command=self._refresh_device_status).pack(side="left", padx=8)
        ttk.Button(top, text="选择设备", command=self._pick_device).pack(side="left")
        self.engine_btn = ttk.Button(top, text="启动映射引擎", command=self._toggle_engine)
        self.engine_btn.pack(side="right")
        self.auto_var = tk.BooleanVar(value=get_autostart())
        ttk.Checkbutton(top, text="开机自启", variable=self.auto_var,
                        command=lambda: set_autostart(self.auto_var.get())).pack(side="right", padx=8)

        mid = ttk.Frame(self, padding=8)
        mid.pack(fill="both", expand=True)

        # --- 学习区 ---
        learn = ttk.LabelFrame(mid, text="① 学习按键：点击“开始学习”，然后按下遥控器上的键", padding=8)
        learn.pack(fill="x", pady=(0, 8))
        self.learn_btn = ttk.Button(learn, text="开始学习", command=self._start_learn)
        self.learn_btn.pack(side="left")
        self.learn_var = tk.StringVar(value="尚未捕获按键")
        ttk.Label(learn, textvariable=self.learn_var, foreground="#0066cc").pack(side="left", padx=12)

        # --- 动作编辑区 ---
        edit = ttk.LabelFrame(mid, text="② 设置这个动作", padding=8)
        edit.pack(fill="x", pady=(0, 8))
        row1 = ttk.Frame(edit); row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="名称:").pack(side="left")
        self.name_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.name_var, width=18).pack(side="left", padx=(4, 12))
        ttk.Label(row1, text="动作类型:").pack(side="left")
        self.act_type = ttk.Combobox(row1, state="readonly", width=34,
                                     values=["%s — %s" % (k, v) for k, v in ACTION_TYPES])
        self.act_type.current(0)
        self.act_type.pack(side="left", padx=4)
        row2 = ttk.Frame(edit); row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="动作内容:").pack(side="left")
        self.act_val = tk.StringVar()
        self.act_entry = ttk.Entry(row2, textvariable=self.act_val, width=32)
        self.act_entry.pack(side="left", padx=4)
        self.record_btn = ttk.Button(row2, text="⌨ 按键录入", command=self._arm_record)
        self.record_btn.pack(side="left", padx=2)
        self.block_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="屏蔽遥控器原键功能", variable=self.block_var).pack(side="left", padx=8)
        ttk.Button(row2, text="保存映射", command=self._save_mapping).pack(side="right")
        # 动作类型完整选项说明（随选择联动）
        self.act_hint = tk.StringVar()
        ttk.Label(edit, textvariable=self.act_hint, foreground="#555555",
                  wraplength=740, justify="left").pack(fill="x", pady=(2, 0))
        self.act_type.bind("<<ComboboxSelected>>", lambda e: self._update_hint())
        self._update_hint()

        # --- 映射列表 ---
        lst = ttk.LabelFrame(mid, text="③ 已保存的映射", padding=8)
        lst.pack(fill="both", expand=True, pady=(0, 8))
        cols = ("name", "sig", "action", "block", "enabled")
        self.tree = ttk.Treeview(lst, columns=cols, show="headings", height=8)
        for c, t, w in [("name", "名称", 120), ("sig", "遥控器按键", 200),
                        ("action", "动作", 220), ("block", "屏蔽原键", 70), ("enabled", "启用", 60)]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lst, orient="vertical", command=self.tree.yview)
        sb.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        btns = ttk.Frame(lst); btns.pack(side="left", fill="y", padx=6)
        ttk.Button(btns, text="启用/禁用", command=self._toggle_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="删除", command=self._delete_selected).pack(fill="x", pady=2)

        # --- 日志 ---
        logf = ttk.LabelFrame(self, text="日志（按遥控器按键时这里会实时显示识别结果）", padding=4)
        logf.pack(fill="both", padx=8, pady=(0, 8))
        self.log = tk.Text(logf, height=6, state="disabled", wrap="none")
        self.log.pack(fill="both", expand=True)

    # ---------------- 引擎 ----------------
    def _update_hint(self):
        t = self.act_type.get().split(" — ")[0]
        self.act_hint.set("可选值 → " + ACTION_HINTS.get(t, ""))

    def _toggle_engine(self):
        if self.engine.is_running():
            self._engine_wanted = False
            self.engine.stop()
            self.engine_btn.config(text="启动映射引擎")
        else:
            self._engine_wanted = True
            self.engine.set_mappings(self.mappings)
            self.engine.start()
            self.engine_btn.config(text="停止映射引擎")

    def _watch_engine(self):
        # 看门狗：期望运行但线程已死 → 自动重启引擎并记录日志
        if self._engine_wanted and not self.engine.is_running():
            self._log("⚠ 引擎线程意外退出，正在自动重启…")
            try:
                self.engine.set_mappings(self.mappings)
                self.engine.start()
                self._log("✅ 引擎已自动恢复")
                self.engine_btn.config(text="停止映射引擎")
            except Exception as e:
                self._log("引擎自动重启失败: %s" % e)
        if self.winfo_exists():
            self.after(3000, self._watch_engine)

    def _refresh_device_status(self):
        match = self.cfg.get("device_match", "")
        if not match:
            self.dev_var.set("⚠ 未指定遥控器 — 请按一下遥控器任意键，或点「选择设备」")
            return
        ok = rawengine.find_device_handle(match) is not None
        self.dev_var.set(("✅ 目标设备已连接" if ok else "❌ 未检测到目标设备") +
                         "（匹配码 %s）" % match)

    # ---------------- 设备选择 ----------------
    TYPE_NAME = {0: "鼠标", 1: "键盘", 2: "HID"}

    @staticmethod
    def match_token(device_path):
        """从设备路径提取稳定标识：蓝牙设备取 MAC 段，USB 设备取 VID_PID 段"""
        try:
            seg = device_path.split("#")[1]      # \\?\HID#<这里>#...
            return seg.split("&Col")[0]          # 去掉集合后缀
        except Exception:
            return device_path

    def _pick_device(self):
        devs = rawengine.enumerate_devices()
        if not devs:
            messagebox.showinfo("提示", "系统没有可用的输入设备")
            return
        win = tk.Toplevel(self)
        win.title("选择遥控器设备")
        win.geometry("640x360")
        ttk.Label(win, text="双击选择你的遥控器对应的设备（可选其一，同类接口会一起匹配）：",
                  padding=(8, 6)).pack(anchor="w")
        lb = tk.Listbox(win, font=("Consolas", 9))
        lb.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        for h, t, name in devs:
            lb.insert("end", "[%s] %s" % (self.TYPE_NAME.get(t, str(t)), name))

        def choose(index):
            if index < 0:
                return
            path = devs[index][2]
            token = self.match_token(path)
            self.cfg["device_match"] = token
            save_config(self.cfg)
            self.engine.set_device_match(token)
            win.destroy()
            self._refresh_device_status()
            self._log("已指定目标设备: " + token)

        lb.bind("<Double-Button-1>", lambda e: choose(lb.curselection()[0] if lb.curselection() else -1))
        ttk.Button(win, text="选为遥控器",
                   command=lambda: choose(lb.curselection()[0] if lb.curselection() else -1)).pack(pady=6)

    # ---------------- 学习 ----------------
    def _start_learn(self):
        if not self.engine.is_running():
            self._toggle_engine()
        self.learning = True
        self.learn_pending = None
        self.learn_var.set("请按下遥控器上的任意按键…")
        self.learn_btn.config(state="disabled")

    def _learn_capture(self, ev):
        if ev["kind"] == "kbd" and ev["down"]:
            self._finish_learn(("kbd", ev["vk"]))
        elif ev["kind"] in ("hid", "mouse"):
            if self.learn_pending is not None:
                return  # 一次连发只取第一个事件（按下），忽略随后的松开报告
            sig = (ev["kind"], ev["bytes"] if ev["kind"] == "hid" else ev["button"])
            self.learn_pending = sig
            # 等一下看是否伴随键盘事件（媒体键会被系统翻译成键盘事件，优先用键盘签名）
            self.after(350, self._finalize_pending)

    def _finalize_pending(self):
        if self.learning and self.learn_pending:
            self._finish_learn(self.learn_pending)

    def _finish_learn(self, sig):
        self.learning = False
        self.learn_pending = None
        self.learn_btn.config(state="normal")
        self.learn_var.set("已捕获: " + sig_text(*sig))
        self._learned_sig = sig
        self.name_var.set(sig_text(*sig).split(": ", 1)[-1] + " 映射")
        self._log("学习成功 → " + sig_text(*sig))

    # ---------------- 按键录入 ----------------
    KEYSYM_MAP = {
        "return": "enter", "escape": "esc", "backspace": "backspace",
        "delete": "delete", "tab": "tab", "space": "space",
        "up": "up", "down": "down", "left": "left", "right": "right",
        "home": "home", "end": "end", "prior": "pageup", "next": "pagedown",
        "insert": "insert", "caps_lock": "capslock", "num_lock": "numlock",
        "print": "printscreen", "pause": "pause", "menu": "menu",
    }
    MODIFIER_KEYSYMS = {"shift_l", "shift_r", "control_l", "control_r",
                        "alt_l", "alt_r", "super_l", "super_r", "meta_l", "meta_r"}

    def _arm_record(self):
        self.act_val.set("")
        self.record_btn.config(text="请按下组合键…", state="disabled")
        self.act_entry.focus_set()
        self.bind("<KeyPress>", self._record_key)

    def _record_key(self, event):
        keysym = event.keysym.lower()
        if keysym in self.MODIFIER_KEYSYMS:
            return "break"  # 等真正的键
        parts = []
        if event.state & 0x0004:
            parts.append("ctrl")
        if event.state & 0x0001:
            parts.append("shift")
        if event.state & 0x20000 or event.state & 0x0008:
            parts.append("alt")
        if keysym.startswith("f") and keysym[1:].isdigit():
            parts.append(keysym)
        elif len(event.keysym) == 1:
            parts.append(keysym)
        else:
            parts.append(self.KEYSYM_MAP.get(keysym, keysym))
        self.act_val.set("+".join(parts))
        self.unbind("<KeyPress>")
        self.record_btn.config(text="⌨ 按键录入", state="normal")
        self._log("已录入按键: " + self.act_val.get())
        return "break"

    # ---------------- 映射管理 ----------------
    def _save_mapping(self):
        sig = getattr(self, "_learned_sig", None)
        if not sig:
            messagebox.showwarning("提示", "请先点击“开始学习”并按一下遥控器按键")
            return
        t = self.act_type.get().split(" — ")[0]
        v = self.act_val.get().strip()
        if not v:
            messagebox.showwarning("提示", "请填写动作内容")
            return
        if t in ("combo", "volume", "media"):
            from vkdefs import parse_combo
            try:
                parse_combo(v)
            except ValueError as e:
                messagebox.showerror("组合键无效", "无法解析「%s」：%s\n\n"
                                     "请用英文键名，如 ctrl+c、alt+f4、lalt+k、esc、enter" % (v, e))
                return
        m = {"sig_kind": sig[0], "sig": sig[1], "name": self.name_var.get().strip() or "未命名",
             "action": {"type": t, "value": v},
             "block": self.block_var.get() and sig[0] in ("kbd", "hid"), "enabled": True}
        self.mappings = [x for x in self.mappings
                         if not (x["sig_kind"] == m["sig_kind"] and x["sig"] == m["sig"])]
        self.mappings.append(m)
        self._persist()
        self._log("已保存映射: %s → %s %s" % (m["name"], t, v))

    def _toggle_selected(self):
        for iid in self.tree.selection():
            i = int(iid)
            self.mappings[i]["enabled"] = not self.mappings[i].get("enabled", True)
        self._persist()

    def _delete_selected(self):
        for iid in sorted(self.tree.selection(), key=int, reverse=True):
            del self.mappings[int(iid)]
        self._persist()

    def _persist(self):
        self.cfg["mappings"] = self.mappings
        save_config(self.cfg)
        self.engine.set_mappings(self.mappings)
        self._reload_tree()

    def _reload_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, m in enumerate(self.mappings):
            self.tree.insert("", "end", iid=str(i), values=(
                m.get("name", ""), sig_text(m["sig_kind"], m["sig"]),
                "%s: %s" % (m["action"]["type"], m["action"]["value"]),
                "是" if m.get("block") else "否",
                "✓" if m.get("enabled", True) else "✗"))

    # ---------------- 队列与日志 ----------------
    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.ui_q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "capture":
                    ev = payload
                    if ev.get("down", True):
                        self._log("捕获: " + sig_text(ev["sig"][0], ev["sig"][1]))
                    if self.learning:
                        self._learn_capture(ev)
        except queue.Empty:
            pass
        self.after(50, self._poll_queue)

    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _on_close(self):
        self.engine.stop()
        # 通知守护进程这是正常关闭，不要自动重启
        try:
            with open(os.path.join(BASE_DIR, "quit.flag"), "w") as f:
                f.write("quit")
        except Exception:
            pass
        self.destroy()


def _ensure_single_instance():
    """单实例锁：已有实例运行时，激活它的窗口并退出当前进程"""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, "RemoteKeyMapper_SingleInstance")
    if kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return  # 我是第一个实例，继续启动
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if n > 0:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if "remote keymapper" in buf.value.lower():
                user32.ShowWindow(hwnd, 9)          # SW_RESTORE
                user32.SetForegroundWindow(hwnd)    # 拉到前台
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    # 已有实例在跑：写 quit.flag 让守护进程也退出（否则会每 3 秒重启我一次）
    try:
        with open(os.path.join(BASE_DIR, "quit.flag"), "w") as f:
            f.write("duplicate")
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    _ensure_single_instance()
    app = App()
    app._reload_tree()
    app.mainloop()

# -*- coding: utf-8 -*-
"""开发调试：枚举 Raw Input 设备，并 20 秒捕获按键事件"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rawengine

devs = rawengine.enumerate_devices()
print("枚举到 %d 个 Raw Input 设备" % len(devs))
for h, t, n in devs:
    print("  type=%d  %s" % (t, n))

print("--- 开始 20 秒捕获，请按遥控器按键 ---")
events = []
eng = rawengine.Engine(on_capture=lambda e: (events.append(e), print("捕获:", e)),
                       on_log=lambda m: print("[引擎]", m))
eng.start()
time.sleep(20)
eng.stop()
print("共捕获 %d 个事件" % len(events))

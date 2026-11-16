# Remote KeyMapper — HID 遥控器键位映射器

一个 Windows 下的通用遥控器键位映射工具。支持蓝牙 / 2.4G 无线 / USB 的 HID 遥控器
（如 T6 空鼠遥控器、各类安卓盒子遥控器），把遥控器按键映射为键盘组合键、
文本、程序、音量/媒体控制、鼠标操作，并可屏蔽按键的系统默认行为。

## 特性

- **设备无关**：通过 Raw Input 识别按键来源，任意 HID 遥控器即插即用（点「选择设备」即可适配）
- **按键学习**：按一下遥控器按键即可建立映射，识别键盘事件 / 鼠标事件 / HID 原始字节
- **丰富动作**：组合键、文本输入、启动程序、音量/媒体键、鼠标（点击/双击/滚轮/移动/拖拽）
- **屏蔽原功能**：
  - 键盘类按键：低级键盘钩子精确拦截（仅拦截该遥控器，不影响电脑自带键盘）
  - HID 消费控制键（如打开搜索 / 浏览器主页）：按键瞬间监视并关闭弹出的系统面板
- **驱动级按键发送（可选）**：集成 [Interception](https://github.com/oblitum/Interception) 驱动，
  发出的按键与真实硬件无异，可唤醒只认真实输入的程序（如某些应用的唤起快捷键）
- **每键独立开关**：映射可随时启用/禁用/删除，配置存于本地 `config.json`

## 运行要求

- Windows 10 / 11（64 位）
- Python 3.10+（安装时勾选 tcl/tk 和 pip）
- 可选：Interception 驱动（仅当需要驱动级按键发送时才装）

## 快速开始

```bat
run.bat            :: 无窗口运行
调试运行.bat        :: 带控制台运行（看日志）
```

1. 打开软件，点「选择设备」，双击你的遥控器（或按一下遥控器任意键让它捕获）
2. 点「开始学习」→ 按下遥控器按键
3. 选择动作类型、填写/录入动作内容 → 「保存映射」

动作内容语法（动作类型下拉框下方的灰字提示也会实时显示）：

| 类型 | 内容示例 |
|---|---|
| combo 组合键 | `ctrl+c`、`win+d`、`alt+f4`、`lalt+k`、`ralt`、`esc`、`f5` |
| text 文本 | 任意文字（支持中文） |
| run 运行 | `notepad`、`calc`、程序完整路径 |
| volume 音量 | `volumeup` / `volumedown` / `mute` |
| media 媒体 | `playpause` / `nexttrack` / `prevtrack` / `stop` |
| mouse 鼠标 | `click_left` / `click_right` / `click_middle`、`double_left`、`scroll_up 3`、`scroll_down`、`scroll_left`、`scroll_right`、`move 0 50`、`moveto 960 540`、`down_left` + `up_left`（拖拽） |

## 安装 Interception 驱动（可选，用于驱动级按键）

1. 从 [Interception Releases](https://github.com/oblitum/Interception/releases) 下载 `Interception.zip`
2. 解压后运行其中的 `command line installer\install-interception.exe /install`（需管理员权限）
3. 重启电脑
4. 把 `library\x64\interception.dll` 复制到本软件目录

软件启动时会自动检测：驱动就绪则走驱动通道，否则回退普通模拟。

## 工作原理（架构）

```
遥控器 (BLE/USB HID)
   │  Raw Input（按设备区分来源，匹配码见 config.json 的 device_match）
   ▼
rawengine.py  ── 捕获/学习 ──▶ app.py (tkinter GUI)
   │
   ├─ 键盘类按键 + 屏蔽原键 → WH_KEYBOARD_LL 钩子（按 Raw Input 时间戳关联设备来源）
   ├─ HID 消费控制键 + 屏蔽   → 监视并关闭系统面板（搜索等）
   ▼
actions.py ── 执行动作 ──▶ icsend.py (Interception 驱动) 或 SendInput
```

## 已知限制

- 遥控器"厂商私有通道"上的按键（Windows 不接收的那种）无法捕获——按一下看日志即可知道
- 鼠标类按键（飞鼠点击等）可以映射，但无法屏蔽其原生点击行为
- 屏蔽 HID 键的系统默认行为目前覆盖"搜索面板"；其它外壳行为（如打开浏览器主页）
  建议用注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\AppKey\<编号>`
  覆盖（浏览器主页 = 7，搜索 = 5）

## 卸载

- 删除本目录；如设置过开机自启，删除注册表 `HKCU\...\Run` 下的 `T6KeyMapper`
- 如安装过 Interception：`install-interception.exe /uninstall`（管理员）后重启

## 许可

- 本项目代码：MIT License
- 本项目未捆绑 Interception，请从其官方仓库获取；Interception 采用 LGPL-3.0 /
  商业授权双许可，由 [Francisco Lopes (oblitum)](https://github.com/oblitum) 开发

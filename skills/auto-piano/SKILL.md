---
name: auto-piano
description: 用 FreePiano 软件自动演奏乐谱。当用户要求弹奏/播放一段曲子、给乐谱（简谱、音名序列或 MIDI 文件）想听到演奏、或提到 freepiano 自动弹琴时使用。纯 Python 实现，无需前台焦点，不干扰用户操作。
---

# auto-piano: FreePiano 自动演奏

## 工作原理

FreePiano（免费键盘钢琴软件）的键盘钩子会过滤一切注入的键盘输入，
但其界面上的 88 键虚拟键盘响应鼠标消息。本包通过 `PostMessage(WM_LBUTTONDOWN/UP)` 点击虚拟键盘发声，
力度用点击纵向位置模拟，坐标按真实客户区自动缩放（兼容不同 DPI）。
**全程无需前台焦点**，FreePiano 被遮挡也能正常演奏；窗口被最小化会自动恢复（不抢焦点）。

## 包位置（自包含，路径全部相对本 skill 目录）

本 skill 目录即根目录（下文用 `{skill}` 指代本 SKILL.md 所在目录）：

- 代码、示例谱全在 skill 目录内，整个目录拷走即可放到任何机器、任何 agent 的 skills 目录下使用
  （仍需 Windows + Python 3.8+，无第三方依赖）
- 包代码: `{skill}/auto_piano/`
- **只读示例谱**: `{skill}/songs/`（随包分发，会被包更新覆盖，**不要往里存用户谱面**）
- **用户谱面库**: `%APPDATA%/auto_piano/songs`（包外目录，包更新/重装/换分支都不受影响，
  用户保存的谱面一律在这里。可用环境变量 `AUTO_PIANO_SONGS` 或 config.json 的 `songs_dir` 改位置）

命令一律在 **skill 目录**下执行（`cd {skill}` 后）：

```bash
python -m auto_piano --file songs/xiaoxingxing.txt
python -m auto_piano --midi songs/mitsuha_theme.mid
```

## 找谱流程（MIDI 优先，必须遵守）

用户点播的曲子如果两处都没有（`python -m auto_piano --list` 看不到），**先调用本目录下的 `find-score` 子 skill**（`find-score/SKILL.md`）检索谱源：

1. 原始 MIDI 文件是唯一权威谱源，找到验证通过后直接 `--midi` 演奏；
2. 找不到 MIDI 时**停下告知用户**，让用户自己去找，不要擅自降级；
3. 仅当用户明确表示不想自己找时，才降级为转录图片简谱/网络谱面，且必须告知转录可能有误差。

详细流程、验证方法与报告格式见 find-score skill。

## 谱面保存流程（重要，必须遵守）

1. **新谱面演奏完成后，必须主动询问用户是否保存**（例如:「这首已经弹完了，要保存谱子吗？」）。
   「新谱面」指：从网络/图片/MIDI 现场转录生成的、或用户临时给出的、且 `--list` 两处都没有的谱面。
2. 用户同意后用 `--save` 存进**用户谱面库（包外）**，**绝不要**写进 skill 目录的 `songs/`：

   ```bash
   python -m auto_piano --save <文件>              # 沿用源文件名
   python -m auto_piano --save <文件> --as <名字>   # 改保存名 (纯文件名, 可省扩展名)
   python -m auto_piano --save <文件> --overwrite  # 覆盖用户库同名文件
   ```

   - 原始 MIDI → 存 `.mid`（最优先，零误差）
   - 简谱/音名序列 → 存 `.txt`（`auto_piano` 的谱面格式，便于改调/改速度）
   - 文件名用曲名拼音或英文，不含空格
   - `--save` 内部会拒绝任何落在包目录内的目标（防止下次更新清掉用户谱面）
3. 用户拒绝则不保存，也不写入任何文件。
4. 已保存过的曲子再次演奏直接用 `--file <曲名>`（查找顺序：显式路径 → 用户库 → 包内示例，
   同名时用户库胜出），无需重新转录，也不必再询问。
5. **为什么必须放包外**：pi 更新 git 包时执行 `git fetch` + `git reset --hard <远端>` +
   `git clean -fdx`，包目录下**所有未跟踪文件（连 .gitignore 里的也删）**都会被清掉。
   存进包内 = 用户谱面在下一次更新时必丢。

## FreePiano 路径解析（自动，不写死）

按顺序尝试，通常无需干预（`--doctor` 会显示本次命中的来源）：
0. **FreePiano 进程已在跑就直接用**（只查进程，不解析路径）
1. 环境变量 `FREEPIANO_HOME`（显式指定，最高优先级）
2. **运行中 `freepiano.exe` 的所在目录**（最权威：用户此刻在用的那份；一次 PowerShell 调用同时拿到「在不在跑」和 exe Path）
3. `%APPDATA%/auto_piano/config.json`（缓存 / 降级位；本机已登记，命中 0 耗时）
4. 可预测安装位候选：`%LOCALAPPDATA%/auto_piano/FreePiano`（`--install` 的目标）、
   `%LOCALAPPDATA%/freepiano`、`Desktop/freepiano`、`Downloads/freepiano`

**1 / 2 / 4 命中都会写回 config.json**（与已有值相同则不重复写盘）；环境变量和进程路径都
失效时自动回落到 config.json 缓存，缓存路径失效（软件被删/挪走）则继续降级到候选，全程静默不报错。

**刻意不做盘根/全盘扫描**：找不到就直接问用户，要快不要猜（旧版本会浅层扫盘，已删）。

都没有时（`get_exe_path()` 抛 `RuntimeError`，消息里带完整指引）：
- **非交互环境**（agent 跑 bash）：**先问用户**「FreePiano 装在哪 / 是不是没装过」：
  - 用户给了路径 → `python -m auto_piano --setup --dir "<目录>"` 直接登记（非交互，不弹提示）
  - 用户没装过 → `python -m auto_piano --install` 自动下载安装（从 SourceForge 拉
    `freepiano_2.2.2.1_win64.zip`，解压到 `%LOCALAPPDATA%/auto_piano/FreePiano` 并登记）
- **交互终端**：`--setup` 会提示输入路径或回车自动下载。

## 常用诊断命令

```bash
python -m auto_piano --doctor   # 自检: Python/FreePiano/进程/窗口/DPI + 谱面库路径
python -m auto_piano --selftest # 离线自测: 解析器/坐标/谱面库, 不需要 FreePiano 在跑
python -m auto_piano --list     # 列出可用谱面 (用户库 + 包内示例)
python -m auto_piano --setup    # 交互式登记路径 (终端)
python -m auto_piano --setup --dir "D:\freepiano"   # 直接登记, 非交互 (agent 优先用这个)
python -m auto_piano --install  # 自动下载安装 FreePiano
python -m auto_piano --test     # 弹一个中央 C 验证链路
```

## 快速开始

```bash
cd {skill}          # 本 SKILL.md 所在目录

# 看有哪些谱面 (用户库 + 包内示例)
python -m auto_piano --list

# 弹内置示例 (也可以只写曲名, 自动在 用户库 -> 包内示例 里找)
python -m auto_piano --file xiaoxingxing
python -m auto_piano --file songs/xiaoxingxing_jianpu.txt --key C

# 弹 MIDI 文件（自动解析 tempo/多轨）
python -m auto_piano --midi 某曲子.mid
python -m auto_piano --file mitsuha_theme.mid

# 把新谱面存进用户库 (包外, 下次更新不会没)
python -m auto_piano --save 某曲子.mid --as qiu_ming.mid

# 直接弹简谱 / 音名序列字符串
python -m auto_piano --jianpu "1 1 5 5 6 6 5-" --key C --bpm 100
python -m auto_piano --notes "C4:1 C4:1 G4:2"

# 参数: --bpm 速度 | --vel 1~127 力度 | --key 简谱的1对应音
# 注意: --bpm / --vel 只对音名序列和简谱生效; MIDI 用文件内自带的 tempo 与力度
```

## 弹窗行为

- **演奏成功**: 只用 `print` 输出结果，**不弹窗**，命令立即返回 —— agent/脚本/交互终端都无需任何参数。
- **演奏失败/中止**: 弹**阻塞式**置顶错误弹窗 (`MessageBoxW`，须用户点确定) + 蜂鸣提示，
  同时错误写入 stderr。失败必须弹窗，无开关 —— 用户需要第一时间知道演奏失败的原因。

## 谱面格式

**1. 音名序列**（默认 .txt；token `音名:拍数`，和弦用 `+`，休止 `R:1`，注释行 `//`）：
```
C4:1 C4:1 G4:1 G4:1 A4:1 A4:1 G4:2
C3+E3+G3:4 R:1
```

**2. 简谱**（自动探测，或 `format: jianpu` 声明行；`--key` 指定 1=哪个音，支持 `C`/`c`/`F#`/`Bb`）：
```
1 1 5 5 6 6 5-        // '-' 延长一拍
1^ 1v                  // '^' 高八度 'v' 低八度
#4 b7                  // 升降半音
0                      // 休止
```

**3. MIDI 文件**：`.mid/.midi` 自动走 MIDI 解析（格式 0/1，读 tempo，忽略打击乐通道）。
   tempo 状态跨轨共享（format 1 的 tempo 事件在第 0 轨），meta/sysex 不更新 running status。

**4. 事件序列脚本**（临时用，不推荐存档）：只有当 MIDI 和谱面图都拿不到、必须精细转录时才写；
直接构造 `[(start_sec, dur_sec, midi_num, velocity), ...]` 后调用 `Player().play(events)`。
文件开头加 `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` 自举，
使其不依赖 skill 目录的实际位置。

## Python API

```python
from auto_piano import Player, scores, library

p = Player()                          # 自动确保 FreePiano 已启动(未运行会拉起)
events = scores.load_file('xiaoxingxing')   # 显式路径 / 裸曲名 (用户库 -> 包内示例)
p.play(events)                        # 演奏；窗口中途被关会抛异常并释放所有按键

library.save('新谱.mid')               # 存进用户库(%APPDATA%/auto_piano/songs)
library.listing()                     # 列出可用谱面

# 事件格式: [(start_sec, dur_sec, midi_num, velocity), ...]
```

模块划分：`config.py` 路径解析/安装/坐标常量 | `library.py` 谱面库(用户库/查找/保存)
| `process.py` 进程管理 | `mapping.py` 音名↔MIDI↔屏幕坐标 | `keyboard.py` 演奏引擎
| `scores.py` 三种谱面解析 | `notify.py` 弹窗提示 | `selftest.py` 离线自测 | `player.py` CLI。

## 注意事项 / 排障

- **成功只用 print 输出，不弹窗；失败必弹窗（阻塞式）**，两种场景都不需要传任何参数
- **先 `--doctor` 再弹**：一次看清 Python/安装/进程/窗口各环节。
- **没声音**：`--test` 无声 → 检查 FreePiano 音源菜单是否加载音源（默认自带 mdaPiano）、系统音量。
- 窗口被最小化会**自动恢复**（`SW_SHOWNOACTIVATE`，不抢焦点）；被关闭则演奏中止并释放全部按键防卡音。
- 音域 A0~C8（MIDI 21~108）：音名序列/简谱越界会直接报错；MIDI 超出部分自动裁剪到该音域。
- 演奏期间用户可正常使用电脑（不需要焦点），打字不受影响。
- 时序精度依赖 Python sleep（约 ±10ms），常规曲目无碍听感。
- **谱面存哪**：包内 `songs/` 只是只读示例（会被包更新覆盖）；用户谱面一律存
  `%APPDATA%/auto_piano/songs`（与 config.json 同目录），`--doctor` / `--list` 会打印两个路径。

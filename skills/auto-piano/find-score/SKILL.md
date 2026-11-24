---
name: find-score
description: 检索乐曲的权威谱源，MIDI 文件优先。当 auto-piano 主 skill 需要为新曲子找谱时调用。规定 MIDI 优先、找不到即停下交给用户、自行转录必须告知风险的完整流程。
---

# find-score: 谱源检索

本 skill 是 **auto-piano 的子 skill**，位于 `skills/auto-piano/find-score/`，由主 skill 在需要找谱时调用。
核心原则：**MIDI 文件是唯一权威谱源**，
任何人工转录（图片简谱、听写、推断）都可能有节奏/八度/调性误差，与 MIDI 不可混为一谈。

## 谱源权威度排序

| 优先级 | 谱源 | 说明 |
|---|---|---|
| 1 | **原始 MIDI 文件 (.mid/.midi)** | 音高/节奏/时值/多声部全部精确，`--midi` 直接演奏，零转录误差 |
| 2 | 官方出版谱（PDF/乐谱书扫描） | 精确但需人工转录 |
| 3 | 社区简谱/五线谱图片 | 可信度中等，转录易出错 |
| 4 | 自行听写/推断转录 | 风险最高，必须声明 |

## 检索流程（按顺序执行，不得跳步）

1. **先查本地**：`python -m auto_piano --list` 看**用户谱面库**（`%APPDATA%/auto_piano/songs`）
   和**包内示例**（`{auto-piano}/songs/`）里是否已有该曲 → 有则 `--file <曲名>` 直接用，结束。
2. **搜 MIDI**（多角度并发查询）：
   - 「曲名 midi」「曲名 .mid」「曲名 midi download」「曲名 midi file」
   - 日文/韩文/外文歌用原文+罗马音+英文名各查一遍（如「三葉のテーマ midi」「Mitsuha no Theme midi」）
   - 候选站点：BitMidi、MidiWorld、FreeMidi、MuseScore（可导出 .mid）、Flat.io、
     各种游戏/动漫 midi 收藏站、VGMusic、钢琴谱站的 midi 附件
3. **找到 MIDI → 下载验证**：
   - 文件头必须是 `MThd`（ASCII，前 4 字节）
   - 用 `auto_piano.scores.load_file()` 试解析：确认能解析、时长合理（< 15 分钟）、
     音域在 A0~C8（MIDI 21~108）、轨数/音符数合理（纯音轨，无打击乐主导）
   - 验证通过 → 交回主 skill 演奏；演奏完按主 skill 的保存流程询问是否存入**用户谱面库**
     （`python -m auto_piano --save <文件>`，不要写进包目录 `songs/`——包更新会清掉）
4. **找不到可靠的原始 MIDI → 停下，把决策权交给用户**：
   - 明确告知：「MIDI 是最权威的谱源，我没有找到可靠的原始 MIDI 文件」
   - 给出用户自己去找的线索：推荐搜索关键词、可能有的站点、钢琴网/MuseScore 等导出途径
   - **等用户回应，不要擅自降级**
5. **降级路径**（仅当用户明确表示「不想自己找/你去找吧」时才走）：
   - 转录网络简谱/图片谱，并**必须同时告知**：「人工转录可能有节奏或八度误差，
     听感可能与原曲有出入；找到原始 MIDI 后可以随时替换」
   - 转录成果照主 skill 保存流程处理

## 检索与验证工具

用当前 agent 环境里可用的任意等价工具（名称因 agent 而异）：

- 搜索工具：2~4 个角度并发查询
- 网页抓取/命令执行工具：下载 .mid（二进制用 python urllib/curl 更稳）
- 验证脚本（无需第三方依赖；`{auto-piano}` 指主 skill 目录，与本 skill 同层）：
  ```python
  import sys; sys.path.insert(0, r"{auto-piano}")
  from auto_piano import scores
  events = scores.load_file("xxx.mid")   # 解析失败/文件损坏都会抛异常
  span = max(s + d for s, d, *_ in events)
  print(len(events), "个事件, 时长 %.1f 秒" % span,
        "音域", min(e[2] for e in events), "~", max(e[2] for e in events))
  ```
- 空字符串/HTML 假装是 midi、重定向到登录墙、曲名对但内容是别的曲子 —— 都算「不可靠」

## 输出约定

向主 skill / 用户报告时必须包含：谱源类型（MIDI/图片谱/转录）、来源 URL、验证结果
（事件数/时长/音域）、以及置信度（MIDI=精确，转录=可能有误差）、
以及谱面存放位置（用户库路径，例：`%APPDATA%/auto_piano/songs/xxx.mid`）。

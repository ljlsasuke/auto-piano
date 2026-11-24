# auto-piano

FreePiano 自动演奏 skill —— 让 AI 编码代理（pi / Claude Code / Codex CLI 等）在你的 Windows 电脑上弹钢琴。

## 它能做什么

- 演奏 **MIDI 文件**（自动解析 tempo / 多轨 / 力度）、**简谱**（支持调性、八度、升降半音）和**音名序列**谱面
- 通过 `PostMessage` 点击 FreePiano 的 88 键虚拟键盘发声，**全程无需前台焦点**，窗口被遮挡甚至最小化都能正常演奏
- 内置谱源检索子 skill（`find-score`）：MIDI 优先的找谱流程与验证方法
- 自动解析 FreePiano 安装路径（进程 / 环境变量 / 配置缓存 / 自动下载安装）

## 安装

### 方式一：pi package（推荐）

```bash
pi install git:github.com/ljlsasuke/auto-piano
```

### 方式二：Agent Skills 通用方式

把 `skills/auto-piano/` 整个目录拷贝到你的 skill 目录：

```bash
# pi
git clone https://github.com/ljlsasuke/auto-piano.git
cp -r auto-piano/skills/auto-piano ~/.pi/agent/skills/

# Claude Code / 其他兼容 Agent Skills 规范的实现
cp -r auto-piano/skills/auto-piano ~/.claude/skills/
```

## 依赖

- Windows + Python 3.8+（无第三方依赖）
- [FreePiano 2.2.2.1](https://sourceforge.net/projects/freepiano/)（缺失时可用 `--install` 自动下载安装）

## 快速开始

```bash
cd skills/auto-piano

python -m auto_piano --doctor      # 环境自检
python -m auto_piano --test        # 弹一个中央 C 验证链路
python -m auto_piano --file songs/xiaoxingxing.txt
python -m auto_piano --midi songs/summer.mid
python -m auto_piano --jianpu "1 1 5 5 6 6 5-" --key C --bpm 100
```

## 谱面格式

```text
C4:1 C4:1 G4:1 G4:1 A4:1 A4:1 G4:2     # 音名序列: 音名:拍数
C3+E3+G3:4 R:1                         # 和弦用 +, 休止 R:拍数

1 1 5 5 6 6 5-                         # 简谱, '-' 延长一拍
1^ 1v                                  # ^ 高八度, v 低八度
#4 b7                                  # 升降半音, 0 休止
```

`.mid/.midi` 文件自动走 MIDI 解析（格式 0/1，读 tempo，忽略打击乐通道）。

## 目录结构

```text
skills/auto-piano/
├── SKILL.md            # skill 主文档（Agent Skills 规范）
├── find-score/         # 子 skill: 谱源检索流程
├── auto_piano/         # Python 实现（纯标准库）
│   ├── config.py       #   FreePiano 路径解析 / 安装
│   ├── process.py      #   进程管理
│   ├── mapping.py      #   音名 ↔ MIDI ↔ 屏幕坐标
│   ├── keyboard.py     #   演奏引擎
│   ├── scores.py       #   三种谱面解析
│   └── player.py       #   CLI 入口
└── songs/              # 示例与已保存谱面
```

## License

MIT

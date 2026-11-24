# -*- coding: utf-8 -*-
"""谱面库 —— 把「用户自己的谱面」和「包内只读示例」彻底分开。

为什么必须分开:
    pi 更新 git 包时执行 `git fetch` + `git reset --hard <远端>` + `git clean -fdx`。
    `git clean -fdx` 会删掉包目录下所有未跟踪文件, 连 .gitignore 里的也不放过,
    所以任何存进包目录的谱面, 都会在下一次包更新时消失。

方案:
    包内 songs/       —— 只读示例, 随包分发, 会被更新覆盖 (可以随便覆盖)
    用户谱面库         —— 包外目录, 更新/重装/换分支都不受影响, 用户真正保存的位置

用户库位置, 优先级从高到低:
    1. 环境变量 AUTO_PIANO_SONGS      —— 显式指定 (便携/自建仓库场景)
    2. config.json 的 songs_dir        —— 持久化自定义位置
    3. %APPDATA%/auto_piano/songs      —— 默认 (与 config.json 同目录, Windows 惯例)

查找顺序: 显式路径 -> 用户库 -> 包内示例 (同名时用户库胜出, 可覆盖官方示例)
"""
import os
import shutil
from pathlib import Path

from .config import CFG_DIR, load_cfg

ENV_SONGS = "AUTO_PIANO_SONGS"
DEFAULT_USER_DIR = CFG_DIR / "songs"
BUNDLED_DIR = Path(__file__).resolve().parent.parent / "songs"
SCORE_SUFFIXES = (".mid", ".midi", ".txt")


# ---------- 目录 ----------
def user_dir():
    """用户谱面库目录 (可能尚未创建)。env > config.json > 默认"""
    raw = str(os.environ.get(ENV_SONGS) or load_cfg().get("songs_dir") or "")
    raw = raw.strip().strip('"')
    return Path(raw).expanduser() if raw else DEFAULT_USER_DIR


def ensure_user_dir():
    d = user_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def search_dirs():
    """查找顺序: 用户库优先, 包内示例兜底"""
    return [user_dir(), BUNDLED_DIR]


def is_bundled(path):
    """是否落在包目录内 (即会被更新覆盖的位置)"""
    try:
        p = Path(path).resolve()
        b = BUNDLED_DIR.resolve()
        return p == b or b in p.parents
    except Exception:
        return False


# ---------- 解析 ----------
def _explicit(name):
    """看起来是显式路径 (绝对路径 / 带目录分隔符 / 有扩展名之外的写法)"""
    s = str(name)
    if os.path.isabs(s) or s.startswith("~"):
        return True
    return ("/" in s) or ("\\" in s)


def resolve(name, must_exist=True):
    """曲名或路径 -> 实际文件 Path。

    支持: 绝对/相对路径(含目录分隔符) 原样使用;
          裸曲名(可省略扩展名) 依次在 用户库 -> 包内示例 里找。
    找不到返回 None (must_exist=False); 默认 raise FileNotFoundError, 错误信息带目录清单。
    """
    if name is None:
        return None
    s = str(name).strip().strip('"')
    p = Path(s).expanduser()
    explicit = _explicit(s)
    candidates = []
    if explicit:
        candidates.append(p)
        if not p.suffix:
            candidates += [p.with_suffix(sfx) for sfx in SCORE_SUFFIXES]
    else:
        for d in search_dirs():
            candidates.append(d / s)
            if not Path(s).suffix:
                candidates += [d / (s + sfx) for sfx in SCORE_SUFFIXES]
    for c in candidates:
        if c.is_file():
            return c
    if not must_exist:
        return None
    raise FileNotFoundError(
        f"找不到谱面: {s}\n"
        f"  用户库: {user_dir()}\n"
        f"  包内示例: {BUNDLED_DIR}\n"
        f"  提示: python -m auto_piano --list 查看已有谱面, "
        f"或用 --save <文件> 存入用户库")


# ---------- 保存 ----------
def save(src, name=None, overwrite=False):
    """把谱面存入**用户库**(包外, 更新安全)。返回目标 Path。

    src 可以是任意路径 (网络下载 / 临时转录 / 包内示例都行)。
    name 只接受纯文件名 (不含路径): 防路径穿越 / 防绕过用户库写到任意位置;
    省略扩展名时沿用源文件的扩展名。
    """
    src = Path(str(src).strip().strip('"')).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"源文件不存在: {src}")
    base = str(name).strip().strip('"') if name else src.name
    if os.path.isabs(base) or ("/" in base) or ("\\" in base):
        raise ValueError(f"保存名只接受纯文件名, 不接受路径: {base!r}")
    if not base:
        raise ValueError("保存名不能为空")
    if not Path(base).suffix:
        if not src.suffix:
            raise ValueError(f"保存名缺少扩展名, 且源文件也没有: {base!r}")
        base += src.suffix
    if Path(base).suffix.lower() not in SCORE_SUFFIXES:
        raise ValueError(
            f"只能保存谱面文件 {SCORE_SUFFIXES}, 不支持: {base!r}")
    target = ensure_user_dir() / base
    if is_bundled(target):
        # 安全兜底: 绝不允许把用户谱面写回包目录
        raise RuntimeError(
            f"拒绝写入包内目录 {target}\n"
            f"  该目录会被包更新 (git clean -fdx) 清空。\n"
            f"  请设置环境变量 {ENV_SONGS} 指向包外目录, 或删除 config.json 里的 songs_dir。")
    if target.exists():
        if target.samefile(src):
            return target           # 已在用户库里, 幂等
        if not overwrite:
            raise FileExistsError(
                f"用户库已存在同名谱面: {target}\n"
                f"  如需覆盖请加 --overwrite, 想保留旧名可加 --as <新名字>")
    shutil.copy2(str(src), str(target))
    return target


# ---------- 列表 ----------
def listing():
    """-> [(name, where, size, path)]

    search_dirs() 用户库在前, 所以同名时先登记用户库版本,
    包内同名文件随后直接跳过 (用户库版本胜出, 可覆盖官方示例)。
    """
    rows, seen = [], set()
    for d in search_dirs():
        if not d.exists():
            continue
        where = "用户库" if not is_bundled(d) else "包内示例"
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.suffix.lower() not in SCORE_SUFFIXES:
                continue
            if f.name in seen:
                continue
            seen.add(f.name)
            rows.append((f.name, where, f.stat().st_size, f))
    return rows

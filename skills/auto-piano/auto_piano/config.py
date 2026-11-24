# -*- coding: utf-8 -*-
"""FreePiano 自动演奏 - 配置与安装解析。

路径不写死, 按以下优先级解析:
1. 环境变量 FREEPIANO_HOME (显式指定, 最高优先级)
2. 运行中 freepiano.exe 的所在目录 (最权威: 用户此刻正在用的那份)
3. 用户配置文件 %APPDATA%/auto_piano/config.json 中的 freepiano_dir (缓存/降级位)
4. 可预测的安装位 (自动安装目标 + 手动解压常见处)
1/2/4 命中都会写回 config.json; 都没有 -> 交互终端问用户输入路径 / 回车自动下载,
非交互环境报错并给出指引。

不做全盘/盘根扫描: 找不到就直接问用户, 要快不要猜。

虚拟键盘几何常量基于参考窗口客户区 752x400, 实际运行时按真实客户区缩放
(见 keyboard.py), 兼容不同 DPI。
"""
import json, os, sys, zipfile
from pathlib import Path

APP_NAME = "auto_piano"
CFG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
CFG_FILE = CFG_DIR / "config.json"

ENV_KEY = "FREEPIANO_HOME"

PROCESS_NAME = "freepiano"
WINDOW_CLASS = "FreePianoMainWindow"

# ---- 可预测的安装位候选 (含 freepiano.exe 的目录) ----
# FreePiano 是绿色免安装软件(官方只发 zip), 不会装进 Program Files,
# 因此只列真正可能出现的位置: 本包的 --install 目标, 以及用户手动解压的常见处。
def candidate_dirs():
    local = Path(os.environ.get("LOCALAPPDATA",
                str(Path.home() / "AppData" / "Local")))
    return [
        INSTALL_DIR,                     # --install 的目标
        INSTALL_DIR / "freepiano",       # zip 内多一层目录时
        local / "freepiano",
        local / "freepiano" / "freepiano",
        Path.home() / "Desktop" / "freepiano",
        Path.home() / "Downloads" / "freepiano",
    ]


# ---- 自动下载安装 ----
DOWNLOAD_URL = ("https://sourceforge.net/projects/freepiano/files/"
                "freepiano_2.2.2.1_win64.zip/download")
FALLBACK_URL = "https://freepiano.tiwb.com/cn/"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA",
                  str(Path.home() / "AppData" / "Local"))) / APP_NAME / "FreePiano"

# ---- 虚拟键盘几何 (参考: 客户区 752x400, 来源 GitHub wzv5/mid 验证值) ----
REF_CLIENT_W, REF_CLIENT_H = 752, 400
KEY_X0 = 19          # 第 1 键 (A0) 左边缘 x
KEY_X_STEP = 8.167   # 相邻半音横向间距
Y_BLACK = 340        # 黑键起始 y
Y_BLACK_SPAN = 15    # 黑键力度纵向跨度
Y_WHITE = 360        # 白键起始 y
Y_WHITE_SPAN = 25    # 白键力度纵向跨度

# ---- 音域 ----
MIDI_MIN = 21        # A0
MIDI_MAX = 108       # C8

DEFAULT_VELOCITY = 100
DEFAULT_BEAT = 0.55  # 每拍秒数 (约 109 BPM)


# ---------- 用户配置 ----------
def load_cfg():
    if CFG_FILE.exists():
        try:
            return json.loads(CFG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cfg(cfg):
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    CFG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                        encoding="utf-8")


def save_freepiano_dir(path):
    cfg = load_cfg()
    cfg["freepiano_dir"] = str(Path(path))
    save_cfg(cfg)


def _remember(path):
    """把成功解析的目录写回 config.json; 与已有值相同则不重复写盘"""
    if str(load_cfg().get("freepiano_dir")) != str(Path(path)):
        save_freepiano_dir(path)


# ---------- 定位 ----------
def _looks_valid(d):
    return (Path(d) / "freepiano.exe").exists()


def _find_exe_under(root, max_depth=4):
    """在已解压的安装目录内递归找 freepiano.exe (zip 内可能多一层目录)。
    仅用于自动安装后的解包定位, 不做跨盘/全盘搜索。"""
    root = Path(root)
    if not root.exists():
        return None
    skip = {'$Recycle.Bin', 'System Volume Information', 'node_modules', '.git'}
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - base_depth
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in skip]
        if "freepiano.exe" in filenames:
            return Path(dirpath)
    return None


def _running_freepiano_dir():
    """运行中进程的 exe 目录 (最权威来源); 拿不到返回 None"""
    from .process import running_exe_path   # 延迟导入, 避开循环依赖
    try:
        exe = running_exe_path()
    except Exception:
        return None
    return exe.parent if exe else None


def resolve_freepiano_dir():
    """-> (dir, source) 或 (None, None)。

    source 取值: 'env' | 'process' | 'config' | 'candidate'

    优先级 (前三个都是“用户/系统当下真的在用”):
      1. 环境变量 FREEPIANO_HOME         —— 显式指定
      2. 运行中的 freepiano.exe 所在目录 —— 最权威 (用户此刻在用的那份)
      3. config.json 里的 freepiano_dir  —— 上次成功解析的缓存 (降级位)
      4. 可预测安装位候选

    除 config 自身外, 任何成功解析都写回 config.json (下次 0 成本)。
    刻意不做盘根/全盘扫描: 找不到就交给调用方询问用户。"""
    # 1. 环境变量
    env = os.environ.get(ENV_KEY)
    if env and _looks_valid(env):
        d = Path(env)
        _remember(d)
        return d, 'env'
    # 2. 运行中进程
    d = _running_freepiano_dir()
    if d and _looks_valid(d):
        _remember(d)
        return Path(d), 'process'
    # 3. 配置缓存
    saved = load_cfg().get("freepiano_dir")
    if saved and _looks_valid(saved):
        return Path(saved), 'config'
    # 4. 可预测安装位
    for c in candidate_dirs():
        if _looks_valid(c):
            _remember(c)
            return Path(c), 'candidate'
    return None, None


def find_freepiano_dir():
    """按优先级解析 FreePiano 目录, 找不到返回 None (详见 resolve_freepiano_dir)"""
    return resolve_freepiano_dir()[0]


def download_and_install(log=print):
    """从 SourceForge 下载 FreePiano 并解压安装到 %LOCALAPPDATA%/auto_piano/FreePiano"""
    import urllib.request
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = INSTALL_DIR / "freepiano_2.2.2.1_win64.zip"
    log(f"下载 FreePiano: {DOWNLOAD_URL}")
    log("(约 10MB, 也可手动从 " + FALLBACK_URL + " 下载)")
    urllib.request.urlretrieve(DOWNLOAD_URL, zip_path)
    log("下载完成, 解压中...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(INSTALL_DIR)
    zip_path.unlink(missing_ok=True)
    # zip 内可能有多层目录, 找到 freepiano.exe
    hit = _find_exe_under(INSTALL_DIR)
    if not hit:
        raise RuntimeError(f"解压完成但未找到 freepiano.exe, 请检查 {INSTALL_DIR}")
    save_freepiano_dir(hit)
    log(f"安装完成: {hit}")
    return hit


def get_freepiano_dir(interactive=None):
    """解析 FreePiano 目录。找不到时:
    - 交互终端: 询问用户输入路径, 或选择自动下载
    - 非交互环境: 抛出带指引的异常 (agent 应转告用户)"""
    d = find_freepiano_dir()
    if d:
        return d
    if interactive is None:
        try:
            interactive = sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            interactive = False
    if interactive:
        try:
            print("未找到 FreePiano。")
            print("  1. 输入安装路径 (含 freepiano.exe 的目录)")
            print("  2. 直接回车 = 自动从 SourceForge 下载安装")
            choice = input("路径 [回车=自动下载]: ").strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            interactive = False   # stdin 不可用, 走非交互报错
        else:
            if choice:
                if not _looks_valid(choice):
                    raise RuntimeError(f"{choice} 下没有 freepiano.exe")
                save_freepiano_dir(choice)
                return Path(choice)
            return download_and_install()
    raise RuntimeError(
        "未找到 FreePiano (已检查环境变量/配置文件/可预测安装位)。\n"
        "agent 应直接问用户: 安装在哪 / 是否没装过。\n"
        f"  a) 用户知道路径 -> `python -m auto_piano --setup --dir \"<目录>\"` 或直接告知我路径, 我来登记\n"
        f"  b) 用户没装过 -> `python -m auto_piano --install` (自动下载安装到 {INSTALL_DIR})\n"
        f"  c) 或设置环境变量 {ENV_KEY} 指向安装目录\n"
        f"  d) 也可手动从 {FALLBACK_URL} 下载解压, 再用 --setup 登记")


def get_exe_path():
    return str(Path(get_freepiano_dir()) / "freepiano.exe")

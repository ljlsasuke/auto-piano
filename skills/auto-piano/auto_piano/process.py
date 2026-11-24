# -*- coding: utf-8 -*-
"""FreePiano 进程管理: 检测 / 启动 / 关闭"""
import ctypes, subprocess, sys, time
from pathlib import Path

from . import config

u32 = ctypes.windll.user32
SMTO_ABORTIFHUNG = 0x0002

# 启动等待: 窗口出现并响应同步消息即视为就绪, 之后留 grace 秒给音频后端。
# 实测窗口 246ms 出现且立刻能回同步消息, 所以不再是"拍脑袋睡 5 秒"。
READY_TIMEOUT = 10.0   # 总超时 (秒), 超时视为启动失败
READY_GRACE = 0.8      # 就绪后再等这么久, 给音频设备/音源初始化的余量


def process_info():
    """一次 PowerShell 调用拿齐 -> (running: bool, exe: Path|None)
    exe 是运行中 freepiano.exe 的路径 (最权威的定位来源); 拿不到时为 None。
    管理员进程可能拒绝读取 Path, 所以一律 try/except 兜底。"""
    try:
        out = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             f'Get-Process {config.PROCESS_NAME} -ErrorAction SilentlyContinue | '
             'Select-Object -First 1 | ForEach-Object { "$($_.Id)|$($_.Path)" }'],
            capture_output=True, text=True, timeout=10)
    except Exception:
        return False, None
    line = out.stdout.strip().splitlines()[0].strip() if out.stdout.strip() else ''
    pid, _, raw = line.partition('|')
    running = pid.strip().isdigit()
    exe = None
    if raw.strip():
        p = Path(raw.strip())
        if (p.parent / 'freepiano.exe').exists():
            exe = p
    return running, exe


def is_running() -> bool:
    return process_info()[0]


def running_exe_path():
    """运行中的 freepiano.exe 路径 -> Path; 未运行/拿不到返回 None"""
    return process_info()[1]


def responsive(hwnd, timeout_ms=1000):
    """向窗口投递同步 WM_NULL, 能收到回包说明 UI 线程活着 (消息循环在跑)"""
    r = ctypes.c_ulong(0)
    ok = u32.SendMessageTimeoutW(hwnd, 0, 0, 0, SMTO_ABORTIFHUNG,
                                 timeout_ms, ctypes.byref(r))
    return bool(ok)


def wait_window(timeout=READY_TIMEOUT, grace=READY_GRACE):
    """轮询等主窗口出现并对同步消息做出响应 -> hwnd; 就绪后再等 grace 秒
    (音频设备/音源初始化在首次发声时才会真正完成, 留一点余量)。
    超时返回 0。"""
    deadline = time.time() + timeout
    hwnd = 0
    while time.time() < deadline:
        hwnd = u32.FindWindowW(config.WINDOW_CLASS, None)
        if hwnd and responsive(hwnd):
            time.sleep(grace)
            return hwnd
        hwnd = 0
        time.sleep(0.05)
    return 0


def launch(wait_sec=READY_TIMEOUT, grace=READY_GRACE):
    """启动 FreePiano, 并轮询等到窗口就绪 (不再盲等固定秒数)。
    wait_sec 是就绪超时上限, 不是固定睡眠时长。"""
    if sys.platform != 'win32':
        raise OSError("仅支持 Windows")
    exe = Path(config.get_exe_path())   # 找不到会给出指引
    t0 = time.perf_counter()
    subprocess.Popen(['cmd', '/c', 'start', '', 'freepiano.exe'],
                     cwd=str(exe.parent), creationflags=subprocess.CREATE_NO_WINDOW)
    if not wait_window(wait_sec, grace):
        raise RuntimeError(
            "FreePiano 启动超时: %.0f 秒内主窗口未就绪 (类名 %s)。\n"
            "请手动启动 FreePiano 或运行 python -m auto_piano --setup 登记安装路径。"
            % (wait_sec, config.WINDOW_CLASS))
    return time.perf_counter() - t0


def ensure_running(wait_sec=READY_TIMEOUT):
    """确保 FreePiano 在运行, 没有则自动启动。
    运行中顺便把它自己的目录记进 config.json (最权威来源, 下次不跑也不丢)。"""
    running, exe = process_info()
    if running:
        if exe:
            try:
                saved = config.load_cfg().get('freepiano_dir')
                if not saved or str(Path(saved)) != str(exe.parent):
                    config.save_freepiano_dir(exe.parent)
            except Exception:
                pass
        return True
    launch(wait_sec)
    if not is_running():
        raise RuntimeError("FreePiano 启动失败, exe: " + config.get_exe_path())
    return True


def kill():
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    f'Stop-Process -Name {config.PROCESS_NAME} -Force -ErrorAction SilentlyContinue'])

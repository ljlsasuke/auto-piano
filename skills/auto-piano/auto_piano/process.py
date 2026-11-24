# -*- coding: utf-8 -*-
"""FreePiano 进程管理: 检测 / 启动 / 关闭"""
import subprocess, sys, time
from pathlib import Path

from . import config


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


def launch(wait_sec=5):
    """启动 FreePiano (音源加载需要几秒)"""
    if sys.platform != 'win32':
        raise OSError("仅支持 Windows")
    exe = Path(config.get_exe_path())   # 找不到会给出指引
    subprocess.Popen(['cmd', '/c', 'start', '', 'freepiano.exe'],
                     cwd=str(exe.parent), creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(wait_sec)


def ensure_running(wait_sec=5):
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

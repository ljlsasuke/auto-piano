# -*- coding: utf-8 -*-
"""命令行入口:
python -m auto_piano --file songs/xiaoxingxing.txt
python -m auto_piano --midi x.mid --vel 110
python -m auto_piano --jianpu "1 1 5 5 6 6 5-" --key C --bpm 100
python -m auto_piano --notes "C4:1 C4:1 G4:2"
python -m auto_piano --test        # 弹一个中央 C 验证链路
python -m auto_piano --doctor      # 环境自检
python -m auto_piano --selftest    # 离线自测 (不用 FreePiano, 校验解析/坐标)
python -m auto_piano --setup       # 交互式登记 FreePiano 路径
python -m auto_piano --install     # 自动下载安装 FreePiano
"""
import argparse, sys
from pathlib import Path

from . import scores, config
from .keyboard import Player, find_window, client_scale
from .notify import notify, INFO, WARN
from .config import DEFAULT_BEAT, DEFAULT_VELOCITY


def doctor():
    """环境自检: python / FreePiano / 进程 / 窗口 逐项报告"""
    print("== auto_piano 环境自检 ==")
    ok = True
    # 1. Python
    v = sys.version_info
    print(f"[{'OK' if v >= (3, 8) else '!!'}] Python {v.major}.{v.minor}.{v.micro}")
    ok &= v >= (3, 8)
    # 2. 平台
    if sys.platform != 'win32':
        print("[!!] 非 Windows 平台, 无法运行")
        return 1
    print("[OK] Windows")
    # 3. FreePiano 安装
    d, src = config.resolve_freepiano_dir()
    if d:
        label = {'env': '环境变量 ' + config.ENV_KEY,
                 'process': '运行中进程(最权威)',
                 'config': '已保存配置',
                 'candidate': '安装位候选'}.get(src, src)
        print(f"[OK] FreePiano 已找到 ({label}): {d}")
    else:
        print(f"[!!] 未找到 FreePiano")
        print(f"     修复: 设置环境变量 {config.ENV_KEY}, 或运行")
        print(f"     python -m auto_piano --setup   (登记已有安装)")
        print(f"     python -m auto_piano --install (自动下载安装)")
        ok = False
    # 4. 进程
    from .process import is_running
    running = is_running()
    print(f"[{'OK' if running else '--'}] FreePiano 进程 {'运行中' if running else '未运行 (演奏时会自动启动)'}")
    # 5. 窗口
    hwnd = find_window()
    if hwnd:
        from .keyboard import restore_no_activate, is_minimized
        if is_minimized(hwnd):
            restore_no_activate(hwnd)
            print("[--] 窗口曾被最小化, 已自动恢复")
        sx, sy = client_scale(hwnd)
        print(f"[OK] 主窗口已找到 (hwnd={hwnd}, 客户区缩放 {sx:.2f}x{sy:.2f})")
    else:
        print("[--] 主窗口未找到 (若进程未运行则属正常; 若已运行请检查是否最小化)")
    print("== 自检结束 ==")
    return 0 if ok else 1


def setup(dir_path=None):
    """登记 FreePiano 路径。dir_path 给定时非交互直接登记 (agent 友好)"""
    if dir_path:
        p = str(Path(str(dir_path).strip().strip('"')))
        if not (Path(p) / 'freepiano.exe').exists():
            print(f"!! {p} 下没有 freepiano.exe"); return 1
        config.save_freepiano_dir(p)
        print(f"已登记: {p} -> {config.CFG_FILE}")
        return 0
    d = config.find_freepiano_dir()
    if d:
        print(f"已找到 FreePiano: {d}")
        r = input("使用该路径? [Y/n]: ").strip().lower()
        if r in ('', 'y', 'yes'):
            config.save_freepiano_dir(d)
            print(f"已保存到 {config.CFG_FILE}")
            return 0
    p = input("请输入 FreePiano 安装目录 (含 freepiano.exe, 直接回车=自动下载安装): ").strip().strip('"')
    if p:
        if not (Path(p) / 'freepiano.exe').exists():
            print(f"!! {p} 下没有 freepiano.exe"); return 1
        config.save_freepiano_dir(p)
        print(f"已保存到 {config.CFG_FILE}")
        return 0
    config.download_and_install()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m auto_piano',
                                 description='FreePiano 自动演奏 (无需前台焦点)')
    ap.add_argument('--file', help='谱面文件 (.txt 音名序列/简谱, .mid MIDI)')
    ap.add_argument('--midi', help='MIDI 文件 (同 --file x.mid)')
    ap.add_argument('--notes', help='音名序列字符串, 如 "C4:1 D4:1 G4:2"')
    ap.add_argument('--jianpu', help='简谱字符串, 如 "1 1 5 5 6 6 5-"')
    ap.add_argument('--key', default='C', help='简谱的 1 = 哪个音 (默认 C)')
    ap.add_argument('--format', choices=['note_seq', 'jianpu', 'midi'],
                    help='强制指定谱面格式')
    ap.add_argument('--bpm', type=float, help='速度 (拍/分钟), 覆盖默认 109')
    ap.add_argument('--vel', type=int, default=DEFAULT_VELOCITY, help='力度 1~127')
    ap.add_argument('--test', action='store_true', help='弹一个中央 C 验证链路')
    ap.add_argument('--doctor', action='store_true', help='环境自检')
    ap.add_argument('--selftest', action='store_true', help='离线自测 (校验解析与坐标, 不碰 FreePiano)')
    ap.add_argument('--setup', action='store_true', help='交互式登记 FreePiano 路径')
    ap.add_argument('--dir', help='配合 --setup: 直接登记该目录 (非交互, 不弹提示)')
    ap.add_argument('--install', action='store_true', help='自动下载安装 FreePiano')
    ap.add_argument('--no-notify', action='store_true', help='不弹完成/错误提示框')
    args = ap.parse_args(argv)

    if args.doctor:
        return doctor()
    if args.selftest:
        from .selftest import run
        return run()
    if args.setup:
        return setup(args.dir)
    if args.dir:
        ap.error("--dir 需要配合 --setup 使用, 如 --setup --dir \"D:\\freepiano\"")
    if args.install:
        config.download_and_install()
        return 0

    beat = DEFAULT_BEAT if not args.bpm else 60.0 / args.bpm

    try:
        if args.test:
            p = Player()
            p.test_note()
            print("OK: 中央 C 已弹响 (链路正常)")
            return 0

        if args.file:
            source = ('file', args.file)
        elif args.midi:
            source = ('file', args.midi)
        elif args.notes:
            source = ('str', args.notes)
        elif args.jianpu:
            source = ('str', args.jianpu)
        else:
            ap.error("需要 --file / --midi / --notes / --jianpu 之一")

        if source[0] == 'file':
            events = scores.load_file(source[1], fmt=args.format,
                                      key=args.key, beat=beat, velocity=args.vel)
        else:
            fmt = args.format or ('jianpu' if args.jianpu else 'note_seq')
            events = scores.load(source[1], fmt=fmt, key=args.key,
                                 beat=beat, velocity=args.vel)

        if not events:
            raise ValueError("谱面解析结果为空")
        total = max(s + d for s, d, *_ in events)
        print(f"解析完成: {len(events)} 个音符事件, 时长约 {total:.1f}s, 开始演奏...")

        p = Player()
        used = p.play(events)
        msg = f"{len(events)} 个音符事件演奏完成 ✓\n耗时 {used:.1f} 秒"
        print(msg)
        if not args.no_notify:
            notify("演奏完成 ✓", msg, INFO)
        return 0

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if not args.no_notify:
            notify("演奏失败/中止", str(e), WARN)
        return 1


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""命令行入口:
python -m auto_piano --file songs/xiaoxingxing.txt
python -m auto_piano --file x.txt --vel 110      # --vel 只对简谱/音名序列生效
python -m auto_piano --jianpu "1 1 5 5 6 6 5-" --key C --bpm 100
python -m auto_piano --notes "C4:1 C4:1 G4:2"
python -m auto_piano --list         # 列出可用谱面 (用户库 + 包内示例)
python -m auto_piano --save x.mid   # 存进用户谱面库 (包外, 包更新不受影响)
python -m auto_piano --test        # 弹一个中央 C 验证链路
python -m auto_piano --doctor      # 环境自检
python -m auto_piano --selftest    # 离线自测 (不用 FreePiano, 校验解析/坐标)
python -m auto_piano --setup       # 交互式登记 FreePiano 路径
python -m auto_piano --install     # 自动下载安装 FreePiano
"""
import argparse, sys
from pathlib import Path

from . import scores, config, library
from .keyboard import Player, find_window, client_scale
from .notify import notify, WARN
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
    # 6. 谱面库 (用户库在包外, 包更新不会清空)
    print(f"[--] 用户谱面库: {library.user_dir()}")
    print(f"[--] 包内示例谱面 (只读, 会被包更新覆盖): {library.BUNDLED_DIR}")
    rows = library.listing()
    n_user = sum(1 for r in rows if r[1] == '用户库')
    print(f"[--] 可用谱面 {len(rows)} 首 (用户库 {n_user} / 包内示例 {len(rows) - n_user})")
    if library.is_bundled(library.user_dir()):
        print(f"[!!] 用户谱面库落在包目录内, 会被更新清空! 请设 {library.ENV_SONGS} 指向包外目录")
        ok = False
    print("== 自检结束 ==")
    return 0 if ok else 1


def list_scores():
    """--list: 用户库 + 包内示例"""
    print(f"用户谱面库 (包外, 更新安全): {library.user_dir()}")
    print(f"包内示例 (只读, 随包更新):   {library.BUNDLED_DIR}")
    rows = library.listing()
    if not rows:
        print("\n(还没有任何谱面)")
        return 0
    width = max(len(r[0]) for r in rows) + 2
    print()
    for name, where, size, _p in rows:
        print(f"  {name:<{width}} {where:<6} {size / 1024:6.1f} KB")
    print(f"\n共 {len(rows)} 首。演奏: python -m auto_piano --file <曲名或路径>")
    return 0


def save_score(src, name=None, overwrite=False):
    """--save: 把谱面存进用户库 (包外)"""
    try:
        dst = library.save(src, name=name, overwrite=overwrite)
    except Exception as e:
        print(f"!! 保存失败: {e}", file=sys.stderr)
        return 1
    print(f"已保存到用户库: {dst}")
    print(f"以后可直接: python -m auto_piano --file \"{dst.name}\"")
    return 0


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
    ap.add_argument('--vel', type=int, default=DEFAULT_VELOCITY,
                    help='力度 1~127 (仅对简谱/音名序列生效; MIDI 用文件自带的每音符力度)')
    ap.add_argument('--max-sec', type=float,
                    help='只演奏前 N 秒 (预览用, 长曲先听开头)')
    ap.add_argument('--list', action='store_true',
                    help='列出可用谱面 (用户库 + 包内示例)')
    ap.add_argument('--save', metavar='FILE',
                    help='把谱面存进用户库 (包外目录, 包更新不会清空)')
    ap.add_argument('--as', dest='savename',
                    help='配合 --save: 指定保存名 (纯文件名, 不含路径, 可省扩展名)')
    ap.add_argument('--overwrite', action='store_true',
                    help='配合 --save: 覆盖用户库同名文件')
    ap.add_argument('--test', action='store_true', help='弹一个中央 C 验证链路')
    ap.add_argument('--doctor', action='store_true', help='环境自检')
    ap.add_argument('--selftest', action='store_true', help='离线自测 (校验解析与坐标, 不碰 FreePiano)')
    ap.add_argument('--setup', action='store_true', help='交互式登记 FreePiano 路径')
    ap.add_argument('--dir', help='配合 --setup: 直接登记该目录 (非交互, 不弹提示)')
    ap.add_argument('--install', action='store_true', help='自动下载安装 FreePiano')
    args = ap.parse_args(argv)

    if args.savename and not args.save:
        ap.error("--as 需要配合 --save 使用")
    if args.overwrite and not args.save:
        ap.error("--overwrite 需要配合 --save 使用")

    if args.doctor:
        return doctor()
    if args.list:
        return list_scores()
    if args.save:
        return save_score(args.save, name=args.savename, overwrite=args.overwrite)
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
        if args.max_sec:
            # 预览: 只留起始时间在前 N 秒的音, 并把尾部裁到 N 秒避免长音悬在那里
            events = [(s, min(d, args.max_sec - s), n, v)
                      for s, d, n, v in events if s < args.max_sec]
            if not events:
                raise ValueError(f"前 {args.max_sec}s 内没有音符")
            print(f"预览模式: 只演奏前 {args.max_sec:g}s (完整时长 {total:.1f}s)")
            total = max(s + d for s, d, *_ in events)
        print(f"解析完成: {len(events)} 个音符事件, 时长约 {total:.1f}s, 开始演奏...")

        p = Player()
        used = p.play(events)
        print(f"{len(events)} 个音符事件演奏完成 ✓\n耗时 {used:.1f} 秒")
        return 0

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        notify("演奏失败/中止", str(e), WARN)
        return 1


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""离线自测 — 不需要 FreePiano, 只校验解析器与坐标映射的契约。

用法: python -m auto_piano --selftest
覆盖: 音名/简谱/MIDI 解析、调号与八度、错误路径、力度夹取、键盘坐标不越界。
"""
from pathlib import Path

from . import scores
from .config import REF_CLIENT_W, REF_CLIENT_H, MIDI_MIN, MIDI_MAX
from .mapping import note_num, note_name, key_point

_fails = []


def _check(label, cond, detail=''):
    if cond:
        print(f"[OK] {label}")
    else:
        print(f"[!!] {label} {detail}")
        _fails.append(label)


def _raises(label, fn, exc=Exception):
    try:
        fn()
    except exc:
        _check(label, True)
        return
    except Exception as e:
        _check(label, False, f'期望 {exc.__name__}, 实际 {type(e).__name__}: {e}')
        return
    _check(label, False, f'期望抛 {exc.__name__}, 却正常返回')



def _path_priority_tests():
    """路径解析优先级: env > 运行中进程 > config 缓存 > 安装位候选。
    全部在临时目录里跑, 不碰真实 %APPDATA% 配置。"""
    import os, tempfile
    from . import config

    tmp = Path(tempfile.mkdtemp(prefix='ap_selftest_'))
    saved_env = dict(os.environ)
    saved = (config.CFG_DIR, config.CFG_FILE, config._running_freepiano_dir)
    try:
        config.CFG_DIR = tmp / 'roaming' / 'auto_piano'
        config.CFG_FILE = config.CFG_DIR / 'config.json'
        os.environ.pop(config.ENV_KEY, None)
        os.environ['LOCALAPPDATA'] = str(tmp / 'local')
        config._running_freepiano_dir = lambda: None

        # 候选 (local/freepiano) 命中并写缓存
        cand = tmp / 'local' / 'freepiano'
        cand.mkdir(parents=True); (cand / 'freepiano.exe').write_bytes(b'')
        d, src = config.resolve_freepiano_dir()
        _check("候选命中不扫描", src == 'candidate', f'{src} / {d}')
        _check("候选命中写入 config.json", config.CFG_FILE.exists())

        # 环境变量压过缓存
        alt = tmp / 'green' / 'freepiano'
        alt.mkdir(parents=True); (alt / 'freepiano.exe').write_bytes(b'')
        os.environ[config.ENV_KEY] = str(alt)
        d, src = config.resolve_freepiano_dir()
        _check("环境变量优先", src == 'env' and d == alt, f'{src} / {d}')

        # 环境变量失效 -> 回落 config 缓存
        os.environ[config.ENV_KEY] = str(tmp / 'nope')
        d, src = config.resolve_freepiano_dir()
        _check("环境变量失效回落缓存", src == 'config' and d == alt, f'{src} / {d}')

        # 运行中进程压过缓存
        os.environ.pop(config.ENV_KEY, None)
        config._running_freepiano_dir = lambda: cand
        d, src = config.resolve_freepiano_dir()
        _check("运行中进程优先于缓存", src == 'process' and d == cand, f'{src} / {d}')

        # 全空
        config._running_freepiano_dir = lambda: None
        for f in (cand, alt):
            (f / 'freepiano.exe').unlink()
        config.CFG_FILE.unlink(missing_ok=True)
        _check("都没有时返回 None", config.resolve_freepiano_dir() == (None, None))
    finally:
        config.CFG_DIR, config.CFG_FILE, config._running_freepiano_dir = saved
        os.environ.clear(); os.environ.update(saved_env)


def run():
    print("== auto_piano 离线自测 ==")

    # 1. 音名 <-> MIDI
    _check("C4 -> 60", note_num('C4') == 60)
    _check("A0 -> 21", note_num('A0') == 21)
    _check("C#4 = Db4 = 61", note_num('C#4') == note_num('Db4') == 61)
    _check("note_name 往返", all(note_num(note_name(n)) == n for n in range(MIDI_MIN, MIDI_MAX + 1)))
    _raises("越界音名报错", lambda: note_num('C9'), ValueError)
    _raises("非法音名报错", lambda: note_num('H4'), ValueError)

    # 2. 键盘坐标: 全部音域 + 边界力度都必须落在客户区内
    bad = []
    for n in range(MIDI_MIN, MIDI_MAX + 1):
        for v in (0, 1, 60, 100, 127, 200):
            x, y = key_point(n, v)
            if not (0 <= x < REF_CLIENT_W and 0 <= y < REF_CLIENT_H):
                bad.append((n, v, x, y))
    _check("坐标全音域不越界 (力度已夹取)", not bad, str(bad[:3]))
    _check("力度 0 与 1 同坐标", key_point(60, 0) == key_point(60, 1))
    _check("力度 300 与 127 同坐标", key_point(60, 300) == key_point(60, 127))

    # 3. 音名序列
    ev = scores.load("C4:1 C4:1 G4:2", fmt='note_seq')
    _check("音名序列 3 事件", len(ev) == 3)
    _check("时值累加正确", abs(ev[2][0] - 1.1) < 1e-9 and abs(ev[2][1] - 1.1) < 1e-9)
    rest = scores.load("C4:1 R:1 C4:1", fmt='note_seq')
    _check("休止符推进时间", len(rest) == 2 and abs(rest[1][0] - 1.1) < 1e-9, str(rest[1][0]))
    chord = scores.load("C4+E4+G4:2", fmt='note_seq')
    _check("和弦同起同长", len(chord) == 3 and all(e[0] == 0 and abs(e[1] - 1.1) < 1e-9 for e in chord))
    _raises("音名序列缺拍数报错", lambda: scores.load("C4", fmt='note_seq'), ValueError)

    # 4. 简谱: 调号、八度、时值
    jp = scores.load("1 1 5- 5", fmt='jianpu', key='C')
    _check("简谱 1=C -> C4", jp[0][2] == 60)
    _check("'5-' 时值 2 拍", abs(jp[2][1] - 1.1) < 1e-9)
    _check("1=G -> G4", scores.load("1", fmt='jianpu', key='G')[0][2] == 67)
    _check("小写调名 c 与 C 等价", scores.load("1", fmt='jianpu', key='c')[0][2] == 60)
    _check("F# 调名可用", scores.load("1", fmt='jianpu', key='F#')[0][2] == 66)
    _check("1^ 高八度 -> C5", scores.load("1^", fmt='jianpu')[0][2] == 72)
    _check("1v 低八度 -> C3", scores.load("1v", fmt='jianpu')[0][2] == 48)
    _check("b1 落到 B3 (不越到 B4)", scores.load("b1", fmt='jianpu')[0][2] == 59)
    _check("#4 -> F#4", scores.load("#4", fmt='jianpu')[0][2] == 66)
    _raises("非法调名报错", lambda: scores.load("1", fmt='jianpu', key='X'), ValueError)
    _raises("非法简谱 token 报错", lambda: scores.load("1^z", fmt='jianpu'), ValueError)

    # 5. format: 声明行 (无论是否显式指定 --format 都要剥离)
    decl = "format: jianpu\n1 1 5 5\n"
    _check("声明行自动识别", len(scores.load(decl)) == 4)
    _check("声明行不影响显式 fmt", len(scores.load(decl, fmt='jianpu')) == 4)

    # 6. MIDI
    mid = Path(__file__).resolve().parents[1] / 'songs' / 'mitsuha_theme.mid'
    if mid.exists():
        ev = scores.load_file(str(mid))
        span = max(e[0] + e[1] for e in ev)
        _check("MIDI 解析成功", len(ev) > 100, f'{len(ev)} 事件')
        _check("MIDI 时长合理 (< 15 分钟)", span < 900, f'{span:.1f}s')
        _check("MIDI 音域在 A0~C8", all(MIDI_MIN <= e[2] <= MIDI_MAX for e in ev))
        _check("MIDI 力度合法", all(1 <= e[3] <= 127 for e in ev))
    else:
        _check("MIDI 样例存在", False, str(mid))

    # 7. 已保存谱面都能解析
    songs = Path(__file__).resolve().parents[1] / 'songs'
    bad = []
    for f in sorted(songs.glob('*.txt')) + sorted(songs.glob('*.mid')):
        try:
            if not scores.load_file(str(f)):
                bad.append((f.name, '空谱面'))
        except Exception as e:
            bad.append((f.name, f'{type(e).__name__}: {e}'))
    _check("songs/ 内全部谱面可解析", not bad, str(bad))

    _path_priority_tests()

    print(f"== 自测结束: {len(_fails)} 项失败 ==")
    return 0 if not _fails else 1

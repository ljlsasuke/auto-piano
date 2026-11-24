# -*- coding: utf-8 -*-
"""离线自测 — 不需要 FreePiano, 只校验解析器与坐标映射的契约。

用法: python -m auto_piano --selftest
覆盖: 音名/简谱/MIDI 解析、调号与八度、错误路径、力度夹取、键盘坐标不越界。
"""
from pathlib import Path

from . import scores, library
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



def _library_tests():
    """谱面库: 用户库在包外 / 用户库同名优先 / 拒绝写回包内 (会被更新清空)"""
    import os, tempfile
    from . import library

    tmp = Path(tempfile.mkdtemp(prefix='ap_lib_'))
    saved_env = dict(os.environ)
    saved_load_cfg = library.load_cfg
    try:
        user = tmp / 'user'
        os.environ[library.ENV_SONGS] = str(user)
        library.load_cfg = lambda: {}

        # 裸曲名默认命中包内示例
        hit = library.resolve('xiaoxingxing.txt')
        _check("裸曲名命中包内示例", hit is not None and library.is_bundled(hit),
               str(hit))

        # 用户库同名时优先取用户库
        user.mkdir(parents=True)
        (user / 'xiaoxingxing.txt').write_bytes(b'1 1 5 5\n')
        hit = library.resolve('xiaoxingxing.txt')
        _check("用户库同名优先", hit is not None and not library.is_bundled(hit),
               str(hit))

        # 省略扩展名也能找到
        _check("裸名可省扩展名", library.resolve('xiaoxingxing') is not None)

        # 保存落到用户库 (包外)
        src = tmp / 'sample.mid'
        src.write_bytes(b'MThd\x00\x00\x00\x06')
        dst = library.save(src)
        _check("保存写入用户库", dst.parent == user and not library.is_bundled(dst),
               str(dst))
        _raises("同名不覆盖报错", lambda: library.save(src), FileExistsError)

        # 保存名只能是纯文件名: 防路径穿越 / 防写到用户库外
        _raises("拒绝路径型保存名",
                lambda: library.save(src, name=str(tmp / 'evil.mid')), ValueError)
        _raises("拒绝相对路径保存名",
                lambda: library.save(src, name='sub/evil.mid'), ValueError)
        # 省略扩展名 -> 沿用源扩展名; 非法扩展名直接拒绝
        inherited = library.save(src, name='inherited', overwrite=True)
        _check("省略扩展名沿用源扩展名", inherited.name == 'inherited.mid',
               inherited.name)
        _raises("拒绝非谱面扩展名",
                lambda: library.save(src, name='evil.exe'), ValueError)

        # 包内目录绝不能作为保存位置
        library.load_cfg = lambda: {'songs_dir': str(library.BUNDLED_DIR)}
        os.environ.pop(library.ENV_SONGS, None)
        _raises("--save 拒绝写回包内", lambda: library.save(tmp / 'sample.mid'),
                RuntimeError)

        # listing 同名去重 (用户库胜出)
        library.load_cfg = lambda: {}
        os.environ[library.ENV_SONGS] = str(user)
        names = {r[0]: r[1] for r in library.listing()}
        _check("列表同名用户库胜出", names.get('xiaoxingxing.txt') == '用户库',
               str(names.get('xiaoxingxing.txt')))
    finally:
        library.load_cfg = saved_load_cfg
        os.environ.clear(); os.environ.update(saved_env)


def _path_priority_tests():
    """路径解析优先级: env > 运行中进程 > config 缓存 > 安装位候选。
    全部在临时目录里跑, 不碰真实 %APPDATA% 配置。"""
    import os, tempfile
    from . import config

    tmp = Path(tempfile.mkdtemp(prefix='ap_selftest_'))
    saved_env = dict(os.environ)
    saved = (config.CFG_DIR, config.CFG_FILE, config._running_freepiano_dir,
             config.candidate_dirs)
    try:
        config.CFG_DIR = tmp / 'roaming' / 'auto_piano'
        config.CFG_FILE = config.CFG_DIR / 'config.json'
        os.environ.pop(config.ENV_KEY, None)
        os.environ['LOCALAPPDATA'] = str(tmp / 'local')
        config._running_freepiano_dir = lambda: None
        # INSTALL_DIR 是模块级常量, 改环境变量救不了 -> 直接接管候选列表,
        # 否则本机真的装了 FreePiano 时 "全空" 用例会误命中真实安装位
        cand = tmp / 'local' / 'freepiano'
        config.candidate_dirs = lambda: [cand, cand / 'freepiano']

        # 候选 (local/freepiano) 命中并写缓存
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
        (config.CFG_DIR, config.CFG_FILE, config._running_freepiano_dir,
         config.candidate_dirs) = saved
        os.environ.clear(); os.environ.update(saved_env)


def _vlq(n):
    """MIDI 变长量编码 (delta time 与元事件长度字段用)"""
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def _make_mid(path, division, tracks):
    """拼一个最小 SMF: tracks 是 [[(delta_tick, 原始字节串), ...], ...]"""
    import struct
    fmt = 1 if len(tracks) > 1 else 0
    hdr = b'MThd' + struct.pack('>IHHH', 6, fmt, len(tracks), division)
    body = b''
    for tr in tracks:
        raw = b''.join(_vlq(dt) + ev for dt, ev in tr)
        body += b'MTrk' + struct.pack('>I', len(raw)) + raw
    Path(path).write_bytes(hdr + body)


def _midi_timing_tests():
    """MIDI 时间轴契约: tempo 分段积分 / format1 控制轨 / SMPTE 时基 / meta 变长长度

    旧实现用「当前 tempo × 绝对 tick」, 多 tempo 文件的时长会偏 +30%~+386%;
    SMPTE 与长 meta 文件则直接抛异常。这里用 4 个内存合成的小文件钉死精确秒数,
    不依赖任何真实谱面, 也不依赖 Windows。"""
    import os, shutil, tempfile

    tmp = tempfile.mkdtemp(prefix='ap_midi_')
    cases = []
    try:
        # A: 两段 tempo (1 拍 = 480 tick), 前段 120bpm, 后段 60bpm
        pa = os.path.join(tmp, 'tempo2.mid')
        _make_mid(pa, 480, [[
            (0, b'\xff\x51\x03\x07\xa1\x20'),      # tick 0  : 500000us (120bpm)
            (480, b'\xff\x51\x03\x0f\x42\x40'),    # tick 480: 1000000us (60bpm)
            (0, b'\x90\x3c\x64'),                  # C4 on  @480
            (1440, b'\x80\x3c\x40'),               # C4 off @1920
        ]])
        cases.append(('两段 tempo', pa, 0.50, 3.00))

        # B: format 1, tempo 只在第 0 轨 (控制轨), 音符在第 1 轨
        pb = os.path.join(tmp, 'fmt1.mid')
        _make_mid(pb, 480, [
            [(0, b'\xff\x51\x03\x07\xa1\x20'), (960, b'\xff\x51\x03\x0f\x42\x40')],
            [(960, b'\x90\x3c\x64'), (960, b'\x80\x3c\x40')],
        ])
        cases.append(('format1 控制轨 tempo', pb, 1.00, 2.00))

        # C: SMPTE 时基 -25fps x 40 tick/frame = 1000 tick/秒 (与 tempo 无关)
        pc = os.path.join(tmp, 'smpte.mid')
        _make_mid(pc, 0xE728, [[(1000, b'\x90\x3c\x64'), (2000, b'\x80\x3c\x40')]])
        cases.append(('SMPTE 时基', pc, 1.00, 2.00))

        # D: 200 字节文本元事件 (长度字段是两字节 VLQ), 无 tempo -> 默认 120bpm
        pd = os.path.join(tmp, 'meta.mid')
        _make_mid(pd, 480, [[
            (0, b'\xff\x03' + _vlq(200) + b'A' * 200),
            (480, b'\x90\x3c\x64'),
            (480, b'\x80\x3c\x40'),
        ]])
        cases.append(('meta 变长长度', pd, 0.50, 0.50))

        for label, path, want_start, want_dur in cases:
            try:
                ev = scores.load_file(path)
            except Exception as e:
                # 解析器直接抛异常也要记成失败项, 而不是让整个自测崩掉
                _check(f"{label}: 解析不抛异常", False, f'{type(e).__name__}: {e}')
                continue
            got_start, got_dur = (ev[0][0], ev[0][1]) if ev else (float('nan'), float('nan'))
            _check(f"{label}: 起点秒数", abs(got_start - want_start) < 0.01,
                   f'得到 {got_start:.2f}, 期望 {want_start:.2f}')
            _check(f"{label}: 时值秒数", abs(got_dur - want_dur) < 0.01,
                   f'得到 {got_dur:.2f}, 期望 {want_dur:.2f}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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

    # 6b. MIDI 时间轴契约 (tempo 分段积分 / 跨轨 / SMPTE / 变长 meta)
    _midi_timing_tests()

    # 7. 已保存谱面都能解析 (用户库 + 包内示例)
    bad = []
    for name, where, _size, path in library.listing():
        try:
            if not scores.load_file(str(path)):
                bad.append((name, '空谱面'))
        except Exception as e:
            bad.append((name, f'{type(e).__name__}: {e}'))
    _check("全部谱面可解析", not bad, str(bad))

    _library_tests()
    _path_priority_tests()

    print(f"== 自测结束: {len(_fails)} 项失败 ==")
    return 0 if not _fails else 1

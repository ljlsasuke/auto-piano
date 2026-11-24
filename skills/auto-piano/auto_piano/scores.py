# -*- coding: utf-8 -*-
"""谱面解析 — 支持三种输入格式, 统一输出事件列表
[(start_sec, dur_sec, midi_num, velocity), ...]

1. 音名序列 (note_seq):  C4:1 D4:1 E4:2 | 和弦 C4+E4+G4:2 | 休止 R:1
2. 简谱 (jianpu):        1 1 5 5 6 6 5- | 高八度 1^ 低八度 1v | 升降号 #4 b7 | 0 休止
3. MIDI 文件 (.mid):     自动解析全部音符事件
"""
import struct
from .config import DEFAULT_VELOCITY, DEFAULT_BEAT
from .mapping import note_num


def _strip_comments(text):
    return '\n'.join(line.split('//')[0] for line in text.splitlines())


def _split_format_decl(text):
    """剥离 'format: jianpu/note_seq' 声明行 -> (body, declared_fmt)
    无论调用方是否已显式指定格式, 声明行都不会污染谱面。"""
    lines, declared = [], None
    for line in text.splitlines():
        ls = line.strip().lower()
        if ls.startswith('format:'):
            val = ls.split(':', 1)[1].strip()
            if val in ('jianpu', 'note_seq', 'midi'):
                declared = val
            continue
        lines.append(line)
    return '\n'.join(lines), declared


# ---------- 1. 音名序列 ----------
def parse_note_seq(text, beat=DEFAULT_BEAT, velocity=DEFAULT_VELOCITY):
    """token: 音名:拍数  和弦用 + 连接, 休止用 R"""
    events = []
    t = 0.0
    for raw in _strip_comments(text).replace('|', ' ').split():
        tok = raw.strip()
        if not tok:
            continue
        if ':' not in tok:
            raise ValueError(f"音名序列格式错误: {tok!r} (应为 音名:拍数 如 C4:1)")
        notes_part, dur_part = tok.rsplit(':', 1)
        dur = float(dur_part) * beat
        if notes_part.upper() == 'R':
            t += dur
            continue
        for name in notes_part.split('+'):
            events.append((t, dur, note_num(name), velocity))
        t += dur
    return events


# ---------- 2. 简谱 ----------
_DEGREE = {'1': 0, '2': 2, '3': 4, '4': 5, '5': 7, '6': 9, '7': 11}
_KEY_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def _key_pc(key):
    """调名 -> 音级 (1 对应的 pitch class)。'C' / 'c' / 'F#' / 'Bb' 均可"""
    k = str(key).strip()
    if not k:
        raise ValueError("--key 为空, 应为 C/D/E/F/G/A/B (可带 # 或 b)")
    base = k[0].upper()
    if base not in _KEY_PC:
        raise ValueError(f"非法调名: {key!r} (支持 C D E F G A B, 可带 # 或 b, 如 F# / Bb)")
    rest = k[1:]
    for c in rest:
        if c not in '#b':
            raise ValueError(f"非法调名: {key!r} (调名只能带 # 或 b)")
    return (_KEY_PC[base] + rest.count('#') - rest.count('b')) % 12


def _degree_to_midi(degree, acc, oct_up, oct_dn, key_pc):
    """简谱度数 -> MIDI 编号。key_pc 是 1 对应的音级, 基准八度为 4"""
    if degree == '0':
        return None
    semi = _DEGREE[degree] + (1 if acc == '#' else 0) - (1 if acc == 'b' else 0)
    # semi//12 处理跨八度: b1 应落到 B3 而不是 B4
    octave = 4 + oct_up - oct_dn + semi // 12
    return note_num(f"{_pc_name((key_pc + semi) % 12)}{octave}")


def _pc_name(pc):
    return ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][pc]


def parse_jianpu(text, key='C', beat=DEFAULT_BEAT, velocity=DEFAULT_VELOCITY):
    """简谱解析。语法:
    - 1~7 为音, 0 为休止
    - 后缀 '-' 每个延长一拍 (5- = 两拍)
    - 后缀 '^' 升八度, 'v' 降八度 (可叠加)
    - 前缀 '#'/'b' 升/降半音 (例: #4 b7)
    - 注释行以 // 开头, '|' 小节线忽略, 空白分隔音符"""
    events = []
    t = 0.0
    kpc = _key_pc(key)
    for raw in _strip_comments(text).replace('|', ' ').split():
        tok = raw.strip()
        if not tok:
            continue
        m = tok
        acc = ''
        if m[0] in '#b':
            acc, m = m[0], m[1:]
        if not m:
            raise ValueError(f"简谱 token 无法解析: {tok!r}")
        degree, rest = m[0], m[1:]
        if degree not in _DEGREE and degree != '0':
            raise ValueError(f"简谱 token 无法解析: {tok!r}")
        oct_up = oct_dn = ext = 0
        for c in rest:
            if c == '^':
                oct_up += 1
            elif c == 'v':
                oct_dn += 1
            elif c == '-':
                ext += 1
            else:
                raise ValueError(f"简谱 token 无法解析: {tok!r}")
        dur = (1 + ext) * beat
        n = _degree_to_midi(degree, acc, oct_up, oct_dn, kpc)
        if n is not None:
            events.append((t, dur, n, velocity))
        t += dur
    return events


# ---------- 3. MIDI 文件 ----------
def parse_midi(path, _velocity=DEFAULT_VELOCITY, min_dur=0.05):
    """解析 SMF 格式 0/1 MIDI 文件, 返回以秒为单位的事件列表。
    忽略打击乐通道(9), 音符裁剪到 A0~C8。

    `_velocity` 对 MIDI **不生效**: MIDI 自带每音符力度(0~127), 直接原样输出;
    统一力度只属于没有力度的谱面(简谱 / 音名序列), 故此处保留形参仅为调用签名一致。

    时间换算走「两遍法」: 第一遍只收集音符的绝对 tick 和各轨 tempo 事件, 第二遍用
    分段积分的 tempo map 把 tick 换算成秒。**不能**用「当前 tempo × 绝对 tick」,
    那是旧实现的 bug: tempo 是分段生效的, 每次变速都会把前面已累计的时间抹掉重算
    (format 1 里 tempo 只在第 0 轨, 其他轨会被最后一条 tempo 全程套用)。"""
    data = open(path, 'rb').read()
    if data[:4] != b'MThd':
        raise ValueError("不是有效的 MIDI 文件 (缺少 MThd)")
    _fmt, ntrk, division = struct.unpack('>HHH', data[8:14])   # fmt(0/1/2) 不参与决策, 保留解包对齐字节偏移
    if division == 0:
        raise ValueError("MIDI 文件损坏: time division 为 0")
    smpte = bool(division & 0x8000)   # SMPTE 时基: 时间与 tempo 无关
    pos = 14
    raw = []                # (start_tick, end_tick, note, vel)
    open_notes = {}         # (track, ch, note) -> (start_tick, vel)
    tempos = {}             # 绝对 tick -> us_pq (set tempo 元事件)
    last_tick = 0

    for ti in range(ntrk):
        if data[pos:pos + 4] != b'MTrk':
            raise ValueError(f"MIDI 文件损坏: 第 {ti + 1} 轨缺少 MTrk 标记")
        length = struct.unpack('>I', data[pos + 4:pos + 8])[0]
        end = pos + 8 + length
        p = pos + 8
        tick = 0
        running = None
        while p < end:
            # delta time
            dt = 0
            while True:
                b = data[p]; p += 1
                dt = (dt << 7) | (b & 0x7F)
                if not b & 0x80:
                    break
            tick += dt
            status = data[p]
            if status & 0x80:
                p += 1
                running = status if status < 0xF0 else None  # meta/sysex 不更新 running status (SMF 规范)
            else:
                if running is None:
                    raise ValueError(f"MIDI running status 异常 (偏移 {p})")
                status = running
            typ = status & 0xF0
            ch = status & 0x0F
            if typ == 0x90 or typ == 0x80:
                note, vel = data[p], data[p + 1]; p += 2
                if typ == 0x90 and vel > 0 and ch != 9:
                    open_notes[(ti, ch, note)] = (tick, vel)
                else:
                    key = (ti, ch, note)
                    if key in open_notes:
                        s, v = open_notes.pop(key)
                        raw.append((s, tick, note, v))
            elif typ == 0xB0 or typ == 0xA0 or typ == 0xE0:
                p += 2
            elif typ == 0xC0 or typ == 0xD0:
                p += 1
            elif status == 0xFF:
                meta = data[p]; p += 1
                length_m = 0                      # meta 长度是变长字段, 不能只读 1 字节
                while True:
                    b = data[p]; p += 1
                    length_m = (length_m << 7) | (b & 0x7F)
                    if not b & 0x80:
                        break
                if meta == 0x51 and length_m >= 3:
                    payload = data[p:p + 3]
                    tempos[tick] = (payload[0] << 16) | (payload[1] << 8) | payload[2]
                p += length_m
            elif status in (0xF0, 0xF7):  # sysex: 跳过变长长度字段及其数据
                ln = 0
                while True:
                    b = data[p]; p += 1
                    ln = (ln << 7) | (b & 0x7F)
                    if not b & 0x80:
                        break
                p += ln
            else:
                raise ValueError(f"MIDI 未知状态字节 {status:#04x} (偏移 {p - 1})")
        last_tick = max(last_tick, tick)
        pos = end

    # ---- tempo map: tick -> 秒 (分段累加, 全局一致, 与解析顺序/轨号无关) ----
    if smpte:
        fps = 256 - (division >> 8)          # 高字节是负的每秒帧数 (二补码)
        rate = fps * (division & 0xFF)       # 每秒 tick 数
        tick2sec = lambda t: t / rate
    else:
        segs = []                            # (起始 tick, 该 tick 处已累计秒数, 该段 us_pq)
        prev_tick, us, acc = 0, 500000, 0.0  # 默认 120bpm 起算
        for tk in sorted(tempos):
            if tk < 0:
                continue
            acc += (tk - prev_tick) * us / 1e6 / division
            segs.append((tk, acc, tempos[tk]))
            prev_tick, us = tk, tempos[tk]

        def tick2sec(tick):
            lo, hi = 0, len(segs)
            while lo < hi:                   # 二分找 tick 落在哪一段
                mid = (lo + hi) // 2
                if segs[mid][0] <= tick:
                    lo = mid + 1
                else:
                    hi = mid
            base_tick, base_sec, cur_us = segs[lo - 1] if lo else (0, 0.0, 500000)
            return base_sec + (tick - base_tick) * cur_us / 1e6 / division

    events = []
    for s, e, note, vel in raw:
        t0, t1 = tick2sec(s), tick2sec(e)
        if t1 - t0 >= min_dur:
            events.append((t0, t1 - t0, min(max(note, 21), 108), vel))
    # 没关掉的音在曲末关闭
    for (_ti, _ch, note), (s, v) in open_notes.items():
        t0 = tick2sec(s)
        t1 = max(tick2sec(last_tick), t0 + 1.0)
        if t1 - t0 >= min_dur:
            events.append((t0, t1 - t0, min(max(note, 21), 108), v))
    events.sort(key=lambda e: e[0])
    return events


# ---------- 统一入口 ----------
def load(source, fmt=None, key='C', beat=DEFAULT_BEAT, velocity=DEFAULT_VELOCITY):
    """根据来源自动/指定格式解析。source: 文本内容或 .mid 文件路径"""
    source = str(source)
    if source.lower().endswith(('.mid', '.midi')):
        return parse_midi(source, velocity)      # MIDI 走专用解析, fmt 不适用
    body, declared = _split_format_decl(source)
    fmt = fmt or declared
    if fmt is None:
        # 自动探测: 含裸数字/简谱记号 -> 简谱, 否则音名序列
        import re
        fmt = 'jianpu' if re.search(r'(^|\s)[#b]?[0-7](\^|v|-|\s|$)', body) else 'note_seq'
    if fmt == 'note_seq':
        return parse_note_seq(body, beat, velocity)
    if fmt == 'jianpu':
        return parse_jianpu(body, key=key, beat=beat, velocity=velocity)
    raise ValueError(f"未知格式: {fmt}")


def load_file(path, fmt=None, key='C', beat=DEFAULT_BEAT, velocity=DEFAULT_VELOCITY):
    """从文件加载。txt 文件支持 'format: jianpu/note_seq' 声明行 (任意位置)

    path 可以是显式路径, 也可以是裸曲名: 依次在 用户谱面库 -> 包内示例 里查找
    (见 library.py, 用户库在包外, 包更新不会影响)。"""
    from . import library
    path = str(library.resolve(path))
    if path.lower().endswith(('.mid', '.midi')):
        return parse_midi(path, velocity)
    text = open(path, encoding='utf-8').read()
    body, declared = _split_format_decl(text)
    return load(body, fmt=fmt or declared, key=key, beat=beat, velocity=velocity)

# -*- coding: utf-8 -*-
"""音符 ↔ MIDI 编号 ↔ 屏幕坐标 自动映射"""
from .config import KEY_X0, KEY_X_STEP, Y_BLACK, Y_BLACK_SPAN, Y_WHITE, Y_WHITE_SPAN, MIDI_MIN, MIDI_MAX

_PITCH = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
_PITCH_REV = {v: k for k, v in _PITCH.items()}
_BLACK = {1, 3, 6, 8, 10}  # C#/D#/F#/G#/A#


_NOTE_RE = None  # 延迟编译

def note_num(name: str) -> int:
    """科学音调记法音名 -> MIDI 编号。
    支持 'C4', 'C#4', 'Db4', '#F4'(前缀式) 等。'C4'->60, 'A0'->21, 'C#4'->61"""
    global _NOTE_RE
    import re
    if _NOTE_RE is None:
        _NOTE_RE = re.compile(r'([#b]?)([A-Ga-g])([#b]?)(-?\d+)$')
    m = _NOTE_RE.match(name.strip())
    if not m:
        raise ValueError(f"非法音名: {name!r} (如 C4 / C#4 / Db4)")
    pre, base, post, oct_str = m.groups()
    base = base.upper()
    if base not in _PITCH:
        raise ValueError(f"非法音名: {name!r}")
    acc_str = pre + post
    semi = _PITCH[base] + acc_str.count('#') - acc_str.count('b')
    octave = int(oct_str)
    n = (octave + 1) * 12 + semi
    if not (MIDI_MIN <= n <= MIDI_MAX):
        raise ValueError(f"音名 {name} 超出 FreePiano 音域 (A0~C8)")
    return n


def note_name(n: int) -> str:
    """MIDI 编号 -> 音名, 'C#4' 形式"""
    octave = n // 12 - 1
    semi = n % 12
    if semi in _BLACK:
        return f"{_PITCH_REV[semi - 1]}#{octave}"
    return f"{_PITCH_REV[semi]}{octave}"


def is_black(n: int) -> bool:
    return (n % 12) in _BLACK


def key_point(n: int, velocity: int = 100):
    """MIDI 编号 + 力度 -> 虚拟键盘客户区坐标 (x, y)。
    力度用点击纵向位置模拟: 越靠下力度越大。力度会被夹到 1~127,
    否则坐标会落到键盘区域之外, 点了不出声。"""
    if not (MIDI_MIN <= n <= MIDI_MAX):
        raise ValueError(f"MIDI 编号 {n} 超出音域 (21~108)")
    p = min(max(int(velocity), 1), 127) / 127.0
    code = n - MIDI_MIN
    x = int(KEY_X0 + code * KEY_X_STEP)
    if is_black(n):
        y = int(Y_BLACK + Y_BLACK_SPAN * p)
    else:
        y = int(Y_WHITE + Y_WHITE_SPAN * p)
    return x, y

# -*- coding: utf-8 -*-
"""FreePiano 演奏引擎 — 通过 PostMessage 鼠标消息点击虚拟键盘发声。
原理: FreePiano 用 WH_KEYBOARD_LL 钩子过滤一切注入键盘输入,
但其界面虚拟键盘响应鼠标消息, 而钩子只拦截键盘不拦截鼠标。
因此 PostMessage WM_LBUTTONDOWN/UP 即可演奏, 且无需前台焦点。

坐标基于参考客户区 752x400, 按真实客户区自动缩放 (兼容不同 DPI)。"""
import ctypes, time
from .config import (WINDOW_CLASS, DEFAULT_VELOCITY,
                     REF_CLIENT_W, REF_CLIENT_H)
from .mapping import note_num, key_point

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 512, 513, 514
u32 = ctypes.windll.user32


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def find_window():
    """返回 FreePiano 主窗口句柄, 找不到返回 0"""
    return u32.FindWindowW(WINDOW_CLASS, None)


def client_scale(hwnd):
    """真实客户区尺寸 / 参考尺寸 -> (sx, sy) 缩放系数"""
    r = _RECT()
    u32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return 1.0, 1.0
    return w / REF_CLIENT_W, h / REF_CLIENT_H


def is_minimized(hwnd):
    return bool(u32.IsIconic(hwnd))


def restore_no_activate(hwnd):
    """恢复最小化窗口且不抢前台焦点 (SW_SHOWNOACTIVATE=4)"""
    if is_minimized(hwnd):
        u32.ShowWindow(hwnd, 4)
        time.sleep(0.3)
        return True
    return False


def _mk_pos(x, y):
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def note_on(hwnd, n, velocity=DEFAULT_VELOCITY, sx=1.0, sy=1.0):
    x, y = key_point(n, velocity)
    pos = _mk_pos(int(x * sx), int(y * sy))
    u32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, pos)   # wParam=1 即 MK_LBUTTON
    u32.PostMessageW(hwnd, WM_MOUSEMOVE, 1, pos)


def note_off(hwnd, n, velocity=DEFAULT_VELOCITY, sx=1.0, sy=1.0):
    x, y = key_point(n, velocity)
    u32.PostMessageW(hwnd, WM_LBUTTONUP, 0, _mk_pos(int(x * sx), int(y * sy)))


def all_notes_off(hwnd, notes, sx=1.0, sy=1.0):
    """释放所有按住的键, 防止“卡音”"""
    for n in set(notes):
        try:
            note_off(hwnd, n, sx=sx, sy=sy)
        except Exception:
            pass


class Player:
    """演奏器: 事件格式 [(start_sec, dur_sec, midi_num, velocity), ...]

    ensure_process=True 时自动确保 FreePiano 已启动 (未安装/未找到会给出指引)。
    """

    def __init__(self, ensure_process=True, wait_sec=5):
        if ensure_process:
            from .process import ensure_running
            ensure_running(wait_sec)
        self.hwnd = find_window()
        if not self.hwnd:
            raise RuntimeError(
                "找不到 FreePiano 主窗口 (类名 " + WINDOW_CLASS + "), "
                "请确认 FreePiano 已启动且未最小化")
        restore_no_activate(self.hwnd)   # 最小化时自动恢复(不抢焦点)
        self._sx, self._sy = client_scale(self.hwnd)

    def play(self, events, on_progress=None):
        """按时间线演奏。演奏中每步检查窗口存活, 异常时释放全部按键。"""
        events = sorted(events, key=lambda e: e[0])
        held = []
        t0 = time.perf_counter()
        # 时间线: note_off 排在同刻 note_on 前, 避免同音重按冲突
        timeline = []
        for start, dur, n, vel in events:
            timeline.append((start, 'on', (n, vel)))
            timeline.append((start + dur, 'off', (n, vel)))
        timeline.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))
        for t, kind, (n, vel) in timeline:
            wait = t - (time.perf_counter() - t0)
            if wait > 0:
                time.sleep(wait)
            if not find_window():
                all_notes_off(self.hwnd, held, self._sx, self._sy)
                raise RuntimeError("演奏中止: FreePiano 窗口已关闭")
            if is_minimized(self.hwnd):
                # 演奏中被最小化: 自动恢复并重算缩放, 继续演奏
                restore_no_activate(self.hwnd)
                self._sx, self._sy = client_scale(self.hwnd)
            if kind == 'on':
                note_on(self.hwnd, n, vel, self._sx, self._sy)
                held.append(n)
            else:
                note_off(self.hwnd, n, vel, self._sx, self._sy)
                if n in held:
                    held.remove(n)
            if on_progress:
                on_progress(t, kind, n)
        all_notes_off(self.hwnd, held, self._sx, self._sy)
        return time.perf_counter() - t0

    def test_note(self, n=60, dur=0.8, velocity=100):
        """弹一个音用于验证链路 (默认中央 C)"""
        note_on(self.hwnd, n, velocity, self._sx, self._sy)
        time.sleep(dur)
        note_off(self.hwnd, n, velocity, self._sx, self._sy)

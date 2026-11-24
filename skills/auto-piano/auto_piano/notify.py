# -*- coding: utf-8 -*-
"""Windows 错误弹窗 / 蜂鸣提示 (仅失败/中止时使用; 成功用 print 输出)"""
import ctypes

TOPMOST, SETFG = 0x40000, 0x10000
INFO, WARN = 0x40, 0x30


def notify(title: str, text: str, icon: int = INFO):
    """置顶弹窗, 阻塞直到用户点确定"""
    try:
        import winsound
        if icon == WARN:
            winsound.Beep(1000, 300)
        else:
            winsound.Beep(800, 150)
    except Exception:
        pass
    ctypes.windll.user32.MessageBoxW(0, text, title, TOPMOST | SETFG | icon)

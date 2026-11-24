# -*- coding: utf-8 -*-
"""auto_piano — FreePiano 自动演奏包

用法:
    from auto_piano import Player, scores

    p = Player()                       # 自动确保 FreePiano 已启动
    p.test_note()                      # 弹一个中央 C 验证链路

    events = scores.load_file('songs/xiaoxingxing.txt')
    p.play(events)                     # 演奏!

谱面格式见 scores.py 模块文档。
"""
from .keyboard import Player, find_window
from . import scores, library
from .notify import notify

__all__ = ['Player', 'find_window', 'scores', 'library', 'notify']
__version__ = '1.0.0'

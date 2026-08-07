# -*- coding: utf-8 -*-
"""测试生成的变速 WAV 能否播放"""
import ctypes, time, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

for speed in ['1.1', '1.2']:
    fname = f'_speed_{speed}x.wav'
    fpath = os.path.join(BASE_DIR, fname)
    if not os.path.exists(fpath):
        print(f'{fname}: 不存在')
        continue
    
    buf = ctypes.create_unicode_buffer(512)
    ctypes.windll.kernel32.GetShortPathNameW(fpath, buf, 512)
    short = buf.value
    
    w = ctypes.windll.winmm
    w.mciSendStringW('close mt', None, 0, 0)
    ret = w.mciSendStringW(f'open "{short}" type waveaudio alias mt', None, 0, 0)
    print(f'{fname}: size={os.path.getsize(fpath)}, open={ret}')
    
    if ret == 0:
        w.mciSendStringW('play mt', None, 0, 0)
        buf2 = ctypes.create_unicode_buffer(256)
        while True:
            w.mciSendStringW('status mt mode', buf2, 256, 0)
            if buf2.value != 'playing':
                break
            time.sleep(0.08)
        w.mciSendStringW('close mt', None, 0, 0)
        print(f'  -> 播放完成')
    else:
        buf2 = ctypes.create_unicode_buffer(256)
        w.mciGetErrorStringW(ret, buf2, 256)
        print(f'  -> 错误: {buf2.value}')

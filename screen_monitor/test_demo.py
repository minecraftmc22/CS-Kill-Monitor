# -*- coding: utf-8 -*-
"""
模拟测试场景
1. 自动生成测试用图片和音频
2. 创建一个无边框颜色方块窗口
3. 启动屏幕监控子进程（自动模式）
4. 倒计时后将窗口颜色切换为触发目标色
5. 如画中画弹出 + 音频响起，则测试通过
"""

import json
import math
import os
import struct
import subprocess
import sys
import time
import tkinter as tk
import wave

# ---- 颜色定义 ----
BG_COLOR       = '#333333'   # 模拟窗口初始颜色（深灰）
TRIGGER_COLOR  = (0, 255, 136)  # 触发目标颜色（亮绿）
TRIGGER_HEX    = '#00ff88'

SIM_WIN_W = 200
SIM_WIN_H = 200
SIM_WIN_X = 100
SIM_WIN_Y = 100

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_test_image():
    """生成画中画用测试图片"""
    from PIL import Image, ImageDraw, ImageFont

    w, h = 500, 360
    img = Image.new('RGB', (w, h), color=(20, 22, 30))
    draw = ImageDraw.Draw(img)

    # 外侧亮绿边框
    draw.rectangle([4, 4, w - 5, h - 5], outline=TRIGGER_COLOR, width=3)

    # 内层半透明框
    draw.rectangle([20, 20, w - 20, h - 20], outline=(40, 44, 55), width=1)

    # 图标：对勾
    cx, cy = w // 2, 110
    r = 35
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=TRIGGER_COLOR, width=4)
    # 简化的勾
    pts = [(cx - 18, cy + 4), (cx - 4, cy + 20), (cx + 20, cy - 12)]
    draw.line(pts, fill=TRIGGER_COLOR, width=5, joint='curve')

    # 主标题
    draw.text((w // 2, 175), 'TRIGGERED!', fill=TRIGGER_COLOR, anchor='mm')
    draw.text((w // 2, 210), '像素匹配成功', fill=TRIGGER_COLOR, anchor='mm')

    # 详细信息
    draw.text((w // 2, 265), '屏幕像素监控  ·  画中画测试', fill=(160, 162, 170), anchor='mm')
    draw.text((w // 2, 295), f'目标颜色 RGB{TRIGGER_COLOR}', fill=(100, 102, 110), anchor='mm')

    path = os.path.join(BASE_DIR, 'test_alert.png')
    img.save(path)
    print(f'  [OK] 测试图片已生成: {path}')
    return path


def generate_test_audio():
    """生成测试音频（880Hz 正弦波，带淡入淡出）"""
    sample_rate = 44100
    freq = 880
    duration = 0.6
    fade = 0.05

    n_total = int(sample_rate * duration)
    n_fade = int(sample_rate * fade)

    path = os.path.join(BASE_DIR, 'test_alert.wav')
    with wave.open(path, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)

        for i in range(n_total):
            t = i / sample_rate
            envelope = min(1.0, i / max(n_fade, 1),
                           (n_total - i) / max(n_fade, 1))
            sample = int(16000 * envelope * math.sin(2 * math.pi * freq * t))
            wav.writeframes(struct.pack('<h', max(-32768, min(32767, sample))))

    print(f'  [OK] 测试音频已生成: {path}')
    return os.path.abspath(path)


def write_test_config(region_left: int, region_top: int,
                      region_w: int, region_h: int,
                      audio_path: str, image_path: str):
    """将测试触发规则写入配置文件（区域模式）"""
    config = {
        "check_rate": 20,
        "cooldown": 2000,
        "triggers": [
            {
                "name": "测试触发器 - 区域变化",
                "type": "region",
                "region": {"left": region_left, "top": region_top,
                           "width": region_w, "height": region_h},
                "tolerance": 30,
                "change_threshold": 0.05,
                "monitor": 1,
                "audio_path": audio_path,
                "image_path": image_path,
                "display_duration": 8000,
                "pip": {
                    "position": [300, 100],
                    "size": [800, 600],
                    "alpha": 0.7
                }
            }
        ]
    }

    path = os.path.join(BASE_DIR, 'test_config.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    print(f'  [OK] 测试配置已生成: {path}\n')


def start_monitor():
    """以子进程方式启动屏幕监控（自动开始）"""
    script = os.path.join(BASE_DIR, 'screen_monitor.py')
    config = os.path.join(BASE_DIR, 'test_config.json')
    proc = subprocess.Popen(
        [sys.executable, script, config, '--auto'],
        cwd=BASE_DIR,
    )
    print('  [OK] 监控子进程已启动 (PID={})\n'.format(proc.pid))
    return proc


def run():
    """主测试流程"""
    print('=' * 55)
    print('  屏幕像素监控 — 模拟测试')
    print('=' * 55)

    # ---------- 1. 生成测试资源 ----------
    print('\n[1/5] 准备测试资源 ...')
    img_path = os.path.join(BASE_DIR, '980d5eff3a1143f38fa06ea431778013.jpg')
    aud_path = generate_test_audio()
    print(f'  [OK] 使用已有图片: {img_path}')

    # ---------- 2. 创建模拟窗口 ----------
    print('\n[2/5] 创建模拟触发窗口 ...')
    root = tk.Tk()
    root.withdraw()

    sim = tk.Toplevel(root)
    sim.overrideredirect(True)                           # 无边框，坐标精确
    sim.attributes('-topmost', True)
    sim.geometry(f'{SIM_WIN_W}x{SIM_WIN_H}+{SIM_WIN_X}+{SIM_WIN_Y}')
    sim.configure(bg=BG_COLOR)

    # 窗口内显示文字提示
    label = tk.Label(sim, text='等待触发...', font=('Microsoft YaHei', 11),
                     fg='#888888', bg=BG_COLOR)
    label.place(relx=0.5, rely=0.5, anchor='center')

    # 强制刷新以获取准确坐标
    sim.update_idletasks()
    sim.update()
    root.update_idletasks()
    root.update()
    time.sleep(0.3)

    # 计算监控区域（整个模拟窗口）
    region_x = sim.winfo_rootx()
    region_y = sim.winfo_rooty()
    print(f'  模拟窗口位置: ({region_x}, {region_y})  尺寸: {SIM_WIN_W}x{SIM_WIN_H}')
    print(f'  监控区域: left={region_x} top={region_y} width={SIM_WIN_W} height={SIM_WIN_H}\n')

    # ---------- 3. 写入配置并启动监控 ----------
    print('[3/5] 写入测试配置并启动监控（区域模式）...')
    write_test_config(region_x, region_y, SIM_WIN_W, SIM_WIN_H, aud_path, img_path)
    monitor_proc = start_monitor()
    time.sleep(2)  # 等待监控初始化完成

    # ---------- 4. 倒计时并触发 ----------
    print('[4/5] 倒计时 ...')
    for i in range(5, 0, -1):
        label.configure(text=f'{i} 秒后触发...')
        print(f'  {i} ...')
        sim.update()
        time.sleep(1)

    print('\n  >>> 切换窗口颜色为 TRIGGER_COLOR <<<\n')
    sim.configure(bg=TRIGGER_HEX)
    label.configure(text='已触发！', fg='#ffffff', bg=TRIGGER_HEX, font=('Microsoft YaHei', 14, 'bold'))
    sim.update()

    # ---------- 5. 等待验证 ----------
    print('[5/5] 等待验证 ...')
    print('  如果画中画窗口弹出 + 听到音频 → 测试通过 ✓')
    print('  10 秒后自动关闭 ...')
    time.sleep(10)

    # ---------- 清理 ----------
    print('\n清理资源 ...')
    monitor_proc.terminate()
    monitor_proc.wait(timeout=5)
    sim.destroy()
    root.destroy()

    # 清理测试文件
    for f in ['test_alert.wav', 'test_config.json']:
        p = os.path.join(BASE_DIR, f)
        if os.path.exists(p):
            os.remove(p)

    print('测试结束。')


if __name__ == '__main__':
    run()

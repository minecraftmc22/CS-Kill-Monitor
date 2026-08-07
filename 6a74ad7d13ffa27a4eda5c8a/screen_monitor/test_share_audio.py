# -*- coding: utf-8 -*-
"""
音频分享测试工具
- 扫描所有输出设备
- 生成测试音（440Hz 正弦波）
- 依次向每个设备发送音频，验证是否能输出
- 最后同时向默认扬声器 + 选定设备双路输出
"""

import numpy as np
import sounddevice as sd
import soundfile as sf
import time
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def generate_test_tone(freq=440, duration=0.5, sr=44100):
    """生成测试正弦波音频。"""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.5 * np.sin(2 * np.pi * freq * t)
    # 渐入渐出避免爆音
    fade = int(sr * 0.01)
    tone[:fade] *= np.linspace(0, 1, fade)
    tone[-fade:] *= np.linspace(1, 0, fade)
    return tone.astype(np.float32), sr


def save_test_wav(tone, sr, path):
    """保存测试音频到文件。"""
    sf.write(path, tone, sr)
    return path


def scan_devices():
    """扫描并分类所有音频设备。"""
    outputs = []
    inputs = []
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        name = d['name']
        ch_out = d['max_output_channels']
        ch_in = d['max_input_channels']
        sr = d['default_samplerate']

        tag = ''
        if any(kw in name.lower() for kw in ['cable', 'virtual', 'voicemeeter', 'vb-audio']):
            tag = ' *** [虚拟设备] ***'

        if ch_out > 0:
            outputs.append((i, name, ch_out, int(sr), tag))
        if ch_in > 0:
            inputs.append((i, name, ch_in, int(sr), tag))
    return outputs, inputs


def test_single_device(dev_id, dev_name, tone, sr, label=''):
    """测试向单个设备播放音频。"""
    print(f'  [{label}] -> {dev_name} (ID={dev_id}) ... ', end='', flush=True)
    try:
        sd.play(tone, samplerate=sr, device=dev_id, blocking=True)
        print('✓ 成功')
        return True
    except Exception as e:
        print(f'✗ 失败: {e}')
        return False


def test_dual_output(dev1_id, dev1_name, dev2_id, dev2_name, tone, sr):
    """测试双路同时输出（模拟真实分享场景）。"""
    print(f'\n双路输出测试:')
    print(f'  路1 (你听):   {dev1_name}')
    print(f'  路2 (队友听): {dev2_name}')
    print(f'  播放中 ... ', end='', flush=True)

    try:
        sd.play(tone, samplerate=sr, device=dev1_id, blocking=False)
        time.sleep(0.03)
        sd.play(tone, samplerate=sr, device=dev2_id, blocking=False)
        time.sleep(len(tone) / sr + 0.2)
        print('✓ 双路输出完成')
        return True
    except Exception as e:
        print(f'✗ 失败: {e}')
        return False


def main():
    print('=' * 60)
    print('  音频分享设备测试工具')
    print('=' * 60)

    # 生成测试音
    tone, sr = generate_test_tone(freq=440, duration=0.6)
    wav_path = os.path.join(BASE_DIR, '_test_tone.wav')
    save_test_wav(tone, sr, wav_path)
    print(f'\n测试音: {wav_path} (440Hz, 0.6s)')

    # 扫描设备
    outputs, inputs = scan_devices()

    print(f'\n--- 输出设备 ({len(outputs)} 个) ---')
    for i, name, ch, srate, tag in outputs:
        print(f'  ID={i:2d}  [{ch}ch @ {srate}Hz] {name}{tag}')

    print(f'\n--- 输入设备 ({len(inputs)} 个) ---')
    for i, name, ch, srate, tag in inputs:
        print(f'  ID={i:2d}  [{ch}ch @ {srate}Hz] {name}{tag}')

    # ========================================
    # 单路测试：逐个设备播放
    # ========================================
    print(f'\n{"=" * 60}')
    print('  单路输出测试（逐个设备播放测试音）')
    print('=' * 60)

    # 只测试前几个输出设备（避免太久）
    test_count = min(len(outputs), 5)
    for idx in range(test_count):
        dev_id, name, *_ = outputs[idx]
        test_single_device(dev_id, name, tone, sr, f'设备{idx + 1}')

    # ========================================
    # 双路测试
    # ========================================
    print(f'\n{"=" * 60}')
    print('  双路输出测试（模拟击杀分享）')
    print('=' * 60)

    default_out = sd.default.device[1]
    default_name = sd.query_devices()[default_out]['name']

    # 找虚拟设备
    virtual = None
    for dev_id, name, *_ in outputs:
        if any(kw in name.lower() for kw in ['cable', 'virtual', 'voicemeeter', 'vb-audio']):
            virtual = (dev_id, name)
            break

    if virtual:
        test_dual_output(default_out, default_name, virtual[0], virtual[1], tone, sr)
        print(f'\n✓ 虚拟设备 {virtual[1]} 可用 - 分享功能就绪！')
    else:
        # 用第二个输出设备代替（如果存在）
        if len(outputs) >= 2:
            dev2 = outputs[1]
            test_dual_output(default_out, default_name, dev2[0], dev2[1], tone, sr)
            print(f'\n提示: 未检测到虚拟设备。安装 VB-Cable 后重新扫描即可。')
            print(f'  下载: https://vb-audio.com/Cable/')
        else:
            print('\n只有 1 个输出设备，无法进行双路测试。')

    print(f'\n{"=" * 60}')
    print('  测试完成')
    print('=' * 60)


if __name__ == '__main__':
    main()

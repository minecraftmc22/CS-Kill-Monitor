# -*- coding: utf-8 -*-
"""
CSGO 击杀监控 — 通过 Game State Integration (GSI) 实时获取击杀记录。
每检测到一次击杀 → 弹出图片 + 播放音频 + 后台记录日志。
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import winsound
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import imageio_ffmpeg
import sounddevice as sd
import soundfile as sf
from PIL import Image, ImageTk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
LOG_PATH = os.path.join(BASE_DIR, 'kill_log.txt')

# Windows API 常量
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040


# ======================== PipWindow ========================
class PipWindow:
    """无边框半透明图片窗口，Windows API 级强制置顶，支持拖拽和点击关闭。"""

    def __init__(self, image_path: str, position: tuple, size: tuple,
                 auto_close: int = 0, fullscreen: bool = False,
                 alpha: float = 0.5):
        self.root = tk.Toplevel()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', 1)
        self.root.attributes('-alpha', alpha)

        if fullscreen:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            size = (sw, sh)
            position = (0, 0)

        self.root.configure(bg='black')
        self.root.geometry(f'{size[0]}x{size[1]}+{position[0]}+{position[1]}')

        self.root.update()
        self._force_topmost()
        self.root.after(50, self._force_topmost)
        self.root.after(200, self._force_topmost)
        # 定时刷新置顶，防止被全屏游戏覆盖
        self._topmost_timer = self.root.after(500, self._keep_topmost)

        inner = tk.Frame(self.root, bg='black')
        inner.pack(fill=tk.BOTH, expand=True)

        try:
            img = Image.open(image_path)
            img = img.resize(size, Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            tk.Label(inner, image=self._photo, cursor='hand2', bg='black').pack(fill=tk.BOTH, expand=True)
        except Exception as exc:
            print(f'[PIP] 图片加载失败: {exc}', flush=True)

        self.root.bind('<Button-1>', lambda e: self.close())
        if auto_close > 0:
            self.root.after(auto_close, self.close)

    def _force_topmost(self):
        """通过 Windows API SetWindowPos 强制置顶。"""
        try:
            hwnd = self.root.frame()
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        except Exception:
            pass

    def _keep_topmost(self):
        """定时刷新置顶状态，防止被全屏应用覆盖。"""
        if self.root.winfo_exists():
            self._force_topmost()
            self._topmost_timer = self.root.after(500, self._keep_topmost)

    def close(self):
        try:
            self.root.after_cancel(self._topmost_timer)
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ======================== GSI HTTP Handler ========================
class GSIHandler(BaseHTTPRequestHandler):
    """接收 CSGO Game State Integration 的 HTTP POST 数据。"""

    monitor = None  # 由外部注入

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            data = json.loads(body)
            if self.monitor:
                self.monitor._root.after(0, lambda d=data: self.monitor._process_gsi(d))
        except json.JSONDecodeError:
            pass
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # 抑制 HTTP 日志


# ======================== 主监控类 ========================
class KillMonitor:
    def __init__(self):
        # tkinter (必须最先创建，BooleanVar 需要 root)
        self._root = tk.Tk()
        self._root.withdraw()

        self._load_config()
        self._kill_count = -1   # -1 表示尚未从 GSI 获取初始值
        self._speed = 1.0       # 音频播放速度倍率，每击杀 +0.1
        self._show_image = tk.BooleanVar(value=True)  # 是否显示图片
        self._play_sound = tk.BooleanVar(value=True)  # 是否播放音频
        self._share_audio = tk.BooleanVar(value=False)  # 是否分享音频到麦克风
        self._share_device_id = None   # 用户选择的分享设备 ID
        self._share_devices = []       # 可用输出设备列表 [(id, name), ...]
        self._share_device_var: tk.StringVar | None = None  # 下拉菜单变量
        self._server: HTTPServer | None = None
        self._active_pip: PipWindow | None = None

        # 确保音频为 WAV 格式（变速需要 WAV）
        self._audio_wav = self._ensure_wav()

        self._root.title('CSGO 击杀监控')
        self._root.protocol('WM_DELETE_WINDOW', self._on_quit)
        self._build_ui()
        self._scan_audio_devices()
        self._rebuild_device_menu()
        self._log('CSGO 击杀监控已就绪，等待 GSI 数据 ...')

    # ======================== 配置 ========================
    def _load_config(self):
        path = Path(CONFIG_PATH)
        if not path.exists():
            self.config = {'port': 3000, 'audio_path': 'alert.wav',
                           'image_path': '980d5eff3a1143f38fa06ea431778013.jpg',
                           'display_duration': 1000, 'pip': {'fullscreen': True, 'alpha': 0.7}}
            return
        with open(path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    # ======================== 音频 ========================
    def _ensure_wav(self) -> str:
        """确保音频文件为 WAV 格式，如果不是则用 ffmpeg 转换。返回 WAV 路径。"""
        path = self.config.get('audio_path', 'alert.wav')
        full = os.path.join(BASE_DIR, path) if not os.path.isabs(path) else path

        if not os.path.exists(full):
            print(f'[AUDIO] 文件不存在: {full}', flush=True)
            return full

        # 已经是 WAV，直接返回
        if full.lower().endswith('.wav'):
            print(f'[AUDIO] WAV 就绪: {os.path.basename(full)}', flush=True)
            return full

        # 需要转换
        wav_path = os.path.splitext(full)[0] + '.wav'
        if os.path.exists(wav_path):
            print(f'[AUDIO] WAV 缓存: {os.path.basename(wav_path)}', flush=True)
            return wav_path

        print(f'[AUDIO] 转换中: {os.path.basename(full)} -> WAV ...', flush=True)
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, '-y', '-i', full, '-acodec', 'pcm_s16le', wav_path],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if os.path.exists(wav_path):
            print(f'[AUDIO] 转换完成: {os.path.basename(wav_path)} '
                  f'({os.path.getsize(wav_path)} bytes)', flush=True)
            return wav_path
        else:
            print(f'[AUDIO] 转换失败!', flush=True)
            return full

    def _play_audio(self):
        """winsound 播放 WAV（变速+变调），每击杀 +0.1x。"""
        full = self._audio_wav
        if not os.path.exists(full):
            print(f'[AUDIO] 文件不存在: {full}', flush=True)
            return
        speed = self._speed
        threading.Thread(target=self._play_speed, args=(full, speed), daemon=True).start()

    def _play_speed(self, path: str, speed: float):
        """后台线程：用 ffmpeg 生成变速+变调 WAV，再用 winsound 播放。"""
        if speed != 1.0:
            cache_name = f'_speed_{speed:.1f}x.wav'
            cache_path = os.path.join(BASE_DIR, cache_name)
            if not os.path.exists(cache_path):
                # rubberband: 同时改变速度(tempo)和音调(pitch)
                filter_str = f'rubberband=tempo={speed:.1f}:pitch={speed:.1f}'
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                subprocess.run(
                    [ffmpeg, '-y', '-i', path, '-filter:a', filter_str,
                     '-acodec', 'pcm_s16le', cache_path],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if not os.path.exists(cache_path):
                    # 回退: atempo + asetrate
                    filter_str = f'atempo={speed:.1f},asetrate=44100*{speed:.1f}'
                    subprocess.run(
                        [ffmpeg, '-y', '-i', path, '-filter:a', filter_str,
                         '-acodec', 'pcm_s16le', cache_path],
                        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                    )
            play_path = cache_path
        else:
            play_path = path

        try:
            if self._share_audio.get() and self._share_device_id is not None:
                self._play_to_devices(play_path, speed)
            else:
                winsound.PlaySound(play_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            print(f'[AUDIO] {"分享" if self._share_audio.get() and self._share_device_id is not None else "本地"}'
                  f' @ {speed:.1f}x (变速+变调)', flush=True)
        except Exception as exc:
            print(f'[AUDIO] 失败: {exc}', flush=True)

    # ======================== 音频分享（队友可听） ========================
    def _scan_audio_devices(self):
        """扫描所有可用输出设备，供用户选择分享目标。"""
        self._share_devices = []
        try:
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                name = d['name']
                if d['max_output_channels'] > 0:
                    # 标记虚拟设备（VB-Cable / Voicemeeter 等）
                    tag = ''
                    if any(kw in name.lower() for kw in
                           ['cable', 'virtual', 'voicemeeter', 'vb-audio']):
                        tag = ' [虚拟]'
                    self._share_devices.append((i, f'{name}{tag}'))
        except Exception as exc:
            print(f'[AUDIO] 设备扫描失败: {exc}', flush=True)

    def _play_to_devices(self, wav_path: str, speed: float):
        """将 WAV 同时播放到默认扬声器（自己听）和用户选择的分享设备（队友听）。"""
        if self._share_device_id is None:
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            print('[AUDIO] 未选择分享设备，仅本地播放', flush=True)
            return

        try:
            data, sr = sf.read(wav_path, dtype='float32')
            if data.ndim == 1:
                data = data.reshape(-1, 1)

            default_out = sd.default.device[1]  # 默认扬声器

            # 播放到默认扬声器
            sd.play(data, samplerate=sr, device=default_out, blocking=False)
            time.sleep(0.03)
            # 播放到用户选择的设备
            sd.play(data, samplerate=sr, device=self._share_device_id, blocking=False)

            print(f'[AUDIO] 双路输出: 扬声器 + 设备#{self._share_device_id}', flush=True)
        except Exception as exc:
            print(f'[AUDIO] 双路输出失败: {exc}，回退 winsound', flush=True)
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

    # ======================== 日志 ========================
    def _log(self, msg: str):
        timestamp = time.strftime('%H:%M:%S')
        line = f'[{timestamp}] {msg}'
        print(line, flush=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f'{line}\n')

    # ======================== UI ========================
    def _build_ui(self):
        win = tk.Toplevel(self._root)
        win.title('CSGO 击杀监控')
        win.geometry('350x380')
        win.resizable(False, False)
        win.protocol('WM_DELETE_WINDOW', self._on_quit)

        tk.Label(win, text='CSGO 击杀监控 (GSI)', font=('Microsoft YaHei', 13, 'bold')).pack(pady=(12, 4))

        self._status_var = tk.StringVar(value='● 等待 GSI 连接 ...')
        tk.Label(win, textvariable=self._status_var, font=('Microsoft YaHei', 10), fg='gray').pack(pady=(0, 4))

        self._kill_var = tk.StringVar(value='击杀数: --')
        tk.Label(win, textvariable=self._kill_var, font=('Consolas', 18, 'bold'), fg='#00cc66').pack(pady=4)

        self._speed_var = tk.StringVar(value='速度: 1.0x')
        tk.Label(win, textvariable=self._speed_var, font=('Consolas', 11), fg='#cc6600').pack(pady=(0, 4))

        info = tk.Frame(win)
        info.pack(pady=2)
        tk.Label(info, text=f'端口: {self.config["port"]}', font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=10)
        tk.Label(info, text=f'日志: kill_log.txt', font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=10)

        toggle_frame = tk.Frame(win)
        toggle_frame.pack(pady=4)
        tk.Checkbutton(toggle_frame, text='播放图片', variable=self._show_image,
                       font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(toggle_frame, text='播放音频', variable=self._play_sound,
                       font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=10)

        share_frame = tk.Frame(win)
        share_frame.pack(pady=(2, 0))
        tk.Checkbutton(share_frame, text='分享音频到麦克风（队友可听）',
                       variable=self._share_audio, command=self._on_share_toggle,
                       font=('Microsoft YaHei', 9)).pack(side=tk.LEFT)

        device_frame = tk.Frame(win)
        device_frame.pack(pady=(2, 0))
        tk.Label(device_frame, text='目标设备:', font=('Microsoft YaHei', 9)).pack(side=tk.LEFT)
        self._share_device_var = tk.StringVar(value='')
        self._share_device_menu = tk.OptionMenu(device_frame, self._share_device_var, '')
        self._share_device_menu.config(font=('Microsoft YaHei', 8), width=28)
        self._share_device_menu.pack(side=tk.LEFT, padx=4)
        self._share_refresh_btn = tk.Button(device_frame, text='⟳', width=2,
                                             command=self._refresh_share_devices,
                                             font=('Microsoft YaHei', 9))
        self._share_refresh_btn.pack(side=tk.LEFT)

        self._share_info_var = tk.StringVar(value='')
        tk.Label(win, textvariable=self._share_info_var,
                 font=('Microsoft YaHei', 8), fg='#888').pack(pady=(0, 2))

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=8)
        self._start_btn = tk.Button(btn_frame, text='▶  启动服务', width=14,
                                     command=self.start, font=('Microsoft YaHei', 10))
        self._start_btn.pack(side=tk.LEFT, padx=6)
        self._stop_btn = tk.Button(btn_frame, text='■  停止服务', width=14,
                                    command=self.stop, state=tk.DISABLED,
                                    font=('Microsoft YaHei', 10))
        self._stop_btn.pack(side=tk.LEFT, padx=6)

        btn_row2 = tk.Frame(win)
        btn_row2.pack(pady=(2, 6))
        tk.Button(btn_row2, text='重置计数', command=self._reset_kills,
                  font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_row2, text='重置速度', command=self._reset_speed,
                  font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=6)

    def _update_status(self, text: str, color: str = 'gray'):
        self._status_var.set(text)
        self._status_var.set('')  # force refresh
        self._status_var.set(text)

    # ======================== GSI 数据处理 ========================
    def _process_gsi(self, data: dict):
        """解析 GSI JSON，检测击杀数变化。"""
        try:
            player = data.get('player', {})
            stats = player.get('match_stats', {})
            kills = stats.get('kills')

            if kills is None:
                return

            # 首次收到数据，初始化计数
            if self._kill_count < 0:
                self._kill_count = kills
                self._speed = 1.0
                self._kill_var.set(f'击杀数: {kills}')
                self._speed_var.set(f'速度: {self._speed:.1f}x')
                if self._status_var.get().startswith('● 等待'):
                    self._update_status('● 已连接（等待击杀）', '#0099cc')
                self._log(f'GSI 已连接，当前击杀数: {kills}')
                return

            if kills > self._kill_count:
                delta = kills - self._kill_count
                self._kill_count = kills
                self._kill_var.set(f'击杀数: {kills}')
                for _ in range(delta):
                    self._on_kill(kills)
            elif kills < self._kill_count:
                # 新对局开始，重置
                self._kill_count = kills
                self._speed = 1.0
                self._kill_var.set(f'击杀数: {kills}')
                self._speed_var.set('速度: 1.0x')
                self._log(f'新对局，击杀数重置为 {kills}，速度重置为 1.0x')
        except Exception as exc:
            print(f'[GSI] 解析错误: {exc}', flush=True)

    def _on_kill(self, total: int):
        """触发一次击杀事件。"""
        self._log(f'击杀! 总计: {total}  |  速度: {self._speed:.1f}x'
                  f'  |  图片: {"开" if self._show_image.get() else "关"}'
                  f'  |  音频: {"开" if self._play_sound.get() else "关"}')
        if self._play_sound.get():
            self._play_audio()
        if self._show_image.get():
            self._show_pip()
        self._speed += 0.1
        self._speed = round(self._speed, 1)  # 避免浮点累积误差
        self._speed_var.set(f'速度: {self._speed:.1f}x')

    def _show_pip(self):
        if self._active_pip:
            self._active_pip.close()
        pip_cfg = self.config.get('pip', {})
        image = self.config.get('image_path', '980d5eff3a1143f38fa06ea431778013.jpg')
        full = os.path.join(BASE_DIR, image) if not os.path.isabs(image) else image
        self._active_pip = PipWindow(
            image_path=full,
            position=tuple(pip_cfg.get('position', [0, 0])),
            size=tuple(pip_cfg.get('size', [800, 600])),
            auto_close=self.config.get('display_duration', 1000),
            fullscreen=pip_cfg.get('fullscreen', True),
            alpha=pip_cfg.get('alpha', 0.7),
        )

    # ======================== 生命周期 ========================
    def start(self):
        GSIHandler.monitor = self
        port = self.config.get('port', 3000)
        self._server = HTTPServer(('127.0.0.1', port), GSIHandler)
        self._start_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.NORMAL)
        self._update_status('● 服务运行中（等待游戏连接）', '#0099cc')
        self._log(f'HTTP 服务已启动 http://127.0.0.1:{port}')
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._start_btn.configure(state=tk.NORMAL)
        self._stop_btn.configure(state=tk.DISABLED)
        self._update_status('● 已停止', 'gray')
        self._log('服务已停止')

    def _reset_kills(self):
        self._kill_count = -1
        self._speed = 1.0
        self._kill_var.set('击杀数: --')
        self._speed_var.set('速度: 1.0x')
        self._update_status('● 已连接（等待击杀）', '#0099cc')
        self._log('击杀计数已手动重置，速度重置为 1.0x')

    def _reset_speed(self):
        self._speed = 1.0
        self._speed_var.set('速度: 1.0x')
        self._log('速度已重置为 1.0x')

    def _refresh_share_devices(self):
        """刷新音频设备列表并重建下拉菜单。"""
        self._scan_audio_devices()
        self._rebuild_device_menu()
        self._log('音频设备列表已刷新')

    def _on_share_toggle(self):
        """分享开关切换时的回调。"""
        self._refresh_share_info()

    def _on_device_select(self, choice: str):
        """用户在设备下拉菜单中选择了设备。"""
        for dev_id, name in self._share_devices:
            if name == choice:
                self._share_device_id = dev_id
                self._log(f'分享设备选择: {name}')
                return
        self._share_device_id = None

    def _rebuild_device_menu(self):
        """重建设备选择下拉菜单。"""
        if not self._share_device_var:
            return
        menu = self._share_device_menu['menu']
        menu.delete(0, 'end')
        if not self._share_devices:
            menu.add_command(label='(无可用设备)', state='disabled')
            self._share_device_var.set('(无可用设备)')
            return
        for dev_id, name in self._share_devices:
            menu.add_command(label=name, command=lambda n=name: self._on_device_select(n))
        # 默认选第一个
        first = self._share_devices[0][1]
        self._share_device_var.set(first)
        self._on_device_select(first)

    def _refresh_share_info(self):
        """更新分享信息显示。"""
        if not self._share_audio.get():
            self._share_info_var.set('分享已关闭')
            return
        if self._share_device_id is not None:
            try:
                name = sd.query_devices()[self._share_device_id]['name']
                self._share_info_var.set(f'目标设备: {name}')
            except Exception:
                self._share_info_var.set('设备已变更，请刷新')
        else:
            self._share_info_var.set('请在下拉菜单选择目标设备')

    def _on_quit(self):
        self.stop()
        self._root.destroy()

    def run(self):
        self.start()
        self._root.mainloop()


# ======================== 入口 ========================
if __name__ == '__main__':
    KillMonitor().run()

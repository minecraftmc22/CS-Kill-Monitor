# -*- coding: utf-8 -*-
"""
屏幕像素监控应用
监控屏幕指定位置的像素颜色，匹配时弹出画中画图片并播放音频。
"""

import ctypes
import json
import os
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import mss
from PIL import Image, ImageTk

# Windows API 常量
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040


class PipWindow:
    """画中画悬浮窗 —— 无边框半透明图片窗口，始终置顶，支持拖拽和点击关闭。"""

    def __init__(self, image_path: str, position: tuple, size: tuple,
                 auto_close: int = 0, fullscreen: bool = False,
                 alpha: float = 0.5, on_close=None):
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
        print(f'[PIP] 窗口已创建: {size[0]}x{size[1]} @ ({position[0]},{position[1]}) fullscreen={fullscreen}', flush=True)

        # 强制置顶：先 update 确保窗口创建完毕，再通过 Windows API 置顶
        self.root.update()
        self._force_topmost()
        self.root.after(50, self._force_topmost)
        self.root.after(200, self._force_topmost)
        self._topmost_timer = self.root.after(500, self._keep_topmost)
        print(f'[PIP] 窗口已置顶 (Windows API)', flush=True)

        # 内边距实现边框效果
        inner = tk.Frame(self.root, bg='black')
        inner.pack(fill=tk.BOTH, expand=True)

        try:
            img = Image.open(image_path)
            orig_w, orig_h = img.size
            img = img.resize(size, Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)

            label = tk.Label(inner, image=self._photo, cursor='hand2', bg='black')
            label.pack(fill=tk.BOTH, expand=True)
            print(f'[PIP] 图片加载成功: {image_path} (原始 {orig_w}x{orig_h} → 缩放 {size[0]}x{size[1]})', flush=True)
        except Exception as exc:
            print(f'[PIP] 图片加载失败: {image_path} → {exc}', flush=True)
            err = tk.Label(inner, text=f'图片加载失败\n{image_path}\n{exc}',
                           fg='red', bg='black', wraplength=size[0] - 20)
            err.pack(expand=True)

        # 绑定事件
        self.root.bind('<Button-1>', self._on_click)
        self.root.bind('<B1-Motion>', self._on_drag)
        self.root.bind('<ButtonRelease-1>', self._on_release)
        self.root.bind('<Button-3>', lambda e: self.close())
        self._drag_data = {'x': 0, 'y': 0, 'dragging': False}

        self._on_close = on_close

        if auto_close > 0:
            self.root.after(auto_close, self.close)

    # ---- 拖拽 ----
    def _on_click(self, event):
        self._drag_data['x'] = event.x
        self._drag_data['y'] = event.y

    def _on_drag(self, event):
        dx = event.x - self._drag_data['x']
        dy = event.y - self._drag_data['y']
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f'+{x}+{y}')
        self._drag_data['dragging'] = True

    def _on_release(self, event):
        if not self._drag_data.get('dragging'):
            self.close()
        self._drag_data['dragging'] = False

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
        print(f'[PIP] 窗口关闭', flush=True)
        try:
            self.root.after_cancel(self._topmost_timer)
        except Exception:
            pass
        if self._on_close:
            self._on_close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass


class ScreenMonitor:
    """屏幕像素监控核心类。

    在后台线程中周期性截取屏幕指定像素，与目标颜色比对；
    匹配时在主线程弹出画中画窗口并播放音频。
    """

    def __init__(self, config_path: str):
        self._config_path = config_path
        self._load_config()

        # 音频
        self._audio_available = False
        self._init_audio()

        # 状态
        self._running = False
        self._lock = threading.Lock()
        self._trigger_cooldowns: dict[int, float] = {}
        self._active_pips: list[PipWindow] = []
        self._region_baselines: dict[int, bytes] = {}

        # ---- tkinter ----
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.title('屏幕监控')
        self._root.protocol('WM_DELETE_WINDOW', self._on_quit)

        self._build_ui()
        self._update_log('应用已启动，请点击"开始监控"。')

    # ======================== 配置 ========================
    def _load_config(self):
        path = Path(self._config_path)
        if not path.exists():
            self._update_log(f'配置文件不存在: {self._config_path}，使用空配置。')
            self.config = {'check_rate': 10, 'cooldown': 3000, 'triggers': []}
            return
        with open(path, 'r', encoding='utf-8') as fh:
            self.config = json.load(fh)

    def _save_config(self):
        with open(self._config_path, 'w', encoding='utf-8') as fh:
            json.dump(self.config, fh, ensure_ascii=False, indent=4)

    # ======================== 音频 ========================
    def _init_audio(self):
        try:
            from pygame import mixer
            mixer.init()
            self._audio_available = True
        except Exception:
            self._update_log('音频初始化失败（将跳过音频播放）')

    def _play_audio(self, audio_path: str):
        if not self._audio_available:
            return
        if not os.path.exists(audio_path):
            self._update_log(f'音频文件不存在: {audio_path}')
            return
        try:
            from pygame import mixer
            mixer.music.load(audio_path)
            mixer.music.play()
        except Exception as exc:
            self._update_log(f'音频播放失败: {exc}')

    # ======================== UI ========================
    def _build_ui(self):
        win = tk.Toplevel(self._root)
        win.title('屏幕像素监控')
        win.geometry('380x280')
        win.resizable(False, False)
        win.protocol('WM_DELETE_WINDOW', self._on_quit)
        self._control_win = win

        # 标题
        tk.Label(win, text='屏幕像素监控', font=('Microsoft YaHei', 13, 'bold')).pack(pady=(12, 4))

        # 状态
        self._status_var = tk.StringVar(value='● 未启动')
        status_lbl = tk.Label(win, textvariable=self._status_var,
                              font=('Microsoft YaHei', 10), fg='gray')
        status_lbl.pack(pady=(0, 6))

        # 触发器信息
        info_frame = tk.Frame(win)
        info_frame.pack(pady=2)
        triggers = self.config.get('triggers', [])
        tk.Label(info_frame, text=f'监控目标: {len(triggers)} 个',
                 font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=8)
        tk.Label(info_frame, text=f'检测频率: {self.config["check_rate"]} 次/秒',
                 font=('Microsoft YaHei', 9)).pack(side=tk.LEFT, padx=8)

        # 按钮
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        self._start_btn = tk.Button(btn_frame, text='▶  开始监控', width=14,
                                     command=self.start, font=('Microsoft YaHei', 10))
        self._start_btn.pack(side=tk.LEFT, padx=6)
        self._stop_btn = tk.Button(btn_frame, text='■  停止监控', width=14,
                                    command=self.stop, state=tk.DISABLED,
                                    font=('Microsoft YaHei', 10))
        self._stop_btn.pack(side=tk.LEFT, padx=6)

        # 重置冷却
        tk.Button(win, text='重置冷却计时', command=self._reset_cooldowns,
                  font=('Microsoft YaHei', 9)).pack(pady=(2, 6))

        # 日志区域
        log_frame = tk.LabelFrame(win, text='运行日志', font=('Microsoft YaHei', 9))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        self._log_text = tk.Text(log_frame, height=6, state=tk.DISABLED,
                                  font=('Consolas', 9), wrap=tk.WORD)
        scroll = tk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scroll.set)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _update_log(self, msg: str):
        """线程安全地追加日志。"""
        timestamp = time.strftime('%H:%M:%S')
        line = f'[{timestamp}] {msg}\n'

        def _append():
            self._log_text.configure(state=tk.NORMAL)
            self._log_text.insert(tk.END, line)
            self._log_text.see(tk.END)
            self._log_text.configure(state=tk.DISABLED)

        try:
            self._root.after(0, _append)
        except Exception:
            pass  # 程序正在退出

    def _reset_cooldowns(self):
        self._trigger_cooldowns.clear()
        self._update_log('冷却计时已重置')

    # ======================== 生命周期 ========================
    def start(self):
        if self._running:
            return
        self._running = True
        self._start_btn.configure(state=tk.DISABLED)
        self._stop_btn.configure(state=tk.NORMAL)
        self._status_var.set('● 运行中')
        self._control_win.configure(bg='#e8f5e9')

        self._update_log('开始监控屏幕像素 ...')
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def stop(self):
        self._running = False
        self._start_btn.configure(state=tk.NORMAL)
        self._stop_btn.configure(state=tk.DISABLED)
        self._status_var.set('● 已停止')
        self._control_win.configure(bg='SystemButtonFace')

        # 关闭所有画中画
        for pip in self._active_pips:
            pip.close()
        self._active_pips.clear()

        self._update_log('监控已停止')

    def _on_quit(self):
        self.stop()
        self._root.destroy()

    def run(self):
        self._root.mainloop()

    # ======================== 监控循环（后台线程） ========================
    def _monitor_loop(self):
        triggers = self.config.get('triggers', [])
        check_interval = 1.0 / max(self.config.get('check_rate', 10), 1)
        cooldown_ms = self.config.get('cooldown', 3000)

        # 区域模式：清除旧基线
        self._region_baselines.clear()

        try:
            with mss.mss() as sct:
                while self._running:
                    for idx, trigger in enumerate(triggers):
                        if not self._running:
                            break
                        if self._is_cooldown(idx, cooldown_ms):
                            continue
                        ttype = trigger.get('type', 'pixel')
                        matched = (self._check_region(sct, idx, trigger)
                                   if ttype == 'region'
                                   else self._check_pixel(sct, idx, trigger))
                        if matched:
                            self._trigger_cooldowns[idx] = time.time() * 1000
                            self._root.after(0, lambda t=trigger: self._handle_trigger(t))
                    time.sleep(check_interval)
        except Exception as exc:
            self._root.after(0, lambda: self._update_log(f'监控异常: {exc}'))
            self._root.after(0, self.stop)

    def _is_cooldown(self, idx: int, cooldown_ms: int) -> bool:
        now = time.time() * 1000
        last = self._trigger_cooldowns.get(idx, 0)
        return (now - last) < cooldown_ms

    def _check_pixel(self, sct: mss.mss, idx: int, trigger: dict) -> bool:
        """截取屏幕指定位置 1x1 像素并与目标颜色比对。"""
        x, y = trigger['position']
        monitor = trigger.get('monitor', 1)
        target = tuple(trigger['target_color'])
        tolerance = trigger.get('tolerance', 0)

        region = {'left': x, 'top': y, 'width': 1, 'height': 1, 'mon': monitor}
        try:
            img = sct.grab(region)
            pixel = img.pixel(0, 0)
            matched = (all(abs(int(pixel[i]) - target[i]) <= tolerance for i in range(3))
                       if tolerance > 0 else pixel == target)
            if matched:
                print(f'[MONITOR] 像素匹配! 位置({x},{y}) 实际={pixel} 目标={target} 容差={tolerance}', flush=True)
            return matched
        except Exception as exc:
            self._root.after(0, lambda: self._update_log(f'截图失败 [{trigger.get("name", idx)}]: {exc}'))
            return False

    def _check_region(self, sct: mss.mss, idx: int, trigger: dict) -> bool:
        """截取屏幕指定区域，与基线比对，变化像素超过阈值则触发。"""
        r = trigger['region']
        monitor = trigger.get('monitor', 1)
        tolerance = trigger.get('tolerance', 30)
        threshold = trigger.get('change_threshold', 0.1)  # 变化比例阈值

        region = {'left': r['left'], 'top': r['top'],
                  'width': r['width'], 'height': r['height'], 'mon': monitor}
        try:
            current = sct.grab(region)
            current_bytes = current.rgb
        except Exception as exc:
            self._root.after(0, lambda: self._update_log(
                f'区域截图失败 [{trigger.get("name", idx)}]: {exc}'))
            return False

        baseline = self._region_baselines.get(idx)
        if baseline is None:
            self._region_baselines[idx] = current_bytes
            print(f'[MONITOR] 区域基线已捕获: {r["width"]}x{r["height"]} @ ({r["left"]},{r["top"]})', flush=True)
            return False

        # 间隔采样比对，避免逐像素遍历过慢（采样步长 step）
        step = max(1, min(r['width'], r['height']) // 20)
        total = r['width'] * r['height']
        diff_count = 0
        for y in range(0, r['height'], step):
            for x in range(0, r['width'], step):
                offset = (y * r['width'] + x) * 3
                dr = abs(current_bytes[offset] - baseline[offset])
                dg = abs(current_bytes[offset + 1] - baseline[offset + 1])
                db = abs(current_bytes[offset + 2] - baseline[offset + 2])
                if dr > tolerance or dg > tolerance or db > tolerance:
                    diff_count += 1

        ratio = diff_count / max(total // (step * step), 1)
        if ratio >= threshold:
            # 触发后更新基线，下次变化才能再次触发
            self._region_baselines[idx] = current_bytes
            print(f'[MONITOR] 区域变化: {ratio:.1%} (阈值 {threshold:.0%})', flush=True)
            return True
        return False

    # ======================== 触发处理（主线程） ========================
    def _handle_trigger(self, trigger: dict):
        name = trigger.get('name', '未命名')
        image = trigger.get('image_path', '')
        audio = trigger.get('audio_path', '')
        auto_close = trigger.get('display_duration', 1000)
        loc = trigger.get('position', trigger.get('region', '?'))
        print(f'[MONITOR] 触发: {name} @ {loc} | 图片={image} | 音频={audio} | 自动关闭={auto_close}ms', flush=True)
        self._update_log(f'触发: {name}  @ {loc}')

        # 播放音频
        audio = trigger.get('audio_path', '')
        if audio:
            self._play_audio(audio)

        # 弹出画中画前，先关闭已有的旧窗口
        for old in self._active_pips:
            old.close()
        self._active_pips.clear()

        image = trigger.get('image_path', '')
        if image:
            pip_cfg = trigger.get('pip', {})
            pip = PipWindow(
                image_path=image,
                position=tuple(pip_cfg.get('position', [100, 100])),
                size=tuple(pip_cfg.get('size', [600, 400])),
                auto_close=trigger.get('display_duration', 1000),
                fullscreen=True,
                alpha=pip_cfg.get('alpha', 0.7),
            )
            pip._on_close = lambda p=pip: self._active_pips.remove(p) if p in self._active_pips else None
            self._active_pips.append(pip)


# ======================== 入口 ========================
if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    config_file = args[0] if args else 'config.json'
    auto_start = '--auto' in flags

    app = ScreenMonitor(config_file)
    if auto_start:
        app.start()
    app.run()

# -*- coding: utf-8 -*-
"""
CSGO 击杀监控 — Material Design 3 版
通过 Game State Integration (GSI) 实时获取击杀记录。
每检测到一次击杀 → 弹出图片 + 播放音频 + 后台记录日志。

原作者: libi2009  (https://github.com/libi2009)
现作者: Minecraftmc22 (https://github.com/minecraftmc22)
License: MIT
"""

import ctypes
import json
import os
import random
import re
import subprocess
import threading
import time
import tkinter as tk
try:
    import winreg
except ImportError:
    winreg = None
from tkinter import filedialog, messagebox
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import sounddevice as sd
import soundfile as sf
from PIL import Image, ImageTk

# ======================== 常量 ========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPDATA = os.environ.get('APPDATA', os.path.expanduser('~'))
DEFAULT_CONFIG_DIR = os.path.join(APPDATA, 'Minecraftmc22', 'csgo_kill_monitor')
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_CONFIG_DIR, 'Config.json')
OLD_CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
DEFAULT_IMAGE_DIR = os.path.join(BASE_DIR, 'images')
DEFAULT_AUDIO_DIR = os.path.join(BASE_DIR, 'audio')
AUDIO_TEMP_DIR = os.path.join(BASE_DIR, 'AudioTemp')
DEFAULT_LOG_PATH = os.path.join(BASE_DIR, 'kill_log.txt')
GSI_CFG_FILENAME = 'gamestate_integration_kill_monitor.cfg'
GSI_CFG_SOURCE = os.path.join(BASE_DIR, GSI_CFG_FILENAME)
DEFAULT_CS2_LAUNCH_ARGS = '+exec gamestate_integration_kill_monitor.cfg'
CS2_APP_ID = 730

# Windows API
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
AUDIO_EXTS = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.wma', '.aac'}


# ======================== MD3 主题 ========================
class MD3:
    """Material Design 3 — Dark Theme 色彩与字体"""
    # Primary
    PRIMARY = '#D0BCFF'
    ON_PRIMARY = '#381E72'
    PRIMARY_CONTAINER = '#4F378B'
    ON_PRIMARY_CONTAINER = '#EADDFF'
    # Secondary
    SECONDARY = '#CCC2DC'
    ON_SECONDARY = '#332D41'
    SECONDARY_CONTAINER = '#4A4458'
    ON_SECONDARY_CONTAINER = '#E8DEF8'
    # Tertiary
    TERTIARY = '#EFB8C8'
    TERTIARY_CONTAINER = '#633B48'
    ON_TERTIARY_CONTAINER = '#FFD8E4'
    # Error
    ERROR = '#F2B8B5'
    ERROR_CONTAINER = '#8C1D18'
    # Surface
    BACKGROUND = '#141218'
    SURFACE = '#1D1B20'
    SURFACE_LOW = '#211F26'
    SURFACE_CONTAINER = '#2B2930'
    SURFACE_HIGH = '#36343B'
    SURFACE_VARIANT = '#49454F'
    ON_BACKGROUND = '#E6E0E9'
    ON_SURFACE = '#E6E0E9'
    ON_SURFACE_VARIANT = '#CAC4D0'
    OUTLINE = '#938F99'
    OUTLINE_VARIANT = '#49454F'
    # Semantic
    SUCCESS = '#A5D6A7'
    WARNING = '#FFCC80'
    INFO = '#90CAF9'
    # Fonts
    F_DISPLAY = ('Microsoft YaHei UI', 22, 'bold')
    F_HEADLINE = ('Microsoft YaHei UI', 18, 'bold')
    F_TITLE = ('Microsoft YaHei UI', 14, 'bold')
    F_BODY = ('Microsoft YaHei UI', 10)
    F_BODY_B = ('Microsoft YaHei UI', 10, 'bold')
    F_LABEL = ('Microsoft YaHei UI', 9)
    F_LABEL_B = ('Microsoft YaHei UI', 9, 'bold')
    F_SMALL = ('Microsoft YaHei UI', 8)
    F_MONO = ('Consolas', 16, 'bold')
    F_MONO_S = ('Consolas', 11)


# ======================== 辅助函数 ========================
def _round_rect(canvas, x1, y1, x2, y2, r=10, **kw):
    """在 Canvas 上绘制圆角矩形"""
    pts = [
        x1 + r, y1, x2 - r, y1,
        x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r,
        x1, y1 + r, x1, y1,
        x1 + r, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _browse_folder(initial=None):
    """打开文件夹选择对话框"""
    return filedialog.askdirectory(initialdir=initial or BASE_DIR)


def _browse_file(initial=None, filetypes=None):
    """打开文件选择对话框"""
    return filedialog.askopenfilename(
        initialdir=initial or BASE_DIR,
        filetypes=filetypes or [('所有文件', '*.*')]
    )


# ======================== MD3 自定义组件 ========================
class MD3Button(tk.Canvas):
    """MD3 填充按钮 — 圆角、悬浮效果"""

    def __init__(self, parent, text, command=None, width=140, height=36,
                 bg_color=None, fg_color=None, font=None, **kw):
        bg = bg_color or MD3.PRIMARY
        fg = fg_color or MD3.ON_PRIMARY
        f = font or MD3.F_BODY_B
        super().__init__(parent, width=width, height=height,
                         bg=parent.cget('bg'), highlightthickness=0, bd=0, **kw)
        self._text = text
        self._command = command
        self._bg = bg
        self._fg = fg
        self._font = f
        self._cw = width
        self._h = height
        self._hover = False
        self._draw()
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<Button-1>', self._on_click)

    def _draw(self):
        self.delete('all')
        bg = self._bg
        if self._hover:
            # 悬浮时稍微变亮
            bg = self._lighten(self._bg, 0.12)
        _round_rect(self, 0, 0, self._cw, self._h, r=self._h // 2,
                    fill=bg, outline='')
        self.create_text(self._cw // 2, self._h // 2, text=self._text,
                         font=self._font, fill=self._fg)

    @staticmethod
    def _lighten(hex_color, amount):
        """使颜色变亮"""
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        r = min(255, int(r + (255 - r) * amount))
        g = min(255, int(g + (255 - g) * amount))
        b = min(255, int(b + (255 - b) * amount))
        return f'#{r:02x}{g:02x}{b:02x}'

    def _on_enter(self, e):
        self._hover = True
        self._draw()

    def _on_leave(self, e):
        self._hover = False
        self._draw()

    def _on_click(self, e):
        if self._command:
            self._command()

    def set_state(self, state):
        """设置按钮状态 (normal/disabled)"""
        if state == tk.DISABLED:
            self._bg = MD3.OUTLINE_VARIANT
            self._fg = MD3.OUTLINE
        else:
            self._bg = MD3.PRIMARY
            self._fg = MD3.ON_PRIMARY
        self._draw()


class MD3OutlinedButton(MD3Button):
    """MD3 轮廓按钮"""

    def __init__(self, parent, text, command=None, width=140, height=36, **kw):
        super().__init__(parent, text, command, width, height,
                         bg_color=MD3.SURFACE_CONTAINER, fg_color=MD3.PRIMARY, **kw)

    def _draw(self):
        self.delete('all')
        bg = MD3.SURFACE_CONTAINER
        if self._hover:
            bg = MD3.SURFACE_HIGH
        _round_rect(self, 0, 0, self._cw, self._h, r=self._h // 2,
                    fill=bg, outline=MD3.OUTLINE, width=1)
        self.create_text(self._cw // 2, self._h // 2, text=self._text,
                         font=self._font, fill=MD3.PRIMARY)


class MD3TextButton(MD3Button):
    """MD3 文本按钮"""

    def __init__(self, parent, text, command=None, width=100, height=32, **kw):
        super().__init__(parent, text, command, width, height,
                         bg_color=MD3.SURFACE, fg_color=MD3.PRIMARY, **kw)

    def _draw(self):
        self.delete('all')
        bg = MD3.SURFACE
        if self._hover:
            # 文本按钮悬浮时显示淡色背景
            _round_rect(self, 0, 0, self._cw, self._h, r=self._h // 2,
                        fill=MD3.SURFACE_CONTAINER, outline='')
        else:
            _round_rect(self, 0, 0, self._cw, self._h, r=self._h // 2,
                        fill=bg, outline='')
        self.create_text(self._cw // 2, self._h // 2, text=self._text,
                         font=self._font, fill=MD3.PRIMARY)


class MD3Switch(tk.Canvas):
    """MD3 开关组件"""

    def __init__(self, parent, variable, command=None, width=52, height=32, **kw):
        super().__init__(parent, width=width, height=height,
                         bg=parent.cget('bg'), highlightthickness=0, bd=0, **kw)
        self._var = variable
        self._command = command
        self._cw = width
        self._h = height
        self._r = height // 2
        self._draw()
        self.bind('<Button-1>', self._on_click)
        self._var.trace_add('write', lambda *_: self._draw())

    def _draw(self):
        self.delete('all')
        val = self._var.get()
        if val:
            track = MD3.PRIMARY
            knob = MD3.ON_PRIMARY
            kx = self._cw - self._r - 4
            kr = self._r - 6
        else:
            track = MD3.SURFACE_VARIANT
            knob = MD3.OUTLINE
            kx = self._r + 4
            kr = self._r - 6
        _round_rect(self, 2, 4, self._cw - 2, self._h - 4, r=self._r - 4,
                    fill=track, outline=MD3.OUTLINE if not val else '')
        self.create_oval(kx - kr, self._h // 2 - kr, kx + kr, self._h // 2 + kr,
                         fill=knob, outline='')

    def _on_click(self, e):
        self._var.set(not self._var.get())
        if self._command:
            self._command()


class MD3Card(tk.Frame):
    """MD3 卡片容器"""

    def __init__(self, parent, title=None, **kw):
        super().__init__(parent, bg=MD3.SURFACE_CONTAINER, **kw)
        self._pad = 16
        if title:
            header = tk.Label(self, text=title, font=MD3.F_TITLE,
                              bg=MD3.SURFACE_CONTAINER, fg=MD3.PRIMARY)
            header.pack(anchor='w', padx=self._pad, pady=(self._pad, 8))
        self._body = tk.Frame(self, bg=MD3.SURFACE_CONTAINER)
        self._body.pack(fill=tk.BOTH, expand=True, padx=self._pad, pady=(0, self._pad))

    @property
    def body(self):
        return self._body


class MD3TabBar(tk.Frame):
    """MD3 标签栏"""

    def __init__(self, parent, tabs, on_select, **kw):
        """tabs: [(id, label), ...]"""
        super().__init__(parent, bg=MD3.SURFACE, **kw)
        self._tabs = tabs
        self._on_select = on_select
        self._current = 0
        self._labels = {}
        for i, (tid, label) in enumerate(tabs):
            c = tk.Canvas(self, width=120, height=44, bg=MD3.SURFACE,
                          highlightthickness=0)
            c.pack(side=tk.LEFT, padx=2)
            c.bind('<Button-1>', lambda e, idx=i: self.select(idx))
            self._labels[i] = (c, label)
        # Canvas 初次创建时不会自动绘制文字，主动完成首次渲染。
        self._redraw()

    def select(self, idx):
        self._current = idx
        self._redraw()
        if self._on_select:
            self._on_select(self._tabs[idx][0])

    def _redraw(self):
        for i, (c, label) in self._labels.items():
            c.delete('all')
            if i == self._current:
                c.create_text(60, 18, text=label, font=MD3.F_LABEL_B,
                              fill=MD3.PRIMARY)
                c.create_rectangle(30, 34, 90, 37, fill=MD3.PRIMARY, outline='')
            else:
                c.create_text(60, 18, text=label, font=MD3.F_LABEL,
                              fill=MD3.ON_SURFACE_VARIANT)


class MD3SegmentedButton(tk.Frame):
    """MD3 分段按钮 (单选)"""

    def __init__(self, parent, options, variable, command=None, **kw):
        """options: [(value, label), ...]"""
        super().__init__(parent, bg=MD3.SURFACE_LOW, **kw)
        self._opts = options
        self._var = variable
        self._command = command
        self._labels = []
        for val, label in options:
            lbl = tk.Label(self, text=label, font=MD3.F_LABEL,
                          padx=16, pady=6, bg=MD3.SURFACE_LOW,
                          fg=MD3.ON_SURFACE_VARIANT, cursor='hand2')
            lbl.pack(side=tk.LEFT)
            lbl.bind('<Button-1>', lambda e, v=val: self._on_click(v))
            self._labels.append((val, lbl))
        self._update()
        self._var.trace_add('write', lambda *_: self._update())

    def _on_click(self, value):
        """点击选项时的处理"""
        self._var.set(value)
        if self._command:
            self._command()

    def _update(self):
        cur = self._var.get()
        for val, lbl in self._labels:
            if val == cur:
                lbl.config(bg=MD3.SECONDARY_CONTAINER,
                           fg=MD3.ON_SECONDARY_CONTAINER)
            else:
                lbl.config(bg=MD3.SURFACE_LOW,
                           fg=MD3.ON_SURFACE_VARIANT)


class MD3Slider(tk.Frame):
    """MD3 滑块 (带标签和数值显示)"""

    def __init__(self, parent, label, variable, frm=0, to=100, unit='%',
                 command=None, **kw):
        super().__init__(parent, bg=parent.cget('bg'), **kw)
        self._var = variable
        self._unit = unit
        self._command = command

        row = tk.Frame(self, bg=self.cget('bg'))
        row.pack(fill=tk.X)

        tk.Label(row, text=label, font=MD3.F_BODY, bg=self.cget('bg'),
                 fg=MD3.ON_SURFACE).pack(side=tk.LEFT)

        self._val_label = tk.Label(row, text='', font=MD3.F_BODY_B,
                                   bg=self.cget('bg'), fg=MD3.PRIMARY)
        self._val_label.pack(side=tk.RIGHT)

        self._scale = tk.Scale(self, from_=frm, to=to, orient=tk.HORIZONTAL,
                               variable=variable, bg=self.cget('bg'),
                               fg=MD3.ON_SURFACE, troughcolor=MD3.SURFACE_VARIANT,
                               highlightthickness=0, bd=0, sliderrelief=tk.FLAT,
                               font=MD3.F_SMALL, length=280,
                               activebackground=MD3.PRIMARY)
        self._scale.pack(fill=tk.X, pady=(0, 4))
        self._update_label()
        variable.trace_add('write', lambda *_: self._update_label())

    def _update_label(self):
        self._val_label.config(text=f'{int(self._var.get())}{self._unit}')
        if self._command:
            self._command()


class MD3ScrollableFrame(tk.Frame):
    """可滚动 Frame"""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=MD3.BACKGROUND, **kw)
        self._canvas = tk.Canvas(self, bg=MD3.BACKGROUND, highlightthickness=0)
        self._scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL,
                                       command=self._canvas.yview)
        self._inner = tk.Frame(self._canvas, bg=MD3.BACKGROUND)

        self._inner.bind('<Configure>',
                         lambda e: self._canvas.configure(scrollregion=self._canvas.bbox('all')))
        self._cwin_id = self._canvas.create_window(0, 0, anchor='nw', window=self._inner)

        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._canvas.bind('<Configure>', self._on_resize)
        self._canvas.bind('<MouseWheel>', self._on_wheel)
        self.bind_all('<MouseWheel>', self._on_wheel)

    def _on_resize(self, e):
        self._canvas.itemconfig(self._cwin_id, width=e.width)

    def _on_wheel(self, e):
        """仅滚动鼠标所在的有效滚动区域。

        bind_all 会在弹窗关闭后保留旧回调；因此必须先确认画布仍存在，
        同时避免一个滚轮动作带动所有打开的滚动区域。
        """
        try:
            if not self._canvas.winfo_exists():
                return
            widget = self.winfo_containing(e.x_root, e.y_root)
            while widget is not None:
                if widget == self._canvas:
                    step = int(-1 * (e.delta / 120))
                    if step:
                        self._canvas.yview_scroll(step, 'units')
                    return
                widget = widget.master
        except tk.TclError:
            # 弹窗销毁与滚轮事件恰好重叠时，忽略这一次已失效的回调。
            return

    @property
    def inner(self):
        return self._inner


# ======================== PipWindow ========================
class PipWindow:
    """无边框半透明图片窗口，支持强制置顶、鼠标穿透"""

    def __init__(self, image_path, position, size, auto_close=0,
                 fullscreen=False, alpha=0.9, click_through=False, effect='shake'):
        self.root = tk.Toplevel()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', 1)
        self.root.attributes('-alpha', alpha)
        self._click_through = click_through

        if fullscreen:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            size = (sw, sh)
            position = (0, 0)

        self.root.configure(bg='black')
        self._position = position
        self._size = size
        self._alpha = alpha
        self._duration = auto_close
        self._effect_timers = []
        self.root.geometry(f'{size[0]}x{size[1]}+{position[0]}+{position[1]}')
        self.root.update()
        self._force_topmost()
        self.root.after(50, self._force_topmost)
        self.root.after(200, self._force_topmost)
        self._topmost_timer = self.root.after(500, self._keep_topmost)

        # 鼠标穿透 (仅全屏时启用)
        if click_through and fullscreen:
            self._set_click_through()

        inner = tk.Frame(self.root, bg='black')
        inner.pack(fill=tk.BOTH, expand=True)

        try:
            img = Image.open(image_path)
            img = img.resize(size, Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            tk.Label(inner, image=self._photo, bg='black').pack(fill=tk.BOTH, expand=True)
        except Exception as exc:
            print(f'[PIP] 图片加载失败: {exc}', flush=True)

        # 非穿透时点击关闭
        if not (click_through and fullscreen):
            self.root.bind('<Button-1>', lambda e: self.close())
        if auto_close > 0:
            self.root.after(auto_close, self.close)
        self._start_effect(effect)

    def _schedule_effect(self, delay, callback):
        """安排效果动画，并在窗口关闭时统一取消。"""
        timer = self.root.after(delay, callback)
        self._effect_timers.append(timer)

    def _start_effect(self, effect):
        """播放一次图片出现效果。"""
        duration = max(self._duration, 700)
        if effect == 'shake':
            # 前 420ms 在原位置附近轻微抖动，最后回到原位。
            offsets = [(0, 0), (-12, 5), (11, -7), (-8, -5), (8, 6), (-4, 3), (0, 0)]
            for i, (dx, dy) in enumerate(offsets):
                self._schedule_effect(i * 65, lambda x=dx, y=dy: self._move_to(x, y))
        elif effect == 'fade':
            # 渐显后，在关闭前预留一小段渐出时间。
            self.root.attributes('-alpha', 0.0)
            steps = 10
            for i in range(1, steps + 1):
                self._schedule_effect(i * 35, lambda n=i: self._set_alpha(self._alpha * n / steps))
            fade_out_start = max(500, duration - 360)
            for i in range(steps):
                self._schedule_effect(fade_out_start + i * 35,
                                      lambda n=i: self._set_alpha(self._alpha * (steps - n - 1) / steps))
        elif effect == 'flash':
            # 快速闪动三次，结束时恢复设定透明度。
            for i in range(6):
                value = self._alpha if i % 2 == 0 else max(0.15, self._alpha * 0.25)
                self._schedule_effect(i * 90, lambda a=value: self._set_alpha(a))
            self._schedule_effect(540, lambda: self._set_alpha(self._alpha))

    def _move_to(self, dx, dy):
        if self.root.winfo_exists():
            x, y = self._position
            w, h = self._size
            self.root.geometry(f'{w}x{h}+{x + dx}+{y + dy}')

    def _set_alpha(self, alpha):
        if self.root.winfo_exists():
            self.root.attributes('-alpha', max(0.0, min(1.0, alpha)))

    def _set_click_through(self):
        """设置窗口鼠标穿透"""
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT | WS_EX_LAYERED)
            print('[PIP] 鼠标穿透已启用', flush=True)
        except Exception as exc:
            print(f'[PIP] 鼠标穿透失败: {exc}', flush=True)

    def _force_topmost(self):
        try:
            hwnd = self.root.frame()
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        except Exception:
            pass

    def _keep_topmost(self):
        if self.root.winfo_exists():
            self._force_topmost()
            self._topmost_timer = self.root.after(500, self._keep_topmost)

    def close(self):
        for timer in self._effect_timers:
            try:
                self.root.after_cancel(timer)
            except Exception:
                pass
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
    """接收 CSGO Game State Integration 的 HTTP POST 数据"""
    monitor = None

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        try:
            data = json.loads(body)
            if self.monitor:
                self.monitor._root.after(0, lambda d=data: self.monitor._process_gsi(d))
        except json.JSONDecodeError:
            pass
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


# ======================== 主监控类 ========================
class KillMonitor:

    def __init__(self):
        self._root = tk.Tk()
        self._root.withdraw()
        self._config = self._load_config()
        self._ensure_dirs()
        self._kill_count = -1
        self._speed = 1.0
        self._player_dead = False
        self._last_kill_time = 0.0

        # UI 变量
        self._show_image = tk.BooleanVar(value=True)
        self._play_sound = tk.BooleanVar(value=True)
        self._share_audio = tk.BooleanVar(value=False)
        self._share_device_id = None
        self._share_devices = []
        self._server = None
        self._active_pip = None

        # 图片/音频库索引
        self._image_files = []
        self._image_idx = 0
        self._audio_files = []
        self._audio_idx = 0
        self._scan_libraries()

        # 设置变量
        self._s_image_path = tk.StringVar(value=self._cfg('image', 'library_path', 'images'))
        self._s_image_order = tk.StringVar(value=self._cfg('image', 'playback_order', 'loop'))
        self._s_repeat_image = tk.StringVar(value=self._cfg('image', 'repeat_image', ''))
        self._s_image_alpha = tk.IntVar(value=int(self._cfg('image', 'alpha', 0.9) * 100))
        self._s_click_through = tk.BooleanVar(value=self._cfg('pip', 'click_through', True))
        self._s_audio_path = tk.StringVar(value=self._cfg('audio', 'library_path', 'audio'))
        self._s_audio_order = tk.StringVar(value=self._cfg('audio', 'playback_order', 'loop'))
        self._s_audio_vol = tk.IntVar(value=self._cfg('audio', 'global_volume', 100))
        self._s_effect_mode = tk.StringVar(value=self._cfg('effect', 'mode', 'random'))
        self._s_effect_name = tk.StringVar(value=self._cfg('effect', 'selected_effect', 'shake'))
        self._s_log_path = tk.StringVar(value=self._cfg('log_path', 'kill_log.txt'))
        self._s_config_path = tk.StringVar(value=self._cfg('config_path', ''))
        self._s_cs2_path = tk.StringVar(value=self._cfg('cs2_path', ''))
        self._s_cs2_launch_args = tk.StringVar(
            value=self._cfg('cs2_launch_args', DEFAULT_CS2_LAUNCH_ARGS))

        self._build_ui()
        self._scan_audio_devices()
        self._rebuild_device_menu()
        self._log('CSGO 击杀监控已就绪，等待 GSI 数据 ...')

    # ======================== 配置 ========================
    def _default_config(self):
        return {
            'port': 3000,
            'display_duration': 1000,
            'pip': {
                'fullscreen': True,
                'alpha': 0.9,
                'click_through': True,
            },
            'image': {
                'library_path': 'images',
                'playback_order': 'loop',
                'repeat_image': '',
                'alpha': 0.9,
            },
            'audio': {
                'library_path': 'audio',
                'playback_order': 'loop',
                'global_volume': 100,
                'per_audio_volume': {},
                'image_audio_map': {},
            },
            'effect': {
                'mode': 'random',
                'selected_effect': 'shake',
                'image_effect_map': {},
            },
            'log_path': 'kill_log.txt',
            'config_path': '',
            'cs2_path': '',
            'cs2_launch_args': DEFAULT_CS2_LAUNCH_ARGS,
        }

    def _cfg(self, *keys):
        """便捷取嵌套配置值: self._cfg('image', 'library_path', 'images')
        最后一个参数是默认值，前面的参数是嵌套键。
        """
        if not keys:
            return None
        *path, default = keys
        v = self._config
        for k in path:
            if isinstance(v, dict):
                v = v.get(k)
            else:
                return default
        return v if v is not None else default

    def _get_config_file_path(self):
        """获取实际配置文件路径"""
        cp = ''
        if hasattr(self, '_config') and isinstance(self._config, dict):
            cp = self._config.get('config_path', '')
        if cp:
            cp = os.path.expandvars(cp)
            return cp
        return DEFAULT_CONFIG_PATH

    def _load_config(self):
        """加载配置，自动从旧格式迁移"""
        path = DEFAULT_CONFIG_PATH

        # 1. 尝试默认路径
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                if 'image' in cfg or 'audio' in cfg:
                    return self._merge_defaults(cfg)
            except Exception:
                pass

        # 2. 尝试旧 config.json
        if os.path.exists(OLD_CONFIG_PATH):
            try:
                with open(OLD_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    old = json.load(f)
                return self._migrate_old_config(old)
            except Exception:
                pass

        # 3. 使用默认配置
        return self._default_config()

    def _merge_defaults(self, cfg):
        """合并用户配置与默认配置 (补全缺失字段)"""
        d = self._default_config()
        for k, v in d.items():
            if k not in cfg:
                cfg[k] = v
            elif isinstance(v, dict) and isinstance(cfg.get(k), dict):
                for dk, dv in v.items():
                    if dk not in cfg[k]:
                        cfg[k][dk] = dv
        return cfg

    def _migrate_old_config(self, old):
        """从旧格式迁移"""
        cfg = self._default_config()
        cfg['port'] = old.get('port', 3000)
        cfg['display_duration'] = old.get('display_duration', 1000)
        old_pip = old.get('pip', {})
        cfg['pip']['fullscreen'] = old_pip.get('fullscreen', True)
        cfg['pip']['alpha'] = old_pip.get('alpha', 0.9)
        cfg['image']['alpha'] = old_pip.get('alpha', 0.9)
        # 旧的单文件路径 → 保留为兼容字段
        if 'image_path' in old:
            cfg['_legacy_image_path'] = old['image_path']
        if 'audio_path' in old:
            cfg['_legacy_audio_path'] = old['audio_path']
        return cfg

    def _save_config(self):
        """保存配置"""
        # 同步 UI 变量到 config
        self._config.setdefault('image', {})['library_path'] = self._s_image_path.get()
        self._config['image']['playback_order'] = self._s_image_order.get()
        self._config['image']['repeat_image'] = self._s_repeat_image.get()
        self._config['image']['alpha'] = self._s_image_alpha.get() / 100.0
        self._config.setdefault('pip', {})['alpha'] = self._s_image_alpha.get() / 100.0
        self._config['pip']['click_through'] = self._s_click_through.get()
        self._config.setdefault('audio', {})['library_path'] = self._s_audio_path.get()
        self._config['audio']['playback_order'] = self._s_audio_order.get()
        self._config['audio']['global_volume'] = self._s_audio_vol.get()
        self._config.setdefault('effect', {})['mode'] = self._s_effect_mode.get()
        self._config['effect']['selected_effect'] = self._s_effect_name.get()
        self._config['log_path'] = self._s_log_path.get()
        self._config['config_path'] = self._s_config_path.get()
        self._config['cs2_path'] = self._s_cs2_path.get()
        self._config['cs2_launch_args'] = self._s_cs2_launch_args.get()

        path = self._get_config_file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except Exception as exc:
            print(f'[CONFIG] 保存失败: {exc}', flush=True)

    def _ensure_dirs(self):
        """确保默认目录存在"""
        for d in [DEFAULT_IMAGE_DIR, DEFAULT_AUDIO_DIR, AUDIO_TEMP_DIR, DEFAULT_CONFIG_DIR]:
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass

    # ======================== 图片/音频库扫描 ========================
    def _resolve_path(self, p):
        """解析相对/绝对路径"""
        if not p:
            return ''
        if os.path.isabs(p):
            return p
        return os.path.join(BASE_DIR, p)

    def _scan_libraries(self):
        """扫描图片库和音频库"""
        img_dir = self._resolve_path(self._cfg('image', 'library_path', 'images'))
        self._image_files = sorted(
            [f for f in os.listdir(img_dir)
             if os.path.splitext(f)[1].lower() in IMAGE_EXTS]
        ) if os.path.isdir(img_dir) else []

        aud_dir = self._resolve_path(self._cfg('audio', 'library_path', 'audio'))
        self._audio_files = sorted(
            [f for f in os.listdir(aud_dir)
             if os.path.splitext(f)[1].lower() in AUDIO_EXTS]
        ) if os.path.isdir(aud_dir) else []

        # 兼容旧的单文件路径
        if not self._image_files and '_legacy_image_path' in self._config:
            lp = self._config['_legacy_image_path']
            full = self._resolve_path(lp)
            if os.path.isfile(full):
                self._image_files = [os.path.basename(full)]
                if not os.path.isabs(lp):
                    self._image_files = [lp]

        if not self._audio_files and '_legacy_audio_path' in self._config:
            lp = self._config['_legacy_audio_path']
            full = self._resolve_path(lp)
            if os.path.isfile(full):
                self._audio_files = [os.path.basename(full)]
                if not os.path.isabs(lp):
                    self._audio_files = [lp]

        print(f'[LIB] 图片: {len(self._image_files)} 个, 音频: {len(self._audio_files)} 个', flush=True)

    def _pick_image(self):
        """根据播放顺序选择下一张图片"""
        if not self._image_files:
            return None
        order = self._s_image_order.get()
        if order == 'random':
            return random.choice(self._image_files)
        elif order == 'repeat':
            picked = self._s_repeat_image.get()
            if picked and picked in self._image_files:
                return picked
            # 未选择或文件不存在时回退到第一张
            return self._image_files[0]
        else:  # loop
            img = self._image_files[self._image_idx % len(self._image_files)]
            self._image_idx += 1
            return img

    def _pick_audio(self, image_name=None):
        """根据播放顺序选择下一个音频; image_name 有映射时直接用映射"""
        # 检查图片-音频映射
        if image_name:
            mapping = self._cfg('audio', 'image_audio_map', {})
            if isinstance(mapping, dict) and image_name in mapping:
                mapped = mapping[image_name]
                # 验证文件存在
                aud_dir = self._resolve_path(self._s_audio_path.get())
                if os.path.isabs(mapped):
                    if os.path.isfile(mapped):
                        return mapped
                elif os.path.isfile(os.path.join(aud_dir, mapped)):
                    return mapped

        if not self._audio_files:
            return None
        order = self._s_audio_order.get()
        if order == 'random':
            return random.choice(self._audio_files)
        elif order == 'repeat':
            return self._audio_files[0]
        else:  # loop
            aud = self._audio_files[self._audio_idx % len(self._audio_files)]
            self._audio_idx += 1
            return aud

    def _resolve_audio_full(self, name):
        """获取音频文件的完整路径"""
        if os.path.isabs(name):
            return name
        return os.path.join(self._resolve_path(self._s_audio_path.get()), name)

    def _resolve_image_full(self, name):
        """获取图片文件的完整路径"""
        if os.path.isabs(name):
            return name
        return os.path.join(self._resolve_path(self._s_image_path.get()), name)

    def _pick_effect(self, image_name=None):
        """获取本次展示效果；图片专属绑定始终优先于全局配置。"""
        mapping = self._cfg('effect', 'image_effect_map', {})
        if image_name and isinstance(mapping, dict):
            bound_effect = mapping.get(os.path.basename(image_name))
            if bound_effect in ('shake', 'fade', 'flash'):
                return bound_effect
        if self._s_effect_mode.get() == 'random':
            return random.choice(('shake', 'fade', 'flash'))
        selected = self._s_effect_name.get()
        return selected if selected in ('shake', 'fade', 'flash') else 'shake'

    # ======================== 音频 ========================
    def _ensure_wav(self, audio_name):
        """确保音频文件为 WAV，返回完整 WAV 路径"""
        full = self._resolve_audio_full(audio_name) if not os.path.isabs(audio_name) else audio_name
        if not os.path.exists(full):
            print(f'[AUDIO] 文件不存在: {full}', flush=True)
            return full
        if full.lower().endswith('.wav'):
            return full
        # 非 WAV 文件转换后的中间文件统一存入项目的 AudioTemp 目录。
        wav_path = os.path.join(AUDIO_TEMP_DIR, f'_converted_{os.path.splitext(os.path.basename(full))[0]}.wav')
        if os.path.exists(wav_path):
            return wav_path
        print(f'[AUDIO] 转换: {os.path.basename(full)} -> WAV ...', flush=True)
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, '-y', '-i', full, '-acodec', 'pcm_s16le', wav_path],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return wav_path if os.path.exists(wav_path) else full

    def _play_audio(self, image_name=None):
        """播放音频 (支持变速、音量控制、图片-音频映射)"""
        audio_name = self._pick_audio(image_name)
        if not audio_name:
            print('[AUDIO] 音频库为空', flush=True)
            return

        speed = self._speed
        threading.Thread(target=self._play_speed_thread,
                          args=(audio_name, speed), daemon=True).start()

    def _play_speed_thread(self, audio_name, speed):
        """后台线程: 变速+音量控制播放"""
        wav_path = self._ensure_wav(audio_name)
        if not os.path.exists(wav_path):
            print(f'[AUDIO] WAV 不存在: {wav_path}', flush=True)
            return

        # 变速缓存
        if speed != 1.0:
            cache_name = f'_speed_{speed:.1f}x_{os.path.basename(wav_path)}'
            # 变速变调后的缓存不再散落在项目根目录。
            cache_path = os.path.join(AUDIO_TEMP_DIR, cache_name)
            if not os.path.exists(cache_path):
                filter_str = f'rubberband=tempo={speed:.1f}:pitch={speed:.1f}'
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
                subprocess.run(
                    [ffmpeg, '-y', '-i', wav_path, '-filter:a', filter_str,
                     '-acodec', 'pcm_s16le', cache_path],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if not os.path.exists(cache_path):
                    filter_str = f'atempo={speed:.1f},asetrate=44100*{speed:.1f}'
                    subprocess.run(
                        [ffmpeg, '-y', '-i', wav_path, '-filter:a', filter_str,
                         '-acodec', 'pcm_s16le', cache_path],
                        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                    )
            play_path = cache_path if os.path.exists(cache_path) else wav_path
        else:
            play_path = wav_path

        # 计算最终音量
        global_vol = self._s_audio_vol.get() / 100.0
        per_vol_map = self._cfg('audio', 'per_audio_volume', {})
        if isinstance(per_vol_map, dict):
            base_name = os.path.basename(audio_name)
            per_vol = per_vol_map.get(base_name, 100) / 100.0
        else:
            per_vol = 1.0
        final_vol = global_vol * per_vol

        try:
            if self._share_audio.get() and self._share_device_id is not None:
                self._play_to_devices(play_path, final_vol)
            else:
                self._play_with_volume(play_path, final_vol)
            print(f'[AUDIO] 播放: {os.path.basename(audio_name)} @ {speed:.1f}x '
                  f'音量:{int(final_vol * 100)}%', flush=True)
        except Exception as exc:
            print(f'[AUDIO] 失败: {exc}', flush=True)

    def _play_with_volume(self, wav_path, volume):
        """用 sounddevice 播放 WAV，带音量控制"""
        data, sr = sf.read(wav_path, dtype='float32')
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        data = data * volume
        default_out = sd.default.device[1]
        sd.play(data, samplerate=sr, device=default_out, blocking=False)

    def _play_to_devices(self, wav_path, volume):
        """双路输出: 默认扬声器 + 分享设备"""
        if self._share_device_id is None:
            self._play_with_volume(wav_path, volume)
            return
        data, sr = sf.read(wav_path, dtype='float32')
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        data = data * volume
        default_out = sd.default.device[1]
        sd.play(data, samplerate=sr, device=default_out, blocking=False)
        time.sleep(0.03)
        sd.play(data, samplerate=sr, device=self._share_device_id, blocking=False)
        print(f'[AUDIO] 双路输出: 扬声器 + 设备#{self._share_device_id}', flush=True)

    def _scan_audio_devices(self):
        """扫描输出设备"""
        self._share_devices = []
        try:
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                name = d['name']
                if d['max_output_channels'] > 0:
                    tag = ''
                    if any(kw in name.lower() for kw in
                           ['cable', 'virtual', 'voicemeeter', 'vb-audio']):
                        tag = ' [虚拟]'
                    self._share_devices.append((i, f'{name}{tag}'))
        except Exception as exc:
            print(f'[AUDIO] 设备扫描失败: {exc}', flush=True)

    # ======================== 日志 ========================
    def _log_path_resolved(self):
        p = self._s_log_path.get() if hasattr(self, '_s_log_path') else self._cfg('log_path', 'kill_log.txt')
        if not p:
            p = 'kill_log.txt'
        return p if os.path.isabs(p) else os.path.join(BASE_DIR, p)

    def _log(self, msg):
        ts = time.strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        print(line, flush=True)
        try:
            with open(self._log_path_resolved(), 'a', encoding='utf-8') as f:
                f.write(f'{line}\n')
        except Exception as exc:
            print(f'[LOG] 写入失败: {exc}', flush=True)

    # ======================== UI 构建 ========================
    def _build_ui(self):
        win = self._root
        win.deiconify()
        win.title('CSGO 击杀监控')
        win.geometry('520x680')
        win.minsize(520, 680)
        win.configure(bg=MD3.BACKGROUND)
        win.protocol('WM_DELETE_WINDOW', self._on_quit)

        # 标题栏
        header = tk.Frame(win, bg=MD3.SURFACE, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text='CSGO 击杀监控', font=MD3.F_HEADLINE,
                 bg=MD3.SURFACE, fg=MD3.ON_SURFACE).pack(side=tk.LEFT, padx=20, pady=8)

        # 标签栏
        tab_frame = tk.Frame(win, bg=MD3.SURFACE)
        tab_frame.pack(fill=tk.X)
        self._tab_bar = MD3TabBar(
            tab_frame,
            [('main', '主界面'), ('settings', '设置'),
             ('help', '如何使用'), ('about', '关于')],
            self._on_tab_select)
        self._tab_bar.pack(padx=8, pady=(0, 4))

        # 内容区
        self._content = tk.Frame(win, bg=MD3.BACKGROUND)
        self._content.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        self._pages = {}
        self._build_main_page()
        self._build_settings_page()
        self._build_help_page()
        self._build_about_page()

        self._show_page('main')

    def _on_tab_select(self, tab_id):
        self._show_page(tab_id)

    def _show_page(self, page_id):
        for pid, frame in self._pages.items():
            if pid == page_id:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()

    # -------------------- 主界面页 --------------------
    def _build_main_page(self):
        page = tk.Frame(self._content, bg=MD3.BACKGROUND)
        self._pages['main'] = page

        # 状态卡片
        card = MD3Card(page, '状态')
        card.pack(fill=tk.X, pady=(8, 6))

        self._status_var = tk.StringVar(value='● 等待 GSI 连接 ...')
        self._status_label = tk.Label(card.body, textvariable=self._status_var, font=MD3.F_BODY,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT)
        self._status_label.pack(anchor='w')

        # 击杀数 & 速度
        stats_frame = tk.Frame(card.body, bg=MD3.SURFACE_CONTAINER)
        stats_frame.pack(fill=tk.X, pady=8)

        self._kill_var = tk.StringVar(value='击杀数: --')
        tk.Label(stats_frame, textvariable=self._kill_var, font=MD3.F_MONO,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.SUCCESS).pack(side=tk.LEFT, padx=(0, 30))

        self._speed_var = tk.StringVar(value='速度: 1.0x')
        tk.Label(stats_frame, textvariable=self._speed_var, font=MD3.F_MONO_S,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.WARNING).pack(side=tk.LEFT)

        info_text = f'端口: {self._config.get("port", 3000)}    日志: {os.path.basename(self._log_path_resolved())}'
        tk.Label(card.body, text=info_text, font=MD3.F_SMALL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(anchor='w')

        # 开关卡片
        toggle_card = MD3Card(page, '播放控制')
        toggle_card.pack(fill=tk.X, pady=6)

        row1 = tk.Frame(toggle_card.body, bg=MD3.SURFACE_CONTAINER)
        row1.pack(fill=tk.X, pady=4)
        tk.Label(row1, text='播放图片', font=MD3.F_BODY,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE).pack(side=tk.LEFT)
        MD3Switch(row1, self._show_image).pack(side=tk.RIGHT)

        row2 = tk.Frame(toggle_card.body, bg=MD3.SURFACE_CONTAINER)
        row2.pack(fill=tk.X, pady=4)
        tk.Label(row2, text='播放音频', font=MD3.F_BODY,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE).pack(side=tk.LEFT)
        MD3Switch(row2, self._play_sound).pack(side=tk.RIGHT)

        row3 = tk.Frame(toggle_card.body, bg=MD3.SURFACE_CONTAINER)
        row3.pack(fill=tk.X, pady=4)
        tk.Label(row3, text='分享音频到麦克风', font=MD3.F_BODY,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE).pack(side=tk.LEFT)
        MD3Switch(row3, self._share_audio, command=self._on_share_toggle).pack(side=tk.RIGHT)

        # 设备选择卡片
        dev_card = MD3Card(page, '音频分享设备')
        dev_card.pack(fill=tk.X, pady=6)

        dev_row = tk.Frame(dev_card.body, bg=MD3.SURFACE_CONTAINER)
        dev_row.pack(fill=tk.X)
        tk.Label(dev_row, text='目标设备:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT)
        self._share_device_var = tk.StringVar(value='')
        self._share_device_menu = tk.OptionMenu(dev_row, self._share_device_var, '')
        self._share_device_menu.config(font=MD3.F_LABEL, bg=MD3.SURFACE_HIGH,
                                       fg=MD3.ON_SURFACE, width=24,
                                       highlightthickness=0, bd=0)
        self._share_device_menu.pack(side=tk.LEFT, padx=8)
        MD3OutlinedButton(dev_row, '⟳', command=self._refresh_share_devices,
                          width=36, height=28).pack(side=tk.LEFT)

        self._share_info_var = tk.StringVar(value='')
        tk.Label(dev_card.body, textvariable=self._share_info_var, font=MD3.F_SMALL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.OUTLINE).pack(anchor='w', pady=(4, 0))

        # 按钮区
        btn_frame = tk.Frame(page, bg=MD3.BACKGROUND)
        btn_frame.pack(pady=12)
        self._start_btn = MD3Button(btn_frame, '▶  启动服务', command=self.start, width=150)
        self._start_btn.pack(side=tk.LEFT, padx=6)
        self._stop_btn = MD3Button(btn_frame, '■  停止服务', command=self.stop, width=150)
        self._stop_btn.set_state(tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=6)

        btn_row2 = tk.Frame(page, bg=MD3.BACKGROUND)
        btn_row2.pack(pady=(0, 8))
        MD3OutlinedButton(btn_row2, '重置计数', command=self._reset_kills, width=130).pack(side=tk.LEFT, padx=6)
        MD3OutlinedButton(btn_row2, '重置速度', command=self._reset_speed, width=130).pack(side=tk.LEFT, padx=6)

        btn_row3 = tk.Frame(page, bg=MD3.BACKGROUND)
        btn_row3.pack(pady=(0, 12))
        MD3Button(btn_row3, '🎮  启动 CS2', command=self._launch_cs2, width=280).pack()

    # -------------------- 设置页 --------------------
    def _build_settings_page(self):
        scroll = MD3ScrollableFrame(self._content)
        self._pages['settings'] = scroll
        page = scroll.inner

        # === 图片设置 ===
        img_card = MD3Card(page, '图片设置')
        img_card.pack(fill=tk.X, pady=(8, 6))

        r = tk.Frame(img_card.body, bg=MD3.SURFACE_CONTAINER)
        r.pack(fill=tk.X, pady=4)
        tk.Label(r, text='图片库路径:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT)
        path_entry = tk.Entry(r, textvariable=self._s_image_path, font=MD3.F_LABEL,
                              bg=MD3.SURFACE_HIGH, fg=MD3.ON_SURFACE,
                              insertbackground=MD3.ON_SURFACE, width=24,
                              highlightthickness=0, bd=0)
        path_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        MD3TextButton(r, '浏览', command=self._browse_image_dir, width=60, height=28).pack(side=tk.LEFT)
        MD3TextButton(r, '刷新', command=self._rescan_libraries, width=60, height=28).pack(side=tk.LEFT)
        MD3TextButton(r, '预览列表', command=self._open_image_preview_dialog,
                      width=72, height=28).pack(side=tk.LEFT)

        r2 = tk.Frame(img_card.body, bg=MD3.SURFACE_CONTAINER)
        r2.pack(fill=tk.X, pady=4)
        tk.Label(r2, text='播放顺序:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT, padx=(0, 8))
        MD3SegmentedButton(r2,
                          [('loop', '循环'), ('random', '随机'), ('repeat', '重复')],
                          self._s_image_order,
                          command=self._on_image_order_change).pack(side=tk.LEFT)

        # 重复模式: 选择具体图片
        self._repeat_row = tk.Frame(img_card.body, bg=MD3.SURFACE_CONTAINER)
        tk.Label(self._repeat_row, text='重复图片:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT, padx=(0, 8))
        self._repeat_menu = tk.OptionMenu(self._repeat_row, self._s_repeat_image, '')
        self._repeat_menu.config(font=MD3.F_LABEL, bg=MD3.SURFACE_HIGH, fg=MD3.ON_SURFACE,
                                 activebackground=MD3.PRIMARY_CONTAINER,
                                 activeforeground=MD3.ON_PRIMARY_CONTAINER,
                                 highlightthickness=0, bd=0, anchor='w')
        self._repeat_menu['menu'].config(bg=MD3.SURFACE_HIGH, fg=MD3.ON_SURFACE,
                                         activebackground=MD3.PRIMARY_CONTAINER,
                                         activeforeground=MD3.ON_PRIMARY_CONTAINER)
        self._repeat_menu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._update_repeat_menu()

        self._alpha_slider = MD3Slider(img_card.body, '透明度', self._s_image_alpha, 0, 100, '%',
                  command=self._on_setting_change)
        self._alpha_slider.pack(fill=tk.X, pady=4)
        self._on_image_order_change()  # 初始显示/隐藏

        ct_row = tk.Frame(img_card.body, bg=MD3.SURFACE_CONTAINER)
        ct_row.pack(fill=tk.X, pady=4)
        tk.Label(ct_row, text='全屏图片鼠标穿透', font=MD3.F_BODY,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE).pack(side=tk.LEFT)
        MD3Switch(ct_row, self._s_click_through, command=self._on_setting_change).pack(side=tk.RIGHT)

        # === 音频设置 ===
        aud_card = MD3Card(page, '音频设置')
        aud_card.pack(fill=tk.X, pady=6)

        r = tk.Frame(aud_card.body, bg=MD3.SURFACE_CONTAINER)
        r.pack(fill=tk.X, pady=4)
        tk.Label(r, text='音频库路径:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT)
        path_entry2 = tk.Entry(r, textvariable=self._s_audio_path, font=MD3.F_LABEL,
                               bg=MD3.SURFACE_HIGH, fg=MD3.ON_SURFACE,
                               insertbackground=MD3.ON_SURFACE, width=24,
                               highlightthickness=0, bd=0)
        path_entry2.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        MD3TextButton(r, '浏览', command=self._browse_audio_dir, width=60, height=28).pack(side=tk.LEFT)
        MD3TextButton(r, '刷新', command=self._rescan_libraries, width=60, height=28).pack(side=tk.LEFT)
        MD3TextButton(r, '预览列表', command=self._open_audio_preview_dialog,
                      width=72, height=28).pack(side=tk.LEFT)

        r2 = tk.Frame(aud_card.body, bg=MD3.SURFACE_CONTAINER)
        r2.pack(fill=tk.X, pady=4)
        tk.Label(r2, text='播放顺序:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT, padx=(0, 8))
        MD3SegmentedButton(r2,
                          [('loop', '循环'), ('random', '随机'), ('repeat', '重复')],
                          self._s_audio_order).pack(side=tk.LEFT)

        MD3Slider(aud_card.body, '全局音量', self._s_audio_vol, 0, 100, '%',
                  command=self._on_setting_change).pack(fill=tk.X, pady=4)

        btn_row = tk.Frame(aud_card.body, bg=MD3.SURFACE_CONTAINER)
        btn_row.pack(fill=tk.X, pady=4)
        MD3OutlinedButton(btn_row, '单独音量设置', command=self._open_volume_dialog, width=130, height=30).pack(side=tk.LEFT, padx=4)
        MD3OutlinedButton(btn_row, '图片-音频绑定', command=self._open_mapping_dialog, width=130, height=30).pack(side=tk.LEFT, padx=4)

        # === 效果设置 ===
        effect_card = MD3Card(page, '效果设置')
        effect_card.pack(fill=tk.X, pady=6)
        tk.Label(effect_card.body, text='图片显示时使用的动态效果', font=MD3.F_SMALL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(anchor='w', pady=(0, 4))

        effect_mode_row = tk.Frame(effect_card.body, bg=MD3.SURFACE_CONTAINER)
        effect_mode_row.pack(fill=tk.X, pady=4)
        tk.Label(effect_mode_row, text='全局效果:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT, padx=(0, 8))
        MD3SegmentedButton(effect_mode_row,
                           [('random', '随机'), ('fixed', '指定效果')],
                           self._s_effect_mode,
                           command=self._on_effect_mode_change).pack(side=tk.LEFT)

        self._fixed_effect_row = tk.Frame(effect_card.body, bg=MD3.SURFACE_CONTAINER)
        tk.Label(self._fixed_effect_row, text='指定效果:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT, padx=(0, 8))
        MD3SegmentedButton(self._fixed_effect_row,
                           [('shake', '抖动'), ('fade', '渐显/出'), ('flash', '闪动')],
                           self._s_effect_name,
                           command=self._on_setting_change).pack(side=tk.LEFT)

        effect_btn_row = tk.Frame(effect_card.body, bg=MD3.SURFACE_CONTAINER)
        effect_btn_row.pack(fill=tk.X, pady=(6, 0))
        MD3OutlinedButton(effect_btn_row, '图片-效果绑定', command=self._open_effect_mapping_dialog,
                          width=150, height=30).pack(side=tk.LEFT, padx=4)
        tk.Label(effect_btn_row, text='已绑定图片始终使用其指定效果', font=MD3.F_SMALL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.OUTLINE).pack(side=tk.LEFT, padx=6)
        self._on_effect_mode_change()

        # === CS2 路径设置 ===
        cs2_card = MD3Card(page, 'CS2 路径')
        cs2_card.pack(fill=tk.X, pady=6)

        r = tk.Frame(cs2_card.body, bg=MD3.SURFACE_CONTAINER)
        r.pack(fill=tk.X, pady=4)
        tk.Label(r, text='CS2 安装路径:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT)
        cs2_entry = tk.Entry(r, textvariable=self._s_cs2_path, font=MD3.F_LABEL,
                             bg=MD3.SURFACE_HIGH, fg=MD3.ON_SURFACE,
                             insertbackground=MD3.ON_SURFACE, width=22,
                             highlightthickness=0, bd=0)
        cs2_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        MD3TextButton(r, '浏览', command=self._browse_cs2_dir, width=60, height=28).pack(side=tk.LEFT)

        r2 = tk.Frame(cs2_card.body, bg=MD3.SURFACE_CONTAINER)
        r2.pack(fill=tk.X, pady=4)
        MD3OutlinedButton(r2, '🔍  自动查找 CS2', command=self._auto_detect_cs2,
                          width=160, height=30).pack(side=tk.LEFT)

        r3 = tk.Frame(cs2_card.body, bg=MD3.SURFACE_CONTAINER)
        r3.pack(fill=tk.X, pady=4)
        tk.Label(r3, text='CS2 启动命令:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT)
        launch_entry = tk.Entry(r3, textvariable=self._s_cs2_launch_args, font=MD3.F_LABEL,
                                bg=MD3.SURFACE_HIGH, fg=MD3.ON_SURFACE,
                                insertbackground=MD3.ON_SURFACE, width=28,
                                highlightthickness=0, bd=0)
        launch_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        MD3TextButton(r3, '重置', command=lambda: self._s_cs2_launch_args.set(
            DEFAULT_CS2_LAUNCH_ARGS), width=60, height=28).pack(side=tk.LEFT)

        self._cs2_detect_var = tk.StringVar(value='')
        tk.Label(cs2_card.body, textvariable=self._cs2_detect_var, font=MD3.F_SMALL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.OUTLINE,
                 wraplength=380, justify='left').pack(anchor='w', pady=(4, 0))

        # === 路径设置 ===
        path_card = MD3Card(page, '路径设置')
        path_card.pack(fill=tk.X, pady=6)

        r = tk.Frame(path_card.body, bg=MD3.SURFACE_CONTAINER)
        r.pack(fill=tk.X, pady=4)
        tk.Label(r, text='游戏日志路径:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT)
        log_entry = tk.Entry(r, textvariable=self._s_log_path, font=MD3.F_LABEL,
                             bg=MD3.SURFACE_HIGH, fg=MD3.ON_SURFACE,
                             insertbackground=MD3.ON_SURFACE, width=22,
                             highlightthickness=0, bd=0)
        log_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        MD3TextButton(r, '浏览', command=self._browse_log_file, width=60, height=28).pack(side=tk.LEFT)

        r2 = tk.Frame(path_card.body, bg=MD3.SURFACE_CONTAINER)
        r2.pack(fill=tk.X, pady=4)
        tk.Label(r2, text='配置保存地址:', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(side=tk.LEFT)
        cfg_entry = tk.Entry(r2, textvariable=self._s_config_path, font=MD3.F_LABEL,
                             bg=MD3.SURFACE_HIGH, fg=MD3.ON_SURFACE,
                             insertbackground=MD3.ON_SURFACE, width=22,
                             highlightthickness=0, bd=0)
        cfg_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        MD3TextButton(r2, '浏览', command=self._browse_config_path, width=60, height=28).pack(side=tk.LEFT)

        default_hint = tk.Label(path_card.body, font=MD3.F_SMALL,
                               text=f'默认: {DEFAULT_CONFIG_PATH}',
                               bg=MD3.SURFACE_CONTAINER, fg=MD3.OUTLINE,
                               wraplength=380, justify='left')
        default_hint.pack(anchor='w', pady=(2, 0))

        # === 配置管理 ===
        mgr_card = MD3Card(page, '配置管理')
        mgr_card.pack(fill=tk.X, pady=6)

        cfg_btn_row = tk.Frame(mgr_card.body, bg=MD3.SURFACE_CONTAINER)
        cfg_btn_row.pack(fill=tk.X, pady=4)
        MD3OutlinedButton(cfg_btn_row, '导入配置', command=self._import_config, width=130, height=32).pack(side=tk.LEFT, padx=4)
        MD3OutlinedButton(cfg_btn_row, '导出配置', command=self._export_config, width=130, height=32).pack(side=tk.LEFT, padx=4)

        # 保存按钮
        save_row = tk.Frame(page, bg=MD3.BACKGROUND)
        save_row.pack(pady=12)
        MD3Button(save_row, '保存设置', command=self._save_and_apply, width=200).pack()

    # -------------------- 如何使用页 --------------------
    def _build_help_page(self):
        scroll = MD3ScrollableFrame(self._content)
        self._pages['help'] = scroll
        page = scroll.inner

        card = MD3Card(page, '如何使用')
        card.pack(fill=tk.BOTH, expand=True, pady=(8, 12))

        steps = [
            ('1. 安装依赖', 'pip install -r requirements.txt'),
            ('2. 准备素材', '将图片放入 images/ 文件夹，音频放入 audio/ 文件夹\n'
                            '支持格式: 图片(jpg/png/gif/bmp/webp) 音频(mp3/wav/m4a/flac/ogg)'),
            ('3. 配置 CSGO GSI', '在设置页点击「自动查找 CS2」可自动定位 CS2 安装路径\n'
                                 '也可手动浏览选择 CS2 目录\n'
                                 '点击主界面「启动 CS2」会自动安装 GSI 配置并启动游戏'),
            ('4. 启动程序', 'python csgo_kill_monitor.py\n点击主界面的「启动服务」'),
            ('5. 进入游戏', '开始对局后，每次击杀会自动:\n'
                            '  • 全屏弹出图片（可设透明度/鼠标穿透）\n'
                            '  • 播放音频（每杀加速0.1x，音调同步升高）\n'
                            '  • 记录到日志文件'),
            ('6. 音频分享', '安装 VB-Cable 虚拟声卡 → 勾选「分享音频」\n'
                            '选择 CABLE Input → CSGO 麦克风选 CABLE Output\n'
                            '队友即可同时听到你的说话声和击杀音效'),
            ('7. 图片-音频绑定', '在设置页点击「图片-音频绑定」\n'
                                 '为特定图片指定专属音频（不受随机/循环影响）'),
            ('8. 配置导入/导出', '在设置页可导出当前配置为 JSON 文件\n'
                                 '也可导入他人的配置文件快速设置'),
            ('9. 鼠标穿透', '设置中开启「全屏图片鼠标穿透」后\n'
                            '图片显示期间鼠标点击会穿透到游戏，不干扰操作'),
        ]

        for title, desc in steps:
            tk.Label(card.body, text=title, font=MD3.F_BODY_B,
                    bg=MD3.SURFACE_CONTAINER, fg=MD3.PRIMARY).pack(anchor='w', pady=(8, 2))
            tk.Label(card.body, text=desc, font=MD3.F_LABEL,
                    bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT,
                    justify='left').pack(anchor='w', padx=(16, 0))

    # -------------------- 关于页 --------------------
    def _build_about_page(self):
        page = tk.Frame(self._content, bg=MD3.BACKGROUND)
        self._pages['about'] = page

        card = MD3Card(page)
        card.pack(fill=tk.BOTH, expand=True, pady=(8, 12))

        # 应用信息
        tk.Label(card.body, text='CSGO 击杀监控', font=MD3.F_DISPLAY,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.PRIMARY).pack(pady=(12, 4))
        tk.Label(card.body, text='Material Design 3 Edition', font=MD3.F_BODY,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(pady=(0, 16))

        # 作者信息
        tk.Label(card.body, text='原作者', font=MD3.F_LABEL_B,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(anchor='w')
        tk.Label(card.body, text='libi2009', font=MD3.F_BODY_B,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE).pack(anchor='w')
        tk.Label(card.body, text='https://github.com/libi2009', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.INFO, cursor='hand2').pack(anchor='w', pady=(0, 12))

        tk.Label(card.body, text='现作者', font=MD3.F_LABEL_B,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(anchor='w')
        tk.Label(card.body, text='Minecraftmc22', font=MD3.F_BODY_B,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE).pack(anchor='w')
        tk.Label(card.body, text='https://github.com/minecraftmc22', font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.INFO, cursor='hand2').pack(anchor='w', pady=(0, 12))

        # 功能列表
        tk.Label(card.body, text='功能特性', font=MD3.F_LABEL_B,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT).pack(anchor='w', pady=(4, 2))
        features = (
            '• GSI 实时击杀监测\n'
            '• 击杀弹图（全屏/透明度/鼠标穿透）\n'
            '• 变速变调音频（每杀+0.1x）\n'
            '• 图片库/音频库管理（循环/随机/重复）\n'
            '• 全局/单独音量控制\n'
            '• 图片-音频绑定映射\n'
            '• 音频分享到麦克风（队友可听）\n'
            '• 配置导入/导出\n'
            '• Material Design 3 界面'
        )
        tk.Label(card.body, text=features, font=MD3.F_LABEL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE_VARIANT,
                 justify='left').pack(anchor='w', padx=(8, 0))

        tk.Label(card.body, text='License: MIT', font=MD3.F_SMALL,
                 bg=MD3.SURFACE_CONTAINER, fg=MD3.OUTLINE).pack(anchor='w', pady=(12, 0))

    # ======================== 设置交互 ========================
    def _on_setting_change(self):
        """设置变更时保存"""
        self._save_config()

    def _on_image_order_change(self):
        """播放顺序变化时显示/隐藏重复图片选择"""
        if self._s_image_order.get() == 'repeat':
            self._update_repeat_menu()
            self._repeat_row.pack(fill=tk.X, pady=4, before=self._alpha_slider)
        else:
            self._repeat_row.pack_forget()
        self._save_config()

    def _on_effect_mode_change(self):
        """仅在指定模式下显示全局效果选择。"""
        if self._s_effect_mode.get() == 'fixed':
            self._fixed_effect_row.pack(fill=tk.X, pady=4)
        else:
            self._fixed_effect_row.pack_forget()
        self._save_config()

    def _update_repeat_menu(self):
        """更新重复图片下拉菜单选项"""
        if not hasattr(self, '_repeat_menu'):
            return
        menu = self._repeat_menu['menu']
        menu.delete(0, 'end')
        current = self._s_repeat_image.get()
        for img in self._image_files:
            label = os.path.basename(img)
            menu.add_command(label=label,
                             command=lambda v=img: self._s_repeat_image.set(v))
        # 如果当前选中的图片不在列表中，重置为第一张
        if current not in self._image_files and self._image_files:
            self._s_repeat_image.set(self._image_files[0])
        elif not self._image_files:
            self._s_repeat_image.set('')

    def _save_and_apply(self):
        """保存并应用设置"""
        self._save_config()
        self._scan_libraries()
        messagebox.showinfo('设置', '设置已保存并应用')

    def _browse_image_dir(self):
        d = _browse_folder(self._resolve_path(self._s_image_path.get()))
        if d:
            rel = os.path.relpath(d, BASE_DIR) if d.startswith(BASE_DIR) else d
            self._s_image_path.set(rel)
            self._on_setting_change()

    def _browse_audio_dir(self):
        d = _browse_folder(self._resolve_path(self._s_audio_path.get()))
        if d:
            rel = os.path.relpath(d, BASE_DIR) if d.startswith(BASE_DIR) else d
            self._s_audio_path.set(rel)
            self._on_setting_change()

    # ======================== CS2 路径检测与启动 ========================
    def _auto_detect_cs2(self):
        """自动查找 CS2 安装路径
        流程: 读注册表找 Steam 根目录 → 解析 libraryfolders.vdf
              → 在每个库中查找 appmanifest_730.acf → 提取 installdir
        """
        self._cs2_detect_var.set('正在查找 Steam...')
        self._root.update()

        # 1. 从注册表读取 Steam 安装路径
        steam_path = self._find_steam_path()
        if not steam_path:
            self._cs2_detect_var.set('❌ 未找到 Steam，请确认 Steam 已安装，或手动浏览选择 CS2 目录')
            return

        self._cs2_detect_var.set(f'Steam: {steam_path}\n正在搜索游戏库...')
        self._root.update()

        # 2. 解析 libraryfolders.vdf 获取所有库路径
        vdf_path = os.path.join(steam_path, 'steamapps', 'libraryfolders.vdf')
        if not os.path.exists(vdf_path):
            self._cs2_detect_var.set(f'❌ 未找到 libraryfolders.vdf\n路径: {vdf_path}')
            return

        library_paths = self._parse_library_folders(vdf_path)
        if not library_paths:
            # 回退: Steam 自身目录
            library_paths = [os.path.join(steam_path, 'steamapps')]
        # 确保 Steam 自身库也在列表中
        default_lib = os.path.join(steam_path, 'steamapps')
        if default_lib not in library_paths:
            library_paths.insert(0, default_lib)

        # 3. 在每个库中查找 appmanifest_730.acf
        for lib_path in library_paths:
            self._cs2_detect_var.set(f'正在搜索: {lib_path} ...')
            self._root.update()

            manifest_path = os.path.join(lib_path, f'appmanifest_{CS2_APP_ID}.acf')
            if not os.path.exists(manifest_path):
                continue

            # 4. 解析 installdir
            installdir = self._parse_acf_installdir(manifest_path)
            if installdir:
                cs2_full_path = os.path.join(lib_path, 'common', installdir)
                if os.path.isdir(cs2_full_path):
                    self._s_cs2_path.set(cs2_full_path)
                    self._on_setting_change()
                    self._cs2_detect_var.set(f'✅ 已找到 CS2:\n{cs2_full_path}')
                    return

        self._cs2_detect_var.set('❌ 未在 Steam 库中找到 CS2 (AppID 730)\n'
                                 '请确认已安装 CS2，或手动浏览选择')

    @staticmethod
    def _find_steam_path():
        """从 Windows 注册表查找 Steam 安装路径"""
        if winreg is None:
            return None
        reg_keys = [
            (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath'),
        ]
        for root, subkey, name in reg_keys:
            try:
                with winreg.OpenKey(root, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, name)
                    if val and os.path.isdir(val):
                        return val.replace('/', os.sep)
            except (FileNotFoundError, OSError):
                continue
        return None

    @staticmethod
    def _parse_library_folders(vdf_path):
        """解析 libraryfolders.vdf，返回所有库路径列表"""
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return []

        paths = []
        # 匹配 "path"     "D:\\SteamLibrary"
        for m in re.finditer(r'"path"\s+"([^"]+)"', content):
            p = m.group(1).replace('\\\\', os.sep).replace('/', os.sep)
            paths.append(p)
        return paths

    @staticmethod
    def _parse_acf_installdir(acf_path):
        """解析 appmanifest_730.acf，提取 installdir"""
        try:
            with open(acf_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return None
        m = re.search(r'"installdir"\s+"([^"]+)"', content)
        return m.group(1) if m else None

    def _browse_cs2_dir(self):
        """手动浏览选择 CS2 安装目录"""
        initial = self._s_cs2_path.get() or None
        d = filedialog.askdirectory(
            initialdir=initial or BASE_DIR,
            title='选择 CS2 安装目录 (包含 bin/ 的目录)')
        if d:
            self._s_cs2_path.set(d)
            self._cs2_detect_var.set(f'已设置: {d}')
            self._on_setting_change()

    def _resolve_cs2_path(self):
        """获取解析后的 CS2 路径"""
        p = self._s_cs2_path.get().strip() if hasattr(self, '_s_cs2_path') else \
            self._cfg('cs2_path', '')
        return p

    def _get_cs2_exe_path(self):
        """获取 cs2.exe 完整路径"""
        cs2_path = self._resolve_cs2_path()
        if not cs2_path:
            return None
        # CS2 可执行文件路径: <cs2_path>/game/bin/win64/cs2.exe
        cs2_exe = os.path.join(cs2_path, 'game', 'bin', 'win64', 'cs2.exe')
        if os.path.exists(cs2_exe):
            return cs2_exe
        # 兼容旧路径
        cs2_exe = os.path.join(cs2_path, 'bin', 'win64', 'cs2.exe')
        if os.path.exists(cs2_exe):
            return cs2_exe
        return None

    def _get_cs2_cfg_dir(self):
        """获取 CS2 cfg 目录路径"""
        cs2_path = self._resolve_cs2_path()
        if not cs2_path:
            return None
        cfg_dir = os.path.join(cs2_path, 'game', 'csgo', 'cfg')
        if os.path.isdir(cfg_dir):
            return cfg_dir
        # 兼容旧路径
        cfg_dir = os.path.join(cs2_path, 'csgo', 'cfg')
        if os.path.isdir(cfg_dir):
            return cfg_dir
        return None

    def _generate_gsi_cfg(self):
        """生成 gamestate_integration_kill_monitor.cfg 内容"""
        port = self._config.get('port', 3000)
        return (
            '"CSGO Kill Monitor"\n'
            '{\n'
            f'\t"uri" "http://127.0.0.1:{port}"\n'
            '\t"timeout" "5.0"\n'
            '\t"buffer" "0.1"\n'
            '\t"throttle" "0.1"\n'
            '\t"heartbeat" "30.0"\n'
            '\t"data"\n'
            '\t{\n'
            '\t\t"provider"            "1"\n'
            '\t\t"player_id"           "1"\n'
            '\t\t"player_state"        "1"\n'
            '\t\t"player_match_stats"  "1"\n'
            '\t}\n'
            '}\n'
        )

    def _launch_cs2(self):
        """启动 CS2
        流程: 1.检查 CS2 路径 → 2.复制 GSI cfg → 3.启动 cs2.exe +exec
        """
        cs2_path = self._resolve_cs2_path()

        # 1. 检查路径
        if not cs2_path:
            result = messagebox.askyesno(
                'CS2 路径未设置',
                '尚未设置 CS2 安装路径。\n是否现在自动查找？\n（点击"否"可手动浏览）')
            if result:
                self._auto_detect_cs2()
                cs2_path = self._resolve_cs2_path()
                if not cs2_path:
                    return
            else:
                self._browse_cs2_dir()
                cs2_path = self._resolve_cs2_path()
                if not cs2_path:
                    return

        cs2_exe = self._get_cs2_exe_path()
        if not cs2_exe:
            messagebox.showerror('错误',
                f'在以下路径中未找到 cs2.exe:\n{cs2_path}\n\n'
                '请确认路径正确（应包含 game/bin/win64/ 目录）')
            return

        # 2. 复制 GSI cfg
        cfg_dir = self._get_cs2_cfg_dir()
        if cfg_dir:
            try:
                cfg_content = self._generate_gsi_cfg()
                dest = os.path.join(cfg_dir, GSI_CFG_FILENAME)
                with open(dest, 'w', encoding='utf-8') as f:
                    f.write(cfg_content)
                self._log(f'GSI 配置已写入: {dest}')
            except Exception as exc:
                self._log(f'GSI 配置写入失败: {exc}')
                if not messagebox.askyesno('警告',
                    f'GSI 配置文件写入失败:\n{exc}\n\n'
                    '是否仍要启动 CS2？'):
                    return
        else:
            if not messagebox.askyesno('警告',
                '未找到 CS2 cfg 目录。\n'
                'GSI 配置将不会被自动安装。\n\n'
                '是否仍要启动 CS2？'):
                return

        # 3. 启动 CS2
        try:
            launch_args = self._s_cs2_launch_args.get().strip()
            if not launch_args:
                launch_args = DEFAULT_CS2_LAUNCH_ARGS
            cmd = [cs2_exe] + launch_args.split()
            self._log(f'启动 CS2: {" ".join(cmd)}')
            subprocess.Popen(cmd, cwd=os.path.dirname(cs2_exe))
            messagebox.showinfo('CS2', 'CS2 正在启动...\n'
                                     '请确保已启动本程序的服务来接收 GSI 数据。')
        except Exception as exc:
            messagebox.showerror('启动失败', f'无法启动 CS2:\n{exc}')

    def _browse_log_file(self):
        f = filedialog.asksaveasfilename(
            initialdir=BASE_DIR,
            defaultextension='.txt',
            filetypes=[('文本文件', '*.txt'), ('所有文件', '*.*')])
        if f:
            rel = os.path.relpath(f, BASE_DIR) if f.startswith(BASE_DIR) else f
            self._s_log_path.set(rel)
            self._on_setting_change()

    def _browse_config_path(self):
        f = filedialog.asksaveasfilename(
            initialdir=DEFAULT_CONFIG_DIR,
            defaultextension='.json',
            filetypes=[('JSON 文件', '*.json'), ('所有文件', '*.*')])
        if f:
            self._s_config_path.set(f)
            self._on_setting_change()

    def _rescan_libraries(self):
        """重新扫描媒体库"""
        self._save_config()
        self._scan_libraries()
        self._update_repeat_menu()
        messagebox.showinfo('刷新', f'图片: {len(self._image_files)} 个\n音频: {len(self._audio_files)} 个')

    def _import_config(self):
        """导入配置"""
        f = filedialog.askopenfilename(
            initialdir=BASE_DIR,
            filetypes=[('JSON 文件', '*.json'), ('所有文件', '*.*')])
        if not f:
            return
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                cfg = json.load(fh)
            self._config = self._merge_defaults(cfg)
            # 更新 UI 变量
            self._s_image_path.set(self._cfg('image', 'library_path', 'images'))
            self._s_image_order.set(self._cfg('image', 'playback_order', 'loop'))
            self._s_repeat_image.set(self._cfg('image', 'repeat_image', ''))
            self._s_image_alpha.set(int(self._cfg('image', 'alpha', 0.9) * 100))
            self._s_click_through.set(self._cfg('pip', 'click_through', True))
            self._s_audio_path.set(self._cfg('audio', 'library_path', 'audio'))
            self._s_audio_order.set(self._cfg('audio', 'playback_order', 'loop'))
            self._s_audio_vol.set(self._cfg('audio', 'global_volume', 100))
            self._s_effect_mode.set(self._cfg('effect', 'mode', 'random'))
            self._s_effect_name.set(self._cfg('effect', 'selected_effect', 'shake'))
            self._on_effect_mode_change()
            self._s_log_path.set(self._cfg('log_path', 'kill_log.txt'))
            self._s_config_path.set(self._cfg('config_path', ''))
            self._s_cs2_path.set(self._cfg('cs2_path', ''))
            self._s_cs2_launch_args.set(
                self._cfg('cs2_launch_args', DEFAULT_CS2_LAUNCH_ARGS))
            self._scan_libraries()
            self._save_config()
            messagebox.showinfo('导入', '配置已导入')
        except Exception as exc:
            messagebox.showerror('错误', f'导入失败:\n{exc}')

    def _export_config(self):
        """导出配置"""
        self._save_config()
        f = filedialog.asksaveasfilename(
            initialdir=BASE_DIR,
            defaultextension='.json',
            filetypes=[('JSON 文件', '*.json')],
            initialfile='csgo_kill_monitor_config.json')
        if not f:
            return
        try:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(self._config, fh, indent=4, ensure_ascii=False)
            messagebox.showinfo('导出', f'配置已导出到:\n{f}')
        except Exception as exc:
            messagebox.showerror('错误', f'导出失败:\n{exc}')

    # ======================== 素材预览列表 ========================
    def _open_image_preview_dialog(self):
        """显示图片库的缩略图列表。"""
        if not self._image_files:
            messagebox.showinfo('提示', '图片库为空，请先添加图片文件')
            return

        dlg = tk.Toplevel(self._root)
        dlg.title('图片预览列表')
        dlg.geometry('580x560')
        dlg.configure(bg=MD3.BACKGROUND)
        dlg.transient(self._root)

        tk.Label(dlg, text=f'图片预览列表（{len(self._image_files)} 张）', font=MD3.F_HEADLINE,
                 bg=MD3.BACKGROUND, fg=MD3.ON_BACKGROUND).pack(pady=(12, 8))
        scroll = MD3ScrollableFrame(dlg)
        scroll.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        thumbnails = []

        for img in self._image_files:
            row = tk.Frame(scroll.inner, bg=MD3.SURFACE_CONTAINER)
            row.pack(fill=tk.X, padx=4, pady=3)
            preview = tk.Label(row, text='无法预览', font=MD3.F_SMALL, width=13, height=5,
                               bg=MD3.SURFACE_HIGH, fg=MD3.OUTLINE)
            preview.pack(side=tk.LEFT, padx=8, pady=5)
            try:
                with Image.open(self._resolve_image_full(img)) as source:
                    thumb = source.convert('RGB')
                    thumb.thumbnail((120, 80), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(thumb)
                preview.config(image=photo, text='', width=120, height=80)
                thumbnails.append(photo)
            except Exception:
                pass
            tk.Label(row, text=os.path.basename(img), font=MD3.F_BODY,
                     bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE,
                     anchor='w', wraplength=380, justify='left').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        dlg._thumbnails = thumbnails

    def _open_audio_preview_dialog(self):
        """显示音频库清单，并允许按正常速度试听单个音频。"""
        if not self._audio_files:
            messagebox.showinfo('提示', '音频库为空，请先添加音频文件')
            return

        dlg = tk.Toplevel(self._root)
        dlg.title('音频预览列表')
        dlg.geometry('560x500')
        dlg.configure(bg=MD3.BACKGROUND)
        dlg.transient(self._root)

        tk.Label(dlg, text=f'音频预览列表（{len(self._audio_files)} 个）', font=MD3.F_HEADLINE,
                 bg=MD3.BACKGROUND, fg=MD3.ON_BACKGROUND).pack(pady=(12, 4))
        tk.Label(dlg, text='点击“试听”将以 1.0 倍速播放，音量遵循全局音量设置', font=MD3.F_SMALL,
                 bg=MD3.BACKGROUND, fg=MD3.ON_SURFACE_VARIANT).pack(pady=(0, 8))
        scroll = MD3ScrollableFrame(dlg)
        scroll.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        for audio_name in self._audio_files:
            row = tk.Frame(scroll.inner, bg=MD3.SURFACE_CONTAINER)
            row.pack(fill=tk.X, padx=4, pady=3)
            tk.Label(row, text=os.path.basename(audio_name), font=MD3.F_BODY,
                     bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE,
                     anchor='w').pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=8)
            MD3TextButton(row, '试听', command=lambda name=audio_name: self._preview_audio(name),
                          width=60, height=28).pack(side=tk.RIGHT, padx=8)

    def _preview_audio(self, audio_name):
        """以正常速度播放预览，避免影响击杀时的累积速度。"""
        threading.Thread(target=self._play_speed_thread,
                         args=(audio_name, 1.0), daemon=True).start()

    # ======================== 单独音量对话框 ========================
    def _open_volume_dialog(self):
        """打开单独音量设置对话框"""
        if not self._audio_files:
            messagebox.showinfo('提示', '音频库为空，请先添加音频文件')
            return

        dlg = tk.Toplevel(self._root)
        dlg.title('单独音量设置')
        dlg.geometry('420x500')
        dlg.configure(bg=MD3.BACKGROUND)
        dlg.transient(self._root)
        dlg.grab_set()

        tk.Label(dlg, text='单独音量设置', font=MD3.F_HEADLINE,
                 bg=MD3.BACKGROUND, fg=MD3.ON_BACKGROUND).pack(pady=(12, 4))
        tk.Label(dlg, text='每个音频的音量与全局音量相乘', font=MD3.F_SMALL,
                 bg=MD3.BACKGROUND, fg=MD3.ON_SURFACE_VARIANT).pack(pady=(0, 8))

        scroll = MD3ScrollableFrame(dlg)
        scroll.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        per_vol = self._cfg('audio', 'per_audio_volume', {})
        if not isinstance(per_vol, dict):
            per_vol = {}

        vol_vars = {}
        for af in self._audio_files:
            row = tk.Frame(scroll.inner, bg=MD3.SURFACE_CONTAINER)
            row.pack(fill=tk.X, pady=2, padx=4)
            tk.Label(row, text=os.path.basename(af), font=MD3.F_LABEL,
                     bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE,
                     width=20, anchor='w').pack(side=tk.LEFT)
            v = tk.IntVar(value=per_vol.get(af, 100))
            vol_vars[af] = v
            scale = tk.Scale(row, from_=0, to=100, orient=tk.HORIZONTAL,
                             variable=v, bg=MD3.SURFACE_CONTAINER,
                             fg=MD3.ON_SURFACE, troughcolor=MD3.SURFACE_VARIANT,
                             highlightthickness=0, bd=0, sliderrelief=tk.FLAT,
                             font=MD3.F_SMALL, length=180)
            scale.pack(side=tk.LEFT, padx=8)

        def save():
            new_map = {af: v.get() for af, v in vol_vars.items()}
            self._config.setdefault('audio', {})['per_audio_volume'] = new_map
            self._save_config()
            dlg.destroy()
            messagebox.showinfo('保存', '单独音量已保存')

        MD3Button(dlg, '保存', command=save, width=140).pack(pady=12)

    # ======================== 图片-音频绑定对话框 ========================
    def _open_mapping_dialog(self):
        """打开图片-音频绑定对话框"""
        if not self._image_files:
            messagebox.showinfo('提示', '图片库为空，请先添加图片文件')
            return

        dlg = tk.Toplevel(self._root)
        dlg.title('图片-音频绑定')
        dlg.geometry('620x560')
        dlg.configure(bg=MD3.BACKGROUND)
        dlg.transient(self._root)
        dlg.grab_set()

        tk.Label(dlg, text='图片-音频绑定', font=MD3.F_HEADLINE,
                 bg=MD3.BACKGROUND, fg=MD3.ON_BACKGROUND).pack(pady=(12, 4))
        tk.Label(dlg, text='为特定图片指定专属音频（不受随机/循环影响）', font=MD3.F_SMALL,
                 bg=MD3.BACKGROUND, fg=MD3.ON_SURFACE_VARIANT).pack(pady=(0, 8))

        scroll = MD3ScrollableFrame(dlg)
        scroll.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        mapping = self._cfg('audio', 'image_audio_map', {})
        if not isinstance(mapping, dict):
            mapping = {}

        map_vars = {}
        thumbnails = []  # 保留 PhotoImage 引用，避免 Tk 回收后缩略图消失。
        for img in self._image_files:
            row = tk.Frame(scroll.inner, bg=MD3.SURFACE_CONTAINER)
            row.pack(fill=tk.X, pady=2, padx=4)
            preview = tk.Label(row, text='无预览', font=MD3.F_SMALL, width=10, height=4,
                               bg=MD3.SURFACE_HIGH, fg=MD3.OUTLINE)
            preview.pack(side=tk.LEFT, padx=(0, 6))
            try:
                with Image.open(self._resolve_image_full(img)) as source:
                    thumb = source.convert('RGB')
                    thumb.thumbnail((72, 54), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(thumb)
                preview.config(image=photo, text='', width=72, height=54)
                thumbnails.append(photo)
            except Exception:
                pass
            tk.Label(row, text=os.path.basename(img), font=MD3.F_LABEL,
                     bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE,
                     width=20, anchor='w').pack(side=tk.LEFT)

            current = mapping.get(img, '(无)')
            options = ['(无)'] + list(self._audio_files)
            var = tk.StringVar(value=current if current in options else '(无)')
            map_vars[img] = var
            menu = tk.OptionMenu(row, var, *options)
            menu.config(font=MD3.F_SMALL, bg=MD3.SURFACE_HIGH,
                        fg=MD3.ON_SURFACE, width=20, highlightthickness=0, bd=0)
            menu.pack(side=tk.LEFT, padx=4)

        dlg._thumbnails = thumbnails

        def save():
            new_map = {img: v.get() for img, v in map_vars.items() if v.get() != '(无)'}
            self._config.setdefault('audio', {})['image_audio_map'] = new_map
            self._save_config()
            dlg.destroy()
            messagebox.showinfo('保存', '图片-音频绑定已保存')

        MD3Button(dlg, '保存', command=save, width=140).pack(pady=12)

    def _open_effect_mapping_dialog(self):
        """为图片指定专属展示效果，优先级高于全局随机效果。"""
        if not self._image_files:
            messagebox.showinfo('提示', '图片库为空，请先添加图片文件')
            return

        dlg = tk.Toplevel(self._root)
        dlg.title('图片-效果绑定')
        dlg.geometry('620x560')
        dlg.configure(bg=MD3.BACKGROUND)
        dlg.transient(self._root)
        dlg.grab_set()

        tk.Label(dlg, text='图片-效果绑定', font=MD3.F_HEADLINE,
                 bg=MD3.BACKGROUND, fg=MD3.ON_BACKGROUND).pack(pady=(12, 4))
        tk.Label(dlg, text='已绑定的图片始终使用此效果，不受全局随机设置影响', font=MD3.F_SMALL,
                 bg=MD3.BACKGROUND, fg=MD3.ON_SURFACE_VARIANT).pack(pady=(0, 8))

        scroll = MD3ScrollableFrame(dlg)
        scroll.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        mapping = self._cfg('effect', 'image_effect_map', {})
        mapping = mapping if isinstance(mapping, dict) else {}
        effect_labels = {'(无)': '(无)', 'shake': '抖动', 'fade': '渐显/出', 'flash': '闪动'}
        label_to_effect = {label: key for key, label in effect_labels.items()}
        options = list(label_to_effect)
        map_vars = {}
        thumbnails = []
        for img in self._image_files:
            row = tk.Frame(scroll.inner, bg=MD3.SURFACE_CONTAINER)
            row.pack(fill=tk.X, pady=2, padx=4)
            preview = tk.Label(row, text='无预览', font=MD3.F_SMALL, width=10, height=4,
                               bg=MD3.SURFACE_HIGH, fg=MD3.OUTLINE)
            preview.pack(side=tk.LEFT, padx=(0, 6))
            try:
                with Image.open(self._resolve_image_full(img)) as source:
                    thumb = source.convert('RGB')
                    thumb.thumbnail((72, 54), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(thumb)
                preview.config(image=photo, text='', width=72, height=54)
                thumbnails.append(photo)
            except Exception:
                pass
            tk.Label(row, text=os.path.basename(img), font=MD3.F_LABEL,
                     bg=MD3.SURFACE_CONTAINER, fg=MD3.ON_SURFACE,
                     width=20, anchor='w').pack(side=tk.LEFT)
            var = tk.StringVar(value=effect_labels.get(mapping.get(img), '(无)'))
            map_vars[img] = var
            menu = tk.OptionMenu(row, var, *options)
            menu.config(font=MD3.F_SMALL, bg=MD3.SURFACE_HIGH,
                        fg=MD3.ON_SURFACE, width=12, highlightthickness=0, bd=0)
            menu.pack(side=tk.LEFT, padx=4)

        dlg._thumbnails = thumbnails

        def save():
            new_map = {img: label_to_effect[v.get()] for img, v in map_vars.items()
                       if v.get() != '(无)'}
            self._config.setdefault('effect', {})['image_effect_map'] = new_map
            self._save_config()
            dlg.destroy()
            messagebox.showinfo('保存', '图片-效果绑定已保存')

        MD3Button(dlg, '保存', command=save, width=140).pack(pady=12)

    # ======================== GSI 数据处理 ========================
    def _process_gsi(self, data):
        try:
            player = data.get('player', {})
            state = player.get('state', {})
            health = state.get('health', 100)

            stats = player.get('match_stats', {})
            kills = stats.get('kills')
            if kills is None:
                return

            # 玩家死亡时暂停处理，避免 kills 波动导致疯狂触发
            if health <= 0:
                self._player_dead = True
                return

            # 玩家刚复活：同步计数但不触发击杀
            if self._player_dead:
                self._player_dead = False
                self._kill_count = kills
                self._kill_var.set(f'击杀数: {kills}')
                self._log(f'玩家复活，击杀数同步为 {kills}')
                return

            if self._kill_count < 0:
                self._kill_count = kills
                self._speed = 1.0
                self._kill_var.set(f'击杀数: {kills}')
                self._speed_var.set(f'速度: {self._speed:.1f}x')
                if self._status_var.get().startswith('● 等待'):
                    self._update_status('● 已连接（等待击杀）', MD3.INFO)
                self._log(f'GSI 已连接，当前击杀数: {kills}')
                return

            if kills > self._kill_count:
                delta = kills - self._kill_count
                self._kill_count = kills
                self._kill_var.set(f'击杀数: {kills}')
                for _ in range(delta):
                    self._on_kill(kills)
            elif kills < self._kill_count:
                # 仅当降幅明显时才视为新对局重置
                # （避免 GSI 数据短暂波动导致的误触发）
                if kills == 0:
                    self._kill_count = kills
                    self._speed = 1.0
                    self._kill_var.set(f'击杀数: {kills}')
                    self._speed_var.set('速度: 1.0x')
                    self._log(f'新对局，击杀数重置为 {kills}，速度重置为 1.0x')
                else:
                    # 小幅波动不重置，只更新计数
                    self._kill_count = kills
        except Exception as exc:
            print(f'[GSI] 解析错误: {exc}', flush=True)

    def _on_kill(self, total):
        self._log(f'击杀! 总计: {total}  |  速度: {self._speed:.1f}x'
                  f'  |  图片: {"开" if self._show_image.get() else "关"}'
                  f'  |  音频: {"开" if self._play_sound.get() else "关"}')

        # 先选图片，再用图片名查音频映射
        selected_image = None
        if self._show_image.get():
            selected_image = self._pick_image()
            if selected_image:
                self._show_pip(selected_image)

        if self._play_sound.get():
            img_name = os.path.basename(selected_image) if selected_image else None
            self._play_audio(img_name)

        self._speed = round(self._speed + 0.1, 1)
        self._speed_var.set(f'速度: {self._speed:.1f}x')

    def _show_pip(self, image_name=None):
        """弹出图片"""
        if self._active_pip:
            self._active_pip.close()

        if image_name is None:
            image_name = self._pick_image()
        if not image_name:
            return

        full = self._resolve_image_full(image_name)
        if not os.path.exists(full):
            # 兼容旧路径
            legacy = self._config.get('_legacy_image_path', '')
            if legacy:
                full = self._resolve_path(legacy)
            if not os.path.exists(full):
                print(f'[PIP] 图片不存在: {full}', flush=True)
                return

        alpha = self._s_image_alpha.get() / 100.0
        click_through = self._s_click_through.get()

        self._active_pip = PipWindow(
            image_path=full,
            position=(0, 0),
            size=(800, 600),
            auto_close=self._config.get('display_duration', 1000),
            fullscreen=self._cfg('pip', 'fullscreen', True),
            alpha=alpha,
            click_through=click_through,
            effect=self._pick_effect(os.path.basename(image_name)),
        )

    def _update_status(self, text, color=None):
        self._status_var.set(text)
        if color and hasattr(self, '_status_label'):
            self._status_label.config(fg=color)

    # ======================== 音频设备 ========================
    def _refresh_share_devices(self):
        self._scan_audio_devices()
        self._rebuild_device_menu()
        self._log('音频设备列表已刷新')

    def _on_share_toggle(self):
        self._refresh_share_info()

    def _on_device_select(self, choice):
        for dev_id, name in self._share_devices:
            if name == choice:
                self._share_device_id = dev_id
                self._log(f'分享设备选择: {name}')
                return
        self._share_device_id = None

    def _rebuild_device_menu(self):
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
        first = self._share_devices[0][1]
        self._share_device_var.set(first)
        self._on_device_select(first)

    def _refresh_share_info(self):
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

    # ======================== 生命周期 ========================
    def start(self):
        GSIHandler.monitor = self
        port = self._config.get('port', 3000)
        self._server = HTTPServer(('127.0.0.1', port), GSIHandler)
        self._start_btn.set_state(tk.DISABLED)
        self._stop_btn.set_state(tk.NORMAL)
        self._update_status('● 服务运行中（等待游戏连接）', MD3.INFO)
        self._log(f'HTTP 服务已启动 http://127.0.0.1:{port}')
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._start_btn.set_state(tk.NORMAL)
        self._stop_btn.set_state(tk.DISABLED)
        self._update_status('● 已停止', MD3.OUTLINE)
        self._log('服务已停止')

    def _reset_kills(self):
        self._kill_count = -1
        self._speed = 1.0
        self._player_dead = False
        self._last_kill_time = 0.0
        self._kill_var.set('击杀数: --')
        self._speed_var.set('速度: 1.0x')
        self._update_status('● 已连接（等待击杀）', MD3.INFO)
        self._log('击杀计数已手动重置，速度重置为 1.0x')

    def _reset_speed(self):
        self._speed = 1.0
        self._speed_var.set('速度: 1.0x')
        self._log('速度已重置为 1.0x')

    def _on_quit(self):
        self._save_config()
        self.stop()
        self._root.destroy()

    def run(self):
        self.start()
        self._root.mainloop()


# ======================== 入口 ========================
if __name__ == '__main__':
    KillMonitor().run()

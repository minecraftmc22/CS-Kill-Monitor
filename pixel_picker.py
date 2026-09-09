# -*- coding: utf-8 -*-
"""
像素坐标拾取工具
移动鼠标到目标位置，按 Space 捕获坐标和颜色，按 Esc 退出。

使用方法:
    python pixel_picker.py

输出示例:
    位置: (500, 300)  颜色: RGB(255, 0, 0)
"""

import tkinter as tk

try:
    import mss
except ImportError:
    mss = None

try:
    import pyautogui
except ImportError:
    pyautogui = None


class PixelPicker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('像素坐标拾取器')
        self.root.geometry('420x200')
        self.root.resizable(False, False)

        # 尝试加载 mss 或 pyautogui
        self._mode = None
        self._sct = None
        if mss is not None:
            self._sct = mss.mss()
            self._mode = 'mss'
        elif pyautogui is not None:
            self._mode = 'pyautogui'
        else:
            self._mode = 'none'

        self._build_ui()
        self._update_loop()

        self.root.bind('<space>', self._capture)
        self.root.bind('<Escape>', lambda e: self._on_quit())
        self.root.protocol('WM_DELETE_WINDOW', self._on_quit)

    def _build_ui(self):
        tk.Label(self.root, text='像素坐标拾取器',
                 font=('Microsoft YaHei', 13, 'bold')).pack(pady=(12, 4))
        tk.Label(self.root, text='移动鼠标到目标位置，按 Space 捕获 | Esc 退出',
                 font=('Microsoft YaHei', 9), fg='gray').pack()

        self._pos_var = tk.StringVar(value='位置: --')
        tk.Label(self.root, textvariable=self._pos_var,
                 font=('Consolas', 14)).pack(pady=(10, 4))

        self._color_var = tk.StringVar(value='颜色: --')
        tk.Label(self.root, textvariable=self._color_var,
                 font=('Consolas', 14)).pack(pady=(0, 2))

        self._color_box = tk.Canvas(self.root, width=40, height=40, bg='black',
                                     highlightthickness=1, highlightbackground='#ccc')
        self._color_box.pack(pady=(2, 4))

        self._log_var = tk.StringVar(value='')
        tk.Label(self.root, textvariable=self._log_var,
                 font=('Microsoft YaHei', 9), fg='green').pack()

        if self._mode == 'none':
            tk.Label(self.root, text='⚠ 需要安装 mss 或 pyautogui\npip install mss',
                     font=('Microsoft YaHei', 9), fg='red').pack()

    def _update_loop(self):
        if self._mode == 'none':
            return

        x, y = self.root.winfo_pointerxy()
        self._pos_var.set(f'位置: ({x}, {y})')

        try:
            color = self._get_pixel(x, y)
            if color:
                self._color_var.set(f'颜色: RGB({color[0]}, {color[1]}, {color[2]})')
                hex_color = f'#{color[0]:02x}{color[1]:02x}{color[2]:02x}'
                self._color_box.configure(bg=hex_color)
        except Exception:
            pass

        self.root.after(100, self._update_loop)

    def _get_pixel(self, x, y):
        if self._mode == 'mss':
            region = {'left': x, 'top': y, 'width': 1, 'height': 1}
            img = self._sct.grab(region)
            return img.pixel(0, 0)
        elif self._mode == 'pyautogui':
            return pyautogui.pixel(x, y)
        return None

    def _capture(self, event):
        x, y = self.root.winfo_pointerxy()
        color = self._get_pixel(x, y) if self._mode != 'none' else None
        if color:
            msg = f'位置: ({x}, {y})  颜色: RGB({color[0]}, {color[1]}, {color[2]})'
            print(f'\n{msg}')
            self._log_var.set(f'已捕获 → {msg}')

            # 复制到剪贴板 (JSON 格式，方便直接粘贴到 config.json)
            clipboard = f'"position": [{x}, {y}], "target_color": [{color[0]}, {color[1]}, {color[2]}]'
            self.root.clipboard_clear()
            self.root.clipboard_append(clipboard)

    def _on_quit(self):
        if self._sct:
            self._sct.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    PixelPicker().run()

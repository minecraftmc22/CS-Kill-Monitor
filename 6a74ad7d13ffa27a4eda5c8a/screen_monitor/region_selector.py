# -*- coding: utf-8 -*-
"""
区域框选工具
在屏幕上拖拽鼠标框选一个矩形区域，松开后输出坐标和尺寸。

使用方法:
    python region_selector.py

操作:
    拖拽鼠标 → 框选目标区域
    Esc      → 取消并退出
    选中后坐标自动复制到剪贴板
"""

import tkinter as tk


class RegionSelector:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('区域框选')

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # 全屏半透明画布
        self.canvas = tk.Canvas(self.root, width=sw, height=sh,
                                 bg='black', highlightthickness=0)
        self.canvas.pack()

        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.35)
        self.root.geometry(f'{sw}x{sh}+0+0')

        self._start_x = 0
        self._start_y = 0
        self._rect_id = None

        self.canvas.bind('<ButtonPress-1>', self._on_press)
        self.canvas.bind('<B1-Motion>', self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.root.bind('<Escape>', lambda e: self.root.destroy())

        # 提示文字
        self.canvas.create_text(sw // 2, sh // 2,
                                text='拖拽鼠标框选监控区域\n按 Esc 取消',
                                fill='white', font=('Microsoft YaHei', 16),
                                justify='center')

    def _on_press(self, event):
        self._start_x = event.x
        self._start_y = event.y
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        self._rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline='#00ff88', width=2, dash=(6, 3)
        )

    def _on_drag(self, event):
        if self._rect_id:
            self.canvas.coords(self._rect_id,
                                self._start_x, self._start_y, event.x, event.y)

    def _on_release(self, event):
        x1, y1 = min(self._start_x, event.x), min(self._start_y, event.y)
        x2, y2 = max(self._start_x, event.x), max(self._start_y, event.y)
        w, h = x2 - x1, y2 - y1

        if w < 5 or h < 5:
            return  # 太小，忽略

        region = f'"region": {{"left": {x1}, "top": {y1}, "width": {w}, "height": {h}}}'
        print(f'\n框选区域: left={x1} top={y1} width={w} height={h}')
        print(f'config 配置:\n  {region}')

        self.root.clipboard_clear()
        self.root.clipboard_append(region)

        self.root.after(500, self.root.destroy)


if __name__ == '__main__':
    RegionSelector().root.mainloop()

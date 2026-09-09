# -*- coding: utf-8 -*-
"""
屏幕监控工具测试脚本
模拟屏幕监控触发，用于测试配置和效果
"""

import time
import json
import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import threading

# 导入屏幕监控主程序
try:
    from screen_monitor import ScreenMonitor
except ImportError:
    # 如果不在同一目录，尝试添加路径
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from screen_monitor import ScreenMonitor


class TestMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("屏幕监控测试工具")
        self.root.geometry("400x350")
        self.root.resizable(False, False)

        # 配置文件路径
        self.config_path = "config.json"
        if len(sys.argv) > 1:
            self.config_path = sys.argv[1]

        # 状态变量
        self.monitor = None
        self.test_running = False

        # 构建UI
        self._build_ui()

        # 加载配置
        self._load_config()

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # 标题
        tk.Label(self.root, text="屏幕监控测试工具", 
                font=("Microsoft YaHei", 14, "bold")).pack(pady=10)

        # 配置文件信息
        config_frame = tk.Frame(self.root)
        config_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(config_frame, text="配置文件:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.config_var = tk.StringVar(value=self.config_path)
        tk.Label(config_frame, textvariable=self.config_var, 
                font=("Consolas", 10), fg="blue").pack(side=tk.LEFT, padx=5)

        # 触发器数量
        self.triggers_frame = tk.Frame(self.root)
        self.triggers_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(self.triggers_frame, text="监控目标:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.triggers_count_var = tk.StringVar(value="加载中...")
        tk.Label(self.triggers_frame, textvariable=self.triggers_count_var, 
                font=("Consolas", 10), fg="green").pack(side=tk.LEFT, padx=5)

        # 控制按钮
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)

        self.start_btn = tk.Button(control_frame, text="启动监控", width=12, 
                                  command=self.start_monitor, font=("Microsoft YaHei", 10))
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = tk.Button(control_frame, text="停止监控", width=12, 
                                 command=self.stop_monitor, state=tk.DISABLED, 
                                 font=("Microsoft YaHei", 10))
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 测试按钮
        test_frame = tk.Frame(self.root)
        test_frame.pack(pady=10)

        self.test_btn = tk.Button(test_frame, text="模拟触发", width=12, 
                                 command=self.simulate_trigger, state=tk.DISABLED, 
                                 font=("Microsoft YaHei", 10))
        self.test_btn.pack(side=tk.LEFT, padx=5)

        tk.Button(test_frame, text="选择配置", width=12, 
                 command=self.select_config, font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=5)

        # 日志区域
        log_frame = tk.LabelFrame(self.root, text="测试日志", font=("Microsoft YaHei", 10))
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.log_text = tk.Text(log_frame, height=8, font=("Consolas", 9), wrap=tk.WORD)
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 添加初始日志
        self.add_log("测试工具已启动")
        self.add_log(f"当前配置文件: {self.config_path}")

    def _load_config(self):
        """加载配置文件并显示信息"""
        try:
            if not os.path.exists(self.config_path):
                self.add_log(f"配置文件不存在: {self.config_path}")
                self.triggers_count_var.set("0")
                return

            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            triggers = config.get('triggers', [])
            self.triggers_count_var.set(str(len(triggers)))

            self.add_log(f"配置文件加载成功，共 {len(triggers)} 个监控目标")

            # 显示前三个触发器的名称
            for i, trigger in enumerate(triggers[:3]):
                name = trigger.get('name', f'触发器{i+1}')
                ttype = trigger.get('type', 'pixel')
                if ttype == 'pixel':
                    pos = trigger.get('position', [0, 0])
                    self.add_log(f"  - {name}: 像素({pos[0]}, {pos[1]})")
                else:
                    region = trigger.get('region', {})
                    self.add_log(f"  - {name}: 区域({region.get('left', 0)}, {region.get('top', 0)}, "
                                f"{region.get('width', 0)}x{region.get('height', 0)})")

            if len(triggers) > 3:
                self.add_log(f"  ... 还有 {len(triggers)-3} 个触发器")

        except Exception as e:
            self.add_log(f"加载配置文件失败: {str(e)}")
            self.triggers_count_var.set("0")

    def add_log(self, message):
        """添加日志"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def start_monitor(self):
        """启动监控"""
        if not os.path.exists(self.config_path):
            messagebox.showerror("错误", f"配置文件不存在: {self.config_path}")
            return

        try:
            self.add_log("正在启动监控...")
            self.monitor = ScreenMonitor(self.config_path)

            # 在后台线程中运行监控
            self.monitor_thread = threading.Thread(target=self.monitor.run, daemon=True)
            self.monitor_thread.start()

            # 更新UI状态
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.test_btn.config(state=tk.NORMAL)
            self.add_log("监控已启动")

            # 自动开始监控
            self.monitor.start()

        except Exception as e:
            self.add_log(f"启动监控失败: {str(e)}")
            messagebox.showerror("错误", f"启动监控失败: {str(e)}")

    def stop_monitor(self):
        """停止监控"""
        if self.monitor:
            self.monitor.stop()
            self.monitor = None

            # 更新UI状态
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.test_btn.config(state=tk.DISABLED)
            self.add_log("监控已停止")

    def simulate_trigger(self):
        """模拟触发事件"""
        if not self.monitor:
            return

        try:
            # 模拟触发第一个触发器
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            triggers = config.get('triggers', [])
            if not triggers:
                self.add_log("没有可用的触发器")
                return

            # 选择第一个触发器进行模拟
            trigger = triggers[0]
            self.add_log(f"模拟触发: {trigger.get('name', '未命名')}")

            # 在主线程中调用触发处理函数
            self.monitor._handle_trigger(trigger)

        except Exception as e:
            self.add_log(f"模拟触发失败: {str(e)}")

    def select_config(self):
        """选择配置文件"""
        from tkinter import filedialog

        file_path = filedialog.askopenfilename(
            title="选择配置文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )

        if file_path:
            self.config_path = file_path
            self.config_var.set(file_path)
            self._load_config()

    def _on_close(self):
        """关闭窗口"""
        self.stop_monitor()
        self.root.destroy()

    def run(self):
        """运行测试工具"""
        self.root.mainloop()


if __name__ == "__main__":
    app = TestMonitor()
    app.run()

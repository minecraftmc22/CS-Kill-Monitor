# CSGO Kill Monitor — Material Design 3

> CSGO 击杀实时监控 — 击杀时弹出图片 + 变速变调音频 + 击杀日志

原作者: [libi2009](https://github.com/libi2009)
现作者: [Minecraftmc22](https://github.com/minecraftmc22)
License: MIT

## 功能

### 核心功能
- **GSI 实时监测** — 通过 CSGO Game State Integration 获取实时击杀数据
- **击杀弹图** — 每次击杀全屏弹出图片（无边框，强制置顶，可调透明度）
- **变速变调音频** — 击杀音频每杀加速 0.1x（速度 + 音调同步升高）
- **击杀日志** — 所有击杀记录写入日志文件
- **音频分享** — 支持双路音频输出，击杀音效可分享给队友（需虚拟声卡）
- **开关控制** — 独立开关控制图片/音频的播放

### 新增功能 (MD3 版)
- **图片库管理** — 支持 `images/` 文件夹批量管理图片
- **音频库管理** — 支持 `audio/` 文件夹批量管理音频
- **播放顺序** — 循环 / 随机 / 重复（图片和音频独立设置）
- **图片透明度** — 可调节弹图透明度 (0% - 100%)
- **全局音量** — 可调节所有音频的音量 (0% - 100%)
- **单独音量** — 可对每个音频文件单独设置音量
- **素材预览** — 图片列表显示缩略图，音频列表支持逐条试听
- **图片-音频绑定** — 为特定图片指定专属音频（不受随机/循环影响），绑定窗口显示图片缩略图
- **图片显示效果** — 支持抖动、渐显/出、闪动；全局可随机或指定，也可为图片绑定专属效果
- **鼠标穿透** — 全屏图片不占用鼠标，点击穿透到游戏
- **缓存整理** — 音频格式转换和变速缓存统一保存到 `AudioTemp/` 文件夹
- **配置管理** — 配置默认保存到 `%AppData%/Minecraftmc22/csgo_kill_monitor/Config.json`
- **导入/导出** — 支持导入导出 JSON 配置文件
- **Material Design 3** — 全新 MD3 暗色主题界面

## 环境要求

- Python 3.10+
- Windows（目前仅支持 Windows）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 准备素材

将图片放入 `images/` 文件夹，音频放入 `audio/` 文件夹：

```
screen_monitor/
├── images/          ← 图片库
│   ├── image1.jpg
│   ├── image2.png
│   └── ...
├── audio/           ← 音频库
│   ├── sound1.mp3
│   ├── sound2.wav
│   └── ...
├── AudioTemp/        ← 音频转换与变速缓存（运行时自动创建）
└── csgo_kill_monitor.py
```

**支持格式:**
- 图片: `.jpg` `.jpeg` `.png` `.gif` `.bmp` `.webp`
- 音频: `.mp3` `.wav` `.m4a` `.flac` `.ogg` `.wma` `.aac`（非 WAV 自动转换）

### 3. 配置 CSGO GSI

将 `gamestate_integration_kill_monitor.cfg` 复制到 CSGO 配置目录：

```
Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg/
```

### 4. 运行

```bash
python csgo_kill_monitor.py
```

启动后点击主界面的 **▶ 启动服务**，进入 CSGO 即可。

---

## 界面说明

### 主界面

| 控件 | 说明 |
|------|------|
| 击杀数 | 当前对局击杀数 |
| 速度 | 当前音频播放倍率（每杀 +0.1x） |
| 播放图片 | 开关击杀弹图 |
| 播放音频 | 开关击杀音效 |
| 分享音频到麦克风 | 开启双路输出（需虚拟声卡） |
| 目标设备 | 选择音频分享的目标设备 |
| ⟳ | 刷新设备列表 |
| 重置计数 | 重置换局（击杀数 + 速度归零） |
| 重置速度 | 仅重置速度到 1.0x |

### 设置

| 设置项 | 说明 |
|--------|------|
| 图片库路径 | 图片文件夹路径（默认: `images/`） |
| 图片预览列表 | 查看图片缩略图与文件名 |
| 图片播放顺序 | 循环 / 随机 / 重复 |
| 图片透明度 | 0% - 100% |
| 全屏图片鼠标穿透 | 开启后图片不占用鼠标 |
| 音频库路径 | 音频文件夹路径（默认: `audio/`） |
| 音频预览列表 | 查看音频清单并逐条试听（1.0 倍速） |
| 音频播放顺序 | 循环 / 随机 / 重复 |
| 全局音量 | 0% - 100% |
| 单独音量设置 | 为每个音频单独设置音量 |
| 图片-音频绑定 | 为特定图片指定专属音频，窗口显示缩略图 |
| 效果设置 | 全局随机或指定抖动、渐显/出、闪动效果 |
| 图片-效果绑定 | 为图片绑定专属效果，不受全局随机影响 |
| 游戏日志路径 | 日志文件路径 |
| 配置保存地址 | 配置文件保存路径 |
| 导入/导出配置 | JSON 格式配置文件导入导出 |

---

## 播放顺序说明

| 模式 | 行为 |
|------|------|
| 循环 (loop) | 按文件名顺序依次播放，到末尾后从头开始 |
| 随机 (random) | 每次随机选择一个文件播放 |
| 重复 (repeat) | 始终播放第一个文件 |

> **图片-音频绑定**: 为特定图片指定的音频不受播放顺序影响，始终使用绑定的音频。

> **图片-效果绑定**: 为特定图片指定的效果优先级最高，不受全局随机或指定效果影响。

## 音频缓存

播放非 WAV 音频时，程序会先转换为 WAV；击杀后的变速变调音频也会生成缓存。两类文件都会保存在项目根目录的 `AudioTemp/` 文件夹中，该文件夹会在程序启动时自动创建。

---

## 音频分享（队友可听）

让队友听到你的击杀音效。

### 安装虚拟声卡

1. 下载安装 [VB-Cable](https://vb-audio.com/Cable/)（免费）
2. 重启电脑

### 配置

1. 打开监控 → 开启「分享音频到麦克风」
2. 下拉菜单选择 `CABLE Input [虚拟]`（点 ⟳ 刷新）
3. CSGO 音频设置 → 麦克风选 **CABLE Output**
4. Windows 声音设置 → 录制 → 你的真实麦克风 → 属性 → 侦听 → 勾选「侦听此设备」→ 播放设备选 **CABLE Input**

> 这样队友能同时听到你的说话声 + 击杀音效。

---

## 配置文件

配置默认保存位置：

```
%AppData%/Minecraftmc22/csgo_kill_monitor/Config.json
```

配置结构：

```json
{
    "port": 3000,
    "display_duration": 1000,
    "pip": {
        "fullscreen": true,
        "alpha": 0.9,
        "click_through": true
    },
    "image": {
        "library_path": "images",
        "playback_order": "loop",
        "alpha": 0.9
    },
    "audio": {
        "library_path": "audio",
        "playback_order": "loop",
        "global_volume": 100,
        "per_audio_volume": {},
        "image_audio_map": {}
    },
    "effect": {
        "mode": "random",
        "selected_effect": "shake",
        "image_effect_map": {}
    },
    "log_path": "kill_log.txt",
    "config_path": ""
}
```

---

## 功能测试

| 脚本 | 用途 |
|------|------|
| `test_share_audio.py` | 测试双路音频输出 |
| `test_audio.py` | 测试音频播放 |
| `test_demo.py` | 模拟击杀触发 |
| `pixel_picker.py` | 屏幕像素坐标拾取 |
| `region_selector.py` | 屏幕区域框选 |

---

## 项目结构

```
screen_monitor/
├── csgo_kill_monitor.py         # 主程序（GSI 击杀监控 MD3 版）
├── screen_monitor.py            # 屏幕像素/区域监控（备用）
├── config.json                   # 旧配置文件（自动迁移）
├── requirements.txt              # Python 依赖
├── gamestate_integration_kill_monitor.cfg  # CSGO GSI 配置
├── images/                       # 图片库（默认）
├── audio/                        # 音频库（默认）
├── AudioTemp/                    # 音频转换和变速缓存（运行时生成）
├── pixel_picker.py               # 像素坐标拾取工具
├── region_selector.py            # 区域框选工具
├── test_audio.py                 # 音频测试
├── test_demo.py                  # 模拟测试
├── test_share_audio.py           # 音频分享测试
└── kill_log.txt                  # 击杀日志（运行时生成）
```

## License

MIT

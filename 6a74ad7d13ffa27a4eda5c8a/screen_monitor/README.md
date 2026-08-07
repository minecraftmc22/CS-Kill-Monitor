# CSGO Kill Monitor

> CSGO 击杀实时监控 — 击杀时弹出图片 + 变速变调音频 + 击杀日志

## 功能

- **GSI 实时监测** — 通过 CSGO Game State Integration 获取实时击杀数据
- **击杀弹图** — 每次击杀全屏弹出图片（无边框，强制置顶，可调透明度）
- **变速变调音频** — 击杀音频每杀加速 0.1x（速度 + 音调同步升高）
- **击杀日志** — 所有击杀记录写入 `kill_log.txt`
- **音频分享** — 支持双路音频输出，击杀音效可分享给队友（需虚拟声卡）
- **开关控制** — 独立开关控制图片/音频的播放

## 环境要求

- Python 3.10+
- Windows（目前仅支持 Windows）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 准备素材

将你的**图片**和**音频文件**放到项目目录下，默认配置为：

| 配置项 | 默认值 |
|--------|--------|
| 音频文件 | `lv_0_20260807010020.mp3` |
| 图片文件 | `980d5eff3a1143f38fa06ea431778013.jpg` |
| GSI 端口 | `3000` |

> 音频支持 MP3 / M4A / WAV，启动时自动转为 WAV。

可在 `config.json` 中修改：

```json
{
    "port": 3000,
    "audio_path": "你的音频.mp3",
    "image_path": "你的图片.jpg",
    "display_duration": 1000,
    "pip": {
        "fullscreen": true,
        "alpha": 0.9
    }
}
```

### 3. 配置 CSGO GSI

将 `gamestate_integration_kill_monitor.cfg` 复制到 CSGO 配置目录：

```
E:\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\
```

### 4. 运行

```bash
python csgo_kill_monitor.py
```

启动后点击界面上的 **▶ 启动服务**，进入 CSGO 即可。

---

## 界面说明

| 控件 | 说明 |
|------|------|
| 击杀数 | 当前对局击杀数 |
| 速度 | 当前音频播放倍率 |
| 播放图片 | 开启/关闭击杀弹图 |
| 播放音频 | 开启/关闭击杀音效 |
| 分享音频到麦克风 | 开启双路输出（需虚拟声卡） |
| 目标设备 | 选择音频分享的目标设备 |
| ⟳ | 刷新设备列表 |
| 重置计数 | 重置换局（击杀数 + 速度归零） |
| 重置速度 | 仅重置速度到 1.0x |

---

## 音频分享（队友可听）

让队友听到你的击杀音效。

### 安装虚拟声卡

1. 下载安装 [VB-Cable](https://vb-audio.com/Cable/)（免费）
2. 重启电脑

### 配置

1. 打开监控 → 勾选「分享音频到麦克风」
2. 下拉菜单选择 `CABLE Input [虚拟]`（点 ⟳ 刷新）
3. CSGO 音频设置 → 麦克风选 **CABLE Output**
4. Windows 声音设置 → 录制 → 你的真实麦克风 → 属性 → 侦听 → 勾选「侦听此设备」→ 播放设备选 **CABLE Input**

> 这样队友能同时听到你的说话声 + 击杀音效。

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
├── csgo_kill_monitor.py         # 主程序（GSI 击杀监控）
├── screen_monitor.py            # 屏幕像素/区域监控（备用）
├── config.json                  # 配置文件
├── requirements.txt             # Python 依赖
├── gamestate_integration_kill_monitor.cfg  # CSGO GSI 配置
├── pixel_picker.py              # 像素坐标拾取工具
├── region_selector.py           # 区域框选工具
├── test_audio.py                # 音频测试
├── test_demo.py                 # 模拟测试
├── test_share_audio.py          # 音频分享测试
└── kill_log.txt                 # 击杀日志（运行时生成）
```

## License

MIT

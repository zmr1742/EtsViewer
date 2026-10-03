# EtsViewer

一个简洁高效的 ETS（英语听说考试系统）考试内容查看器，支持美观格式化输出、图片预览、音频播放和多格式导出。

> 本项目 Fork 自 [Maicy0609/EtsViewer](https://github.com/Maicy0609/EtsViewer)（原 [hite4044/EtsContentViewer](https://github.com/hite4044/EtsContentViewer)），在原基础上增强了图片预览、音频播放、HTML/PNG 导出等功能。

## 功能特性

### 基础功能（继承自原项目）
- 📁 **自动识别** - 自动查找 `%APPDATA%` 下的 ETS 数据目录
- 🎨 **美观输出** - 将 JSON 内容格式化为易读的文本，支持 7 种题型
- 📝 **多题型支持** - 角色扮演、图片描述、听力选择、阅读理解、问答短文、对话复述、词汇问答
- ⌨️ **快捷操作** - Ctrl + 方向键翻页、Ctrl + 滚轮缩放字体、点击标题切换题目

### 增强功能（本 Fork 新增）
- 🖼️ **图片预览** - 听录音选图片题型自动显示 A/B/C 选项图片，正确答案绿色高亮 + ✓
- 🎵 **音频播放** - 基于 Windows MCI 播放 MP3，支持逐题切换；播放进度条可拖动跳转
- 🔊 **音量控制** - 基于 Core Audio API 控制进程音量，实时生效，带百分比显示
- 📄 **TXT 导出** - 导出整卷内容为纯文本（原功能增强）
- 🌐 **HTML 导出** - 导出整卷为单文件 HTML，图片 base64 内嵌、音频相对路径引用
  - 内嵌交互：深浅色主题、显示答案开关、听力原文 W/M 分行折叠、答案展开/收起、搜索过滤高亮、核对勾选 + localStorage 持久化
  - 题型自动细分：听句子选择图片 / 听对话选择 / 听句子选择 等
- 🖼️ **PNG 导出** - 当前内容渲染为 PNG 图片，正确答案高亮，方便分享
- ℹ️ **关于菜单** - 菜单栏新增「帮助」→「关于」，展示项目信息

## 安装

```bash
pip install -r requirements.txt
```

> Python 3.13 需使用 `wxPython >= 4.2.3`，4.2.2 无对应 wheel。

## 使用方法

1. 运行 `python main.py` 启动程序
2. 菜单「操作」→「自动选择文件夹」加载 ETS 数据目录（或手动「打开文件夹」）
3. 左侧列表选择试卷，右侧查看内容
4. 选项栏操作：
   - **启用美观输出** / **显示完整答案**：控制显示格式
   - **导出为TXT** / **导出为HTML** / **导出为PNG**：三种导出格式
   - **音频下拉 + 播放**：选择并播放题目音频
   - **音量滑块**：调节播放音量（带百分比）
5. 底部播放控制：进度条可拖动跳转，时间显示当前/总时长

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + ←` | 上一条内容 |
| `Ctrl + →` | 下一条内容 |
| `Ctrl + 滚轮` | 调整字体大小 |
| 点击目录标题 | 快速切换题目 |

## 项目结构

```
EtsViewer/
├── main.py           # 程序入口、主窗口、菜单栏（含关于对话框）
├── widgets.py        # 自定义控件（列表视图、JSON查看器、图片预览、音频播放）
├── formatters.py     # JSON 格式化（7种题型）+ 音频/图片信息提取
├── html_export.py    # HTML 单文件导出（内嵌 CSS/JS，对齐模板视觉风格）
├── png_export.py     # PNG 图片导出（wx.MemoryDC 渲染）
├── utils.py          # 字体缓存、HTML清理、AudioPlayer（MCI）、VolumeController（Core Audio）
├── requirements.txt  # 依赖列表
└── photos/           # README 截图
```

## 依赖

- wxPython >= 4.2.3（GUI 框架）
- six

仅支持 **Windows**（依赖 `ctypes.windll`、MCI、Core Audio API）。

## 从源码构建 exe

```bash
pip install pyinstaller
python -m PyInstaller --onefile --noconsole --name EtsViewer main.py
```

生成的单文件位于 `dist/EtsViewer.exe`。

## License

MIT

# Moepet - 萌系桌面宠物

基于 [PySide6](https://doc.qt.io/qtforpython-6/) 的 Windows 桌面宠物应用。将喜欢的角色立绘放到桌面上，支持拖拽、立绘切换、动画演出、系统托盘，以及通过 OpenAI 兼容 API 进行 AI 对话。

> 当前内置角色：诺瓦（`noir`），来源《星空列车与白的旅行》。请仅使用你有权使用的角色素材。

## 功能

- 透明、无边框、可置顶的桌面宠物窗口
- 左键拖拽移动；短按立绘切换下一张表情
- 立绘淡入淡出和弹跳、摇摆、震动、放大缩小等演出动画
- 支持扫描多个角色目录，并从右键菜单切换角色
- Galgame 风格对话窗口，支持逐字显示和流式 AI 回复
- 支持 DeepSeek、OpenAI、Ollama 等 OpenAI Chat Completions 兼容接口
- 对话历史按角色保存到本地，支持系统托盘、位置记忆和设置窗口

## 快速开始

### 环境要求

- Python 3.10 或更高版本
- Windows（当前窗口与托盘交互主要面向 Windows）

### 安装与启动

```powershell
git clone https://github.com/zhuge-Tom/moepet.git
cd moepet
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6
python main.py
```

如果 PowerShell 阻止激活脚本，可直接使用虚拟环境解释器：

```powershell
.\.venv\Scripts\python.exe -m pip install PySide6
.\.venv\Scripts\python.exe main.py
```

## 使用说明

- 左键拖拽宠物以移动位置；轻点立绘切换下一张图片。
- 右键宠物可切换角色、打开对话框、进入设置或退出。
- 托盘图标双击可打开设置，也可重置宠物位置。
- 在“设置 -> AI 模型”中填写 Base URL、API Key 和模型名称；开启流式输出即可逐段显示回复。
- 在“设置 -> 角色设置”中调整角色提示词，或打开立绘目录管理 PNG 文件。

## AI 配置示例

Moepet 调用 OpenAI Chat Completions 兼容接口。若 Base URL 未包含 `/chat/completions`，程序会自动补全该路径。

| 服务 | Base URL 示例 | 模型示例 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Ollama | `http://localhost:11434/v1` | 本地已下载的模型名 |

API Key 通过设置窗口保存在本机的 `config.json` 中。该文件已被 `.gitignore` 忽略：不要将密钥提交到 Git，也不要在截图或日志中暴露它。若密钥已经泄露，请立即到服务商控制台轮换。

## 添加角色和立绘

每个角色是 `characters/` 下包含 `config.json` 的一个子目录。程序会自动读取该目录 `sprites/` 内的所有 PNG 文件；文件名即为立绘名称。

```text
characters/
└── my_character/
    ├── config.json
    ├── sprites/
    │   ├── idle.png
    │   └── happy.png
    └── animations.json       # 可选
```

最小角色配置示例：

```json
{
  "name": "角色显示名",
  "name_en": "my_character",
  "source": "作品来源",
  "scale": 0.5,
  "sprites": {
    "idle": "idle.png",
    "happy": "happy.png"
  }
}
```

`sprites` 字段用于保存角色的语义映射；实际可显示的图片以 `sprites/` 中存在的 `.png` 文件为准。

## 项目结构

```text
moepet/
├── main.py                  # Qt 应用入口
├── pet_manager.py           # 窗口、角色、对话和设置的顶层协调器
├── core/
│   ├── animation.py         # 立绘动画
│   ├── character.py         # 角色及立绘加载
│   ├── config.py            # 全局配置和默认值
│   ├── llm_service.py       # OpenAI 兼容 LLM 服务
│   └── signals.py           # 全局信号总线
├── ui/
│   ├── pet_window.py        # 桌宠透明窗口与右键菜单
│   ├── dialog_window.py     # Galgame 风格对话窗口
│   ├── settings_window.py   # 设置窗口
│   ├── tray_icon.py         # 系统托盘
│   └── theme.py             # QSS 主题
└── characters/
    └── noir/                # 内置角色资源和配置
```

## 本地数据

以下文件由程序在本地创建或更新，均不会提交到仓库：

- `config.json`：窗口、AI 和角色提示词设置
- `characters/*/chat_history.json`：按角色保存的对话历史

删除这些文件即可分别恢复默认设置或清空对话记录。

## 路线图

- [ ] TTS 语音合成与角色音色配置
- [ ] ASR 语音输入
- [ ] 更完善的角色接口与表情联动
- [ ] 自动待机动画和粒子特效
- [ ] 更多角色与立绘资源管理能力

## 致谢

- [PySide6](https://doc.qt.io/qtforpython-6/)
- 所有为本项目提供灵感的桌宠和视觉小说作品

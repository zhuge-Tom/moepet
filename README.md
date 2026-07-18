# Moepet

基于 [PySide6](https://doc.qt.io/qtforpython-6/) 的 Windows 2D 桌面宠物。它支持 PNG 帧动画、OpenAI 兼容聊天、本地角色资料库、主动屏幕识别，以及可选的本地语音能力。

> 内置角色为 Noir，素材来源《星空列车与白的旅行》。请只导入你拥有使用权的角色素材、参考音频和资料。

## 功能

- 透明、无边框、可置顶的桌宠；拖拽定位、立绘切换、托盘与多角色切换。
- 基于 `animations.json` 的 PNG 帧状态：`idle`、`think`、`happy`、`speak` 等；单 PNG 角色保持兼容。
- Galgame 风格聊天窗口，支持流式回复、逐字显示、缩放和可调显示速度。
- 支持 DeepSeek、OpenAI、Ollama 等 OpenAI Chat Completions 兼容 API。
- 角色资料库：导入世界观、角色设定、对话示例；角色设定固定约束人格，其余资料按问题检索。
- 屏幕理解：聊天输入“识别屏幕”“看屏幕”或使用全局快捷键；可选随机主动观察会先要求明确授权，云端视觉模型失败时手动识图回退本地 OCR。
- 按住说话：按住全局快捷键录音、松开后转写并可自动发送；支持本地 faster-whisper 或 OpenAI 兼容 ASR。
- 语音朗读：支持本地 CosyVoice 音色克隆或 OpenAI 兼容云端 TTS；模型与依赖由用户自行配置。

## 快速开始

需要 Windows 与 Python 3.10+：

```powershell
git clone https://github.com/zhuge-Tom/moepet.git
cd moepet
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6
python main.py
```

PowerShell 无法激活虚拟环境时：

```powershell
.\.venv\Scripts\python.exe -m pip install PySide6
.\.venv\Scripts\python.exe main.py
```

## 配置聊天模型

在“设置 -> AI 模型”中填写 Base URL、API Key 和模型名称，点击“应用”或“确定”后即可聊天。Base URL 未包含 `/chat/completions` 时会自动补全。

| 服务 | Base URL 示例 | 模型示例 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Ollama | `http://localhost:11434/v1` | 本地模型名 |

程序优先将密钥写入 Windows 凭据管理器；没有可用的 `keyring` 时，会保存到本机 `config.json`。该文件已被 Git 忽略，绝不要提交、截图或分享 API Key。

## 角色资料库

打开“设置 -> 角色设置 -> 角色资料库”，先选择资料类型再导入 `TXT`、`Markdown` 或 `JSON`：

- `世界观 / 背景`：地点、规则、组织与环境；聊天时按相关性检索。
- `角色设定`：性格、身份、边界与关系；每轮固定加入系统提示词。
- `对话示例`：用户与角色的高质量问答；按相关性作为语气示范。

文件会复制到当前角色目录，路径与类型一一对应：

```text
characters/noir/knowledge/sources/
├── world/
├── character/
└── dialogue/
```

无需维护章节、好感度或剧情状态；资料库服务于自由对话。

仓库 `datasets/` 提供 Noir 的可选示例资料：

- `noir_world_background.md`
- `noir_character_profile.md`
- `noir_dialogue_examples.json`

## 屏幕、识图与语音

“设置 -> 通用设置”的控制中心会汇总聊天、朗读、按住说话、识图的准备状态，并可直接跳转对应配置页。

“设置 -> 屏幕识别”中可设置全局截图快捷键，默认 `Ctrl+Alt+O`。手动截图仅由聊天意图或快捷键触发；启用并配置视觉服务时优先图像理解，否则使用本地 OCR。主动观察默认关闭：开启后，角色会在指定的随机间隔内截图、理解内容并作出一次简短回应。它需要先配置视觉模型；云端服务还必须在“图像理解”页明确同意上传截图。截图会在处理后删除，除非启用了“保留截图”。

“设置 -> 语音输入”中可开启按住说话（默认 `Ctrl+Alt+Space`）：按下快捷键开始录音，松开后转写；默认会自动发给角色。录音仅在按键按住期间采集，临时 WAV 会在识别结束或失败后删除。

安装可选依赖：

```powershell
python -m pip install -r requirements-optional.txt
```

- OCR 使用 `rapidocr-onnxruntime`。
- 快捷键使用 `keyboard`。
- ASR 使用用户配置的 `faster-whisper` 模型，CPU 默认 `int8`。
- TTS 使用用户自行安装与配置的 CosyVoice 模型、且仅可使用获得授权的参考音频。

## 添加角色与动画

每个角色是 `characters/` 下包含 `config.json` 的目录。`sprites/` 下的 PNG 会自动加载；`animations.json` 可定义帧状态。

```text
characters/my_character/
├── config.json
├── sprites/
│   ├── idle.png
│   └── speak_1.png
└── animations.json
```

`animations.json` 示例：

```json
{
  "idle": {"frames": ["idle.png"], "frame_ms": 500, "loop": true},
  "speak": {"frames": ["speak_1.png", "idle.png"], "frame_ms": 160, "loop": true}
}
```

## 本地数据

- `config.json`：窗口、模型、快捷键、提示词设置与本地密钥回退。
- `characters/*/chat_history.json`：按角色保存的聊天记录。
- `characters/*/knowledge/`：用户导入资料与运行时索引。

以上均不应提交到仓库。删除 `config.json` 可恢复默认设置；删除聊天记录可清空对应角色的历史。

## 项目结构

```text
moepet/
├── core/          # 配置、角色、LLM、资料库、OCR/TTS/ASR/视觉服务
├── ui/            # 桌宠、对话框、设置与托盘
├── characters/    # 角色资源
├── datasets/      # 可选导入资料示例
├── tools/         # 数据集转换脚本
└── requirements-optional.txt
```

## 致谢

- [PySide6](https://doc.qt.io/qtforpython-6/)
- 所有为本项目提供灵感的桌宠与视觉小说作品

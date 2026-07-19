# Moepet

Moepet 是一个基于 PySide6 的 Windows 桌面角色伴侣。它将透明立绘、聊天、角色资料、屏幕理解和可选的语音输入/输出组合在一个轻量桌面应用中。

默认角色为 Noir。请只使用你拥有合法使用权的角色素材、参考音频、训练权重和资料。

## 功能

- 透明无边框立绘，支持置顶、拖动、多角色切换和 PNG 帧动画。
- 双击立绘显示或关闭聊天框；聊天框自动位于立绘上方。
- OpenAI Chat Completions 兼容聊天服务，支持 DeepSeek、OpenAI、Ollama 等。
- 大字号 Galgame 风格聊天界面，支持流式显示与简短纯对话输出。
- 角色资料库：导入世界观、角色设定和对话示例，按相关性辅助回复。
- 屏幕理解：手动识图或授权后的定时观察；优先使用视觉模型，失败时可回退本地 OCR。
- 按住说话：支持本地 faster-whisper 或 OpenAI 兼容 ASR。
- GPT-SoVITS 语音：聊天框保留中文，后台翻译为日文后以角色音色输出连续语音。

## 快速开始

需要 Windows 和 Python 3.10+。

```powershell
git clone https://github.com/zhuge-Tom/moepet.git
cd moepet
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install PySide6 PySide6-Addons
.\.venv\Scripts\python.exe main.py
```

首次运行后，双击右下角立绘打开聊天框，在“设置 -> AI 模型”填写聊天服务。

## 聊天服务配置

Moepet 使用 OpenAI Chat Completions 格式。设置页填写 Base URL、模型名与 API Key；地址不含 `/chat/completions` 时会自动补全。

| 服务 | Base URL 示例 | 模型示例 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Ollama | `http://localhost:11434/v1` | `qwen3:8b` |

密钥优先保存在系统凭据管理器中。运行时 `config.json` 已被 Git 忽略，不应提交或分享。

## 语音输出：GPT-SoVITS

在“设置 -> 语音输出”中启用“LLM 回复后自动朗读”，选择远端 GPT-SoVITS API，并填写：

- 服务地址：GPT-SoVITS API 的根地址，例如 `https://your-host.example`。不要填写 `/v2`；程序会调用 `/tts`。
- 服务器参考音频路径：API 所在服务器上的绝对路径。
- 角色参考台词：与参考音频对应的日文文本，保存在角色 `config.json` 的 `voice.reference_text`。

语音链路为：中文角色回复 -> 日文翻译 -> GPT-SoVITS 合成 -> 本机播放。整段回复会合成为一个 WAV；句号会保留为自然短暂停顿。

远端 API 应兼容 GPT-SoVITS `api_v2.py` 的 `/tts` 接口，并接受 `text`、`text_lang`、`ref_audio_path`、`prompt_text` 与 `prompt_lang` 字段。远端 API Key 可留空，除非你的网关另有鉴权要求。

### 本地 GPT-SoVITS v2Pro（CPU）

本地模式适合已准备好 GPT-SoVITS 项目、权重与角色参考音频的 Windows 环境。CPU 推理可用，但首次加载与合成会比 GPU 明显更慢，建议空闲内存至少 12 GB，并将 Windows 分页文件留出 16 GB 或更多的空间。

1. 准备 GPT-SoVITS 项目，例如 `G:\GPT-SoVITS-v2pro-20250604-nvidia50`。
2. 将 GPT 权重放入 `GPT_weights_v2Pro\`，将 SoVITS 权重放入 `SoVITS_weights_v2Pro\`。例如 Noir 使用 `noir-e15.ckpt` 与 `noir_e8_s968.pth`。
3. 将获得授权的参考音频放入 `characters/noir/voice/` 目录，例如 `noi0287.wav`。该目录下的音频已被 Git 忽略，不会被提交。
4. 在角色 `config.json` 的 `voice.reference_audio` 中填写文件名（不含路径），并保留与录音对应的 `voice.reference_text`。
5. 在“设置 -> 语音合成”中选择“本地 GPT-SoVITS v2ProPlus”，将“项目目录”设为 GPT-SoVITS 根目录，本地 API 保持 `http://127.0.0.1:9880`。程序会在首次朗读时自行启动 `api_v2.py`。

请使用 CPU 安全推理配置：在 `GPT_SoVITS/configs/tts_infer.yaml` 的 `v2Pro` 段保持 `device: cpu` 和 `is_half: false`。不要启用 CUDA、FP16 或 GPU 量化选项。如果 `9880` 长时未监听、进程退出或 Windows 报分页文件不足，请先关闭占用内存的程序并增大分页文件。

### 语音与显示同步

当语音服务已成功合成过一次 WAV 时，Moepet 会在日文翻译完成后让中文回复按设定逐字速度开始显示，同时在后台合成语音，让文字比声音稍早出现。流式的原始文本不会闪现，括号内的动作/旁白也会在显示前过滤。

如果本地或远端 TTS 未启动、失败或断开，程序会立即回退为纯文本显示，不会等待语音超时。语音服务恢复且再次成功合成后，同步行为会自动恢复。

## 可选依赖

需要语音输入、本地 OCR 或全局快捷键时安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-optional.txt
```

- `sounddevice`、`numpy`：录制麦克风输入。
- `faster-whisper`：本地语音识别。
- `rapidocr-onnxruntime`：本地 OCR。
- `keyboard`：全局快捷键。
- `PySide6-Addons`：生成语音的 WAV 播放。

仅在 ASR 服务配置完整时，按住说话按钮和全局录音快捷键才会启用。

## 屏幕理解与隐私

在聊天框中输入“识图”或使用默认快捷键 `Ctrl+Alt+O` 可请求识别当前屏幕。云端视觉服务需要在设置中明确授权，截图处理后会自动删除，除非启用了保留截图。

定时观察默认关闭。开启前需同时配置聊天与视觉服务；角色会根据屏幕内容自然回应，而非逐项复述画面。

## 角色与资料库

每个角色是 `characters/` 下包含 `config.json` 的目录：

```text
characters/my_character/
|- config.json
|- sprites/
|  |- idle.png
|  `- speak_1.png
`- animations.json
```

`animations.json` 示例：

```json
{
  "idle": {"frames": ["idle.png"], "frame_ms": 500, "loop": true},
  "speak": {"frames": ["speak_1.png", "idle.png"], "frame_ms": 160, "loop": true}
}
```

在“设置 -> 角色设置 -> 角色资料库”导入 TXT、Markdown 或 JSON：

- 世界观/背景：地点、规则和环境信息。
- 角色设定：身份、性格、边界与关系。
- 对话示例：用于参考语气的高质量问答。

资料保存到角色目录的 `knowledge/sources/`，聊天记录保存到 `characters/*/chat_history.json`。它们都是本地运行数据，不应提交。

## 项目结构

```text
moepet/
|- core/                  # 配置、角色、LLM、TTS、ASR、OCR、视觉服务
|- ui/                    # 立绘、聊天框、设置页、托盘
|- characters/            # 角色配置、立绘与资料
|- datasets/              # 可选资料示例
|- tools/                 # 辅助脚本
|- requirements-optional.txt
`- main.py
```

## 说明

- 本项目不提供或分发第三方角色音频、训练权重或受版权保护的素材。
- 请遵守所使用模型、语音、素材和第三方 API 的许可与服务条款。

# Noir 本地语音资产

本目录是 Moepet 的角色语音资产目录，不包含 GPT-SoVITS 整合包本体。

- `noir-e15.ckpt`：Noir GPT 权重
- `noir_e8_s968.pth`：Noir SoVITS 权重
- `reference.wav`：授权参考音频
- `reference.txt`：参考音频的实际日文转写，GPT-SoVITS 推理时使用
- `reference_zh.txt`：该文本的中文释义，用于设置页提示

在“语音合成 → 本地 GPT-SoVITS”中，必须同时检测到整合包和这四类资产，才会显示为已就绪。权重与音频因为体积和许可原因不提交到 Git；选择 CPU 兼容包时，执行 `setup.ps1 -InstallCpuTts` 会从 Moepet Release 下载并放入本目录。GPU 用户可自行提供兼容资源。

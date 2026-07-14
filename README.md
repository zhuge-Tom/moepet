# 🐱 Moepet - 萌系桌面宠物

基于 PySide6 的动漫角色桌面宠物，支持多角色切换。

## ✨ 功能
- 🎨 透明无边框窗口，浮动在桌面最上层
- 🖱️ 鼠标拖拽移动
- 🔄 点击切换表情/立绘
- 👥 多角色支持，一键切换
- 🔊 音色训练与 TTS 语音（计划中）

## 🎭 角色
| 角色 | 来源 | 状态 |
|------|------|:----:|
| nuowa | 星空列车与白的旅行 | 🚧 制作中 |

## 🚀 快速开始

```bash
pip install PySide6
python main.py
```

## 📁 项目结构
```
moepet/
├── main.py              # 入口
├── core/                # 核心引擎
│   ├── pet_window.py    # 透明窗口
│   ├── pet_manager.py   # 角色管理
│   └── config.py        # 全局配置
├── characters/          # 角色资源
│   └── nuowa/
│       ├── sprites/     # 立绘图片
│       └── config.json  # 角色配置
└── voice/               # 音色模型（计划中）
```

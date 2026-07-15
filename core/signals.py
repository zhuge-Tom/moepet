"""全局信号总线

各组件通过信号通信，避免直接引用，降低耦合。
借鉴 ZcChat 的 signal/slot 分层模式。
"""

from PySide6.QtCore import QObject, Signal


class SignalHub(QObject):
    """集中管理所有跨组件信号"""

    # 立绘相关
    sprite_change_requested = Signal(str)      # 请求切换立绘（传入立绘名）
    sprite_animation_requested = Signal(str)    # 请求播放动画（传入动画类型）

    # 对话框相关
    dialog_toggle_requested = Signal()          # 请求显示/隐藏对话框
    dialog_text_received = Signal(str)          # 对话框收到新文本

    # 角色相关
    character_switched = Signal(str)            # 角色已切换
    character_loaded = Signal(str)              # 角色加载完成

    # 设置相关
    settings_changed = Signal(dict)             # 设置项变更
    scale_changed = Signal(float)               # 缩放变更

    # 位置相关
    position_changed = Signal(int, int)         # 立绘位置变更

    # 系统
    quit_requested = Signal()                   # 退出请求


# 全局单例
signals = SignalHub()

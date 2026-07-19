"""Select static portrait expressions from conversational meaning."""

from __future__ import annotations

import re


# More specific meanings come first. Interaction-only portraits are never
# referenced here; they belong exclusively to PetWindow's head-touch flow.
_REPLY_EXPRESSIONS = (
    ("angry", ("生气", "恼火", "恼怒", "讨厌", "过分", "不可以", "别这样", "不准", "哼")),
    ("sad", ("难过", "伤心", "悲伤", "遗憾", "可惜", "对不起", "抱歉", "想哭", "失落")),
    ("concern", ("担心", "小心", "注意安全", "没事吧", "保重", "辛苦了", "别勉强", "休息一下")),
    ("surprised", ("诶", "欸", "啊？", "什么？", "真的吗", "居然", "没想到", "意外", "吓了一跳")),
    ("shy", ("害羞", "脸红", "不好意思", "才不是", "别夸我", "这样说我")),
    ("puzzled", ("不明白", "不太懂", "为什么", "怎么回事", "奇怪", "疑惑", "不确定")),
    ("thinking", ("想想", "让我想", "大概", "也许", "可能", "需要确认", "考虑一下", "分析一下")),
    ("happy", ("开心", "高兴", "太好了", "喜欢", "谢谢", "真好", "当然", "顺利", "成功", "恭喜")),
    ("embarrassed", ("打扰了", "不方便", "麻烦你了", "失礼了")),
    ("content", ("知道了", "明白了", "可以的", "好的", "没问题", "交给我", "嗯嗯")),
)

_USER_EXPRESSIONS = (
    ("sad", ("难过", "伤心", "痛苦", "想哭", "失落", "失败", "分手", "压力", "郁闷")),
    ("concern", ("累了", "不舒服", "生病", "疼", "害怕", "焦虑", "睡不着")),
    ("angry", ("生气", "愤怒", "气死", "讨厌", "被欺负")),
    ("surprised", ("震惊", "吓到", "怎么会", "居然", "真的吗", "没想到")),
    ("puzzled", ("不懂", "不明白", "为什么", "怎么办", "搞不清")),
    ("happy", ("开心", "高兴", "好耶", "成功", "谢谢", "喜欢", "太棒", "顺利")),
)


def select_expression(reply: str, user_text: str = "") -> str:
    """Return a configured expression key without involving the chat model."""
    normalized_reply = re.sub(r"\s+", "", reply.lower())
    for expression, keywords in _REPLY_EXPRESSIONS:
        if any(keyword in normalized_reply for keyword in keywords):
            return expression

    normalized_user = re.sub(r"\s+", "", user_text.lower())
    for expression, keywords in _USER_EXPRESSIONS:
        if any(keyword in normalized_user for keyword in keywords):
            return expression
    return "idle"

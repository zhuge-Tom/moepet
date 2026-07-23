"""Non-blocking structured memory analysis using the configured chat provider."""

from __future__ import annotations

import json
import re

from PySide6.QtCore import QObject, Signal

from core.llm_service import LLMService


class MemoryAnalyzer(QObject):
    finished = Signal(dict, object)
    screened = Signal(list, object)
    failed = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._service = LLMService(self)
        self._token = None
        self._summary_source_ids = []
        self._mode = "analysis"
        self._service.response_finished.connect(self._done)
        self._service.error_occurred.connect(self._error)

    def is_busy(self) -> bool:
        return self._service.is_busy()

    def cancel(self) -> None:
        self._service.cancel()
        self._token = None

    def analyze(self, provider: dict, character_name: str, user_text: str,
                assistant_text: str, pending: dict | None, token=None) -> bool:
        if self.is_busy():
            return False
        self._token = token
        self._mode = "analysis"
        self._summary_source_ids = [row["id"] for row in (pending or {}).get("messages", [])]
        self._service.configure(
            provider.get("base_url", ""), provider.get("api_key", ""), provider.get("model", ""),
            clean_response=False)
        self._service.set_system_prompt(
            f"你是{character_name}的私密记忆整理器。只输出一个 JSON 对象，不要 Markdown。"
            "字段：mood(简短中文情绪), intensity(1-5), emotion_note, importance(1-5), "
            "keywords(字符串数组), facts(数组，每项含 content、importance、subject=user/assistant/other、"
            "category=闲聊/爱好/事实/计划/关系/事件、keywords)。只保留角色自己认为值得记住且未来有用的事实；"
            "测试和无意义闲聊不生成 facts。若提供待摘要消息，还要输出 summary 和 summary_source_ids，"
            "摘要用角色给自己整理记忆的口吻，保留时间、事实与情绪，不重复旧摘要。"
            "若提供待压缩旧摘要，将它提炼为 long_term_facts（与 facts 相同结构），并输出 "
            "compressed_summary_ids。")
        payload = {"current_turn": {"user": user_text, "assistant": assistant_text}}
        if pending:
            payload["previous_summary"] = pending.get("previous_summary", "")
            payload["messages_to_summarize"] = [
                {"id": row["id"], "role": row["role"], "content": row["content"],
                 "time": row["created_at"], "period": row["period"]}
                for row in pending.get("messages", [])]
            if pending.get("summary_to_compress"):
                payload["summary_to_compress"] = pending["summary_to_compress"]
        self._service.add_user_message(json.dumps(payload, ensure_ascii=False), persist=False)
        self._service.send(stream=False)
        return True

    def screen(self, provider: dict, query: str, candidates: list[dict], token=None) -> bool:
        if self.is_busy():
            return False
        self._token = token
        self._mode = "screen"
        self._service.configure(
            provider.get("base_url", ""), provider.get("api_key", ""), provider.get("model", ""),
            clean_response=False)
        self._service.set_system_prompt(
            "你是记忆相关性检查器。只输出 JSON：{\"selected_ids\":[整数ID]}。"
            "仅选择确实有助于回答当前问题的记忆；无关或重复信息不要选择。")
        self._service.add_user_message(json.dumps({
            "query": query,
            "candidates": [{"id": item["id"], "content": item["content"],
                            "date": item["memory_date"], "period": item["period"]}
                           for item in candidates],
        }, ensure_ascii=False), persist=False)
        self._service.send(stream=False)
        return True

    @staticmethod
    def _json_object(text: str) -> dict:
        cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.I).strip()
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            value = json.loads(match.group(0)) if match else {}
        return value if isinstance(value, dict) else {}

    def _done(self, text: str) -> None:
        token, self._token = self._token, None
        try:
            value = self._json_object(text)
            if self._mode == "screen":
                ids = value.get("selected_ids", [])
                self.screened.emit([int(item) for item in ids if str(item).isdigit()], token)
                self._service.clear_history()
                return
            if value.get("summary") and not value.get("summary_source_ids"):
                value["summary_source_ids"] = self._summary_source_ids
            self.finished.emit(value, token)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self.failed.emit(f"记忆分析结果无效：{exc}", token)
        self._service.clear_history()
        self._summary_source_ids = []

    def _error(self, message: str) -> None:
        token, self._token = self._token, None
        self._service.clear_history()
        self.failed.emit(message, token)

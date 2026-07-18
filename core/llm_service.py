"""LLM 对话服务

支持 OpenAI 兼容 API（DeepSeek、OpenAI、本地模型等）。
使用 QNetworkAccessManager 异步请求，支持流式输出。
"""

import json
import re
from PySide6.QtCore import QObject, Signal, QByteArray, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from core.openai_compat import bearer_headers, chat_completions_url, is_local_endpoint


class LLMService(QObject):
    """OpenAI 兼容的对话服务"""

    # 流式输出信号
    chunk_received = Signal(str)      # 每次收到一个文本片段
    response_finished = Signal(str)   # 完整回复
    error_occurred = Signal(str)      # 错误信息

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._messages: list[dict] = []
        self._current_reply: QNetworkReply | None = None
        self._buffer = ""
        self._streaming = False
        self._turn_context = ""

    def configure(self, base_url: str, api_key: str, model: str,
                  post_processing: str = "", ignore_format_error: bool = True):
        """设置 API 参数"""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._post_processing = post_processing.strip()
        self._ignore_format_error = bool(ignore_format_error)

    def _clean_response(self, text: str) -> str:
        """Remove model markup and an optional user-configured pattern."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if not self._post_processing:
            return text
        try:
            return re.sub(self._post_processing, "", text, flags=re.DOTALL).strip()
        except re.error as exc:
            if self._ignore_format_error:
                return text
            raise ValueError(f"回复后处理正则无效：{exc}") from exc

    def set_system_prompt(self, prompt: str):
        """设置系统提示词（保留在消息列表最前面）"""
        if self._messages and self._messages[0]["role"] == "system":
            self._messages[0]["content"] = prompt
        else:
            self._messages.insert(0, {"role": "system", "content": prompt})

    def add_user_message(self, text: str, persist: bool = True):
        """Append a user turn, optionally keeping it out of saved chat history."""
        message = {"role": "user", "content": text}
        if not persist:
            message["transient"] = True
        self._messages.append(message)

    def add_assistant_message(self, text: str):
        self._messages.append({"role": "assistant", "content": text})

    def set_turn_context(self, context: str):
        """Use retrieved material for the next request without saving it to history."""
        self._turn_context = context

    def clear_history(self):
        """清空对话历史（保留系统提示词）"""
        if self._messages and self._messages[0]["role"] == "system":
            self._messages = [self._messages[0]]
        else:
            self._messages = []
        # Retrieved context belongs to one turn and must not cross characters.
        self._turn_context = ""

    @property
    def history(self) -> list[dict]:
        # Internal prompts (for example screen observation instructions) must
        # never appear in the user-visible persisted conversation.
        return [
            {"role": item["role"], "content": item["content"]}
            for item in self._messages if not item.get("transient", False)
        ]

    def is_busy(self) -> bool:
        return self._current_reply is not None

    def cancel(self):
        """取消当前请求"""
        if self._current_reply:
            self._current_reply.abort()
            self._current_reply = None

    def send(self, stream: bool = True):
        """发送对话请求"""
        if self.is_busy():
            self.cancel()

        if not self._base_url or not self._model:
            self.error_occurred.emit("请先在设置中配置 API 地址和模型")
            return
        if not self._api_key and not is_local_endpoint(self._base_url):
            self.error_occurred.emit("请先在设置中配置 API Key；本地服务可以留空")
            return

        url = chat_completions_url(self._base_url)

        messages = [
            {"role": item["role"], "content": item["content"]}
            for item in self._messages
        ]
        if self._turn_context:
            insert_at = 1 if messages and messages[0].get("role") == "system" else 0
            messages.insert(insert_at, {"role": "system", "content": self._turn_context})
        body = {
            "model": self._model,
            "messages": messages,
            "stream": stream,
        }
        # Transient turns are only request instructions, never conversation
        # state for subsequent requests or history persistence.
        self._messages = [item for item in self._messages if not item.get("transient", False)]

        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        for name, value in bearer_headers(self._api_key).items():
            request.setRawHeader(name.encode(), value.encode())

        self._streaming = stream
        self._buffer = ""
        self._turn_context = ""

        if stream:
            self._current_reply = self._manager.post(request, QByteArray(json.dumps(body).encode()))
            self._current_reply.readyRead.connect(self._on_stream_data)
            self._current_reply.finished.connect(self._on_stream_finished)
        else:
            self._current_reply = self._manager.post(request, QByteArray(json.dumps(body).encode()))
            self._current_reply.finished.connect(self._on_non_stream_finished)

    def _on_stream_data(self):
        """处理流式数据（SSE 格式）"""
        if not self._current_reply:
            return
        data = self._current_reply.readAll().data().decode("utf-8", errors="replace")
        self._buffer += data

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()

            if not line or not line.startswith("data:"):
                continue

            payload = line[5:].strip()
            if payload == "[DONE]":
                continue

            try:
                obj = json.loads(payload)
                choices = obj.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    self._buffer_out = getattr(self, "_buffer_out", "") + content
                    self.chunk_received.emit(content)
            except json.JSONDecodeError:
                pass

    def _on_stream_finished(self):
        """流式请求结束"""
        reply = self._current_reply
        self._current_reply = None

        if reply.error() != QNetworkReply.NoError:
            err = reply.errorString()
            self.error_occurred.emit(f"请求失败: {err}")
            reply.deleteLater()
            return

        full_text = getattr(self, "_buffer_out", "")
        # 清理 think 标签等模型杂项
        try:
            full_text = self._clean_response(full_text)
        except ValueError as exc:
            self.error_occurred.emit(str(exc))
            reply.deleteLater()
            return
        self._buffer_out = ""

        if full_text:
            self.add_assistant_message(full_text)
            self.response_finished.emit(full_text)
        else:
            self.error_occurred.emit("收到空回复，请检查 API 配置")

        reply.deleteLater()

    def _on_non_stream_finished(self):
        """非流式请求结束"""
        reply = self._current_reply
        self._current_reply = None

        if reply.error() != QNetworkReply.NoError:
            self.error_occurred.emit(f"请求失败: {reply.errorString()}")
            reply.deleteLater()
            return

        try:
            data = json.loads(reply.readAll().data().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                try:
                    content = self._clean_response(content)
                except ValueError as exc:
                    self.error_occurred.emit(str(exc))
                    reply.deleteLater()
                    return
                if content:
                    self.add_assistant_message(content)
                    self.response_finished.emit(content)
                else:
                    self.error_occurred.emit("收到空回复")
            else:
                err = data.get("error", {}).get("message", "未知错误")
                self.error_occurred.emit(f"API 返回错误: {err}")
        except (json.JSONDecodeError, KeyError) as e:
            self.error_occurred.emit(f"解析回复失败: {e}")

        reply.deleteLater()

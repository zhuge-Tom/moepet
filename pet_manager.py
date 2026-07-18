"""宠物管理器

顶层协调者，负责角色加载、窗口管理、LLM 对话、信号路由。
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt

from core.config import Config
from core.character import CharacterLoader, CharacterData
from core.signals import signals
from core.llm_service import LLMService
from core.ocr_service import OcrService
from core.tts_service import TTSService
from core.vision_service import VisionService
from core.openai_compat import is_local_endpoint
from core.screen_observer import ScreenObserver
from core.asr_service import ASRService
from core.voice_input import PushToTalkRecorder
from core.startup import set_enabled as set_startup_enabled
from core.hotkeys import HotkeyService
from core.knowledge_base import KnowledgeBase
from ui.pet_window import PetWindow
from ui.dialog_window import DialogWindow
from ui.settings_window import SettingsWindow
from ui.tray_icon import TrayIcon


class PetManager:
    """管理角色实例和各 UI 组件的生命周期"""

    def __init__(self, base_dir: Path, config: Config):
        self.base_dir = base_dir
        self.config = config
        self._loader = CharacterLoader(base_dir / "characters")
        self._windows: dict[str, PetWindow] = {}
        self._char_data: dict[str, CharacterData] = {}
        self._knowledge: KnowledgeBase | None = None
        self._dialog: DialogWindow | None = None
        self._settings_dlg: SettingsWindow | None = None
        self._tray: TrayIcon | None = None

        self._llm = LLMService()
        self._ocr = OcrService()
        self._ocr.completed.connect(self._on_ocr_done)
        self._ocr.failed.connect(self._on_ocr_error)
        self._tts = TTSService()
        self._tts.completed.connect(self._on_tts_done)
        self._tts.failed.connect(self._on_tts_error)
        self._vision = VisionService()
        self._vision.completed.connect(self._on_vision_done)
        self._vision.failed.connect(self._on_vision_error)
        self._asr = ASRService()
        self._asr.completed.connect(self._on_asr_done)
        self._asr.failed.connect(self._on_asr_error)
        self._voice_recorder = PushToTalkRecorder()
        self._voice_recorder.completed.connect(self._on_voice_recorded)
        self._voice_recorder.failed.connect(self._on_voice_error)
        self._screen_hotkey = HotkeyService()
        self._screen_hotkey.triggered.connect(self._capture_screen)
        self._screen_request_active = False
        self._role_epoch = 0
        self._asr_hotkey = HotkeyService()
        self._screen_mode = "manual"
        self._last_observation_at: datetime | None = None
        self._screen_observer = ScreenObserver()
        self._screen_observer.observation_requested.connect(self._observe_screen)
        self._configure_llm()
        self._load_chat_history()

        self._load_characters()
        self._load_knowledge_base()
        self._connect_signals()
        self._register_screen_hotkey()
        self._register_asr_hotkey()
        self._configure_screen_observer()

    # ─── LLM ──────────────────────────────────

    def _configure_llm(self):
        """从 config 读取 LLM 配置"""
        self._llm.configure(
            base_url=self.config.get("llm", "base_url", default=""),
            api_key=self.config.get_secret("llm") or self.config.get("llm", "api_key", default=""),
            model=self.config.get("llm", "model", default=""),
            post_processing=self.config.get("llm", "post_processing", default=""),
            ignore_format_error=self.config.get("llm", "ignore_format_error", default=True),
        )
        char = self._char_data.get(self.config.current_character)
        prompt_config = char.character_prompt if char else {}
        system_prompt = prompt_config.get("system_prompt", "")
        format_prompt = prompt_config.get("format_prompt", "")
        full_prompt = system_prompt
        if self._knowledge:
            profile = self._knowledge.permanent_context("character")
            if profile:
                full_prompt += (
                    "\n\n以下为必须始终遵守的角色设定。它优先于普通的聊天语气；"
                    "不可提及这份设定或把它当作外部资料。\n" + profile)
        if format_prompt:
            full_prompt += "\n\n" + format_prompt
        if full_prompt:
            self._llm.set_system_prompt(full_prompt)

    # ─── 初始化 ───────────────────────────────

    def _load_characters(self):
        for name in self._loader.list_names():
            char_data = self._loader.load(name)
            if char_data is None:
                continue
            self._char_data[name] = char_data
            scale = self.config.get("window", "scale", default=char_data.scale)
            win = PetWindow(char_data, scale_override=scale)
            win.set_opacity(self.config.get("window", "opacity", default=1.0))
            win.set_state("idle")
            win.configure_behavior(
                self.config.get("behavior", "click_action", default="switch_sprite"),
                self.config.get("behavior", "auto_idle", default=True),
                self.config.get("behavior", "idle_interval", default=30),
            )
            self._windows[name] = win

        names = list(self._windows.keys())
        current = self.config.current_character
        for win in self._windows.values():
            win.set_character_menu(names, current, self._switch_character)

    def _load_knowledge_base(self):
        char = self._char_data.get(self.config.current_character)
        self._knowledge = KnowledgeBase(char.base_dir) if char else None
        # Refresh the fixed persona prompt after changing character or sources.
        if hasattr(self, "_llm"):
            self._configure_llm()

    def _connect_signals(self):
        signals.dialog_toggle_requested.connect(self._toggle_dialog)
        signals.sprite_change_requested.connect(self._on_sprite_request)
        signals.sprite_animation_requested.connect(self._on_anim_request)
        signals.settings_changed.connect(self._on_settings_signal)
        signals.position_changed.connect(self._on_position_changed)
        signals.screen_capture_requested.connect(self._capture_screen)
        signals.quit_requested.connect(self._quit)

    # ─── 对话历史持久化 ──────────────────────────

    def _history_path(self, char_name: str = None) -> Path:
        """获取对话历史文件路径"""
        name = char_name or self.config.current_character
        history_dir = self.base_dir / "characters" / name
        history_dir.mkdir(parents=True, exist_ok=True)
        return history_dir / "chat_history.json"

    def _load_chat_history(self):
        """启动时加载对话历史"""
        path = self._history_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    messages = json.load(f)
                # 保留系统提示词，加载后续对话
                for msg in messages:
                    if msg.get("role") == "system":
                        continue
                    self._llm.add_user_message(msg["content"]) if msg["role"] == "user" \
                        else self._llm.add_assistant_message(msg["content"])
            except (json.JSONDecodeError, OSError, KeyError):
                pass

    def _save_chat_history(self):
        """保存对话历史到文件"""
        path = self._history_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._llm.history, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _setup_tray(self):
        current = self.config.current_character
        char = self._char_data.get(current)
        name = char.name if char else "Moepet"
        self._tray = TrayIcon(
            char_name=name,
            observe_enabled=self.config.get("screen_capture", "auto_observe", default=False),
        )
        self._tray.show()

    # ─── 启动 ────────────────────────────────

    def start(self):
        current = self.config.current_character
        if current in self._windows:
            win = self._windows[current]
            pos = self.config.get_position("pet")
            if pos:
                win.move(*pos)
            # Saved coordinates can belong to a disconnected monitor. Keep the
            # pet reachable on the current primary display after a restart.
            screen = QApplication.primaryScreen()
            if screen and not screen.availableGeometry().intersects(win.frameGeometry()):
                area = screen.availableGeometry()
                win.move(area.x() + 100, area.y() + 100)
                self.config.save_position("pet", win.x(), win.y())
            win.show()

        self._setup_tray()

        if self.config.get("dialog", "visible", default=False):
            self._toggle_dialog()

    # ─── 角色切换 ─────────────────────────────

    def _switch_character(self, name: str):
        if name == self.config.current_character:
            return
        old = self.config.current_character
        # Reset old-role state before the new role is made active.
        self._cancel_role_async_work()
        self._save_chat_history()
        self._llm.cancel()
        self._llm.clear_history()
        if old in self._windows:
            self._windows[old].hide()
        if name in self._windows:
            self._windows[name].show()
            self.config.set("current_character", name)
            self.config.save()
            self._load_knowledge_base()
            self._load_chat_history()

            names = list(self._windows.keys())
            for win in self._windows.values():
                win.set_character_menu(names, name, self._switch_character)

            if self._dialog and self._dialog.isVisible():
                char = self._char_data.get(name)
                if char:
                    self._dialog.set_character_name(char.name)

            if self._tray:
                char = self._char_data.get(name)
                if char:
                    self._tray.setToolTip(f"Moepet - {char.name}")

            signals.character_switched.emit(name)

    def _cancel_role_async_work(self):
        """Invalidate background results that belong to the outgoing role."""
        self._role_epoch += 1
        if self._screen_request_active:
            self._finish_screen_request()
        self._voice_recorder.cancel()
        path = getattr(self, "_active_voice_path", None)
        if path:
            path.unlink(missing_ok=True)
        self._active_voice_path = None
        self._voice_epoch = None
        player = getattr(self, "_player", None)
        if player is not None:
            player.stop()
        self._player_epoch = None
        self._tts_epoch = None

    # ─── 对话框 ───────────────────────────────

    def _toggle_dialog(self):
        current = self.config.current_character
        win = self._windows.get(current)

        if self._dialog and self._dialog.isVisible():
            self._dialog.hide()
            self.config.set("dialog", "visible", False)
            self.config.save()
            return

        char = self._char_data.get(current)
        if not char:
            return

        if self._dialog is None:
            self._dialog = DialogWindow(char_name=char.name)
            self._dialog.text_submitted.connect(self._on_dialog_text)
            self._dialog.voice_pressed.connect(self._start_voice_input)
            self._dialog.voice_released.connect(self._stop_voice_input)
            self._dialog.screen_capture_requested.connect(self._capture_screen)
            self._dialog.set_typing_speed(
                self.config.get("general", "typing_speed", default=40))

        self._refresh_dialog_capabilities()

        # 始终定位在立绘正上方居中，紧挨着
        if win:
            self._dialog.show()
            dlg_w = self._dialog.width()
            dlg_h = self._dialog.height()
            dialog_x = win.x() + (win.width() - dlg_w) // 2
            dialog_y = win.y() - dlg_h + 110
            self._dialog.move(dialog_x, dialog_y)
        self.config.set("dialog", "visible", True)
        self.config.save()

    def _on_dialog_text(self, text: str):
        """用户发送消息 → 发给 LLM"""
        if not self._dialog:
            return

        if self._is_screen_request(text):
            self._capture_screen(prompt=text)
            return

        # 每次发消息前重新配置 LLM，确保使用最新设置
        self._configure_llm()

        api_key = self.config.get_secret("llm") or self.config.get("llm", "api_key", default="")
        if not api_key and not is_local_endpoint(self.config.get("llm", "base_url", default="")):
            self._dialog.display_text("请先在设置 → AI 模型 中配置 API Key；本地服务可以留空。", "assistant")
            return

        if self._llm.is_busy():
            self._dialog.display_text("上一条还在处理中，请稍等~", "assistant")
            return

        self._llm.add_user_message(text)
        self._llm.set_turn_context(self._knowledge_context(text))
        self._set_pet_state("think")

        stream = self.config.get("llm", "stream", default=True)
        if stream:
            self._dialog.start_stream()
            self._llm.chunk_received.connect(self._on_llm_chunk)
            self._llm.response_finished.connect(self._on_llm_done)
            self._llm.error_occurred.connect(self._on_llm_error)
            self._llm.send(stream=True)
        else:
            self._dialog.start_stream()
            self._dialog.append_stream("思考中...")
            self._llm.response_finished.connect(self._on_llm_done_non_stream)
            self._llm.error_occurred.connect(self._on_llm_error)
            self._llm.send(stream=False)

    def _knowledge_context(self, user_text: str) -> str:
        """Build a bounded, turn-only roleplay context from imported user material."""
        if not self._knowledge:
            return ""
        settings = self.config.get("knowledge", default={})
        if not settings.get("enabled", True):
            return ""
        chunks = self._knowledge.search(
            user_text,
            limit=int(settings.get("retrieval_count", 4)),
            max_chars=int(settings.get("max_context_chars", 3000)),
        )
        if not chunks:
            return ""
        facts = [item for item in chunks if item.get("type") != "dialogue"]
        examples = [item for item in chunks if item.get("type") == "dialogue"]
        source_text = "\n\n".join(
            f"[{item['type']}：{item['source']}]\n{item['text']}" for item in facts)
        example_text = "\n\n".join(item["text"] for item in examples)
        return (
            "以下是用户导入的角色资料，仅在与当前问题相关时作为事实依据。"
            "不要提及资料库或编造未提供的设定。\n"
            f"相关资料：\n{source_text or '无'}\n\n"
            f"对话示例（模仿其角色语气，不复述无关内容）：\n{example_text or '无'}"
        )

    def _on_llm_chunk(self, chunk: str):
        """流式输出片段"""
        if self._dialog:
            self._dialog.append_stream(chunk)

    def _on_llm_done(self, full_text: str):
        """流式完成"""
        self._llm.chunk_received.disconnect(self._on_llm_chunk)
        self._llm.response_finished.disconnect(self._on_llm_done)
        self._llm.error_occurred.disconnect(self._on_llm_error)
        if self._dialog:
            self._dialog.finish_stream(full_text)
        self._save_chat_history()
        self._set_pet_state("happy")
        self._speak(full_text)

    def _on_llm_done_non_stream(self, full_text: str):
        """非流式完成"""
        self._llm.response_finished.disconnect(self._on_llm_done_non_stream)
        self._llm.error_occurred.disconnect(self._on_llm_error)
        if self._dialog:
            self._dialog._text_display.clear()
            self._dialog.display_text(full_text, "assistant")
        self._save_chat_history()
        self._set_pet_state("happy")
        self._speak(full_text)

    def _on_llm_error(self, err: str):
        """LLM 错误"""
        try:
            self._llm.chunk_received.disconnect(self._on_llm_chunk)
        except RuntimeError:
            pass
        try:
            self._llm.response_finished.disconnect(self._on_llm_done)
        except RuntimeError:
            pass
        try:
            self._llm.response_finished.disconnect(self._on_llm_done_non_stream)
        except RuntimeError:
            pass
        try:
            self._llm.error_occurred.disconnect(self._on_llm_error)
        except RuntimeError:
            pass
        if self._dialog:
            self._dialog.finish_stream()
            self._dialog.display_text(f"出错了: {err}", "assistant")
        self._set_pet_state("idle")

    def _set_pet_state(self, state: str):
        win = self._windows.get(self.config.current_character)
        if win:
            win.set_state(state)

    @staticmethod
    def _is_screen_request(text: str) -> bool:
        keywords = ("识图", "识别屏幕", "看屏幕", "看看屏幕", "分析屏幕", "截图", "识别这个界面")
        return any(word in text.replace(" ", "") for word in keywords)

    def _register_screen_hotkey(self):
        self._screen_hotkey.register(self.config.get("screen_capture", "hotkey", default="Ctrl+Alt+O"))

    def _register_asr_hotkey(self):
        self._asr_hotkey.unregister_push_to_talk()
        if self.config.get("asr", "enabled", default=False):
            self._asr_hotkey.register_push_to_talk(
                self.config.get("asr", "hotkey", default="Ctrl+Alt+Space"),
                self._start_voice_input, self._stop_voice_input,
            )

    def _start_voice_input(self):
        if self.config.get("asr", "enabled", default=False) and not self._asr.is_busy():
            self._voice_recorder.start()

    def _stop_voice_input(self):
        if self._voice_recorder.recording:
            path = Path(tempfile.gettempdir()) / f"moepet-voice-{datetime.now():%Y%m%d-%H%M%S}.wav"
            self._voice_recorder.stop(path)

    def _on_voice_recorded(self, audio_path: str):
        path = Path(audio_path)
        self._active_voice_path = path
        self._voice_epoch = self._role_epoch
        if self._dialog:
            self._dialog.display_text("正在识别语音...", "assistant")
        if self.config.get("asr", "provider", default="local") == "cloud":
            self._asr.transcribe_cloud(
                path, self.config.get("asr", "base_url", default=""),
                self.config.get_secret("asr") or self.config.get("asr", "api_key", default=""),
                self.config.get("asr", "model", default="whisper-1"),
                self.config.get("asr", "language", default=""),
            )
        else:
            self._asr.transcribe(
                path, self.config.get("asr", "model_path", default=""),
                self.config.get("asr", "device", default="cpu"),
                self.config.get("asr", "compute_type", default="int8"),
            )

    def _on_asr_done(self, result: dict):
        path = getattr(self, "_active_voice_path", None)
        if path:
            path.unlink(missing_ok=True)
        self._active_voice_path = None
        if getattr(self, "_voice_epoch", None) != self._role_epoch:
            return
        self._voice_epoch = None
        text = (result or {}).get("text", "").strip()
        signals.voice_transcribed.emit(text)
        if not text:
            if self._dialog:
                self._dialog.display_text("没有听清，请再试一次。", "assistant")
            return
        if self.config.get("asr", "auto_send", default=True):
            self._ensure_dialog_and_send(text)
        elif self._dialog:
            self._dialog.display_text(f"语音识别：{text}", "user")

    def _on_asr_error(self, error: str):
        path = getattr(self, "_active_voice_path", None)
        if path:
            path.unlink(missing_ok=True)
        self._active_voice_path = None
        if getattr(self, "_voice_epoch", None) != self._role_epoch:
            return
        self._voice_epoch = None
        if self._dialog:
            self._dialog.display_text(f"语音识别失败：{error}", "assistant")

    def _on_voice_error(self, error: str):
        if self._dialog:
            self._dialog.display_text(error, "assistant")

    def _refresh_dialog_capabilities(self):
        """Reflect configured integrations in the persistent chat controls."""
        if self._dialog is None:
            return
        self._dialog.set_voice_available(self.config.get("asr", "enabled", default=False))
        # OCR has its own local fallback, so manual capture is always reachable.
        self._dialog.set_screen_available(True)

    def _ensure_dialog_and_send(self, text: str):
        if self._dialog is None or not self._dialog.isVisible():
            self._toggle_dialog()
        if self._dialog:
            self._dialog.display_instant(text, "user")
        self._on_dialog_text(text)

    def _vision_is_ready(self) -> bool:
        """Return whether screenshots may be sent to the configured vision API."""
        vision_url = self.config.get("vision", "base_url", default="")
        local_vision = any(host in vision_url.lower() for host in ("localhost", "127.0.0.1", "[::1]"))
        return bool(
            self.config.get("vision", "enabled", default=False)
            and vision_url
            and self.config.get("vision", "model", default="")
            and (local_vision or self.config.get("vision", "allow_cloud", default=False))
        )

    def _configure_screen_observer(self):
        screen = self.config.get("screen_capture", default={})
        enabled = bool(screen.get("auto_observe", False)) and self._vision_is_ready()
        self._screen_observer.configure(
            enabled,
            screen.get("observe_min_interval", 300),
            screen.get("observe_max_interval", 900),
        )

    def _observe_screen(self):
        """Start one consented, random-interval visual observation."""
        screen = self.config.get("screen_capture", default={})
        cooldown = max(60, int(screen.get("observe_cooldown", 600)))
        if self._last_observation_at and datetime.now() - self._last_observation_at < timedelta(seconds=cooldown):
            self._screen_observer.schedule_next()
            return
        if not self._llm.is_busy() and self._vision_is_ready():
            self._capture_screen(mode="observation")
        else:
            self._screen_observer.schedule_next()

    def _capture_screen(self, prompt: str = "", mode: str = "manual"):
        """Explicit hotkey/chat request: cloud vision first, then private local OCR."""
        if self._screen_request_active:
            return
        screen = QApplication.primaryScreen()
        if not screen:
            return
        path = Path(tempfile.gettempdir()) / f"moepet-capture-{datetime.now():%Y%m%d-%H%M%S}.png"
        if not screen.grabWindow(0).save(str(path), "PNG"):
            return
        self._ocr_path = path
        self._screen_prompt = prompt
        self._screen_mode = mode
        self._screen_request_active = True
        if self._dialog and mode == "manual":
            self._dialog.display_text("正在读取当前屏幕...", "assistant")
        if self._vision_is_ready() and (mode == "observation" or self.config.get("screen_capture", "cloud_first", default=True)):
            started = self._vision.describe(
                path, self.config.get("vision", "base_url"),
                self.config.get_secret("vision") or self.config.get("vision", "api_key", default=""),
                self.config.get("vision", "model"), "",
            )
        else:
            started = self._ocr.recognize(path)
        if not started:
            self._finish_screen_request()
            if mode == "manual" and self._dialog:
                self._dialog.display_text("屏幕识别服务正在处理中，请稍后再试。", "assistant")

    def _finish_screen_request(self) -> bool:
        """Release the active screenshot and return whether it was observation."""
        observation = self._screen_mode == "observation"
        path = getattr(self, "_ocr_path", None)
        if path and not self.config.get("screen_capture", "keep_captures", default=False):
            path.unlink(missing_ok=True)
        self._screen_request_active = False
        self._screen_mode = "manual"
        self._screen_prompt = ""
        return observation

    def _on_ocr_done(self, text: str):
        if not self._screen_request_active:
            return
        observation = self._finish_screen_request()
        if self._dialog:
            self._dialog.display_text(text or "未在截图中识别到文字。", "assistant")
        signals.ocr_completed.emit(text)
        if observation:
            self._screen_observer.schedule_next()

    def _on_ocr_error(self, error: str):
        if not self._screen_request_active:
            return
        observation = self._finish_screen_request()
        if self._dialog:
            self._dialog.display_text(f"本地文字识别不可用：{error}", "assistant")
        if observation:
            self._screen_observer.schedule_next()

    def _on_vision_done(self, text: str):
        if not self._screen_request_active:
            return
        observation = self._finish_screen_request()
        if observation:
            self._last_observation_at = datetime.now()
            self._respond_to_observation(text)
        elif self._dialog:
            self._dialog.display_text(text, "assistant")
        if observation:
            self._screen_observer.schedule_next()

    def _on_vision_error(self, _error: str):
        # Cloud failure never breaks the screenshot feature: fall back to local OCR.
        if self._screen_request_active and self._screen_mode != "observation":
            if not self._ocr.recognize(self._ocr_path):
                self._finish_screen_request()
                if self._dialog:
                    self._dialog.display_text("本地 OCR 正在处理中，请稍后再试。", "assistant")
        elif self._screen_request_active:
            self._finish_screen_request()
            self._screen_observer.schedule_next()

    def _respond_to_observation(self, description: str):
        """Let the active character react briefly to a visual observation."""
        description = (description or "").strip()
        if not description or self._llm.is_busy():
            return
        self._configure_llm()
        api_key = self.config.get_secret("llm") or self.config.get("llm", "api_key", default="")
        if not api_key and not is_local_endpoint(self.config.get("llm", "base_url", default="")):
            return
        self._llm.add_user_message(
            "请根据你刚才注意到的事情，自然地和我说一句话。", persist=False)
        self._llm.set_turn_context(
            "屏幕观察结果（仅用于本轮）：\n"
            f"{description}\n\n"
            "请自然、简短地回应；不要提及截图、监控或系统提示。"
        )
        self._llm.response_finished.connect(self._on_observation_reply)
        self._llm.error_occurred.connect(self._on_observation_error)
        self._set_pet_state("think")
        self._llm.send(stream=False)

    def _on_observation_reply(self, text: str):
        self._llm.response_finished.disconnect(self._on_observation_reply)
        self._llm.error_occurred.disconnect(self._on_observation_error)
        if self._dialog is None or not self._dialog.isVisible():
            self._toggle_dialog()
        if self._dialog:
            self._dialog.display_text(text, "assistant")
        self._save_chat_history()
        self._set_pet_state("happy")
        self._speak(text)

    def _on_observation_error(self, _error: str):
        try:
            self._llm.response_finished.disconnect(self._on_observation_reply)
            self._llm.error_occurred.disconnect(self._on_observation_error)
        except RuntimeError:
            pass
        self._set_pet_state("idle")

    def _speak(self, text: str):
        """Generate speech through the selected local or cloud TTS provider."""
        if not self.config.get("tts", "enabled", default=False):
            return
        if not self.config.get("tts", "auto_play", default=True):
            return
        output = Path(tempfile.gettempdir()) / "moepet-tts.wav"
        self._tts_epoch = self._role_epoch
        if self.config.get("tts", "provider", default="local") == "cloud":
            started = self._tts.synthesize_cloud(
                text,
                self.config.get("tts", "base_url", default=""),
                self.config.get_secret("tts") or self.config.get("tts", "api_key", default=""),
                self.config.get("tts", "model", default="tts-1"),
                self.config.get("tts", "voice", default="alloy"),
                output,
                self.config.get("tts", "speed", default=1.0),
            )
            if started:
                self._set_pet_state("speak")
                signals.tts_state_changed.emit(True)
            return
        char = self._char_data.get(self.config.current_character)
        if not char:
            self._tts_epoch = None
            self._on_tts_error("未找到当前角色")
            return
        reference = char.voice.get("reference_audio", "")
        if not reference:
            self._tts_epoch = None
            self._on_tts_error("本地 CosyVoice 需要角色的授权参考音频")
            return
        reference_path = char.base_dir / "voice" / reference
        started = self._tts.synthesize(
            text, self.config.get("tts", "model_path", default=""), reference_path,
            output, self.config.get("tts", "speed", default=1.0))
        if started:
            self._set_pet_state("speak")
            signals.tts_state_changed.emit(True)

    def _on_tts_done(self, audio_path: str):
        if getattr(self, "_tts_epoch", None) != self._role_epoch:
            Path(audio_path).unlink(missing_ok=True)
            return
        # Qt Multimedia avoids an additional playback dependency.
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtCore import QUrl
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(float(self.config.get("tts", "volume", default=1.0)))
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.setSource(QUrl.fromLocalFile(audio_path))
        self._player.mediaStatusChanged.connect(self._on_audio_status)
        self._player_epoch = self._role_epoch
        self._player.play()

    def _on_audio_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.EndOfMedia and getattr(self, "_player_epoch", None) == self._role_epoch:
            self._set_pet_state("idle")
            signals.tts_state_changed.emit(False)

    def _on_tts_error(self, error: str):
        if getattr(self, "_tts_epoch", None) not in (None, self._role_epoch):
            return
        self._tts_epoch = None
        self._set_pet_state("idle")
        signals.tts_state_changed.emit(False)
        if self._dialog:
            self._dialog.display_text(f"语音合成失败：{error}", "assistant")

    # ─── 立绘请求 ─────────────────────────────

    def _on_sprite_request(self, name: str):
        current = self.config.current_character
        win = self._windows.get(current)
        if win:
            win.set_sprite_by_name(name)

    def _on_anim_request(self, anim_type: str):
        current = self.config.current_character
        win = self._windows.get(current)
        if win:
            win.play_animation(anim_type)

    # ─── 设置 ────────────────────────────────

    def _on_settings_signal(self, data: dict):
        if data.get("action") == "open_settings":
            self._open_settings()
        elif data.get("action") == "capture_screen":
            self._capture_screen()
        elif data.get("action") == "set_screen_observation":
            self._set_screen_observation(bool(data.get("enabled", False)))

    def _set_screen_observation(self, enabled: bool):
        """Toggle the consented watcher from the tray without bypassing policy."""
        if enabled and not self._vision_is_ready():
            if self._tray:
                self._tray.set_observation_enabled(False)
            if self._dialog is None or not self._dialog.isVisible():
                self._toggle_dialog()
            if self._dialog:
                self._dialog.display_text(
                    "请先在图像理解页配置可用视觉服务，并确认云端上传授权。", "assistant")
            return
        self.config.set("screen_capture", "auto_observe", enabled)
        self.config.save()
        self._configure_screen_observer()
        if self._tray:
            self._tray.set_observation_enabled(enabled)

    def _open_settings(self):
        if self._settings_dlg and self._settings_dlg.isVisible():
            self._settings_dlg.activateWindow()
            return

        current = self.config.current_character
        dlg = SettingsWindow(
            self.config, list(self._windows.keys()), current,
            base_dir=self.base_dir,
        )
        dlg.setModal(False)
        dlg.setAttribute(Qt.WA_DeleteOnClose)

        dlg.scale_changed.connect(self._on_live_scale)
        dlg.apply_clicked.connect(self._apply_settings)

        def on_finished(result):
            self._settings_dlg = None
            if result == QDialog.Accepted:
                new_char = dlg.get_new_character()
                if new_char:
                    self._switch_character(new_char)
                self._apply_settings({})

        dlg.finished.connect(on_finished)
        self._settings_dlg = dlg
        dlg.show()

    def _on_live_scale(self, scale: float):
        current = self.config.current_character
        win = self._windows.get(current)
        if win:
            win.rescale(scale)

    def _apply_settings(self, settings: dict):
        """应用所有设置"""
        always_on_top = self.config.get("window", "always_on_top", default=True)
        scale = self.config.get("window", "scale", default=0.5)
        opacity = self.config.get("window", "opacity", default=1.0)
        click_action = self.config.get("behavior", "click_action", default="switch_sprite")
        auto_idle = self.config.get("behavior", "auto_idle", default=True)
        idle_interval = self.config.get("behavior", "idle_interval", default=30)

        for win in self._windows.values():
            win.set_always_on_top(always_on_top)
            win.rescale(scale)
            win.set_opacity(opacity)
            win.configure_behavior(click_action, auto_idle, idle_interval)

        startup_ok, startup_error = set_startup_enabled(
            self.config.get("general", "auto_start", default=False), self.base_dir / "main.py")
        if not startup_ok and startup_error and self._dialog:
            self._dialog.display_text(startup_error, "assistant")

        # 更新对话框缩放比例
        dialog_scale = self.config.get("general", "dialog_scale", default=100)
        typing_speed = self.config.get("general", "typing_speed", default=40)
        if self._dialog:
            self._dialog.set_typing_speed(typing_speed)
            self._dialog.set_dialog_scale(dialog_scale)
            self._refresh_dialog_capabilities()

        # 重新配置 LLM
        self._configure_llm()
        self._register_screen_hotkey()
        self._register_asr_hotkey()
        self._configure_screen_observer()
        if self._tray:
            self._tray.set_observation_enabled(
                self.config.get("screen_capture", "auto_observe", default=False))

        new_char = settings.get("current_character")
        if new_char and new_char != self.config.current_character:
            self._switch_character(new_char)

    # ─── 位置记忆 ─────────────────────────────

    def _on_position_changed(self, x: int, y: int):
        if x == -1 and y == -1:
            current = self.config.current_character
            win = self._windows.get(current)
            if win:
                win.move(100, 100)
                self.config.save_position("pet", 100, 100)
        else:
            self.config.save_position("pet", x, y)

    # ─── 退出 ────────────────────────────────

    def _quit(self):
        self._screen_observer.stop()
        self._cancel_role_async_work()
        self._screen_hotkey.close()
        self._asr_hotkey.close()
        self._save_chat_history()
        current = self.config.current_character
        win = self._windows.get(current)
        if win:
            self.config.save_position("pet", win.x(), win.y())
        if self._dialog and self._dialog.isVisible():
            self.config.save_position("dialog", self._dialog.x(), self._dialog.y())
            self.config.set("dialog", "visible", True)
        else:
            self.config.set("dialog", "visible", False)
        self.config.save()

        if self._tray:
            self._tray.hide()
        QApplication.quit()

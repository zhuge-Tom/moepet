"""宠物管理器

顶层协调者，负责角色加载、窗口管理、LLM 对话、信号路由。
"""

import json
import logging
import sqlite3
import tempfile
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt, QTimer

from core.config import Config
from core.character import CharacterLoader, CharacterData
from core.character_scaffold import find_live2d_model
from core.signals import signals
from core.llm_service import LLMService
from core.ocr_service import OcrService
from core.tts_service import AudioPlaybackService, JapaneseTranslationService, TTSService
from core.vision_service import VisionService
from core.openai_compat import is_local_endpoint
from core.screen_observer import ScreenObserver
from core.asr_service import ASRService
from core.voice_input import PushToTalkRecorder
from core.startup import set_enabled as set_startup_enabled
from core.hotkeys import HotkeyService
from core.knowledge_base import KnowledgeBase
from core.memory import MemoryAnalyzer, MemorySettings, MemoryStore
from core.expression import select_expression
from ui.pet_window import PetWindow
from ui.live2d_window import Live2DWindow
from ui.dialog_window import DialogWindow
from ui.settings_window import SettingsWindow
from ui.settings.service_status import asr_ready
from ui.tray_icon import TrayIcon


LOGGER = logging.getLogger(__name__)


class PetManager:
    """管理角色实例和各 UI 组件的生命周期"""

    def __init__(self, base_dir: Path, config: Config):
        self.base_dir = base_dir
        self.config = config
        self._loader = CharacterLoader(base_dir / "characters")
        self._windows: dict[str, PetWindow] = {}
        # Failed Live2D renderers fall back only for this process; the saved
        # preference remains Live2D for the next launch.
        self._live2d_session_fallbacks: set[str] = set()
        self._char_data: dict[str, CharacterData] = {}
        self._knowledge: KnowledgeBase | None = None
        self._memory: MemoryStore | None = None
        self._memory_analyzer = MemoryAnalyzer()
        self._memory_analyzer.finished.connect(self._on_memory_analysis_done)
        self._memory_analyzer.failed.connect(self._on_memory_analysis_failed)
        self._memory_screener = MemoryAnalyzer()
        self._memory_screener.screened.connect(self._on_memory_screened)
        self._memory_screener.failed.connect(self._on_memory_screen_failed)
        self._memory_screen_pending: dict | None = None
        self._memory_analysis_queue: list[dict] = []
        self._dialog: DialogWindow | None = None
        self._settings_dlg: SettingsWindow | None = None
        self._tray: TrayIcon | None = None

        self._llm = LLMService()
        self._ocr = OcrService()
        self._ocr.completed.connect(self._on_ocr_done)
        self._ocr.failed.connect(self._on_ocr_error)
        self._tts = TTSService()
        self._tts.completed.connect(self._on_tts_done)
        self._tts.fragment_ready.connect(self._on_tts_done)
        self._tts.failed.connect(self._on_tts_error)
        self._audio_player = AudioPlaybackService()
        self._audio_player.completed.connect(self._on_audio_playback_done)
        self._audio_player.failed.connect(self._on_audio_playback_error)
        self._tts_translator = JapaneseTranslationService()
        self._tts_translator.completed.connect(self._on_tts_translation_done)
        self._tts_translator.failed.connect(self._on_tts_error)
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
        self._observation_epoch: int | None = None
        self._screen_response_epoch: int | None = None
        self._pending_tts_text: str | None = None
        self._pending_tts_epoch: int | None = None
        # Audio sync is opt-in at runtime: a fresh or failed remote service
        # must never hold the chat reply behind a synthesis timeout.
        self._tts_available = False
        self._tts_audio_queue = deque()
        self._tts_audio_playing = False
        self._screen_observer = ScreenObserver()
        self._screen_observer.observation_requested.connect(self._observe_screen)
        self._configure_llm()
        self._open_memory_store()
        self._load_chat_history()

        self._load_characters()
        self._prewarm_local_tts()
        self._load_knowledge_base()
        self._connect_signals()
        self._register_screen_hotkey()
        self._register_asr_hotkey()
        self._configure_screen_observer()

    def _prewarm_local_tts(self) -> None:
        if not self.config.get("tts", "enabled", default=False):
            return
        if self.config.get("tts", "provider", default="gpt_sovits_local") != "gpt_sovits_local":
            return
        char = self._char_data.get(self.config.current_character)
        reference = char.voice.get("reference_audio", "") if char else ""
        reference_path = char.base_dir / "voice" / reference if char and reference else ""
        self._tts.prewarm_local(
            self._project_path(self.config.get("tts", "model_path", default="")),
            self._project_path(self.config.get("tts", "local_python", default="")),
            self._project_path(self.config.get("tts", "local_config", default="")),
            self.config.get("tts", "local_api_url", default="http://127.0.0.1:9880"),
            self.config.get("tts", "cpu_threads", default=4),
            reference_path,
            char.voice.get("reference_text", "") if char else "",
        )

    def _project_path(self, value: str) -> str:
        """Resolve portable configuration paths against the Moepet root."""
        if not value:
            return ""
        path = Path(value)
        return str(path if path.is_absolute() else self.base_dir / path)

    # ─── LLM ──────────────────────────────────

    def _configure_llm(self):
        """从 config 读取 LLM 配置"""
        self._llm.configure(
            base_url=self.config.get("llm", "base_url", default=""),
            api_key=self.config.get_secret("llm") or self.config.get("llm", "api_key", default=""),
            model=self.config.get("llm", "model", default=""),
            post_processing=self.config.get("llm", "post_processing", default=""),
            ignore_format_error=self.config.get("llm", "ignore_format_error", default=True),
            history_message_limit=int(self.config.get("memory", "recent_turns", default=12)) * 2,
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
            win = self._create_pet_window(name, char_data)
            self._windows[name] = win

        names = list(self._windows.keys())
        current = self.config.current_character
        for win in self._windows.values():
            win.set_character_menu(names, current, self._switch_character)

    def _live2d_model_path(self, name: str) -> Path | None:
        return find_live2d_model(self.base_dir / "characters" / name)

    def _create_pet_window(self, name: str, char_data: CharacterData):
        scale = self.config.get("window", "scale", default=char_data.scale)
        renderer = self.config.get("window", "renderer", default="live2d")
        model_path = self._live2d_model_path(name)
        if (renderer == "live2d" and model_path is not None and model_path.is_file()
                and name not in self._live2d_session_fallbacks):
            win = Live2DWindow(char_data, model_path, scale_override=scale)
            win.live2d_failed.connect(
                lambda message, character=name: self._on_live2d_failed(character, message))
        else:
            win = PetWindow(char_data, scale_override=scale)
        win.set_opacity(self.config.get("window", "opacity", default=1.0))
        win.set_state("idle")
        win.configure_behavior(
            self.config.get("behavior", "click_action", default="switch_sprite"),
            self.config.get("behavior", "auto_idle", default=True),
            self.config.get("behavior", "idle_interval", default=30),
        )
        return win

    def _on_live2d_failed(self, name: str, message: str) -> None:
        """Keep the pet usable when an OpenGL context or model cannot load."""
        if not isinstance(self._windows.get(name), Live2DWindow):
            return
        LOGGER.warning("%s", message)
        self._live2d_session_fallbacks.add(name)
        self._recreate_pet_windows()
        if self._dialog and self._dialog.isVisible():
            self._dialog.display_text("Live2D 无法初始化，已自动切回静态立绘。", "assistant")

    def _recreate_pet_windows(self) -> None:
        """Rebuild windows when the renderer changes while preserving pet placement."""
        current = self.config.current_character
        old_windows = self._windows
        positions = {name: win.pos() for name, win in old_windows.items()}
        visible = {name: win.isVisible() for name, win in old_windows.items()}
        self._windows = {}
        for name, char_data in self._char_data.items():
            old = old_windows.get(name)
            if old:
                old.hide()
                old.deleteLater()
            win = self._create_pet_window(name, char_data)
            if name in positions:
                win.move(positions[name])
            self._windows[name] = win
        names = list(self._windows.keys())
        for name, win in self._windows.items():
            win.set_character_menu(names, current, self._switch_character)
            if visible.get(name, False):
                win.show()

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

    def _open_memory_store(self) -> None:
        if self._memory:
            self._memory.close()
        self._memory = None
        try:
            char_dir = self.base_dir / "characters" / self.config.current_character
            self._memory = MemoryStore(
                char_dir, MemorySettings.from_dict(self.config.get("memory", default={})))
        except (OSError, sqlite3.Error) as exc:
            LOGGER.warning("记忆数据库初始化失败：%s", exc)

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
                if self._memory:
                    self._memory.import_history_once(messages)
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
            saved_position = self.config.get_position("pet")
            if saved_position:
                win.move(*saved_position)
            else:
                screen = QApplication.primaryScreen()
                if screen:
                    area = screen.availableGeometry()
                    margin = 24
                    win.move(
                        area.right() - win.width() - margin + 1,
                        area.bottom() - win.height() - margin + 1,
                    )
                    self.config.save_position("pet", win.x(), win.y())
            win.show()

        self._setup_tray()

        # Chat is opt-in at every launch; double-clicking the portrait toggles it.
        self.config.set("dialog", "visible", False)
        self.config.save()

    def _needs_initial_setup(self) -> bool:
        """Open the focused first-run setup only when chat cannot yet be used."""
        base_url = self.config.get("llm", "base_url", default="")
        api_key = self.config.get_secret("llm") or self.config.get("llm", "api_key", default="")
        return not bool(
            base_url
            and self.config.get("llm", "model", default="")
            and (api_key or is_local_endpoint(base_url))
        )

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
        analyzer = getattr(self, "_memory_analyzer", None)
        if analyzer:
            analyzer.cancel()
        screener = getattr(self, "_memory_screener", None)
        if screener:
            screener.cancel()
        if hasattr(self, "_memory_screen_pending"):
            self._memory_screen_pending = None
        getattr(self, "_memory_analysis_queue", []).clear()
        if old in self._windows:
            self._windows[old].hide()
        if name in self._windows:
            self._windows[name].show()
            self.config.set("current_character", name)
            self.config.save()
            if hasattr(self, "_memory"):
                PetManager._open_memory_store(self)
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
        audio_player = getattr(self, "_audio_player", None)
        if audio_player is not None:
            audio_player.stop()
        active_tts = getattr(self, "_active_tts_audio_path", "")
        if active_tts:
            Path(active_tts).unlink(missing_ok=True)
        self._active_tts_audio_path = ""
        queue = getattr(self, "_tts_audio_queue", None)
        if queue is not None:
            while queue:
                Path(queue.popleft()).unlink(missing_ok=True)
        self._tts_audio_playing = False
        self._player_epoch = None
        self._tts_epoch = None
        self._observation_epoch = None
        self._disconnect_observation_signals()
        self._screen_response_epoch = None
        self._disconnect_screen_response_signals()

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
            self._dialog.position_changed.connect(self._save_dialog_offset)
            self._dialog.size_changed.connect(self._save_dialog_size)
            self._dialog.resize(
                self.config.get("dialog", "width", default=480),
                self.config.get("dialog", "height", default=240),
            )

        self._refresh_dialog_capabilities()

        if win:
            self._dialog.show()
            offset_x, offset_y = self._dialog_offset_for(win)
            desired_x = win.x() + offset_x
            desired_y = win.y() + offset_y
            screen = QApplication.screenAt(win.frameGeometry().center()) or QApplication.primaryScreen()
            if screen is not None:
                dialog_x, dialog_y = self._clamp_dialog_position(
                    desired_x,
                    desired_y,
                    self._dialog.width(),
                    self._dialog.height(),
                    screen.availableGeometry(),
                )
            else:
                dialog_x, dialog_y = desired_x, desired_y
            self._dialog.move(dialog_x, dialog_y)
            if (dialog_x, dialog_y) != (desired_x, desired_y):
                self._save_dialog_offset(dialog_x, dialog_y)
        self.config.set("dialog", "visible", True)
        self.config.save()

    @staticmethod
    def _clamp_dialog_position(x: int, y: int, width: int, height: int, available) -> tuple[int, int]:
        """Keep a restored dialog fully visible on its pet's current screen."""
        max_x = max(available.left(), available.right() - max(1, width) + 1)
        max_y = max(available.top(), available.bottom() - max(1, height) + 1)
        return (
            max(available.left(), min(int(x), max_x)),
            max(available.top(), min(int(y), max_y)),
        )

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
        if self._memory_screen_pending:
            self._dialog.display_text("我还在整理上一条相关记忆，请稍等。", "assistant")
            return

        self._last_user_text = text
        if self._start_memory_screen(text):
            self._dialog.start_stream()
            self._dialog.append_stream("正在回应...")
            return
        self._dispatch_chat_request(text, self._combined_turn_context(text))

    def _dispatch_chat_request(self, text: str, turn_context: str) -> None:
        self._llm.add_user_message(text)
        self._llm.set_turn_context(turn_context)
        # Only show the dazed reaction for an actually slow reply. Quick
        # turns retain the natural blinking model without a forced reset.
        request_epoch = self._role_epoch
        QTimer.singleShot(1400, lambda: self._show_delayed_thinking(request_epoch))

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

    def _provider_config(self) -> dict:
        return {
            "base_url": self.config.get("llm", "base_url", default=""),
            "api_key": self.config.get_secret("llm") or self.config.get("llm", "api_key", default=""),
            "model": self.config.get("llm", "model", default=""),
        }

    def _start_memory_screen(self, text: str) -> bool:
        if not getattr(self, "_memory", None):
            return False
        try:
            records = self._memory.search(
                text, visible_message_ids=self._memory.visible_message_ids())
        except (sqlite3.Error, OSError, ValueError) as exc:
            LOGGER.warning("记忆候选检索失败：%s", exc)
            return False
        if not records:
            return False
        token = (self._role_epoch, self.config.current_character, text)
        self._memory_screen_pending = {"token": token, "records": records}
        if self._memory_screener.screen(self._provider_config(), text, records, token):
            return True
        self._memory_screen_pending = None
        return False

    def _on_memory_screened(self, selected_ids: list[int], token) -> None:
        pending, self._memory_screen_pending = self._memory_screen_pending, None
        if not pending or pending["token"] != token or token[0] != self._role_epoch:
            return
        selected = [item for item in pending["records"] if item["id"] in set(selected_ids)]
        context = self._combined_turn_context(token[2], memory_records=selected)
        self._dispatch_chat_request(token[2], context)

    def _on_memory_screen_failed(self, message: str, token) -> None:
        LOGGER.warning("记忆二次筛选失败，使用本地排序结果：%s", message)
        pending, self._memory_screen_pending = self._memory_screen_pending, None
        if not pending or pending["token"] != token or token[0] != self._role_epoch:
            return
        context = self._combined_turn_context(token[2], memory_records=pending["records"])
        self._dispatch_chat_request(token[2], context)

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

    def _combined_turn_context(self, user_text: str, memory_records: list[dict] | None = None) -> str:
        sections = [self._knowledge_context(user_text), self._memory_context(user_text, memory_records)]
        return "\n\n".join(item for item in sections if item)

    def _memory_context(self, user_text: str, records: list[dict] | None = None) -> str:
        if not self._memory:
            return ""
        try:
            if records is None:
                records = self._memory.search(
                    user_text, visible_message_ids=self._memory.visible_message_ids())
            mood = self._memory.latest_mood()
        except (sqlite3.Error, OSError, ValueError) as exc:
            LOGGER.warning("记忆检索失败：%s", exc)
            return ""
        parts = []
        if mood:
            parts.append(f"你上一轮留下的心情是：{mood}。保持自然连续，不要直接说明这是情绪记录。")
        if records:
            lines = []
            for item in records:
                stamp = f"{item['memory_date']} {item['period']}"
                lines.append(f"- [{stamp}｜{item['category']}｜{item['subject']}] {item['content']}")
            parts.append(
                "以下是你自己过去整理的相关记忆。只在确实相关时自然使用，不要提及记忆系统，"
                "不要重复用户当前已经说出的内容：\n" + "\n".join(lines))
        return "\n".join(parts)

    def _on_llm_chunk(self, chunk: str):
        """流式输出片段"""
        # In audio-sync mode, retain stream chunks in LLMService only. Showing
        # them here would flash the reply before the WAV is ready.
        if self._dialog and not self._should_sync_text_to_audio():
            self._dialog.append_stream(chunk)

    def _on_llm_done(self, full_text: str):
        """流式完成"""
        self._llm.chunk_received.disconnect(self._on_llm_chunk)
        self._llm.response_finished.disconnect(self._on_llm_done)
        self._llm.error_occurred.disconnect(self._on_llm_error)
        sync_text = self._should_sync_text_to_audio()
        if self._dialog and not sync_text:
            self._dialog.finish_stream(full_text)
        self._save_chat_history()
        self._schedule_memory_analysis(full_text)
        self._show_reply_expression(full_text)
        if sync_text:
            self._queue_text_for_audio(full_text)
        if not self._speak(full_text):
            self._animate_text_speech(full_text)
            if sync_text:
                self._show_pending_tts_text()

    def _on_llm_done_non_stream(self, full_text: str):
        """非流式完成"""
        self._llm.response_finished.disconnect(self._on_llm_done_non_stream)
        self._llm.error_occurred.disconnect(self._on_llm_error)
        sync_text = self._should_sync_text_to_audio()
        if self._dialog and not sync_text:
            self._dialog._text_display.clear()
            self._dialog.display_text(full_text, "assistant")
        self._save_chat_history()
        self._schedule_memory_analysis(full_text)
        self._show_reply_expression(full_text)
        if sync_text:
            self._queue_text_for_audio(full_text)
        if not self._speak(full_text):
            self._animate_text_speech(full_text)
            if sync_text:
                self._show_pending_tts_text()

    def _schedule_memory_analysis(self, assistant_text: str) -> None:
        if not getattr(self, "_memory", None):
            return
        user_text = getattr(self, "_last_user_text", "").strip()
        if not user_text or not assistant_text.strip():
            return
        try:
            _, assistant_id = self._memory.add_turn(user_text, assistant_text)
        except (sqlite3.Error, OSError) as exc:
            LOGGER.warning("记忆写入失败：%s", exc)
            return
        self._memory_analysis_queue.append({
            "epoch": self._role_epoch,
            "character": self.config.current_character,
            "user_text": user_text,
            "assistant_text": assistant_text,
            "assistant_id": assistant_id,
        })
        self._start_next_memory_analysis()

    def _start_next_memory_analysis(self) -> None:
        if self._memory_analyzer.is_busy() or not self._memory_analysis_queue or not self._memory:
            return
        item = self._memory_analysis_queue.pop(0)
        char = self._char_data.get(item["character"])
        provider = self._provider_config()
        token = (item["epoch"], item["character"], item["assistant_id"])
        started = self._memory_analyzer.analyze(
            provider, char.name if char else item["character"], item["user_text"],
            item["assistant_text"], self._memory.pending_summary(), token)
        if not started:
            self._memory_analysis_queue.insert(0, item)

    def _on_memory_analysis_done(self, analysis: dict, token) -> None:
        if (self._memory and token and token[0] == self._role_epoch
                and token[1] == self.config.current_character):
            try:
                self._memory.apply_analysis(analysis, token[2])
            except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
                LOGGER.warning("记忆分析写回失败：%s", exc)
        self._start_next_memory_analysis()

    def _on_memory_analysis_failed(self, message: str, token) -> None:
        LOGGER.warning("后台记忆分析失败：%s", message)
        self._start_next_memory_analysis()

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
            # Live2D needs every semantic state: notably ``speak`` starts
            # its mouth controller, whereas static portraits have no frame
            # for that state and deliberately keep their current sprite.
            if isinstance(win, Live2DWindow):
                win.set_state(state)
                return
            # Static portraits share semantic states with the animation API.
            expression = {"idle": "idle"}.get(state)
            char = self._char_data.get(self.config.current_character)
            if expression and char:
                win.set_sprite_by_name(char.sprite_for_expression(expression))
            elif state != "speak":
                win.set_state(state)

    def _show_reply_expression(self, reply: str) -> None:
        """Switch the static portrait while keeping animation support optional."""
        char = self._char_data.get(self.config.current_character)
        win = self._windows.get(self.config.current_character)
        if not char or not win:
            return
        expression = select_expression(reply, getattr(self, "_last_user_text", ""))
        if isinstance(win, Live2DWindow):
            # Audio playback temporarily uses the speaking state. Remember the
            # semantic expression so it can return after the mouth closes.
            self._last_live2d_expression = expression
            # Ordinary dialogue intentionally has no forced expression: the
            # model keeps its natural auto-blink. Only meaningful reactions
            # are applied briefly by the Live2D window.
            if expression != "idle":
                win.set_state(expression)
            return
        if expression == "idle":
            return
        sprite_name = char.sprite_for_expression(expression)
        if sprite_name:
            win.set_sprite_by_name(sprite_name)

    def _show_delayed_thinking(self, epoch: int) -> None:
        """Show dazed eyes only while a reply remains pending after a delay."""
        if epoch != self._role_epoch or not self._llm.is_busy():
            return
        self._set_pet_state("think")

    def _animate_text_speech(self, text: str) -> None:
        """Give Live2D a natural speaking turn when audio is disabled."""
        win = self._windows.get(self.config.current_character)
        if not isinstance(win, Live2DWindow) or not text.strip():
            return
        epoch = self._role_epoch
        # Chinese dialogue is commonly 4-5 characters per second.  Bound the
        # visual turn so a very short reply is visible and a long reply does
        # not hold the mouth open for an excessive time.
        duration_ms = max(1100, min(14000, len(text.strip()) * 220))
        win.set_state("speak")

        def finish_text_speech():
            if epoch != self._role_epoch:
                return
            active = self._windows.get(self.config.current_character)
            if active is win:
                self._show_reply_expression(text)

        QTimer.singleShot(duration_ms, finish_text_speech)

    @staticmethod
    def _is_screen_request(text: str) -> bool:
        keywords = ("识图", "识别屏幕", "看屏幕", "看看屏幕", "分析屏幕", "截图", "识别这个界面")
        return any(word in text.replace(" ", "") for word in keywords)

    def _register_screen_hotkey(self):
        self._screen_hotkey.register(self.config.get("screen_capture", "hotkey", default="Ctrl+Alt+O"))

    def _register_asr_hotkey(self):
        self._asr_hotkey.unregister_push_to_talk()
        # A globally registered shortcut must never open the microphone when
        # the transcription service has not been configured to receive it.
        if asr_ready(self.config):
            self._asr_hotkey.register_push_to_talk(
                self.config.get("asr", "hotkey", default="Ctrl+Alt+Space"),
                self._start_voice_input, self._stop_voice_input,
            )

    def _start_voice_input(self):
        if asr_ready(self.config) and not self._asr.is_busy():
            if self._voice_recorder.start() and self._dialog:
                self._dialog.set_voice_recording(True)

    def _stop_voice_input(self):
        if self._voice_recorder.recording:
            path = Path(tempfile.gettempdir()) / f"moepet-voice-{datetime.now():%Y%m%d-%H%M%S}.wav"
            self._voice_recorder.stop(path)
        if self._dialog:
            self._dialog.set_voice_recording(False)

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
            self._dialog.set_voice_recording(False)
            # Low-level driver/module errors are not useful dialogue and can
            # collide visually with the next model reply.
            self._dialog.display_text("麦克风暂时不可用，请检查设备或权限后再试。", "assistant")

    def _refresh_dialog_capabilities(self):
        """Reflect configured integrations in the persistent chat controls."""
        if self._dialog is None:
            return
        self._dialog.set_voice_available(asr_ready(self.config))
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
        enabled = bool(screen.get("auto_observe", False)) and self._vision_is_ready() and not self._needs_initial_setup()
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
        if not self._llm.is_busy() and self._vision_is_ready() and not self._needs_initial_setup():
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
        if self._dialog:
            self._dialog.set_screen_busy(True)
        if self._dialog and mode == "manual":
            self._dialog.display_text(self._screen_observation_message(), "assistant")
        if self._vision_is_ready() and (mode == "observation" or self.config.get("screen_capture", "cloud_first", default=True)):
            started = self._vision.describe(
                path, self.config.get("vision", "base_url"),
                self.config.get_secret("vision") or self.config.get("vision", "api_key", default=""),
                self.config.get("vision", "model"), "",
                self.config.get("screen_capture", "vision_max_dimension", default=1280),
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
        dialog = getattr(self, "_dialog", None)
        if dialog:
            dialog.set_screen_busy(False)
        self._screen_mode = "manual"
        self._screen_prompt = ""
        return observation

    def _on_ocr_done(self, text: str):
        if not self._screen_request_active:
            return
        mode, prompt = self._screen_mode, self._screen_prompt
        observation = self._finish_screen_request()
        signals.ocr_completed.emit(text)
        if observation:
            self._screen_observer.schedule_next()
            return
        self._respond_to_screen_content(text, prompt, source="OCR")

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
        mode, prompt = self._screen_mode, self._screen_prompt
        observation = self._finish_screen_request()
        if observation:
            self._last_observation_at = datetime.now()
            self._respond_to_observation(text)
        else:
            self._respond_to_screen_content(text, prompt, source="视觉理解")
        if observation:
            self._screen_observer.schedule_next()

    def _respond_to_screen_content(self, content: str, prompt: str, source: str) -> None:
        """Use screen understanding as private context, then reply in character."""
        content = (content or "").strip()
        if not content:
            if self._dialog:
                self._dialog.display_text("我没有看清画面里的内容，能再试一次吗？", "assistant")
            return
        if self._llm.is_busy() or self._needs_initial_setup():
            if self._dialog:
                self._dialog.display_text("识别到了画面，但聊天服务暂时不可用，稍后再试吧。", "assistant")
            return
        self._configure_llm()
        request = prompt.strip() or "请结合我现在正在看的内容，和我自然地说句话。"
        self._llm.add_user_message(request, persist=False)
        self._llm.set_turn_context(
            f"{source}结果（仅供你理解当前情境，不要复述给用户）：\n{content}\n\n"
            "请严格遵循当前角色的人设和长度约束，自然回应用户刚才的话。把画面内容当作"
            "背景线索，优先给出理解、感受、提醒或与用户相关的回应，而不是逐项描述、"
            "罗列或概括画面。除非用户明确要求识别或分析细节，否则不要复述可见文字、"
            "界面元素或画面内容。不要提及 OCR、视觉模型、截图、系统提示或内部识别过程。"
        )
        self._screen_response_epoch = self._role_epoch
        self._llm.response_finished.connect(self._on_screen_response)
        self._llm.error_occurred.connect(self._on_screen_response_error)
        self._set_pet_state("think")
        if self._dialog:
            self._dialog.display_text(self._screen_thinking_message(), "assistant")
        self._llm.send(stream=False)

    def _on_screen_response(self, text: str):
        active = self._screen_response_epoch == self._role_epoch
        self._screen_response_epoch = None
        self._disconnect_screen_response_signals()
        if not active:
            return
        if self._dialog:
            self._dialog.display_text(text, "assistant")
        self._save_chat_history()
        self._set_pet_state("happy")
        if not self._speak(text):
            self._animate_text_speech(text)

    def _on_screen_response_error(self, _error: str):
        active = self._screen_response_epoch == self._role_epoch
        self._screen_response_epoch = None
        self._disconnect_screen_response_signals()
        if active and self._dialog:
            self._dialog.display_text("我看到了画面，不过这次没能组织好回答。", "assistant")
        if active:
            self._set_pet_state("idle")

    def _screen_observation_message(self) -> str:
        char = self._char_data.get(self.config.current_character)
        name = char.name if char else "我"
        return f"{name} 正在悄悄观察一下……"

    def _screen_thinking_message(self) -> str:
        char = self._char_data.get(self.config.current_character)
        name = char.name if char else "我"
        return f"{name} 看到了……让我想想该怎么说。"

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
        self._observation_epoch = self._role_epoch
        self._llm.response_finished.connect(self._on_observation_reply)
        self._llm.error_occurred.connect(self._on_observation_error)
        self._set_pet_state("think")
        self._llm.send(stream=False)

    def _on_observation_reply(self, text: str):
        active = self._observation_epoch == self._role_epoch
        self._observation_epoch = None
        self._disconnect_observation_signals()
        if not active:
            return
        if self._dialog is None or not self._dialog.isVisible():
            self._toggle_dialog()
        if self._dialog:
            self._dialog.display_text(text, "assistant")
        self._save_chat_history()
        self._set_pet_state("happy")
        if not self._speak(text):
            self._animate_text_speech(text)

    def _on_observation_error(self, _error: str):
        active = self._observation_epoch == self._role_epoch
        self._observation_epoch = None
        self._disconnect_observation_signals()
        if not active:
            return
        self._set_pet_state("idle")

    def _disconnect_observation_signals(self):
        """Remove transient observation handlers before a role can change."""
        try:
            self._llm.response_finished.disconnect(self._on_observation_reply)
        except RuntimeError:
            pass

    def _disconnect_screen_response_signals(self):
        """Detach the one-turn manual screen-response handlers."""
        try:
            self._llm.response_finished.disconnect(self._on_screen_response)
        except RuntimeError:
            pass
        try:
            self._llm.error_occurred.disconnect(self._on_screen_response_error)
        except RuntimeError:
            pass
        try:
            self._llm.error_occurred.disconnect(self._on_observation_error)
        except RuntimeError:
            pass

    def _speak(self, text: str):
        """Translate and synthesize one complete reply as one utterance."""
        if not self.config.get("tts", "enabled", default=False):
            return False
        if not self.config.get("tts", "auto_play", default=True):
            return False
        self._tts_epoch = self._role_epoch
        if self.config.get("tts", "provider", default="gpt_sovits_local") == "openai_compatible":
            output_format = self.config.get("tts", "response_format", default="wav") or "wav"
            output = Path(tempfile.gettempdir()) / f"moepet-tts.{output_format}"
            self._show_pending_tts_text()
            started = self._tts.synthesize_cloud(
                text,
                self.config.get("tts", "base_url", default=""),
                self.config.get_secret("tts") or self.config.get("tts", "api_key", default=""),
                self.config.get("tts", "model", default=""),
                self.config.get("tts", "voice", default=""),
                output,
                self.config.get("tts", "speed", default=1.0),
                output_format,
            )
            if started:
                self._set_pet_state("think")
                signals.tts_state_changed.emit(True)
            return started
        started = self._tts_translator.translate(
            text,
            self.config.get("llm", "base_url", default=""),
            self.config.get_secret("llm") or self.config.get("llm", "api_key", default=""),
            self.config.get("llm", "model", default=""),
        )
        if started:
            self._set_pet_state("think")
            signals.tts_state_changed.emit(True)
        return started

    def _should_sync_text_to_audio(self) -> bool:
        return bool(self.config.get("tts", "enabled", default=False)
                    and self.config.get("tts", "auto_play", default=True)
                    and self._tts_available)

    def _queue_text_for_audio(self, text: str) -> None:
        self._pending_tts_text = text
        self._pending_tts_epoch = self._role_epoch
        if self._dialog:
            # Remove the provisional stream text until the WAV is ready.
            self._dialog.start_stream()

    def _show_pending_tts_text(self) -> None:
        if self._pending_tts_epoch != self._role_epoch:
            return
        text = self._pending_tts_text
        self._pending_tts_text = None
        self._pending_tts_epoch = None
        if text and self._dialog:
            # Use the normal typewriter path so the configured display speed
            # applies while TTS is synthesizing in the background.
            self._dialog.display_text(text, "assistant")

    def _on_tts_translation_done(self, japanese_text: str):
        if getattr(self, "_tts_epoch", None) != self._role_epoch:
            return
        char = self._char_data.get(self.config.current_character)
        if not char:
            self._tts_epoch = None
            self._on_tts_error("未找到当前角色")
            return
        provider = self.config.get("tts", "provider", default="gpt_sovits_local")
        is_local = provider == "gpt_sovits_local"
        reference = char.voice.get("reference_audio", "") if is_local else (
            self.config.get("tts", "remote_reference_audio", default="")
            or char.voice.get("remote_reference_audio", ""))
        if not reference:
            self._tts_epoch = None
            self._on_tts_error("GPT-SoVITS 需要角色的授权参考音频")
            return
        reference_path = char.base_dir / "voice" / reference if is_local else reference
        output = Path(tempfile.gettempdir()) / "moepet-tts.wav"
        base_url = (self.config.get("tts", "local_api_url", default="http://127.0.0.1:9880")
                    if is_local else self.config.get("tts", "base_url", default=""))
        # The translation is ready and synthesis is about to begin. Reveal
        # the reply now, rather than waiting for the finished WAV, so text
        # naturally leads speech without the raw-stream flash.
        self._show_pending_tts_text()
        started = self._tts.synthesize_gpt_sovits(
            japanese_text, base_url,
            "" if is_local else (self.config.get_secret("tts") or self.config.get("tts", "api_key", default="")),
            reference_path, char.voice.get("reference_text", ""), output,
            self.config.get("tts", "speed", default=1.0),
            local_project=self._project_path(self.config.get("tts", "model_path", default="")) if is_local else "",
            local_python=self._project_path(self.config.get("tts", "local_python", default="")),
            local_config=self._project_path(self.config.get("tts", "local_config", default="")),
            cpu_threads=self.config.get("tts", "cpu_threads", default=4),
            streaming_mode=self.config.get("tts", "streaming_mode", default=3),
            fragment_interval=self.config.get("tts", "fragment_interval", default=0.12),
        )
        if started:
            signals.tts_state_changed.emit(True)

    def _on_tts_done(self, audio_path):
        if not audio_path:
            return
        if getattr(self, "_tts_epoch", None) != self._role_epoch:
            Path(audio_path).unlink(missing_ok=True)
            return
        self._tts_audio_queue.append(str(audio_path))
        if self._tts_audio_playing:
            return
        self._play_next_tts_fragment()

    def _play_next_tts_fragment(self):
        if not self._tts_audio_queue:
            self._tts_audio_playing = False
            expression = getattr(self, "_last_live2d_expression", "")
            self._set_pet_state(expression or "idle")
            signals.tts_state_changed.emit(False)
            return
        audio_path = self._tts_audio_queue.popleft()
        self._tts_audio_playing = True
        self._player_epoch = self._role_epoch
        self._active_tts_audio_path = str(audio_path)
        self._tts_available = True
        self._set_pet_state("speak")
        win = self._windows.get(self.config.current_character)
        if isinstance(win, Live2DWindow):
            win.start_lipsync(audio_path)
        if not self._audio_player.play(audio_path):
            self._on_audio_playback_error("Windows 音频播放启动失败")

    def _on_audio_playback_done(self, audio_path: str):
        Path(audio_path).unlink(missing_ok=True)
        if getattr(self, "_player_epoch", None) != self._role_epoch:
            return
        self._active_tts_audio_path = ""
        self._tts_audio_playing = False
        self._play_next_tts_fragment()

    def _on_audio_playback_error(self, error: str):
        active_path = getattr(self, "_active_tts_audio_path", "")
        if active_path:
            Path(active_path).unlink(missing_ok=True)
        self._active_tts_audio_path = ""
        self._tts_audio_playing = False
        LOGGER.error("Audio playback failed: %s", error)
        self._play_next_tts_fragment()

    def _on_tts_error(self, error: str):
        if getattr(self, "_tts_epoch", None) not in (None, self._role_epoch):
            return
        self._tts_epoch = None
        self._tts_available = False
        queue = getattr(self, "_tts_audio_queue", None)
        if queue is not None:
            while queue:
                Path(queue.popleft()).unlink(missing_ok=True)
        # The coordinator can be exercised without the optional audio queue.
        if hasattr(self, "_show_pending_tts_text"):
            self._show_pending_tts_text()
        self._set_pet_state("idle")
        signals.tts_state_changed.emit(False)
        # TTS is optional output. Keep transport failures out of the role's
        # conversation and leave details available in the process log.
        LOGGER.error("TTS synthesis failed: %s", error)

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
        if enabled and (not self._vision_is_ready() or self._needs_initial_setup()):
            if self._tray:
                self._tray.set_observation_enabled(False)
            if self._dialog is None or not self._dialog.isVisible():
                self._toggle_dialog()
            if self._dialog:
                self._dialog.display_text(
                    "请先配置可用的聊天模型和图像理解服务，并确认云端上传授权。", "assistant")
            return
        self.config.set("screen_capture", "auto_observe", enabled)
        self.config.save()

    def _dialog_offset_for(self, win) -> tuple[int, int]:
        """Return a saved chat position relative to the active pet window."""
        # Match the initial placement beside/above Noir from the reference
        # layout. A user drag persists a different relative offset below.
        default_x = -66
        default_y = -96
        return (
            self.config.get("dialog", "offset_x", default=default_x),
            self.config.get("dialog", "offset_y", default=default_y),
        )

    def _save_dialog_offset(self, x: int, y: int) -> None:
        win = self._windows.get(self.config.current_character)
        if not win:
            return
        self.config.set("dialog", "offset_x", x - win.x())
        self.config.set("dialog", "offset_y", y - win.y())
        self.config.save()

    def _save_dialog_size(self, width: int, height: int) -> None:
        self.config.set("dialog", "width", width)
        self.config.set("dialog", "height", height)
        self.config.save()

    def _open_settings(self, initial_page: str = ""):
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
        dlg.memory_cleared.connect(self._on_memory_cleared)
        dlg.memory_changed.connect(self._on_memory_changed)

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
        if initial_page:
            dlg.open_page(initial_page)

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
        renderer = self.config.get("window", "renderer", default="live2d")
        if settings.get("window", {}).get("renderer") == "live2d":
            # An explicit settings apply retries a renderer that failed earlier.
            self._live2d_session_fallbacks.clear()
        click_action = self.config.get("behavior", "click_action", default="switch_sprite")
        auto_idle = self.config.get("behavior", "auto_idle", default=True)
        idle_interval = self.config.get("behavior", "idle_interval", default=30)

        renderer_changed = any(
            (renderer == "live2d" and self._live2d_model_path(name).exists())
            != isinstance(win, Live2DWindow)
            for name, win in self._windows.items()
        )
        if renderer_changed:
            self._recreate_pet_windows()

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
        if self._memory:
            self._memory.update_settings(self.config.get("memory", default={}))
        else:
            self._open_memory_store()
        self._register_screen_hotkey()
        self._register_asr_hotkey()
        self._configure_screen_observer()
        if self._tray:
            self._tray.set_observation_enabled(
                self.config.get("screen_capture", "auto_observe", default=False))

        new_char = settings.get("current_character")
        if new_char and new_char != self.config.current_character:
            self._switch_character(new_char)

    def _on_memory_cleared(self, character: str) -> None:
        if character != self.config.current_character:
            return
        self._memory_analyzer.cancel()
        self._memory_screener.cancel()
        self._memory_analysis_queue.clear()
        self._memory_screen_pending = None
        self._llm.cancel()
        self._llm.clear_history()
        self._configure_llm()

    def _on_memory_changed(self, character: str) -> None:
        if character == self.config.current_character and self._memory:
            self._memory.sync_summary_files()

    # ─── 位置记忆 ─────────────────────────────

    def _on_position_changed(self, x: int, y: int):
        """Move for this session without changing the fixed startup position."""
        if x == -1 and y == -1:
            current = self.config.current_character
            win = self._windows.get(current)
            fixed_position = self.config.get_position("pet")
            if win and fixed_position:
                win.move(*fixed_position)

    # ─── 退出 ────────────────────────────────

    def _quit(self):
        self._screen_observer.stop()
        self._cancel_role_async_work()
        self._tts.shutdown_local()
        self._screen_hotkey.close()
        self._asr_hotkey.close()
        self._save_chat_history()
        self._memory_analyzer.cancel()
        self._memory_screener.cancel()
        self._memory_screen_pending = None
        self._memory_analysis_queue.clear()
        if self._memory:
            self._memory.close()
            self._memory = None
        if self._dialog and self._dialog.isVisible():
            self._save_dialog_offset(self._dialog.x(), self._dialog.y())
            self._save_dialog_size(self._dialog.width(), self._dialog.height())
            self.config.set("dialog", "visible", True)
        else:
            self.config.set("dialog", "visible", False)
        self.config.save()

        if self._tray:
            self._tray.hide()
        QApplication.quit()

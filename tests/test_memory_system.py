import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from core.config import Config
from core.llm_service import LLMService
from core.memory import MemorySettings, MemoryStore, parse_time_query


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def make_store(tmp_path, **settings):
    values = MemorySettings.from_dict({**MemorySettings().__dict__, **settings})
    return MemoryStore(tmp_path / "characters" / "noir", values)


def test_memory_defaults_are_enabled_and_bounded(tmp_path):
    config = Config(tmp_path / "config.json")
    assert config.get("memory", "enabled") is True
    assert config.get("memory", "recent_turns") == 12
    assert config.get("memory", "fact_limit") == 128
    assert MemorySettings.from_dict({"recent_turns": 999, "min_importance": -2}).recent_turns == 50
    assert MemorySettings.from_dict({"recent_turns": 999, "min_importance": -2}).min_importance == 1


def test_legacy_memory_switches_are_migrated_to_always_on(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"memory": {
        "enabled": False, "emotion_enabled": False, "smart_filter": False,
    }}), encoding="utf-8")
    config = Config(path)
    assert config.get("memory", "enabled") is True
    assert config.get("memory", "emotion_enabled") is True
    assert config.get("memory", "smart_filter") is True
    assert MemorySettings.from_dict({"enabled": False}).enabled is True


def test_history_import_is_idempotent_and_role_scoped(tmp_path):
    store = make_store(tmp_path)
    history = [{"role": "user", "content": "我喜欢咖啡"},
               {"role": "assistant", "content": "我记住了"}]
    assert store.import_history_once(history) == 2
    assert store.import_history_once(history) == 0
    assert store.stats()["messages"] == 2
    other = MemoryStore(tmp_path / "characters" / "other")
    assert other.stats()["messages"] == 0
    store.close(); other.close()


def test_pending_summary_keeps_recent_window_and_marks_sources(tmp_path):
    store = make_store(tmp_path, recent_turns=2)
    for number in range(4):
        store.add_turn(f"问题{number}", f"回答{number}")
    pending = store.pending_summary()
    assert pending and len(pending["messages"]) == 8
    source_ids = [item["id"] for item in pending["messages"]]
    store.apply_analysis({
        "mood": "安心", "intensity": 3, "summary": "我们连续聊了几个问题。",
        "summary_source_ids": source_ids, "importance": 3, "keywords": ["问题"],
    }, source_ids[-1])
    assert store.stats()["summaries"] == 1
    assert store.pending_summary() is None
    assert store.latest_mood() == "安心"
    store.close()


def test_summary_overflow_promotes_oldest_without_losing_content(tmp_path):
    store = make_store(tmp_path, summary_limit=2, fact_limit=8)
    now = datetime(2026, 7, 24, 14, 0)
    with store.conn:
        for number in range(3):
            store._insert_memory("summary", {"content": f"摘要{number}", "importance": 3}, now)
        store._promote_old_summaries(now)
    assert store.stats()["summaries"] == 2
    assert store.stats()["facts"] == 1
    assert store.list_records(layer="fact")[0]["content"] == "摘要0"
    store.close()


def test_hybrid_search_supports_time_subject_and_category(tmp_path):
    store = make_store(tmp_path, min_importance=1)
    when = datetime(2026, 7, 23, 15, 30)
    with store.conn:
        store._insert_memory("fact", {
            "content": "用户喜欢喝冰咖啡", "importance": 5, "subject": "user",
            "category": "爱好", "keywords": ["咖啡", "饮料"],
        }, when)
        store._insert_memory("fact", {
            "content": "角色计划晚上看星星", "importance": 4, "subject": "assistant",
            "category": "计划", "keywords": ["星星"],
        }, when.replace(hour=21))
    result = store.search("昨天喜欢什么饮料", date="2026-07-23", periods=["下午"],
                          subject="user", category="爱好")
    assert result and "冰咖啡" in result[0]["content"]
    store.close()


def test_retrieval_excludes_summary_covered_by_visible_raw_messages(tmp_path):
    store = make_store(tmp_path, recent_turns=2, min_importance=1)
    first_ids = store.add_turn("我喜欢冰咖啡", "我记住了")
    store.add_turn("今天很热", "记得补水")
    now = datetime.now()
    with store.conn:
        store._insert_memory("summary", {
            "content": "用户喜欢冰咖啡。", "importance": 5,
            "source_ids": list(first_ids),
        }, now)
    assert store.search("喜欢什么咖啡", visible_message_ids=store.visible_message_ids()) == []
    assert store.search("喜欢什么咖啡", visible_message_ids=set())
    store.close()


def test_relative_time_parser_handles_chinese_periods():
    now = datetime(2026, 7, 24, 10, 0)
    assert parse_time_query("昨天下午聊了什么", now) == {
        "date": "2026-07-23", "periods": ["下午"]}
    assert parse_time_query("前天早上", now) == {
        "date": "2026-07-22", "periods": ["上午"]}


def test_edit_rebuilds_vector_export_and_clear(tmp_path):
    store = make_store(tmp_path, min_importance=1)
    now = datetime.now()
    with store.conn:
        memory_id = store._insert_memory("fact", {"content": "喜欢茶", "importance": 3}, now)
    before = store.list_records()[0]["embedding"]
    assert store.update_record(memory_id, "喜欢咖啡", 5)
    after = store.list_records()[0]["embedding"]
    assert before != after
    target = tmp_path / "export.json"
    store.export_json(target)
    assert json.loads(target.read_text(encoding="utf-8"))["memories"][0]["content"] == "喜欢咖啡"
    store.clear_all()
    assert store.stats() == {"messages": 0, "summaries": 0, "facts": 0, "emotions": 0}
    store.close()


def test_summary_markdown_is_materialized_and_external_edits_sync(tmp_path):
    store = make_store(tmp_path, recent_turns=2)
    now = datetime(2026, 7, 24, 10, 0)
    with store.conn:
        memory_id = store._insert_memory("summary", {
            "content": "最初的近期摘要", "importance": 3,
            "source_ids": [1, 2], "range_start": "2026-07-23", "range_end": "2026-07-24",
        }, now)
    row = store.get_summary(memory_id)
    path = store.root / row["file_path"]
    assert path.exists()
    metadata, content = store._parse_frontmatter(path.read_text(encoding="utf-8"))
    assert metadata["id"] == row["stable_id"]
    assert metadata["source_ids"] == [1, 2]
    assert content == "最初的近期摘要"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "最初的近期摘要", "人工修改后的摘要"), encoding="utf-8")
    report = store.sync_summary_files()
    assert report["updated"] == 1
    assert store.get_summary(memory_id)["content"] == "人工修改后的摘要"
    assert store.sync_summary_files()["updated"] == 0
    store.close()


def test_plain_markdown_import_gets_stable_metadata_and_exports(tmp_path):
    store = make_store(tmp_path)
    source = tmp_path / "recent.md"
    source.write_text("用户最近开始学习绘画。", encoding="utf-8")
    report = store.import_summary_markdown([source])
    assert report["imported"] == 1
    summary = store.list_summaries()[0]
    assert summary["stable_id"]
    canonical = store.root / summary["file_path"]
    assert canonical.read_text(encoding="utf-8").startswith("---\n")
    output = tmp_path / "out"
    assert store.export_summary_markdown([summary["id"]], output) == 1
    assert len(list(output.glob("*.md"))) == 1
    store.close()


def test_json_import_merges_idempotently_and_preserves_local_conflicts(tmp_path):
    source_store = MemoryStore(tmp_path / "source")
    source_store.add_turn("我喜欢旅行", "我记住了", when=datetime(2026, 7, 20, 9, 0))
    with source_store.conn:
        source_store._insert_memory("summary", {
            "content": "用户喜欢旅行。", "source_ids": [1, 2],
            "range_start": "2026-07-20", "range_end": "2026-07-20",
        }, datetime(2026, 7, 20, 9, 0))
    backup = tmp_path / "backup.json"
    source_store.export_json(backup)
    source_store.close()

    target = MemoryStore(tmp_path / "target")
    first = target.import_json(backup)
    second = target.import_json(backup)
    assert first["messages"] == 2 and first["memories"] == 1
    assert second["messages"] == 0 and second["memories"] == 0
    assert target.stats()["messages"] == 2
    assert target.stats()["summaries"] == 1
    assert second["skipped"] >= 3
    target.close()


def test_llm_request_window_does_not_remove_persisted_history():
    service = LLMService()
    service.configure("http://localhost:11434/v1", "", "model", history_message_limit=2)
    service.set_system_prompt("persona")
    for text in ("u1", "a1", "u2", "a2"):
        service.add_user_message(text) if text.startswith("u") else service.add_assistant_message(text)
    assert [item["content"] for item in service._messages_for_request()] == ["persona", "u2", "a2"]
    assert len(service.history) == 5


def test_memory_settings_page_route_and_collection(qapp, tmp_path):
    from ui.settings_window import SettingsWindow
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    window.open_page("memory")
    assert window._stack.currentWidget() is window._pages["memory"]
    values = window._collect_settings()["memory"]
    assert "enabled" not in values
    assert values["retrieval_count"] == 6
    window._memory_page.shutdown()
    window.close()


def test_calendar_archives_timeline_and_portable_bundle(tmp_path):
    store = make_store(tmp_path)
    store.add_turn("今天一起画画", "好呀，我陪你", when=datetime(2026, 7, 24, 15, 0))
    kinds = {item["kind"] for item in store.list_archives()}
    assert kinds == {"diary", "weekly", "monthly", "quarterly", "yearly"}
    diary = store.list_archives("diary")[0]
    assert "陪伴 1 天" in diary["content"]
    assert (store.root / diary["file_path"]).exists()
    series = store.activity_series(2, "2026-07-24")
    assert series[-1] == {"date": "2026-07-24", "chats": 1, "messages": 2}
    target = tmp_path / "all-memory.zip"
    report = store.export_archive(target)
    assert report["archives"] == 5
    with zipfile.ZipFile(target) as bundle:
        names = bundle.namelist()
        assert "memory.json" in names
        assert any(name.startswith("archives/diary/") for name in names)
    store.close()


def test_memory_navigation_children_and_clickable_cards(qapp, tmp_path):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from ui.settings.memory_page import MemoryStatCard
    from ui.settings_window import SettingsWindow
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    memory_item = next(window._tree.topLevelItem(i) for i in range(window._tree.topLevelItemCount())
                       if window._tree.topLevelItem(i).data(0, 256) == "memory")
    child_keys = {memory_item.child(i).data(0, 256) for i in range(memory_item.childCount())}
    assert child_keys == {"memory_overview", "memory_timeline", "memory_diary",
                          "memory_recent", "memory_facts"}
    window.open_page("memory_monthly")
    assert window._memory_page.tabs.currentIndex() == 2
    assert window._memory_page.archive_kind.currentData() == "monthly"
    assert [window._memory_page.archive_kind.itemText(i)
            for i in range(window._memory_page.archive_kind.count())] == [
                "日记", "周记", "月记", "季记", "年记"]
    cards = window._memory_page.findChildren(MemoryStatCard)
    assert len(cards) == 4
    window.open_page("memory_overview"); window.show(); qapp.processEvents()
    message_card = next(card for card in cards if card.key == "messages")
    normal_style = message_card.styleSheet()
    QTest.mouseMove(message_card, QPoint(2, 2)); qapp.processEvents()
    assert message_card.styleSheet() != normal_style
    QTest.mouseClick(message_card, Qt.LeftButton); qapp.processEvents()
    assert window._memory_page.tabs.currentIndex() == 1
    window._memory_page.shutdown(); window.close()


def test_memory_top_tabs_keep_left_navigation_selected(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from ui.settings_window import SettingsWindow
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    window.open_page("memory_overview")
    window._memory_page.tabs.setCurrentIndex(4)
    qapp.processEvents()
    assert window._tree.currentItem().data(0, Qt.UserRole) == "memory_facts"
    window._memory_page.tabs.setCurrentIndex(1)
    qapp.processEvents()
    assert window._tree.currentItem().data(0, Qt.UserRole) == "memory_timeline"
    window._memory_page.shutdown(); window.close()


def test_memory_navigation_has_no_scrollbar_and_high_contrast_tabs(qapp, tmp_path):
    from PySide6.QtCore import Qt
    from ui.settings_window import SettingsWindow
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    window.resize(980, 720); window.show(); window.open_page("memory")
    memory_item = next(window._tree.topLevelItem(i) for i in range(window._tree.topLevelItemCount())
                       if window._tree.topLevelItem(i).data(0, Qt.UserRole) == "memory")
    memory_item.setExpanded(True); qapp.processEvents()
    assert window._tree.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert window._tree.verticalScrollBar().maximum() == 0
    assert window._memory_page.tabs.objectName() == "memory_sections"
    assert "QTabBar::tab" in window._memory_page.tabs.styleSheet()
    window._memory_page.shutdown(); window.close()


def test_about_page_uses_structured_high_contrast_cards(qapp, tmp_path):
    from PySide6.QtWidgets import QFrame, QLabel
    from ui.settings_window import SettingsWindow
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    window.open_page("about")
    page = window._pages["about"]
    assert page.findChild(QFrame, "about_hero") is not None
    assert len(page.findChildren(QFrame, "about_feature")) == 4
    texts = {label.text() for label in page.findChildren(QLabel)}
    assert "让角色真正住进你的桌面" in texts
    window._memory_page.shutdown(); window.close()


def test_settings_window_minimizes_is_not_forced_on_top_and_uses_noir_icon(qapp, tmp_path):
    import shutil
    from pathlib import Path
    from PySide6.QtCore import Qt
    from ui.settings_window import SettingsWindow
    assets = tmp_path / "assets"; assets.mkdir()
    shutil.copy2(Path(__file__).parents[1] / "assets" / "moepet.ico", assets / "moepet.ico")
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    flags = window.windowFlags()
    assert flags & Qt.WindowMinimizeButtonHint
    assert flags & Qt.WindowMaximizeButtonHint
    assert not flags & Qt.WindowStaysOnTopHint
    assert not window.windowIcon().isNull()
    window.resize(980, 720); window.show(); qapp.processEvents()
    normal_size = window.size()
    window.showMaximized(); qapp.processEvents()
    assert window.isMaximized()
    window.showNormal(); qapp.processEvents()
    assert not window.isMaximized()
    assert window.size() == normal_size
    window._memory_page.shutdown(); window.close()


def test_character_scaffold_isolates_roles_and_discovers_own_live2d(tmp_path):
    from core.character import CharacterLoader
    from core.character_scaffold import create_character_scaffold, find_live2d_model
    characters = tmp_path / "characters"
    alice = create_character_scaffold(characters, "alice", "Alice", "static")
    bob = create_character_scaffold(characters, "bob", "Bob", "live2d")
    default_role = create_character_scaffold(characters, "default_role", "Default")
    (alice / "chat_history.json").write_text("[]", encoding="utf-8")
    model = bob / "sprites" / "live2d" / "custom" / "avatar.model3.json"
    model.parent.mkdir(parents=True); model.write_text("{}", encoding="utf-8")
    assert CharacterLoader(characters).list_names() == ["alice", "bob", "default_role"]
    assert find_live2d_model(alice) is None
    assert find_live2d_model(bob) == model
    assert not (bob / "chat_history.json").exists()
    assert (alice / "memory").resolve() != (bob / "memory").resolve()
    assert json.loads((alice / "config.json").read_text(encoding="utf-8"))["name"] == "Alice"
    assert json.loads((bob / "config.json").read_text(encoding="utf-8"))["name"] == "Bob"
    assert json.loads((default_role / "config.json").read_text(encoding="utf-8"))["preferred_renderer"] == "live2d"
    guide = (alice / "角色配置指南.md").read_text(encoding="utf-8")
    assert "## 配置角色" in guide and "## 1. 配置角色" not in guide


def test_general_settings_exposes_add_character_entry(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    from ui.settings_window import SettingsWindow
    answers = iter([("luna", True), ("露娜", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs: next(answers))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *_args, **_kwargs: ("Live2D 动态模型", True))
    opened = []
    monkeypatch.setattr("ui.settings_window.QDesktopServices.openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: QMessageBox.Ok)
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    window.open_page("general")
    assert window._add_character_btn.text() == "＋ 增加角色"
    window._add_character_btn.click()
    role = tmp_path / "characters" / "luna"
    assert len(opened) == 1 and Path(opened[0]).resolve() == role.resolve()
    assert (role / "角色配置指南.md").exists()
    assert json.loads((role / "config.json").read_text(encoding="utf-8"))["preferred_renderer"] == "live2d"
    window._memory_page.shutdown(); window.close()


@pytest.mark.parametrize("width", [760, 980, 1200])
def test_memory_module_layout_never_exceeds_settings_viewport(qapp, tmp_path, width):
    from PySide6.QtWidgets import QCheckBox, QScrollArea
    from ui.settings_window import SettingsWindow
    (tmp_path / "characters" / "noir").mkdir(parents=True, exist_ok=True)
    window = SettingsWindow(Config(tmp_path / "config.json"), ["noir"], "noir", tmp_path)
    window.resize(width, 720)
    window.show()
    window.open_page("memory")
    qapp.processEvents()
    viewport = window.findChild(QScrollArea).viewport()
    page = window._memory_page
    assert page.width() <= viewport.width()
    assert page.minimumSizeHint().width() <= viewport.width()
    assert not page.findChildren(QCheckBox)
    assert window._page_title.text() == "记忆模块"
    page.shutdown()
    window.close()

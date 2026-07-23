"""Responsive memory dashboard, summary gallery, and long-term memory editor."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHeaderView, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from core.memory import MemoryStore
from ui.theme import (STAR_ACCENT, STAR_BORDER, STAR_SURFACE,
                      STAR_SURFACE_ELEVATED, STAR_TEXT, STAR_TEXT_MUTED)


def _spin(value: int, low: int, high: int) -> QSpinBox:
    widget = QSpinBox()
    widget.setRange(low, high)
    widget.setValue(value)
    widget.setFixedWidth(84)
    return widget


def _button(text: str, slot, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("settings_primary_button" if primary else "settings_secondary_button")
    button.clicked.connect(slot)
    return button


class MemoryStatCard(QFrame):
    clicked = Signal(str)

    def __init__(self, key: str, title: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("memory_stat_card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 11, 13, 10)
        layout.setSpacing(3)
        self.title_label = QLabel(title)
        self.value_label = QLabel("0")
        self.hint_label = QLabel("点击查看  ›")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.hint_label)
        self._restyle(False)

    def _restyle(self, hovered: bool) -> None:
        background = "#26356a" if hovered else STAR_SURFACE_ELEVATED
        border = STAR_ACCENT if hovered else STAR_BORDER
        self.setStyleSheet(
            f"QFrame#memory_stat_card{{background:{background};border:1px solid {border};border-radius:9px;}}"
            f"QLabel{{border:none;background:transparent;color:{STAR_TEXT_MUTED};}}")
        self.value_label.setStyleSheet(f"color:{STAR_TEXT};font-size:22px;font-weight:700;border:none;")
        self.title_label.setStyleSheet(f"color:{STAR_TEXT};font-weight:600;border:none;")
        self.hint_label.setStyleSheet(f"color:{STAR_ACCENT if hovered else STAR_TEXT_MUTED};border:none;")

    def enterEvent(self, event):
        self._restyle(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._restyle(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit(self.key)
        super().mouseReleaseEvent(event)


class FrequencyChart(QWidget):
    """Dependency-free activity chart; bars are chats, line is all messages."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = []
        self.setMinimumHeight(210)

    def set_series(self, values: list[dict]) -> None:
        self.series = values
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = self.rect().adjusted(42, 18, -16, -34)
        painter.setPen(QPen(QColor(STAR_BORDER), 1))
        painter.drawRect(area)
        if not self.series:
            painter.setPen(QColor(STAR_TEXT_MUTED)); painter.drawText(area, Qt.AlignCenter, "暂无陪伴记录")
            return
        maximum = max(1, max(item["messages"] for item in self.series))
        step = area.width() / max(1, len(self.series))
        points = []
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(STAR_ACCENT))
        for index, item in enumerate(self.series):
            height = area.height() * item["chats"] / maximum
            x = area.left() + index * step + step * .18
            painter.drawRoundedRect(x, area.bottom() - height, max(2.0, step * .55), height, 2, 2)
            points.append((area.left() + (index + .5) * step,
                           area.bottom() - area.height() * item["messages"] / maximum))
        painter.setPen(QPen(QColor("#77d5ff"), 2))
        for left, right in zip(points, points[1:]):
            painter.drawLine(*left, *right)
        painter.setPen(QColor(STAR_TEXT_MUTED))
        painter.drawText(4, area.top() + 12, str(maximum))
        painter.drawText(area.left(), self.height() - 8, self.series[0]["date"][5:])
        painter.drawText(area.right() - 34, self.height() - 8, self.series[-1]["date"][5:])


class MemorySettingsPage(QWidget):
    memory_cleared = Signal(str)
    memory_changed = Signal(str)
    section_requested = Signal(str)

    def __init__(self, config, base_dir: Path, character: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.base_dir = Path(base_dir)
        self.character = character
        self.store = MemoryStore(self.base_dir / "characters" / character,
                                 config.get("memory", default={}))
        self.fields: dict[str, QSpinBox] = {}
        self._build()
        self.refresh_all()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(9)

        intro = QLabel(
            "角色记忆默认持续工作。近期对话会逐步整理为摘要和长期事实，并只在相关时用于回复。")
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color:{STAR_TEXT_MUTED};background:{STAR_SURFACE};border:1px solid {STAR_BORDER};"
            "border-radius:8px;padding:9px 12px;")
        root.addWidget(intro)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("memory_sections")
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(f"""
            QTabBar::tab {{ color:{STAR_TEXT_MUTED}; background:transparent; padding:8px 14px;
                            margin-right:2px; font-weight:600; border:none; }}
            QTabBar::tab:hover {{ color:#ffffff; background:#293765; border-radius:7px 7px 0 0; }}
            QTabBar::tab:selected {{ color:#ffffff; background:{STAR_SURFACE_ELEVATED};
                                    border-bottom:3px solid {STAR_ACCENT}; }}
        """)
        self.tabs.addTab(self._build_overview_tab(), "记忆概览")
        self.tabs.addTab(self._build_timeline_tab(), "时间线")
        self.tabs.addTab(self._build_archive_tab(), "日记归档")
        self.tabs.addTab(self._build_summary_tab(), "近期摘要")
        self.tabs.addTab(self._build_facts_tab(), "长期记忆")
        root.addWidget(self.tabs, 1)

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 14)
        layout.setSpacing(11)

        stats_grid = QGridLayout()
        stats_grid.setSpacing(8)
        self.stat_labels = {}; self.stat_cards = {}
        for index, (key, title) in enumerate((
                ("messages", "原始消息"), ("summaries", "近期摘要"),
                ("facts", "长期事实"), ("emotions", "情绪记录"))):
            card = MemoryStatCard(key, title)
            card.clicked.connect(self._on_stat_card)
            stats_grid.addWidget(card, index // 2, index % 2)
            self.stat_labels[key] = card.value_label
            self.stat_cards[key] = card
        layout.addLayout(stats_grid)

        self.engine_status = QLabel()
        self.engine_status.setWordWrap(True)
        self.engine_status.setStyleSheet(f"color:{STAR_ACCENT};font-weight:600;")
        layout.addWidget(self.engine_status)

        parameter_card = QFrame()
        parameter_card.setStyleSheet(
            f"QFrame {{border:1px solid {STAR_BORDER};border-radius:10px;background:{STAR_SURFACE};}}"
            "QLabel{border:none;background:transparent;}")
        form = QGridLayout(parameter_card)
        form.setContentsMargins(14, 13, 14, 13)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        rows = (
            ("recent_turns", "近期原始对话（轮）", 12, 2, 50),
            ("summary_limit", "近期摘要上限", 12, 2, 100),
            ("fact_limit", "长期事实上限", 128, 8, 2000),
            ("retrieval_count", "单轮召回数量", 6, 1, 20),
            ("max_context_chars", "最大注入字符", 2400, 400, 12000),
            ("min_importance", "最低重要度", 2, 1, 5),
        )
        for index, (key, title, default, low, high) in enumerate(rows):
            field = _spin(self.config.get("memory", key, default=default), low, high)
            item = QWidget(); item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0); item_layout.setSpacing(8)
            label = QLabel(title); label.setStyleSheet(f"color:{STAR_TEXT};font-weight:600;")
            item_layout.addWidget(label); item_layout.addStretch(); item_layout.addWidget(field)
            form.addWidget(item, index // 2, index % 2)
            self.fields[key] = field
        form.setColumnStretch(0, 1); form.setColumnStretch(1, 1)
        layout.addWidget(parameter_card)
        layout.addStretch()
        return page

    def _on_stat_card(self, key: str) -> None:
        routes = {"messages": "memory_timeline", "summaries": "memory_recent",
                  "facts": "memory_facts", "emotions": "memory_timeline"}
        self.section_requested.emit(routes[key])

    def _build_timeline_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("陪伴频率"))
        self.timeline_days = QComboBox()
        for title, days in (("最近 7 天", 7), ("最近 30 天", 30), ("最近 90 天", 90), ("最近一年", 365)):
            self.timeline_days.addItem(title, days)
        self.timeline_days.setCurrentIndex(1)
        self.timeline_days.currentIndexChanged.connect(self.refresh_timeline)
        controls.addWidget(self.timeline_days); controls.addStretch()
        controls.addWidget(_button("打开记忆目录", self.open_memory_folder))
        layout.addLayout(controls)
        legend = QLabel("粉色柱：聊天轮数　 蓝色折线：消息总量")
        legend.setStyleSheet(f"color:{STAR_TEXT_MUTED};")
        layout.addWidget(legend)
        self.frequency_chart = FrequencyChart(); layout.addWidget(self.frequency_chart)
        self.timeline_table = QTableWidget(0, 3)
        self.timeline_table.setHorizontalHeaderLabels(("日期", "聊天轮数", "消息数量"))
        self.timeline_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.timeline_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.timeline_table, 1)
        return page

    def _build_archive_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        toolbar = QHBoxLayout(); toolbar.addWidget(QLabel("归档类型"))
        self.archive_kind = QComboBox()
        for title, kind in (("日记", "diary"), ("周记", "weekly"), ("月记", "monthly"),
                            ("季记", "quarterly"), ("年记", "yearly")):
            self.archive_kind.addItem(title, kind)
        self.archive_kind.currentIndexChanged.connect(self.refresh_archives)
        toolbar.addWidget(self.archive_kind); toolbar.addStretch()
        toolbar.addWidget(_button("打开存放位置", self.open_archive_folder))
        toolbar.addWidget(_button("一键导出全部记忆", self.export_bundle, True))
        layout.addLayout(toolbar)
        self.archive_table = QTableWidget(0, 4)
        self.archive_table.setHorizontalHeaderLabels(("时间范围", "对话来源", "更新时间", "标题"))
        self.archive_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.archive_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.archive_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.archive_table.itemSelectionChanged.connect(self._show_archive)
        self.archive_table.cellDoubleClicked.connect(lambda *_: self.open_selected_archive())
        layout.addWidget(self.archive_table, 1)
        self.archive_editor = QTextEdit(); self.archive_editor.setMinimumHeight(150)
        self.archive_editor.setReadOnly(True)
        layout.addWidget(self.archive_editor)
        actions = QHBoxLayout(); actions.addStretch()
        actions.addWidget(_button("打开选中文件", self.open_selected_archive))
        layout.addLayout(actions)
        return page

    def _build_summary_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        toolbar = QGridLayout()
        toolbar.setHorizontalSpacing(7)
        for index, button in enumerate((
                _button("刷新", self.refresh_summaries),
                _button("导入 Markdown", self.import_summaries),
                _button("导出所选", self.export_selected_summaries),
                _button("导出全部", self.export_all_summaries),
                _button("打开选中文件", self.open_selected_summary))):
            toolbar.addWidget(button, index // 2, index % 2)
        layout.addLayout(toolbar)

        self.summary_table = QTableWidget(0, 4)
        self.summary_table.setHorizontalHeaderLabels(("日期范围", "来源", "更新时间", "摘要预览"))
        self.summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.summary_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.summary_table.verticalHeader().setVisible(False)
        header = self.summary_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.summary_table.itemSelectionChanged.connect(self._show_selected_summary)
        self.summary_table.cellDoubleClicked.connect(lambda *_: self.open_selected_summary())
        layout.addWidget(self.summary_table, 1)

        self.summary_meta = QLabel("选择一条摘要查看详情")
        self.summary_meta.setWordWrap(True)
        self.summary_meta.setStyleSheet(f"color:{STAR_TEXT_MUTED};")
        layout.addWidget(self.summary_meta)
        self.summary_editor = QTextEdit()
        self.summary_editor.setPlaceholderText("选择摘要后可在此查看和修改完整内容。")
        self.summary_editor.setMinimumHeight(130)
        layout.addWidget(self.summary_editor)
        layout.addWidget(_button("保存摘要修改", self.save_summary, True), alignment=Qt.AlignRight)
        return page

    def _build_facts_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        filters = QGridLayout()
        filters.setHorizontalSpacing(7)
        filters.setVerticalSpacing(7)
        self.query = QLineEdit(); self.query.setPlaceholderText("搜索长期记忆…")
        self.subject = QComboBox(); self.subject.addItem("全部主体", "")
        for title, value in (("用户", "user"), ("角色", "assistant"), ("其他", "other")):
            self.subject.addItem(title, value)
        self.category = QComboBox(); self.category.addItem("全部分类", "")
        for value in ("闲聊", "爱好", "事实", "计划", "关系", "事件"):
            self.category.addItem(value, value)
        self.period = QComboBox(); self.period.addItem("全部时段", "")
        for value in ("上午", "下午", "晚上"):
            self.period.addItem(value, value)
        self.date = QLineEdit(); self.date.setPlaceholderText("日期 YYYY-MM-DD")
        self.importance = _spin(1, 1, 5); self.importance.setPrefix("重要度 ≥ ")
        self.importance.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.importance.setMaximumWidth(180)
        filter_widgets = (self.query, self.subject, self.category,
                          self.period, self.date, self.importance)
        for index, field in enumerate(filter_widgets):
            field.setProperty("settings_ignore_dirty", True)
            field.setMinimumWidth(80)
            filters.addWidget(field, index // 3, index % 3)
        for column in range(3):
            filters.setColumnStretch(column, 1)
        layout.addLayout(filters)

        self.fact_table = QTableWidget(0, 7)
        self.fact_table.setHorizontalHeaderLabels(("主体", "分类", "重要度", "日期", "时段", "来源", "内容"))
        self.fact_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fact_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.fact_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.fact_table.verticalHeader().setVisible(False)
        self.fact_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        layout.addWidget(self.fact_table, 1)

        actions = QGridLayout()
        action_buttons = (
            _button("刷新", self.refresh_facts), _button("手动添加", self.add_fact),
            _button("编辑所选", self.edit_selected_fact), _button("删除所选", self.delete_selected_fact),
            _button("导入 JSON", self.import_json), _button("导出 JSON", self.export_json),
            _button("清空当前角色记忆", self.clear_memory),
        )
        for index, button in enumerate(action_buttons):
            actions.addWidget(button, index // 3, index % 3)
        layout.addLayout(actions)

        self.query.returnPressed.connect(self.refresh_facts)
        for combo in (self.subject, self.category, self.period):
            combo.currentIndexChanged.connect(self.refresh_facts)
        self.importance.valueChanged.connect(self.refresh_facts)
        return page

    def collect(self) -> dict:
        return {key: field.value() for key, field in self.fields.items()}

    def refresh_all(self) -> None:
        self.refresh_stats()
        self.refresh_timeline()
        self.refresh_archives()
        self.refresh_summaries()
        self.refresh_facts()

    def open_section(self, key: str) -> None:
        mapping = {"memory": 0, "memory_overview": 0, "memory_timeline": 1,
                   "memory_diary": 2, "memory_weekly": 2, "memory_monthly": 2,
                   "memory_quarterly": 2, "memory_yearly": 2,
                   "memory_recent": 3, "memory_facts": 4, "memory_export": 2}
        self.tabs.setCurrentIndex(mapping.get(key, 0))
        archive_kind = key.removeprefix("memory_")
        if archive_kind in {"diary", "weekly", "monthly", "quarterly", "yearly"}:
            index = self.archive_kind.findData(archive_kind)
            if index >= 0:
                self.archive_kind.setCurrentIndex(index)

    def refresh_timeline(self, *_args) -> None:
        if not hasattr(self, "timeline_days"):
            return
        values = self.store.activity_series(int(self.timeline_days.currentData()))
        self.frequency_chart.set_series(values)
        populated = [item for item in reversed(values) if item["messages"]]
        self.timeline_table.setRowCount(len(populated))
        for row, item in enumerate(populated):
            for column, value in enumerate((item["date"], item["chats"], item["messages"])):
                self.timeline_table.setItem(row, column, QTableWidgetItem(str(value)))

    def refresh_archives(self, *_args) -> None:
        if not hasattr(self, "archive_kind"):
            return
        rows = self.store.list_archives(self.archive_kind.currentData())
        self.archive_table.setRowCount(len(rows))
        for index, record in enumerate(rows):
            values = (f"{record['range_start']} 至 {record['range_end']}",
                      str(len(self._json_list(record["source_ids"]))),
                      record["updated_at"], record["title"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, record["id"])
                self.archive_table.setItem(index, column, item)

    def _selected_archive_id(self) -> int | None:
        row = self.archive_table.currentRow() if hasattr(self, "archive_table") else -1
        item = self.archive_table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.UserRole)) if item else None

    def _show_archive(self) -> None:
        record = self.store.get_archive(self._selected_archive_id()) if self._selected_archive_id() else None
        self.archive_editor.setPlainText(record["content"] if record else "")

    def save_archive(self) -> None:
        archive_id = self._selected_archive_id()
        if archive_id and self.store.update_archive(archive_id, self.archive_editor.toPlainText()):
            self.memory_changed.emit(self.character); self.refresh_archives()

    def open_memory_folder(self) -> None:
        self.store.root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root.resolve())))

    def open_archive_folder(self) -> None:
        folder = self.store.archives_dir / str(self.archive_kind.currentData())
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    def open_selected_archive(self) -> None:
        record = self.store.get_archive(self._selected_archive_id()) if self._selected_archive_id() else None
        if record:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str((self.store.root / record["file_path"]).resolve())))

    def export_bundle(self) -> None:
        default = f"{self.character}_memory_{__import__('datetime').date.today().isoformat()}.zip"
        path, _ = QFileDialog.getSaveFileName(self, "一键导出全部记忆", default, "ZIP 压缩包 (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        report = self.store.export_archive(Path(path))
        QMessageBox.information(self, "导出完成",
                                f"已打包 {report['messages']} 条消息、{report['memories']} 条记忆、"
                                f"{report['archives']} 份日历归档。\n{path}")

    def refresh_stats(self) -> None:
        stats = self.store.stats()
        for key, label in self.stat_labels.items():
            label.setText(str(stats[key]))
        if self.store.native_available:
            mode = "Rust 原生混合向量已启用"
        elif self.store.jieba_available:
            mode = "Python/jieba 兼容模式"
        else:
            mode = "Python 字符向量兼容模式"
        self.engine_status.setText(f"检索引擎：{mode}　·　Markdown 摘要正本已启用")

    def refresh_summaries(self, *_args) -> None:
        self.store.sync_summary_files()
        rows = self.store.list_summaries()
        self.summary_table.setRowCount(len(rows))
        for index, record in enumerate(rows):
            source_ids = self._json_list(record.get("source_ids"))
            values = (
                f"{record['range_start']} 至 {record['range_end']}", str(len(source_ids)),
                record.get("manual_updated_at") or record.get("updated_at", ""),
                record["content"].replace("\n", " ")[:100],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, record["id"])
                self.summary_table.setItem(index, column, item)
        self.refresh_stats()

    @staticmethod
    def _json_list(value) -> list:
        if isinstance(value, list):
            return value
        try:
            parsed = __import__("json").loads(value or "[]")
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []

    def _selected_summary_ids(self) -> list[int]:
        ids = []
        for index in self.summary_table.selectionModel().selectedRows(0):
            item = self.summary_table.item(index.row(), 0)
            if item:
                ids.append(int(item.data(Qt.UserRole)))
        return ids

    def _show_selected_summary(self) -> None:
        ids = self._selected_summary_ids()
        if len(ids) != 1:
            self.summary_meta.setText("选择一条摘要查看详情；可多选后批量导出。")
            self.summary_editor.clear()
            return
        record = self.store.get_summary(ids[0])
        if not record:
            return
        sources = self._json_list(record["source_ids"])
        self.summary_meta.setText(
            f"{record['range_start']} 至 {record['range_end']}　·　来源消息 {len(sources)} 条　·　"
            f"生成于 {record['generated_at'] or record['created_at']}　·　ID {record['stable_id']}")
        self.summary_editor.setPlainText(record["content"])

    def save_summary(self) -> None:
        ids = self._selected_summary_ids()
        if len(ids) != 1:
            QMessageBox.information(self, "保存摘要", "请只选择一条摘要。")
            return
        if self.store.update_summary(ids[0], self.summary_editor.toPlainText()):
            self.memory_changed.emit(self.character)
            self.refresh_summaries()

    def open_selected_summary(self) -> None:
        ids = self._selected_summary_ids()
        record = self.store.get_summary(ids[0]) if len(ids) == 1 else None
        if record and record.get("file_path"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(
                str((self.store.root / record["file_path"]).resolve())))

    def import_summaries(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "导入近期摘要", "", "Markdown (*.md *.markdown)")
        if not paths:
            return
        report = self.store.import_summary_markdown(Path(path) for path in paths)
        self.memory_changed.emit(self.character)
        self.refresh_summaries()
        QMessageBox.information(
            self, "摘要导入完成",
            f"新增 {report['imported']}，更新 {report['updated']}，跳过 {report['skipped']}，错误 {report['errors']}。")

    def export_selected_summaries(self) -> None:
        ids = self._selected_summary_ids()
        if not ids:
            QMessageBox.information(self, "导出摘要", "请先选择至少一条摘要。")
            return
        directory = QFileDialog.getExistingDirectory(self, "选择摘要导出目录")
        if directory:
            count = self.store.export_summary_markdown(ids, Path(directory))
            QMessageBox.information(self, "导出完成", f"已导出 {count} 条摘要。")

    def export_all_summaries(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择摘要导出目录")
        if directory:
            ids = [record["id"] for record in self.store.list_summaries()]
            count = self.store.export_summary_markdown(ids, Path(directory))
            QMessageBox.information(self, "导出完成", f"已导出 {count} 条摘要。")

    def refresh_facts(self, *_args) -> None:
        rows = self.store.list_records(
            query=self.query.text().strip(), layer="fact", subject=self.subject.currentData(),
            category=self.category.currentData(), date=self.date.text().strip(),
            period=self.period.currentData(), min_importance=self.importance.value())
        self.fact_table.setRowCount(len(rows))
        labels = {"user": "用户", "assistant": "角色", "other": "其他"}
        for row_index, record in enumerate(rows):
            values = (labels.get(record["subject"], record["subject"]), record["category"],
                      str(record["importance"]), record["memory_date"], record["period"],
                      str(len(self._json_list(record["source_ids"]))), record["content"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, record["id"])
                self.fact_table.setItem(row_index, column, item)
        self.refresh_stats()

    def _selected_fact_id(self) -> int | None:
        row = self.fact_table.currentRow()
        item = self.fact_table.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.UserRole)) if item else None

    def add_fact(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "手动添加记忆", "记忆内容：")
        if ok and text.strip():
            self.store.add_manual_fact(text)
            self.memory_changed.emit(self.character)
            self.refresh_facts()

    def edit_selected_fact(self) -> None:
        memory_id = self._selected_fact_id()
        if memory_id is None:
            QMessageBox.information(self, "编辑记忆", "请先选择一条长期记忆。")
            return
        row = self.fact_table.currentRow()
        current = self.fact_table.item(row, 6).text()
        text, ok = QInputDialog.getMultiLineText(self, "编辑记忆", "记忆内容：", current)
        if not ok:
            return
        importance, ok = QInputDialog.getInt(
            self, "编辑记忆", "重要度（1-5）：", int(self.fact_table.item(row, 2).text()), 1, 5)
        if ok and self.store.update_record(memory_id, text, importance):
            self.memory_changed.emit(self.character)
            self.refresh_facts()

    def delete_selected_fact(self) -> None:
        memory_id = self._selected_fact_id()
        if memory_id is None:
            QMessageBox.information(self, "删除记忆", "请先选择一条长期记忆。")
            return
        if QMessageBox.question(self, "删除记忆", "确定删除选中的长期记忆吗？") == QMessageBox.Yes:
            self.store.delete_record(memory_id)
            self.memory_changed.emit(self.character)
            self.refresh_facts()

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出当前角色完整记忆", f"{self.character}_memory.json", "JSON (*.json)")
        if path:
            self.store.export_json(Path(path))
            QMessageBox.information(self, "导出完成", "当前角色完整记忆已导出。")

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入角色记忆备份", "", "JSON (*.json)")
        if not path:
            return
        report = self.store.import_json(Path(path))
        self.memory_changed.emit(self.character)
        self.refresh_all()
        QMessageBox.information(
            self, "记忆导入完成",
            f"消息 {report['messages']}，记忆 {report['memories']}，情绪 {report['emotions']}，"
            f"跳过 {report['skipped']}，错误 {report['errors']}。")

    def clear_memory(self) -> None:
        answer = QMessageBox.warning(
            self, "清空当前角色记忆",
            "这会删除当前角色的全部记忆、摘要文件、情绪日志和聊天历史，且无法撤销。\n\n确定继续吗？",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return
        self.store.clear_all()
        history = self.base_dir / "characters" / self.character / "chat_history.json"
        try:
            history.unlink(missing_ok=True)
        except OSError:
            pass
        self.memory_cleared.emit(self.character)
        self.refresh_all()

    def shutdown(self) -> None:
        if not getattr(self, "_closed", False):
            self.store.close()
            self._closed = True

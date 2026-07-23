"""SQLite-backed layered memory with dependency-light hybrid retrieval."""

from __future__ import annotations

import json
import re
import hashlib
import shutil
import sqlite3
import threading
import uuid
import zipfile
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .native import NATIVE_AVAILABLE, embed as native_embed, hybrid_rank

try:
    import jieba  # type: ignore
except ImportError:  # Character n-grams remain a useful offline fallback.
    jieba = None


SCHEMA_VERSION = 3
VECTOR_DIM = 2048
CATEGORIES = ("闲聊", "爱好", "事实", "计划", "关系", "事件")
SUBJECTS = ("user", "assistant", "other")


@dataclass(frozen=True)
class MemorySettings:
    enabled: bool = True
    emotion_enabled: bool = True
    smart_filter: bool = True
    recent_turns: int = 12
    summary_limit: int = 12
    fact_limit: int = 128
    retrieval_count: int = 6
    max_context_chars: int = 2400
    min_importance: int = 2

    @classmethod
    def from_dict(cls, value: dict | None) -> "MemorySettings":
        value = value or {}
        bounded = {
            "recent_turns": (2, 50), "summary_limit": (2, 100),
            "fact_limit": (8, 2000), "retrieval_count": (1, 20),
            "max_context_chars": (400, 12000), "min_importance": (1, 5),
        }
        data = {}
        for key in ("enabled", "emotion_enabled", "smart_filter"):
            data[key] = True
        for key, (low, high) in bounded.items():
            try:
                raw = int(value.get(key, getattr(cls(), key)))
            except (TypeError, ValueError):
                raw = getattr(cls(), key)
            data[key] = max(low, min(high, raw))
        return cls(**data)


def _period(dt: datetime) -> str:
    if 5 <= dt.hour < 12:
        return "上午"
    if 12 <= dt.hour < 18:
        return "下午"
    return "晚上"


def parse_time_query(text: str, now: datetime | None = None) -> dict:
    """Resolve common Chinese relative dates and day periods."""
    now = now or datetime.now()
    date = None
    offsets = (("大前天", -3), ("前天", -2), ("昨天", -1), ("今天", 0))
    for token, offset in offsets:
        if token in text:
            date = (now + timedelta(days=offset)).date().isoformat()
            break
    if date is None:
        match = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})日?", text)
        if match:
            try:
                date = datetime(*map(int, match.groups())).date().isoformat()
            except ValueError:
                pass
    periods = [name for name in ("上午", "下午", "晚上") if name in text]
    if any(word in text for word in ("早上", "早晨")) and "上午" not in periods:
        periods.append("上午")
    if any(word in text for word in ("中午", "午后")) and "下午" not in periods:
        periods.append("下午")
    if any(word in text for word in ("夜里", "今晚", "凌晨")) and "晚上" not in periods:
        periods.append("晚上")
    return {"date": date, "periods": periods}


def _tokens(text: str) -> list[str]:
    text = (text or "").strip().lower()
    if not text:
        return []
    values = []
    if jieba is not None:
        values.extend(word.strip() for word in jieba.lcut(text) if word.strip())
    values.extend(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text))
    values.extend(text[i:i + 2] for i in range(len(text) - 1)
                  if "\u4e00" <= text[i] <= "\u9fff" and "\u4e00" <= text[i + 1] <= "\u9fff")
    return list(dict.fromkeys(values))


def _embedding(text: str) -> list[tuple[int, float]]:
    if NATIVE_AVAILABLE:
        return native_embed(text)
    return native_embed(text, _tokens(text))


def _cosine(left: list, right: list) -> float:
    a = {int(k): float(v) for k, v in left}
    return sum(value * dict((int(k), float(v)) for k, v in right).get(key, 0.0)
               for key, value in a.items())


class MemoryStore:
    """Owns one character's layered memory database."""

    def __init__(self, character_dir: Path, settings: MemorySettings | dict | None = None):
        self.character_dir = Path(character_dir)
        self.root = self.character_dir / "memory"
        self.summaries_dir = self.root / "summaries"
        self.archives_dir = self.root / "archives"
        self.root.mkdir(parents=True, exist_ok=True)
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        self.archives_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "memory.db"
        self.settings = settings if isinstance(settings, MemorySettings) else MemorySettings.from_dict(settings)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=3000")
        self._init_schema()
        self._ensure_embedding_engine()
        self.sync_summary_files()
        self._ensure_calendar_archives()

    @property
    def jieba_available(self) -> bool:
        return jieba is not None

    @property
    def native_available(self) -> bool:
        return NATIVE_AVAILABLE

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def update_settings(self, settings: MemorySettings | dict) -> None:
        self.settings = settings if isinstance(settings, MemorySettings) else MemorySettings.from_dict(settings)

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, content TEXT NOT NULL,
                    mood TEXT NOT NULL DEFAULT '平静', created_at TEXT NOT NULL, memory_date TEXT NOT NULL,
                    period TEXT NOT NULL, summarized INTEGER NOT NULL DEFAULT 0,
                    importance INTEGER NOT NULL DEFAULT 1, subject TEXT NOT NULL DEFAULT 'other',
                    category TEXT NOT NULL DEFAULT '闲聊', keywords TEXT NOT NULL DEFAULT '[]',
                    source_ids TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE IF NOT EXISTS memories(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, layer TEXT NOT NULL, content TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 2, subject TEXT NOT NULL DEFAULT 'other',
                    category TEXT NOT NULL DEFAULT '事实', keywords TEXT NOT NULL DEFAULT '[]',
                    source_ids TEXT NOT NULL DEFAULT '[]', embedding TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, memory_date TEXT NOT NULL,
                    period TEXT NOT NULL, range_start TEXT NOT NULL DEFAULT '',
                    range_end TEXT NOT NULL DEFAULT '', recalled_at TEXT,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    stable_id TEXT NOT NULL DEFAULT '', file_path TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL DEFAULT '', generated_at TEXT NOT NULL DEFAULT '',
                    manual_updated_at TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS emotion_log(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, mood TEXT NOT NULL, intensity INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '', source_message_id INTEGER, created_at TEXT NOT NULL,
                    memory_date TEXT NOT NULL, period TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS archives(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, stable_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
                    range_start TEXT NOT NULL, range_end TEXT NOT NULL,
                    source_ids TEXT NOT NULL DEFAULT '[]', file_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL, generated_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_messages_unsummarized ON messages(summarized, id);
                CREATE INDEX IF NOT EXISTS idx_memories_layer_date ON memories(layer, memory_date, period);
                CREATE INDEX IF NOT EXISTS idx_archives_kind_range ON archives(kind, range_start, range_end);
            """)
            self.conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_version',?)",
                              (str(SCHEMA_VERSION),))
        self._migrate_columns()

    def _migrate_columns(self) -> None:
        additions = {
            "messages": {"importance": "INTEGER NOT NULL DEFAULT 1", "subject": "TEXT NOT NULL DEFAULT 'other'",
                         "category": "TEXT NOT NULL DEFAULT '闲聊'", "keywords": "TEXT NOT NULL DEFAULT '[]'",
                         "source_ids": "TEXT NOT NULL DEFAULT '[]'"},
            "memories": {
                "range_start": "TEXT NOT NULL DEFAULT ''", "range_end": "TEXT NOT NULL DEFAULT ''",
                "stable_id": "TEXT NOT NULL DEFAULT ''", "file_path": "TEXT NOT NULL DEFAULT ''",
                "content_hash": "TEXT NOT NULL DEFAULT ''", "generated_at": "TEXT NOT NULL DEFAULT ''",
                "manual_updated_at": "TEXT NOT NULL DEFAULT ''",
            },
        }
        with self.conn:
            for table, columns in additions.items():
                existing = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
                for name, declaration in columns.items():
                    if name not in existing:
                        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
            self.conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_stable_id "
                "ON memories(stable_id) WHERE stable_id<>''")
            rows = self.conn.execute(
                "SELECT id,content,created_at FROM memories WHERE stable_id='' OR content_hash=''"
            ).fetchall()
            namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(self.character_dir.resolve()))
            for row in rows:
                stable_id = str(uuid.uuid5(namespace, f"memory:{row['id']}"))
                self.conn.execute(
                    "UPDATE memories SET stable_id=?,content_hash=?,generated_at=? WHERE id=?",
                    (stable_id, self._content_hash(row["content"]), row["created_at"], row["id"]))

    def _ensure_embedding_engine(self) -> None:
        engine = "rust-blake3-v1" if NATIVE_AVAILABLE else "python-blake2-v1"
        if self.meta("embedding_engine") == engine:
            return
        with self._lock, self.conn:
            rows = self.conn.execute("SELECT id,content FROM memories").fetchall()
            for row in rows:
                self.conn.execute("UPDATE memories SET embedding=? WHERE id=?",
                                  (json.dumps(_embedding(row["content"])), row["id"]))
            self.conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('embedding_engine',?)",
                              (engine,))

    def add_turn(self, user_text: str, assistant_text: str, mood: str = "平静",
                 when: datetime | None = None) -> tuple[int, int]:
        when = when or datetime.now()
        values = (when.isoformat(timespec="seconds"), when.date().isoformat(), _period(when))
        with self._lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO messages(role,content,mood,created_at,memory_date,period,subject) VALUES(?,?,?,?,?,?,?)",
                ("user", user_text, "", *values, "user"))
            user_id = cur.lastrowid
            cur = self.conn.execute(
                "INSERT INTO messages(role,content,mood,created_at,memory_date,period,subject) VALUES(?,?,?,?,?,?,?)",
                ("assistant", assistant_text, mood, *values, "assistant"))
            result = (int(user_id), int(cur.lastrowid))
        self.refresh_calendar_archives(when.date().isoformat())
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('archive_source_max',?)",
                              (str(result[1]),))
        return result

    def import_history_once(self, messages: Iterable[dict]) -> int:
        if self.meta("history_imported") == "1":
            return 0
        items = [item for item in messages if item.get("role") in ("user", "assistant") and item.get("content")]
        now = datetime.now()
        with self._lock, self.conn:
            for index, item in enumerate(items):
                dt = now - timedelta(seconds=len(items) - index)
                self.conn.execute(
                    "INSERT INTO messages(role,content,mood,created_at,memory_date,period,subject) VALUES(?,?,?,?,?,?,?)",
                    (item["role"], item["content"], "", dt.isoformat(timespec="seconds"),
                     dt.date().isoformat(), _period(dt), item["role"]))
            self.conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('history_imported','1')")
        for day in {item["memory_date"] for item in self.conn.execute("SELECT DISTINCT memory_date FROM messages")}:
            self.refresh_calendar_archives(day)
        maximum = self.conn.execute("SELECT COALESCE(MAX(id),0) FROM messages").fetchone()[0]
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('archive_source_max',?)",
                              (str(maximum),))
        return len(items)

    def meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _as_list(value) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

    def _summary_file_name(self, row: dict | sqlite3.Row) -> str:
        start = (row["range_start"] or row["memory_date"] or datetime.now().date().isoformat())
        stable_id = row["stable_id"] or str(uuid.uuid4())
        return f"{start}_{stable_id[:8]}.md"

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict, str]:
        cleaned = text.lstrip("\ufeff")
        if not cleaned.startswith("---\n") and not cleaned.startswith("---\r\n"):
            return {}, cleaned.strip()
        match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", cleaned, re.S)
        if not match:
            return {}, cleaned.strip()
        metadata = {}
        for line in match.group(1).splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue
            value = value.strip()
            if value.startswith("[") or value.startswith("{"):
                try:
                    metadata[key.strip()] = json.loads(value)
                    continue
                except json.JSONDecodeError:
                    pass
            metadata[key.strip()] = value
        return metadata, match.group(2).strip()

    def _summary_markdown(self, row: dict | sqlite3.Row) -> str:
        source_ids = row["source_ids"] or "[]"
        if not isinstance(source_ids, str):
            source_ids = json.dumps(source_ids, ensure_ascii=False)
        header = {
            "id": row["stable_id"], "start_date": row["range_start"] or row["memory_date"],
            "end_date": row["range_end"] or row["memory_date"], "source_ids": source_ids,
            "importance": row["importance"], "subject": row["subject"],
            "category": row["category"], "generated_at": row["generated_at"] or row["created_at"],
            "updated_at": row["manual_updated_at"] or row["updated_at"],
            "content_hash": self._content_hash(row["content"]),
        }
        lines = []
        for key, value in header.items():
            if key == "source_ids":
                lines.append(f"{key}: {value}")
            else:
                lines.append(f"{key}: {value}")
        return "---\n" + "\n".join(lines) + "\n---\n\n" + row["content"].strip() + "\n"

    def _write_summary_file(self, memory_id: int, destination: Path | None = None) -> Path:
        row = self.conn.execute("SELECT * FROM memories WHERE id=? AND layer='summary'", (memory_id,)).fetchone()
        if not row:
            raise ValueError("摘要不存在")
        target = Path(destination) if destination else self.summaries_dir / self._summary_file_name(row)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(self._summary_markdown(row), encoding="utf-8")
        temporary.replace(target)
        if destination is None:
            with self.conn:
                self.conn.execute("UPDATE memories SET file_path=?,content_hash=? WHERE id=?",
                                  (str(target.relative_to(self.root)), self._content_hash(row["content"]), memory_id))
        return target

    def sync_summary_files(self) -> dict[str, int]:
        """Materialize legacy DB summaries, then index Markdown changes."""
        report = {"created": 0, "updated": 0, "imported": 0, "skipped": 0}
        with self._lock:
            rows = self.conn.execute("SELECT * FROM memories WHERE layer='summary' ORDER BY id").fetchall()
            for row in rows:
                path = self.root / row["file_path"] if row["file_path"] else None
                if not path or not path.exists():
                    self._write_summary_file(row["id"])
                    report["created"] += 1
            for path in sorted(self.summaries_dir.rglob("*.md")):
                try:
                    metadata, content = self._parse_frontmatter(path.read_text(encoding="utf-8-sig"))
                except OSError:
                    report["skipped"] += 1
                    continue
                if not content:
                    report["skipped"] += 1
                    continue
                stable_id = str(metadata.get("id") or uuid.uuid4())
                existing = self.conn.execute(
                    "SELECT * FROM memories WHERE stable_id=?", (stable_id,)).fetchone()
                digest = self._content_hash(content)
                relative = str(path.relative_to(self.root))
                now = datetime.now()
                if existing:
                    if digest != existing["content_hash"] or relative != existing["file_path"]:
                        with self.conn:
                            self.conn.execute("""
                                UPDATE memories SET content=?,embedding=?,file_path=?,content_hash=?,
                                    updated_at=?,manual_updated_at=?,range_start=?,range_end=? WHERE id=?""", (
                                content, json.dumps(_embedding(content)), relative, digest,
                                now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"),
                                metadata.get("start_date") or existing["range_start"],
                                metadata.get("end_date") or existing["range_end"], existing["id"]))
                        report["updated"] += 1
                    else:
                        report["skipped"] += 1
                    continue
                data = {
                    "content": content, "importance": metadata.get("importance", 2),
                    "subject": metadata.get("subject", "other"), "category": metadata.get("category", "事件"),
                    "source_ids": metadata.get("source_ids", []),
                    "range_start": metadata.get("start_date", now.date().isoformat()),
                    "range_end": metadata.get("end_date", now.date().isoformat()),
                    "stable_id": stable_id, "file_path": relative,
                    "generated_at": metadata.get("generated_at", now.isoformat(timespec="seconds")),
                    "manual_updated_at": metadata.get("updated_at", ""),
                }
                memory_id = self._insert_memory("summary", data, now, write_summary_file=False)
                self._write_summary_file(memory_id, path)
                report["imported"] += 1
        return report

    def list_summaries(self, limit: int = 200) -> list[dict]:
        return [dict(row) for row in self.conn.execute(
            "SELECT * FROM memories WHERE layer='summary' ORDER BY range_end DESC,id DESC LIMIT ?", (limit,))]

    def get_summary(self, memory_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM memories WHERE id=? AND layer='summary'", (memory_id,)).fetchone()
        return dict(row) if row else None

    def update_summary(self, memory_id: int, content: str) -> bool:
        content = content.strip()
        if not content:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        with self.conn:
            cur = self.conn.execute("""
                UPDATE memories SET content=?,embedding=?,content_hash=?,updated_at=?,manual_updated_at=?
                WHERE id=? AND layer='summary'""", (
                content, json.dumps(_embedding(content)), self._content_hash(content), now, now, memory_id))
        if cur.rowcount:
            self._write_summary_file(memory_id)
        return bool(cur.rowcount)

    def import_summary_markdown(self, paths: Iterable[Path]) -> dict[str, int]:
        report = {"imported": 0, "updated": 0, "skipped": 0, "errors": 0}
        for source in paths:
            source = Path(source)
            try:
                metadata, content = self._parse_frontmatter(source.read_text(encoding="utf-8-sig"))
                if not content:
                    report["skipped"] += 1
                    continue
                stable_id = str(metadata.get("id") or uuid.uuid4())
                destination = self.summaries_dir / f"{metadata.get('start_date', datetime.now().date().isoformat())}_{stable_id[:8]}.md"
                existing = self.conn.execute("SELECT id,content_hash FROM memories WHERE stable_id=?", (stable_id,)).fetchone()
                if existing and existing["content_hash"] != self._content_hash(content):
                    # Safe merge: the local version wins on an ID conflict.
                    report["skipped"] += 1
                    continue
                if existing:
                    report["skipped"] += 1
                    continue
                if metadata:
                    shutil.copy2(source, destination)
                else:
                    destination.write_text(content, encoding="utf-8")
                sync = self.sync_summary_files()
                report["imported"] += sync["imported"]
                report["updated"] += sync["updated"]
            except (OSError, ValueError, sqlite3.Error):
                report["errors"] += 1
        return report

    def export_summary_markdown(self, memory_ids: Iterable[int], directory: Path) -> int:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        count = 0
        for memory_id in memory_ids:
            row = self.get_summary(int(memory_id))
            if not row:
                continue
            self._write_summary_file(int(memory_id), directory / self._summary_file_name(row))
            count += 1
        return count

    def latest_mood(self) -> str:
        row = self.conn.execute("SELECT mood FROM emotion_log ORDER BY id DESC LIMIT 1").fetchone()
        return str(row[0]) if row else ""

    def pending_summary(self) -> dict | None:
        threshold = self.settings.recent_turns * 2
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE summarized=0 ORDER BY id DESC").fetchall()
        if len(rows) <= threshold:
            return None
        # Archive six complete oldest turns at a time.
        batch = list(reversed(rows))[:12]
        prior = self.conn.execute(
            "SELECT content FROM memories WHERE layer='summary' ORDER BY id DESC LIMIT 1").fetchone()
        summary_count = self.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE layer='summary'").fetchone()[0]
        oldest_summary = self.conn.execute(
            "SELECT id,content FROM memories WHERE layer='summary' ORDER BY id LIMIT 1").fetchone() \
            if summary_count >= self.settings.summary_limit else None
        return {"messages": [dict(row) for row in batch], "previous_summary": prior[0] if prior else "",
                "summary_to_compress": dict(oldest_summary) if oldest_summary else None}

    def apply_analysis(self, analysis: dict, assistant_message_id: int | None = None) -> None:
        mood = str(analysis.get("mood") or "平静")[:30]
        intensity = max(1, min(5, int(analysis.get("intensity", 2) or 2)))
        now = datetime.now()
        with self._lock, self.conn:
            self.conn.execute(
                "INSERT INTO emotion_log(mood,intensity,note,source_message_id,created_at,memory_date,period) VALUES(?,?,?,?,?,?,?)",
                (mood, intensity, str(analysis.get("emotion_note", ""))[:300], assistant_message_id,
                 now.isoformat(timespec="seconds"), now.date().isoformat(), _period(now)))
            if assistant_message_id:
                self.conn.execute(
                    "UPDATE messages SET mood=?,importance=?,category=?,keywords=? WHERE id=?",
                    (mood, max(1, min(5, int(analysis.get("importance", 2) or 2))),
                     analysis.get("category") if analysis.get("category") in CATEGORIES else "闲聊",
                     json.dumps(analysis.get("keywords", []), ensure_ascii=False), assistant_message_id))
            summary = analysis.get("summary")
            source_ids = analysis.get("summary_source_ids", [])
            if summary and source_ids:
                source_rows = self.conn.execute(
                    f"SELECT memory_date,period FROM messages WHERE id IN ({','.join('?' for _ in source_ids)}) ORDER BY id",
                    source_ids).fetchall()
                self._insert_memory("summary", {
                    "content": summary, "importance": analysis.get("importance", 2),
                    "subject": "other", "category": "事件", "keywords": analysis.get("keywords", []),
                    "source_ids": source_ids,
                    "range_start": source_rows[0]["memory_date"] if source_rows else now.date().isoformat(),
                    "range_end": source_rows[-1]["memory_date"] if source_rows else now.date().isoformat(),
                }, now)
                placeholders = ",".join("?" for _ in source_ids)
                self.conn.execute(f"UPDATE messages SET summarized=1 WHERE id IN ({placeholders})", source_ids)
                compressed_ids = analysis.get("compressed_summary_ids", [])
                long_facts = analysis.get("long_term_facts", [])
                if compressed_ids and long_facts:
                    marks = ",".join("?" for _ in compressed_ids)
                    compressed_rows = self.conn.execute(
                        f"SELECT source_ids,range_start,range_end FROM memories "
                        f"WHERE layer='summary' AND id IN ({marks})", compressed_ids).fetchall()
                    original_sources, range_starts, range_ends = [], [], []
                    for row in compressed_rows:
                        original_sources.extend(json.loads(row["source_ids"] or "[]"))
                        range_starts.append(row["range_start"])
                        range_ends.append(row["range_end"])
                    for fact in long_facts:
                        if isinstance(fact, str):
                            fact = {"content": fact}
                        if isinstance(fact, dict) and fact.get("content"):
                            fact["source_ids"] = list(dict.fromkeys(original_sources))
                            fact["range_start"] = min(filter(None, range_starts), default=now.date().isoformat())
                            fact["range_end"] = max(filter(None, range_ends), default=now.date().isoformat())
                            self._insert_memory("fact", fact, now)
                    for memory_id in compressed_ids:
                        self._delete_summary_file(int(memory_id))
                    self.conn.execute(f"DELETE FROM memories WHERE layer='summary' AND id IN ({marks})",
                                      compressed_ids)
                self._promote_old_summaries(now)
            self._enforce_limits(now)

    def _promote_old_summaries(self, now: datetime) -> None:
        rows = self.conn.execute(
            "SELECT id FROM memories WHERE layer='summary' ORDER BY id DESC").fetchall()
        for row in rows[self.settings.summary_limit:]:
            self._delete_summary_file(row["id"])
            self.conn.execute(
                "UPDATE memories SET layer='fact',category='事实',updated_at=? WHERE id=?",
                (now.isoformat(timespec="seconds"), row["id"]))

    def _insert_memory(self, layer: str, data: dict, now: datetime,
                       write_summary_file: bool = True) -> int:
        content = str(data.get("content", "")).strip()
        importance = max(1, min(5, int(data.get("importance", 2) or 2)))
        subject = data.get("subject") if data.get("subject") in SUBJECTS else "other"
        category = data.get("category") if data.get("category") in CATEGORIES else "事实"
        keywords = data.get("keywords", []) if isinstance(data.get("keywords", []), list) else []
        source_ids = data.get("source_ids", []) if isinstance(data.get("source_ids", []), list) else []
        stable_id = str(data.get("stable_id") or uuid.uuid4())
        generated_at = str(data.get("generated_at") or now.isoformat(timespec="seconds"))
        manual_updated_at = str(data.get("manual_updated_at") or "")
        cur = self.conn.execute("""
            INSERT INTO memories(layer,content,importance,subject,category,keywords,source_ids,embedding,
                                 created_at,updated_at,memory_date,period,range_start,range_end,
                                 stable_id,file_path,content_hash,generated_at,manual_updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                layer, content, importance, subject, category,
                json.dumps(keywords, ensure_ascii=False), json.dumps(source_ids),
                json.dumps(_embedding(content), ensure_ascii=False), now.isoformat(timespec="seconds"),
                now.isoformat(timespec="seconds"), now.date().isoformat(), _period(now),
                data.get("range_start", now.date().isoformat()),
                data.get("range_end", now.date().isoformat()), stable_id,
                str(data.get("file_path") or ""), self._content_hash(content),
                generated_at, manual_updated_at))
        memory_id = int(cur.lastrowid)
        if layer == "summary" and write_summary_file:
            self._write_summary_file(memory_id)
        return memory_id

    def _delete_summary_file(self, memory_id: int) -> None:
        row = self.conn.execute(
            "SELECT file_path FROM memories WHERE id=? AND layer='summary'", (memory_id,)).fetchone()
        if row and row["file_path"]:
            try:
                (self.root / row["file_path"]).unlink(missing_ok=True)
            except OSError:
                pass

    def _enforce_limits(self, now: datetime) -> None:
        for layer, limit in (("summary", self.settings.summary_limit), ("fact", self.settings.fact_limit)):
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE layer=? ORDER BY id", (layer,)).fetchall()
            while len(rows) > limit:
                first, second = rows[0], rows[1]
                if layer == "summary":
                    self._delete_summary_file(first["id"])
                merged = f"{first['content']}；{second['content']}"
                sources = json.loads(first["source_ids"] or "[]") + json.loads(second["source_ids"] or "[]")
                self.conn.execute(
                    "UPDATE memories SET content=?,source_ids=?,embedding=?,updated_at=? WHERE id=?",
                    (merged[:1200], json.dumps(list(dict.fromkeys(sources))),
                     json.dumps(_embedding(merged[:1200])), now.isoformat(timespec="seconds"), second["id"]))
                self.conn.execute("DELETE FROM memories WHERE id=?", (first["id"],))
                if layer == "summary":
                    self._write_summary_file(second["id"])
                rows = rows[1:]

    def search(self, query: str, exclude_ids: set[int] | None = None, **filters) -> list[dict]:
        exclude_ids = exclude_ids or set()
        visible_message_ids = set(filters.get("visible_message_ids") or ())
        time_filter = parse_time_query(query)
        date = filters.get("date") or time_filter["date"]
        periods = filters.get("periods") or time_filter["periods"]
        query_emb, terms = _embedding(query), _tokens(query)
        rows = self.conn.execute("SELECT * FROM memories ORDER BY id DESC").fetchall()
        candidates = []
        for row in rows:
            if row["id"] in exclude_ids or row["importance"] < self.settings.min_importance:
                continue
            if visible_message_ids:
                try:
                    sources = set(json.loads(row["source_ids"] or "[]"))
                except (json.JSONDecodeError, TypeError):
                    sources = set()
                if sources & visible_message_ids:
                    continue
            if date and not ((row["range_start"] or row["memory_date"]) <= date
                             <= (row["range_end"] or row["memory_date"])):
                continue
            if periods and row["period"] not in periods:
                continue
            if filters.get("layer") and row["layer"] != filters["layer"]:
                continue
            if filters.get("subject") and row["subject"] != filters["subject"]:
                continue
            if filters.get("category") and row["category"] != filters["category"]:
                continue
            lowered = row["content"].lower()
            keyword = sum(lowered.count(term) for term in terms) / max(1, len(terms))
            candidates.append((row, json.loads(row["embedding"] or "[]"), keyword))
        scores = hybrid_rank(
            query_emb, [item[1] for item in candidates], [item[2] for item in candidates],
            [item[0]["importance"] for item in candidates])
        ranked = [(score, dict(candidates[index][0])) for index, score in scores
                  if score > 0 or date]
        result, chars = [], 0
        for _, item in ranked:
            if len(result) >= self.settings.retrieval_count:
                break
            if chars + len(item["content"]) > self.settings.max_context_chars:
                continue
            item["source_messages"] = self._source_messages(item)
            result.append(item)
            chars += len(item["content"])
        if result:
            ids = [item["id"] for item in result]
            placeholders = ",".join("?" for _ in ids)
            with self.conn:
                self.conn.execute(
                    f"UPDATE memories SET recalled_at=?,access_count=access_count+1 WHERE id IN ({placeholders})",
                    (datetime.now().isoformat(timespec="seconds"), *ids))
        return result

    def _source_messages(self, memory: dict) -> list[dict]:
        ids = json.loads(memory.get("source_ids") or "[]")
        if not ids:
            return []
        expanded = set()
        for value in ids:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            expanded.update((max(1, value - 1), value, value + 1))
        placeholders = ",".join("?" for _ in expanded)
        return [dict(row) for row in self.conn.execute(
            f"SELECT id,role,content,created_at FROM messages WHERE id IN ({placeholders}) ORDER BY id", tuple(expanded))]

    def recent_messages(self, turns: int | None = None) -> list[dict]:
        limit = (turns or self.settings.recent_turns) * 2
        rows = self.conn.execute("SELECT * FROM messages WHERE summarized=0 ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def visible_message_ids(self) -> set[int]:
        rows = self.conn.execute(
            "SELECT id FROM messages ORDER BY id DESC LIMIT ?", (self.settings.recent_turns * 2,)).fetchall()
        return {int(row["id"]) for row in rows}

    @staticmethod
    def _archive_ranges(day: str) -> dict[str, tuple[str, str]]:
        value = datetime.fromisoformat(day).date()
        monday = value - timedelta(days=value.weekday())
        quarter_month = ((value.month - 1) // 3) * 3 + 1
        quarter_start = value.replace(month=quarter_month, day=1)
        quarter_end_month = quarter_month + 2
        return {
            "diary": (value.isoformat(), value.isoformat()),
            "weekly": (monday.isoformat(), (monday + timedelta(days=6)).isoformat()),
            "monthly": (value.replace(day=1).isoformat(),
                        value.replace(day=monthrange(value.year, value.month)[1]).isoformat()),
            "quarterly": (quarter_start.isoformat(),
                          value.replace(month=quarter_end_month,
                                        day=monthrange(value.year, quarter_end_month)[1]).isoformat()),
            "yearly": (value.replace(month=1, day=1).isoformat(),
                       value.replace(month=12, day=31).isoformat()),
        }

    @staticmethod
    def _archive_kind_label(kind: str) -> str:
        return {"diary": "日记", "weekly": "周记", "monthly": "月记",
                "quarterly": "季记", "yearly": "年记"}.get(kind, kind)

    def _archive_markdown(self, row: dict | sqlite3.Row) -> str:
        return ("---\n"
                f"id: {row['stable_id']}\nkind: {row['kind']}\n"
                f"start_date: {row['range_start']}\nend_date: {row['range_end']}\n"
                f"source_ids: {row['source_ids']}\n"
                f"generated_at: {row['generated_at']}\nupdated_at: {row['updated_at']}\n"
                "---\n\n" + row["content"].strip() + "\n")

    def _ensure_calendar_archives(self) -> None:
        maximum = int(self.conn.execute("SELECT COALESCE(MAX(id),0) FROM messages").fetchone()[0])
        if (self.meta("archive_source_max", "0") == str(maximum)
                and self.meta("archive_format_version", "0") == "2"):
            return
        days = [row[0] for row in self.conn.execute(
            "SELECT DISTINCT memory_date FROM messages ORDER BY memory_date")]
        for day in days:
            self.refresh_calendar_archives(str(day))
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('archive_source_max',?)",
                              (str(maximum),))
            self.conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('archive_format_version','2')")

    def refresh_calendar_archives(self, day: str | None = None) -> int:
        """Incrementally materialize human-readable calendar summaries."""
        day = day or datetime.now().date().isoformat()
        changed = 0
        with self._lock, self.conn:
            for kind, (start, end) in self._archive_ranges(day).items():
                messages = self.conn.execute(
                    "SELECT id,role,content,memory_date,period FROM messages "
                    "WHERE memory_date BETWEEN ? AND ? ORDER BY id", (start, end)).fetchall()
                if not messages:
                    continue
                source_ids = [int(row["id"]) for row in messages]
                active_days = len({row["memory_date"] for row in messages})
                turns = sum(1 for row in messages if row["role"] == "user")
                excerpts = []
                for row in messages[-40:]:
                    speaker = "我" if row["role"] == "assistant" else "用户"
                    excerpts.append(f"- {row['memory_date']} {row['period']} · {speaker}：{row['content'][:240]}")
                label = self._archive_kind_label(kind)
                title = f"{start} {label}" if start == end else f"{start} 至 {end} {label}"
                content = (f"# {title}\n\n本周期陪伴 {active_days} 天，共完成 {turns} 轮对话。\n\n"
                           "## 对话记录摘要\n\n" + "\n".join(excerpts))
                stable_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                           f"{self.character_dir.resolve()}:{kind}:{start}:{end}"))
                relative = Path("archives") / kind / start[:4] / f"{start}.md"
                now = datetime.now().isoformat(timespec="seconds")
                existing = self.conn.execute(
                    "SELECT id,generated_at FROM archives WHERE stable_id=?", (stable_id,)).fetchone()
                digest = self._content_hash(content)
                if existing:
                    self.conn.execute(
                        "UPDATE archives SET title=?,content=?,source_ids=?,file_path=?,content_hash=?,updated_at=? WHERE id=?",
                        (title, content, json.dumps(source_ids), str(relative), digest, now, existing["id"]))
                else:
                    self.conn.execute(
                        "INSERT INTO archives(stable_id,kind,title,content,range_start,range_end,source_ids,file_path,content_hash,generated_at,updated_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (stable_id, kind, title, content, start, end, json.dumps(source_ids),
                         str(relative), digest, now, now))
                row = self.conn.execute("SELECT * FROM archives WHERE stable_id=?", (stable_id,)).fetchone()
                target = self.root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(self._archive_markdown(row), encoding="utf-8")
                changed += 1
        return changed

    def list_archives(self, kind: str = "", limit: int = 500) -> list[dict]:
        if kind:
            rows = self.conn.execute(
                "SELECT * FROM archives WHERE kind=? ORDER BY range_start DESC LIMIT ?", (kind, limit))
        else:
            rows = self.conn.execute("SELECT * FROM archives ORDER BY range_start DESC,kind LIMIT ?", (limit,))
        return [dict(row) for row in rows]

    def get_archive(self, archive_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM archives WHERE id=?", (archive_id,)).fetchone()
        return dict(row) if row else None

    def update_archive(self, archive_id: int, content: str) -> bool:
        content = content.strip()
        if not content:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        with self.conn:
            cur = self.conn.execute(
                "UPDATE archives SET content=?,content_hash=?,updated_at=? WHERE id=?",
                (content, self._content_hash(content), now, archive_id))
            row = self.conn.execute("SELECT * FROM archives WHERE id=?", (archive_id,)).fetchone()
        if row:
            (self.root / row["file_path"]).write_text(self._archive_markdown(row), encoding="utf-8")
        return bool(cur.rowcount)

    def activity_series(self, days: int = 30, end_date: str | None = None) -> list[dict]:
        end = datetime.fromisoformat(end_date).date() if end_date else datetime.now().date()
        start = end - timedelta(days=max(1, days) - 1)
        counts = {row["memory_date"]: dict(row) for row in self.conn.execute(
            "SELECT memory_date, SUM(role='user') AS chats, COUNT(*) AS messages "
            "FROM messages WHERE memory_date BETWEEN ? AND ? GROUP BY memory_date",
            (start.isoformat(), end.isoformat()))}
        return [{"date": (start + timedelta(days=index)).isoformat(),
                 "chats": int(counts.get((start + timedelta(days=index)).isoformat(), {}).get("chats", 0)),
                 "messages": int(counts.get((start + timedelta(days=index)).isoformat(), {}).get("messages", 0))}
                for index in range(days)]

    def export_archive(self, path: Path) -> dict[str, int]:
        """Create a portable ZIP containing JSON, Markdown sources and a manifest."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "character": self.character_dir.name,
            "messages": [dict(row) for row in self.conn.execute("SELECT * FROM messages ORDER BY id")],
            "memories": [dict(row) for row in self.conn.execute("SELECT * FROM memories ORDER BY id")],
            "emotions": [dict(row) for row in self.conn.execute("SELECT * FROM emotion_log ORDER BY id")],
            "archives": [dict(row) for row in self.conn.execute("SELECT * FROM archives ORDER BY id")],
        }
        files = [item for folder in (self.summaries_dir, self.archives_dir)
                 for item in folder.rglob("*.md")]
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.writestr("memory.json", json.dumps(payload, ensure_ascii=False, indent=2))
            bundle.writestr("README.txt", "Moepet 角色记忆备份：memory.json 为完整索引，Markdown 为人工可读正本。\n")
            for item in files:
                bundle.write(item, item.relative_to(self.root).as_posix())
        return {"messages": len(payload["messages"]), "memories": len(payload["memories"]),
                "emotions": len(payload["emotions"]), "archives": len(payload["archives"]),
                "files": len(files) + 2}

    def stats(self) -> dict[str, int]:
        return {
            "messages": self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            "summaries": self.conn.execute("SELECT COUNT(*) FROM memories WHERE layer='summary'").fetchone()[0],
            "facts": self.conn.execute("SELECT COUNT(*) FROM memories WHERE layer='fact'").fetchone()[0],
            "emotions": self.conn.execute("SELECT COUNT(*) FROM emotion_log").fetchone()[0],
        }

    def list_records(self, query: str = "", layer: str = "", subject: str = "",
                     category: str = "", min_importance: int = 1, date: str = "",
                     period: str = "", limit: int = 200) -> list[dict]:
        clauses, params = ["importance>=?"], [min_importance]
        for column, value in (("layer", layer), ("subject", subject), ("category", category),
                              ("memory_date", date), ("period", period)):
            if value:
                clauses.append(f"{column}=?")
                params.append(value)
        if query:
            clauses.append("content LIKE ?")
            params.append(f"%{query}%")
        params.append(limit)
        return [dict(row) for row in self.conn.execute(
            f"SELECT * FROM memories WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?", params)]

    def update_record(self, memory_id: int, content: str, importance: int | None = None) -> bool:
        row = self.conn.execute("SELECT layer FROM memories WHERE id=?", (memory_id,)).fetchone()
        if row and row["layer"] == "summary":
            updated = self.update_summary(memory_id, content)
            if updated and importance is not None:
                with self.conn:
                    self.conn.execute("UPDATE memories SET importance=? WHERE id=?",
                                      (max(1, min(5, int(importance))), memory_id))
                self._write_summary_file(memory_id)
            return updated
        content = content.strip()
        if not content:
            return False
        values = [content, json.dumps(_embedding(content)), datetime.now().isoformat(timespec="seconds")]
        sql = "UPDATE memories SET content=?,embedding=?,content_hash=?,updated_at=?"
        values.insert(2, self._content_hash(content))
        if importance is not None:
            sql += ",importance=?"
            values.append(max(1, min(5, int(importance))))
        sql += " WHERE id=?"
        values.append(memory_id)
        with self.conn:
            cur = self.conn.execute(sql, values)
        return bool(cur.rowcount)

    def delete_record(self, memory_id: int) -> bool:
        self._delete_summary_file(memory_id)
        with self.conn:
            cur = self.conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        return bool(cur.rowcount)

    def export_json(self, path: Path) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "messages": [dict(row) for row in self.conn.execute("SELECT * FROM messages ORDER BY id")],
            "memories": [dict(row) for row in self.conn.execute("SELECT * FROM memories ORDER BY id")],
            "emotions": [dict(row) for row in self.conn.execute("SELECT * FROM emotion_log ORDER BY id")],
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_json(self, path: Path) -> dict[str, int]:
        """Merge a role backup without replacing conflicting local records."""
        report = {"messages": 0, "memories": 0, "emotions": 0, "skipped": 0, "errors": 0}
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            report["errors"] = 1
            return report
        if not isinstance(payload, dict):
            report["errors"] = 1
            return report
        message_map = {}
        with self._lock, self.conn:
            for item in payload.get("messages", []):
                if not isinstance(item, dict) or not item.get("content") or item.get("role") not in ("user", "assistant"):
                    report["errors"] += 1
                    continue
                existing = self.conn.execute(
                    "SELECT id FROM messages WHERE role=? AND content=? AND created_at=?",
                    (item["role"], item["content"], item.get("created_at", ""))).fetchone()
                if existing:
                    message_map[item.get("id")] = existing["id"]
                    report["skipped"] += 1
                    continue
                now = datetime.now()
                cur = self.conn.execute("""
                    INSERT INTO messages(role,content,mood,created_at,memory_date,period,summarized,
                        importance,subject,category,keywords,source_ids)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    item["role"], item["content"], item.get("mood", ""),
                    item.get("created_at", now.isoformat(timespec="seconds")),
                    item.get("memory_date", now.date().isoformat()), item.get("period", _period(now)),
                    int(bool(item.get("summarized", 0))), int(item.get("importance", 1)),
                    item.get("subject", item["role"]), item.get("category", "闲聊"),
                    item.get("keywords", "[]"), item.get("source_ids", "[]")))
                message_map[item.get("id")] = cur.lastrowid
                report["messages"] += 1
            for item in payload.get("memories", []):
                if not isinstance(item, dict) or not str(item.get("content", "")).strip():
                    report["errors"] += 1
                    continue
                stable_id = str(item.get("stable_id") or uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{item.get('layer')}:{item.get('range_start')}:{self._content_hash(item['content'])}"))
                if self.conn.execute("SELECT 1 FROM memories WHERE stable_id=?", (stable_id,)).fetchone():
                    report["skipped"] += 1
                    continue
                raw_sources = self._as_list(item.get("source_ids", []))
                sources = [message_map[value] for value in raw_sources if value in message_map]
                try:
                    created = datetime.fromisoformat(item.get("created_at", ""))
                except (TypeError, ValueError):
                    created = datetime.now()
                try:
                    self._insert_memory(item.get("layer", "fact"), {
                        "content": item["content"], "importance": item.get("importance", 2),
                        "subject": item.get("subject", "other"), "category": item.get("category", "事实"),
                        "keywords": self._as_list(item.get("keywords", [])), "source_ids": sources,
                        "range_start": item.get("range_start") or item.get("memory_date"),
                        "range_end": item.get("range_end") or item.get("memory_date"),
                        "stable_id": stable_id,
                        "generated_at": item.get("generated_at") or item.get("created_at"),
                        "manual_updated_at": item.get("manual_updated_at", ""),
                    }, created)
                except (TypeError, ValueError, sqlite3.Error):
                    report["errors"] += 1
                    continue
                report["memories"] += 1
            for item in payload.get("emotions", []):
                if not isinstance(item, dict) or not item.get("mood"):
                    continue
                source_id = message_map.get(item.get("source_message_id"))
                signature = (item["mood"], item.get("created_at", ""), source_id)
                if self.conn.execute(
                        "SELECT 1 FROM emotion_log WHERE mood=? AND created_at=? AND source_message_id IS ?",
                        signature).fetchone():
                    report["skipped"] += 1
                    continue
                now = datetime.now()
                self.conn.execute("""
                    INSERT INTO emotion_log(mood,intensity,note,source_message_id,created_at,memory_date,period)
                    VALUES(?,?,?,?,?,?,?)""", (
                    item["mood"], max(1, min(5, int(item.get("intensity", 2)))), item.get("note", ""),
                    source_id, item.get("created_at", now.isoformat(timespec="seconds")),
                    item.get("memory_date", now.date().isoformat()), item.get("period", _period(now))))
                report["emotions"] += 1
        self._ensure_calendar_archives()
        return report

    def add_manual_fact(self, content: str, importance: int = 3, subject: str = "user",
                        category: str = "事实") -> int:
        with self.conn:
            return self._insert_memory("fact", {
                "content": content, "importance": importance, "subject": subject,
                "category": category, "keywords": _tokens(content)[:12],
            }, datetime.now())

    def clear_all(self) -> None:
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM messages")
            self.conn.execute("DELETE FROM memories")
            self.conn.execute("DELETE FROM emotion_log")
            self.conn.execute("DELETE FROM archives")
            self.conn.execute("DELETE FROM metadata WHERE key='history_imported'")
        shutil.rmtree(self.summaries_dir, ignore_errors=True)
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.archives_dir, ignore_errors=True)
        self.archives_dir.mkdir(parents=True, exist_ok=True)

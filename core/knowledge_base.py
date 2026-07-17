"""Small dependency-free, per-character retrieval library for roleplay context."""
import json
import re
import shutil
from pathlib import Path


class KnowledgeBase:
    """Imports user-authored sources and ranks short passages for each message."""

    INDEX_NAME = "index.json"
    SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".json"}

    def __init__(self, character_dir: Path):
        self.character_dir = character_dir
        self.root = character_dir / "knowledge"
        self.sources_dir = self.root / "sources"
        self.index_path = self.root / self.INDEX_NAME

    def import_files(self, paths: list[str], source_type: str = "world") -> tuple[int, list[str]]:
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        copied, errors = 0, []
        for raw_path in paths:
            source = Path(raw_path)
            if source.suffix.lower() not in self.SUPPORTED_SUFFIXES:
                errors.append(f"不支持的文件：{source.name}")
                continue
            try:
                # Folder names make the selected type obvious and durable on disk.
                target_dir = self.sources_dir / source_type
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / source.name
                if source.resolve() != target.resolve():
                    shutil.copy2(source, target)
                copied += 1
            except OSError as exc:
                errors.append(f"{source.name}: {exc}")
        if copied:
            self.rebuild()
        return copied, errors

    def rebuild(self) -> int:
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        chunks = []
        for source in sorted(self.sources_dir.rglob("*")):
            if not source.is_file() or source.suffix.lower() not in self.SUPPORTED_SUFFIXES:
                continue
            try:
                text = self._read_source(source)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            # New imports use sources/<type>/<file>; old prefixed files still work.
            relative = source.relative_to(self.sources_dir)
            source_type = relative.parts[0] if len(relative.parts) > 1 else self._parse_source_name(source.name)[0]
            display_name = source.name if len(relative.parts) > 1 else self._parse_source_name(source.name)[1]
            for index, chunk in enumerate(self._split(text)):
                chunks.append({"source": display_name, "type": source_type,
                               "index": index, "text": chunk})
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(chunks)

    def search(self, query: str, limit: int = 4, max_chars: int = 3000) -> list[dict]:
        if not self.index_path.exists():
            self.rebuild()
        try:
            chunks = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        terms = self._tokens(query)
        if not terms:
            return []
        ranked = []
        for chunk in chunks:
            text = chunk["text"].lower()
            score = sum(text.count(term) for term in terms)
            if score:
                ranked.append((score, chunk))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]["source"], pair[1]["index"]))
        result, used = [], 0
        for _, chunk in ranked[:limit]:
            if used + len(chunk["text"]) > max_chars:
                break
            result.append(chunk)
            used += len(chunk["text"])
        return result

    def permanent_context(self, source_type: str, max_chars: int = 4000) -> str:
        """Return all small, always-on sources such as character identity."""
        if not self.index_path.exists():
            self.rebuild()
        try:
            chunks = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        selected, used = [], 0
        for item in chunks:
            if item.get("type") != source_type:
                continue
            text = item["text"]
            if used + len(text) > max_chars:
                break
            selected.append(text)
            used += len(text)
        return "\n\n".join(selected)

    def source_summary(self) -> dict[str, int]:
        if not self.index_path.exists():
            self.rebuild()
        try:
            chunks = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        summary = {}
        for item in chunks:
            kind = item.get("type", "world")
            summary[kind] = summary.get(kind, 0) + 1
        return summary

    @staticmethod
    def _parse_source_name(name: str) -> tuple[str, str]:
        source_type, sep, display_name = name.partition("__")
        return (source_type, display_name) if sep and source_type else ("world", name)

    @staticmethod
    def _read_source(source: Path) -> str:
        raw = source.read_text(encoding="utf-8-sig")
        if source.suffix.lower() != ".json":
            return raw
        value = json.loads(raw)
        return KnowledgeBase._json_to_text(value)

    @staticmethod
    def _json_to_text(value) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return "\n".join(f"{key}: {KnowledgeBase._json_to_text(item)}" for key, item in value.items())
        if isinstance(value, list):
            return "\n".join(KnowledgeBase._json_to_text(item) for item in value)
        return str(value)

    @staticmethod
    def _split(text: str, size: int = 700) -> list[str]:
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
        chunks, current = [], ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 1 > size:
                chunks.append(current)
                current = ""
            while len(paragraph) > size:
                chunks.append(paragraph[:size])
                paragraph = paragraph[size:]
            current = f"{current}\n{paragraph}".strip()
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _tokens(text: str) -> list[str]:
        words = re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
        chinese = [text[i:i + 2] for i in range(len(text) - 1) if "\u4e00" <= text[i] <= "\u9fff" and "\u4e00" <= text[i + 1] <= "\u9fff"]
        return list(dict.fromkeys(words + chinese))

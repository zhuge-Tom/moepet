"""Stable adapter for the optional Rust memory accelerator."""

from __future__ import annotations

import hashlib
import math

try:
    from moepet_memory_core import embed as _native_embed  # type: ignore
    from moepet_memory_core import hybrid_rank as _native_hybrid_rank  # type: ignore
    NATIVE_AVAILABLE = True

    def embed(text: str, tokens: list[str] | None = None) -> list[tuple[int, float]]:
        return [(int(key), float(value)) for key, value in _native_embed(text)]

    def hybrid_rank(query, documents, keyword_scores, importance):
        normalized_query = [(int(key), float(value)) for key, value in query]
        normalized_documents = [
            [(int(key), float(value)) for key, value in document]
            for document in documents]
        return _native_hybrid_rank(
            normalized_query, normalized_documents,
            [float(value) for value in keyword_scores], [int(value) for value in importance])
except ImportError:
    NATIVE_AVAILABLE = False

    def embed(text: str, tokens: list[str] | None = None) -> list[tuple[int, float]]:
        freq = {}
        for token in tokens or []:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
            index = int.from_bytes(digest, "little") % 2048
            freq[index] = freq.get(index, 0.0) + 1.0
        norm = math.sqrt(sum(value * value for value in freq.values()))
        return sorted((key, value / norm) for key, value in freq.items()) if norm else []

    def hybrid_rank(query, documents, keyword_scores, importance):
        query_map = dict(query)
        result = []
        for index, document in enumerate(documents):
            similarity = sum(value * query_map.get(int(key), 0.0) for key, value in document)
            keyword = min(1.0, keyword_scores[index] if index < len(keyword_scores) else 0.0)
            weight = (importance[index] if index < len(importance) else 1) / 50.0
            result.append((index, similarity * 0.65 + keyword * 0.25 + weight))
        return sorted(result, key=lambda item: (-item[1], item[0]))

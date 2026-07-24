from __future__ import annotations

import re
from dataclasses import dataclass

import torch


STRONG_PUNCT = set(".!?。！？")
WEAK_PUNCT = set(",;:、，；：…")

WORD_KEYWORDS = {
    "en": {
        "and",
        "but",
        "because",
        "while",
        "though",
        "although",
        "when",
        "until",
        "before",
        "after",
        "then",
        "so",
        "yet",
    },
    "zh": {"但是", "可是", "然后", "于是", "如果", "因为", "所以", "而且", "不过", "直到", "等到", "只是", "却"},
    "yue": {"但系", "不过", "然后", "于是", "如果", "因为", "所以", "直到", "等到", "只系", "却"},
    "ja": {"しかし", "けれど", "けれども", "そして", "だから", "なので", "すると", "でも", "ただ", "そのあと"},
    "ko": {"하지만", "그리고", "그런데", "그래서", "그러다가", "그러면", "다만", "아직"},
}

EN_FUNCTION_WORDS = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "as",
    "into",
    "onto",
    "be",
    "been",
    "being",
}
EN_BAD_LEFT_WORDS = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "as",
    "into",
    "onto",
}
EN_BAD_RIGHT_WORDS = {
    "a",
    "an",
    "the",
    "to",
    "be",
    "been",
    "being",
    "of",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "as",
    "into",
    "onto",
}

ZH_FUNCTION_WORDS = {
    "的",
    "地",
    "得",
    "了",
    "着",
    "过",
    "吗",
    "呢",
    "吧",
    "啊",
    "呀",
    "嘛",
    "么",
    "就",
    "也",
    "还",
    "又",
    "都",
    "才",
    "把",
    "被",
    "给",
    "在",
    "对",
    "向",
    "往",
    "从",
    "跟",
    "和",
    "与",
    "及",
    "并",
    "而",
    "或",
    "且",
}
ZH_BOUNDARY_BAD_LEFT_WORDS = {"让"}
ZH_CONTENT_POS_PREFIXES = ("n", "v", "a", "i", "l", "j", "t", "s", "f")
ZH_FUNCTION_POS_PREFIXES = ("u", "p", "c", "r", "m", "q", "d")

YUE_FUNCTION_WORDS = {
    "系",
    "喺",
    "又",
    "都",
    "就",
    "先",
    "未",
    "唔",
    "会",
    "會",
    "将",
    "將",
    "同",
    "似",
    "嘅",
    "呀",
    "啊",
    "呢",
    "啫",
    "啦",
    "喇",
    "咩",
    "嚟",
}
YUE_BOUNDARY_BAD_LEFT_WORDS = {"会", "會", "将", "將", "同", "似", "系", "喺", "唔"}

JA_FUNCTION_WORDS = {
    "の",
    "に",
    "は",
    "が",
    "を",
    "て",
    "で",
    "と",
    "も",
    "へ",
    "や",
    "か",
    "な",
    "ね",
    "よ",
    "ので",
    "から",
    "まで",
    "より",
    "だけ",
    "ほど",
}
JA_BOUNDARY_BAD_LEFT_WORDS = {"て", "で", "の", "に", "は", "が", "を", "と", "も", "ので", "から", "だけ", "まで"}
JA_CONTENT_POS = {"名詞", "動詞", "形容詞", "副詞", "連体詞"}
JA_FUNCTION_POS = {"助詞", "助動詞"}

KO_FUNCTION_WORDS = {"은", "는", "이", "가", "을", "를", "에", "에서", "와", "과", "도", "만", "로", "으로", "고", "서", "채"}
KO_BAD_LEFT_SUFFIXES = {"에서", "으로", "은", "는", "이", "가", "을", "를", "에", "와", "과", "도", "만", "로", "고", "서"}
KO_BAD_RIGHT_WORDS = {"은", "는", "이", "가", "을", "를", "에", "에서", "와", "과", "도", "만", "로", "으로", "고", "서", "채"}
KO_GOOD_LEFT_PHRASE_END_WORDS = {"채"}


@dataclass
class SplitCandidate:
    split_char_index: int
    left_phone_len: int
    right_phone_len: int
    quality_score: float
    reasons: list[str]
    naturalness_reasons: list[str]


def maybe_secondary_split_preprocess_items(
    items: list[dict],
    language: str,
    *,
    max_phone_len: int = 110,
    min_phone_len: int = 24,
    max_splits_per_item: int = 1,
    min_quality_score: float = 2.5,
) -> tuple[list[dict], dict]:
    normalized_language = _normalize_supported_language(language)
    if normalized_language is None:
        return items, {"enabled": False, "items_split": 0, "applied_splits": 0}

    output_items: list[dict] = []
    items_split = 0
    applied_splits = 0
    for item in items:
        pieces, split_count = _split_item_iteratively(
            item,
            normalized_language,
            max_phone_len=max_phone_len,
            min_phone_len=min_phone_len,
            max_splits_per_item=max_splits_per_item,
            min_quality_score=min_quality_score,
        )
        if split_count > 0:
            items_split += 1
            applied_splits += split_count
        output_items.extend(pieces)
    return output_items, {
        "enabled": True,
        "items_split": int(items_split),
        "applied_splits": int(applied_splits),
        "input_items": int(len(items)),
        "output_items": int(len(output_items)),
    }


def _split_item_iteratively(
    item: dict,
    language: str,
    *,
    max_phone_len: int,
    min_phone_len: int,
    max_splits_per_item: int,
    min_quality_score: float,
) -> tuple[list[dict], int]:
    pieces = [item]
    split_count = 0
    while split_count < max_splits_per_item:
        target_index = None
        target_candidate = None
        target_phone_len = -1
        for idx, piece in enumerate(pieces):
            phone_len = _get_phone_len(piece)
            if phone_len <= max_phone_len:
                continue
            candidate = _select_best_candidate(
                piece,
                language,
                max_phone_len=max_phone_len,
                min_phone_len=min_phone_len,
            )
            if candidate is None or candidate.quality_score < min_quality_score:
                continue
            if phone_len > target_phone_len:
                target_index = idx
                target_candidate = candidate
                target_phone_len = phone_len
        if target_index is None or target_candidate is None:
            break
        split_items = _split_preprocess_item(pieces[target_index], target_candidate.split_char_index)
        if split_items is None:
            break
        left_item, right_item = split_items
        pieces = pieces[:target_index] + [left_item, right_item] + pieces[target_index + 1 :]
        split_count += 1
    return pieces, split_count


def _select_best_candidate(
    item: dict,
    language: str,
    *,
    max_phone_len: int,
    min_phone_len: int,
) -> SplitCandidate | None:
    phone_units = item.get("phone_units")
    if not phone_units:
        return None
    total_phone_len = _get_phone_len(item)
    text = str(item.get("norm_text", "") or "")
    text_len = len(text)
    if total_phone_len <= max_phone_len or text_len <= 1:
        return None

    candidates: list[SplitCandidate] = []
    for split_char_index in _get_legal_split_boundaries(phone_units, text_len):
        left_phone_len = _get_left_phone_len(phone_units, split_char_index)
        right_phone_len = total_phone_len - left_phone_len
        if left_phone_len < min_phone_len or right_phone_len < min_phone_len:
            continue
        left_unit, right_unit = _get_boundary_units(phone_units, split_char_index)
        reason_score, reasons = _score_boundary_reasons(text, language, split_char_index, left_unit, right_unit)
        naturalness_score, naturalness_reasons = _score_boundary_naturalness(
            item,
            language,
            split_char_index,
            left_unit,
            right_unit,
        )
        quality_score = _candidate_quality_score(
            left_phone_len=left_phone_len,
            right_phone_len=right_phone_len,
            total_phone_len=total_phone_len,
            max_phone_len=max_phone_len,
            reason_score=reason_score,
            reason_count=len(reasons),
            naturalness_score=naturalness_score,
        )
        candidates.append(
            SplitCandidate(
                split_char_index=int(split_char_index),
                left_phone_len=int(left_phone_len),
                right_phone_len=int(right_phone_len),
                quality_score=float(quality_score),
                reasons=reasons,
                naturalness_reasons=naturalness_reasons,
            )
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item.quality_score, item.split_char_index))
    return candidates[0]


def _score_boundary_reasons(
    text: str,
    language: str,
    split_char_index: int,
    left_unit: dict | None,
    right_unit: dict | None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if split_char_index > 0:
        left_char = text[split_char_index - 1]
        if left_char in STRONG_PUNCT:
            score += 4.0
            reasons.append(f"strong_punct:{left_char}")
        elif left_char in WEAK_PUNCT:
            score += 3.4
            reasons.append(f"weak_punct:{left_char}")

    if (left_unit or {}).get("unit_type") == "space" or (right_unit or {}).get("unit_type") == "space":
        score += 1.2
        reasons.append("space")

    right_context = text[split_char_index:]
    if language in {"en", "ko"}:
        right_context = right_context.lstrip()
    matched_right_keyword = _match_right_prefix(right_context, 0, WORD_KEYWORDS.get(language, set()))
    if matched_right_keyword is not None:
        score += 2.7
        reasons.append(f"keyword:{matched_right_keyword}")
    return score, reasons


def _candidate_quality_score(
    *,
    left_phone_len: int,
    right_phone_len: int,
    total_phone_len: int,
    max_phone_len: int,
    reason_score: float,
    reason_count: int,
    naturalness_score: float,
) -> float:
    worst_side = max(left_phone_len, right_phone_len)
    best_side = min(left_phone_len, right_phone_len)
    balance_ratio = best_side / worst_side if worst_side else 0.0
    multi_reason_bonus = max(0, reason_count - 1) * 0.25
    within_cap_bonus = 1.0 if worst_side <= max_phone_len else max(0.0, 1.0 - (worst_side - max_phone_len) / max_phone_len)
    target_gap = abs(left_phone_len - right_phone_len) / max(total_phone_len, 1)
    return float(0.7 * reason_score + multi_reason_bonus + 2.0 * balance_ratio + 1.5 * within_cap_bonus - 0.75 * target_gap + naturalness_score)


def _score_boundary_naturalness(
    item: dict,
    language: str,
    split_char_index: int,
    left_unit: dict | None,
    right_unit: dict | None,
) -> tuple[float, list[str]]:
    if language == "en":
        return _score_en_boundary_naturalness(item, split_char_index, left_unit, right_unit)
    if language == "zh":
        return _score_zh_boundary_naturalness(left_unit, right_unit)
    if language == "yue":
        return _score_yue_boundary_naturalness(item, split_char_index, left_unit, right_unit)
    if language == "ja":
        return _score_ja_boundary_naturalness(item, split_char_index, left_unit, right_unit)
    if language == "ko":
        return _score_ko_boundary_naturalness(item, split_char_index, left_unit, right_unit)
    return 0.0, []


def _score_zh_boundary_naturalness(left_unit: dict | None, right_unit: dict | None) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    left_text = _unit_text(left_unit)
    right_text = _unit_text(right_unit)
    left_pos = _pos_prefix(left_unit)
    right_pos = _pos_prefix(right_unit)
    left_len = len(left_text)
    right_len = len(right_text)

    if right_text in WORD_KEYWORDS["zh"]:
        score += 1.35
        reasons.append(f"zh_right_opener:{right_text}")
    if left_text in ZH_BOUNDARY_BAD_LEFT_WORDS:
        score -= 1.6
        reasons.append(f"zh_bad_left_word:{left_text}")
    if left_text in ZH_FUNCTION_WORDS:
        score -= 1.1
        reasons.append(f"zh_left_function:{left_text}")
    if right_text in ZH_FUNCTION_WORDS:
        score -= 1.1
        reasons.append(f"zh_right_function:{right_text}")
    if left_len == 1 and left_pos in ZH_FUNCTION_POS_PREFIXES:
        score -= 0.9
        reasons.append(f"zh_left_light_pos:{left_pos}")
    if right_len == 1 and right_pos in ZH_FUNCTION_POS_PREFIXES:
        score -= 0.9
        reasons.append(f"zh_right_light_pos:{right_pos}")
    if left_pos == "v" and right_pos in {"n", "r"}:
        score -= 1.25
        reasons.append(f"zh_verb_object:{left_text}|{right_text}")
    if left_pos == "a" and right_pos in {"n", "r"}:
        score -= 0.8
        reasons.append(f"zh_modifier_head:{left_text}|{right_text}")
    if left_pos == "m" and right_pos == "q":
        score -= 1.0
        reasons.append(f"zh_num_classifier:{left_text}|{right_text}")
    if left_len >= 2 and right_len >= 2 and left_pos in ZH_CONTENT_POS_PREFIXES and right_pos in ZH_CONTENT_POS_PREFIXES:
        score += 0.35
        reasons.append("zh_both_content_words")
    if left_len >= 2 and right_len >= 2 and left_pos == "v" and right_pos == "v":
        score += 0.2
        reasons.append("zh_clause_like_transition")
    return score, reasons


def _score_en_boundary_naturalness(
    item: dict,
    split_char_index: int,
    left_unit: dict | None,
    right_unit: dict | None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text = str(item.get("norm_text", "") or "")
    phone_units = item.get("phone_units") or []
    left_lexical, right_lexical = _get_adjacent_lexical_units(phone_units, split_char_index)
    left_text = _unit_text(left_lexical).lower()
    right_text = _unit_text(right_lexical).lower()
    left_len = len(left_text)
    right_len = len(right_text)
    right_context = text[split_char_index:].lstrip().lower()

    matched_right_opener = _match_right_prefix(right_context, 0, WORD_KEYWORDS["en"])
    if matched_right_opener is not None:
        score += 1.35
        reasons.append(f"en_right_opener:{matched_right_opener}")
    if left_text in EN_BAD_LEFT_WORDS:
        score -= 1.1
        reasons.append(f"en_bad_left_word:{left_text}")
    if right_text in EN_BAD_RIGHT_WORDS:
        score -= 1.25
        reasons.append(f"en_bad_right_word:{right_text}")
    if left_text in EN_FUNCTION_WORDS:
        score -= 0.7
        reasons.append(f"en_left_function:{left_text}")
    if right_text in EN_FUNCTION_WORDS:
        score -= 0.7
        reasons.append(f"en_right_function:{right_text}")
    if (left_unit or {}).get("unit_type") == "space" or (right_unit or {}).get("unit_type") == "space":
        score += 0.2
        reasons.append("en_space_boundary")
    if left_len >= 3 and right_len >= 3 and left_text not in EN_FUNCTION_WORDS and right_text not in EN_FUNCTION_WORDS:
        score += 0.35
        reasons.append("en_both_content_like")
    return score, reasons


def _score_yue_boundary_naturalness(
    item: dict,
    split_char_index: int,
    left_unit: dict | None,
    right_unit: dict | None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text = str(item.get("norm_text", "") or "")
    left_text = _unit_text(left_unit)
    right_text = _unit_text(right_unit)
    left_len = len(left_text)
    right_len = len(right_text)

    matched_right_opener = _match_right_prefix(text, split_char_index, WORD_KEYWORDS["yue"])
    if matched_right_opener is not None:
        score += 1.35
        reasons.append(f"yue_right_opener:{matched_right_opener}")
    matched_left_bad = _match_left_suffix(text, split_char_index, YUE_BOUNDARY_BAD_LEFT_WORDS)
    if matched_left_bad is not None:
        score -= 1.45
        reasons.append(f"yue_bad_left_word:{matched_left_bad}")
    if left_text in YUE_FUNCTION_WORDS:
        score -= 1.0
        reasons.append(f"yue_left_function:{left_text}")
    if right_text in YUE_FUNCTION_WORDS:
        score -= 1.0
        reasons.append(f"yue_right_function:{right_text}")
    if left_len == 1 and left_text in {"会", "會", "将", "將", "同", "似", "系", "喺"}:
        score -= 0.8
        reasons.append(f"yue_left_light_word:{left_text}")
    if right_len == 1 and right_text in {"会", "會", "将", "將", "同", "似", "系", "喺"}:
        score -= 0.8
        reasons.append(f"yue_right_light_word:{right_text}")
    if left_len >= 2 and right_len >= 2 and left_text not in YUE_FUNCTION_WORDS and right_text not in YUE_FUNCTION_WORDS:
        score += 0.35
        reasons.append("yue_both_content_like")
    return score, reasons


def _score_ja_boundary_naturalness(
    item: dict,
    split_char_index: int,
    left_unit: dict | None,
    right_unit: dict | None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text = str(item.get("norm_text", "") or "")
    left_text = _unit_text(left_unit)
    right_text = _unit_text(right_unit)
    left_pos = str((left_unit or {}).get("pos", "") or "")
    right_pos = str((right_unit or {}).get("pos", "") or "")
    left_len = len(left_text)
    right_len = len(right_text)
    phone_units = item.get("phone_units") or []
    left_prosody, right_prosody = _get_adjacent_prosody_units(phone_units, split_char_index)

    matched_right_opener = _match_right_prefix(text, split_char_index, WORD_KEYWORDS["ja"])
    if matched_right_opener is not None:
        score += 1.35
        reasons.append(f"ja_right_opener:{matched_right_opener}")
    matched_left_bad = _match_left_suffix(text, split_char_index, JA_BOUNDARY_BAD_LEFT_WORDS)
    if matched_left_bad is not None:
        score -= 1.45
        reasons.append(f"ja_bad_left_word:{matched_left_bad}")
    if left_text in JA_FUNCTION_WORDS:
        score -= 1.0
        reasons.append(f"ja_left_function:{left_text}")
    if right_text in JA_FUNCTION_WORDS:
        score -= 1.0
        reasons.append(f"ja_right_function:{right_text}")
    if left_pos in JA_FUNCTION_POS:
        score -= 1.0
        reasons.append(f"ja_left_function_pos:{left_pos}")
    if right_pos in JA_FUNCTION_POS:
        score -= 1.0
        reasons.append(f"ja_right_function_pos:{right_pos}")
    if left_len == 1 and left_text in JA_FUNCTION_WORDS:
        score -= 0.7
        reasons.append(f"ja_left_short_function:{left_text}")
    if right_len == 1 and right_text in JA_FUNCTION_WORDS:
        score -= 0.7
        reasons.append(f"ja_right_short_function:{right_text}")
    if left_pos in JA_CONTENT_POS and right_pos in JA_CONTENT_POS and left_len >= 2 and right_len >= 2:
        score += 0.4
        reasons.append("ja_both_content_words")
    if left_pos == "動詞" and right_pos in {"名詞", "副詞"}:
        score += 0.35
        reasons.append("ja_clause_like_transition")
    if left_prosody is not None and _unit_text(left_prosody) == "]":
        score += 0.4
        reasons.append("ja_pitch_fall_boundary")
    if left_prosody is not None and _unit_text(left_prosody) == "#":
        score += 0.55
        reasons.append("ja_accent_phrase_boundary")
    if right_prosody is not None and _unit_text(right_prosody) == "#":
        score += 0.35
        reasons.append("ja_right_phrase_marker")
    return score, reasons


def _score_ko_boundary_naturalness(
    item: dict,
    split_char_index: int,
    left_unit: dict | None,
    right_unit: dict | None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    text = str(item.get("norm_text", "") or "")
    phone_units = item.get("phone_units") or []
    left_lexical, right_lexical = _get_adjacent_lexical_units(phone_units, split_char_index)
    left_text = _unit_text(left_lexical)
    right_text = _unit_text(right_lexical)
    left_len = len(left_text)
    right_len = len(right_text)
    left_context = text[:split_char_index].rstrip()
    right_context = text[split_char_index:].lstrip()

    matched_right_opener = _match_right_prefix(right_context, 0, WORD_KEYWORDS["ko"])
    if matched_right_opener is not None:
        score += 1.35
        reasons.append(f"ko_right_opener:{matched_right_opener}")
    matched_left_bad = _match_left_suffix(left_context, len(left_context), KO_BAD_LEFT_SUFFIXES)
    if matched_left_bad is not None:
        score -= 1.35 if matched_left_bad in {"을", "를"} else 1.1
        reasons.append(f"ko_bad_left_suffix:{matched_left_bad}")
    if right_text in KO_BAD_RIGHT_WORDS:
        score -= 1.45 if right_text == "채" else 1.05
        reasons.append(f"ko_bad_right_word:{right_text}")
    if left_text in KO_GOOD_LEFT_PHRASE_END_WORDS and right_len >= 3:
        score += 0.95
        reasons.append(f"ko_good_left_phrase_end:{left_text}")
    if left_text in KO_FUNCTION_WORDS and left_text not in KO_GOOD_LEFT_PHRASE_END_WORDS:
        score -= 0.75
        reasons.append(f"ko_left_function:{left_text}")
    if right_text in KO_FUNCTION_WORDS:
        score -= 0.75
        reasons.append(f"ko_right_function:{right_text}")
    if (left_unit or {}).get("unit_type") == "space" or (right_unit or {}).get("unit_type") == "space":
        score += 0.2
        reasons.append("ko_space_boundary")
    if left_len >= 2 and right_len >= 2 and left_text not in KO_FUNCTION_WORDS and right_text not in KO_FUNCTION_WORDS:
        score += 0.35
        reasons.append("ko_both_content_like")
    return score, reasons


def _split_preprocess_item(item: dict, split_char_index: int) -> tuple[dict, dict] | None:
    phone_units = item.get("phone_units")
    if not phone_units:
        return None
    left_units = [unit for unit in phone_units if int(unit.get("char_end", -1)) <= split_char_index]
    right_units = [unit for unit in phone_units if int(unit.get("char_start", -1)) >= split_char_index]
    while right_units and right_units[0].get("unit_type") == "space":
        left_units.append(right_units.pop(0))
    left_units = _trim_zero_phone_space_edges(left_units)
    right_units = _trim_zero_phone_space_edges(right_units)
    if not left_units or not right_units:
        return None
    left_item = _build_split_item(item, left_units)
    right_item = _build_split_item(item, right_units)
    if left_item is None or right_item is None:
        return None
    return left_item, right_item


def _build_split_item(item: dict, units: list[dict]) -> dict | None:
    if not units:
        return None
    char_start = int(units[0].get("char_start", 0))
    char_end = int(units[-1].get("char_end", 0))
    phone_start = int(min(int(unit.get("phone_start", 0)) for unit in units))
    phone_end = int(max(int(unit.get("phone_end", 0)) for unit in units))
    if char_end <= char_start or phone_end <= phone_start:
        return None

    split_units = []
    for raw_unit in units:
        unit = dict(raw_unit)
        unit["char_start"] = int(unit.get("char_start", 0)) - char_start
        unit["char_end"] = int(unit.get("char_end", 0)) - char_start
        unit["phone_start"] = int(unit.get("phone_start", 0)) - phone_start
        unit["phone_end"] = int(unit.get("phone_end", 0)) - phone_start
        split_units.append(unit)

    bert_features = item["bert_features"][:, phone_start:phone_end].contiguous()
    phones = _slice_sequence(item["phones"], phone_start, phone_end)
    return {
        "phones": phones,
        "bert_features": bert_features,
        "norm_text": str(item.get("norm_text", "") or "")[char_start:char_end],
        "phone_units": split_units,
    }


def _slice_sequence(seq, start: int, end: int):
    if isinstance(seq, torch.Tensor):
        return seq[start:end].contiguous()
    return seq[start:end]


def _trim_zero_phone_space_edges(units: list[dict]) -> list[dict]:
    start = 0
    end = len(units)
    while start < end and int(units[start].get("phone_count", 0)) == 0 and units[start].get("unit_type") == "space":
        start += 1
    while end > start and int(units[end - 1].get("phone_count", 0)) == 0 and units[end - 1].get("unit_type") == "space":
        end -= 1
    return units[start:end]


def _get_phone_len(item: dict) -> int:
    return int(len(item["phones"]))


def _get_legal_split_boundaries(phone_units: list[dict], text_len: int) -> list[int]:
    return sorted(
        {
            int(unit["char_end"])
            for unit in phone_units
            if 0 < int(unit.get("char_end", 0)) < text_len
        }
    )


def _get_left_phone_len(phone_units: list[dict], split_char_index: int) -> int:
    left_phone_len = 0
    for unit in phone_units:
        if int(unit.get("char_end", -1)) <= split_char_index:
            left_phone_len = int(unit.get("phone_end", left_phone_len))
        else:
            break
    return left_phone_len


def _get_boundary_units(phone_units: list[dict], split_char_index: int) -> tuple[dict | None, dict | None]:
    left_unit = None
    right_unit = None
    for unit in phone_units:
        if int(unit.get("char_end", -1)) == split_char_index:
            left_unit = unit
        if int(unit.get("char_start", -1)) == split_char_index:
            right_unit = unit
            break
    return left_unit, right_unit


def _get_adjacent_lexical_units(
    phone_units: list[dict],
    split_char_index: int,
    skip_types: set[str] | None = None,
) -> tuple[dict | None, dict | None]:
    if skip_types is None:
        skip_types = {"space", "punct", "prosody"}
    left_unit = None
    for unit in reversed(phone_units):
        if unit.get("unit_type") in skip_types:
            continue
        if int(unit.get("char_end", -1)) <= split_char_index:
            left_unit = unit
            break
    right_unit = None
    for unit in phone_units:
        if unit.get("unit_type") in skip_types:
            continue
        if int(unit.get("char_start", -1)) >= split_char_index:
            right_unit = unit
            break
    return left_unit, right_unit


def _get_adjacent_prosody_units(phone_units: list[dict], split_char_index: int) -> tuple[dict | None, dict | None]:
    left_prosody = None
    right_prosody = None
    for unit in phone_units:
        if unit.get("unit_type") != "prosody":
            continue
        if int(unit.get("char_end", -1)) == split_char_index:
            left_prosody = unit
        if int(unit.get("char_start", -1)) == split_char_index:
            right_prosody = unit
            break
    return left_prosody, right_prosody


def _match_right_prefix(text: str, split_index: int, keywords: set[str]) -> str | None:
    if not keywords:
        return None
    right_text = text[split_index:]
    for keyword in sorted(keywords, key=len, reverse=True):
        if right_text.startswith(keyword):
            return keyword
    return None


def _match_left_suffix(text: str, split_index: int, keywords: set[str]) -> str | None:
    if not keywords:
        return None
    left_text = text[:split_index]
    for keyword in sorted(keywords, key=len, reverse=True):
        if left_text.endswith(keyword):
            return keyword
    return None


def _pos_prefix(unit: dict | None) -> str:
    if not unit:
        return ""
    return str(unit.get("pos", "") or "")[:1]


def _unit_text(unit: dict | None) -> str:
    if not unit:
        return ""
    return str(unit.get("text", "") or "")


def _normalize_supported_language(language: str) -> str | None:
    normalized = language.replace("all_", "")
    if normalized in {"zh", "yue", "ja", "ko", "en"}:
        return normalized
    return None

"""Convert a quoted Chinese script into a safe, directly importable dialogue JSON."""
import json
import re
from pathlib import Path


SOURCE = Path("C:/Users/30425_u2q1nih/Desktop/" + "\u661f\u7a7a\u5217\u8f66.txt")
OUTPUT = Path("datasets/xingkong_train_dialogue_examples.json")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main():
    source_text = SOURCE.read_text(encoding="utf-8-sig")
    turns = [(match.start(), clean(match.group(1)))
             for match in re.finditer(r"“([^”]{1,180})”", source_text)]
    turns = [(position, text) for position, text in turns if len(text) >= 2]
    examples = []
    seen = set()
    for (first_pos, user), (second_pos, assistant) in zip(turns, turns[1:]):
        # Nearby quotes are the most likely conversational turn pairs.  Original
        # speaker names are absent, so labels remain intentionally neutral.
        if second_pos - first_pos > 900 or (user, assistant) in seen:
            continue
        seen.add((user, assistant))
        examples.append({
            "user": user,
            "assistant": assistant,
            "speaker_inference": False,
        })
    dataset = {
        "type": "dialogue_examples",
        "title": "星空列车原文对白实例（未标注说话人）",
        "source_file": SOURCE.name,
        "speaker_inference": False,
        "usage": "导入 Moepet 时选择“对话示例”。仅用于语气和对话节奏参考。",
        "examples": examples,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(examples)} examples to {OUTPUT}")


if __name__ == "__main__":
    main()

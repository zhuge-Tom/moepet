"""Build direct-import dialogue examples for Nuo Wa from a tagged VN script."""
import json
import re
from collections import Counter
from pathlib import Path


SOURCE = Path(r"D:/download/talk(1).txt")
OUTPUT = Path("datasets/noir_dialogue_examples.json")
NOIR_NAMES = {"诺瓦", "黑猫"}
USER_NAME = "晓"
SKIP_NAMES = {"——", "背景切换", "播放视频", "播放音乐", "音效"}
NON_DIALOGUE_SPEAKERS = {"说明", "表情", "背景", "系统"}


def parse_lines(text: str):
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # The script aligns name and dialogue with ideographic spaces instead
        # of a colon.  Some comments still use a colon, so accept both forms.
        match = re.match(r"^([^：\s　]+)(?:：|[\s　]{2,})(.+)$", line)
        if not match:
            continue
        speaker, content = match.groups()
        speaker, content = speaker.strip(), content.strip()
        if not speaker or not content or speaker in SKIP_NAMES:
            continue
        # Visual commands sometimes include a colon but are never dialogue.
        if speaker.startswith(("背景", "表情", "立绘", "播放")):
            continue
        rows.append((speaker, content))
    return rows


def is_spoken_line(text: str) -> bool:
    """Exclude visual-expression asset names while keeping short natural replies."""
    if re.search(r"[\u3040-\u30ff]", text):
        return False
    if re.fullmatch(r"[通常微笑真剣困り目逸らし口明け閉じ目悲しみ怒り驚き様子を窺う_+\-＞＜]+", text):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text)) and len(text) <= 180


def useful_prompt(text: str) -> bool:
    return is_spoken_line(text) and len(re.sub(r"[……。！？、，\s]", "", text)) >= 2


def main():
    rows = parse_lines(SOURCE.read_text(encoding="utf-8-sig"))
    examples, seen = [], set()
    pending_prompt = []
    pending_response = []

    def flush():
        nonlocal pending_prompt, pending_response
        if not pending_prompt or not pending_response:
            pending_prompt, pending_response = [], []
            return
        user = "\n".join(pending_prompt)
        assistant = "\n".join(pending_response)
        key = (user, assistant)
        if key not in seen:
            seen.add(key)
            examples.append({
                "user": user, "assistant": assistant,
                "user_speaker": "晓", "assistant_speaker": "诺瓦",
            })
        pending_prompt, pending_response = [], []

    for speaker, content in rows:
        if not is_spoken_line(content):
            continue
        if speaker == USER_NAME:
            flush()
            if useful_prompt(content):
                pending_prompt = [content]
        elif speaker in NOIR_NAMES:
            if pending_prompt:
                pending_response.append(content)
        elif speaker not in NON_DIALOGUE_SPEAKERS:
            # Another speaking character makes the pending exchange ambiguous.
            flush()
    flush()
    dataset = {
        "type": "dialogue_examples",
        "character": "诺瓦",
        "source_file": SOURCE.name,
        "description": "从标注剧本提取。黑猫与诺瓦标签均归为诺瓦；只保留晓发言后、无第三方插话的诺瓦回答。已过滤表情资源名。",
        "examples": examples,
        "statistics": {"examples": len(examples), "source_speakers": dict(Counter(name for name, _ in rows))},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(examples)} examples to {OUTPUT}")


if __name__ == "__main__":
    main()

import re

import yaml

from app.settings import CONFIG_DIR

LEVELS = {"calm": 0, "dissatisfied": 1, "angry": 2, "complaint_risk": 3}


def load_policy():
    return yaml.safe_load((CONFIG_DIR / "emotion_policy.yaml").read_text())


def load_terms() -> dict[str, list[str]]:
    return yaml.safe_load((CONFIG_DIR / "rules/complaint_terms.yaml").read_text())


def emotion_terms() -> list[str]:
    """全部情绪词（不分级）：判断一句话是否只是在表达情绪。"""
    return [word for level in LEVELS if level != "calm" for word in load_terms().get(level, [])]


def complaint_flagged(state) -> bool:
    """Case priority follows the strategy's action, so an angry-and-rising customer is flagged too."""
    return (state.get("emotion") or {}).get("level") == "complaint_risk" or "flag_complaint_risk" in (
        state.get("emotion_actions") or []
    )


ZH_NEGATIONS = ("不", "不会", "没有", "不用", "不想", "无需", "别")
LATIN_NEGATION = re.compile(r"\b(not|never|no|don'?t|doesn'?t|isn'?t|wasn'?t|niet|nicht|pas|no es)\s+(\w+\s+)?$", re.IGNORECASE)


def term_hit(word: str, text: str) -> bool:
    """情绪词命中：中文按子串、前面紧跟否定词不算；拉丁字母词忽略大小写、按整词匹配，前一两个词是否定词不算
    （「not disappointed」不是失望，「scam」不能命中「scampi」）。"""
    if not word.isascii() or not any(ch.isalpha() for ch in word):
        start = text.find(word)
        return start >= 0 and not any(text[max(0, start - 3) : start].endswith(n) for n in ZH_NEGATIONS)
    for match in re.finditer(rf"(?<![\w]){re.escape(word)}(?![\w])", text, re.IGNORECASE):
        if not LATIN_NEGATION.search(text[max(0, match.start() - 24) : match.start()]):
            return True
    return False


def evaluate_emotion(level, text, track, input_id, *, unresolved_turns=0, risk=False, prior_emotion=None, cues=None):
    level = "dissatisfied" if level == "anxious" else level
    grounded = cues is None or any(cue.strip() and cue in text for cue in cues)
    if level not in LEVELS:
        level, source = None, "no_signal"
    elif grounded:
        source = "model"
    elif level == "calm":
        # "Calm" without a quote is the schema default, not an observation.
        level, source = None, "no_signal"
    else:
        # The model saw something it could not quote. Dropping it loses the signal
        # entirely; cap it at the lowest non-calm level instead.
        level, source = "dissatisfied", "cues_missing"
    terms = load_terms()
    for candidate in ("complaint_risk", "angry", "dissatisfied"):
        hits = [word for word in terms[candidate] if term_hit(word, text)]
        if hits and LEVELS[candidate] > LEVELS.get(level, -1):
            level = candidate
            source = "rules"
    prior = [t for t in track if t["input_id"] != input_id]
    previous = prior[-1]["level"] if prior else (prior_emotion or {}).get("level")
    previous = "dissatisfied" if previous == "anxious" else previous
    observed = level is not None
    if not observed:
        level = previous
    trend = (
        "rising"
        if observed and LEVELS.get(level, 0) > LEVELS.get(previous, LEVELS.get(level, 0))
        else "falling"
        if observed and LEVELS.get(level, 0) < LEVELS.get(previous, LEVELS.get(level, 0))
        else "stable"
    )
    context = {"level": level, "trend": trend, "unresolved_turns": unresolved_turns, "risk": risk}
    policy = load_policy()
    strategy = "normal"
    for rule in policy["rules"]:
        if all(
            context["unresolved_turns"] >= value
            if name == "unresolved_turns_gte"
            else context.get(name) == value
            for name, value in rule["when"].items()
        ):
            strategy = rule["strategy"]
            break
    return {
        "emotion": {"level": level, "strategy": strategy},
        "emotion_track": ([*prior, {"input_id": input_id, "level": level, "source": source}] if observed else prior)[-6:],
        "emotion_trend": trend,
        "emotion_actions": policy["strategies"][strategy]["actions"],
        "unresolved_turns": unresolved_turns,
    }

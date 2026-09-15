import yaml

from app.settings import CONFIG_DIR

LEVELS = {"calm": 0, "dissatisfied": 1, "angry": 2, "complaint_risk": 3}


def load_policy():
    return yaml.safe_load((CONFIG_DIR / "emotion_policy.yaml").read_text())


def evaluate_emotion(level, text, track, input_id, *, unresolved_turns=0, risk=False):
    level = "dissatisfied" if level == "anxious" else level
    if level not in LEVELS:
        level = "calm"
    terms = yaml.safe_load((CONFIG_DIR / "rules/complaint_terms.yaml").read_text())
    for candidate in ("complaint_risk", "angry", "dissatisfied"):
        hits = []
        for word in terms[candidate]:
            start = text.find(word)
            if start >= 0 and not any(
                text[max(0, start - 3) : start].endswith(n)
                for n in ("不", "不会", "没有", "不用", "不想", "无需", "别")
            ):
                hits.append(word)
        if hits and LEVELS[candidate] > LEVELS[level]:
            level = candidate
    prior = [t for t in track if t["input_id"] != input_id]
    previous = prior[-1]["level"] if prior else level
    previous = "dissatisfied" if previous == "anxious" else previous
    trend = (
        "rising"
        if LEVELS[level] > LEVELS.get(previous, 0)
        else "falling"
        if LEVELS[level] < LEVELS.get(previous, 0)
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
        "emotion_track": [*prior, {"input_id": input_id, "level": level}][-6:],
        "emotion_trend": trend,
        "emotion_actions": policy["strategies"][strategy]["actions"],
        "unresolved_turns": unresolved_turns,
    }

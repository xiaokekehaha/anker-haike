import yaml

from app.settings import CONFIG_DIR

LEVELS = {"calm": 0, "dissatisfied": 1, "angry": 2, "complaint_risk": 3}


def load_policy():
    return yaml.safe_load((CONFIG_DIR / "emotion_policy.yaml").read_text())


def complaint_flagged(state) -> bool:
    """Case priority follows the strategy's action, so an angry-and-rising customer is flagged too."""
    return (state.get("emotion") or {}).get("level") == "complaint_risk" or "flag_complaint_risk" in (
        state.get("emotion_actions") or []
    )


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

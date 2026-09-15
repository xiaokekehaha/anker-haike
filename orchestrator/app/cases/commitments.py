"""Record sourced terms, estimates and explicit human decisions."""


def valid_commitment(value):
    source = value.get("source")
    return bool((value.get("text") or "").strip()) and (
        source in {"clause", "receipt"}
        or (source in {"action_config", "human_decision"} and bool((value.get("source_ref") or "").strip()))
    )

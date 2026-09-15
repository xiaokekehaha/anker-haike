import yaml

from app.settings import CONFIG_DIR


def vocabulary():
    return yaml.safe_load((CONFIG_DIR / "vision_vocab.yaml").read_text())


def normalize(localization):
    config = vocabulary()
    result = localization.model_dump(mode="json", exclude={"observations", "visible_parts"})
    for finding in result["findings"]:
        for key, vocab in [("part", "parts"), ("phenomenon", "phenomena")]:
            if finding[key] not in config[vocab]:
                finding.setdefault("raw", {})[key] = finding[key]
                finding[key] = "其他"
    quality = result["image_quality"]
    quality["guidance"] = [config["retake_guidance"][r] for r in quality["reasons"]]
    return result


def signature_plans(localization, faults=None):
    if not localization or not localization["image_quality"]["usable"]:
        return []
    signatures = (
        [
            {"part": s.part, "phenomenon": s.phenomenon, "plan_id": f.plan_id}
            for f in faults
            for s in f.signatures
        ]
        if faults is not None
        else vocabulary()["signatures"]
    )
    return list(
        dict.fromkeys(
            s["plan_id"]
            for f in localization["findings"]
            if f["confidence"] >= 0.7
            for s in signatures
            if (f["part"], f["phenomenon"]) == (s["part"], s["phenomenon"])
        )
    )

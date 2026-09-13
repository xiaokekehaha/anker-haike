import json

from haike_contracts.export import SCHEMA_DIR, build_schemas, render


def test_three_schemas_with_titles():
    s = build_schemas()
    assert set(s) == {"events.schema.json", "actions.schema.json", "snapshot.schema.json"}
    assert [v["title"] for v in s.values()] == ["ServerEvent", "ActionRequest", "SessionSnapshot"]
    for v in s.values():
        assert v["$schema"].endswith("2020-12/schema")


def test_render_is_deterministic():
    a = {k: render(v) for k, v in build_schemas().items()}
    b = {k: render(v) for k, v in build_schemas().items()}
    assert a == b


def test_event_schema_discriminates_15_types():
    ev = build_schemas()["events.schema.json"]
    assert len(ev["discriminator"]["mapping"]) == 19
    ac = build_schemas()["actions.schema.json"]
    assert len(ac["discriminator"]["mapping"]) == 7
    assert {"ActionResult", "ActionConflict"} <= set(ac["$defs"])


def test_committed_schema_files_match_models():
    """schema/ 下文件须与模型一致（CI 用 --check 做同样比对）。"""
    for name, schema in build_schemas().items():
        path = SCHEMA_DIR / name
        assert path.exists(), f"missing {path}; run `make contracts`"
        assert json.loads(path.read_text(encoding="utf-8")) == json.loads(render(schema))

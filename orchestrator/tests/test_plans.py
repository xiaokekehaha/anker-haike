"""票 31：计划加载校验、next_on 规则推进、L4 重载、JSON Schema、plans 表 seed。"""

from __future__ import annotations

import copy

import pytest
import yaml

from app.plans import PlanLibrary, PlansError, load_plans_config, plan_json_schema
from app.settings import REPO_ROOT

REAL = REPO_ROOT / "config" / "plans.yaml"
EXPECTED_IDS = [
    "rv_power_supply",
    "rv_suction_dustbin_full",
    "rv_suction_filter_clog",
    "rv_suction_hair_wrap",
    "rv_suction_motor_fault",
    "rv_suction_side_brush",
]


@pytest.fixture(scope="module")
def library() -> PlanLibrary:
    return PlanLibrary.from_yaml(REAL)


def _write(tmp_path, data):
    p = tmp_path / "plans.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


@pytest.fixture
def data():
    return yaml.safe_load(REAL.read_text(encoding="utf-8"))


def test_plans_load(library):
    assert library.plan_ids == EXPECTED_IDS
    motor = library.get("rv_suction_motor_fault")
    assert len(motor.steps) == 1
    assert motor.steps[0].next_on.model_dump() == {
        "solved": "EXHAUSTED",
        "not_solved": "EXHAUSTED",
        "cannot_do": "EXHAUSTED",
    }
    for p in library.plans:
        for s in p.steps:
            assert library.evidence_snippet(s.instruction_src)


def test_next_on_rule_advance(library):
    p = library.get("rv_suction_hair_wrap")
    assert p.first_step().step_id == "s1"
    assert p.next_step_id("s1", "not_solved") == "s2"
    assert p.next_step_id("s1", "solved") == "DONE"
    assert p.next_step_id("s2", "cannot_do") == "EXHAUSTED"
    assert p.next_step_id("s3", "not_solved") == "EXHAUSTED"


def test_allowed_for_product_state(library):
    assert len(library.allowed_for(category="robot_vacuum")) == 6  # category_only
    assert len(library.allowed_for(category="robot_vacuum", sku="EUFY-X9-PRO")) == 6
    assert library.allowed_for(category="breast_pump") == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda d: d["plans"][0]["steps"][0]["next_on"].__setitem__("not_solved", "s9"),
            "next_on.not_solved -> 's9'",
        ),
        (
            lambda d: d["plans"][0]["steps"][0]["next_on"].__setitem__("cannot_do", "s1"),
            "points to itself",
        ),
        (
            lambda d: d["plans"][0]["steps"][1].__setitem__(
                "instruction_src", "evidence:manual_rv_v1#c99"
            ),
            "not in evidence index",
        ),
        (
            lambda d: d["plans"][0]["steps"][1].__setitem__("instruction_src", "manual_rv_v1#c15"),
            "instruction_src must look like",
        ),
        (lambda d: d["plans"][0]["steps"][1].__setitem__("step_id", "s1"), "duplicate step_id"),
        (lambda d: d["plans"].append(copy.deepcopy(d["plans"][0])), "duplicate plan"),
        (
            lambda d: d["plans"][0].__setitem__(
                "applies_to", {"scope": "sku", "category": "robot_vacuum"}
            ),
            "requires sku_list",
        ),
        (lambda d: d["plans"][0].__setitem__("steps", []), "plans.0.steps"),
        (
            lambda d: d["plans"][0]["steps"][0].__setitem__("bogus", 1),
            "Extra inputs are not permitted",
        ),
    ],
)
def test_invalid_plan_fails_with_reason(tmp_path, data, mutate, expected):
    mutate(data)
    with pytest.raises(PlansError) as ei:
        load_plans_config(_write(tmp_path, data))
    assert expected in str(ei.value)


def test_startup_uses_library_and_fails_on_bad_config(tmp_path, data, monkeypatch):
    """main.py lifespan 通过 PlanLibrary.from_yaml 加载；坏配置抛 PlansError 即启动失败。"""
    from app import main as main_mod
    from app.settings import settings

    data["plans"][0]["steps"][0]["next_on"]["solved"] = "nowhere"
    bad = _write(tmp_path, data)
    monkeypatch.setattr(settings, "plans_config_path", str(bad))
    with pytest.raises(PlansError):
        main_mod.PlanLibrary.from_yaml(settings.plans_config_path)


def test_reload_if_changed(tmp_path, data):
    p = _write(tmp_path, data)
    lib = PlanLibrary.from_yaml(p)
    data["plans"][0]["fault"] = "改了"
    _write(tmp_path, data)
    assert lib.reload_if_changed() is False
    data["version"] = "2099.1"
    _write(tmp_path, data)
    assert lib.reload_if_changed() is True and lib.get("rv_suction_hair_wrap").fault == "改了"


def test_latest_version_wins(tmp_path, data):
    v2 = copy.deepcopy(data["plans"][0])
    v2["version"] = 2
    v2["fault"] = "v2"
    data["plans"].append(v2)
    lib = PlanLibrary.from_yaml(_write(tmp_path, data))
    assert lib.get("rv_suction_hair_wrap").version == 2 and len(lib.plan_ids) == 6


def test_plan_json_schema(library):
    schema = plan_json_schema()
    assert schema["title"] == "TroubleshootPlan" and "steps" in schema["properties"]
    assert set(schema["required"]) >= {"plan_id", "version", "fault", "applies_to", "steps"}
    narrowed = library.schema_for(category="robot_vacuum")
    assert narrowed["properties"]["plan_id"] == {"type": "string", "enum": EXPECTED_IDS}
    assert library.schema_for(category="breast_pump")["properties"]["plan_id"]["enum"] == []
    import jsonschema

    jsonschema.Draft202012Validator(narrowed).validate(
        library.get("rv_suction_hair_wrap").model_dump()
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(narrowed).validate(
            {**library.get("rv_suction_hair_wrap").model_dump(), "plan_id": "made_up"}
        )


async def test_seed_plans_is_idempotent(library):
    from app.plans import store
    from tests.test_catalog import _pool

    pool = await _pool()
    try:
        a = await store.seed_plans(pool, library)
        b = await store.seed_plans(pool, library)
        assert a["upserted"] == b["upserted"] == 6 and b["total"] >= 6
        async with pool.connection() as conn:
            cur = await conn.execute(
                "select plan_id, steps from plans where plan_id = 'rv_suction_motor_fault'"
            )
            row = await cur.fetchone()
        assert len(row["steps"]) == 1 and row["steps"][0]["next_on"]["solved"] == "EXHAUSTED"
    finally:
        await pool.close()

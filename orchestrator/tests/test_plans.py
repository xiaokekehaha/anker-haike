"""票 31：计划加载校验、next_on 规则推进、L4 重载、JSON Schema、plans 表 seed。"""

from __future__ import annotations

import copy

import pytest
import yaml

from app.plans import PlanLibrary, PlansError, load_plans_config, plan_json_schema
from app.settings import REPO_ROOT

REAL = REPO_ROOT / "config" / "plans.yaml"
# 品类通用（category_only 也能用）的扫地机计划
RV_CATEGORY_IDS = [
    "rv_noise_obstruction",
    "rv_power_supply",
    "rv_suction_dustbin_full",
    "rv_suction_filter_clog",
    "rv_suction_hair_wrap",
    "rv_suction_motor_fault",
    "rv_suction_side_brush",
]
# 引用官方资料、只对清单内型号开放的扫地机计划
RV_SKU_IDS = [
    "rv_map_lost",
    "rv_x10_dock_return",
    "rv_x10_loud_noise",
    "rv_x10_mop_no_water",
    "rv_x10_station_leak",
    "rv_x10_wifi_connect",
]
EXPECTED_IDS = sorted(RV_CATEGORY_IDS + RV_SKU_IDS)


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
    assert [p for p in library.plan_ids if p.startswith("rv_")] == EXPECTED_IDS  # 多品类后库里还有其他前缀
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
    # 做不到清洁滤网不代表做不到检查吸口：cannot_do 只在后续步骤依赖同一前提时才直达 EXHAUSTED
    assert p.next_step_id("s2", "cannot_do") == "s3"
    assert p.next_step_id("s3", "cannot_do") == "EXHAUSTED"
    assert p.next_step_id("s3", "not_solved") == "EXHAUSTED"


def test_allowed_for_product_state(library):
    assert sorted(p.plan_id for p in library.allowed_for(category="robot_vacuum")) == RV_CATEGORY_IDS
    # X9 只额外拿到型号清单里包含它的那条官方计划，X10 拿到全部型号计划
    assert sorted(p.plan_id for p in library.allowed_for(category="robot_vacuum", sku="EUFY-X9-PRO")) == sorted(
        [*RV_CATEGORY_IDS, "rv_map_lost"]
    )
    assert sorted(p.plan_id for p in library.allowed_for(category="robot_vacuum", sku="EUFY-X10-PRO-OMNI")) == EXPECTED_IDS
    # 头戴耳机只有型号级计划：未确认型号时没有可用计划，调用方据此走 R5
    assert library.allowed_for(category="headphones") == []
    assert {p.plan_id for p in library.allowed_for(category="headphones", sku="SOUNDCORE-A3035")} == {
        "hd_so_power_failure", "hd_so_battery_drain", "hd_so_connect_drop",
        "hd_so_one_side", "hd_so_noise", "hd_so_mic",
    }
    assert {p.plan_id for p in library.allowed_for(category="breast_pump")} == {"bp_valve_membrane", "bp_power_check", "bp_noise_check", "bp_app_pair"}; assert library.allowed_for(category="hub") == []  # 目录级品类没有计划


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
    assert lib.get("rv_suction_hair_wrap").version == 2
    assert len(lib.plan_ids) == len({p["plan_id"] for p in data["plans"]})


def test_plan_json_schema(library):
    schema = plan_json_schema()
    assert schema["title"] == "TroubleshootPlan" and "steps" in schema["properties"]
    assert set(schema["required"]) >= {"plan_id", "version", "fault", "applies_to", "steps"}
    narrowed = library.schema_for(category="robot_vacuum")
    assert narrowed["properties"]["plan_id"] == {"type": "string", "enum": RV_CATEGORY_IDS}
    assert library.schema_for(category="hub")["properties"]["plan_id"]["enum"] == []
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
        total = len(library.plan_ids)
        assert a["upserted"] == b["upserted"] == total and b["total"] >= total
        async with pool.connection() as conn:
            cur = await conn.execute(
                "select plan_id, steps from plans where plan_id = 'rv_suction_motor_fault'"
            )
            row = await cur.fetchone()
        assert len(row["steps"]) == 1 and row["steps"][0]["next_on"]["solved"] == "EXHAUSTED"
    finally:
        await pool.close()


def test_every_registered_symptom_code_has_a_plan(library):
    """词表登记了症状码却没有任何计划，用户答完问诊仍然只能 R5。品类级缺口必须为零。"""
    from app.conversation.taxonomy import taxonomy

    missing = {}
    for category, spec in (taxonomy()["categories"] or {}).items():
        codes = {f["symptom_code"] for f in spec["families"]}
        covered = {
            code
            for p in library.plans
            if p.applies_to.category == category
            for code in p.symptom_codes
        }
        if codes - covered:
            missing[category] = sorted(codes - covered)
    assert missing == {}


def test_official_evidence_plans_stay_within_the_source_sku_list(library):
    """官方资料按型号发布：引用它的计划必须是型号级，且型号不能超出该资料的适用清单。"""
    import yaml as _yaml

    from app.settings import REPO_ROOT

    kb = REPO_ROOT / "data/knowledge/kb_manual"
    for plan in library.plans:
        docs = {
            s.evidence_key.split("#", 1)[0]
            for s in plan.steps
            if s.evidence_key.startswith("official_")
        }
        if not docs:
            continue
        assert plan.applies_to.scope == "sku", plan.plan_id
        for doc_id in docs:
            front = (kb / f"{doc_id}.md").read_text(encoding="utf-8").split("---\n")[1]
            allowed = set(_yaml.safe_load(front)["sku_list"])
            assert set(plan.applies_to.sku_list) <= allowed, (plan.plan_id, doc_id)


def test_differentiated_skus_follow_sku_scoped_knowledge(library):
    """spec 2026-09-19-0810 A：只有型号专属计划或被排除的型号算分化；症状码收窄；纯通用品类为空。"""
    assert library.differentiated_skus(category="robot_vacuum") == {"EUFY-X10-PRO-OMNI", "EUFY-X9-PRO"}
    assert library.differentiated_skus(category="robot_vacuum", symptom_codes=["map_lost"]) == {
        "EUFY-X10-PRO-OMNI", "EUFY-X9-PRO",
    }
    assert library.differentiated_skus(category="robot_vacuum", symptom_codes=["abnormal_noise"]) == {"EUFY-X10-PRO-OMNI"}
    # 吸力下降只有品类通用计划：知道型号不改变下一步
    assert library.differentiated_skus(category="robot_vacuum", symptom_codes=["suction_low"]) == set()
    # A1289 既有专属计划，也被通用计划 excluded_skus 排除
    assert library.differentiated_skus(category="power_bank") == {"ANKER-A1289"}
    assert library.differentiated_skus(category="headphones", symptom_codes=["hd_one_side_silent"]) == {
        "SOUNDCORE-A3035", "SOUNDCORE-A3040",
    }
    assert library.differentiated_skus(category="breast_pump") == set()

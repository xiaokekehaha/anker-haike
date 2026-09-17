"""政策三级化（2026-09-17）的边界与约束回归。

金标 data/eval/policy/cases.yaml 钉的是「典型输入 → 期望结论」，这里钉的是边界：
月份算术、保修期闭区间、终身保与过保排除项的交互、三级匹配的优先级与误命中、
自动办理的硬约束、条款可回链，以及配置校验器该拒绝什么。
"""

from copy import deepcopy
from datetime import date

import pytest
from pydantic import ValidationError

from app.policy.engine import PolicyEngine
from app.policy.loader import ConfigError, PolicyLoader, validate
from app.policy.models import PolicyInput

TODAY = date(2026, 9, 17)


@pytest.fixture(scope="module")
def engine():
    return PolicyEngine()


def value(**kw) -> PolicyInput:
    return PolicyInput(
        **{
            "region_purchase": "US",
            "region_use": "US",
            "channel": "official_store",
            "purchase_date": date(2026, 8, 1),
            "fault_class": "quality",
            "today": TODAY,
            **kw,
        }
    )


def auto(result, remedy: str) -> bool:
    return any(r.remedy == remedy and r.auto_allowed for r in result.remedies)


def eligible(result) -> list[str]:
    return [r.remedy for r in result.remedies if r.eligible]


# ---------- 月份算术与保修期闭区间 ----------


@pytest.mark.parametrize(
    "sku,category,purchase,expected",
    [
        # 闰日 +12 月：2 月没有 29 日就压到 28 日
        ("EUFY-X10-PRO-OMNI", "robot_vacuum", date(2024, 2, 29), date(2025, 2, 28)),
        # 月末 +24 月：目标月有 31 日则保持 31 日
        ("ANKER-A1257", "power_bank", date(2026, 1, 31), date(2028, 1, 31)),
        ("EUFY-X10-PRO-OMNI", "robot_vacuum", date(2025, 8, 31), date(2026, 8, 31)),
    ],
)
def test_month_arithmetic_clamps_to_valid_day(engine, sku, category, purchase, expected):
    assert engine.decide(value(sku=sku, category=category, purchase_date=purchase)).warranty_end == expected


@pytest.mark.parametrize(
    "purchase,today,expected",
    [
        (TODAY, TODAY, True),  # 当天买当天报修
        (date(2025, 9, 17), date(2026, 9, 17), True),  # 保修最后一天
        (date(2025, 9, 17), date(2026, 9, 18), False),  # 后一天
    ],
)
def test_warranty_window_is_closed_interval(engine, purchase, today, expected):
    result = engine.decide(
        value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum", purchase_date=purchase, today=today)
    )
    assert result.within_warranty is expected


def test_lifetime_warranty_never_expires_and_skips_expiry_exclusion(engine):
    """终身保没有到期日，过保排除项（within_warranty: false）必须永不命中。"""
    result = engine.decide(value(sku="ANKER-A8121", category="cable", purchase_date=date(2005, 1, 1)))
    assert result.policy_id == "us_cable_powerline_lifetime"
    assert result.warranty_end is None and result.within_warranty
    assert not any(h["effect"] == "no_free_remedy" for h in result.exclusions_hit)
    assert auto(result, "parts")


# ---------- 三级匹配 ----------


@pytest.mark.parametrize(
    "kwargs,expected_policy",
    [
        # 部件级 30 压过品类兜底 10
        ({"sku": "EUFY-BP-S1-PRO", "category": "breast_pump", "part_class": "accessory"},
         "us_breast_pump_accessory"),
        # 系列级 20 压过品类兜底 10
        ({"sku": "ANKER-A1257", "category": "power_bank"}, "us_power_bank_prime"),
        # 系列例外 30 压过终身保 20：PowerLine III Flow 名字里含 PowerLine III
        ({"category": "cable", "series": "Anker PowerLine III Flow"}, "us_cable_powerline_flow"),
        # 系列与部件同时命中
        ({"category": "projector", "series": "Nebula X1 Pro", "part_class": "accessory"},
         "us_projector_nebula_x_accessory"),
    ],
)
def test_specificity_wins(engine, kwargs, expected_policy):
    assert engine.decide(value(**kwargs)).policy_id == expected_policy


@pytest.mark.parametrize(
    "kwargs,expected_policy",
    [
        # 子串匹配的误命中风险：X10 不该被投影仪的 Nebula X1 规则吃掉（跨品类）
        ({"sku": "EUFY-X10-PRO-OMNI", "category": "robot_vacuum"}, "us_robot_vacuum_base"),
        # Nano 不在充电器 24 个月那一行里
        ({"sku": "ANKER-A2337", "category": "charger"}, "us_charger_base"),
        # 充电站的 Prime 规则不该被 727 命中
        ({"category": "charging_station", "series": "Anker 727 充电站"}, "us_charging_station_base"),
        # 系列名大小写无关
        ({"category": "power_bank", "series": "prime"}, "us_power_bank_prime"),
    ],
)
def test_series_substring_does_not_overmatch(engine, kwargs, expected_policy):
    assert engine.decide(value(**kwargs)).policy_id == expected_policy


# ---------- 缺参数与未知输入 ----------


@pytest.mark.parametrize("field", ["region_purchase", "region_use", "channel", "purchase_date"])
def test_missing_input_goes_to_human_with_named_field(engine, field):
    result = engine.decide(value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum", **{field: None}))
    assert result.needs_human and field in result.missing_inputs


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sku": "NOT-IN-CATALOG"},  # 目录外型号不猜品类
        {"sku": "EUFY-X10-PRO-OMNI", "category": "robot_vacuum", "channel": "某个没见过的渠道"},
        {"sku": "EUFY-X10-PRO-OMNI", "category": "robot_vacuum", "region_purchase": "CN"},
        {"sku": "ANKER-A1761", "category": "portable_power_station"},  # 公开政策页无对应行
    ],
)
def test_no_source_means_human_not_a_guess(engine, kwargs):
    result = engine.decide(value(**kwargs))
    assert result.needs_human and "no_policy_matched" in result.needs_human_reasons
    assert result.warranty_end is None and not result.remedies


def test_illegal_part_class_rejected_by_contract():
    with pytest.raises(ValidationError):
        value(part_class="不存在的部件")


@pytest.mark.parametrize("alias", ["Anker Store", "Amazon", "官方"])
def test_channel_aliases_normalize(engine, alias):
    assert engine.decide(value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum", channel=alias)).matched


# ---------- 排除项与处置阶梯的交互 ----------


def test_user_damage_kills_free_remedies_without_escalating(engine):
    """人为损坏是政策明确不保，不是判不了——不该转人工。"""
    result = engine.decide(value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum", fault_class="user_damage"))
    assert not result.needs_human
    assert not [r for r in result.remedies if r.eligible and r.cost_bearer == "company"]


def test_out_of_warranty_vacuum_leaves_only_paid_repair(engine):
    result = engine.decide(
        value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum", purchase_date=date(2019, 1, 1))
    )
    assert eligible(result) == ["paid_repair"]
    assert not auto(result, "paid_repair"), "付费维修要客户掏钱，永不自动办理"


def test_paid_repair_only_offered_for_vacuum_category(engine):
    """官方只对 RoboVac / HomeVac / Vacuum 写了过保付费维修。"""
    result = engine.decide(
        value(sku="SOUNDCORE-A3035", category="headphones", purchase_date=date(2019, 1, 1))
    )
    assert not any(r.remedy == "paid_repair" for r in result.remedies)


def test_prior_replace_blocks_replace_but_not_parts(engine):
    """换过一次货之后，寄配件这一档仍然成立——这正是补上 parts 的价值。"""
    result = engine.decide(
        value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum", prior_remedies=["replace"])
    )
    assert not any(r.remedy == "replace" and r.eligible for r in result.remedies)
    assert auto(result, "parts") and auto(result, "repair")


def test_prior_parts_does_not_block_replace(engine):
    result = engine.decide(
        value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum", prior_remedies=["parts", "repair"])
    )
    assert auto(result, "replace")


# ---------- 自动办理的硬约束 ----------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sku": "EUFY-X10-PRO-OMNI", "category": "robot_vacuum"},
        {"sku": "ANKER-A1257", "category": "power_bank", "fault_class": "safety"},
        {"sku": "EUFY-X10-PRO-OMNI", "category": "robot_vacuum", "region_use": "DE"},
        {"sku": "EUFY-X10-PRO-OMNI", "category": "robot_vacuum", "channel": "unauthorized_dealer"},
        {"sku": "SOUNDCORE-A3130", "category": "speaker", "purchase_date": date(2019, 1, 1)},
    ],
)
def test_auto_allowed_stays_inside_its_fence(engine, kwargs):
    result = engine.decide(value(**kwargs))
    for remedy in result.remedies:
        if remedy.auto_allowed:
            assert remedy.eligible and remedy.cost_bearer == "company" and not result.needs_human
            assert remedy.remedy not in {"refund", "paid_repair"}


# ---------- 反幻觉：条款可回链 ----------


def test_every_clause_carries_a_source_url(engine):
    result = engine.decide(value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum"))
    clauses = [c for r in result.remedies for c in r.clauses]
    assert clauses
    assert all(c.source_url for c in clauses), [c.clause_id for c in clauses if not c.source_url]
    assert all(c.policy_version == "2026-09-17.1" for c in clauses)


def test_decision_is_reproducible(engine):
    one = value(sku="EUFY-X10-PRO-OMNI", category="robot_vacuum")
    other = value(sku="ANKER-A1257", category="power_bank")
    assert engine.decide(one).trace_id == engine.decide(one).trace_id
    assert engine.decide(one).trace_id != engine.decide(other).trace_id


# ---------- 配置校验器该拒绝什么 ----------


def _clash(bundle):
    other = deepcopy(bundle["policy"]["policies"][0])
    other["policy_id"] = "clash"
    bundle["policy"]["policies"].append(other)


def _auto_refund(bundle):
    for policy in bundle["policy"]["policies"]:
        for rule in policy["remedies"]:
            if rule["remedy"] == "refund":
                rule["auto_allowed"] = True
                return


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda b: b["policy"].__setitem__("source", "handwritten"), id="未知来源"),
        pytest.param(lambda b: b["policy"]["policies"][0]["source"].pop("quote"), id="缺原文引用"),
        pytest.param(lambda b: b["policy"]["policies"][0].__setitem__("warranty_months", 0), id="零月数"),
        pytest.param(lambda b: b["policy"]["policies"][0].__setitem__("warranty_months", -1), id="负月数"),
        pytest.param(lambda b: b["policy"]["policies"][0].__setitem__("warranty_months", "forever"), id="非法特殊值"),
        pytest.param(lambda b: b["policy"]["policies"][0]["applies_to"].__setitem__("color", "red"), id="未知匹配键"),
        pytest.param(lambda b: b["policy"]["policies"][0]["remedies"][0].__setitem__("remedy", "赔新机"), id="非法处置"),
        pytest.param(lambda b: b["policy"]["policies"][0]["remedies"][0].__setitem__("clauses", ["无此条款"]), id="悬空条款"),
        pytest.param(lambda b: b["policy"]["policies"][0]["remedies"][0]["when"].__setitem__("看心情", True), id="未知条件"),
        pytest.param(lambda b: b["clauses"]["clauses"]["US-W-3.0"].pop("source_url"), id="条款无出处"),
        pytest.param(_clash, id="同优先级交叠"),
        pytest.param(_auto_refund, id="退款自动办理"),
    ],
)
def test_loader_rejects(mutate):
    bundle = PolicyLoader().load()
    mutate(bundle)
    with pytest.raises(ConfigError):
        validate(bundle)

"""S0 确定性查询扩展（阶段 3）：只用已审核同义词表，不引入型号 / 数字，有上限、去重。"""

from __future__ import annotations

from app.diagnose.config import get_retrieval_config
from app.diagnose.expand import expand_queries, precise_tokens_in

SYN = {
    "尘盒": ["垃圾盒", "集尘盒"],
    "吸力下降": ["不吸", "吸不起", "吸力小", "吸力弱", "吸力变小"],
    "边刷": ["侧刷"],
    "扫地机器人": ["扫地机", "扫拖机器人", "机器人"],
}


def test_single_hit_replaces_with_canonical_word():
    assert expand_queries("EUFY-X9-PRO 垃圾盒卡不进去", SYN, 2) == ["EUFY-X9-PRO 尘盒卡不进去"]


def test_multiple_hits_yield_single_replacements_then_full():
    # 单点替换按同义词表顺序（吸力下降 → 边刷 → 扫地机器人），最后一个是全部替换
    out = expand_queries("扫地机 侧刷不转 不吸", SYN, 4)
    assert out == [
        "扫地机 侧刷不转 吸力下降",
        "扫地机 边刷不转 不吸",
        "扫地机器人 侧刷不转 不吸",
        "扫地机器人 边刷不转 吸力下降",
    ]
    assert expand_queries("扫地机 侧刷不转 不吸", SYN, 2) == out[:2]  # 上限


def test_no_variant_when_canonical_already_present_or_no_hit():
    assert expand_queries("扫地机器人 尘盒 吸力下降", SYN, 2) == []
    assert expand_queries("T2351 冒烟", SYN, 2) == []
    assert expand_queries("", SYN, 2) == [] and expand_queries("不吸", {}, 2) == []
    assert expand_queries("不吸", SYN, 0) == []


def test_longest_alt_wins_and_dedupe():
    # 「扫地机」是「扫地机器人」的前缀：原文已含规范词时不再生成变体
    assert expand_queries("扫地机器人 不吸", SYN, 3) == ["扫地机器人 吸力下降"]


def test_variants_never_add_model_tokens_or_numbers():
    bad = {"尘盒": ["垃圾盒"], "X9 Pro": ["机器"]}  # 故意放一个带型号的规范词
    out = expand_queries("机器 垃圾盒卡不进去", bad, 3)
    assert out == ["机器 尘盒卡不进去"]  # 引入 X9 的候选被丢弃


def test_repo_synonyms_expand_eval_style_queries():
    syn = get_retrieval_config().query_rewrite.synonyms
    assert expand_queries("T2351 不吸", syn, 2) == ["T2351 吸力下降"]
    v = expand_queries("T2351 侧刷不动", syn, 2)
    assert v == ["T2351 边刷不动"]
    # 歧义的「刷子」不能被自动定位到滚刷，保留给理解/澄清层处理。
    v2 = expand_queries("T2351 侧面那个小刷子不动了", syn, 2)
    assert v2 == []


def test_single_char_synonyms_are_ignored_for_expansion():
    syn = {"清扫": ["扫", "跑"], "清扫后": ["跑完了", "扫完"]}
    assert expand_queries("扫地机器人 冒烟", syn, 2) == []
    assert expand_queries("扫地机器人 跑完了一地渣", syn, 2) == ["扫地机器人 清扫后一地渣"]


def test_precise_tokens():
    assert precise_tokens_in("它一直说请检查滚刷") == ["请检查滚刷"]
    assert precise_tokens_in("吸力下降") == []

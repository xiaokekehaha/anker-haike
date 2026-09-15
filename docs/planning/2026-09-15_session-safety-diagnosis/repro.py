"""离线复现：泛化故障输入选中电机计划后，被计划自身的安全提示升级。"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from app.guide.steps import prepare_step
from app.plans.library import PlanLibrary
from app.rules.service import RulesService

async def main():
    library = PlanLibrary.from_yaml(ROOT / 'config/plans.yaml')
    rules = RulesService(ROOT / 'config/rules/safety_terms.yaml', hot_reload=False)
    plan = library.get('rv_suction_motor_fault')
    step = plan.first_step()
    source = library.evidence_snippet(step.instruction_src)
    incoming = rules.check_in(text='不能用了')
    pre = rules.check_pre_step(instruction=source, title=step.title, caution=step.caution)
    state = {
        'plan_cursor': {'plan_id': plan.plan_id, 'step_id': step.step_id},
        'evidence': {'manual': {'doc_id': 'manual_rv_v1', 'source': 'kb_manual'}},
        'plans_ranked': [{'plan_id': plan.plan_id, 'evidence_ids': ['manual']}],
    }
    result = await prepare_step(state=state, library=library, rules=rules, router=None,
                                lane='domestic', session_id='offline-safety-repro', budget_ms=0)
    print(json.dumps({'user_text': '不能用了', 'input_hits': incoming.flags,
                      'plan': plan.plan_id, 'step': step.step_id,
                      'instruction_src': step.instruction_src, 'source_text': source,
                      'matched_term': pre.term, 'outcome': result.outcome,
                      'escalate_reason': result.escalate_reason,
                      'minimal_probe': rules.check_pre_step(instruction='焦味', caution=None).action,
                      'remove_term_probe': rules.check_pre_step(
                          instruction=source.replace('焦味', ''), title=step.title,
                          caution=step.caution).action}, ensure_ascii=False, indent=2))
    assert not incoming.escalate
    assert result.outcome != 'escalate', '误升级复现：用户未报告安全风险，计划安全提示触发 R4'

asyncio.run(main())

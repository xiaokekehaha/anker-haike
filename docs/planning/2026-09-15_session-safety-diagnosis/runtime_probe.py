"""在运行镜像内离线检查两种计划推进结果及真实风险输入；不连接模型或数据库。"""
import asyncio
import json
from app.plans import PlanLibrary
from app.rules import RulesService
from app.sessions import graph
from app.settings import settings

async def main():
    library = PlanLibrary.from_yaml(settings.plans_config_path)
    rules = RulesService(settings.rules_config_path, hot_reload=False)
    graph.get_stream_writer = lambda: lambda event: None
    graph.get_plan_library = lambda: library
    graph.get_rules_service = lambda: rules
    graph.get_model_router = lambda: None
    results = []
    for confidence in (0.25, 0.5):
        state = {
            'session_id': 'offline-safety-probe', 'input_id': 'input',
            'active_issue_id': 'issue', 'text': '不能用了',
            'plan_cursor': {'plan_id': 'rv_suction_motor_fault', 'step_id': 's1'},
            'plans_ranked': [
                {'plan_id': 'rv_suction_motor_fault', 'confidence': 0.3},
                {'plan_id': 'rv_suction_dustbin_full', 'confidence': confidence},
            ],
            'evidence': {'manual': {'doc_id': 'manual_rv_v1', 'source': 'kb_manual'}},
        }
        result = await graph.guide(state)
        assert not result.get('safety_flags') and not result.get('risk_cases')
        if confidence == 0.25:
            assert result['escalate_reason'] == 'R2'
        else:
            assert result.get('escalate_reason') is None
            assert result['pending_card']['payload']['step']['plan_id'] == 'rv_suction_dustbin_full'
        results.append({'next_confidence': confidence, 'reason': result.get('escalate_reason'),
                        'step_dropped': result['guide_trace'][0]})
    for kwargs in ({'text': '机身有焦味'}, {'observations': ['smoke']}, {'action_note': '有焦味'}):
        assert rules.check_in(**kwargs).escalate
    assert not rules.check_in(text='不能用了').escalate
    print(json.dumps({'passed': True, 'results': results, 'real_risk_preserved': True}, ensure_ascii=False))

asyncio.run(main())

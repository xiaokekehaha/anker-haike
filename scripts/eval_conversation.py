"""Run independent semantic gold cases through the actual configured intake chain.

Usage: HAIKE_LLM=on uv run --project orchestrator python scripts/eval_conversation.py
Raw conversations are synthetic. No production session data is sent or deleted.
"""
import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import time

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestrator'))
from app.conversation.history import ConversationEntry
from app.conversation.interpret import interpret_turn
from app.conversation.reduce import reduce_turn
from app.models.runtime import get_model_router

ROOT = Path(__file__).resolve().parents[1]


def scenario(case):
    at = '2026-09-13T10:00:00+08:00'
    def fact(fid, value, iid):
        return dict(fact_id=fid, value=value, kind='symptom', status='active', revision=1,
                    source_entry_ids=[iid], recorded_at=at)
    issues = {
        'ear': dict(issue_id='ear', title='耳机没有声音', status='open', issue_revision=1,
                    device_ref={'device_ref_id':'ear-device','category':'headphones'}, facts=[fact('ear-fact','没有声音','first')]),
        'robot': dict(issue_id='robot', title='X9 Pro滚刷不转', status='open', issue_revision=1,
                    device_ref={'device_ref_id':'robot-device','category':'robot_vacuum'}, facts=[fact('robot-fact','滚刷不转','second')]),
    }
    pending = dict(kind='step_feedback', card_id='step1', input_token='token1', issue_id='robot',
        payload={'step': {'step_id':'brush1','title':'检查滚刷','instruction':'关机后检查滚刷是否缠绕毛发','expected_result':'清理后滚刷正常转动'}})
    if case.get('pending') == 'product':
        pending = dict(kind='select_product', card_id='products1', input_token='product-token', issue_id='robot',
            payload={'candidates':[{'sku':'T2351','name':'X9 Pro'},{'sku':'T2352','name':'X10 Pro Omni'}]})
    history = []
    for index,(iid,role,text) in enumerate([
        ('first','user','我的耳机没有声音'),('first-answer','assistant','是两侧都没有声音吗？'),
        ('second','user','另一个问题，我的X9 Pro机器人滚刷不转'),
        ('second-answer','assistant','请按卡片关机检查滚刷，然后反馈是否解决。'),
        (case['id'],'user',case['text'])],1):
        history.append(ConversationEntry(entry_id=iid,session_id='semantic-gold',run_id=f'run-{(index-1)//2}',
            kind='message',role=role,first_seq=index,last_seq=index,recorded_at=at,received_at=at if role=='user' else None,
            started_at=at if role=='assistant' else None,text=text,issue_id='ear' if index<3 else 'robot').as_dict())
    return dict(session_id='semantic-gold',input_id=case['id'],input_seq=5,at=at,text=case['text'],entry='message',
        active_issue_id='robot',issues=issues,history=history,pending_card=pending,product_hints=['X9 Pro'],
        product_confirmed={'sku':'T2351','name':'X9 Pro'},symptoms=['滚刷不转'],counters={'executed':1},
        steps_executed=[{'step_id':'brush0','feedback':'not_solved'}], risk_cases=[])


def judge(case, meaning, state):
    errors=[]
    data=meaning.model_dump()
    for key,value in case['expected'].items():
        actual=data.get(key)
        if key=='correction_target':
            if not any(c['fact_id']==value for c in data['corrections']): errors.append(key)
        elif key=='pending_kind':
            if (data.get('pending_answer') or {}).get('kind')!=value: errors.append(key)
        elif key=='clarification_required':
            if value and not actual and not data.get('clarification'): errors.append(key)
        elif key=='intent_one_of':
            if data['primary_intent'] not in value: errors.append(key)
        elif actual!=value:
            errors.append(f'{key}: {actual!r} != {value!r}')
    reduced=reduce_turn(copy.deepcopy(state),meaning,precheck_risk='冒烟' in state['text'])
    if case['family'] in {'history','explain','social','handoff_status','preference'}:
        if reduced['turn_decision']['escalation_trigger']: errors.append('control_escalated')
        if reduced['symptoms']!=['滚刷不转']: errors.append('control_changed_facts')
        if reduced['counters']!={'executed':1}: errors.append('control_changed_counters')
    if case['family']=='risk_reported' and reduced['turn_decision']['allowed_operations']:errors.append('risk_not_restricted')
    if case['family']=='risk_negated' and reduced['risk_cases']:errors.append('negated_risk_created')
    if case['family']=='resume':
        if reduced['active_issue_id']!='ear' or len(reduced['issues'])!=2:errors.append('resume_did_not_restore_existing_issue')
    return errors


async def main():
    cases=yaml.safe_load((ROOT/'data/eval/conversation/semantic-gold.yaml').read_text())['cases']
    router=get_model_router()
    if router is None: raise RuntimeError('Set HAIKE_LLM=on; real configured router required')
    output=ROOT/'docs/planning/2026-09-13_conversation-memory-v2-design/semantic-eval.json'
    rows=[]
    for case in cases:
        state=scenario(case); start=time.monotonic()
        meaning, context=await interpret_turn(router,state,lane=os.environ.get('MODEL_LANE','domestic'))
        errors=judge(case,meaning,state)
        if context.get('source')!='model':errors.append('model_unavailable')
        rows.append(dict(id=case['id'],family=case['family'],text=case['text'],expected=case['expected'],
                         actual=meaning.model_dump(),errors=errors,model=context.get('model_used'),
                         latency_ms=round((time.monotonic()-start)*1000),context_tokens=context.get('tokens')))
        output.write_text(json.dumps({'cases':rows,'passed':sum(not r['errors'] for r in rows),'total':len(rows)},ensure_ascii=False,indent=2)+'\n')
        print(f"{len(rows)}/{len(cases)} {case['id']} {'PASS' if not errors else errors}",flush=True)
    passed=sum(not r['errors'] for r in rows)
    print(f'accuracy={passed}/{len(rows)}',flush=True)
    return 0 if passed/len(rows)>=.95 else 1

if __name__=='__main__':sys.exit(asyncio.run(main()))

"""Offline diagnostic harness: actual graph/runner, recorded intake outputs, no live writes.
Run from repository root: uv run --project orchestrator python docs/planning/2026-09-13_conversation-context-diagnosis/repro.py
Nonzero exit is expected until conversational control is implemented.
"""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ['HAIKE_LLM'] = 'off'
os.environ['LANGFUSE_ENABLED'] = 'false'
from langgraph.checkpoint.memory import InMemorySaver
from app.intake.extract import IntakeOutcome
from app.sessions.graph import build_graph
from app.sessions.runner import run_message
from app.sessions.store import InMemorySessionStore

ROOT = Path(__file__).resolve().parent
recorded = json.loads((ROOT / 'session-events.json').read_text())
outputs = {}
for event in recorded:
    if event['event'] == 'model_call' and event['task'] == 'intake':
        text = event['input'][-1][1].split('<data kind="user_message">\n')[1].split('\n</data>')[0]
        outputs[text] = event['output']

async def intake(router, text, **kwargs):
    result = outputs.get(text, {'emotion_level':'calm','product_hints':[],'symptoms':[],'wants_human':False})
    return IntakeOutcome(emotion={'level':result['emotion_level'],'strategy':'normal'}, product_hints=result['product_hints'], symptoms=result['symptoms'], wants_human=result['wants_human'])

async def scenario(name, turns):
    store = InMemorySessionStore()
    graph = build_graph(InMemorySaver())
    row = await store.create_session()
    result = []
    for index, turn in enumerate(turns):
        kwargs = {'entry_action':{'kind':'request_human','action_id':f'action-{index}','expected_version':0}} if turn == '<request_human>' else {}
        events = [event async for event in run_message(store, graph, row.session_id, None if kwargs else turn, **kwargs)]
        assert events[-1]['type'] == 'done' and events[-1]['reason'] != 'error', events
        state = (await graph.aget_state({'configurable':{'thread_id':row.session_id}})).values
        summary = next((event['summary'] for event in events if event['type']=='escalation_summary'), None)
        item = {'input':turn,'stages':[e['stage'] for e in events if e['type']=='progress'], 'reply': ''.join(e['delta'] for e in events if e['type']=='message'), 'reason':state.get('escalate_reason'), 'category':state.get('category'), 'summary':summary}
        result.append(item)
        print(json.dumps({'scenario':name,**{k:v for k,v in item.items() if k!='summary'}},ensure_ascii=False))
    return result

async def main():
    with patch('app.sessions.graph.extract_intake', intake):
        full = await scenario('full', ['我的耳机没有声音','我机器人，冒烟了','我之前问了什么问题','有什么故障','新问题','<request_human>','刚说错了'])
        minimal = await scenario('minimal_new_issue', ['我机器人，冒烟了','新问题'])
        correction = await scenario('minimal_correction', ['<request_human>','刚说错了'])
    checks = {
        'history_query_answers_previous_problem': '没有声音' in full[2]['reply'],
        'new_issue_not_added_as_fault_observation': not any('新问题' in x for x in (full[4]['summary'] or {}).get('observations',[])),
        'new_issue_not_only_repeated_safety_transfer': '为了您的安全' not in minimal[-1]['reply'],
        'correction_not_only_repeated_human_transfer': '马上为您转接人工' not in correction[-1]['reply'],
    }
    (ROOT/'repro-result.json').write_text(json.dumps({'full':full,'minimal':minimal,'correction':correction,'checks':checks},ensure_ascii=False,indent=2))
    for label, ok in checks.items(): print(('PASS' if ok else 'FAIL')+' '+label)
    assert all(checks.values()), 'Conversation context symptoms reproduced; see repro-result.json'

if __name__ == "__main__":
    asyncio.run(main())

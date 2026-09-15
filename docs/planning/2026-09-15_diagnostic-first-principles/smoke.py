"""Local API smoke; creates only evaluation_source=smoke sessions, never edits real sessions."""
import json
import uuid
from pathlib import Path

import httpx

BASE = 'http://localhost:8000'
results = []


def events(response):
    response.raise_for_status()
    rows = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert not any(e['type'] == 'error' for e in rows), rows
    return rows


def send(client, sid, text):
    snap = client.get(f'/sessions/{sid}').json()
    rows = events(client.post(f'/sessions/{sid}/messages', data={
        'input_id': uuid.uuid4().hex, 'expected_version': snap['version'],
        'text': text, 'evaluation_source': 'smoke'}))
    results.append({'session_id': sid, 'input': text, 'types': [e['type'] for e in rows],
        'reply': ''.join(e.get('delta', '') for e in rows),
        'steps': [e['step'] for e in rows if e['type'] == 'step_card'],
        'reasons': [e['summary']['reason'] for e in rows if e['type'] == 'escalation_summary']})
    Path(__file__).with_name('smoke-result.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    return rows


def feedback(client, sid, value):
    snap = client.get(f'/sessions/{sid}').json()
    pending = snap['pending_input']
    rows = events(client.post(f'/sessions/{sid}/actions', json={
        'action_id': uuid.uuid4().hex, 'expected_version': snap['version'],
        'target_issue_id': snap['active_issue_id'], 'card_id': pending['card_id'],
        'input_token': pending['input_token'], 'kind': 'step_feedback', 'payload': {'feedback':value}}))
    results.append({'session_id':sid, 'feedback':value, 'steps':[e['step']['step_id'] for e in rows if e['type']=='step_card'],
        'reasons':[e['summary']['reason']['rule_id'] for e in rows if e['type']=='escalation_summary'],
        'stage':client.get(f'/sessions/{sid}').json()['stage']})
    Path(__file__).with_name('smoke-result.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    return rows


with httpx.Client(base_url=BASE, timeout=60) as client:
    sid = client.post('/sessions').json()['session_id']
    rows = send(client, sid, 'eufy X10 Pro Omni 启动不了')
    assert any(e['type']=='step_card' and e['step']['plan_id']=='rv_power_supply' for e in rows)
    assert not any(e['type']=='escalation_summary' for e in rows)
    before = client.get(f'/sessions/{sid}').json()['pending_input']['card_id']
    rows = send(client, sid, '还有其他的方案吗')
    assert '当前已确认的排查步骤' in ''.join(e.get('delta','') for e in rows)
    assert client.get(f'/sessions/{sid}').json()['pending_input']['card_id'] == before
    rows = feedback(client, sid, 'not_solved')
    assert any(e['type']=='step_card' and e['step']['step_id']=='s2' for e in rows)
    rows = feedback(client, sid, 'not_solved')
    assert any(e['type']=='escalation_summary' and e['summary']['reason']['rule_id']=='R2' for e in rows)
    rows = send(client, sid, '还有其他的方案吗')
    assert not any(e['type']=='step_card' for e in rows)
    rows = send(client, sid, '这台设备现在有焦味')
    assert any(e['type']=='escalation_summary' and e['summary']['reason']['rule_id']=='R4' for e in rows)
    assert not any(e['type']=='step_card' for e in rows)
    sid2 = client.post('/sessions').json()['session_id']
    rows = send(client, sid2, 'eufy X10 Pro Omni 不能用了')
    assert not any(e['type'] in {'step_card', 'escalation_summary'} for e in rows)
    assert any(e.get('delta') for e in rows)
    print(json.dumps({'passed':True, 'sessions':[sid,sid2], 'checks':len(results)}, ensure_ascii=False))

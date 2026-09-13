"""Explicit new-protocol metadata for business-flow tests.

Transport/idempotency tests exercise the raw endpoints separately. This helper does
not infer semantics, retry requests, or change supplied version/ID/target values.
"""
import uuid
import json


def model_task_text(call):
    """Read task material from the data layer; it no longer occupies the last message."""
    contents = []
    for message in call['messages']:
        content = message.content
        if isinstance(content, str) and content.startswith('会话状态数据：\n'):
            data = json.loads(content.split('\n', 1)[1])
            contents.append(data.get('task_data') or '')
        elif isinstance(content, str) and message.type != 'system':
            contents.append(content)
    return '\n'.join(contents)


async def message_form(client, url, data):
    snapshot = (await client.get(url.removesuffix('/messages'))).json()
    return {'input_id': uuid.uuid4().hex, 'expected_version': snapshot.get('version', 0), **data}


async def action_body(client, url, body):
    snapshot = (await client.get(url.removesuffix('/actions'))).json()
    return {'target_issue_id': snapshot.get('active_issue_id'), **body}


async def escalate_on_feedback(client, sid, reason='R1'):
    """Fixture a verify result at its boundary, then exercise the real input/commit path."""
    from dataclasses import replace
    from unittest.mock import patch
    from app.sessions.graph import apply_feedback
    from app.sessions import sse
    snapshot = (await client.get(f'/sessions/{sid}')).json()
    pending = snapshot['pending_input']
    assert pending and pending['kind'] == 'step_feedback', snapshot
    def result(**kwargs):
        return replace(apply_feedback(**kwargs), outcome='escalate', escalate_reason=reason)
    with patch('app.sessions.graph.apply_feedback', side_effect=result):
        response = await client.post(f'/sessions/{sid}/actions', json={
            'action_id': uuid.uuid4().hex, 'expected_version': snapshot['version'],
            'target_issue_id': snapshot['active_issue_id'], 'card_id': pending['card_id'],
            'input_token': pending['input_token'], 'kind': 'step_feedback',
            'payload': {'feedback': 'not_solved'}})
    assert response.status_code == 200, response.text
    events = sse.parse(response.text)
    assert not any(e['type'] == 'error' for e in events), events
    return events

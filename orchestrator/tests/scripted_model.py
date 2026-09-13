"""Fixture adapter for pre-authored business expectations, never used by the app.

Real semantic evaluations and test_conversation_* use the unified schema directly.
"""
import json
from app.models.fake import FakeChatModel


class ScriptedSemanticModel(FakeChatModel):
    def _next(self, messages, run_manager, kwargs):
        if self.script and any('TurnInterpretation' in str(m.content) for m in messages):
            item = self.script[0]
            try:
                data = json.loads(item) if isinstance(item, str) else item
            except ValueError:
                data = None
            if isinstance(data, dict) and 'wants_human' in data and 'primary_intent' not in data:
                current = str(messages[-1].content).split('\n', 1)[-1]
                authority = next((json.loads(m.content.split('\n', 1)[1]) for m in messages
                    if isinstance(m.content, str) and m.content.startswith('会话状态数据：\n')), {})
                corrections = [dict(fact_id=f['fact_id'], quote=current) for f in authority.get('facts', [])
                    if f['value'] in data.get('negated_symptoms', [])]
                intent = ('request_human' if data['wants_human'] else
                          'correct' if corrections or ('new_symptoms' in data and data.get('product_hints')) else
                          'supplement' if 'new_symptoms' in data else 'report_problem')
                self.script[0] = json.dumps(dict(primary_intent=intent,
                    emotion_level=data.get('emotion_level', 'calm'), product_hints=data.get('product_hints', []),
                    device_relation='current', corrections=corrections,
                    clarification='请说明需要更正的设备或现象。' if data.get('needs_clarification') else None,
                    facts=[dict(value=value, quote=current) for value in data.get('new_symptoms', data.get('symptoms', []))]), ensure_ascii=False)
        return super()._next(messages, run_manager, kwargs)

"""离线复现：原会话第二次回答经过真实 reduce_turn -> decide 被误判为 R7。"""
import copy
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from app.conversation.l3_intents import symptom_question_answer
from app.conversation.reduce import reduce_turn
from app.conversation.taxonomy import interview_answer
from app.sessions.clarify import decide, _has_symptom_text
from app.sessions.cards import get_catalog

state = json.loads(Path(sys.argv[1]).read_text())
meaning = symptom_question_answer(state)
assert meaning.symptom_answer.answer == 'no'
answered, accepted = interview_answer(state['symptom_interview'], meaning.symptom_answer, state['text'], state['input_id'])
updated = {**state, **reduce_turn(state, meaning)}
decision = decide(updated, abandoned_card=None)
fixed_status = copy.deepcopy(updated)
fixed_status['symptom_interview']['status'] = 'narrowed'
probe = decide(fixed_status, abandoned_card=None)
result = {
 'accepted': accepted,
 'answer_result': {'candidates': answered['candidates'], 'status': answered['status']},
 'after_reduce': {'candidates': updated['symptom_interview']['candidates'], 'status': updated['symptom_interview']['status'], 'codes': updated['symptom_codes']},
 'decision': {'outcome': decision.outcome, 'reason': decision.update.get('escalate_reason')},
 'change_only_interview_status': {'outcome': probe.outcome, 'codes': probe.update.get('symptom_codes')},
 'legacy_text_check': {text: _has_symptom_text(get_catalog(), text) for text in ['启动不了','无法启动']},
}
print(json.dumps(result,ensure_ascii=False,indent=2))
assert decision.update.get('escalate_reason') != 'R7', '有效回答已收敛到唯一候选，却触发 R7'

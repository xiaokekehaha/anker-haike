"""Offline causal probe for the ce6 R7 decision; no writes to application state."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from app.conversation.taxonomy import taxonomy
from app.sessions.clarify import decide

state = json.loads(Path(sys.argv[1]).read_text())
before = decide(copy.deepcopy(state), abandoned_card=None)
assert before.outcome == 'escalate'
assert before.update['diagnostic_decision']['reason'] == 'no_discriminating_question'
config = copy.deepcopy(taxonomy())
config['discriminators'].append({
    'question': '主要是吸尘、清扫不干净吗？',
    'splits': {'yes': ['吸力下降'], 'no': ['拖地异常']},
})
with patch('app.conversation.taxonomy.taxonomy', return_value=config):
    after = decide(copy.deepcopy(state), abandoned_card=None)
assert after.outcome == 'clarify'
result = {
    'session_id': 'ce6e9188c18a433b8d310dda24f8cc50',
    'accepted_answers': state['symptom_interview']['answers'],
    'remaining_candidates': state['symptom_interview']['candidates'],
    'before': {'outcome': before.outcome, 'reason': before.update['diagnostic_decision']['reason']},
    'add_one_question_only': {'outcome': after.outcome, 'question': after.detail['discriminator']['question']},
}
print(json.dumps(result, ensure_ascii=False, indent=2))

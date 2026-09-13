"""只读复现：已成功继续排障的会话不应重新呈现旧错误。"""
import json
from urllib.request import urlopen

SESSION_ID = 'd99223bb05244f7a8c254fe2136f78bc'
with urlopen(f'http://localhost:8000/sessions/{SESSION_ID}', timeout=5) as response:
    snapshot = json.load(response)
print(json.dumps({key: snapshot[key] for key in ('session_id', 'version', 'stage', 'pending_input', 'last_error')}, ensure_ascii=False, indent=2))
assert snapshot['last_error'] is None, 'BUG: 成功推进至下一步骤后，快照仍携带旧错误，前端 restore 会重新显示通用错误 toast'

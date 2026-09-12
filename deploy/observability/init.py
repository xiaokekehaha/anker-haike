"""生成本地 Langfuse 项目凭据；不覆盖已有文件，不输出密钥。"""
import os
import secrets
from pathlib import Path

path = Path(__file__).with_name('.env')
values = {
    'OBS_DB_PASSWORD': secrets.token_hex(24),
    'OBS_STORAGE_SECRET': secrets.token_hex(24),
    'OBS_AUTH_SECRET': secrets.token_hex(32),
    'OBS_SALT': secrets.token_hex(24),
    'OBS_ENCRYPTION_KEY': secrets.token_hex(32),
    'LANGFUSE_PUBLIC_KEY': 'pk-lf-' + secrets.token_hex(16),
    'LANGFUSE_SECRET_KEY': 'sk-lf-' + secrets.token_hex(24),
    'OBS_USER_PASSWORD': secrets.token_urlsafe(24),
}
try:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
except FileExistsError:
    print('Existing observability .env retained')
else:
    with os.fdopen(fd, 'w') as out:
        out.write(''.join(f'{k}={v}\n' for k, v in values.items()))
    print('Created private deploy/observability/.env')

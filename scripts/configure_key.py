"""Receive a key without echoing it, then store it only in the ignored server .env."""
import getpass
import os
import re
from pathlib import Path

key = getpass.getpass('DeepSeek API key (hidden): ').strip()
if not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,}', key):
    raise SystemExit('Invalid key format; nothing saved.')
path = Path(__file__).resolve().parents[1] / '.env'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write('DEEPSEEK_API_KEY=' + key + '\nDEEPSEEK_MODEL=deepseek-flash\n')
print('Server configuration saved. Key was not printed.')

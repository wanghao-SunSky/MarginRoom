"""Legacy DeepSeek shortcut; preserve other server settings."""
import getpass
from configure_model import ROOT, save_settings

key = getpass.getpass('DeepSeek API key (hidden): ').strip()
if not key or any(c.isspace() for c in key):
    raise SystemExit('Invalid key format; nothing saved.')
save_settings(ROOT / '.env', {'LLM_PROVIDER':'deepseek','LLM_BASE_URL':'https://api.deepseek.com',
    'LLM_MODEL':'deepseek-flash','LLM_API_KEY':key,'LLM_REASONING_EFFORT':'','LLM_THINKING':'disabled','LLM_DISPLAY_NAME':''})
print('Server configuration saved. Key was not printed. Restart MarginRoom to apply.')

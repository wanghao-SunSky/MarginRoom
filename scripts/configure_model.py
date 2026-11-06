"""Configure a server-side model without echoing the key or replacing other settings."""
import argparse
import getpass
import os
from pathlib import Path
import sys
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.model_config import DEFAULTS, get_model_config


def save_settings(path, settings):
    # Validate the complete prospective configuration before changing a file.
    previous = dict(os.environ)
    try:
        os.environ.update({k:v for k,v in dotenv_values(path).items() if v is not None})
        os.environ.update(settings)
        get_model_config()
    finally:
        os.environ.clear();os.environ.update(previous)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_WRONLY,0o600);os.fchmod(fd,0o600);os.close(fd)
    for key,value in settings.items():set_key(path,key,value)
    os.chmod(path,0o600)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',choices=DEFAULTS)
    args=parser.parse_args()
    provider=args.provider or input('Provider [deepseek / openai / anthropic] (deepseek): ').strip() or 'deepseek'
    if provider not in DEFAULTS:raise SystemExit('Unknown provider; nothing saved.')
    url,model,_,_=DEFAULTS[provider]
    url=input(f'Base URL [{url}]: ').strip() or url
    model=input(f'Model ID [{model}]: ').strip() or model
    effort=input('Reasoning effort (blank = model default; e.g. medium): ').strip()
    thinking=input('Claude thinking [blank / adaptive / enabled / disabled]: ').strip() if provider=='anthropic' else ''
    key=getpass.getpass('API key (hidden): ').strip()
    if not key or any(c.isspace() for c in key):raise SystemExit('Invalid key; nothing saved.')
    try:save_settings(ROOT/'.env',{'LLM_PROVIDER':provider,'LLM_BASE_URL':url,'LLM_MODEL':model,'LLM_API_KEY':key,
                                 'LLM_REASONING_EFFORT':effort,'LLM_THINKING':thinking,'LLM_DISPLAY_NAME':''})
    except (ValueError,TypeError):raise SystemExit('Invalid model settings; nothing saved. Check the provider, base URL, effort and token budget.')
    print('Model configuration saved to server .env. Restart MarginRoom to apply. Key was not printed.')

if __name__=='__main__':main()

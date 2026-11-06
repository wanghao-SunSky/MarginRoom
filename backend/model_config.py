"""Server-only model settings. Public status never exposes keys or endpoints."""
from dataclasses import dataclass, field
import os
from urllib.parse import urlsplit

DEFAULTS = {
    'deepseek': ('https://api.deepseek.com', 'deepseek-flash', 'DEEPSEEK_API_KEY', 'DeepSeek'),
    'openai': ('https://api.openai.com/v1', 'gpt-4.1', 'OPENAI_API_KEY', 'OpenAI'),
    'anthropic': ('https://api.anthropic.com/v1', 'claude-sonnet-4-6', 'ANTHROPIC_API_KEY', 'Claude'),
}

@dataclass(frozen=True)
class ModelConfig:
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    label: str = ''
    effort: str = ''
    thinking: str = ''
    thinking_budget: int = 2048
    max_tokens: int = 5000

    @property
    def endpoint(self):
        return self.base_url.rstrip('/') + ('/messages' if self.provider == 'anthropic' else '/chat/completions')

    def public(self):
        return {'configured': bool(self.api_key), 'provider': DEFAULTS[self.provider][3],
                'model': self.model, 'model_label': self.label, 'reasoning_effort': self.effort,
                'thinking': self.thinking, 'version': '0.1.0'}


def get_model_config():
    provider = os.getenv('LLM_PROVIDER', 'deepseek').strip().lower()
    if provider not in DEFAULTS:
        raise ValueError('LLM_PROVIDER must be deepseek, openai, or anthropic')
    url, model, key_env, _ = DEFAULTS[provider]
    base = os.getenv('LLM_BASE_URL', '').strip() or os.getenv(provider.upper() + '_BASE_URL', '').strip() or url
    parsed = urlsplit(base)
    if (parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.username or parsed.password
            or parsed.query or parsed.fragment or (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'))):
        raise ValueError('LLM_BASE_URL must be an HTTPS base URL (HTTP only for localhost)')
    if parsed.path.rstrip('/').endswith(('/chat/completions', '/messages', '/responses')):
        raise ValueError('LLM_BASE_URL must be the base URL, not a complete endpoint')
    model = os.getenv('LLM_MODEL', '').strip() or os.getenv(provider.upper() + '_MODEL', '').strip() or model
    key = os.getenv('LLM_API_KEY', '').strip() or os.getenv(key_env, '').strip()
    effort = os.getenv('LLM_REASONING_EFFORT', '').strip().lower()
    if effort not in ('', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'):
        raise ValueError('Invalid LLM_REASONING_EFFORT')
    thinking = os.getenv('LLM_THINKING', '').strip().lower()
    if thinking not in ('', 'disabled', 'enabled', 'adaptive'):
        raise ValueError('Invalid LLM_THINKING')
    if thinking == 'adaptive' and provider != 'anthropic':
        raise ValueError('Adaptive thinking is only supported by the Anthropic adapter')
    if thinking and provider == 'openai':
        raise ValueError('Use LLM_REASONING_EFFORT for OpenAI-compatible APIs; leave LLM_THINKING empty')
    budget = int(os.getenv('LLM_THINKING_BUDGET', '2048'))
    limit = int(os.getenv('LLM_MAX_TOKENS', '5000'))
    if not 256 <= limit <= 64000 or (provider == 'anthropic' and thinking == 'enabled' and not 1024 <= budget < limit):
        raise ValueError('Invalid model token budget')
    return ModelConfig(provider, base.rstrip('/'), model, key,
                       os.getenv('LLM_DISPLAY_NAME', '').strip() or model, effort, thinking, budget, limit)

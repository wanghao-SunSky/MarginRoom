# Model configuration / 模型配置

MarginRoom supports three server-side protocols. Configure one active model for the local app; the browser displays its name and explicit reasoning level. Keys stay in the ignored server `.env`, never browser storage or `/api/status`.

阅间支持以下三种服务端协议。为本地应用配置一个当前模型，阅读器显示其名称与明确配置的思考强度。密钥只保存在被 Git 忽略的服务端 `.env`，不会发送给浏览器。

| `LLM_PROVIDER` | Default base URL | Default model | Protocol |
| --- | --- | --- | --- |
| `deepseek` | `https://api.deepseek.com` | `deepseek-flash` | DeepSeek Chat Completions |
| `openai` | `https://api.openai.com/v1` | `gpt-4.1` | OpenAI-compatible Chat Completions |
| `anthropic` | `https://api.anthropic.com/v1` | `claude-sonnet-4-6` | Native Claude Messages |

Model availability depends on your account. These are editable starting values, not a claim that every compatible gateway/model is tested. OpenAI Responses-only models are not supported by this adapter.

模型是否可用以你的账号为准；默认值可改，不代表所有兼容网关和型号都已实测。本适配器暂不支持只能使用 OpenAI Responses API 的模型。

## Quick setup / 快速配置

```sh
uv run python scripts/configure_model.py
# Or select a protocol first / 也可以预选协议：
uv run python scripts/configure_model.py --provider openai
uv run python scripts/configure_model.py --provider anthropic
```

The wizard asks for base URL, model ID, optional reasoning effort and a hidden key. Existing unrelated `.env` settings are retained. Restart the server after saving. `scripts/configure_key.py` remains a shortcut for DeepSeek.

向导依次询问接口地址、模型 ID、可选思考强度和密钥（输入不回显），保留 `.env` 中其他设置。保存后重启服务。`scripts/configure_key.py` 仍可快捷配置 DeepSeek。

## Examples / 示例

Set these in the server `.env` (or equivalent process environment). Never commit a real key.

### OpenAI

```dotenv
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1
LLM_API_KEY=your-key-here
```

### OpenAI-compatible gateway / 兼容接口

```dotenv
LLM_PROVIDER=openai
LLM_BASE_URL=https://your-provider.example/v1
LLM_MODEL=your-model-id
LLM_API_KEY=your-key-here
LLM_REASONING_EFFORT=medium
```

The base URL does **not** include `/chat/completions`. The chosen model must support streaming and function/tool calling. This sends `reasoning_effort=medium` and `max_completion_tokens`; remove the effort setting if unsupported. No DeepSeek-specific `thinking` field is sent to this protocol.

地址不包含 `/chat/completions`。所选模型须支持流式输出和工具调用；以上示例发送 `reasoning_effort=medium` 与 `max_completion_tokens`，不支持思考强度的模型请将强度留空。不会向此协议发送 DeepSeek 专用的 `thinking` 参数。

### Claude native API / Claude 原生接口

```dotenv
LLM_PROVIDER=anthropic
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_MODEL=claude-sonnet-4-6
LLM_API_KEY=your-key-here
LLM_THINKING=adaptive
LLM_REASONING_EFFORT=medium
```

Claude uses `/messages`, `x-api-key`, `anthropic-version: 2023-06-01`, and `output_config.effort`. For a model without adaptive thinking/effort support, leave those settings empty. Legacy budgeted thinking can use `LLM_THINKING=enabled` and `LLM_THINKING_BUDGET=2048`, below `LLM_MAX_TOKENS`. Signed thinking blocks are replayed only to Claude within the current run and are not shown or saved as reader replies.

Claude 使用原生 Messages 协议。模型不支持自适应思考或强度参数时，将对应配置留空；预算式思考可设 `enabled` 和预算，预算必须小于最大输出额度。思考签名只用于本轮工具调用的续接，不展示或保存为阅读回复。

### Existing DeepSeek setup / 兼容旧配置

With no `LLM_PROVIDER`, DeepSeek remains the default. `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL` continue to work. Setting another provider never falls back to the DeepSeek key. `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` and each provider's `_BASE_URL` / `_MODEL` are also accepted; explicit nonempty `LLM_*` values take precedence. There is no automatic fallback to a different provider.

不设置供应商时仍默认 DeepSeek；旧的 `DEEPSEEK_*` 配置继续可用。改选其他供应商不会误用 DeepSeek 密钥。也支持供应商自己的环境变量，非空的 `LLM_*` 优先。不自动切换到其他供应商。

## Behavior and verification / 行为与验证

Reading tools, citations, navigation acknowledgements and saved-artifact checks remain shared across protocols. Incomplete streams, token-limit stops and provider errors are not treated as complete answers. There is no web search added by this configuration.

协议切换共用原有读书工具、引用检查、导航回执和保存检查；中断、超出输出上限或供应商报错不会被当成完整回答。本功能没有增加联网搜索。

Regression tests cover request parameters, private status fields, fragmented tool arguments, signed thinking replay, Gemini-style tool signatures, incomplete streams and provider errors. Real account availability still requires testing with your own key. API references: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [Claude streaming](https://platform.claude.com/docs/en/build-with-claude/streaming), [Claude effort](https://platform.claude.com/docs/en/build-with-claude/effort).

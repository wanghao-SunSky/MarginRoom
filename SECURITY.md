# Security and privacy / 安全与隐私

MarginRoom is an early, single-user localhost application. Bind to 127.0.0.1. It has no account authentication or multi-user authorization and must not be exposed directly to a public network. Same-origin checks and book-scoped tool validation do not make it a multi-tenant service.

Imported books, notes and conversations are stored locally. AI requests send the current section, selected text, recent history and tool-fetched material to the official DeepSeek API. Do not import confidential material unless that transfer is appropriate for you. A citation proves that a source section exists, not that the model's claim is correct.

Never put .env, API keys, databases or private books in issues or pull requests. Use GitHub private vulnerability reporting for security reports when available. For an ordinary bug, provide a minimal non-private sample.

这是个人本地预览版，没有账号登录或多用户权限，请仅绑定127.0.0.1。不要直接开放公网；来源检查与跨书工具限制不等于多用户安全隔离。AI问答会把相关原文与历史发送给DeepSeek官方接口。

请勿在公开Issue/PR里放密钥、数据库或私人书籍。安全问题优先使用GitHub私密漏洞报告；普通问题提供不含隐私的最小样例。

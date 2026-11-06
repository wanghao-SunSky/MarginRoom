# Release progress

## 2026-11-05 — Local reader and documentation sync

Updated the public reading core, six-format imports, source navigation, scroll turning and bilingual sample material. Kept the README narrative while aligning online/local use and capabilities. Hosted login, verification, OAuth, quotas and production settings are excluded so this repository stays independently runnable.

Validation: 141 backend tests passed, 1 native-tool test skipped; 8 frontend tests and a clean production build passed. Browser verified the direct local reading entry. Real-phone touch and high-load behavior remain unverified. Next: publish and check GitHub CI.

```mermaid
flowchart TD
 A[Public source preparation — complete] --> B[Local validation — complete]
 B --> C[GitHub publication — in progress]
 C --> D[Remote checks — pending]
```


## 2026-11-06 — 模型接口适配完成

现在可配置 DeepSeek、OpenAI 兼容接口和 Claude 原生接口的地址、密钥、模型与思考强度。Claude 工具格式不同，因此增加原生适配，而不是仅替换地址。密钥仅留在服务端。已有 DeepSeek 配置继续有效。

真实 OpenAI 兼容模型已用 Medium 参数完成查目录与工具结果续接；后端 237 项、前端 13 项检查通过，另有 2 项跳过。Claude 目前通过协议模拟测试，尚未做官方账号实测。下一步提交通用代码，然后独立切换线上配置并验收；不更改讲解提示词和已读规则。

```mermaid
flowchart TD
 A[模型接口适配：已完成] --> B[GitHub 提交：正在做]
 B --> C[正式站模型切换：未开始]
 C --> D[阅读问答验收：未开始]
```

### 2026-11-06 — 公开本地版阅读体验候选

这一阶段将通用的回答恢复、连续阅读、笔记定位、理解反馈与 Anki 导出适配到公开本地版，保留原来的首页和中英示例。按文件逐项适配，没有引入账号或试读身份功能；本地反馈保留单次并发、次数和超时限制。

后端 169 项通过、1 项按原有条件跳过，前端 16 项和 Node 24 构建通过。官方 Anki 引擎已在临时集合验证首次导入、重复导入、同卡更新与重开保留；图形界面、来源链接点击和 iPhone/iPad 真机仍未测。下一步交付本地提交供审查，尚不推送或发布。

```mermaid
flowchart TD
 A[本地版适配 已完成] --> B[自动检查 已完成]
 B --> C[候选审查 未开始]
```

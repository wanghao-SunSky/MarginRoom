# v0.1.0 preview checks / 预览版验收

Validated on macOS with Chrome, Python 3.12 and Node.js 22. A separate release directory was installed from lockfiles on the same Mac. This is not an independent clean-machine or mobile certification.

## Automated

- 73 backend tests passed, including protocol leakage, book boundaries, run idempotency, cancellation/stream timeouts, import parsing, localized errors and exports.
- 4 frontend tests passed; TypeScript check and Vite production build passed.
- `npm ci` reported no known dependency vulnerabilities at validation time. This is not a security audit.
- One upstream test-client deprecation warning and a large frontend bundle warning remain.

## Actual browser workflows

- Select text, save or cancel a note: selection toolbar and captured quote cleared; typing a question retains its captured quote.
- Official DeepSeek English and Chinese questions, source citations, section return, and agent-requested navigation with a page acknowledgement.
- Save/edit notes, save a chapter summary, generate a card, quickly edit both sides, reload and verify persistence.
- Download Anki TSV and Markdown notes, check edited content and source links using the active server origin.
- Import original PDF/Markdown/TXT fixtures; reject a malformed PDF and successfully import another file afterwards. Original PDF and extracted text views render.
- Search per-book conversation history with Enter, mark a section read, switch books/language and restore position.
- During a real streamed answer, clicking the conversation held scrollTop at 3649 while content height grew from 4067 to 7825. Stop completed as cancelled; later questions worked.
- Fresh release installation with no API key: only the two original examples are seeded, status says unconfigured, AI requests fail with a clear English message.

## Known limits / 验证边界

An English summary was saved successfully, but the following model response failed. That historical record did not contain the exception category, so its root cause is unknown. Safe exception-category diagnostics and clearer saved-work notices were added; a later Chinese summary completed end to end. External model/network availability remains a dependency.

This is a desktop localhost preview. Mobile/narrow-window behavior and a second physical machine were not verified. A requested viewport override did not take effect during this run. PDF extraction does not support OCR or diagram understanding. Citation validity does not establish answer correctness. See the README for supported formats and operating limits.

独立review发现并关闭了：前言绕过结构标签防护、嵌套代码围栏误切章节、同一任务不同同类产物被静默吞掉。选区残留、卡片连续编辑竞争及导出来源链接也已覆盖。不能据此承诺没有任何bug。

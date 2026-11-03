# 阅间 · MarginRoom

**读难懂的书时，把 AI 放在原文旁边。**

[English](README.md) · [简体中文](README.zh-CN.md)

导入技术书、教程或论文，圈出没懂的一段直接提问。对照回答里的来源继续读，再留下一条笔记或一张可以自己修改的卡片。问题、讨论和阅读位置放在一起。

> 初版预览，运行在自己的电脑上。AI 问答需要自备 **DeepSeek 官方 API Key 和调用余额**。相关原文与对话会发送给 DeepSeek；本地存储不等于离线模型。

![阅间阅读工作台](docs/images/reading-zh.jpg)

## 本地启动

需要 **Python 3.12+、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Node.js 22.12+ 与 npm**。便捷脚本用于 macOS/Linux；Windows 可在合适的终端逐条运行手动命令。

```sh
git clone https://github.com/wanghao-SunSky/MarginRoom.git
cd MarginRoom
uv sync
uv run python scripts/configure_key.py
cd web
npm ci
npm run build
cd ..
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

打开 **http://127.0.0.1:8765**。密钥输入不会回显，保存到已忽略的服务端 `.env`，不会进入前端。密钥在 [DeepSeek 官方平台](https://platform.deepseek.com/) 创建。不配置密钥也能浏览自带样例、手写笔记；AI 提问需要有效密钥。

后续可用 `./scripts/start.sh` 启动，缺少前端产物时会构建。改过前端后，在 `web` 中重新运行 `npm run build`。默认模型为 `deepseek-flash`，由 `.env` 的 `DEEPSEEK_MODEL` 指定；实际可用性与费用以 DeepSeek 账户为准。

## 先这样试一遍

1. 打开自带的中文阅读示例，或导入自己的 PDF、Markdown、UTF-8 TXT。
2. 圈出一句话，问“这个解释下”。系统同时提供当前段落和选中的原文。
3. 问“读取这一章，总结它解决的问题与关键思路”。Agent 可以读节、读章、搜书、查本书以前的对话。
4. 点回答中的来源，或者让它跳到另一节；“返回阅读位置”回到此前的段落。
5. 保存笔记或让它出复习卡，修改卡片后导出 Anki TSV。

顶部 **中文 / English** 切换界面、快捷问题和新回答的目标语言。导入的原文、已有笔记与旧对话保留原语言。

## 已有功能

- 带阅读位置和选区提问，引用定位原文；按要求跳转，等待页面确认执行。
- 笔记、章节小结、学习回顾、原始对话保存与本书历史检索。
- 卡片编辑、Markdown 笔记导出、Anki TSV 导出。
- 回答边生成边显示；点击对话区或向上滚动后停止自动跟随，点“回到最新”恢复。
- 取消、超时、工具调用预算、不完整回复的明确失败提示。
- 本机 SQLite 存储，自带原创中英文示例。

实现采用 React/TypeScript、FastAPI 和 SQLite。模型通过工具读资料、导航和保存成果；最终表达区分释义、因果追问、章节概括和完整展开，不为压缩篇幅额外调用一次模型。详见[架构说明](docs/architecture.md)。

## 当前边界

| 方面 | 实际支持 |
|---|---|
| 文件 | PDF、Markdown、UTF-8 TXT；单份最多 20 MB，PDF 最多 600 页。暂不支持 EPUB。 |
| PDF | 按页提取文字，可查看原版。没有 OCR、图片和图表理解；双栏、公式、表格可能提取错序。未识别章节目录，“本章”按可用文字范围读取。 |
| 回答 | 模型可能出错或过度概括。引用有效只代表来源段落存在，不代表每条判断都有原文支持。读取预算可能限制覆盖范围。 |
| 检索 | 关键词搜索与按需读取，没有向量索引。 |
| 复习 | 导出 Anki TSV，不是 `.apkg` 或 AnkiConnect；没有站内间隔复习。已读标记不等于已经掌握。 |
| 部署 | 没有用户登录，面向个人 localhost 使用。不要直接暴露到公网作为多用户服务。 |

## 数据与隐私

资料、笔记、卡片和对话保存在 `data/`。问答使用 **DeepSeek 官方 API**。隐私范围补充：每次问答会发送书名、当前小节（最多16,000字符）、选区（最多5,000字符）、问题、最近最多12条对话（每条最多5,000字符），以及后续工具读取的内容。并非只发送手动选中的一句话。密钥保留在服务端，项目未加入遥测或后台统计。

备份前停止服务，再复制 `data/`；`.env` 单独私密保存，不要提交到 Git。仓库仅含原创示例，不附带你的私人书籍、学习资料库或对话。[安全与隐私说明](SECURITY.md)。

## 导入 Anki

新建笔记类型，字段依次为 **ID / Question / Answer / Source / Tags**。导入 TSV 时开启 HTML，以 ID 为首字段去重。模板示例：

```html
<!-- 正面 -->
{{Question}}
<!-- 背面 -->
{{FrontSide}}<hr id="answer">{{Answer}}<br>{{Source}}
```

来源链接回本机阅间，需要服务运行。导出内容是草稿卡片，复习前请核对其正确性。

## 开发与反馈

```sh
uv run pytest -q
cd web
npm test
npm run build
```

前端开发可同时启动后端和 `web` 中的 `npm run dev`，Vite 将 `/api` 转到 8765 端口。

欢迎[提交问题](https://github.com/wanghao-SunSky/MarginRoom/issues)：写清复现步骤、预期与实际结果、浏览器和系统版本；需要样例时使用不含隐私的最小文件。不要上传密钥、私人书籍或整份对话数据库。[参与开发](CONTRIBUTING.md)。

代码采用 [MIT 协议](LICENSE)，第三方依赖保留各自许可。初版已测流程见[发布检查](docs/release-checks.md)，不承诺没有 bug。

# Contributing / 参与开发

Small, reproducible fixes are welcome. Explain the problem and expected behavior, add a regression test at the affected boundary, then run `uv run pytest -q` and `cd web && npm test && npm run build`. Keep changes scoped and preserve Chinese and English interface behavior.

Use original or openly licensed samples. Never include personal conversations, books, keys or databases. Use a separate `READING_DATA_DIR` and port for tests so the user's running reader is not affected. UI checks should use a separate browser page.

欢迎小而明确的修复：提供复现步骤与预期行为，补上对应回归，运行后端测试、前端测试与构建。保留中英文行为，不附带私人资料。测试使用独立数据目录、端口和页面。

"""Isolated, deterministic long stream; never mount against the user's data."""
import asyncio
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['READING_DATA_DIR'] = str(ROOT / 'data/ui-validation/db')
from backend import app as web, store as s
from backend.ingest import import_file

def seed(_):
    import_file('滚动验收样本.md', '# 滚动验收样本\n\n这是假数据，只用来验证流式阅读，不调用模型。'.encode())

async def fake_agent(rid):
    run = s.one('SELECT * FROM runs WHERE id=?', (rid,))
    content = ''
    try:
        for i in range(60):
            paragraph = f'\n\n**第 {i+1:02d} 段 · 阅读定位标记**\n\n你可以停在这句话慢慢看。后续段落继续生成，但不应该把正在看的内容推走。'
            for start in range(0, len(paragraph), 9):
                text = paragraph[start:start+9]
                content += text
                s.emit(rid, 'delta', {'text': text})
                await asyncio.sleep(.1)
        with s.db() as c:
            c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?)', (s.uid(),run['book_id'],rid,'assistant',content,run['section_id'],s.now()))
            c.execute("UPDATE runs SET status='complete' WHERE id=?", (rid,))
        s.emit(rid, 'done', {'usage': {}})
    except asyncio.CancelledError:
        with s.db() as c:c.execute("UPDATE runs SET status='cancelled' WHERE id=?", (rid,))
        s.emit(rid, 'cancelled', {'message': '测试已停止'})

web.seed = seed
web.run_agent = fake_agent
app = web.app

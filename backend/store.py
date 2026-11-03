from __future__ import annotations
import contextlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('READING_DATA_DIR', ROOT / 'data'))

def uid() -> str:
    return uuid.uuid4().hex

def now() -> float:
    return time.time()

@contextlib.contextmanager
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / 'reading.sqlite', timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS books (
          id TEXT PRIMARY KEY,title TEXT NOT NULL,subtitle TEXT NOT NULL DEFAULT '',
          format TEXT NOT NULL,file_path TEXT,source TEXT NOT NULL DEFAULT '',
          color TEXT NOT NULL DEFAULT 'teal',content_hash TEXT NOT NULL UNIQUE,
          created_at REAL NOT NULL,missing_pages INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sections (
          id TEXT PRIMARY KEY,book_id TEXT NOT NULL REFERENCES books(id),
          chapter TEXT NOT NULL,title TEXT NOT NULL,ordinal INTEGER NOT NULL,
          content TEXT NOT NULL,page INTEGER,UNIQUE(book_id,ordinal));
        CREATE TABLE IF NOT EXISTS positions (
          book_id TEXT PRIMARY KEY REFERENCES books(id),section_id TEXT REFERENCES sections(id),
          updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS marks (
          section_id TEXT PRIMARY KEY REFERENCES sections(id),created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY,book_id TEXT NOT NULL REFERENCES books(id),client_id TEXT NOT NULL,
          question TEXT NOT NULL,status TEXT NOT NULL,created_at REAL NOT NULL,
          error TEXT,usage TEXT NOT NULL DEFAULT '{}',selected_text TEXT NOT NULL DEFAULT '',
          section_id TEXT NOT NULL REFERENCES sections(id),view_revision INTEGER NOT NULL DEFAULT 0,language TEXT NOT NULL DEFAULT 'zh');
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(book_id) WHERE status='running';
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,book_id TEXT NOT NULL REFERENCES books(id),run_id TEXT REFERENCES runs(id),
          role TEXT NOT NULL,content TEXT NOT NULL,section_id TEXT REFERENCES sections(id),created_at REAL NOT NULL,
          UNIQUE(run_id,role));
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL REFERENCES runs(id),
          type TEXT NOT NULL,data TEXT NOT NULL,created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS commands (
          id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(id),client_id TEXT NOT NULL,
          action TEXT NOT NULL,section_id TEXT REFERENCES sections(id),expected_revision INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',result TEXT,expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS artifacts (
          id TEXT PRIMARY KEY,book_id TEXT NOT NULL REFERENCES books(id),run_id TEXT REFERENCES runs(id),
          kind TEXT NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,section_id TEXT REFERENCES sections(id),
          created_at REAL NOT NULL,slot INTEGER NOT NULL DEFAULT 0,UNIQUE(run_id,kind,slot));
        CREATE INDEX IF NOT EXISTS msg_book_time ON messages(book_id,created_at);
        CREATE INDEX IF NOT EXISTS event_run_id ON events(run_id,id);
        ''')
        if 'language' not in {r['name'] for r in c.execute('PRAGMA table_info(runs)')}:
            c.execute("ALTER TABLE runs ADD COLUMN language TEXT NOT NULL DEFAULT 'zh'")
        c.execute("UPDATE runs SET status='interrupted',error=CASE WHEN language='en' THEN 'The server restarted before this answer finished. You can ask again.' ELSE '服务已重启，这次回答未完成；可以重新提问。' END WHERE status='running'")
        c.execute("UPDATE commands SET status='expired' WHERE status='pending'")

def one(sql, args=()):
    with db() as c:
        row = c.execute(sql, args).fetchone()
        return dict(row) if row else None

def all_rows(sql, args=()):
    with db() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]

def emit(run_id, kind, data):
    with db() as c:
        c.execute('INSERT INTO events(run_id,type,data,created_at) VALUES (?,?,?,?)',
                  (run_id, kind, json.dumps(data, ensure_ascii=False), now()))

def save_artifact(book_id, kind, title, content, section_id=None, run_id=None, slot=0):
    if not title.strip() or not content.strip():raise ValueError('标题或内容为空')
    with db() as c:
        if run_id:
            run = c.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()
            if not run or run['status'] != 'running':
                raise ValueError('任务已停止，未保存新内容')
            old = c.execute('SELECT * FROM artifacts WHERE run_id=? AND kind=? AND slot=?', (run_id, kind, slot)).fetchone()
            if old:
                if (old['title'],old['content'],old['section_id'])!=(title,content,section_id):
                    raise ValueError('本次请求已保存同类内容，不能用另一份内容覆盖；请另发请求。')
                return dict(old)
        if section_id and not c.execute('SELECT 1 FROM sections WHERE id=? AND book_id=?', (section_id, book_id)).fetchone():
            raise ValueError('来源不属于当前资料')
        aid = uid()
        c.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)',
                  (aid, book_id, run_id, kind, title, content, section_id, now(), slot))
        return dict(c.execute('SELECT * FROM artifacts WHERE id=?', (aid,)).fetchone())

import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'student',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS profiles (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  disabilities TEXT DEFAULT '[]',
  preferred_formats TEXT DEFAULT '[]',
  subjects TEXT DEFAULT '[]',
  level INTEGER DEFAULT 1,
  language TEXT DEFAULT 'English',
  pace TEXT DEFAULT 'Medium',
  needs TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS content (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  subject TEXT NOT NULL,
  topic TEXT NOT NULL,
  difficulty INTEGER NOT NULL DEFAULT 1,
  format TEXT NOT NULL,
  duration_min INTEGER DEFAULT 5,
  language TEXT DEFAULT 'English',
  tags TEXT DEFAULT '',
  description TEXT DEFAULT '',
  url TEXT DEFAULT '',
  youtube_query TEXT DEFAULT '',
  video_id TEXT DEFAULT '',
  has_captions INTEGER DEFAULT 0,
  has_transcript INTEGER DEFAULT 0,
  audio_described INTEGER DEFAULT 0,
  screen_reader_friendly INTEGER DEFAULT 0,
  low_motion INTEGER DEFAULT 0,
  simple_language INTEGER DEFAULT 0,
  source TEXT DEFAULT 'seed',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject TEXT NOT NULL,
  name TEXT NOT NULL,
  order_idx INTEGER NOT NULL,
  UNIQUE(subject, name)
);
CREATE TABLE IF NOT EXISTS interactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  watch_seconds INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ratings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
  rating INTEGER,
  difficulty_feedback TEXT,
  accessible_issue INTEGER DEFAULT 0,
  comment TEXT,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, content_id)
);
CREATE TABLE IF NOT EXISTS quizzes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic TEXT NOT NULL,
  question TEXT NOT NULL,
  options TEXT NOT NULL,
  answer_idx INTEGER NOT NULL,
  explanation TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS quiz_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  topic TEXT NOT NULL,
  score INTEGER NOT NULL,
  total INTEGER NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bookmarks (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, content_id)
);
CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_inter_user ON interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_content_subject ON content(subject, topic);
"""


def connect(path=None):
    conn = sqlite3.connect(path or config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def fetch_all(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetch_one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None

"""Business logic. Pure functions over a sqlite3 connection, so they are easy to test."""
import json
import re
import threading
from datetime import date, datetime, timedelta

from . import security
from .constants import DISABILITY_PRESETS, FORMATS, LEVELS, NEED_LABELS, PACES, SUBJECTS, TOPICS
from .db import fetch_all, fetch_one
from .engine import HybridRecommender, accessibility_labels, adaptive_level, evaluate_offline
from .profile import get_profile

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTENT_FIELDS = [
    "title", "subject", "topic", "difficulty", "format", "duration_min", "language", "tags", "description",
    "url", "youtube_query", "video_id", "has_captions", "has_transcript", "audio_described",
    "screen_reader_friendly", "low_motion", "simple_language", "source",
]
FLAG_FIELDS = ["has_captions", "has_transcript", "audio_described", "screen_reader_friendly", "low_motion", "simple_language"]


class ServiceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ----------------------------------------------------------------- meta / auth
def meta():
    return {
        "subjects": SUBJECTS,
        "topics": TOPICS,
        "formats": FORMATS,
        "levels": {str(k): v for k, v in LEVELS.items()},
        "paces": PACES,
        "disability_presets": DISABILITY_PRESETS,
        "need_labels": NEED_LABELS,
    }


def register_user(conn, name, email, password):
    email = email.strip().lower()
    if not name.strip():
        raise ServiceError("Enter your name.")
    if not EMAIL_RE.match(email):
        raise ServiceError("Enter a valid email address.")
    if len(password) < 6:
        raise ServiceError("Use a password with at least 6 characters.")
    if fetch_one(conn, "SELECT id FROM users WHERE email=?", (email,)):
        raise ServiceError("An account with this email already exists.", 409)
    cur = conn.execute(
        "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?, 'student')",
        (name.strip(), email, security.hash_password(password)),
    )
    conn.commit()
    return login_payload(conn, cur.lastrowid)


def authenticate(conn, email, password):
    user = fetch_one(conn, "SELECT * FROM users WHERE email=?", (email.strip().lower(),))
    if not user or not security.verify_password(password, user["password_hash"]):
        raise ServiceError("Email or password is incorrect.", 401)
    return login_payload(conn, user["id"])


def login_payload(conn, user_id):
    user = fetch_one(conn, "SELECT id,name,email,role FROM users WHERE id=?", (user_id,))
    return {"token": security.create_token(user["id"], user["role"]), "user": user}


def get_user(conn, user_id):
    return fetch_one(conn, "SELECT id,name,email,role FROM users WHERE id=?", (user_id,))


# ----------------------------------------------------------------- content
def _decorate(item):
    item["accessibility"] = accessibility_labels(item)
    return item


def list_content(conn, q=None, subject=None, topic=None, fmt=None, difficulty=None, flags=None, limit=12, offset=0):
    where, params = [], []
    if q:
        where.append("(title LIKE ? OR topic LIKE ? OR tags LIKE ? OR description LIKE ?)")
        params += [f"%{q}%"] * 4
    for col, val in (("subject", subject), ("topic", topic), ("format", fmt), ("difficulty", difficulty)):
        if val:
            where.append(f"{col}=?")
            params.append(val)
    for f in flags or []:
        if f in FLAG_FIELDS:
            where.append(f"{f}=1")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM content {clause}", params).fetchone()[0]
    rows = fetch_all(conn, f"SELECT * FROM content {clause} ORDER BY subject, topic, id LIMIT ? OFFSET ?", params + [limit, offset])
    return {"total": total, "items": [_decorate(r) for r in rows]}


def get_content(conn, content_id):
    row = fetch_one(conn, "SELECT * FROM content WHERE id=?", (content_id,))
    if not row:
        raise ServiceError("Resource not found.", 404)
    return _decorate(row)


def _clean_content(data):
    out = {}
    for f in CONTENT_FIELDS:
        if f in data and data[f] is not None:
            out[f] = int(data[f]) if f in FLAG_FIELDS + ["difficulty", "duration_min"] else str(data[f])
    if "format" in out and out["format"] not in FORMATS:
        raise ServiceError(f"Format must be one of {', '.join(FORMATS)}.")
    if "difficulty" in out:
        out["difficulty"] = min(3, max(1, out["difficulty"]))
    return out


def create_content(conn, data):
    clean = _clean_content(data)
    for req in ("title", "subject", "topic", "format"):
        if not clean.get(req):
            raise ServiceError(f"'{req}' is required.")
    clean.setdefault("source", "admin")
    cols = list(clean)
    cur = conn.execute(f"INSERT INTO content({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", [clean[c] for c in cols])
    conn.commit()
    return get_content(conn, cur.lastrowid)


def update_content(conn, content_id, data):
    get_content(conn, content_id)
    clean = _clean_content(data)
    if clean:
        sets = ",".join(f"{c}=?" for c in clean)
        conn.execute(f"UPDATE content SET {sets} WHERE id=?", list(clean.values()) + [content_id])
        conn.commit()
    return get_content(conn, content_id)


def delete_content(conn, content_id):
    get_content(conn, content_id)
    conn.execute("DELETE FROM content WHERE id=?", (content_id,))
    conn.commit()


def bulk_create_content(conn, rows):
    created, errors = 0, []
    for i, row in enumerate(rows, start=1):
        try:
            create_content(conn, row)
            created += 1
        except (ServiceError, ValueError, TypeError) as e:
            errors.append(f"Row {i}: {e}")
    return {"created": created, "errors": errors}


# ----------------------------------------------------------------- recommendations
_engine_cache = {"key": None, "engine": None}
_engine_lock = threading.Lock()


def reset_engine():
    with _engine_lock:
        _engine_cache["key"] = None
        _engine_cache["engine"] = None


def get_engine(conn):
    db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    key = (
        db_file,
        conn.execute("SELECT COUNT(*), COALESCE(MAX(id),0) FROM content").fetchone()[:],
        conn.execute("SELECT COUNT(*), COALESCE(SUM(rating),0), COALESCE(MAX(updated_at),'') FROM ratings").fetchone()[:],
    )
    key = (key[0], tuple(key[1]), tuple(key[2]))
    with _engine_lock:
        if _engine_cache["key"] != key or _engine_cache["engine"] is None:
            _engine_cache["engine"] = HybridRecommender(conn).fit()
            _engine_cache["key"] = key
        engine = _engine_cache["engine"]
        engine.conn = conn
        return engine


def recommendations(conn, user_id, k=10, subject=None, fmt=None, topic=None):
    profile = get_profile(conn, user_id)
    result = get_engine(conn).recommend(user_id, profile, k=k, subject=subject, fmt=fmt, topic=topic)
    n_ratings = conn.execute("SELECT COUNT(*) FROM ratings WHERE user_id=? AND rating IS NOT NULL", (user_id,)).fetchone()[0]
    result["ratings_count"] = n_ratings
    result["cold_start"] = n_ratings == 0
    return result


def retrain(conn):
    reset_engine()
    engine = get_engine(conn)
    return {"items": len(engine.items), "collaborative_model": engine.svd is not None}


def evaluation(conn, k=10):
    return evaluate_offline(conn, k=k)


# ----------------------------------------------------------------- interactions / feedback
def record_interaction(conn, user_id, content_id, kind, watch_seconds=0):
    if kind not in ("view", "complete", "watch"):
        raise ServiceError("Interaction type must be view, watch or complete.")
    get_content(conn, content_id)
    conn.execute(
        "INSERT INTO interactions(user_id,content_id,type,watch_seconds) VALUES(?,?,?,?)",
        (user_id, content_id, kind, max(0, int(watch_seconds))),
    )
    conn.commit()
    return {"ok": True}


def submit_feedback(conn, user_id, content_id, rating=None, thumb=None, difficulty=None, accessibility_issue=False, comment=None):
    get_content(conn, content_id)
    if thumb == "up" and rating is None:
        rating = 5
    if thumb == "down" and rating is None:
        rating = 1
    if rating is not None and not 1 <= int(rating) <= 5:
        raise ServiceError("Rating must be between 1 and 5.")
    if difficulty not in (None, "", "too_hard", "too_easy", "just_right"):
        raise ServiceError("Difficulty must be too_hard, too_easy or just_right.")
    conn.execute(
        """INSERT INTO ratings(user_id,content_id,rating,difficulty_feedback,accessible_issue,comment)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(user_id,content_id) DO UPDATE SET
             rating=COALESCE(excluded.rating, ratings.rating),
             difficulty_feedback=COALESCE(excluded.difficulty_feedback, ratings.difficulty_feedback),
             accessible_issue=MAX(ratings.accessible_issue, excluded.accessible_issue),
             comment=COALESCE(excluded.comment, ratings.comment),
             updated_at=CURRENT_TIMESTAMP""",
        (user_id, content_id, rating, difficulty or None, 1 if accessibility_issue else 0, comment or None),
    )
    conn.commit()
    return {"ok": True, "level_target": adaptive_level(conn, user_id, get_profile(conn, user_id)["level"])}


# ----------------------------------------------------------------- learning path / quizzes
def learning_path(conn, user_id, subject):
    if subject not in TOPICS:
        raise ServiceError("Unknown subject.", 404)
    steps, found_next = [], False
    for i, topic in enumerate(TOPICS[subject]):
        done_items = conn.execute(
            """SELECT COUNT(DISTINCT i.content_id) FROM interactions i JOIN content c ON c.id=i.content_id
               WHERE i.user_id=? AND i.type='complete' AND c.topic=?""",
            (user_id, topic),
        ).fetchone()[0]
        best = conn.execute(
            "SELECT MAX(CAST(score AS REAL)/total) FROM quiz_attempts WHERE user_id=? AND topic=?", (user_id, topic)
        ).fetchone()[0]
        done = (best is not None and best >= 0.6) or done_items >= 2
        status = "done" if done else ("next" if not found_next else "upcoming")
        if status == "next":
            found_next = True
        steps.append(
            {"order": i + 1, "topic": topic, "status": status, "completed_resources": done_items,
             "best_quiz_pct": None if best is None else round(best * 100)}
        )
    return {"subject": subject, "steps": steps,
            "progress": round(100 * sum(s["status"] == "done" for s in steps) / len(steps))}


def quiz_topics(conn):
    return fetch_all(conn, "SELECT topic, COUNT(*) AS questions FROM quizzes GROUP BY topic ORDER BY topic")


def get_quiz(conn, topic):
    rows = fetch_all(conn, "SELECT id, question, options FROM quizzes WHERE topic=? ORDER BY id", (topic,))
    if not rows:
        raise ServiceError("No quiz for this topic yet.", 404)
    return {"topic": topic, "questions": [{"id": r["id"], "question": r["question"], "options": json.loads(r["options"])} for r in rows]}


def submit_quiz(conn, user_id, topic, answers):
    rows = fetch_all(conn, "SELECT * FROM quizzes WHERE topic=? ORDER BY id", (topic,))
    if not rows:
        raise ServiceError("No quiz for this topic yet.", 404)
    score, details = 0, []
    for r in rows:
        given = answers.get(str(r["id"]), answers.get(r["id"]))
        correct = given == r["answer_idx"]
        score += int(correct)
        opts = json.loads(r["options"])
        details.append({"question": r["question"], "your_answer": None if given is None else opts[given],
                        "correct_answer": opts[r["answer_idx"]], "correct": correct, "explanation": r["explanation"]})
    conn.execute("INSERT INTO quiz_attempts(user_id,topic,score,total) VALUES(?,?,?,?)", (user_id, topic, score, len(rows)))
    conn.commit()
    level = adaptive_level(conn, user_id, get_profile(conn, user_id)["level"])
    return {"score": score, "total": len(rows), "details": details, "level_target": level}


# ----------------------------------------------------------------- notes / bookmarks
def add_note(conn, user_id, content_id, text):
    if not text.strip():
        raise ServiceError("Write something before saving the note.")
    get_content(conn, content_id)
    cur = conn.execute("INSERT INTO notes(user_id,content_id,text) VALUES(?,?,?)", (user_id, content_id, text.strip()))
    conn.commit()
    return {"id": cur.lastrowid}


def list_notes(conn, user_id):
    return fetch_all(
        conn,
        """SELECT n.id, n.content_id, n.text, n.created_at, c.title FROM notes n JOIN content c ON c.id=n.content_id
           WHERE n.user_id=? ORDER BY n.id DESC""",
        (user_id,),
    )


def delete_note(conn, user_id, note_id):
    conn.execute("DELETE FROM notes WHERE id=? AND user_id=?", (note_id, user_id))
    conn.commit()


def toggle_bookmark(conn, user_id, content_id):
    get_content(conn, content_id)
    exists = conn.execute("SELECT 1 FROM bookmarks WHERE user_id=? AND content_id=?", (user_id, content_id)).fetchone()
    if exists:
        conn.execute("DELETE FROM bookmarks WHERE user_id=? AND content_id=?", (user_id, content_id))
    else:
        conn.execute("INSERT INTO bookmarks(user_id,content_id) VALUES(?,?)", (user_id, content_id))
    conn.commit()
    return {"bookmarked": not exists}


def list_bookmarks(conn, user_id):
    rows = fetch_all(
        conn, "SELECT c.* FROM bookmarks b JOIN content c ON c.id=b.content_id WHERE b.user_id=? ORDER BY b.created_at DESC", (user_id,)
    )
    return [_decorate(r) for r in rows]


# ----------------------------------------------------------------- analytics
def _streak(days):
    if not days:
        return 0
    have = {datetime.strptime(d, "%Y-%m-%d").date() for d in days}
    cur = date.today()
    if cur not in have:
        cur -= timedelta(days=1)
    n = 0
    while cur in have:
        n += 1
        cur -= timedelta(days=1)
    return n


def student_analytics(conn, user_id):
    profile = get_profile(conn, user_id)
    attempts = fetch_all(conn, "SELECT topic, score, total, created_at FROM quiz_attempts WHERE user_id=? ORDER BY id", (user_id,))
    for a in attempts:
        a["pct"] = round(100 * a["score"] / a["total"])
    by_subject = fetch_all(
        conn,
        """SELECT c.subject, COUNT(DISTINCT i.content_id) AS completed FROM interactions i JOIN content c ON c.id=i.content_id
           WHERE i.user_id=? AND i.type='complete' GROUP BY c.subject""",
        (user_id,),
    )
    days = [r["d"] for r in fetch_all(conn, "SELECT DISTINCT date(created_at) AS d FROM interactions WHERE user_id=?", (user_id,))]
    recent = fetch_all(
        conn,
        """SELECT c.id, c.title, c.subject, c.format, MAX(i.created_at) AS last_seen FROM interactions i
           JOIN content c ON c.id=i.content_id WHERE i.user_id=? GROUP BY c.id ORDER BY last_seen DESC LIMIT 5""",
        (user_id,),
    )
    one = lambda sql: conn.execute(sql, (user_id,)).fetchone()[0]
    return {
        "completed": one("SELECT COUNT(DISTINCT content_id) FROM interactions WHERE user_id=? AND type='complete'"),
        "rated": one("SELECT COUNT(*) FROM ratings WHERE user_id=? AND rating IS NOT NULL"),
        "quiz_attempts": attempts,
        "avg_quiz_pct": round(sum(a["pct"] for a in attempts) / len(attempts)) if attempts else None,
        "completed_by_subject": by_subject,
        "streak_days": _streak(days),
        "recent": recent,
        "level_target": adaptive_level(conn, user_id, profile["level"]),
        "level_name": LEVELS[round(adaptive_level(conn, user_id, profile["level"]))],
    }


def admin_analytics(conn):
    one = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "students": one("SELECT COUNT(*) FROM users WHERE role='student'"),
        "resources": one("SELECT COUNT(*) FROM content"),
        "interactions": one("SELECT COUNT(*) FROM interactions"),
        "avg_rating": round(one("SELECT COALESCE(AVG(rating),0) FROM ratings WHERE rating IS NOT NULL"), 2),
        "popular": fetch_all(
            conn,
            """SELECT c.id, c.title, c.subject, c.format, COUNT(i.id) AS interactions FROM content c
               JOIN interactions i ON i.content_id=c.id GROUP BY c.id ORDER BY interactions DESC LIMIT 10""",
        ),
        "by_format": fetch_all(conn, "SELECT format, COUNT(*) AS n FROM content GROUP BY format"),
        "by_subject": fetch_all(conn, "SELECT subject, COUNT(*) AS n FROM content GROUP BY subject"),
        "accessibility_reports": fetch_all(
            conn,
            """SELECT c.id, c.title, c.format, COUNT(*) AS reports FROM ratings r JOIN content c ON c.id=r.content_id
               WHERE r.accessible_issue=1 GROUP BY c.id ORDER BY reports DESC""",
        ),
        "quiz_avg_by_topic": fetch_all(
            conn,
            "SELECT topic, ROUND(100.0*SUM(score)/SUM(total)) AS avg_pct, COUNT(*) AS attempts FROM quiz_attempts GROUP BY topic ORDER BY topic",
        ),
    }

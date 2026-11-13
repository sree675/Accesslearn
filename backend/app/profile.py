import json

from .constants import NEEDS

DEFAULT_PROFILE = {
    "disabilities": [],
    "preferred_formats": [],
    "subjects": [],
    "level": 1,
    "language": "English",
    "pace": "Medium",
    "needs": {k: False for k in NEEDS},
}


def get_profile(conn, user_id):
    row = conn.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    prof = json.loads(json.dumps(DEFAULT_PROFILE))
    if row:
        prof["disabilities"] = json.loads(row["disabilities"] or "[]")
        prof["preferred_formats"] = json.loads(row["preferred_formats"] or "[]")
        prof["subjects"] = json.loads(row["subjects"] or "[]")
        prof["level"] = int(row["level"] or 1)
        prof["language"] = row["language"] or "English"
        prof["pace"] = row["pace"] or "Medium"
        stored = json.loads(row["needs"] or "{}")
        prof["needs"] = {k: bool(stored.get(k, False)) for k in NEEDS}
    return prof


def save_profile(conn, user_id, data):
    needs = {k: bool(data.get("needs", {}).get(k, False)) for k in NEEDS}
    level = min(3, max(1, int(data.get("level", 1))))
    conn.execute(
        """INSERT INTO profiles(user_id, disabilities, preferred_formats, subjects, level, language, pace, needs)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET disabilities=excluded.disabilities,
             preferred_formats=excluded.preferred_formats, subjects=excluded.subjects, level=excluded.level,
             language=excluded.language, pace=excluded.pace, needs=excluded.needs""",
        (
            user_id,
            json.dumps(data.get("disabilities", [])),
            json.dumps(data.get("preferred_formats", [])),
            json.dumps(data.get("subjects", [])),
            level,
            data.get("language", "English"),
            data.get("pace", "Medium"),
            json.dumps(needs),
        ),
    )
    conn.commit()
    return get_profile(conn, user_id)

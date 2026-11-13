"""Seed data: topics, 120 learning resources, quizzes, demo accounts and synthetic students."""
import json
import os
import random
from urllib.parse import quote_plus

from . import db
from .constants import DISABILITY_PRESETS, FORMATS, SUBJECTS, TOPICS
from .engine import violates_needs
from .profile import save_profile
from .security import hash_password

QUIZZES = {
    "Fractions": [
        ("What is 1/2 + 1/4?", ["1/6", "3/4", "2/6", "1/4"], 1, "1/2 equals 2/4, and 2/4 + 1/4 = 3/4."),
        ("Which fraction is the largest?", ["1/8", "1/3", "1/2", "1/5"], 2, "With the same numerator, a smaller denominator means a bigger piece."),
    ],
    "Algebra Basics": [
        ("Solve: x + 5 = 12", ["5", "7", "17", "6"], 1, "Subtract 5 from both sides, so x = 7."),
        ("In the term 3y, what is 3 called?", ["Variable", "Constant", "Coefficient", "Exponent"], 2, "The number multiplying a variable is its coefficient."),
    ],
    "Geometry Shapes": [
        ("How many sides does a hexagon have?", ["5", "6", "7", "8"], 1, "Hex means six."),
        ("The angles of a triangle add up to:", ["90 degrees", "180 degrees", "270 degrees", "360 degrees"], 1, "Triangle angles always add up to 180 degrees."),
    ],
    "Percentages": [
        ("What is 10% of 250?", ["10", "15", "25", "50"], 2, "10% is one tenth: 250 divided by 10 is 25."),
        ("50% is the same as which fraction?", ["1/4", "1/3", "1/2", "2/3"], 2, "50 out of 100 is one half."),
    ],
    "Photosynthesis": [
        ("Which gas do plants take in for photosynthesis?", ["Oxygen", "Nitrogen", "Carbon dioxide", "Hydrogen"], 2, "Plants use carbon dioxide, water and sunlight to make glucose."),
        ("Where does photosynthesis mostly happen?", ["Roots", "Chloroplasts", "Bark", "Petals"], 1, "Chloroplasts contain the green pigment chlorophyll."),
    ],
    "States of Matter": [
        ("Which state of matter has a fixed shape and volume?", ["Solid", "Liquid", "Gas", "Steam"], 0, "Particles in a solid are tightly packed and hold their shape."),
        ("Water turning into vapour is called:", ["Freezing", "Condensation", "Evaporation", "Melting"], 2, "Evaporation is liquid changing to gas."),
    ],
    "Human Body Systems": [
        ("Which organ pumps blood around the body?", ["Lungs", "Heart", "Liver", "Kidney"], 1, "The heart is a muscle that pumps blood."),
        ("Which system helps us breathe?", ["Digestive", "Respiratory", "Nervous", "Skeletal"], 1, "The respiratory system includes the lungs."),
    ],
    "Electricity Basics": [
        ("Which unit measures electric current?", ["Volt", "Ampere", "Ohm", "Watt"], 1, "Current is measured in amperes (amps)."),
        ("Which material is a good conductor?", ["Rubber", "Wood", "Copper", "Plastic"], 2, "Metals such as copper let current flow easily."),
    ],
    "Parts of Speech": [
        ("Which word is the verb in 'The dog runs fast'?", ["dog", "runs", "fast", "The"], 1, "A verb shows action, and runs is the action."),
        ("An adjective describes a:", ["Verb", "Noun", "Sentence", "Comma"], 1, "Adjectives describe nouns, such as a red ball."),
    ],
    "Reading Comprehension": [
        ("The main idea of a passage is:", ["A small detail", "What it is mostly about", "The title only", "The last line"], 1, "The main idea is the central point of the text."),
        ("Making a guess from clues in the text is called:", ["Summarising", "Inferring", "Copying", "Skipping"], 1, "Inferring combines clues with what you already know."),
    ],
    "Essay Writing": [
        ("The first paragraph of an essay is the:", ["Conclusion", "Introduction", "Body", "Reference list"], 1, "The introduction presents the topic."),
        ("A thesis statement shows the essay's:", ["Main argument", "Word count", "Font", "Date"], 0, "The thesis states the central claim."),
    ],
    "Grammar Tenses": [
        ("What is the past tense of 'go'?", ["goed", "went", "gone", "going"], 1, "Went is the irregular past tense of go."),
        ("Which sentence is in the future tense?", ["She sings.", "She sang.", "She will sing.", "She has sung."], 2, "Will plus a verb makes the future tense."),
    ],
    "Intro to Programming": [
        ("What is a variable?", ["A named place to store a value", "A type of screen", "A virus", "A keyboard key"], 0, "Variables store values the program can use later."),
        ("Which idea repeats code many times?", ["Loop", "Comment", "Import", "Variable"], 0, "A loop repeats instructions."),
    ],
    "Binary Numbers": [
        ("Binary uses which digits?", ["0 to 9", "0 and 1", "1 and 2", "A to F"], 1, "Binary has only two digits: 0 and 1."),
        ("Binary 101 equals which decimal number?", ["3", "4", "5", "6"], 2, "4 + 0 + 1 = 5."),
    ],
    "Internet Safety": [
        ("A strong password should be:", ["Your name", "Long and mixed", "12345", "Your birthday"], 1, "Long passwords with mixed characters are hard to guess."),
        ("What should you do with a suspicious link?", ["Click it", "Share it", "Do not click it and tell a trusted adult", "Reply to it"], 2, "Suspicious links can lead to scams or malware."),
    ],
    "Algorithms": [
        ("An algorithm is:", ["Step-by-step instructions to solve a problem", "A computer brand", "A bug", "A website"], 0, "An algorithm is a clear sequence of steps."),
        ("Which of these is a sorting task?", ["Putting numbers in order", "Drawing a picture", "Typing a name", "Opening a file"], 0, "Sorting arranges items in a chosen order."),
    ],
    "Indian Constitution": [
        ("When did the Indian Constitution come into effect?", ["15 Aug 1947", "26 Jan 1950", "2 Oct 1948", "26 Nov 1949"], 1, "It was adopted on 26 Nov 1949 and came into effect on 26 Jan 1950."),
        ("Who chaired the Drafting Committee?", ["B. R. Ambedkar", "Jawaharlal Nehru", "Mahatma Gandhi", "Sardar Patel"], 0, "Dr B. R. Ambedkar chaired the Drafting Committee."),
    ],
    "Climate and Weather": [
        ("Weather is:", ["A long-term pattern", "Short-term conditions of the atmosphere", "A season", "A map"], 1, "Weather is what happens day to day; climate is the long-term pattern."),
        ("Which instrument measures rainfall?", ["Thermometer", "Barometer", "Rain gauge", "Compass"], 2, "A rain gauge collects and measures rain."),
    ],
    "Map Skills": [
        ("A map legend (key) explains:", ["The symbols", "The title", "Only the scale", "The date"], 0, "The legend tells you what each symbol means."),
        ("Which direction is opposite to north?", ["East", "West", "South", "Northeast"], 2, "South is directly opposite north."),
    ],
    "Ancient Civilizations": [
        ("Which river supported the Indus Valley Civilization?", ["Nile", "Indus", "Tigris", "Yangtze"], 1, "The civilization grew along the Indus river."),
        ("Ancient Egyptians built pyramids as:", ["Markets", "Tombs", "Schools", "Ports"], 1, "Pyramids were royal tombs."),
    ],
    "Money Management": [
        ("Money you set aside for later is called:", ["Debt", "Savings", "Tax", "A bill"], 1, "Savings are money kept for future needs."),
        ("A budget helps you:", ["Plan income and spending", "Spend more", "Avoid saving", "Ignore bills"], 0, "A budget plans how money comes in and goes out."),
    ],
    "Time Management": [
        ("Doing the most important task first is called:", ["Prioritising", "Delaying", "Multitasking", "Skipping"], 0, "Prioritising puts important tasks first."),
        ("A to-do list helps by:", ["Making tasks visible", "Adding stress", "Hiding tasks", "Wasting time"], 0, "Writing tasks down makes them easier to plan."),
    ],
    "Communication Skills": [
        ("Active listening means:", ["Interrupting", "Giving full attention", "Looking at your phone", "Finishing their sentences"], 1, "Active listening is paying full attention to the speaker."),
        ("Which is a polite way to ask for help?", ["Do this now", "Could you please help me?", "Help!", "Whatever"], 1, "Please and a calm tone make requests polite."),
    ],
    "Healthy Habits": [
        ("How much sleep do school-age children usually need?", ["4 to 5 hours", "6 hours", "9 to 11 hours", "14 hours"], 2, "Most school-age children need 9 to 11 hours."),
        ("Which habit helps keep the body healthy?", ["Regular exercise", "Skipping meals", "Avoiding water", "Late-night screens"], 0, "Regular exercise supports heart, bones and mood."),
    ],
}

# (kind, label, minutes, captions, transcript, audio_described, screen_reader, low_motion, simple_language, query suffix)
VARIANTS = [
    ("video", "Captioned video lesson", 9, 1, 1, 0, 0, 0, 0, "explained step by step with captions"),
    ("video", "Narrated walkthrough with audio description", 7, 1, 1, 1, 1, 1, 0, "slow narrated walkthrough"),
    ("text", "Plain-language reading guide", 6, 0, 1, 0, 1, 1, 1, ""),
    ("audio", "Audio lesson", 10, 0, 0, 1, 1, 1, 1, "audio lesson explained simply"),
    ("interactive", "Interactive practice", 12, 0, 0, 0, 1, 0, 1, ""),
]
LEVEL_WORDS = {1: "beginner", 2: "intermediate", 3: "advanced"}


def build_content():
    items = []
    for si, (subject, topics) in enumerate(TOPICS.items()):
        for ti, topic in enumerate(topics):
            for vi, v in enumerate(VARIANTS):
                kind, label, mins, cap, tr, ad, sr, lm, sl, qs = v
                diff = ((ti + vi) % 3) + 1
                if kind in ("video", "audio"):
                    query = f"{topic} {subject} {qs}".strip()
                    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
                elif kind == "text":
                    query = ""
                    url = "https://en.wikipedia.org/w/index.php?search=" + quote_plus(topic)
                else:
                    query = ""
                    url = "https://www.khanacademy.org/search?page_search_query=" + quote_plus(topic)
                items.append(
                    dict(
                        title=f"{topic}: {label}",
                        subject=subject,
                        topic=topic,
                        difficulty=diff,
                        format=kind,
                        duration_min=mins,
                        language="English",
                        tags=f"{subject.lower()} {topic.lower()} {kind} {LEVEL_WORDS[diff]}",
                        description=f"A {LEVEL_WORDS[diff]} {kind} resource on {topic} ({subject}).",
                        url=url,
                        youtube_query=query,
                        video_id="",
                        has_captions=cap,
                        has_transcript=tr,
                        audio_described=ad,
                        screen_reader_friendly=sr,
                        low_motion=lm,
                        simple_language=sl,
                        source="seed",
                    )
                )
    return items


def insert_content(conn, item):
    cols = list(item.keys())
    cur = conn.execute(
        f"INSERT INTO content({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
        [item[c] for c in cols],
    )
    return cur.lastrowid


def seed_core(conn):
    for subject, topics in TOPICS.items():
        for i, t in enumerate(topics):
            conn.execute("INSERT OR IGNORE INTO topics(subject,name,order_idx) VALUES(?,?,?)", (subject, t, i))
    for item in build_content():
        insert_content(conn, item)
    for topic, qs in QUIZZES.items():
        for q, opts, ans, expl in qs:
            conn.execute(
                "INSERT INTO quizzes(topic,question,options,answer_idx,explanation) VALUES(?,?,?,?,?)",
                (topic, q, json.dumps(opts), ans, expl),
            )
    conn.commit()


def _create_user(conn, name, email, password, role="student"):
    cur = conn.execute(
        "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
        (name, email, hash_password(password), role),
    )
    return cur.lastrowid


def seed_users(conn, n_synthetic=40, seed=42):
    rng = random.Random(seed)
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    _create_user(conn, "Admin", "admin@accesslearn.com", admin_password, "admin")
    demo = _create_user(conn, "Demo Student", "student@accesslearn.com", "student123")
    save_profile(
        conn,
        demo,
        dict(
            disabilities=["Dyslexia"],
            preferred_formats=["text", "audio"],
            subjects=["Science", "English"],
            level=1,
            needs={"simple_language": True},
        ),
    )
    items = [dict(r) for r in conn.execute("SELECT * FROM content").fetchall()]
    disabilities = [d for d in DISABILITY_PRESETS if d != "None"]
    first_names = ["Asha", "Ravi", "Meena", "Karthik", "Divya", "Arun", "Priya", "Vijay", "Lakshmi", "Naveen"]
    for i in range(n_synthetic):
        uid = _create_user(conn, f"{rng.choice(first_names)} {i + 1}", f"student{i + 1}@example.com", "demo1234")
        dis = rng.choice(disabilities)
        needs = {k: True for k in DISABILITY_PRESETS[dis]}
        subjects = rng.sample(SUBJECTS, 2)
        formats = rng.sample(FORMATS, rng.randint(1, 2))
        level = rng.randint(1, 3)
        save_profile(
            conn,
            uid,
            dict(disabilities=[dis], preferred_formats=formats, subjects=subjects, level=level, needs=needs),
        )
        pool = [it for it in items if not violates_needs(it, needs)]
        for it in rng.sample(pool, min(len(pool), rng.randint(12, 25))):
            r = 2.4 + 1.3 * (it["subject"] in subjects) + 0.8 * (it["format"] in formats)
            r -= 0.5 * abs(it["difficulty"] - level) + 0 * rng.random()
            r = max(1, min(5, round(r + rng.gauss(0, 0.6))))
            conn.execute("INSERT INTO ratings(user_id,content_id,rating) VALUES(?,?,?)", (uid, it["id"], r))
            conn.execute(
                "INSERT INTO interactions(user_id,content_id,type,watch_seconds) VALUES(?,?,?,?)",
                (uid, it["id"], "complete", it["duration_min"] * 60),
            )
    conn.commit()


def seed_if_empty(conn, n_synthetic=40):
    if conn.execute("SELECT COUNT(*) FROM content").fetchone()[0] == 0:
        seed_core(conn)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        seed_users(conn, n_synthetic)


if __name__ == "__main__":
    c = db.connect()
    db.init_db(c)
    seed_if_empty(c)
    print("Database ready at", db.config.DB_PATH)

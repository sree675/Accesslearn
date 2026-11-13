"""AccessLearn Streamlit frontend.  Run from the project root:  streamlit run frontend/app.py"""
import json
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
import api  # noqa: E402
import theme  # noqa: E402

st.set_page_config(page_title="AccessLearn", page_icon="📚", layout="wide")


@st.cache_data(ttl=300, show_spinner=False)
def load_meta():
    return api.get("/meta")


def safe(fn, *args, **kwargs):
    """Call the API and show a readable error instead of a stack trace."""
    try:
        return fn(*args, **kwargs)
    except api.ApiError as e:
        st.error(str(e))
        return None


# ------------------------------------------------------------------ resource card
DIFF_FEEDBACK = {"No comment": None, "Too hard": "too_hard", "Too easy": "too_easy", "Just right": "just_right"}


def render_item(item, prefix, meta, show_reasons=True):
    with st.container(border=True):
        st.markdown(f"#### {item['title']}")
        level = meta["levels"][str(item["difficulty"])]
        st.caption(f"{item['subject']}, {item['topic']}. {item['format'].title()}, {level}, {item['duration_min']} min.")
        if item.get("description"):
            st.write(item["description"])
        if item.get("accessibility"):
            st.write("Accessibility: " + ", ".join(item["accessibility"]))
        if show_reasons and item.get("reasons"):
            st.write("Why this was suggested:")
            for r in item["reasons"]:
                st.markdown(f"- {r}")
        if item.get("video_id"):
            st.video(f"https://www.youtube.com/watch?v={item['video_id']}")
        elif item["format"] in ("video", "audio"):
            st.link_button("Search YouTube for this lesson", item["url"])
        else:
            st.link_button("Open resource", item["url"])

        c1, c2, c3 = st.columns([1, 1, 1])
        if c1.button("Mark as completed", key=f"{prefix}_done_{item['id']}"):
            if safe(api.post, "/interactions", {"content_id": item["id"], "type": "complete"}):
                st.toast("Marked as completed.")
        if c2.button("Bookmark or remove bookmark", key=f"{prefix}_bm_{item['id']}"):
            res = safe(api.post, f"/bookmarks/{item['id']}")
            if res:
                st.toast("Bookmarked." if res["bookmarked"] else "Bookmark removed.")
        with c3:
            theme.speak_button(f"{item['title']}. {item.get('description', '')}")

        with st.expander("Rate this resource or add a note"):
            rating = st.radio("Your rating (5 is best)", ["No rating", 1, 2, 3, 4, 5], horizontal=True, key=f"{prefix}_rate_{item['id']}")
            diff = st.selectbox("How was the difficulty?", list(DIFF_FEEDBACK), key=f"{prefix}_diff_{item['id']}")
            issue = st.checkbox("This did not work for my accessibility needs", key=f"{prefix}_issue_{item['id']}")
            if st.button("Send feedback", key=f"{prefix}_fb_{item['id']}"):
                body = {"content_id": item["id"], "difficulty": DIFF_FEEDBACK[diff], "accessibility_issue": issue}
                if rating != "No rating":
                    body["rating"] = int(rating)
                res = safe(api.post, "/feedback", body)
                if res:
                    st.success(f"Thanks. Your recommendations will adapt. Target level is now {res['level_target']} out of 3.")
            note = st.text_area("Your note", key=f"{prefix}_note_{item['id']}", height=80)
            if st.button("Save note", key=f"{prefix}_savenote_{item['id']}"):
                if safe(api.post, "/notes", {"content_id": item["id"], "text": note}):
                    st.success("Note saved.")


# ------------------------------------------------------------------ auth
def auth_screen():
    st.title("AccessLearn")
    st.write("Learning resources matched to your needs, your interests and your level.")
    tab_in, tab_up = st.tabs(["Sign in", "Create account"])
    with tab_in:
        with st.form("login"):
            email = st.text_input("Email", value="student@accesslearn.com")
            pw = st.text_input("Password", type="password", value="student123")
            if st.form_submit_button("Sign in"):
                res = safe(api.post, "/auth/login", {"email": email, "password": pw})
                if res:
                    st.session_state.token, st.session_state.user = res["token"], res["user"]
                    st.rerun()
        st.caption("Demo accounts: student@accesslearn.com / student123 and admin@accesslearn.com / admin123")
    with tab_up:
        with st.form("register"):
            name = st.text_input("Full name")
            email = st.text_input("Email address")
            pw = st.text_input("Password (6 or more characters)", type="password")
            if st.form_submit_button("Create account"):
                res = safe(api.post, "/auth/register", {"name": name, "email": email, "password": pw})
                if res:
                    st.session_state.token, st.session_state.user = res["token"], res["user"]
                    st.session_state.page = "My profile"
                    st.rerun()


# ------------------------------------------------------------------ pages
def page_recommendations(meta):
    st.header("Recommended for you")
    c1, c2, c3 = st.columns(3)
    subject = c1.selectbox("Subject", ["All"] + meta["subjects"])
    fmt = c2.selectbox("Format", ["All"] + meta["formats"])
    k = c3.slider("How many", 3, 20, 8)
    res = safe(api.get, "/recommendations", k=k, subject=None if subject == "All" else subject, format=None if fmt == "All" else fmt)
    if not res:
        return
    m1, m2, m3 = st.columns(3)
    m1.metric("Your target level", f"{res['level_target']} of 3")
    m2.metric("Ratings given", res["ratings_count"])
    m3.metric("Weight on similar students", f"{int(res['collab_weight'] * 100)}%")
    if res["cold_start"]:
        st.info("Rate a few resources and these suggestions will adapt to you. For now they follow your profile.")
    if not res["items"]:
        st.warning(
            "Nothing matches your current accessibility needs and filters. Review your profile or clear a filter. "
            "Seeded videos link to YouTube search results; embedded playback requires a teacher-added video ID."
        )
    for it in res["items"]:
        render_item(it, "rec", meta)


def page_browse(meta):
    st.header("Browse resources")
    c1, c2, c3, c4 = st.columns(4)
    q = c1.text_input("Search")
    subject = c2.selectbox("Subject", ["All"] + meta["subjects"])
    fmt = c3.selectbox("Format", ["All"] + meta["formats"])
    diff = c4.selectbox("Level", ["All", 1, 2, 3], format_func=lambda x: x if x == "All" else meta["levels"][str(x)])
    flag_labels = {"has_captions": "Captions", "audio_described": "Audio described", "screen_reader_friendly": "Screen-reader friendly",
                   "low_motion": "Low motion", "simple_language": "Simple language"}
    flags = st.multiselect("Accessibility features", list(flag_labels), format_func=lambda f: flag_labels[f])
    page = st.number_input("Page", min_value=1, value=1, step=1)
    res = safe(api.get, "/content", q=q, subject=None if subject == "All" else subject, format=None if fmt == "All" else fmt,
               difficulty=None if diff == "All" else diff, flags=",".join(flags), limit=8, offset=(page - 1) * 8)
    if not res:
        return
    st.write(f"{res['total']} resources found.")
    for it in res["items"]:
        render_item(it, "br", meta, show_reasons=False)


def page_path(meta):
    st.header("Learning path")
    subject = st.selectbox("Subject", meta["subjects"])
    res = safe(api.get, f"/learning-path/{subject}")
    if not res:
        return
    st.progress(res["progress"] / 100, text=f"{res['progress']}% of {subject} complete")
    labels = {"done": "Done", "next": "Up next", "upcoming": "Coming up"}
    for s in res["steps"]:
        with st.container(border=True):
            st.markdown(f"**Step {s['order']}: {s['topic']}** ({labels[s['status']]})")
            quiz = "no quiz taken yet" if s["best_quiz_pct"] is None else f"best quiz score {s['best_quiz_pct']}%"
            st.caption(f"{s['completed_resources']} resources completed, {quiz}.")
            if s["status"] == "next":
                recs = safe(api.get, "/recommendations", k=2, subject=subject, topic=s["topic"])
                for it in (recs or {}).get("items", []):
                    render_item(it, f"lp{s['order']}", meta)


def page_quiz(meta):
    st.header("Quizzes")
    topics = safe(api.get, "/quizzes") or []
    if not topics:
        return
    topic = st.selectbox("Topic", [t["topic"] for t in topics])
    quiz = safe(api.get, f"/quizzes/{topic}")
    if not quiz:
        return
    with st.form(f"quiz_{topic}"):
        answers = {}
        for q in quiz["questions"]:
            choice = st.radio(q["question"], q["options"], index=None, key=f"q_{q['id']}")
            answers[str(q["id"])] = None if choice is None else q["options"].index(choice)
        submitted = st.form_submit_button("Submit answers")
    if submitted:
        res = safe(api.post, f"/quizzes/{topic}/submit", {"answers": {k: v for k, v in answers.items() if v is not None}})
        if res:
            st.subheader(f"Score: {res['score']} out of {res['total']}")
            for d in res["details"]:
                st.markdown(f"**{d['question']}**")
                st.write(("Correct. " if d["correct"] else f"Not quite. The answer is {d['correct_answer']}. ") + d["explanation"])
            st.info(f"Your target level is now {res['level_target']} out of 3.")


def page_library(meta):
    st.header("My library")
    tab_b, tab_n = st.tabs(["Bookmarks", "Notes"])
    with tab_b:
        items = safe(api.get, "/bookmarks") or []
        if not items:
            st.write("No bookmarks yet. Use Bookmark on any resource.")
        for it in items:
            render_item(it, "bm", meta, show_reasons=False)
    with tab_n:
        notes = safe(api.get, "/notes") or []
        if not notes:
            st.write("No notes yet. Open a resource and use Rate this resource or add a note.")
        for n in notes:
            with st.container(border=True):
                st.markdown(f"**{n['title']}**")
                st.write(n["text"])
                if st.button("Delete note", key=f"dn_{n['id']}"):
                    safe(api.delete, f"/notes/{n['id']}")
                    st.rerun()


def page_dashboard(meta):
    st.header("My progress")
    s = safe(api.get, "/analytics/student")
    if not s:
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Completed", s["completed"])
    c2.metric("Average quiz score", "none yet" if s["avg_quiz_pct"] is None else f"{s['avg_quiz_pct']}%")
    c3.metric("Day streak", s["streak_days"])
    c4.metric("Current level", s["level_name"])
    if s["quiz_attempts"]:
        st.subheader("Quiz scores over time")
        df = pd.DataFrame(s["quiz_attempts"])
        df["attempt"] = range(1, len(df) + 1)
        st.line_chart(df.set_index("attempt")["pct"], y_label="Score (%)")
    if s["completed_by_subject"]:
        st.subheader("Completed by subject")
        st.bar_chart(pd.DataFrame(s["completed_by_subject"]).set_index("subject")["completed"])
    if s["recent"]:
        st.subheader("Recently viewed")
        for r in s["recent"]:
            st.write(f"{r['title']} ({r['subject']}, {r['format']})")


def page_profile(meta):
    st.header("My profile")
    prof = safe(api.get, "/students/me/profile")
    if not prof:
        return
    st.write("This is how AccessLearn decides what to show you. Anything you switch on under accessibility needs is a firm rule.")
    dis = st.multiselect("Disabilities or learning differences (optional)", list(meta["disability_presets"]), default=prof["disabilities"])
    suggested = {}
    for d in dis:
        suggested.update(meta["disability_presets"].get(d, {}))
    if suggested:
        st.caption("Suggested for your selection: " + ", ".join(meta["need_labels"][k].lower() for k in suggested))
    st.subheader("Accessibility needs")
    needs = {}
    for key, label in meta["need_labels"].items():
        needs[key] = st.checkbox(label, value=prof["needs"].get(key, False) or suggested.get(key, False), key=f"need_{key}_{','.join(sorted(dis))}")
    st.subheader("Learning preferences")
    formats = st.multiselect("Preferred formats", meta["formats"], default=prof["preferred_formats"])
    subjects = st.multiselect("Subjects I want to learn", meta["subjects"], default=prof["subjects"])
    c1, c2, c3 = st.columns(3)
    level = c1.selectbox("My starting level", [1, 2, 3], index=prof["level"] - 1, format_func=lambda x: meta["levels"][str(x)])
    pace = c2.selectbox("Pace", meta["paces"], index=meta["paces"].index(prof["pace"]))
    language = c3.text_input("Language", value=prof["language"])
    if st.button("Save profile"):
        body = dict(disabilities=dis, preferred_formats=formats, subjects=subjects, level=level, pace=pace, language=language, needs=needs)
        if safe(api.put, "/students/me/profile", body):
            st.success("Profile saved. Your recommendations are updated.")


# ------------------------------------------------------------------ admin
def page_admin(meta):
    st.header("Teacher and admin tools")
    t_an, t_cont, t_bulk, t_yt, t_eval = st.tabs(["Analytics", "Resources", "Bulk upload", "YouTube", "Model and evaluation"])
    with t_an:
        a = safe(api.get, "/analytics/admin")
        if a:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Students", a["students"])
            c2.metric("Resources", a["resources"])
            c3.metric("Interactions", a["interactions"])
            c4.metric("Average rating", a["avg_rating"])
            st.subheader("Most used resources")
            st.dataframe(pd.DataFrame(a["popular"]), use_container_width=True, hide_index=True)
            st.subheader("Accessibility reports from students")
            if a["accessibility_reports"]:
                st.dataframe(pd.DataFrame(a["accessibility_reports"]), use_container_width=True, hide_index=True)
            else:
                st.write("No accessibility problems have been reported.")
            st.subheader("Average quiz score by topic")
            if a["quiz_avg_by_topic"]:
                st.bar_chart(pd.DataFrame(a["quiz_avg_by_topic"]).set_index("topic")["avg_pct"])
            col1, col2 = st.columns(2)
            col1.bar_chart(pd.DataFrame(a["by_format"]).set_index("format")["n"])
            col2.bar_chart(pd.DataFrame(a["by_subject"]).set_index("subject")["n"])
    with t_cont:
        st.subheader("Add a resource")
        with st.form("add_content"):
            c1, c2 = st.columns(2)
            title = c1.text_input("Title")
            url = c2.text_input("Link (YouTube watch link or any page)")
            c3, c4, c5, c6 = st.columns(4)
            subject = c3.selectbox("Subject", meta["subjects"])
            topic = c4.text_input("Topic")
            fmt = c5.selectbox("Format", meta["formats"])
            diff = c6.selectbox("Level", [1, 2, 3], format_func=lambda x: meta["levels"][str(x)])
            desc = st.text_input("Description")
            minutes = st.number_input("Minutes", 1, 180, 8)
            flags = st.multiselect("Accessibility features", ["has_captions", "has_transcript", "audio_described", "screen_reader_friendly", "low_motion", "simple_language"])
            if st.form_submit_button("Add resource"):
                vid = url.split("v=")[1].split("&")[0] if "youtube.com/watch?v=" in url else ""
                body = dict(title=title, subject=subject, topic=topic, format=fmt, difficulty=diff, description=desc, url=url,
                            video_id=vid, duration_min=minutes, tags=f"{subject.lower()} {topic.lower()} {fmt}", **{f: 1 for f in flags})
                if safe(api.post, "/content", body):
                    st.success("Resource added.")
        st.subheader("Edit or delete")
        rid = st.number_input("Resource ID", min_value=1, step=1)
        new_title = st.text_input("New title (leave empty to keep)")
        e1, e2 = st.columns(2)
        if e1.button("Update title") and new_title:
            if safe(api.put, f"/content/{rid}", {"title": new_title}):
                st.success("Updated.")
        if e2.button("Delete resource"):
            if safe(api.delete, f"/content/{rid}"):
                st.success("Deleted.")
    with t_bulk:
        st.write("Upload a CSV with columns: title, subject, topic, format, difficulty, duration_min, url, description, tags, "
                 "has_captions, has_transcript, audio_described, screen_reader_friendly, low_motion, simple_language. "
                 "See data/sample_bulk_upload.csv.")
        up = st.file_uploader("CSV file", type="csv")
        if up is not None:
            df = pd.read_csv(up)
            st.dataframe(df.head(20), use_container_width=True, hide_index=True)
            if st.button("Import all rows"):
                rows = json.loads(df.dropna(how="all").to_json(orient="records"))
                res = safe(api.post, "/admin/content/bulk", rows)
                if res:
                    st.success(f"Imported {res['created']} resources.")
                    for e in res["errors"]:
                        st.warning(e)
    with t_yt:
        st.write("Needs YOUTUBE_API_KEY in your .env file. Videos are fetched with captions on and embedding allowed.")
        subj = st.selectbox("Subject", meta["subjects"], key="yt_s")
        topic = st.selectbox("Topic", meta["topics"][subj], key="yt_t")
        d = st.selectbox("Level", [1, 2, 3], format_func=lambda x: meta["levels"][str(x)], key="yt_d")
        n = st.slider("Videos to add", 1, 10, 3)
        if st.button("Fetch videos for this topic"):
            res = safe(api.post, "/admin/youtube-fetch", {"subject": subj, "topic": topic, "difficulty": d, "max_results": n})
            if res:
                st.success(f"Added {res['added']} videos.")
        st.divider()
        st.write("Replace the seeded YouTube search links with real video IDs so they play inside the app.")
        lim = st.slider("How many seeded videos to convert (each uses API quota)", 1, 50, 10)
        if st.button("Convert seeded video links"):
            res = safe(api.post, f"/admin/youtube-enrich?limit={lim}")
            if res:
                st.success(f"Converted {res['updated']} of {res['checked']} videos.")
    with t_eval:
        if st.button("Retrain the recommender now"):
            res = safe(api.post, "/admin/retrain")
            if res:
                st.success(f"Retrained on {res['items']} resources. Collaborative model active: {res['collaborative_model']}.")
        k = st.slider("Top K", 3, 20, 10)
        if st.button("Run offline evaluation"):
            res = safe(api.get, "/analytics/evaluation", k=k)
            if res:
                st.dataframe(pd.DataFrame({"metric": list(res), "value": [str(v) for v in res.values()]}), use_container_width=True, hide_index=True)
                st.caption("Precision and recall come from holding out 20% of each student's ratings. "
                           "The violation rates show how often a list would break a student's accessibility needs.")


# ------------------------------------------------------------------ main
def main():
    with st.sidebar:
        st.subheader("Display settings")
        scale = st.slider("Text size (%)", 90, 160, 100, 5)
        contrast = st.toggle("High contrast")
        dyslexia = st.toggle("Dyslexia-friendly font and spacing")
    theme.inject(scale, contrast, dyslexia)

    if "token" not in st.session_state:
        auth_screen()
        return

    meta = safe(load_meta)
    if not meta:
        return
    user = st.session_state.user
    pages = {
        "Recommended for you": page_recommendations, "Browse": page_browse, "Learning path": page_path,
        "Quizzes": page_quiz, "My library": page_library, "My progress": page_dashboard, "My profile": page_profile,
    }
    if user["role"] == "admin":
        pages = {"Teacher tools": page_admin, **{"Browse": page_browse}}
    with st.sidebar:
        st.write(f"Signed in as {user['name']}")
        names = list(pages)
        if st.session_state.get("page") not in names:
            st.session_state.page = names[0]
        st.radio("Go to", names, key="page")
        if st.button("Sign out"):
            for key in ("token", "user", "page"):
                st.session_state.pop(key, None)
            st.rerun()
    pages[st.session_state.page](meta)


main()

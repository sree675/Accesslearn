# AccessLearn: Personalized Educational Content Recommender for Students with Disabilities

A full-stack project. A FastAPI backend serves a hybrid recommender (content-based plus collaborative filtering)
with an adaptive feedback loop, and a Streamlit frontend gives students and teachers an accessible interface.
## Live app

[Open AccessLearn](https://accesslearn-dmvmkc9fmpt3lgp7zlpnjv.streamlit.app/)
## Quick start

Requires Python 3.10 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows.  On Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Mac/Linux: cp .env.example .env
```

Open two terminals in the project folder.

```bash
# Terminal 1: backend (API docs at http://127.0.0.1:8000/docs)
uvicorn backend.app.main:app --reload --port 8000

# Terminal 2: frontend (opens http://localhost:8501)
streamlit run frontend/app.py
```

On Windows you can also double-click `run_backend.bat` and `run_frontend.bat`.
The first start creates `accesslearn.db` and seeds it automatically.

**Demo accounts**

| Role | Email | Password |
|---|---|---|
| Student (dyslexia profile) | student@accesslearn.com | student123 |
| Teacher/Admin | admin@accesslearn.com | admin123 |

The seed also creates 40 synthetic students (`student1@example.com` to `student40@example.com`, password `demo1234`)
with ratings, so collaborative filtering works from the first run.

## Deployment

Deploy the backend to Render using the included `render.yaml` Blueprint. Set `ADMIN_PASSWORD`,
`YOUTUBE_API_KEY` (optional), and `ALLOWED_ORIGINS` to your Streamlit Community Cloud app origin;
Render generates `SECRET_KEY`. The admin password is applied when the database is first seeded.
Render's free service has an ephemeral filesystem, so the SQLite database can be reset on restart or
redeploy; use persistent external storage for data that must be retained.

Deploy `frontend/app.py` to Streamlit Community Cloud with the repository's root `requirements.txt`.
In the app's Streamlit secrets, set:

```toml
API_URL = "https://<your-render-service>.onrender.com"
```

## Features

- Sign in and registration with JWT tokens and PBKDF2 password hashing
- Student profile: disabilities, accessibility needs, preferred formats, subjects, level, pace, language
- Catalog of 120 resources across 6 subjects and 24 topics, in video, audio, text and interactive formats, each tagged with
  accessibility flags (captions, transcript, audio description, screen-reader friendly, low motion, simple language)
- **Hybrid recommender** with a hard accessibility filter, explanations for every suggestion and cold-start handling
- **Adaptive feedback loop**: ratings, thumbs, "too hard / too easy", "not accessible for me", completion tracking and quiz scores
  all change what you see next and your target difficulty
- YouTube support: seeded video entries link to YouTube searches; with an API key, admins fetch real captioned,
  embeddable videos that play inside the app
- Learning paths per subject, auto-graded quizzes, notes, bookmarks, student dashboard with streak and charts
- Teacher tools: analytics, accessibility reports, add/edit/delete resources, CSV bulk import, YouTube fetch, retrain, evaluation
- App accessibility: adjustable text size, high contrast, dyslexia-friendly font and spacing (Atkinson Hyperlegible by default,
  Lexend in dyslexia mode), large touch targets, visible focus ring, read-aloud button, reduced-motion support

## How the recommender works

1. **Hard filter.** Needs a student switches on are rules, not preferences. Captions required removes audio and video with no
   captions or transcript. Audio description or screen reader removes video that is not audio described, and non-video
   content that is not screen-reader friendly. Low motion and simple language remove anything not flagged. Resources the
   student rated 1 or 2, or reported as inaccessible, are removed too.
2. **Content-based score.** TF-IDF (unigrams and bigrams) over subject, topic, format, tags, title and description. The query is built
   from the student's subjects and formats. After a few ratings, similarity to items rated 4 or 5 is blended in and similarity to items rated 1 or 2 is subtracted.
3. **Collaborative score.** Mean-centered user-item matrix, TruncatedSVD, then each student's own ratings are folded into the latent
   space to predict ratings for unseen items. The collaborative weight grows with every rating (0.04 per rating, max 0.6), so new students rely on content-based scores.
4. **Final ranking** = 0.50 hybrid + 0.15 difficulty fit + 0.10 preferred format + 0.10 subject interest + 0.15 soft preferences
   (for example short lessons for ADHD). Completed items are halved, rated items are reduced to 70%. At most 2 items per topic appear in a default list.
5. **Adaptive difficulty.** Target level starts at the profile level, then moves +0.5 if the last 5 quizzes average 80% or more, -0.5 if below 50%,
   and by 0.25 for each recent "too easy" or "too hard" vote. It is clamped between 1 and 3.

## Project layout

```
backend/app/   main.py (routes), services.py (logic), engine.py (recommender), seed.py, db.py, profile.py, security.py, youtube.py
frontend/      app.py (pages), api.py (client), theme.py (accessibility styling)
tests/         test_core.py (10 tests)
scripts/       evaluate.py, reset_db.py
data/          sample_bulk_upload.csv
```

## Useful commands

```bash
python -m unittest discover -s tests -t .      # run the tests
python -m scripts.evaluate 10                  # offline evaluation at K=10
python -m scripts.reset_db                     # rebuild the database from scratch
```

## YouTube setup (optional)

1. Create a YouTube Data API v3 key in Google Cloud Console and put it in `.env` as `YOUTUBE_API_KEY`.
2. Sign in as admin, open Teacher tools, then YouTube.
3. Fetch videos for a topic, or convert the seeded video links to real, embeddable video IDs. Each search costs 100 quota units of the 10,000 daily default.

Without a key, video items open a YouTube search for that lesson in a new tab. These seeded links are searches, not hand-picked videos.

## Evaluation

`python -m scripts.evaluate` holds out 20% of each student's ratings. On the bundled synthetic data (40 students, K=10) it reported:

| Metric | Result |
|---|---|
| Precision@10, collaborative model | 0.031 |
| Precision@10, popularity baseline | 0.012 |
| Recall@10, collaborative model | 0.231 |
| Recall@10, popularity baseline | 0.096 |
| RMSE, SVD model vs user-mean baseline | 1.106 vs 1.117 |
| Accessibility violations in an unfiltered popularity list | 17.5% |
| Accessibility violations from this recommender | 0% |

These numbers come from small synthetic data, so treat them as a smoke test of the pipeline. They are not evidence of real-world accuracy.
Replace the synthetic ratings with real student data to get meaningful results. The rating prediction barely beats the baseline, so the main gains here
come from the ranking quality and the accessibility filter.

## Notes for production use

- Set a long random `SECRET_KEY` in `.env`, and restrict CORS origins in `backend/app/main.py`.
- SQLite is fine for a project demo. To use PostgreSQL or MySQL you would replace `db.py` and the SQL in `services.py`.
- Seeded text and interactive items link to Wikipedia and Khan Academy search pages, so replace them with vetted resources for real use.

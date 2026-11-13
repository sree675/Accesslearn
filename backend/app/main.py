"""AccessLearn API.  Run from the project root:  uvicorn backend.app.main:app --reload"""
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from . import db, services, youtube
from .profile import get_profile, save_profile
from .security import decode_token
from .seed import seed_if_empty
from .services import ServiceError


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    db.init_db(conn)
    seed_if_empty(conn)
    conn.close()
    yield


app = FastAPI(title="AccessLearn API", version="1.0.0", lifespan=lifespan,
              description="Personalized educational content recommender for students with disabilities.")
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=["*"], allow_headers=["*"])
bearer = HTTPBearer(auto_error=False)


@app.exception_handler(ServiceError)
async def service_error_handler(request, exc: ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


# ----------------------------------------------------------------- dependencies
def get_db():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer), conn=Depends(get_db)):
    if not creds:
        raise HTTPException(401, "Sign in to continue.")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(401, "Your session has expired. Sign in again.")
    user = services.get_user(conn, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "Account not found.")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only teachers and admins can do this.")
    return user


# ----------------------------------------------------------------- schemas
class RegisterIn(BaseModel):
    name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    disabilities: List[str] = []
    preferred_formats: List[str] = []
    subjects: List[str] = []
    level: int = Field(1, ge=1, le=3)
    language: str = "English"
    pace: str = "Medium"
    needs: Dict[str, bool] = {}


class FeedbackIn(BaseModel):
    content_id: int
    rating: Optional[int] = Field(None, ge=1, le=5)
    thumb: Optional[str] = None
    difficulty: Optional[str] = None
    accessibility_issue: bool = False
    comment: Optional[str] = None


class InteractionIn(BaseModel):
    content_id: int
    type: str = "view"
    watch_seconds: int = 0


class QuizSubmitIn(BaseModel):
    answers: Dict[str, int]


class NoteIn(BaseModel):
    content_id: int
    text: str


class YouTubeFetchIn(BaseModel):
    subject: str
    topic: str
    difficulty: int = 1
    max_results: int = Field(3, ge=1, le=10)


# ----------------------------------------------------------------- routes: public + auth
@app.get("/", tags=["meta"])
def root():
    return {"app": "AccessLearn", "docs": "/docs"}


@app.get("/meta", tags=["meta"])
def get_meta():
    return services.meta()


@app.post("/auth/register", tags=["auth"])
def register(body: RegisterIn, conn=Depends(get_db)):
    return services.register_user(conn, body.name, body.email, body.password)


@app.post("/auth/login", tags=["auth"])
def login(body: LoginIn, conn=Depends(get_db)):
    return services.authenticate(conn, body.email, body.password)


@app.get("/auth/me", tags=["auth"])
def me(user=Depends(current_user)):
    return user


# ----------------------------------------------------------------- student profile
@app.get("/students/me/profile", tags=["students"])
def read_profile(user=Depends(current_user), conn=Depends(get_db)):
    return get_profile(conn, user["id"])


@app.put("/students/me/profile", tags=["students"])
def write_profile(body: ProfileIn, user=Depends(current_user), conn=Depends(get_db)):
    return save_profile(conn, user["id"], body.model_dump())


# ----------------------------------------------------------------- content
@app.get("/content", tags=["content"])
def browse(q: Optional[str] = None, subject: Optional[str] = None, topic: Optional[str] = None,
           format: Optional[str] = None, difficulty: Optional[int] = None,
           flags: Optional[str] = Query(None, description="comma-separated: has_captions,low_motion,..."),
           limit: int = Query(12, le=100), offset: int = 0, user=Depends(current_user), conn=Depends(get_db)):
    return services.list_content(conn, q, subject, topic, format, difficulty, flags.split(",") if flags else None, limit, offset)


@app.get("/content/{content_id}", tags=["content"])
def one_content(content_id: int, user=Depends(current_user), conn=Depends(get_db)):
    return services.get_content(conn, content_id)


@app.post("/content", tags=["content"])
def add_content(body: dict, user=Depends(admin_user), conn=Depends(get_db)):
    return services.create_content(conn, body)


@app.put("/content/{content_id}", tags=["content"])
def edit_content(content_id: int, body: dict, user=Depends(admin_user), conn=Depends(get_db)):
    return services.update_content(conn, content_id, body)


@app.delete("/content/{content_id}", tags=["content"])
def remove_content(content_id: int, user=Depends(admin_user), conn=Depends(get_db)):
    services.delete_content(conn, content_id)
    return {"ok": True}


# ----------------------------------------------------------------- recommendations and feedback
@app.get("/recommendations", tags=["recommender"])
def recommend(k: int = Query(10, ge=1, le=30), subject: Optional[str] = None, format: Optional[str] = None,
              topic: Optional[str] = None, user=Depends(current_user), conn=Depends(get_db)):
    return services.recommendations(conn, user["id"], k, subject, format, topic)


@app.post("/feedback", tags=["recommender"])
def feedback(body: FeedbackIn, user=Depends(current_user), conn=Depends(get_db)):
    return services.submit_feedback(conn, user["id"], body.content_id, body.rating, body.thumb,
                                    body.difficulty, body.accessibility_issue, body.comment)


@app.post("/interactions", tags=["recommender"])
def interaction(body: InteractionIn, user=Depends(current_user), conn=Depends(get_db)):
    return services.record_interaction(conn, user["id"], body.content_id, body.type, body.watch_seconds)


# ----------------------------------------------------------------- learning path and quizzes
@app.get("/learning-path/{subject}", tags=["learning"])
def path(subject: str, user=Depends(current_user), conn=Depends(get_db)):
    return services.learning_path(conn, user["id"], subject)


@app.get("/quizzes", tags=["learning"])
def quizzes(user=Depends(current_user), conn=Depends(get_db)):
    return services.quiz_topics(conn)


@app.get("/quizzes/{topic}", tags=["learning"])
def quiz(topic: str, user=Depends(current_user), conn=Depends(get_db)):
    return services.get_quiz(conn, topic)


@app.post("/quizzes/{topic}/submit", tags=["learning"])
def quiz_submit(topic: str, body: QuizSubmitIn, user=Depends(current_user), conn=Depends(get_db)):
    return services.submit_quiz(conn, user["id"], topic, body.answers)


# ----------------------------------------------------------------- notes and bookmarks
@app.get("/notes", tags=["library"])
def notes(user=Depends(current_user), conn=Depends(get_db)):
    return services.list_notes(conn, user["id"])


@app.post("/notes", tags=["library"])
def create_note(body: NoteIn, user=Depends(current_user), conn=Depends(get_db)):
    return services.add_note(conn, user["id"], body.content_id, body.text)


@app.delete("/notes/{note_id}", tags=["library"])
def remove_note(note_id: int, user=Depends(current_user), conn=Depends(get_db)):
    services.delete_note(conn, user["id"], note_id)
    return {"ok": True}


@app.get("/bookmarks", tags=["library"])
def bookmarks(user=Depends(current_user), conn=Depends(get_db)):
    return services.list_bookmarks(conn, user["id"])


@app.post("/bookmarks/{content_id}", tags=["library"])
def bookmark(content_id: int, user=Depends(current_user), conn=Depends(get_db)):
    return services.toggle_bookmark(conn, user["id"], content_id)


# ----------------------------------------------------------------- analytics and admin
@app.get("/analytics/student", tags=["analytics"])
def student_stats(user=Depends(current_user), conn=Depends(get_db)):
    return services.student_analytics(conn, user["id"])


@app.get("/analytics/admin", tags=["analytics"])
def admin_stats(user=Depends(admin_user), conn=Depends(get_db)):
    return services.admin_analytics(conn)


@app.get("/analytics/evaluation", tags=["analytics"])
def evaluation(k: int = Query(10, ge=1, le=30), user=Depends(admin_user), conn=Depends(get_db)):
    return services.evaluation(conn, k)


@app.post("/admin/retrain", tags=["admin"])
def retrain(user=Depends(admin_user), conn=Depends(get_db)):
    return services.retrain(conn)


@app.post("/admin/content/bulk", tags=["admin"])
def bulk(rows: List[dict], user=Depends(admin_user), conn=Depends(get_db)):
    return services.bulk_create_content(conn, rows)


@app.post("/admin/youtube-fetch", tags=["admin"])
def youtube_fetch(body: YouTubeFetchIn, user=Depends(admin_user), conn=Depends(get_db)):
    added = youtube.fetch_and_add(conn, body.subject, body.topic, body.difficulty, body.max_results)
    return {"added": len(added), "items": added}


@app.post("/admin/youtube-enrich", tags=["admin"])
def youtube_enrich(limit: int = Query(20, ge=1, le=100), user=Depends(admin_user), conn=Depends(get_db)):
    return youtube.enrich_seed_videos(conn, limit)

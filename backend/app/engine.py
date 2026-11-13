"""Hybrid recommender: content-based + collaborative filtering with adaptive feedback."""
import math

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .constants import DISABILITY_SOFT_PREFS, LEVELS, NEED_LABELS, SHORT_MINUTES


# ----------------------------------------------------------------- accessibility
def violates_needs(item, needs):
    """Hard filter: True if the item cannot be used by a student with these needs."""
    fmt = item["format"]
    if needs.get("captions") and fmt in ("video", "audio") and not (item["has_captions"] or item["has_transcript"]):
        return True
    if needs.get("audio_description") and fmt == "video" and not item["audio_described"]:
        return True
    if needs.get("screen_reader"):
        if fmt == "video" and not item["audio_described"]:
            return True
        if fmt != "video" and not item["screen_reader_friendly"]:
            return True
    if needs.get("low_motion") and not item["low_motion"]:
        return True
    if needs.get("simple_language") and not item["simple_language"]:
        return True
    return False


def accessibility_labels(item):
    labels = []
    if item["has_captions"]:
        labels.append("Captions")
    if item["has_transcript"] and item["format"] in ("video", "audio"):
        labels.append("Transcript")
    if item["audio_described"]:
        labels.append("Audio described")
    if item["screen_reader_friendly"]:
        labels.append("Screen-reader friendly")
    if item["low_motion"]:
        labels.append("Low motion")
    if item["simple_language"]:
        labels.append("Simple language")
    return labels


def soft_prefs(disabilities):
    prefs = set()
    for d in disabilities:
        prefs.update(DISABILITY_SOFT_PREFS.get(d, []))
    return prefs


def _soft_match(item, prefs):
    if not prefs:
        return 1.0
    hits = 0
    for p in prefs:
        if p == "short" and item["duration_min"] <= SHORT_MINUTES:
            hits += 1
        elif p == "low_motion" and item["low_motion"]:
            hits += 1
        elif p == "simple_language" and item["simple_language"]:
            hits += 1
    return hits / len(prefs)


# ----------------------------------------------------------------- adaptive level
def adaptive_level(conn, user_id, base_level):
    """Nudge the student's target difficulty (1..3) from quiz results and feedback."""
    level = float(base_level)
    attempts = conn.execute(
        "SELECT score, total FROM quiz_attempts WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,)
    ).fetchall()
    if attempts:
        pct = sum(a["score"] for a in attempts) / max(1, sum(a["total"] for a in attempts))
        if pct >= 0.8:
            level += 0.5
        elif pct < 0.5:
            level -= 0.5
    fb = conn.execute(
        """SELECT difficulty_feedback FROM ratings
           WHERE user_id=? AND difficulty_feedback IN ('too_hard','too_easy')
           ORDER BY updated_at DESC, id DESC LIMIT 6""",
        (user_id,),
    ).fetchall()
    for row in fb:
        level += 0.25 if row["difficulty_feedback"] == "too_easy" else -0.25
    return round(min(3.0, max(1.0, level)), 2)


# ----------------------------------------------------------------- recommender
class HybridRecommender:
    def __init__(self, conn):
        self.conn = conn
        self.items = pd.DataFrame()
        self.X = None
        self.svd = None

    def fit(self):
        self.items = pd.read_sql_query("SELECT * FROM content", self.conn)
        self.svd = None
        if self.items.empty:
            self.X = None
            return self
        it = self.items
        text = (
            it["subject"] + " " + it["subject"] + " " + it["topic"] + " " + it["format"] + " "
            + it["tags"].fillna("") + " " + it["title"] + " " + it["description"].fillna("")
        )
        self.tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        self.X = self.tfidf.fit_transform(text)
        self.idx = {int(c): i for i, c in enumerate(it["id"])}
        ratings = pd.read_sql_query("SELECT user_id, content_id, rating FROM ratings WHERE rating IS NOT NULL", self.conn)
        if len(ratings) >= 10 and ratings["user_id"].nunique() >= 3:
            self.svd = _fit_svd(ratings, list(it["id"]))
        return self

    # --- component scores
    def _cb_scores(self, profile, liked, disliked):
        query = " ".join(profile["subjects"] * 3 + profile["preferred_formats"] * 2) or "learning"
        sim = cosine_similarity(self.tfidf.transform([query]), self.X).ravel()
        sim = sim / max(sim.max(), 1e-9)
        if liked:
            centroid = np.asarray(self.X[liked].mean(axis=0))
            sl = cosine_similarity(centroid, self.X).ravel()
            sl = sl / max(sl.max(), 1e-9)
            sim = 0.5 * sim + 0.5 * sl
        if disliked:
            centroid = np.asarray(self.X[disliked].mean(axis=0))
            sd = cosine_similarity(centroid, self.X).ravel()
            sd = sd / max(sd.max(), 1e-9)
            sim = np.clip(sim - 0.3 * sd, 0, 1)
        return sim

    def _cf_scores(self, user_ratings):
        if self.svd is None or not user_ratings:
            return None
        svd, n = self.svd, len(self.items)
        mean = float(np.mean(list(user_ratings.values())))
        vec = np.zeros((1, n))
        for cid, r in user_ratings.items():
            if cid in self.idx:
                vec[0, self.idx[cid]] = r - mean
        recon = svd.inverse_transform(svd.transform(vec))[0]
        return np.clip((mean + recon - 1) / 4, 0, 1)

    # --- public API
    def recommend(self, user_id, profile, k=10, subject=None, fmt=None, topic=None):
        if self.X is None:
            return {"items": [], "level_target": 1.0, "collab_weight": 0.0}
        rows = self.conn.execute(
            "SELECT content_id, rating, accessible_issue FROM ratings WHERE user_id=?", (user_id,)
        ).fetchall()
        user_ratings = {r["content_id"]: r["rating"] for r in rows if r["rating"] is not None}
        reported = {r["content_id"] for r in rows if r["accessible_issue"]}
        done = {
            r["content_id"]
            for r in self.conn.execute(
                "SELECT DISTINCT content_id FROM interactions WHERE user_id=? AND type='complete'", (user_id,)
            ).fetchall()
        }
        liked = [self.idx[c] for c, r in user_ratings.items() if r >= 4 and c in self.idx]
        disliked = [self.idx[c] for c, r in user_ratings.items() if r <= 2 and c in self.idx]

        cb = self._cb_scores(profile, liked, disliked)
        cf = self._cf_scores(user_ratings)
        w_cf = min(0.6, 0.04 * len(user_ratings)) if cf is not None else 0.0
        hybrid = (1 - w_cf) * cb + (w_cf * cf if cf is not None else 0)
        target = adaptive_level(self.conn, user_id, profile["level"])
        prefs = soft_prefs(profile["disabilities"])
        needs = profile["needs"]

        scored = []
        for i, row in enumerate(self.items.to_dict("records")):
            cid = int(row["id"])
            if violates_needs(row, needs) or cid in reported or user_ratings.get(cid, 5) <= 2:
                continue
            if subject and row["subject"] != subject:
                continue
            if fmt and row["format"] != fmt:
                continue
            if topic and row["topic"] != topic:
                continue
            diff_fit = 1 - min(abs(row["difficulty"] - target), 2) / 2
            in_subjects = row["subject"] in profile["subjects"]
            in_formats = row["format"] in profile["preferred_formats"]
            soft = _soft_match(row, prefs)
            score = 0.50 * hybrid[i] + 0.15 * diff_fit + 0.10 * in_formats + 0.10 * in_subjects + 0.15 * soft
            if cid in done:
                score *= 0.5
            elif cid in user_ratings:
                score *= 0.7
            reasons = self._reasons(row, needs, prefs, in_subjects, in_formats, diff_fit, target, cb[i], cf, i, w_cf, bool(liked))
            scored.append((score, cid, row, reasons))

        scored.sort(key=lambda t: -t[0])
        picked, per_topic = [], {}
        cap = 2 if not (subject or topic) else k
        for s in scored:
            if per_topic.get(s[2]["topic"], 0) < cap:
                picked.append(s)
                per_topic[s[2]["topic"]] = per_topic.get(s[2]["topic"], 0) + 1
            if len(picked) >= k:
                break
        for s in scored:
            if len(picked) >= k:
                break
            if s not in picked:
                picked.append(s)

        out = []
        for score, cid, row, reasons in picked:
            d = {key: row[key] for key in (
                "id", "title", "subject", "topic", "difficulty", "format", "duration_min",
                "description", "url", "video_id", "language")}
            d["score"] = round(float(score), 3)
            d["reasons"] = reasons
            d["accessibility"] = accessibility_labels(row)
            out.append(d)
        return {"items": out, "level_target": target, "collab_weight": round(w_cf, 2)}

    @staticmethod
    def _reasons(row, needs, prefs, in_subjects, in_formats, diff_fit, target, cb_i, cf, i, w_cf, has_liked):
        reasons = []
        active = [NEED_LABELS[k].lower() for k, v in needs.items() if v]
        if active:
            reasons.append("Meets your accessibility needs: " + ", ".join(active))
        if in_subjects:
            reasons.append(f"Matches your interest in {row['subject']}")
        if in_formats:
            reasons.append(f"A {row['format']} resource, one of your preferred formats")
        if has_liked and cb_i >= 0.6:
            reasons.append("Similar to resources you rated highly")
        if cf is not None and w_cf > 0.1 and cf[i] >= 0.7:
            reasons.append("Students with similar ratings found this helpful")
        if diff_fit == 1:
            reasons.append(f"Right difficulty for your current level ({LEVELS[round(target)]})")
        elif row["difficulty"] > target:
            reasons.append("A step up from your current level")
        else:
            reasons.append("A lighter review of your current level")
        if "short" in prefs and row["duration_min"] <= SHORT_MINUTES:
            reasons.append(f"Short lesson ({row['duration_min']} min)")
        return reasons[:4]


def _fit_svd(ratings, item_ids, n_components=8):
    pivot = ratings.pivot_table(index="user_id", columns="content_id", values="rating").reindex(columns=item_ids)
    vals = pivot.values
    mask = ~np.isnan(vals)
    means = np.nanmean(vals, axis=1)
    centered = np.where(mask, vals - means[:, None], 0.0)
    n = min(n_components, centered.shape[0] - 1, centered.shape[1] - 1)
    if n < 1:
        return None
    return TruncatedSVD(n_components=n, random_state=42).fit(centered)


# ----------------------------------------------------------------- evaluation
def evaluate_offline(conn, k=10, seed=42):
    """Hold out 20% of each student's ratings, then compare the collaborative model to a popularity baseline."""
    from .profile import get_profile

    items = pd.read_sql_query("SELECT * FROM content", conn)
    ratings = pd.read_sql_query("SELECT user_id, content_id, rating FROM ratings WHERE rating IS NOT NULL", conn)
    if ratings.empty or items.empty:
        return {"error": "Not enough rating data to evaluate."}
    rng = np.random.default_rng(seed)
    counts = ratings.groupby("user_id").size()
    eligible = list(counts[counts >= 6].index)
    test_idx = []
    for u in eligible:
        idx = ratings.index[ratings["user_id"] == u].to_numpy()
        n_test = max(1, math.ceil(0.2 * len(idx)))
        test_idx.extend(rng.choice(idx, size=n_test, replace=False))
    test = ratings.loc[test_idx]
    train = ratings.drop(index=test_idx)
    item_ids = list(items["id"])
    svd = _fit_svd(train, item_ids)
    if svd is None:
        return {"error": "Not enough rating data to evaluate."}
    id_pos = {int(c): i for i, c in enumerate(item_ids)}
    pop = train.groupby("content_id")["rating"].agg(["mean", "count"])
    pop_score = {int(c): (r["mean"] * min(r["count"], 5) / 5) for c, r in pop.iterrows()}
    records = items.to_dict("records")

    se_model, se_base, precs, recs_, precs_b, recs_b = [], [], [], [], [], []
    recommended, viol_model, viol_pop, total_model = set(), 0, 0, 0
    for u in eligible:
        tr = train[train["user_id"] == u]
        te = test[test["user_id"] == u]
        mean = tr["rating"].mean()
        vec = np.zeros((1, len(item_ids)))
        for c, r in zip(tr["content_id"], tr["rating"]):
            vec[0, id_pos[int(c)]] = r - mean
        pred = np.clip(mean + svd.inverse_transform(svd.transform(vec))[0], 1, 5)
        for c, r in zip(te["content_id"], te["rating"]):
            se_model.append((pred[id_pos[int(c)]] - r) ** 2)
            se_base.append((mean - r) ** 2)
        needs = get_profile(conn, int(u))["needs"]
        seen = set(int(c) for c in tr["content_id"])
        relevant = set(int(c) for c, r in zip(te["content_id"], te["rating"]) if r >= 4)
        ok = [int(records[i]["id"]) for i in range(len(records))
              if int(records[i]["id"]) not in seen and not violates_needs(records[i], needs)]
        top_model = sorted(ok, key=lambda c: -pred[id_pos[c]])[:k]
        top_pop = sorted(ok, key=lambda c: -pop_score.get(c, 0))[:k]
        recommended.update(top_model)
        total_model += len(top_model)
        if relevant:
            precs.append(len(set(top_model) & relevant) / k)
            recs_.append(len(set(top_model) & relevant) / len(relevant))
            precs_b.append(len(set(top_pop) & relevant) / k)
            recs_b.append(len(set(top_pop) & relevant) / len(relevant))
        # accessibility: what an unfiltered popularity list would have shown
        unfiltered = sorted([int(r["id"]) for r in records if int(r["id"]) not in seen], key=lambda c: -pop_score.get(c, 0))[:k]
        by_id = {int(r["id"]): r for r in records}
        viol_pop += sum(1 for c in unfiltered if violates_needs(by_id[c], needs))
        viol_model += sum(1 for c in top_model if violates_needs(by_id[c], needs))

    m = lambda xs: round(float(np.mean(xs)), 4) if xs else 0.0
    n_lists = max(1, len(eligible) * k)
    return {
        "students_evaluated": len(eligible),
        "k": k,
        "rmse_hybrid_cf": round(float(np.sqrt(np.mean(se_model))), 4),
        "rmse_user_mean_baseline": round(float(np.sqrt(np.mean(se_base))), 4),
        f"precision_at_{k}_cf": m(precs),
        f"recall_at_{k}_cf": m(recs_),
        f"precision_at_{k}_popularity": m(precs_b),
        f"recall_at_{k}_popularity": m(recs_b),
        "catalog_coverage": round(len(recommended) / len(items), 4),
        "accessibility_violation_rate_recommender": round(viol_model / n_lists, 4),
        "accessibility_violation_rate_unfiltered_popularity": round(viol_pop / n_lists, 4),
    }

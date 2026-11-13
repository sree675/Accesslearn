import os
import tempfile
import unittest
from unittest.mock import patch

from backend.app import db, security, services
from backend.app.engine import violates_needs
from backend.app.seed import seed_if_empty


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.tmp.close()
        cls.conn = db.connect(cls.tmp.name)
        db.init_db(cls.conn)
        seed_if_empty(cls.conn, n_synthetic=30)
        services.reset_engine()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        os.unlink(cls.tmp.name)

    def test_password_and_token(self):
        h = security.hash_password("secret1")
        self.assertTrue(security.verify_password("secret1", h))
        self.assertFalse(security.verify_password("wrong", h))
        tok = security.create_token(5, "student")
        self.assertEqual(security.decode_token(tok)["sub"], "5")

    def test_catalog_size(self):
        self.assertGreaterEqual(services.list_content(self.conn, limit=1)["total"], 100)

    def test_register_and_login(self):
        out = services.register_user(self.conn, "Test User", "t@example.com", "abcdef")
        self.assertIn("token", out)
        self.assertEqual(services.authenticate(self.conn, "t@example.com", "abcdef")["user"]["role"], "student")
        with self.assertRaises(services.ServiceError):
            services.authenticate(self.conn, "t@example.com", "nope")

    def test_admin_password_from_environment(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            conn = db.connect(tmp.name)
            db.init_db(conn)
            with patch.dict(os.environ, {"ADMIN_PASSWORD": "deployment-pass"}):
                seed_if_empty(conn, n_synthetic=0)
            admin = services.authenticate(conn, "admin@accesslearn.com", "deployment-pass")
            self.assertEqual(admin["user"]["role"], "admin")
            with self.assertRaises(services.ServiceError):
                services.authenticate(conn, "admin@accesslearn.com", "admin123")
        finally:
            conn.close()
            os.unlink(tmp.name)

    def test_recommendations_respect_hard_needs(self):
        from backend.app.profile import save_profile
        uid = services.register_user(self.conn, "Blind Student", "b@example.com", "abcdef")["user"]["id"]
        needs = {"audio_description": True, "screen_reader": True}
        save_profile(self.conn, uid, dict(disabilities=["Visual impairment"], subjects=["Science"],
                                          preferred_formats=["audio"], level=2, needs=needs))
        res = services.recommendations(self.conn, uid, k=10)
        self.assertTrue(res["cold_start"])
        self.assertEqual(len(res["items"]), 10)
        for it in res["items"]:
            full = services.get_content(self.conn, it["id"])
            self.assertFalse(violates_needs(full, needs), it["title"])
            self.assertTrue(it["reasons"])

    def test_deaf_student_never_gets_audio_only(self):
        from backend.app.profile import save_profile
        uid = services.register_user(self.conn, "Deaf Student", "d@example.com", "abcdef")["user"]["id"]
        save_profile(self.conn, uid, dict(disabilities=["Hearing impairment"], subjects=["Maths"], level=1, needs={"captions": True}))
        fmts = {i["format"] for i in services.recommendations(self.conn, uid, k=30)["items"]}
        self.assertNotIn("audio", fmts)

    def test_feedback_changes_recommendations(self):
        uid = services.authenticate(self.conn, "student@accesslearn.com", "student123")["user"]["id"]
        before = services.recommendations(self.conn, uid, k=10)
        target = before["items"][0]["id"]
        services.submit_feedback(self.conn, uid, target, rating=1)
        after = services.recommendations(self.conn, uid, k=10)
        self.assertNotIn(target, [i["id"] for i in after["items"]])
        services.submit_feedback(self.conn, uid, before["items"][1]["id"], accessibility_issue=True)
        again = services.recommendations(self.conn, uid, k=10)
        self.assertNotIn(before["items"][1]["id"], [i["id"] for i in again["items"]])
        self.assertFalse(again["cold_start"])

    def test_quiz_and_adaptive_level(self):
        uid = services.register_user(self.conn, "Quiz Kid", "q@example.com", "abcdef")["user"]["id"]
        quiz = services.get_quiz(self.conn, "Fractions")
        self.assertEqual(len(quiz["questions"]), 2)
        res = services.submit_quiz(self.conn, uid, "Fractions", {"1": 1, "2": 2})
        self.assertEqual(res["score"], 2)
        self.assertEqual(res["level_target"], 1.5)
        path = services.learning_path(self.conn, uid, "Maths")
        self.assertEqual(path["steps"][0]["status"], "done")
        self.assertEqual(path["steps"][1]["status"], "next")

    def test_notes_bookmarks_analytics(self):
        uid = services.authenticate(self.conn, "student@accesslearn.com", "student123")["user"]["id"]
        services.add_note(self.conn, uid, 1, "Remember this")
        self.assertEqual(len(services.list_notes(self.conn, uid)), 1)
        self.assertTrue(services.toggle_bookmark(self.conn, uid, 1)["bookmarked"])
        self.assertEqual(len(services.list_bookmarks(self.conn, uid)), 1)
        services.record_interaction(self.conn, uid, 1, "complete", 300)
        self.assertGreaterEqual(services.student_analytics(self.conn, uid)["completed"], 1)
        self.assertGreater(services.admin_analytics(self.conn)["students"], 10)

    def test_admin_crud_and_bulk(self):
        item = services.create_content(self.conn, dict(title="X", subject="Maths", topic="Fractions", format="video", difficulty=2, has_captions=1))
        self.assertEqual(services.update_content(self.conn, item["id"], {"title": "Y"})["title"], "Y")
        services.delete_content(self.conn, item["id"])
        out = services.bulk_create_content(self.conn, [dict(title="A", subject="Maths", topic="Fractions", format="text"), dict(title="B")])
        self.assertEqual(out["created"], 1)
        self.assertEqual(len(out["errors"]), 1)

    def test_evaluation(self):
        res = services.evaluation(self.conn, k=10)
        self.assertGreater(res["students_evaluated"], 10)
        self.assertEqual(res["accessibility_violation_rate_recommender"], 0.0)
        self.assertLess(res["rmse_hybrid_cf"], 2.0)


if __name__ == "__main__":
    unittest.main()

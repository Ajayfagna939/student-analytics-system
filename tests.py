"""Basic automated tests.  Run: python tests.py   (uses the current database.db, cleans up after itself)"""
import io, json, os, unittest
import pandas as pd
from app import app, compute_stats, UPLOAD_DIR
from interview_analysis import analyze, detect_skills
from common import *

GOOD = {"roll_no": "TEST001", "name": "Test User", "gender": "Male", "course": "BCA", "batch": "2026",
        "tenth_pct": "80", "twelfth_pct": "75", "degree_pct": "70", "attendance": "85", "backlogs": "0",
        "projects": "2", "skills": "Python, SQL, python", "certs": "AWS", "intern_company": "Acme",
        "intern_months": "3", "status": "Placed", "company": "TCS", "package_lpa": "6"}


class T(unittest.TestCase):
    def setUp(self):
        self.c = app.test_client(); self._clean()

    def tearDown(self):
        self._clean()

    def _clean(self):
        conn = get_conn(); conn.execute("DELETE FROM students WHERE roll_no='TEST001'"); conn.commit(); conn.close()

    def sid(self):
        conn = get_conn(); r = conn.execute("SELECT id FROM students WHERE roll_no='TEST001'").fetchone(); conn.close()
        return r[0] if r else None

    def test_pages_load(self):
        for u in ["/", "/students", "/students/add", "/predict", "/report", "/export.csv", "/api/stats", "/interviews"]:
            self.assertEqual(self.c.get(u).status_code, 200, u)

    def test_input_validation(self):
        r = self.c.post("/students/add", data={"roll_no": "TEST001", "name": "", "batch": "abc"})
        self.assertIn(b"required", r.data); self.assertIsNone(self.sid())
        bad = dict(GOOD, degree_pct="140")
        self.assertIn(b"between 0 and 100", self.c.post("/students/add", data=bad).data)

    def test_crud(self):
        self.c.post("/students/add", data=GOOD); sid = self.sid(); self.assertIsNotNone(sid)
        conn = get_conn()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM skills WHERE student_id=?", (sid,)).fetchone()[0], 2)  # de-duplicated
        conn.close()
        self.assertIn(b"already exists", self.c.post("/students/add", data=GOOD).data)
        self.c.post(f"/students/{sid}/edit", data=dict(GOOD, degree_pct="72"))
        conn = get_conn(); self.assertEqual(conn.execute("SELECT degree_pct FROM students WHERE id=?", (sid,)).fetchone()[0], 72.0); conn.close()
        self.c.post(f"/students/{sid}/delete")
        conn = get_conn(); self.assertEqual(conn.execute("SELECT COUNT(*) FROM skills WHERE student_id=?", (sid,)).fetchone()[0], 0); conn.close()

    def test_search_and_filter(self):
        self.c.post("/students/add", data=GOOD)
        self.assertIn(b"Test User", self.c.get("/students?q=TEST001").data)
        self.assertNotIn(b"Test User", self.c.get("/students?q=TEST001&status=Not+Placed").data)

    def test_analytics_matches_manual(self):
        conn = get_conn(); df = load_df(conn); conn.close()
        s = compute_stats()
        self.assertEqual(s["total"], len(df)); self.assertEqual(s["placed"], int(df.placed.sum()))
        self.assertAlmostEqual(s["rate"], round(100 * df.placed.mean(), 1), places=1)

    def test_prediction(self):
        p = {"tenth_pct": 75, "twelfth_pct": 72, "degree_pct": 70, "attendance": 80, "backlogs": 0,
             "projects": 2, "n_skills": 5, "n_certs": 2, "has_internship": 1}
        self.assertIn(b"Estimated placement", self.c.post("/predict", data=p).data)
        self.assertIn(b"between 0 and 100", self.c.post("/predict", data=dict(p, attendance=150)).data)

    # ---------------- video interview module
    TEXT = ("My name is Test and I am studying BCA. I built a project called placement analytics using Python Flask and SQL. "
            "I also know Machine Learning and Power BI. I completed a Coursera certification. My goal is to become a data analyst.")

    def test_interview_analysis(self):
        self.assertEqual(set(detect_skills("I use Python, SQL and Java but not javascript")), {"Python", "SQL", "Java", "JavaScript"})
        r = analyze([{"question": "q", "text": self.TEXT, "duration": 40}], True, ["Python"])
        self.assertGreater(r["auto_score"], 0); self.assertIn("SQL", r["insights"]["new_skills"])
        self.assertNotIn("Python", r["insights"]["new_skills"]); self.assertTrue(r["insights"]["goals"])
        self.assertEqual(analyze([{"question": "q", "text": "", "duration": 10}], True, [])["auto_score"], 0)
        typed = analyze([{"question": "q", "text": self.TEXT, "duration": 40}], False, [])   # no speech -> pace skipped
        self.assertIsNone(typed["pace_score"])

    def test_interview_flow(self):
        self.c.post("/students/add", data=GOOD); sid = self.sid()
        self.assertEqual(self.c.get(f"/students/{sid}/interview").status_code, 200)
        payload = {"answers": json.dumps([{"question": "Q1", "text": self.TEXT, "duration": 45}]), "speech": "true"}
        mk = lambda **k: dict(payload, video=(io.BytesIO(b"fakevideo"), "i.webm"), **k)
        self.assertEqual(self.c.post(f"/students/{sid}/interview/submit", data=mk(), content_type="multipart/form-data").status_code, 400)
        r = self.c.post(f"/students/{sid}/interview/submit", data=mk(consent="yes"), content_type="multipart/form-data")
        self.assertTrue(r.json["ok"]); url = r.json["redirect"]; iid = int(url.rstrip("/").split("/")[-1])
        self.assertEqual(self.c.get(url).status_code, 200)
        self.assertEqual(self.c.get(f"/interviews/{iid}/video").data, b"fakevideo")
        self.assertIn(b"Add these skills", self.c.get(url).data)
        self.c.post(f"/interviews/{iid}/review", data={"fac_comm": 4, "fac_tech": 3, "fac_conf": 5, "fac_overall": 4, "fac_comments": "good"})
        conn = get_conn(); self.assertEqual(conn.execute("SELECT fac_overall FROM interviews WHERE id=?", (iid,)).fetchone()[0], 4); conn.close()
        self.c.post(f"/interviews/{iid}/add-skills")
        conn = get_conn(); n = conn.execute("SELECT COUNT(*) FROM skills WHERE student_id=? AND skill_name='Machine Learning'", (sid,)).fetchone()[0]; conn.close()
        self.assertEqual(n, 1)
        self.assertGreaterEqual(compute_stats()["interview"]["n"], 1)
        self.c.post(f"/students/{sid}/delete")                    # deleting student removes interview + video file
        self.assertFalse(os.path.exists(os.path.join(UPLOAD_DIR, f"interview_{iid}.webm")))
        conn = get_conn(); self.assertEqual(conn.execute("SELECT COUNT(*) FROM interviews WHERE id=?", (iid,)).fetchone()[0], 0); conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

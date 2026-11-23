"""Shared config, DB helpers and data loading for the project."""
import os, sqlite3
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "database.db")
CSV_PATH = os.path.join(BASE, "data", "students.csv")
MODEL_PATH = os.path.join(BASE, "models", "model.pkl")
METRICS_PATH = os.path.join(BASE, "models", "metrics.json")
LR_PARAMS_PATH = os.path.join(BASE, "models", "lr_params.json")

FEATURES = ["tenth_pct", "twelfth_pct", "degree_pct", "attendance",
            "backlogs", "projects", "n_skills", "n_certs", "has_internship"]
FEATURE_LABELS = {
    "tenth_pct": "10th %", "twelfth_pct": "12th %", "degree_pct": "Degree %",
    "attendance": "Attendance %", "backlogs": "Backlogs", "projects": "Projects",
    "n_skills": "No. of skills", "n_certs": "No. of certifications",
    "has_internship": "Internship done",
}

SKILL_CATEGORY = {
    "python": "Programming", "java": "Programming", "c++": "Programming", "sql": "Data / AI",
    "javascript": "Web", "html/css": "Web", "react": "Web", "flask": "Web",
    "machine learning": "Data / AI", "data analysis": "Data / AI", "power bi": "Data / AI",
    "excel": "Tools", "git": "Tools", "aws": "Tools",
    "communication": "Soft Skills", "aptitude": "Soft Skills",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS students(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  roll_no TEXT UNIQUE NOT NULL, name TEXT NOT NULL, gender TEXT,
  course TEXT NOT NULL, batch INTEGER NOT NULL,
  tenth_pct REAL, twelfth_pct REAL, degree_pct REAL,
  attendance REAL, backlogs INTEGER DEFAULT 0, projects INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS skills(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  skill_name TEXT NOT NULL, category TEXT);
CREATE TABLE IF NOT EXISTS certifications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  cert_name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS internships(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  company TEXT NOT NULL, duration_months INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS interviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, video_file TEXT, duration_sec REAL DEFAULT 0, speech_used INTEGER DEFAULT 0,
  word_count INTEGER, wpm REAL, filler_count INTEGER,
  fluency_score REAL, pace_score REAL, content_score REAL, vocab_score REAL, technical_score REAL, auto_score REAL,
  insights TEXT,
  fac_comm INTEGER, fac_tech INTEGER, fac_conf INTEGER, fac_overall INTEGER, fac_comments TEXT);
CREATE TABLE IF NOT EXISTS interview_answers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interview_id INTEGER NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
  q_no INTEGER, question TEXT, answer_text TEXT, duration_sec REAL);
CREATE TABLE IF NOT EXISTS placements(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  student_id INTEGER UNIQUE NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  status TEXT NOT NULL, company TEXT, package_lpa REAL DEFAULT 0);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def save_student(conn, sid, rec):
    """Insert (sid=None) or update a student with all related rows. rec has typed values."""
    cols = ("roll_no", "name", "gender", "course", "batch", "tenth_pct", "twelfth_pct",
            "degree_pct", "attendance", "backlogs", "projects")
    vals = [rec[c] for c in cols]
    if sid is None:
        cur = conn.execute(
            f"INSERT INTO students({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)
        sid = cur.lastrowid
    else:
        conn.execute(f"UPDATE students SET {','.join(c + '=?' for c in cols)} WHERE id=?", vals + [sid])
        for t in ("skills", "certifications", "internships", "placements"):
            conn.execute(f"DELETE FROM {t} WHERE student_id=?", (sid,))
    for s in rec["skills"]:
        conn.execute("INSERT INTO skills(student_id,skill_name,category) VALUES(?,?,?)",
                     (sid, s, SKILL_CATEGORY.get(s.lower(), "Other")))
    for c in rec["certs"]:
        conn.execute("INSERT INTO certifications(student_id,cert_name) VALUES(?,?)", (sid, c))
    if rec["intern_company"]:
        conn.execute("INSERT INTO internships(student_id,company,duration_months) VALUES(?,?,?)",
                     (sid, rec["intern_company"], rec["intern_months"] or 0))
    conn.execute("INSERT INTO placements(student_id,status,company,package_lpa) VALUES(?,?,?,?)",
                 (sid, rec["status"], rec["company"] if rec["status"] == "Placed" else None,
                  rec["package_lpa"] if rec["status"] == "Placed" else 0))
    conn.commit()
    return sid


BASE_QUERY = """
SELECT s.*,
  (SELECT COUNT(*) FROM skills k WHERE k.student_id=s.id) AS n_skills,
  (SELECT COUNT(*) FROM certifications c WHERE c.student_id=s.id) AS n_certs,
  (SELECT COUNT(*) FROM internships i WHERE i.student_id=s.id) AS n_interns,
  COALESCE(p.status,'Not Placed') AS placement_status, p.company AS placed_company,
  COALESCE(p.package_lpa,0) AS package_lpa
FROM students s LEFT JOIN placements p ON p.student_id=s.id
"""


def load_df(conn, course=None, batch=None):
    where, params = [], []
    if course:
        where.append("s.course=?"); params.append(course)
    if batch:
        where.append("s.batch=?"); params.append(int(batch))
    sql = BASE_QUERY + (" WHERE " + " AND ".join(where) if where else "")
    df = pd.read_sql_query(sql, conn, params=params)
    df["has_internship"] = (df["n_interns"] > 0).astype(int)
    df["placed"] = (df["placement_status"] == "Placed").astype(int)
    return df

"""Optional: add ~40 DEMO interview records (text only, no video) so the dashboard interview charts have data.
Transcripts are generated from templates - they are NOT real interviews.  Usage: python seed_demo_interviews.py"""
import json, random
from datetime import datetime, timedelta
from common import *
from interview_analysis import QUESTIONS, analyze

random.seed(7)
conn = get_conn(); init_schema(conn)
students = conn.execute("SELECT id,name,course FROM students WHERE id NOT IN (SELECT student_id FROM interviews)").fetchall()
ROLES = ["data analyst", "software developer", "machine learning engineer", "web developer"]
count = 0
for s in random.sample(students, min(40, len(students))):
    sk = [r[0] for r in conn.execute("SELECT skill_name FROM skills WHERE student_id=?", (s["id"],))]
    random.shuffle(sk)
    level = random.choice(["low", "mid", "mid", "high"])          # answer quality, independent of placement
    k = {"low": 1, "mid": 3, "high": 5}[level]
    use = ", ".join(sk[:k]) or "basic programming"
    longer = {"low": "", "mid": " I enjoy learning new tools and working in a team.",
              "high": " I enjoy learning new tools, working in a team and explaining my work clearly to others. I regularly practise on online platforms and try to improve every week."}[level]
    texts = [
        f"My name is {s['name']} and I am studying {s['course']}.{longer}",
        f"I built a project for managing student data using {use}. I was responsible for the database and the user interface." + (longer if level != "low" else ""),
        f"My strongest skills are {use}. I have used them in my college project and assignments." + longer,
        "One challenge was fixing errors in my project before the deadline. I read the documentation and asked my teacher for help." + (longer if level == "high" else ""),
        f"My goal is to become a {random.choice(ROLES)}. I completed an online course and I want to grow my career in this field." + (longer if level != "low" else ""),
    ]
    answers = []
    wps = random.uniform(1.6, 3.2)                                  # words per second
    for q, t in zip(QUESTIONS, texts):
        answers.append({"question": q, "text": t, "duration": round(len(t.split()) / wps + random.uniform(4, 12), 1)})
    r = analyze(answers, True, sk)
    cur = conn.execute(
        "INSERT INTO interviews(student_id,created_at,duration_sec,speech_used,word_count,wpm,filler_count,fluency_score,pace_score,"
        "content_score,vocab_score,technical_score,auto_score,insights) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (s["id"], (datetime.now() - timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d %H:%M"),
         sum(a["duration"] for a in answers), 1, r["word_count"], r["wpm"], r["filler_count"], r["fluency_score"],
         r["pace_score"], r["content_score"], r["vocab_score"], r["technical_score"], r["auto_score"], json.dumps(r["insights"])))
    for n, a in enumerate(answers, 1):
        conn.execute("INSERT INTO interview_answers(interview_id,q_no,question,answer_text,duration_sec) VALUES(?,?,?,?,?)",
                     (cur.lastrowid, n, a["question"], a["text"], a["duration"]))
    count += 1
conn.commit(); conn.close()
print(f"Added {count} demo interview records (no video).")

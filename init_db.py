"""Create database.db and load data/students.csv.  Usage: python init_db.py"""
import csv, os
from common import *

def clean_list(s):
    return [x.strip() for x in (s or "").split(";") if x.strip()]

import glob
for f in glob.glob(os.path.join(BASE, 'uploads', 'interview_*')):
    os.remove(f)
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
conn = get_conn(); init_schema(conn)
with open(CSV_PATH, encoding="utf-8") as f:
    n = 0
    for r in csv.DictReader(f):
        rec = dict(roll_no=r["roll_no"], name=r["name"], gender=r["gender"], course=r["course"],
                   batch=int(r["batch"]), tenth_pct=float(r["tenth_pct"]), twelfth_pct=float(r["twelfth_pct"]),
                   degree_pct=float(r["degree_pct"]), attendance=float(r["attendance"]),
                   backlogs=int(r["backlogs"]), projects=int(r["projects"]),
                   skills=clean_list(r["skills"]), certs=clean_list(r["certifications"]),
                   intern_company=r["internship_company"], intern_months=int(r["internship_months"] or 0),
                   status=r["placement_status"], company=r["company"], package_lpa=float(r["package_lpa"] or 0))
        save_student(conn, None, rec); n += 1
conn.close()
print(f"Database ready: {n} students loaded -> database.db")

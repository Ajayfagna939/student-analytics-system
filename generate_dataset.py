"""Generate a SYNTHETIC student dataset -> data/students.csv
Usage: python generate_dataset.py [num_students]
The data is artificial (no real students). Placement is generated from a noisy
scoring rule so that a model has realistic, but not perfect, signal to learn."""
import csv, os, random, sys
import numpy as np

random.seed(42); np.random.seed(42)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300

FIRST = ["Aarav","Vivaan","Aditya","Arjun","Rohan","Karan","Rahul","Amit","Sahil","Nikhil","Priya","Ananya",
         "Neha","Pooja","Riya","Simran","Kavya","Isha","Sneha","Anjali","Mohit","Deepak","Manish","Ritu","Komal"]
LAST = ["Sharma","Verma","Gupta","Singh","Yadav","Chauhan","Mehta","Jain","Kumar","Malik","Tiwari","Saini","Rana","Bansal"]
COURSES = ["BCA", "BCA (AI & ML)", "B.Sc IT", "B.Tech CSE", "MCA"]
BATCHES = [2023, 2024, 2025, 2026]
SKILLS = ["Python","Java","C++","SQL","JavaScript","HTML/CSS","React","Flask","Machine Learning",
          "Data Analysis","Power BI","Excel","Git","AWS","Communication","Aptitude"]
CERTS = ["Python for Everybody (Coursera)","SQL Basics (HackerRank)","Power BI Essentials (Microsoft)",
         "Machine Learning (Coursera)","Java Programming (NPTEL)","Web Development (Udemy)",
         "AWS Cloud Practitioner","Data Analytics (Google)","Git & GitHub (Simplilearn)"]
INTERN_CO = ["TechNova Solutions","DataWorks","CloudNest","CodeCraft Labs","InfoBridge","PixelSoft"]
HIRE_CO = ["TCS","Infosys","Wipro","Cognizant","Capgemini","Accenture","HCL","Tech Mahindra","Deloitte","Zoho"]

rows = []
for i in range(N):
    batch = random.choice(BATCHES); course = random.choice(COURSES)
    degree = float(np.clip(np.random.normal(70, 10), 40, 98))
    tenth = float(np.clip(np.random.normal(74, 10), 45, 99))
    twelfth = float(np.clip(np.random.normal(72, 10), 45, 99))
    attendance = float(np.clip(np.random.normal(80, 10), 45, 100))
    backlogs = int(np.random.choice([0, 0, 0, 1, 2, 3], p=[.5, .15, .1, .12, .08, .05]))
    projects = int(np.random.choice([0, 1, 2, 3, 4], p=[.1, .3, .3, .2, .1]))
    skills = random.sample(SKILLS, random.randint(2, 9))
    certs = random.sample(CERTS, random.choices([0, 1, 2, 3, 4], [.2, .3, .25, .15, .1])[0])
    has_int = random.random() < 0.5
    months = random.choice([1, 2, 3, 6]) if has_int else 0
    z = (0.08*(degree-65) + 0.02*(attendance-80) + 0.35*(len(skills)-5) + 0.4*len(certs)
         + 0.9*has_int + 0.3*projects - 0.8*backlogs + np.random.normal(0, 1.2))
    rows.append(dict(i=i, batch=batch, course=course, degree=degree, tenth=tenth, twelfth=twelfth,
                     attendance=attendance, backlogs=backlogs, projects=projects, skills=skills,
                     certs=certs, has_int=has_int, months=months, z=z))

cut = np.quantile([r["z"] for r in rows], 0.35)   # ~65% placed
os.makedirs("data", exist_ok=True)
with open("data/students.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["roll_no","name","gender","course","batch","tenth_pct","twelfth_pct","degree_pct","attendance",
                "backlogs","projects","skills","certifications","internship_company","internship_months",
                "placement_status","company","package_lpa"])
    for r in rows:
        fn = random.choice(FIRST); ln = random.choice(LAST)
        gender = "Female" if fn in {"Priya","Ananya","Neha","Pooja","Riya","Simran","Kavya","Isha","Sneha","Anjali","Ritu","Komal"} else "Male"
        placed = r["z"] >= cut
        pkg = round(float(np.clip(3 + 0.08*(r["degree"]-60) + 0.3*len(r["certs"]) + np.random.normal(0, 1.2), 2.5, 18)), 1) if placed else 0
        w.writerow([f"MVN{r['batch']}{r['i']+1:03d}", f"{fn} {ln}", gender, r["course"], r["batch"],
                    round(r["tenth"], 1), round(r["twelfth"], 1), round(r["degree"], 1), round(r["attendance"], 1),
                    r["backlogs"], r["projects"], ";".join(r["skills"]), ";".join(r["certs"]),
                    random.choice(INTERN_CO) if r["has_int"] else "", r["months"],
                    "Placed" if placed else "Not Placed", random.choice(HIRE_CO) if placed else "", pkg])
print(f"Generated {N} synthetic records -> data/students.csv")

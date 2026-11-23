"""Student Performance, Placement & Career Analytics System - Flask app."""
import io, json, os
from datetime import datetime
import pandas as pd
from interview_analysis import QUESTIONS, analyze
from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from common import *

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
PER_PAGE = 15

UPLOAD_DIR = os.path.join(BASE, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024   # interview videos
_c = get_conn(); init_schema(_c); _c.close()          # creates missing tables, keeps existing data


def split_list(s):
    seen, out = set(), []
    for x in (s or "").replace(";", ",").split(","):
        x = x.strip()
        if x and x.lower() not in seen:
            seen.add(x.lower()); out.append(x)
    return out


def filter_options(conn):
    courses = [r[0] for r in conn.execute("SELECT DISTINCT course FROM students ORDER BY course")]
    batches = [r[0] for r in conn.execute("SELECT DISTINCT batch FROM students ORDER BY batch")]
    return courses, batches


# ---------------------------------------------------------------- validation
FIELDS = ["roll_no", "name", "gender", "course", "batch", "tenth_pct", "twelfth_pct", "degree_pct",
          "attendance", "backlogs", "projects", "skills", "certs", "intern_company", "intern_months",
          "status", "company", "package_lpa"]


def parse_form(form):
    v = {f: (form.get(f) or "").strip() for f in FIELDS}
    errs, rec = [], {}

    def num(f, label, lo, hi, integer=False):
        if v[f] == "":
            errs.append(f"{label} is required."); return None
        try:
            x = int(v[f]) if integer else float(v[f])
        except ValueError:
            errs.append(f"{label} must be a {'whole ' if integer else ''}number."); return None
        if not lo <= x <= hi:
            errs.append(f"{label} must be between {lo} and {hi}."); return None
        return x

    for f, label in [("roll_no", "Roll number"), ("name", "Name"), ("course", "Course")]:
        if not v[f]:
            errs.append(f"{label} is required.")
    rec.update(roll_no=v["roll_no"], name=v["name"], gender=v["gender"] or "Other", course=v["course"])
    rec["batch"] = num("batch", "Batch year", 2000, 2100, True)
    rec["tenth_pct"] = num("tenth_pct", "10th %", 0, 100)
    rec["twelfth_pct"] = num("twelfth_pct", "12th %", 0, 100)
    rec["degree_pct"] = num("degree_pct", "Degree %", 0, 100)
    rec["attendance"] = num("attendance", "Attendance %", 0, 100)
    rec["backlogs"] = num("backlogs", "Backlogs", 0, 50, True)
    rec["projects"] = num("projects", "Projects", 0, 50, True)
    rec["skills"], rec["certs"] = split_list(v["skills"]), split_list(v["certs"])
    rec["intern_company"] = v["intern_company"]
    rec["intern_months"] = 0
    if v["intern_company"]:
        rec["intern_months"] = num("intern_months", "Internship duration (months)", 0, 36, True) or 0
    rec["status"] = v["status"] if v["status"] in ("Placed", "Not Placed") else "Not Placed"
    rec["company"], rec["package_lpa"] = v["company"], 0.0
    if rec["status"] == "Placed":
        if not v["company"]:
            errs.append("Company is required when status is Placed.")
        if v["package_lpa"]:
            try:
                rec["package_lpa"] = float(v["package_lpa"])
                if not 0 <= rec["package_lpa"] <= 200:
                    errs.append("Package must be between 0 and 200 LPA.")
            except ValueError:
                errs.append("Package must be a number.")
    return v, rec, errs


def get_student(conn, sid):
    s = conn.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    if not s:
        return None
    d = dict(s)
    d["skills_list"] = [dict(r) for r in conn.execute("SELECT skill_name,category FROM skills WHERE student_id=?", (sid,))]
    d["certs_list"] = [r[0] for r in conn.execute("SELECT cert_name FROM certifications WHERE student_id=?", (sid,))]
    i = conn.execute("SELECT company,duration_months FROM internships WHERE student_id=?", (sid,)).fetchone()
    d["internship"] = dict(i) if i else None
    p = conn.execute("SELECT status,company,package_lpa FROM placements WHERE student_id=?", (sid,)).fetchone()
    d["placement"] = dict(p) if p else {"status": "Not Placed", "company": None, "package_lpa": 0}
    d["interviews"] = [dict(r) for r in conn.execute(
        "SELECT id,created_at,auto_score,fac_overall FROM interviews WHERE student_id=? ORDER BY id DESC", (sid,))]
    return d


def form_values(d):
    return {"roll_no": d["roll_no"], "name": d["name"], "gender": d["gender"], "course": d["course"],
            "batch": d["batch"], "tenth_pct": d["tenth_pct"], "twelfth_pct": d["twelfth_pct"],
            "degree_pct": d["degree_pct"], "attendance": d["attendance"], "backlogs": d["backlogs"],
            "projects": d["projects"], "skills": ", ".join(x["skill_name"] for x in d["skills_list"]),
            "certs": ", ".join(d["certs_list"]),
            "intern_company": d["internship"]["company"] if d["internship"] else "",
            "intern_months": d["internship"]["duration_months"] if d["internship"] else "",
            "status": d["placement"]["status"], "company": d["placement"]["company"] or "",
            "package_lpa": d["placement"]["package_lpa"] or ""}


# ---------------------------------------------------------------- analytics
def compute_stats(course=None, batch=None):
    conn = get_conn()
    df = load_df(conn, course, batch)
    if df.empty:
        conn.close(); return {"empty": True}
    sk = pd.read_sql_query("SELECT student_id, skill_name FROM skills", conn)
    iv = pd.read_sql_query("SELECT student_id, AVG(auto_score) AS score FROM interviews GROUP BY student_id", conn)
    conn.close()
    total, placed = len(df), int(df["placed"].sum())
    pk = df.loc[df["placed"] == 1, "package_lpa"]
    out = {"empty": False, "total": total, "placed": placed,
           "rate": round(100 * placed / total, 1),
           "avg_marks": round(float(df["degree_pct"].mean()), 1),
           "avg_package": round(float(pk.mean()), 2) if len(pk) else 0,
           "max_package": round(float(pk.max()), 1) if len(pk) else 0,
           "avg_attendance": round(float(df["attendance"].mean()), 1)}
    g = df.groupby("course").agg(total=("id", "count"), placed=("placed", "sum"), marks=("degree_pct", "mean"))
    out["course"] = {"labels": g.index.tolist(),
                     "rate": [round(100 * a / b, 1) for a, b in zip(g["placed"], g["total"])],
                     "marks": [round(float(x), 1) for x in g["marks"]]}
    b = df.groupby("batch").agg(total=("id", "count"), placed=("placed", "sum"))
    out["batch"] = {"labels": [str(x) for x in b.index], "rate": [round(100 * a / t, 1) for a, t in zip(b["placed"], b["total"])]}
    df["band"] = pd.cut(df["degree_pct"], [0, 50, 60, 70, 80, 101], labels=["<50", "50-60", "60-70", "70-80", "80+"], right=False)
    mb = df.groupby("band", observed=True)["placed"].mean() * 100
    out["marks_band"] = {"labels": [str(x) for x in mb.index], "rate": [round(float(x), 1) for x in mb]}
    ib = df.groupby("has_internship")["placed"].mean() * 100
    out["internship"] = {"labels": ["No internship" if i == 0 else "Internship done" for i in ib.index],
                         "rate": [round(float(x), 1) for x in ib]}
    m = sk[sk["student_id"].isin(df["id"])].merge(df[["id", "placed"]], left_on="student_id", right_on="id")
    if not m.empty:
        s = m.groupby("skill_name").agg(n=("placed", "size"), rate=("placed", "mean")).sort_values("n", ascending=False).head(10)
        out["skills"] = {"labels": s.index.tolist(), "count": s["n"].astype(int).tolist(),
                         "rate": [round(float(x) * 100, 1) for x in s["rate"]]}
    else:
        out["skills"] = {"labels": [], "count": [], "rate": []}
    mi = iv[iv["student_id"].isin(df["id"])].merge(df[["id", "placed"]], left_on="student_id", right_on="id")
    out["interview"] = {"n": 0, "avg": 0, "labels": [], "rate": [], "count": []}
    if not mi.empty:
        mi["band"] = pd.cut(mi["score"], [0, 40, 60, 80, 101], labels=["<40", "40-60", "60-80", "80+"], right=False)
        gb = mi.groupby("band", observed=True).agg(n=("placed", "size"), rate=("placed", "mean"))
        out["interview"] = {"n": int(len(mi)), "avg": round(float(mi["score"].mean()), 1),
                            "labels": [str(x) for x in gb.index], "rate": [round(float(x) * 100, 1) for x in gb["rate"]],
                            "count": gb["n"].astype(int).tolist()}
    return out


# ---------------------------------------------------------------- routes
@app.route("/")
def dashboard():
    conn = get_conn(); courses, batches = filter_options(conn); conn.close()
    return render_template("dashboard.html", courses=courses, batches=batches)


@app.route("/api/stats")
def api_stats():
    return jsonify(compute_stats(request.args.get("course") or None, request.args.get("batch") or None))


@app.route("/students")
def students():
    q = request.args.get("q", "").strip()
    course = request.args.get("course", ""); batch = request.args.get("batch", "")
    status = request.args.get("status", ""); skill = request.args.get("skill", "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    where, params = [], []
    if q:
        where.append("(s.name LIKE ? OR s.roll_no LIKE ?)"); params += [f"%{q}%"] * 2
    if course:
        where.append("s.course=?"); params.append(course)
    if batch:
        where.append("s.batch=?"); params.append(batch)
    if status:
        where.append("COALESCE(p.status,'Not Placed')=?"); params.append(status)
    if skill:
        where.append("EXISTS(SELECT 1 FROM skills k WHERE k.student_id=s.id AND k.skill_name LIKE ?)"); params.append(f"%{skill}%")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    base = f"FROM students s LEFT JOIN placements p ON p.student_id=s.id{w}"
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT s.*, COALESCE(p.status,'Not Placed') AS status, p.company, p.package_lpa {base} "
        f"ORDER BY s.batch DESC, s.name LIMIT ? OFFSET ?", params + [PER_PAGE, (page - 1) * PER_PAGE]).fetchall()
    courses, batches = filter_options(conn); conn.close()
    pages = max(1, -(-total // PER_PAGE))
    args = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("students.html", rows=rows, total=total, page=page, pages=pages, args=args,
                           courses=courses, batches=batches, f=dict(q=q, course=course, batch=batch, status=status, skill=skill))


@app.route("/students/add", methods=["GET", "POST"])
def add_student():
    conn = get_conn(); courses, _ = filter_options(conn)
    v, errs = {"status": "Not Placed", "gender": "Male"}, []
    if request.method == "POST":
        v, rec, errs = parse_form(request.form)
        if not errs and conn.execute("SELECT 1 FROM students WHERE roll_no=?", (rec["roll_no"],)).fetchone():
            errs.append("A student with this roll number already exists.")
        if not errs:
            sid = save_student(conn, None, rec); conn.close()
            flash("Student added successfully.", "success")
            return redirect(url_for("student_detail", sid=sid))
    conn.close()
    return render_template("student_form.html", v=v, errors=errs, courses=courses, mode="Add", action=url_for("add_student"))


@app.route("/students/<int:sid>")
def student_detail(sid):
    conn = get_conn(); d = get_student(conn, sid); conn.close()
    if not d:
        abort(404)
    return render_template("student_detail.html", s=d)


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
def edit_student(sid):
    conn = get_conn(); d = get_student(conn, sid)
    if not d:
        conn.close(); abort(404)
    courses, _ = filter_options(conn)
    v, errs = form_values(d), []
    if request.method == "POST":
        v, rec, errs = parse_form(request.form)
        if not errs and conn.execute("SELECT 1 FROM students WHERE roll_no=? AND id<>?", (rec["roll_no"], sid)).fetchone():
            errs.append("Another student already uses this roll number.")
        if not errs:
            save_student(conn, sid, rec); conn.close()
            flash("Student updated.", "success")
            return redirect(url_for("student_detail", sid=sid))
    conn.close()
    return render_template("student_form.html", v=v, errors=errs, courses=courses, mode="Edit", action=url_for("edit_student", sid=sid))


@app.route("/students/<int:sid>/delete", methods=["POST"])
def delete_student(sid):
    conn = get_conn()
    remove_video_files(conn, "student_id=?", (sid,))
    conn.execute("DELETE FROM students WHERE id=?", (sid,)); conn.commit(); conn.close()
    flash("Student deleted.", "warning")
    return redirect(url_for("students"))


def estimate_probability(vals):
    """Placement probability. Uses the saved scikit-learn model; if scikit-learn cannot be loaded
    (e.g. blocked by a Windows policy) falls back to saved Logistic Regression weights (numpy only)."""
    try:
        import joblib
        model = joblib.load(MODEL_PATH)
        return float(model.predict_proba(pd.DataFrame([vals], columns=FEATURES))[0][1])
    except Exception:
        if not os.path.exists(LR_PARAMS_PATH):
            raise
        import numpy as np
        with open(LR_PARAMS_PATH) as f:
            w = json.load(f)
        x = (np.array([vals[k] for k in FEATURES]) - np.array(w["mean"])) / np.array(w["scale"])
        z = float(x @ np.array(w["coef"]) + w["intercept"])
        return float(1 / (1 + np.exp(-z)))


def load_metrics():
    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH) as f:
            return json.load(f)
    return None


@app.route("/predict", methods=["GET", "POST"])
def predict():
    metrics = load_metrics(); result, errs, v = None, [], {}
    if request.method == "POST":
        v = {k: (request.form.get(k) or "").strip() for k in FEATURES}
        vals = {}
        for k in FEATURES:
            try:
                x = float(v[k])
            except ValueError:
                errs.append(f"{FEATURE_LABELS[k]} must be a number."); continue
            hi = 100 if k.endswith("_pct") or k == "attendance" else 50
            if not 0 <= x <= hi:
                errs.append(f"{FEATURE_LABELS[k]} must be between 0 and {hi}.")
            vals[k] = x
        if vals.get("has_internship") not in (None, 0.0, 1.0):
            errs.append("Internship must be 0 (No) or 1 (Yes).")
        if not errs:
            if not (os.path.exists(MODEL_PATH) or os.path.exists(LR_PARAMS_PATH)):
                errs.append("Model not trained yet. Click 'Train / Retrain model' first.")
            else:
                p = estimate_probability(vals)
                tips = []
                if vals["n_skills"] < 5: tips.append("Add more in-demand skills (aim for 5+).")
                if vals["n_certs"] < 2: tips.append("Complete 1-2 industry certifications.")
                if vals["has_internship"] == 0: tips.append("Do an internship or live project.")
                if vals["projects"] < 2: tips.append("Build at least 2 portfolio projects.")
                if vals["backlogs"] > 0: tips.append("Clear pending backlogs.")
                if vals["attendance"] < 75: tips.append("Improve attendance.")
                result = {"p": round(100 * p, 1), "band": "High" if p >= .7 else "Medium" if p >= .4 else "Low", "tips": tips}
    return render_template("predict.html", metrics=metrics, result=result, errors=errs, v=v,
                           features=FEATURES, labels=FEATURE_LABELS)


@app.route("/retrain", methods=["POST"])
def retrain():
    try:
        import train_model
        m = train_model.train()
        flash(f"Model trained. Best model: {m['best_model']}.", "success")
    except Exception as e:
        flash(f"Training failed: {e}", "danger")
    return redirect(url_for("predict"))


@app.route("/report")
def report():
    conn = get_conn(); df = load_df(conn); conn.close()
    if df.empty:
        return render_template("report.html", table=[], overall=None)
    g = df.groupby(["course", "batch"]).agg(total=("id", "count"), placed=("placed", "sum"),
                                            marks=("degree_pct", "mean"), att=("attendance", "mean"),
                                            pkg=("package_lpa", lambda s: s[s > 0].mean())).reset_index()
    table = [dict(course=r.course, batch=r.batch, total=int(r.total), placed=int(r.placed),
                  rate=round(100 * r.placed / r.total, 1), marks=round(r.marks, 1), att=round(r.att, 1),
                  pkg=None if pd.isna(r.pkg) else round(r.pkg, 2)) for r in g.itertuples()]
    return render_template("report.html", table=table, overall=compute_stats())


@app.route("/export.csv")
def export_csv():
    conn = get_conn(); df = load_df(conn); conn.close()
    cols = ["roll_no", "name", "course", "batch", "tenth_pct", "twelfth_pct", "degree_pct", "attendance",
            "backlogs", "projects", "n_skills", "n_certs", "n_interns", "placement_status", "placed_company", "package_lpa"]
    buf = io.StringIO(); df[cols].to_csv(buf, index=False)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=student_report.csv"})



# ---------------------------------------------------------------- video interview module
def remove_video_files(conn, where, params):
    for r in conn.execute(f"SELECT video_file FROM interviews WHERE {where}", params).fetchall():
        if r[0]:
            try:
                os.remove(os.path.join(UPLOAD_DIR, r[0]))
            except OSError:
                pass


@app.route("/interviews")
def interviews():
    q = request.args.get("q", "").strip(); course = request.args.get("course", "")
    where, params = [], []
    if q:
        where.append("(s.name LIKE ? OR s.roll_no LIKE ?)"); params += [f"%{q}%"] * 2
    if course:
        where.append("s.course=?"); params.append(course)
    w = (" WHERE " + " AND ".join(where)) if where else ""
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT i.*, s.name, s.roll_no, s.course FROM interviews i JOIN students s ON s.id=i.student_id"
        f"{w} ORDER BY i.id DESC LIMIT 200", params)]
    for r in rows:
        f = [r["fac_comm"], r["fac_tech"], r["fac_conf"], r["fac_overall"]]
        r["fac_avg"] = round(sum(f) / 4, 1) if all(x is not None for x in f) else None
    courses, _ = filter_options(conn); conn.close()
    return render_template("interviews.html", rows=rows, courses=courses, q=q, course=course)


@app.route("/interviews/start")
def interview_start():
    roll = request.args.get("roll_no", "").strip()
    conn = get_conn(); s = conn.execute("SELECT id FROM students WHERE roll_no=?", (roll,)).fetchone(); conn.close()
    if not s:
        flash("No student found with that roll number.", "danger")
        return redirect(url_for("interviews"))
    return redirect(url_for("interview_record", sid=s["id"]))


@app.route("/students/<int:sid>/interview")
def interview_record(sid):
    conn = get_conn(); s = get_student(conn, sid); conn.close()
    if not s:
        abort(404)
    return render_template("interview_record.html", s=s, questions=QUESTIONS)


@app.route("/students/<int:sid>/interview/submit", methods=["POST"])
def interview_submit(sid):
    conn = get_conn(); s = get_student(conn, sid)
    if not s:
        conn.close(); abort(404)
    if request.form.get("consent") != "yes":
        conn.close(); return jsonify(error="Consent is required before recording."), 400
    try:
        answers = json.loads(request.form.get("answers", "[]"))
        assert isinstance(answers, list) and 1 <= len(answers) <= 10
        answers = [{"question": str(a.get("question", ""))[:300], "text": str(a.get("text", ""))[:5000],
                    "duration": max(0.0, min(float(a.get("duration") or 0), 3600))} for a in answers]
    except Exception:
        conn.close(); return jsonify(error="Invalid answers data."), 400
    video = request.files.get("video")
    if not video or not video.filename:
        conn.close(); return jsonify(error="No video received."), 400
    speech = request.form.get("speech") == "true"
    r = analyze(answers, speech, [k["skill_name"] for k in s["skills_list"]])
    cur = conn.execute(
        "INSERT INTO interviews(student_id,created_at,duration_sec,speech_used,word_count,wpm,filler_count,fluency_score,"
        "pace_score,content_score,vocab_score,technical_score,auto_score,insights) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, datetime.now().strftime("%Y-%m-%d %H:%M"), sum(a["duration"] for a in answers), int(speech), r["word_count"],
         r["wpm"], r["filler_count"], r["fluency_score"], r["pace_score"], r["content_score"], r["vocab_score"],
         r["technical_score"], r["auto_score"], json.dumps(r["insights"])))
    iid = cur.lastrowid
    fname = f"interview_{iid}" + (".mp4" if "mp4" in (video.mimetype or "") else ".webm")
    video.save(os.path.join(UPLOAD_DIR, fname))
    conn.execute("UPDATE interviews SET video_file=? WHERE id=?", (fname, iid))
    for n, a in enumerate(answers, 1):
        conn.execute("INSERT INTO interview_answers(interview_id,q_no,question,answer_text,duration_sec) VALUES(?,?,?,?,?)",
                     (iid, n, a["question"], a["text"], a["duration"]))
    conn.commit(); conn.close()
    return jsonify(ok=True, redirect=url_for("interview_review", iid=iid))


@app.errorhandler(413)
def too_large(e):
    return jsonify(error="Video is too large (max 300 MB). Record shorter answers."), 413


def get_interview(conn, iid):
    row = conn.execute("SELECT i.*, s.name, s.roll_no, s.course FROM interviews i JOIN students s ON s.id=i.student_id "
                       "WHERE i.id=?", (iid,)).fetchone()
    return dict(row) if row else None


@app.route("/interviews/<int:iid>")
def interview_review(iid):
    conn = get_conn(); iv = get_interview(conn, iid)
    if not iv:
        conn.close(); abort(404)
    answers = [dict(r) for r in conn.execute("SELECT * FROM interview_answers WHERE interview_id=? ORDER BY q_no", (iid,))]
    conn.close()
    return render_template("interview_review.html", iv=iv, answers=answers, ins=json.loads(iv["insights"] or "{}"))


@app.route("/interviews/<int:iid>/video")
def interview_video(iid):
    conn = get_conn(); r = conn.execute("SELECT video_file FROM interviews WHERE id=?", (iid,)).fetchone(); conn.close()
    if not r or not r["video_file"] or not os.path.exists(os.path.join(UPLOAD_DIR, r["video_file"])):
        abort(404)
    return send_from_directory(UPLOAD_DIR, r["video_file"])


@app.route("/interviews/<int:iid>/review", methods=["POST"])
def interview_rate(iid):
    def rate(k):
        try:
            v = int(request.form.get(k, ""))
            return v if 1 <= v <= 5 else None
        except ValueError:
            return None
    vals = [rate(k) for k in ("fac_comm", "fac_tech", "fac_conf", "fac_overall")]
    if any(v is None for v in vals):
        flash("Please give all four ratings (1 to 5).", "danger")
    else:
        conn = get_conn()
        conn.execute("UPDATE interviews SET fac_comm=?,fac_tech=?,fac_conf=?,fac_overall=?,fac_comments=? WHERE id=?",
                     (*vals, request.form.get("fac_comments", "").strip()[:1000], iid))
        conn.commit(); conn.close(); flash("Faculty review saved.", "success")
    return redirect(url_for("interview_review", iid=iid))


@app.route("/interviews/<int:iid>/add-skills", methods=["POST"])
def interview_add_skills(iid):
    conn = get_conn(); iv = get_interview(conn, iid)
    if not iv:
        conn.close(); abort(404)
    have = {r[0].lower() for r in conn.execute("SELECT skill_name FROM skills WHERE student_id=?", (iv["student_id"],))}
    added = 0
    for sk in json.loads(iv["insights"] or "{}").get("new_skills", []):
        if sk.lower() not in have:
            conn.execute("INSERT INTO skills(student_id,skill_name,category) VALUES(?,?,?)",
                         (iv["student_id"], sk, SKILL_CATEGORY.get(sk.lower(), "Other"))); added += 1
    conn.commit(); conn.close()
    flash(f"{added} skill(s) added to the student profile.", "success")
    return redirect(url_for("student_detail", sid=iv["student_id"]))


@app.route("/interviews/<int:iid>/delete", methods=["POST"])
def interview_delete(iid):
    conn = get_conn(); remove_video_files(conn, "id=?", (iid,))
    conn.execute("DELETE FROM interviews WHERE id=?", (iid,)); conn.commit(); conn.close()
    flash("Interview deleted.", "warning")
    return redirect(url_for("interviews"))


@app.errorhandler(404)
def nf(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)

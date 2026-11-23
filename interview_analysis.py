"""Rule-based analysis of video-interview transcripts (pure Python, no ML library needed).
The scores are a transparent screening aid, NOT a judgement of the student - faculty review comes alongside."""
import json, math, re
from common import SKILL_CATEGORY

QUESTIONS = [
    "Please introduce yourself - your background, course and interests.",
    "Describe a project you have built. What was your role and which technologies did you use?",
    "Which technical skills are you strongest in, and how have you used them?",
    "Tell us about a challenge you faced and how you handled it.",
    "What are your career goals, and why should a company hire you?",
]

FILLERS = ["um", "umm", "uh", "er", "ah", "basically", "actually", "you know", "i mean", "kind of", "sort of"]

# phrase -> canonical skill name (matched as whole words, case-insensitive)
SKILL_ALIASES = {
    "python": "Python", "java": "Java", "c++": "C++", "sql": "SQL", "mysql": "SQL", "sqlite": "SQL",
    "javascript": "JavaScript", "html": "HTML/CSS", "css": "HTML/CSS", "react": "React", "flask": "Flask",
    "machine learning": "Machine Learning", "deep learning": "Machine Learning", "data analysis": "Data Analysis",
    "data analytics": "Data Analysis", "pandas": "Data Analysis", "numpy": "Data Analysis",
    "power bi": "Power BI", "excel": "Excel", "git": "Git", "github": "Git", "aws": "AWS", "cloud": "AWS",
    "communication": "Communication", "aptitude": "Aptitude", "django": "Django", "node": "Node.js",
    "mongodb": "MongoDB", "tensorflow": "TensorFlow", "nlp": "NLP", "scikit-learn": "Machine Learning",
}
GOAL_KW = ["i want to", "my goal", "i aim", "my aim", "dream", "i plan to", "aspire", "career", "in the future", "become a"]
PROJECT_KW = ["project", "i built", "i developed", "i created", "i made", "application", "website", "system"]
LEARN_KW = ["certif", "course", "coursera", "nptel", "udemy", "internship", "hackathon", "workshop", "training"]

clamp = lambda x, lo=0.0, hi=100.0: max(lo, min(hi, x))


def tokens(text):
    return re.findall(r"[a-zA-Z0-9'+#]+", text.lower())


def detect_skills(text):
    low = text.lower(); found = set()
    for phrase, canon in SKILL_ALIASES.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", low):
            found.add(canon)
    return sorted(found)


def snippets(text, keywords, n=2, before=50, after=110):
    """Short text windows around keyword matches (works even when the transcript has no punctuation)."""
    low, out, last_end = text.lower(), [], -1
    hits = sorted(m.start() for kw in keywords for m in re.finditer(re.escape(kw), low))
    for pos in hits:
        if pos < last_end:
            continue
        s, e = max(0, pos - before), min(len(text), pos + after)
        if s > 0 and " " in text[s:pos]: s = text.find(" ", s) + 1
        if e < len(text) and " " in text[pos:e]: e = text.rfind(" ", pos, e)
        out.append(text[s:e].strip()); last_end = e
        if len(out) >= n:
            break
    return out


def analyze(answers, speech_used, known_skills=()):
    """answers: list of {question, text, duration}. Returns metrics, component scores and extracted insights."""
    texts = [(a.get("text") or "").strip() for a in answers]
    full = " ".join(texts)
    words = tokens(full); n = len(words)
    total_dur = sum(float(a.get("duration") or 0) for a in answers)
    res = dict(word_count=n, wpm=None, filler_count=0, fluency_score=None, pace_score=None,
               content_score=0.0, vocab_score=0.0, technical_score=0.0, auto_score=0.0, insights={})
    if n == 0:
        res["insights"] = dict(skills_detected=[], new_skills=[], goals=[], projects=[], learning=[])
        return res
    low = " " + " ".join(words) + " "
    res["filler_count"] = sum(len(re.findall(r"(?<![a-z])" + re.escape(f) + r"(?![a-z])", low)) for f in FILLERS)
    # content: average answer length (~60 words = full marks) + share of answers with >=10 words
    avg_words = n / max(1, len(answers))
    answered = sum(1 for t in texts if len(tokens(t)) >= 10) / max(1, len(answers))
    res["content_score"] = round(clamp(0.7 * min(100, avg_words / 60 * 100) + 0.3 * answered * 100), 1)
    # vocabulary: root type-token ratio (typical speech 5-9)
    rttr = len(set(words)) / math.sqrt(n)
    res["vocab_score"] = round(clamp((rttr - 3) / (8 - 3) * 100), 1)
    # technical: distinct skills mentioned (5 skills = full marks)
    skills = detect_skills(full)
    res["technical_score"] = round(clamp(len(skills) * 20), 1)
    if speech_used and total_dur > 5:
        wpm = n / (total_dur / 60); res["wpm"] = round(wpm, 1)
        res["pace_score"] = round(clamp(100 if 100 <= wpm <= 170 else 100 - (100 - wpm) * 1.5 if wpm < 100 else 100 - (wpm - 170) * 1.5), 1)
        res["fluency_score"] = round(clamp(100 - res["filler_count"] / n * 500), 1)
    weights = {"content_score": .30, "technical_score": .25, "vocab_score": .15, "pace_score": .15, "fluency_score": .15}
    avail = {k: w for k, w in weights.items() if res[k] is not None}
    res["auto_score"] = round(sum(res[k] * w for k, w in avail.items()) / sum(avail.values()), 1)
    known = {k.lower() for k in known_skills}
    res["insights"] = dict(
        skills_detected=skills, new_skills=[s for s in skills if s.lower() not in known],
        goals=snippets(full, GOAL_KW), projects=snippets(full, PROJECT_KW, 3), learning=snippets(full, LEARN_KW))
    return res

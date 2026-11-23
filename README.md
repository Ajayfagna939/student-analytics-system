# Student Performance, Placement & Career Analytics System
BCA (AI & ML) Major Project - MVN University, Palwal. Flask + SQLite + Pandas + Scikit-learn + Chart.js.

## Run (Windows / Linux / Mac)
```
pip install -r requirements.txt
python generate_dataset.py     # creates data/students.csv (300 SYNTHETIC students; optional, already included)
python init_db.py              # builds database.db from the CSV
python train_model.py          # trains + evaluates the ML model (or use the button on the Prediction page)
python app.py                  # open http://127.0.0.1:5000
python seed_demo_interviews.py # optional: 40 demo interview records (text only)
python tests.py                # automated tests
```
## Files
| File | Purpose |
|---|---|
| app.py | Flask routes: dashboard, CRUD, search/filter, prediction, reports, CSV export |
| common.py | DB schema, helpers, data loading (Pandas), feature list |
| generate_dataset.py | Synthetic dataset generator |
| init_db.py | CSV -> SQLite loader |
| train_model.py | Logistic Regression vs Random Forest, held-out evaluation |
| interview_analysis.py | Transcript analysis: skills, goals, projects, scores (no ML library) |
| seed_demo_interviews.py | Optional demo interview data |
| tests.py | Unit/integration tests (8) |
| templates/, static/ | Bootstrap 5 UI, Chart.js dashboard |

## Using your own data
Replace `data/students.csv` with real (approved, anonymised) data in the same columns, then run `init_db.py` and `train_model.py`.
Prediction output is an estimate, not a guarantee of placement.
Dashboard charts load Bootstrap/Chart.js from a CDN, so internet is needed in the browser.

## Video interview module
Interviews page -> enter roll number -> allow camera/mic -> answer 5 questions. Chrome/Edge give automatic speech-to-text (editable); other browsers let you type. Videos are saved in `uploads/`. Faculty can review the video, see extracted skills/projects/goals, add detected skills to the profile and give 1-5 ratings.
Auto scores are a rule-based screening aid (no face/emotion analysis is used) and not a final judgement of a student.

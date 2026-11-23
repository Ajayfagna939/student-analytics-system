"""Train placement-estimation models from the database.  Usage: python train_model.py
Compares Logistic Regression and Random Forest, keeps the better one (by CV F1)."""
import json, os
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from common import *


def train():
    conn = get_conn(); df = load_df(conn); conn.close()
    if len(df) < 50 or df["placed"].nunique() < 2:
        raise ValueError("Need at least 50 records with both Placed and Not Placed outcomes.")
    X, y = df[FEATURES], df["placed"]
    # Features deliberately exclude package/company -> avoids data leakage.
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    models = {
        "Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "Random Forest": RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42),
    }
    results, best_name, best_cv = {}, None, -1
    for name, m in models.items():
        cv = float(cross_val_score(m, Xtr, ytr, cv=5, scoring="f1").mean())
        m.fit(Xtr, ytr); pred = m.predict(Xte)
        if name == "Random Forest":
            imp = m.feature_importances_
        else:
            imp = np.abs(m[-1].coef_[0]); imp = imp / imp.sum()
        results[name] = dict(
            cv_f1=round(cv, 3), accuracy=round(accuracy_score(yte, pred), 3),
            precision=round(precision_score(yte, pred), 3), recall=round(recall_score(yte, pred), 3),
            f1=round(f1_score(yte, pred), 3), confusion=confusion_matrix(yte, pred).tolist(),
            importance={FEATURE_LABELS[f]: round(float(v), 3) for f, v in zip(FEATURES, imp)})
        if cv > best_cv:
            best_name, best_cv = name, cv
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(models[best_name], MODEL_PATH)
    # numpy-only copy of the Logistic Regression weights (used if scikit-learn cannot be loaded on a PC)
    lr = models["Logistic Regression"]
    with open(LR_PARAMS_PATH, "w") as f:
        json.dump({"features": FEATURES, "mean": lr[0].mean_.tolist(), "scale": lr[0].scale_.tolist(),
                   "coef": lr[-1].coef_[0].tolist(), "intercept": float(lr[-1].intercept_[0])}, f)
    metrics = dict(best_model=best_name, n_train=len(Xtr), n_test=len(Xte), results=results)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    return metrics


if __name__ == "__main__":
    m = train()
    print("Best model:", m["best_model"])
    for k, v in m["results"].items():
        print(f"{k}: acc={v['accuracy']} prec={v['precision']} rec={v['recall']} f1={v['f1']} cv_f1={v['cv_f1']}")

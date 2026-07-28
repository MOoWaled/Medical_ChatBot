"""Build a non-overfitting symptom-retrieval baseline from the project dataset.

There is one source record per condition, so a supervised multi-class classifier
would memorise the labels and cannot be validly evaluated.  This baseline fits a
TF-IDF symptom space and retrieves the nearest known condition instead.
"""

from __future__ import annotations

import argparse
import hashlib
import pickle
from pathlib import Path

import faiss
import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


ROOT_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT_DIR / "dataset" / "usable_dataset.csv"
ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "symptom_retrieval_baseline.joblib"
FAISS_INDEX_PATH = ARTIFACT_PATH.parent / "symptom_tfidf_faiss.bin"
FAISS_RECORDS_PATH = ARTIFACT_PATH.parent / "symptom_tfidf_records.pkl"


def _clean(value: object) -> str:
    return str(value or "").replace("\ufffd", "'").strip()


def _dataset_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def train(force: bool = False) -> Path:
    dataset_hash = _dataset_hash(DATASET_PATH)
    if ARTIFACT_PATH.exists() and FAISS_INDEX_PATH.exists() and FAISS_RECORDS_PATH.exists() and not force:
        existing = joblib.load(ARTIFACT_PATH)
        if existing.get("dataset_hash") == dataset_hash:
            print(f"Baseline is up to date: {ARTIFACT_PATH}")
            return ARTIFACT_PATH

    frame = pd.read_csv(DATASET_PATH).fillna("")
    required = {"Condition_name", "Symptoms"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Dataset must contain {sorted(required)}")

    symptom_column = "cleaned_Symptoms" if "cleaned_Symptoms" in frame.columns else "Symptoms"
    frame["_symptoms"] = frame[symptom_column].map(_clean)
    frame["_condition"] = frame["Condition_name"].map(_clean)
    frame = frame[(frame["_condition"] != "") & (frame["_symptoms"] != "")]
    frame = frame.drop_duplicates(subset=["_condition"], keep="first").reset_index(drop=True)

    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        norm="l2",
    )
    symptom_matrix = vectorizer.fit_transform(frame["_symptoms"])
    records = frame[["_condition", "Symptoms", "Causes", "Warnings", "Recommendations"]].rename(
        columns={"_condition": "Condition_name"}
    ).to_dict(orient="records")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dense_matrix = symptom_matrix.astype(np.float32).toarray()
    faiss.normalize_L2(dense_matrix)
    faiss_index = faiss.IndexFlatIP(dense_matrix.shape[1])
    faiss_index.add(dense_matrix)
    faiss.write_index(faiss_index, str(FAISS_INDEX_PATH))
    with FAISS_RECORDS_PATH.open("wb") as handle:
        pickle.dump(records, handle)
    joblib.dump(
        {
            "kind": "tfidf_symptom_retrieval",
            "dataset_hash": dataset_hash,
            "vectorizer": vectorizer,
            "symptom_matrix": symptom_matrix,
            "records": records,
            "faiss_index_path": str(FAISS_INDEX_PATH),
            "metrics": {
                "method": "cosine retrieval over symptom-only records",
                "training_rows": len(records),
                "note": "No train/test score is reported because each condition has one source record; a label split would be misleading.",
            },
        },
        ARTIFACT_PATH,
    )
    print(f"Built symptom-only TF-IDF FAISS baseline from {len(records)} conditions: {ARTIFACT_PATH}")
    return ARTIFACT_PATH


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Rebuild even if the source dataset is unchanged.")
    args = parser.parse_args()
    train(force=args.force)

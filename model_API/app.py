"""Grounded baseline API.

The former Logistic Regression memorised one long document per condition.  This
service now uses the same symptom-only retrieval knowledge base as the LLMs and
returns source fields verbatim from the selected record.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import joblib
import numpy as np
from flask import Flask, jsonify, request

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from rag_llm_API.retriever import get_retriever, grounded_result
from model_API.train_baseline import ARTIFACT_PATH, train


app = Flask(__name__)


def _fallback_tfidf_result(text: str) -> dict:
    """Use the locally fitted symptom baseline if FAISS cannot be loaded."""
    if not ARTIFACT_PATH.exists():
        train()
    artifact = joblib.load(ARTIFACT_PATH)
    query_vector = artifact["vectorizer"].transform([text])
    scores = (artifact["symptom_matrix"] @ query_vector.T).toarray().ravel()
    index = int(np.argmax(scores))
    record = artifact["records"][index]
    candidate = {
        "condition": str(record["Condition_name"]),
        "symptoms": str(record.get("Symptoms", "")),
        "causes": str(record.get("Causes", "")),
        "warnings": str(record.get("Warnings", "")),
        "recommendations": str(record.get("Recommendations", "")),
        "score": float(scores[index]),
    }
    return grounded_result(candidate)


def _predict(text: str) -> dict:
    try:
        candidates = get_retriever().search(text, top_k=3)
        if candidates:
            return grounded_result(candidates[0], candidates=candidates)
    except Exception as exc:
        app.logger.warning("FAISS retrieval unavailable; using local TF-IDF fallback: %s", exc)
    return _fallback_tfidf_result(text)


@app.get("/health")
def health_check():
    return jsonify(
        {
            "status": "Active",
            "model_name": "grounded_symptom_retrieval_baseline",
            "artifact_path": str(ARTIFACT_PATH),
            "rag_index_available": (ROOT_DIR / "rag_llm_API" / "faiss_index" / "faiss_store.bin").exists(),
        }
    )


@app.post("/predict")
def predict_disease():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"error": "Please provide non-empty text in the JSON body."}), 400

    result = _predict(text)
    details = {key: result[key] for key in ("condition", "symptoms", "causes", "warnings", "recommendations")}
    return jsonify(
        {
            "status": "success",
            "predicted_condition": result["condition"],
            "confidence": result["confidence"],
            "medical_details": details,
            "retrieval_candidates": result["retrieval_candidates"],
        }
    )


if __name__ == "__main__":
    train()  # Build/update the local, symptom-only baseline when the dataset changes.
    app.run(host="0.0.0.0", port=5000, debug=False)

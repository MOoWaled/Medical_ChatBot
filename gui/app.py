"""Streamlit user interface for the Medical ChatBot project."""

from __future__ import annotations

import os

import streamlit as st

from model_clients import (
    DEFAULT_BASELINE_URL,
    DEFAULT_MISTRAL_URL,
    DEFAULT_QWEN_URL,
    ModelRequestError,
    analyse_symptoms,
)


st.set_page_config(
    page_title="Medical ChatBot",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)


def add_page_style() -> None:
    """Apply small, local styling without relying on external assets."""
    st.markdown(
        """
        <style>
            .block-container { max-width: 1120px; padding-top: 2.5rem; }
            .result-card {
                border: 1px solid #dce5ec;
                border-radius: 12px;
                padding: 1rem 1.1rem;
                min-height: 148px;
                background: #ffffff;
            }
            .result-card h3 { color: #0b5e55; margin-top: 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_result_card(title: str, value: str) -> None:
    """Render one safely escaped result block."""
    st.markdown(f"### {title}")
    st.write(value or "No information returned by the selected model.")


add_page_style()

st.title("🩺 Medical Condition Assistant")
st.caption("Describe symptoms, select one model, and receive a structured medical-information response.")
st.warning(
    "This tool provides educational information only; it is not a medical diagnosis. "
    "For severe symptoms or a medical emergency, contact local emergency services immediately."
)

with st.sidebar:
    st.header("Model settings")
    model_label = st.selectbox(
        "Choose a model",
        ("Grounded FAISS Baseline", "Mistral", "Qwen"),
        help="All choices retrieve their answer from the local condition knowledge base first.",
    )

    baseline_url = st.text_input(
        "Grounded Baseline API URL",
        value=os.getenv("BASELINE_API_URL", DEFAULT_BASELINE_URL),
        help="The local Flask API from model_API/app.py, usually running on port 5000.",
    )
    qwen_url = st.text_input(
        "Qwen API URL",
        value=os.getenv("QWEN_API_URL", DEFAULT_QWEN_URL),
        help="Base ngrok/Ollama URL. The app calls its /api/chat endpoint.",
    )
    mistral_url = st.text_input(
        "Mistral API URL",
        value=os.getenv("MISTRAL_API_URL", DEFAULT_MISTRAL_URL),
        help="Custom ngrok/Flask base URL (the app calls /generate), or https://api.mistral.ai/v1.",
    )
    mistral_api_key = st.text_input(
        "Mistral API key (optional)",
        value=os.getenv("MISTRAL_API_KEY", ""),
        type="password",
    )

    st.divider()
    st.caption("Endpoint addresses are used only for the current request and are not saved by the app.")

symptoms = st.text_area(
    "Symptoms or medical concern",
    placeholder="Example: I have a persistent cough, wheezing, and shortness of breath.",
    height=190,
)

submit = st.button("Analyse symptoms", type="primary", use_container_width=True)

if submit:
    if not symptoms.strip():
        st.error("Please describe at least one symptom before continuing.")
        st.stop()

    selected_model = {
        "Grounded FAISS Baseline": "logistic_baseline",
        "Mistral": "mistral",
        "Qwen": "qwen",
    }[model_label]

    with st.spinner(f"Contacting {model_label}..."):
        try:
            result = analyse_symptoms(
                model=selected_model,
                symptoms=symptoms.strip(),
                baseline_url=baseline_url,
                qwen_url=qwen_url,
                mistral_url=mistral_url,
                mistral_api_key=mistral_api_key,
            )
        except ModelRequestError as error:
            st.error(str(error))
            st.stop()

    st.success(f"Response received from {model_label}.")

    confidence = result.get("confidence")
    if confidence is not None:
        st.caption(f"Baseline model confidence: {confidence}%")

    left, right = st.columns(2)
    with left:
        show_result_card("Condition", result["condition"])
        show_result_card("Symptoms", result["symptoms"])
        show_result_card("Causes", result["causes"])
    with right:
        show_result_card("Warnings", result["warnings"])
        show_result_card("Recommendations", result["recommendations"])

    with st.expander("Technical response"):
        st.json(result)

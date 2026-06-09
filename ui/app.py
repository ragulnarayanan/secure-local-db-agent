"""Streamlit UI for the secure local DB agent.

Surfaces each pipeline stage — generated SQL, the safety verdict, then results —
so the SQL safety gate is visible, not implicit. Run with:

    streamlit run ui/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# `streamlit run ui/app.py` executes this file as a standalone script, so `src`
# is not guaranteed to be importable. Put the project root on the path so the
# app runs from any cwd, with or without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent import OllamaAgent  # noqa: E402
from src.runner import Runner  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(PROJECT_ROOT / "data" / "chinook.db")
MODELS = ["llama3.1:8b", "qwen2.5-coder:7b", "phi3:mini"]


@st.cache_resource(show_spinner=False)
def get_runner(model: str, db_path: str) -> Runner:
    """One Runner per model, built once. Streamlit re-runs the whole script on
    every interaction, so the schema introspection must be cached here."""
    return Runner(db_path, OllamaAgent(model))


st.set_page_config(page_title="Secure Local DB Agent", page_icon="🛡️")
st.title("🛡️ Secure Local DB Agent")
st.caption("Offline text-to-SQL with an AST-based safety layer. No data leaves the host.")

with st.sidebar:
    st.header("Settings")
    model = st.selectbox("Model", MODELS)
    runner = get_runner(model, DB_PATH)
    with st.expander("Database schema", expanded=False):
        st.code(runner.schema.to_prompt(), language="text")

question = st.text_input(
    "Ask a question about the database",
    placeholder="Which 5 artists have the most albums?",
)

if st.button("Generate SQL", type="primary") and question:
    with st.spinner(f"Asking {model}…"):
        result = runner.run(question)

    reason = result.failure_reason or ""

    if reason.startswith("generation"):
        st.error(f"Model did not return valid SQL ({reason}).")
    else:
        st.subheader("Generated SQL")
        st.code(result.sql, language="sql")
        if result.reasoning:
            st.caption(result.reasoning)
        st.metric("Inference latency", f"{result.latency_ms:.0f} ms")

        if reason.startswith("safety"):
            st.error(f"❌ Safety check FAILED — query blocked before execution.\n\n{reason}")
        else:
            st.success("✅ Safety check passed — single read-only SELECT on allowed tables.")
            if reason.startswith("execution"):
                st.warning(f"Query was safe but failed to execute: {reason}")
            elif result.ok:
                st.subheader(f"Results ({len(result.rows)} rows)")
                st.dataframe(
                    pd.DataFrame(result.rows, columns=result.columns),
                    use_container_width=True,
                )

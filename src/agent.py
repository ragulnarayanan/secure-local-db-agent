"""Ollama client that turns a natural-language question into a validated SQL response.

The model is asked for JSON via Ollama's `format: "json"` constraint (not prompt
begging), and the result is validated with Pydantic before anything downstream
trusts it.
"""
from __future__ import annotations

import logging

import requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"


class SQLResponse(BaseModel):
    """The contract we require from the model. `model_validate_json` rejects any
    response missing `sql`, or with the wrong types, at the boundary."""

    sql: str
    reasoning: str


# The model is *asked* for SELECT-only here, but the Day 3 safety layer is what
# *guarantees* it. Prompt = please; safety layer = enforce. Defense in depth.
SYSTEM_PROMPT = (
    "You are an expert SQLite analyst. Given a database schema and a question, "
    "write a single SQLite SELECT query that answers it.\n"
    "Rules:\n"
    "- Use ONLY tables and columns that appear in the schema.\n"
    "- Write exactly one read-only SELECT statement. Never modify data.\n"
    "- Respond with JSON only, matching: "
    '{"sql": "<the query>", "reasoning": "<one short sentence>"}'
)


def build_user_prompt(schema_text: str, question: str) -> str:
    """Combine the introspected schema with the user's question.

    Schema first, question last: the model reads the schema as context, then the
    question is the most recent (and most attended-to) part of the prompt.
    """
    return f"Schema:\n{schema_text}\n\nQuestion: {question}"


class OllamaAgent:
    """Client for a single local model served by Ollama.

    One instance per model — the Day 5 eval creates several and benchmarks them.
    """

    def __init__(
        self,
        model: str,
        host: str = DEFAULT_HOST,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def generate_sql(self, schema_text: str, question: str) -> SQLResponse:
        """Ask the model for SQL and return a validated SQLResponse.

        Raises requests.HTTPError / ConnectionError on transport failure and
        pydantic.ValidationError if the model's JSON doesn't match the contract.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(schema_text, question)},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},  # deterministic output for reproducible evals
        }
        logger.debug("POST %s/api/chat model=%s", self.host, self.model)
        resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
        resp.raise_for_status()

        content = resp.json()["message"]["content"]
        return SQLResponse.model_validate_json(content)

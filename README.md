# Secure Local DB Agent

An offline text-to-SQL agent for SQLite databases. Runs entirely on local LLMs via Ollama, with a structured-output layer and a SQL safety gate that rejects anything that isn't a safe SELECT against the allowed schema.

> Status: in development (7-day build, Day 5 of 7).

## What it does

Takes a natural-language question, introspects the database schema, asks a local LLM to write a SQL query (in structured JSON), validates the query through a safety layer, runs it, and returns the result.

## Why it exists

- **Zero data egress** — query proprietary databases without sending schema or data to any cloud API
- **Structured output** — no markdown-stripping, no regex parsing of LLM responses
- **Safety layer** — every query is parsed with `sqlglot` and rejected if it's not a single SELECT against allowlisted tables
- **Benchmarked** — evaluates multiple local 7B/8B models on the same question set with result-equivalence checking

## Stack

- Ollama (local LLM serving)
- `qwen2.5-coder:7b`, `llama3.1:8b` (benchmarked)
- `sqlglot` (SQL parsing + safety)
- `pydantic` (structured output validation)
- `streamlit` (UI)

## Setup

```bash
# Prereqs: Ollama installed, models pulled
brew install ollama
ollama serve  # in a separate terminal
ollama pull qwen2.5-coder:7b
ollama pull llama3.1:8b

# Project
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Get the Chinook sample DB
curl -L -o data/chinook.db https://github.com/lerocha/chinook-database/raw/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite

# Test schema introspection
python -m src.schema data/chinook.db
```

## Results

Benchmarked on 20 questions against the Chinook schema (M4 Pro, 24 GB unified memory), `temperature = 0`, with result-equivalence checking:

| Model | Accuracy | p50 latency | p95 latency |
|-------|----------|-------------|-------------|
| llama3.1:8b      | **85%** | 1580 ms | 2748 ms |
| qwen2.5-coder:7b | 75%     | 1566 ms | 2580 ms |
| phi3:mini (3.8B) | 70%     | 994 ms  | 1797 ms |

See [`docs/results.md`](docs/results.md) for per-tier accuracy and failure-mode analysis.

## Architecture

_Diagram coming on Day 7._

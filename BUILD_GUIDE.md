# Secure Local DB Agent — Claude Code Build Guide

> **For Claude Code:** This document is your single source of truth for this 7-day project. Read it fully before doing anything. Follow the **Teaching Protocol** in Section 0 on every step.

---

## Section 0: Teaching Protocol (READ FIRST — APPLIES TO EVERY STEP)

The user (Rana) is building this project **to learn**, not just to ship. He has a strong data engineering background (PySpark, Snowflake, Airflow) and applied LLM experience (LangChain, RAG, MarketMind), but wants to deeply understand local-model orchestration, SQL safety, and evaluation harnesses.

**On every meaningful step you take, you MUST:**

1. **Explain WHAT before you do it.** Before writing or running code, state in 1-3 sentences what you are about to do and why this step exists in the project.
2. **Explain WHY this approach.** When you pick a library, pattern, or design — briefly contrast it with at least one alternative and explain the tradeoff. Example: "I'm using `sqlglot` here instead of regex because regex can't reliably tell `SELECT ... FROM users WHERE name = 'DROP TABLE x'` apart from an actual DROP."
3. **Pause for understanding.** After each non-trivial chunk of code, ask Rana: *"Does this make sense? Want me to go deeper on X, or move on?"* — and actually wait for his response. Don't barrel through.
4. **Quiz periodically.** Every 2-3 substantial steps, ask him a small comprehension question: *"Quick check — why did we make the schema introspection a separate module instead of inlining it into the agent?"* Don't make this a test; make it a conversation.
5. **Surface tradeoffs honestly.** When a "best practice" has downsides, name them. When a shortcut is acceptable, say so. Don't pretend everything is optimal.
6. **Never just dump code.** Comments inside the code are good; an explanation in chat before/after is required.

**Tone:** Direct, technical-peer, not hand-holding. Rana communicates concisely and pushes back on inflated language — match that. No "Great question!" or filler. Just teach.

**If Rana says "skip the explanation, just do it"** — respect it, but ask once if he wants to come back to that concept later.

---

## Section 1: Project Overview

### What we're building

A text-to-SQL agent that runs **entirely locally** on an M4 Pro Mac. It:
1. Introspects any SQLite database schema automatically
2. Sends (schema + question) to a local LLM via Ollama
3. Receives a structured JSON response (`{sql, reasoning}`) — no markdown stripping, no regex
4. Validates the SQL through a **safety layer** using `sqlglot`: SELECT-only, single statement, table allowlist, blocks `PRAGMA`/`ATTACH`/`.dump`
5. Executes the query and returns results
6. Benchmarks multiple local models (`qwen2.5-coder:7b`, `llama3.1:8b`) on a curated question set with **result-equivalence checking** (two correct SQL statements may differ in text but produce identical result sets)
7. Ships with a Streamlit UI and a recorded demo

### Why this project (for the resume)

Three things this proves that MarketMind/EchoAI don't:
- **Production safety thinking** — anyone can wrap an LLM API. The `sqlglot` safety layer with proper rejection handling is what an actual ML platform engineer would build.
- **Evaluation rigor** — a benchmark table in the README with accuracy + p50 latency across models is what hiring managers at DataRobot/Salsify/Dynatrace want to see.
- **Local-LLM specialization** — most candidates only know cloud APIs. Understanding `format: json`, unified memory inference, and the tradeoffs of quantized 7B models is differentiated.

### Resume bullet (target, to verify against results on Day 5)

> Engineered an offline text-to-SQL agent with `sqlglot`-based safety layer and structured JSON output; benchmarked 3 local 7B/8B models across 20 questions on Chinook schema, achieving __% accuracy with p50 __ms inference on M4 Pro (no cloud egress).

---

## Section 2: Pre-flight Checklist (do BEFORE starting Day 1)

Confirm with Rana that these are done. If any aren't, walk him through them.

- [ ] Ollama installed via `brew install ollama`
- [ ] `ollama serve` running in a background terminal
- [ ] `ollama pull qwen2.5-coder:7b` complete
- [ ] `ollama pull llama3.1:8b` complete
- [ ] `ollama run qwen2.5-coder:7b "say hi"` returns a response
- [ ] Python 3.11+ available (`python3 --version`)
- [ ] Git installed and configured with his name/email (`git config --global user.name` and `user.email`)
- [ ] A GitHub account exists (`ragulnarayanan`) — confirmed from his existing repos
- [ ] He has a GitHub Personal Access Token OR SSH key set up for pushing

---

## Section 3: Initial Project Setup (Claude Code best practices)

Before writing any project code, set up these files. Explain each one to Rana as you create it.

### 3.1 Directory structure

```
secure-local-db-agent/
├── .claude/
│   ├── settings.json         # Project-level Claude Code settings
│   └── commands/             # Reusable slash-commands (added as we go)
├── .github/
│   └── workflows/
│       └── tests.yml         # CI: run pytest on push
├── src/
│   ├── __init__.py
│   ├── schema.py             # Schema introspection (Day 1)
│   ├── agent.py              # Ollama client + structured output (Day 2)
│   ├── safety.py             # sqlglot validator (Day 3)
│   └── runner.py             # Orchestrator: question -> SQL -> safety -> execute
├── tests/
│   ├── __init__.py
│   ├── test_schema.py
│   ├── test_safety.py
│   └── test_runner.py
├── data/
│   └── chinook.db            # Downloaded, gitignored if large
├── evals/
│   ├── questions.yaml        # Curated question/SQL pairs (Day 4)
│   ├── run_eval.py           # Eval harness (Day 4)
│   └── results/              # Eval CSV outputs (gitignored)
├── ui/
│   └── app.py                # Streamlit UI (Day 6)
├── docs/
│   ├── architecture.md       # Diagram + design notes (Day 7)
│   └── results.md            # Eval results writeup (Day 5)
├── .gitignore
├── .python-version           # Pin Python version
├── CLAUDE.md                 # Project memory for Claude Code
├── README.md
├── pyproject.toml            # Modern Python project config
└── BUILD_GUIDE.md            # This file
```

### 3.2 `CLAUDE.md` (project memory)

Create this **first**. Claude Code automatically reads it on every session. Content:

```markdown
# Project: Secure Local DB Agent

## Mode
This is a learning project. Follow the Teaching Protocol in `BUILD_GUIDE.md` Section 0.
Always explain WHAT and WHY before writing code. Pause for understanding.

## Stack
- Python 3.11+
- Ollama (local LLM server at http://localhost:11434)
- Models: qwen2.5-coder:7b, llama3.1:8b
- Libs: requests, pydantic, sqlglot, pandas, streamlit, pytest

## Conventions
- Type hints on all functions (PEP 604: `str | None`, not `Optional[str]`)
- Dataclasses for plain data, Pydantic only when validating untrusted input
- Tests live in `tests/`, mirror `src/` structure
- No `print()` in src code — use `logging`
- Run `pytest -q` before any commit

## Git
- Conventional commit prefixes: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- One logical change per commit
- DO NOT add Claude as a co-author. DO NOT include "Generated with Claude Code" trailers. Commits are authored by Rana only.

## Anti-patterns to avoid
- Stripping markdown from LLM output with regex (use Ollama's `format: "json"` instead)
- Catching bare `Exception` (catch specific ones)
- Mutable default arguments
- Hardcoding paths (use `pathlib.Path` and config)
```

### 3.3 `.claude/settings.json`

Project-level Claude Code config. Allows certain tools without per-action prompting.

```json
{
  "permissions": {
    "allow": [
      "Bash(python -m pytest:*)",
      "Bash(python -m src.*)",
      "Bash(python -m evals.*)",
      "Bash(pip install:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git add:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(curl -L -o data/*)"
    ],
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(git push --force:*)"
    ]
  }
}
```

**Explain to Rana:** `allow` skips the per-action approval prompt for safe operations. `deny` blocks dangerous ones outright. He should adjust as needed.

### 3.4 `pyproject.toml`

Modern Python config — preferred over standalone `requirements.txt` (though we keep `requirements.txt` as a generated artifact for compatibility).

```toml
[project]
name = "secure-local-db-agent"
version = "0.1.0"
description = "Offline text-to-SQL agent with structured output and SQL safety layer"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31.0",
    "pydantic>=2.5.0",
    "sqlglot>=23.0.0",
    "pandas>=2.1.0",
    "streamlit>=1.30.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "-q --tb=short"

[tool.ruff]
line-length = 100
target-version = "py311"
```

### 3.5 `.gitignore`

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.env
.DS_Store
.pytest_cache/
.ruff_cache/
evals/results/
*.log
# Keep data/chinook.db tracked since it's small (~1MB) and useful for reviewers
```

### 3.6 `.python-version`

```
3.11
```

### 3.7 `.github/workflows/tests.yml`

CI runs pytest on every push. Hiring managers check this — a green badge says "this person tests their code."

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest -q
```

**Explain:** This won't run the Ollama-dependent tests in CI (no GPU on GitHub runners), so write `safety.py` and `schema.py` tests so they don't require Ollama. Mark Ollama tests with `@pytest.mark.integration` and skip them in CI.

### 3.8 Initial Git setup

```bash
cd secure-local-db-agent
git init
git add .
git commit -m "chore: initial project scaffold"
# Then on GitHub.com create the repo (do NOT initialize with README on GitHub)
git remote add origin git@github.com:ragulnarayanan/secure-local-db-agent.git
git branch -M main
git push -u origin main
```

**CRITICAL git rules for Claude Code:**
- Author is **Rana**, not Claude. Never use `--author` flag with Claude's name.
- Never add `Co-Authored-By: Claude` lines.
- Never add `🤖 Generated with [Claude Code](...)` trailers.
- Use conventional commit prefixes only.
- One logical change per commit (e.g., "feat: add schema introspection" is one commit; tests for it are a separate commit "test: add schema introspection tests").

---

## Section 4: Day-by-Day Plan

### Day 1 — Foundation
**Goal:** Schema introspection working end-to-end on Chinook.

Steps:
1. Run pre-flight checklist (Section 2)
2. Create project scaffold (Section 3) — every file
3. Download Chinook DB: `curl -L -o data/chinook.db https://github.com/lerocha/chinook-database/raw/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite`
4. Implement `src/schema.py` (introspection: tables, columns, types, PKs, FKs → prompt-ready string)
5. Write `tests/test_schema.py` (use a tiny in-memory DB built in the test fixture, not chinook)
6. Run `pytest -q` — must be green
7. Commit: `feat: add SQLite schema introspection`
8. Commit: `test: cover schema introspection`
9. Push to GitHub

**Teaching focus for Day 1:**
- Why introspection > hardcoded schemas (works on any DB)
- Why PRAGMA queries instead of parsing `CREATE TABLE` strings
- Why dataclasses here, not Pydantic (we control this data, no validation needed)
- Why we test against an in-memory DB, not the real Chinook (fast, deterministic, no file dependency)

### Day 2 — Ollama client + structured output
**Goal:** Agent returns valid JSON for any natural language question.

Steps:
1. Implement `src/agent.py` — Ollama HTTP client with `format: "json"`
2. Pydantic model for response: `class SQLResponse(BaseModel): sql: str; reasoning: str`
3. Prompt template combining schema + question
4. Tests using a mock Ollama response (don't hit the real server in unit tests)
5. One integration test marked `@pytest.mark.integration` that hits real Ollama
6. Commit + push

**Teaching focus:**
- Why `format: "json"` beats prompt engineering ("respond in JSON")
- How Pydantic catches schema drift early
- Mock vs integration tests — when each is right

### Day 3 — The safety layer (THE differentiator)
**Goal:** Any non-SELECT, multi-statement, or out-of-allowlist query is rejected before execution.

Steps:
1. Implement `src/safety.py`:
   - Parse SQL with `sqlglot.parse()`
   - Reject if more than one statement
   - Reject if statement isn't `SELECT`
   - Reject if any referenced table is outside the allowlist
   - Reject `PRAGMA`, `ATTACH`, `.dump`, `.import`, etc.
   - Each rejection raises a typed exception (`MultipleStatementsError`, `NonSelectError`, `UnknownTableError`)
2. Exhaustive tests in `tests/test_safety.py`:
   - All valid SELECTs pass
   - `SELECT * FROM users; DROP TABLE users;` fails with `MultipleStatementsError`
   - `DROP TABLE users` fails with `NonSelectError`
   - `SELECT * FROM secret_table` fails with `UnknownTableError`
   - `SELECT * FROM users WHERE name = 'DROP TABLE x'` PASSES (it's a string literal, not a statement)
3. Commit + push

**Teaching focus:**
- Why AST-based validation > regex (the last test case proves this)
- What's an AST, what does `sqlglot.parse()` actually return
- Why we use custom exceptions instead of bare `ValueError`

### Day 4 — Runner + Eval harness
**Goal:** End-to-end pipeline + measurable benchmarks.

Steps:
1. Implement `src/runner.py` — orchestrates: schema → agent → safety → execute → result
2. Build `evals/questions.yaml`: 20 questions across difficulty tiers (5 easy, 10 medium, 5 hard), each with the canonical correct SQL
3. Implement `evals/run_eval.py`:
   - Load questions
   - For each question × model: generate SQL, validate, execute, compare result set to canonical
   - Result-equivalence check: sort both result sets, compare as sets of tuples (handles column ordering, row ordering)
   - Record: question_id, model, generated_sql, latency_ms, passed, failure_reason
   - Output CSV to `evals/results/{timestamp}_{model}.csv`
4. Commit + push

**Teaching focus:**
- Why result-equivalence > string comparison (two correct SQLs differ textually)
- How to handle SQL non-determinism (ORDER BY missing → row order varies)
- Why difficulty tiers — single number hides whether the model fails on JOINs vs aggregations

### Day 5 — Run evals + writeup
**Goal:** Real numbers in the README.

Steps:
1. Run eval against `qwen2.5-coder:7b`, `llama3.1:8b`, and one more (let Rana pick from `mistral`, `phi3`, `codellama`)
2. Aggregate results: accuracy per model, accuracy per difficulty tier, p50/p95 latency
3. Write `docs/results.md` with the results table and a short failure-mode analysis ("qwen failed mostly on multi-JOIN queries, llama failed mostly on aggregation with WHERE")
4. Update README with the headline number
5. Commit + push

**Teaching focus:**
- How to read evaluation results — accuracy alone is misleading
- Failure modes matter more than overall accuracy for model selection

### Day 6 — Streamlit UI
**Goal:** Demo-able interface, GIF for README.

Steps:
1. Implement `ui/app.py`:
   - Sidebar: model picker, schema viewer
   - Main: question input → "Generate SQL" → preview generated SQL → "Safety check: passed/failed" → if passed, show results table
   - Show latency
2. Record a 30-second GIF (use macOS built-in screen record + convert with `ffmpeg` or QuickTime → `gifski`)
3. Add GIF to README
4. Commit + push

### Day 7 — Polish, README, ship
**Goal:** Repository looks recruiter-ready.

Steps:
1. Architecture diagram (Mermaid in `docs/architecture.md`)
2. Full README rewrite using the template in Section 5 below
3. Pin the repo on his GitHub profile (`ragulnarayanan`)
4. Add the bullet to his resume (Section 1 above, with real numbers filled in)
5. Final commit + push

---

## Section 5: README template (for Day 7)

```markdown
# Secure Local DB Agent

> Offline text-to-SQL agent with structured output and SQL safety layer. Built for environments where data cannot leave the host.

![demo](docs/demo.gif)

## Results

| Model | Accuracy | p50 latency | p95 latency |
|-------|----------|-------------|-------------|
| qwen2.5-coder:7b | __% | __ms | __ms |
| llama3.1:8b | __% | __ms | __ms |
| __ | __% | __ms | __ms |

Tested on 20 questions against the Chinook schema (M4 Pro, 24GB unified memory). See `docs/results.md` for failure-mode analysis.

## Architecture

[Mermaid diagram]

## Why this exists

- Zero data egress — schema and data never leave the host
- Structured output via Ollama `format: "json"` — no markdown stripping, no regex parsing
- AST-based safety layer (`sqlglot`) — every query parsed and validated against an allowlist before execution
- Benchmarked, not just claimed

## Stack

- Python 3.11+, Ollama, `sqlglot`, `pydantic`, `streamlit`
- Local models: `qwen2.5-coder:7b`, `llama3.1:8b`

## Run it

[setup steps]

## License

MIT
```

---

## Section 6: Things to specifically NOT do

- Don't reproduce Gemini's original 60-line script. We are intentionally building a larger, more credible artifact.
- Don't claim "zero hallucination" or "100% accuracy" anywhere. Use real numbers from the eval.
- Don't commit `data/chinook.db` if it's >5MB. Check size first.
- Don't push secrets. There shouldn't be any in this project, but check before each push.
- Don't add Claude as co-author to any commit.
- Don't skip the teaching protocol because something seems "obvious."

---

## Section 7: Where to pause and check with Rana

At minimum, pause and ask before:
- Installing any new dependency not listed in `pyproject.toml`
- Making the first commit (verify git config is his, not yours)
- Making the first push (verify the remote is correct)
- Modifying anything in `.claude/settings.json` after initial setup
- Picking the third model for the eval (let him choose)

---

## Section 8: First message to send Rana when you start

Tell him:
1. You've read this guide
2. Confirm you understand the teaching protocol — explain it back in your own words in 2 sentences
3. Walk him through the pre-flight checklist and confirm each item before starting Day 1
4. Then start with Section 3 (project scaffold), explaining each file as you create it

Ready? Begin.

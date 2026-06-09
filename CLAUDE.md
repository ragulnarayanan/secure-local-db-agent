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

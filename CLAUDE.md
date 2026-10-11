# CLAUDE.md

Working rules for Claude Code in this repository. README.md is the spec for how the app
behaves; this file is about how to work on it.

## README-first workflow

1. **Before implementing**, update README.md to describe the new or changed behavior
   (what the user sees, scoring rules, API fields, config, privacy). Treat it as the spec
   you then implement.
2. **Implement** the change, with tests.
3. **After implementing**, compare README.md with the code and fix any gap, in either
   direction. Check at least:
   - "How it works" and "Tech stack"
   - Configuration table vs. the environment variables actually read (also `.env.example`)
   - Scoring tables (patterns, penalties, questions) vs. `app/questions.py`
   - "How to improve" vs. `suggest_improvements()` in `app/analyzer.py`
   - "Data collection and privacy" vs. what `app/db.py` stores and what is sent to
     external services (Gemma, Have I Been Pwned)
   - API table and example response vs. `app/main.py` (run the example if values changed)
   - Project structure vs. the files in the repo
   - "Testing" and "Changing questions or penalties"
4. When reporting the work, say what was changed in README.md and any gap you found.

## Project rules

- Run tests with `uv run pytest`. Tests must not make network calls
  (mock `app.breach` or set `BREACH_CHECK=false`).
- Bump `SCORING_VERSION` in `app/analyzer.py` whenever scores or the assessment
  response change.
- All rules (questions, automatic checks, penalties, tips, fixes) live in
  `app/questions.py`.
- Never store or log the password or any hash of it. Only derived features go to the
  database and to Gemma; only the first 5 SHA-1 characters go to Have I Been Pwned.
- The app deliberately never asks users to type personal details (name, birthday, etc.).
  Personal-info checks stay as yes/no questions.
- UI text and README are English only.

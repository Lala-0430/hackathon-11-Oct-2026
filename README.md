# Password Strength Checker

A web app that rates how strong a password is. It combines **automatic analysis** with a few
**yes/no questions** about things that can't be detected from the password alone, such as
"Does it contain your name?" or "Do you reuse it on other sites?".

No account is needed. The password is analyzed in memory and is **never stored**.
Each check is saved as an anonymous record (derived features + answers + result),
so the scoring can be improved over time.

## How it works

1. **Enter a password.** It is kept in the browser until you submit.
2. **Answer yes/no questions** about personal information and how you use the password.
3. **Get your result:** a 0–100 score, a label (Very Weak → Very Strong), an estimated
   crack time, the issues found, and concrete tips.
4. *(Optional)* **Get AI advice** from Gemma, based on the analysis only (never the password).
5. *(Optional)* **Rate the result** ("Too low" / "Accurate" / "Too high"). This feedback is stored
   with the record and can be used to tune the scoring.

```
Browser ──POST /api/assess {password, answers}──▶ FastAPI
                                                   ├─ analyzer: features + score (in memory)
                                                   └─ SQLite: features, answers, score   ← no password
Browser ◀────────────── score, label, tips ────────┘
```

## Tech stack

| Layer    | Technology                                   |
|----------|----------------------------------------------|
| Backend  | Python 3.12, FastAPI, Uvicorn                |
| Database | SQLite (Python standard library `sqlite3`)   |
| Frontend | Plain HTML, CSS, and JavaScript (no build)   |
| AI       | Gemma via the Gemini API (`google-genai`), optional |
| Tooling  | [uv](https://docs.astral.sh/uv/), pytest     |

## Getting started

Prerequisite: [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
# 1. Install dependencies
uv sync

# 2. (Optional) configure environment variables
cp .env.example .env
# Set GEMINI_API_KEY in .env to enable AI advice

# 3. Run the server
uv run python main.py
```

Open <http://127.0.0.1:8000>.

For development with auto-reload:

```bash
RELOAD=true uv run python main.py
```

### Configuration

All settings are optional and read from the environment or `.env`.

| Variable         | Default                 | Description                                  |
|------------------|-------------------------|----------------------------------------------|
| `GEMINI_API_KEY` | *(unset)*               | Enables the "Get AI advice" button           |
| `GEMMA_MODEL`    | `gemma-4-26b-a4b-it`    | Gemma model used for advice                  |
| `DATABASE_PATH`  | `data/assessments.db`   | SQLite database file                         |
| `HOST`           | `127.0.0.1`             | Server host                                  |
| `PORT`           | `8000`                  | Server port                                  |
| `RELOAD`         | `false`                 | Auto-reload on code changes                  |

## Scoring

All questions, automatic checks, penalties, and advice are defined in one place:
[`app/questions.py`](app/questions.py). The detection and scoring code is in
[`app/analyzer.py`](app/analyzer.py).

1. **Base score from entropy.** Entropy is estimated as `length × log2(character pool size)`,
   where the pool depends on which character types are used (lowercase 26, uppercase 26,
   digits 10, symbols 33, non-ASCII 100). 90 bits or more gives a base score of 100.
2. **Pattern penalties.** These patterns are detected automatically:

   | Pattern                | Penalty | Example          |
   |------------------------|---------|------------------|
   | Common password        | 100     | `password`, `P@ssw0rd` |
   | Contains common password | 20    | `xxpassword99`   |
   | Keyboard pattern       | 15      | `qwer`, `asdf`   |
   | Sequence               | 10      | `abc`, `321`     |
   | Repeated characters    | 10      | `aaa`            |
   | Year                   | 10      | `1998`           |
   | Date                   | 10      | `0315` + a year  |
   | Letters only           | 10      | `sunflower`      |
   | Digits only            | 20      | `48291736`       |
   | Shorter than 8         | 20      | `a1!b`           |
   | All one case           | 10      | `sunflower99`, `HELLO!` |

3. **Question penalties.** Each "yes" answer subtracts points:

   | Question                                                          | Penalty |
   |-------------------------------------------------------------------|---------|
   | Contains your name or nickname                                    | 25      |
   | Contains your date of birth or birth year                         | 25      |
   | Contains your city, town or street name                           | 15      |
   | Contains the name of a family member, friend, partner or pet      | 20      |
   | Contains a predictable sequence or repeats (e.g. `12345`, `qwerty`, `aaa`) | 15* |
   | Used on other websites or accounts                                | 20      |
   | Contains a phone number, house number, postcode or ID number      | 20      |
   | Based on a favourite team, band, hobby or brand                   | 10      |
   | A normal word with simple swaps (e.g. `a` → `@`, `o` → `0`)       | 15      |
   | Shared with anyone else                                           | 10      |
   | Appeared in a data breach                                         | 30      |

   \* Skipped if a sequence, keyboard pattern, or repeated characters were already
   detected automatically, so the same weakness is not counted twice
   (see `overlaps` in `app/questions.py`).

   Things the app can check from the password itself (common passwords, length,
   digits/letters only, single case) are detected automatically instead of being asked.

4. **Final score** = base − penalties, clamped to 0–100.

   | Score  | Label       |
   |--------|-------------|
   | 80–100 | Very Strong |
   | 60–79  | Strong      |
   | 40–59  | Fair        |
   | 20–39  | Weak        |
   | 0–19   | Very Weak   |

The **crack time** assumes an offline attack at 10 billion guesses per second, using the
"effective" entropy implied by the final score.

Every record stores a `scoring_version` (see `SCORING_VERSION` in `app/analyzer.py`).
Increase it whenever the scoring changes, so old and new results can be compared.

## Data collection and privacy

**What is stored** (table `assessments` in SQLite):

| Column            | Description                                         |
|-------------------|-----------------------------------------------------|
| `id`, `created_at`, `scoring_version` | Record metadata                 |
| `length`          | Password length                                     |
| `has_lower`, `has_upper`, `has_digit`, `has_symbol`, `has_other` | Character types used |
| `pool_size`, `entropy_bits` | Entropy estimate                          |
| `patterns`        | JSON array of detected pattern IDs                  |
| `answers`         | JSON object of yes/no answers, e.g. `{"contains_name": true}` |
| `score`, `label`  | Result                                              |
| `user_feedback`   | `accurate`, `too_high`, `too_low`, or `NULL`        |

**What is never stored:** the password itself or any hash of it. A hash of a short,
human-chosen password can be cracked, so storing one would be a risk. Gemma also receives
only the stored features and answers, never the password.

**Production note:** the password is sent to the server for analysis. Always serve the
app over HTTPS, and do not log request bodies.

### Using the data to improve accuracy

Each record links the user's answers to the result, and optionally to their feedback.
You can use this to tune the penalty weights. Some example queries:

```bash
sqlite3 data/assessments.db
```

```sql
-- How often each question is answered "yes"
SELECT key AS question, SUM(value) AS yes_count, COUNT(*) AS total
FROM assessments, json_each(assessments.answers)
GROUP BY key;

-- Where users think the score is wrong, by label
SELECT label, user_feedback, COUNT(*)
FROM assessments
WHERE user_feedback IS NOT NULL
GROUP BY label, user_feedback;

-- Average score for passwords that contain a name vs. those that don't
SELECT json_extract(answers, '$.contains_name') AS has_name, AVG(score)
FROM assessments
GROUP BY has_name;
```

A summary is also available at `GET /api/stats`.

## API

| Method | Path                                  | Description                         |
|--------|---------------------------------------|-------------------------------------|
| GET    | `/api/questions`                      | List the yes/no questions           |
| POST   | `/api/assess`                         | Analyze a password and store the result |
| POST   | `/api/assessments/{id}/advice`        | Get AI advice from Gemma (needs `GEMINI_API_KEY`) |
| POST   | `/api/assessments/{id}/feedback`      | Rate the result                     |
| GET    | `/api/stats`                          | Aggregated statistics               |

Interactive docs: <http://127.0.0.1:8000/docs>.

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/assess \
  -H "Content-Type: application/json" \
  -d '{"password": "Taro1998!", "answers": {"contains_name": true, "contains_birthday": true}}'
```

```json
{
  "id": 1,
  "score": 6,
  "label": "Very Weak",
  "crack_time_display": "less than a second",
  "issues": ["It contains something that looks like a year.", "..."],
  "tips": ["Avoid years. Attackers try 1900-2099 automatically.", "..."],
  "features": {"length": 9, "entropy_bits": 59.13, "patterns": ["year"], "...": "..."},
  "ai_advice_available": false
}
```

## Project structure

```
.
├── main.py              # Entry point: starts the Uvicorn server
├── app/
│   ├── main.py          # FastAPI app and API routes
│   ├── analyzer.py      # Feature extraction, pattern detection, scoring
│   ├── questions.py     # All questions, automatic checks, penalties, and advice
│   ├── db.py            # SQLite storage
│   └── advisor.py       # Optional Gemma advice
├── static/              # Frontend (index.html, app.js, style.css)
├── tests/               # pytest tests
├── .env.example
└── pyproject.toml
```

## Testing

```bash
uv run pytest
```

The tests cover pattern detection, scoring, the API, and a check that the
raw password never appears in the database.

## Changing questions or penalties

Edit [`app/questions.py`](app/questions.py):

- **Questions** (`QUESTIONS`): each has an `id`, the question `text`, a `penalty`,
  and a `tip`. The frontend loads questions from the API, so no frontend change is needed.
- **Automatic checks** (`AUTO_CHECKS`): you can change the `issue` text, `penalty`,
  and `tip` here. Adding a *new* automatic check also needs detection code in
  `detect_patterns()` in `app/analyzer.py`.

Increase `SCORING_VERSION` in `app/analyzer.py` afterwards.

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
   crack time, the issues found, concrete tips, and step-by-step changes that would raise
   the score (or a prompt to replace the password if attackers already know it).
4. *(Optional)* **Get AI advice** from Gemma, based on the analysis only (never the password).
5. *(Optional)* **Rate the result** ("Too low" / "Accurate" / "Too high"). This feedback is stored
   with the record and can be used to tune the scoring.

```
Browser ──POST /api/assess {password, answers}──▶ FastAPI
                                                   ├─ Have I Been Pwned: first 5 chars of SHA-1 only
                                                   ├─ analyzer: features + score (in memory)
                                                   └─ DB: features, answers, score   ← no password
Browser ◀────────────── score, label, tips ────────┘
```

## Tech stack

| Layer    | Technology                                   |
|----------|----------------------------------------------|
| Backend  | Python 3.12, FastAPI, Uvicorn                |
| Database | SQLite locally, PostgreSQL ([Neon](https://neon.tech)) in production |
| Frontend | Plain HTML, CSS, and JavaScript (no build)   |
| AI       | Gemma via the Gemini API (`google-genai`), optional |
| Breach check | [Have I Been Pwned](https://haveibeenpwned.com/Passwords) Pwned Passwords API (no key needed) |
| Hosting  | [Vercel](https://vercel.com) (Hobby plan), or Cloudflare Tunnel from your computer |
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
| `DATABASE_URL`   | *(unset)*               | PostgreSQL connection string. When set, it is used instead of SQLite |
| `DATABASE_PATH`  | `data/assessments.db`   | SQLite database file (used when `DATABASE_URL` is unset) |
| `ADMIN_TOKEN`    | *(unset)*               | Token for `GET /api/stats`. Stats are disabled when unset |
| `HOST`           | `127.0.0.1`             | Server host                                  |
| `PORT`           | `8000`                  | Server port                                  |
| `RELOAD`         | `false`                 | Auto-reload on code changes                  |
| `BREACH_CHECK`   | `true`                  | Set to `false` to skip the Have I Been Pwned check |

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
   | Found in a data breach | 100     | `Tr0ub4dor&3`    |
   | Common password        | 100     | `password`, `P@ssw0rd` |
   | Contains common password | 20    | `xxpassword99`, `summer1998` |
   | Keyboard pattern       | 15      | `qwer`, `asdf`   |
   | Sequence               | 10      | `abc`, `321`     |
   | Repeated characters    | 10      | `aaa`            |
   | Year                   | 10      | `1998`           |
   | Date                   | 10      | `0315` + a year  |
   | Letters only           | 10      | `sunflower`      |
   | Digits only            | 20      | `48291736`       |
   | Shorter than 8         | 20      | `a1!b`           |
   | All one case           | 10      | `sunflower99`, `HELLO!` |

   Common passwords come from the 10,000 most common passwords in
   [SecLists](https://github.com/danielmiessler/SecLists) (MIT license), stored in
   [`app/wordlists/common-passwords.txt`](app/wordlists/common-passwords.txt).
   Leet substitutions are undone before matching (`P@ssw0rd` → `password`).
   "Contains common password" only applies when the common password (5+ characters)
   makes up at least half of the password, so a passphrase such as
   `correcthorsebatterystaple` is not penalized for containing `horse`.

   "Found in a data breach" uses the [Have I Been Pwned](https://haveibeenpwned.com/Passwords)
   Pwned Passwords range API ([`app/breach.py`](app/breach.py)). Only the first 5 characters of
   the password's SHA-1 hash are sent, with response padding enabled; the match is done on the
   server. If the API is unreachable (3-second timeout), the check is skipped and the
   "data breach" question is scored as usual. When a breach is found, that question is skipped.

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
   | Appeared in a data breach                                         | 30*     |

   \* Skipped if the same weakness was already detected automatically, so it is not
   counted twice (see `overlaps` in `app/questions.py`): the sequence question when a
   sequence, keyboard pattern, or repeated characters were found, and the data breach
   question when Have I Been Pwned found the password.

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

### How to improve

The result lists changes that would raise the score, each with the score it would reach
(`suggest_improvements()` in `app/analyzer.py`). Every detected weakness has a short `fix`
in `app/questions.py`, such as "Remove the year" or "Mix upper and lower case".
The scores come from re-scoring the features as if the change were made: lengthening to
16 characters, adding character types, dropping a pattern, or answering "no" to a question.

Fixes are applied one at a time, always choosing the one that helps most next, so each step's
score includes the steps before it. Unclamped scores are compared, so the steps are still
ranked sensibly when the score is stuck at 0.

When the password is a common password or was found in a breach (automatically or by the
user's answer), no edits are suggested. The user is told to replace it instead.

The **Password Generator** page creates random-character passwords or passphrases of 4–10
words from the [EFF large word list](https://www.eff.org/dice)
([`static/wordlists/eff-large.txt`](static/wordlists/eff-large.txt), CC BY 3.0 US),
entirely in the browser with `crypto.getRandomValues`.

Every record stores a `scoring_version` (see `SCORING_VERSION` in `app/analyzer.py`).
Increase it whenever the scoring changes, so old and new results can be compared.

## Data collection and privacy

**What is stored** (table `assessments`, same schema in SQLite and PostgreSQL):

| Column            | Description                                         |
|-------------------|-----------------------------------------------------|
| `id`, `created_at`, `scoring_version` | Record metadata                 |
| `public_id`       | Random ID returned by the API (so records can't be enumerated) |
| `length`          | Password length                                     |
| `has_lower`, `has_upper`, `has_digit`, `has_symbol`, `has_other` | Character types used |
| `pool_size`, `entropy_bits` | Entropy estimate                          |
| `patterns`        | JSON array of detected pattern IDs                  |
| `answers`         | JSON object of yes/no answers, e.g. `{"contains_name": true}` |
| `score`, `label`  | Result                                              |
| `user_feedback`   | `accurate`, `too_high`, `too_low`, or `NULL`        |

**What is never stored:** the password itself or any hash of it. A hash of a short,
human-chosen password can be cracked, so storing one would be a risk. Gemma also receives
only the stored features and answers, never the password. Have I Been Pwned receives only
the first 5 characters of the SHA-1 hash, which matches hundreds of different passwords.

**Production note:** the password is sent to the server for analysis. Always serve the
app over HTTPS (Vercel does this automatically), and do not log request bodies.

### Using the data to improve accuracy

Each record links the user's answers to the result, and optionally to their feedback.
You can use this to tune the penalty weights. Some example queries:

```bash
sqlite3 data/assessments.db
```

These queries use SQLite syntax. On Neon, run SQL in the Neon console's SQL Editor,
and cast the JSON columns, e.g. `answers::jsonb ->> 'contains_name'`.

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

A summary is also available at `GET /api/stats` (requires `ADMIN_TOKEN`):

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://<your-app>.vercel.app/api/stats
```

## API

| Method | Path                                  | Description                         |
|--------|---------------------------------------|-------------------------------------|
| GET    | `/api/questions`                      | List the yes/no questions           |
| POST   | `/api/assess`                         | Analyze a password and store the result |
| POST   | `/api/assessments/{id}/advice`        | Get AI advice from Gemma (needs `GEMINI_API_KEY`) |
| POST   | `/api/assessments/{id}/feedback`      | Rate the result (once per assessment) |
| GET    | `/api/stats`                          | Aggregated statistics (needs `Authorization: Bearer <ADMIN_TOKEN>`) |

`{id}` is the random `id` returned by `/api/assess`.

**Rate limits** (per client IP, in memory): 30 assessments/min, 30 feedback/min,
5 AI advice/min, and 200 AI advice/hour in total across all users.
Exceeding a limit returns `429 Too Many Requests`.

Interactive docs: <http://127.0.0.1:8000/docs>.

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/assess \
  -H "Content-Type: application/json" \
  -d '{"password": "Taro1998!Kz", "answers": {"contains_name": true, "contains_birthday": true}}'
```

```json
{
  "id": "3f9c2a7e5b1d4c8e9a0b6d2f4e7c1a35",
  "score": 20,
  "label": "Weak",
  "crack_time_display": "less than a second",
  "issues": ["It contains something that looks like a year.", "..."],
  "tips": ["Avoid years. Attackers try 1900-2099 automatically.", "..."],
  "features": {"length": 11, "entropy_bits": 72.27, "patterns": ["year"], "breach_count": 0, "...": "..."},
  "improvements": [
    {"fix": "Remove your name or nickname", "score": 45},
    {"fix": "Remove your birth date or year", "score": 70},
    {"fix": "Make it at least 16 characters long", "score": 90},
    {"fix": "Remove the year", "score": 100}
  ],
  "replace_recommended": false,
  "ai_advice_available": false
}
```

- `features.breach_count`: times seen in breaches, or `null` if the check was skipped.
- `improvements`: step-by-step fixes; each `score` includes the steps before it.
- `replace_recommended`: `true` (with empty `improvements`) for common or breached
  passwords. For example, `Taro1998!` itself has been seen 100 times in breaches.

## Sharing from your computer (free): Cloudflare Tunnel + Neon

The quickest free way to share the app is to run it on your own computer and expose it
with a [Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/do-more-with-tunnels/trycloudflare/).
No Cloudflare account or credit card is needed. Data is stored in
[Neon](https://neon.tech)'s free PostgreSQL, so it is kept even when your computer is off.

### Setup (once)

1. Install cloudflared:

   ```bash
   brew install cloudflared
   ```

2. Create a free project on <https://neon.tech>, click **Connect**, and copy the connection string.
3. Add it to `.env` (never commit this file), together with an admin token for `/api/stats`:

   ```bash
   DATABASE_URL=postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
   ADMIN_TOKEN=any-long-random-string
   ```

### Start sharing

```bash
./share.sh
```

This starts the app and the tunnel. After a few seconds, a public URL like
`https://<random-words>.trycloudflare.com` appears in the output. Share that URL.
Press `Ctrl+C` to stop.

Notes:

- The app is only reachable while `share.sh` is running and your computer is awake
  and online. `share.sh` keeps a Mac awake with `caffeinate`, but closing the lid still
  puts it to sleep.
- **The URL changes every time you restart `share.sh`.** For a fixed URL, use a named
  tunnel with a Cloudflare account and your own domain, or deploy to Vercel (below).
- Quick tunnels have no uptime guarantee and are meant for demos and testing.

## Deploying to Vercel (always on)

The app runs on [Vercel](https://vercel.com)'s free Hobby plan, at a fixed
`https://<project>.vercel.app` URL. Data is stored in [Neon](https://neon.tech)'s free
PostgreSQL, because Vercel Functions have no persistent disk (SQLite cannot be used).
Both services can be used with a GitHub login and no credit card.

Vercel runs the whole FastAPI app as a single Vercel Function. The entrypoint is set
in `pyproject.toml` (`[tool.vercel] entrypoint = "app.main:app"`), because the root
`main.py` only starts Uvicorn for local use. Files under `static/` are served from
Vercel's CDN.

### 1. Create the database on Neon

1. Sign up at <https://neon.tech> and create a project in **AWS US East 2 (Ohio)**.
   `vercel.json` runs the Vercel Function in Cleveland (`cle1`), next to that region.
   If your Neon project is elsewhere, change `regions` in `vercel.json` to the
   [Vercel region](https://vercel.com/docs/regions) closest to it.
2. On the project dashboard, click **Connect** and copy the connection string.
   It looks like `postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require`.

The `assessments` table is created automatically the first time the app starts.

### 2. Deploy the app on Vercel

1. Open <https://vercel.com/new>, sign in with GitHub, and import this repository.
2. Leave the build settings as they are (Vercel detects FastAPI). Under
   **Environment Variables**, set:
   - `DATABASE_URL`: the Neon connection string from step 1 (required)
   - `GEMINI_API_KEY`: your Gemini API key (optional; leave it out to hide AI advice)
   - `ADMIN_TOKEN`: any long random string (optional; enables `/api/stats`)
3. Click **Deploy**. The first build takes a minute or two.
4. Open the URL Vercel shows (e.g. `https://securepass-ai.vercel.app`) and share it.

Every push to `main` deploys to that URL automatically, and every pull request gets its
own preview URL. After changing environment variables, redeploy for them to take effect.

### Free plan limits

- **Vercel:** the Hobby plan is for personal, non-commercial use. The function starts on
  demand, so the first request after a quiet period takes a second or two longer.
- **Neon:** 0.5 GB of storage on the free plan, which is enough for over a million
  assessments. The database also sleeps when idle and wakes in under a second.
- **Rate limits** are kept in memory per function instance, so on Vercel they are
  approximate: they reset when an instance stops, and each instance counts separately.
  On Vercel the client IP is taken from `X-Forwarded-For` (set by Vercel), and
  `CF-Connecting-IP` is ignored because clients could forge it there.

## Project structure

```
.
├── main.py              # Entry point: starts the Uvicorn server
├── app/
│   ├── main.py          # FastAPI app and API routes
│   ├── analyzer.py      # Feature extraction, pattern detection, scoring, improvements
│   ├── questions.py     # All questions, automatic checks, penalties, advice, and fixes
│   ├── breach.py        # Have I Been Pwned check (k-anonymity)
│   ├── wordlists/       # 10,000 most common passwords
│   ├── db.py            # Storage (SQLite or PostgreSQL)
│   ├── ratelimit.py     # In-memory rate limiting
│   └── advisor.py       # Optional Gemma advice
├── static/              # Frontend (index.html, app.js, style.css)
│   └── wordlists/       # EFF word list for the passphrase generator
├── tests/               # pytest tests
├── CLAUDE.md            # Working rules for Claude Code (README-first workflow)
├── .env.example
├── share.sh             # Share publicly via Cloudflare Tunnel
├── vercel.json          # Vercel Function region
└── pyproject.toml     # Dependencies, and the Vercel entrypoint ([tool.vercel])
```

## Testing

```bash
uv run pytest
```

The tests cover pattern detection, scoring, improvement suggestions, the breach check,
the API, and a check that the raw password never appears in the database.
They make no network calls: the breach check is mocked or disabled with `BREACH_CHECK=false`.

## Changing questions or penalties

Edit [`app/questions.py`](app/questions.py):

- **Questions** (`QUESTIONS`): each has an `id`, the question `text`, a `penalty`,
  a `tip`, a short `fix` shown in "How to improve", and optional `overlaps` (automatic
  checks that cover the same weakness). The frontend loads questions from the API,
  so no frontend change is needed.
- **Automatic checks** (`AUTO_CHECKS`): you can change the `issue` text, `penalty`,
  `tip`, and `fix` here. Adding a *new* automatic check also needs detection code in
  `detect_patterns()` in `app/analyzer.py`, and a what-if fix in `_available_fixes()`
  if it should appear in "How to improve".

Increase `SCORING_VERSION` in `app/analyzer.py` afterwards.

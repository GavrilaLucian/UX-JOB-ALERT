# ux-job-alerts

A personal, fully-automated "job radar" that checks daily for new UI/UX/Product
Design jobs in Romania and sends you a Telegram message — only for jobs you
haven't seen before. Runs entirely on GitHub Actions (free), no server and no
PC required.

## How it works, in one paragraph

Every day at 09:00 Europe/Bucharest, a GitHub Actions workflow checks a
watchlist of ~50 companies (via their official ATS APIs — Greenhouse/Lever/Ashby
— where known, or a scoped Google search otherwise), runs a set of discovery
searches to catch companies *not* on your list, scores every candidate first
with a free keyword filter and then (only for the survivors) with a cheap
Claude API call, drops anything you've already been notified about, and sends
one concise Telegram message with what's left. State (which jobs you've
already seen) is stored in `data/seen_jobs.json` and auto-committed back to
the repo after each run.

## What's actually verified vs. best-effort

I built and tested this project's logic (21 unit tests, all passing — dedup,
filtering, storage, Telegram formatting) and ran the full pipeline end-to-end
to confirm it doesn't crash and degrades gracefully when a source fails. I do
**not** have live access to Google/Telegram/Greenhouse/Lever/Ashby from the
environment I built this in, so two things need your verification after setup:

1. **ATS slugs in `config/companies.json`** — a handful of companies have a
   best-guess `ats`/`ats_slug` (e.g. `"ats": "greenhouse", "ats_slug": "uipath"`).
   These are educated guesses, not confirmed. Run `python -m src.tools.verify_ats_slugs`
   once you have internet access to find out which are real — wrong slugs just
   mean that company falls back silently to Google Search, nothing breaks.
2. **RSS feeds** for eJobs/BestJobs/Hipo — I didn't hardcode any, since their
   feed URLs change and I couldn't verify one live. `rss_feed_urls` in
   `config/settings.json` is empty; add any feed URLs you find working there.

Everything else (Greenhouse/Lever/Ashby API shapes, Telegram Bot API, Google
Custom Search API, GitHub Actions timezone scheduling) is built against the
real, documented, stable public APIs.

---

## 1. Files created

```
ux-job-alerts/
├── .github/workflows/check-jobs.yml   # daily schedule (09:00 Europe/Bucharest) + manual trigger
├── config/
│   ├── companies.json                 # your watchlist — edit freely, no code changes needed
│   └── settings.json                  # all tunable thresholds/keywords/queries
├── data/
│   └── seen_jobs.json                 # persistent "already notified" store (auto-committed by CI)
├── src/
│   ├── main.py                        # orchestrator / entry point
│   ├── config.py                      # loads settings.json + companies.json + env secrets
│   ├── models.py                      # Job data model
│   ├── dedup.py                       # URL normalization + robust job identity
│   ├── storage.py                     # seen-jobs persistence (JSON)
│   ├── filters.py                     # free keyword prefilter
│   ├── ai_filter.py                   # paid AI relevance scoring (Claude API)
│   ├── telegram.py                    # message formatting + sending
│   ├── sources/
│   │   ├── ats_greenhouse.py          # Greenhouse public API
│   │   ├── ats_lever.py               # Lever public API
│   │   ├── ats_ashby.py               # Ashby public API
│   │   ├── google_search.py           # Google Custom Search API (discovery + fallback)
│   │   ├── rss_source.py              # optional RSS feeds (off by default)
│   │   └── watchlist.py               # dispatches each watchlist company to the right source
│   └── tools/
│       └── verify_ats_slugs.py        # run locally to check which ATS slugs are real
├── tests/                             # 21 unit tests (pytest) — all passing
├── requirements.txt
└── .gitignore
```

## 2. Install & run locally (optional, for testing before you push to GitHub)

```bash
cd ux-job-alerts
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Create a .env file (never committed — it's in .gitignore) with your secrets:
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SEARCH_API_KEY=your_google_cse_api_key
SEARCH_ENGINE_ID=your_google_cse_engine_id
ANTHROPIC_API_KEY=your_anthropic_key
EOF

# Run the tests
pytest tests/ -v

# Run the full pipeline once
python -m src.main
```

Everything works with zero secrets configured too — sources that aren't
configured are skipped with a log line, nothing crashes (I verified this).

## 3. Telegram setup

1. Open Telegram, search for **@BotFather**, send `/newbot`, follow the
   prompts (choose a name and a username ending in `bot`).
2. BotFather gives you a token like `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxx` —
   this is your `TELEGRAM_BOT_TOKEN`.
3. Send any message (e.g. "hi") to your new bot from your own Telegram account
   — bots can't message you first, so this step is required.
4. Find your chat ID: open this URL in a browser (replace `<TOKEN>`):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Look for `"chat":{"id":123456789, ...}` in the response — that number is
   your `TELEGRAM_CHAT_ID`.
5. Add both as GitHub Secrets (see section 5 below).

## 4. Google Custom Search setup (used for discovery + companies without a known ATS)

Free tier: **100 queries/day**. This project's default config uses roughly
9 discovery queries + up to ~45 per-company fallback queries = ~54/day,
comfortably inside the free tier. If you add many more companies without an
ATS, watch the daily count in the GitHub Actions summary.

1. Go to https://programmablesearchengine.google.com/ → "Add" a new search
   engine → under "Sites to search" choose **"Search the entire web"**.
2. Copy the **Search engine ID** (this is `SEARCH_ENGINE_ID`).
3. Go to https://console.cloud.google.com/apis/credentials, create a project
   if you don't have one, enable the **"Custom Search API"**, then create an
   API key (this is `SEARCH_API_KEY`).

If you'd rather not set this up at all, the system still works using only the
ATS APIs (Greenhouse/Lever/Ashby) for whichever watchlist companies use those
— you just lose discovery mode and the fallback for other watchlist companies.

## 5. AI filtering setup (Claude API — optional but recommended)

The AI filter only runs on jobs that already passed the free keyword filter,
which keeps cost minimal.

1. Get an API key at https://console.anthropic.com/ — this is a **paid** key
   (no free tier), billed per token, and this is `ANTHROPIC_API_KEY`.
2. **Cost estimate**: each scored job costs roughly 250-400 input tokens and
   ~120 output tokens. Even on a busy day with 40 candidates scored, that's
   about 16,000 input + 4,800 output tokens — at current Claude Haiku pricing
   (check https://www.anthropic.com/pricing for the latest numbers) this is a
   fraction of a cent to a few cents per day, well under $1/month.
3. If you'd rather pay nothing, set `"enabled": false` under `ai_filter` in
   `config/settings.json` — the system will then rank jobs using only the
   free keyword prefilter score (less precise, especially for judging
   "is this Senior role actually reasonable" or "does remote really cover
   Romania", but still functional and free).

## 6. GitHub setup

```bash
cd ux-job-alerts
git add -A
git commit -m "Initial commit: ux-job-alerts"
# create a new repo on github.com first, then:
git remote add origin https://github.com/<your-username>/ux-job-alerts.git
git branch -M main
git push -u origin main
```

### GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**
in your repo, and add:

| Secret name | Required? | Where to get it |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Section 3 above |
| `TELEGRAM_CHAT_ID` | Yes | Section 3 above |
| `SEARCH_API_KEY` | Recommended | Section 4 above |
| `SEARCH_ENGINE_ID` | Recommended | Section 4 above |
| `ANTHROPIC_API_KEY` | Optional | Section 5 above |

Never commit these values into the repo itself — they only ever live in
GitHub Secrets and are injected as environment variables at run time.

### Enable the workflow / run it manually

1. Push the repo (above). GitHub Actions is enabled by default for new repos.
2. Go to the **Actions** tab → **Check UX/UI/Product Design Jobs** → **Run workflow**
   to trigger a manual test run any time (this uses `workflow_dispatch`).
3. The scheduled run fires automatically every day at **09:00 Europe/Bucharest**
   (GitHub Actions added native per-schedule timezone support in March 2026,
   so this is exact — no manual UTC conversion, and it stays correct across
   the DST switch).

⚠️ Note: GitHub disables the `schedule` trigger automatically after **60 days
of repository inactivity** (no commits). The daily auto-commit of
`data/seen_jobs.json` on days with new jobs counts as activity, but on a long
stretch of zero new jobs you might see nothing committed — if the schedule
ever silently stops firing, just push any commit (or re-run manually) to
reactivate it.

## 7. How the daily check works, step by step

1. **Watchlist check** — for each of the ~53 tracked companies: if it has a
   known ATS (Greenhouse/Lever/Ashby), query that company's public job-board
   API directly (fast, free, robust, no scraping). Otherwise, run one scoped
   Google search for that company's design job postings.
2. **Discovery search** — run ~9 broad Google searches ("UI Designer Romania",
   "Product Designer Bucharest", etc.) to catch companies not on your list.
3. **Cross-source de-duplication** — the same role found on LinkedIn *and* a
   company's career page is collapsed into one job, preferring the official
   source's URL.
4. **Keyword prefilter** (free) — hard-excludes Lead/Staff/Principal/Director/
   Manager titles and pure branding/marketing/motion design roles (with an
   exception for "Visual Designer" roles that are clearly digital-product
   work), and scores everything else on role/location/seniority fit.
5. **AI filter** (only for prefilter survivors, minimizes cost) — a Claude
   Haiku call scores 0-100 with the same rules applied more precisely
   (e.g. judging whether a "Senior" role's requirements are actually
   reasonable, or whether "Remote" really covers Romania).
6. **Threshold** — only jobs scoring **60+** (configurable) make it through.
7. **New-jobs check** — compares against `data/seen_jobs.json`; only jobs
   never seen before are notified.
8. **Telegram notification** — one concise message (or a few, if there are
   many jobs), grouped into watchlist-company jobs and a 🆕 NEW COMPANY
   section for relevant jobs from companies not on your list.
9. **State is saved** — `data/seen_jobs.json` is updated and auto-committed
   by the workflow so the next run remembers what's already been sent.
10. **GitHub Actions summary** — every run prints a summary (sources checked,
    jobs found, new jobs, relevant jobs, notifications sent, errors) visible
    on the Actions run page.

## 8. Configuring without touching code

Everything you're likely to want to change lives in two JSON files:

- **`config/companies.json`** — add/remove companies to track. Each entry:
  `{"name": "...", "careers_url": "...", "ats": "greenhouse|lever|ashby|null", "ats_slug": "..."}`.
  Leave `ats`/`ats_slug` as `null` if you don't know it — Google Search
  fallback covers it (see also `src/tools/verify_ats_slugs.py`).
- **`config/settings.json`** — job title keywords, excluded keywords,
  location keywords, `relevance_threshold` (default 60), max jobs per
  Telegram message, recency windows, discovery search queries, and the AI
  filter's model/threshold/enabled flag.

## 9. Known limitations

- **ATS slugs are best-effort** for several watchlist companies (see section
  "What's actually verified" above) — run `verify_ats_slugs.py` to confirm.
- **Google Custom Search free tier is 100 queries/day.** If you add many more
  watchlist companies without a known ATS, you may need to either add a
  billing method on the Google Cloud project (pay-as-you-go beyond 100/day)
  or reduce `per_company_fallback_queries_enabled` usage.
- **"Published in the last 24h" filtering is best-effort.** Greenhouse/Lever/
  Ashby give reliable timestamps; Google search results usually don't carry a
  reliable publish date. The system compensates by relying on the seen-jobs
  store (so you're never re-notified for the same posting) rather than a
  strict recency cutoff for search-sourced jobs.
- **LinkedIn isn't queried directly.** LinkedIn doesn't offer a public,
  ToS-compliant search API for this use case, and scraping it would violate
  their Terms of Service and break unpredictably (also explicitly against
  your brief). LinkedIn postings that also appear in Google's index will
  still surface through discovery search.
- **RSS feeds for eJobs/BestJobs/Hipo are opt-in and empty by default** — see
  section "What's actually verified" above.
- **No CAPTCHA/anti-bot bypass, no login-walled sources** — by design, per
  your brief.

# London Graduate Radar

An automated job-search dashboard for London graduate schemes, Summer 2027 internships and entry-level roles. A GitHub Actions workflow runs every two hours, discovers and re-verifies vacancies, scores them against the candidate profile from the 10 tailored CVs, saves everything to `data/roles.json`, republishes the dashboard to GitHub Pages and creates Gmail **drafts** (never sends) when something important changes.

**Dashboard:** https://milanspurs.github.io/london-job-dashboard/

---

## How a run works

```
schedule (every 2h) ─► jobsearch/run.py
   1. Adzuna + Reed APIs        rotating plan of ~190 queries (12 categories × title variants × grad/intern/entry)
   2. New employers queued      every employer seen in aggregator results joins the probe queue
   3. Board discovery           probes queued employers for public Greenhouse / Lever / Ashby boards
   4. Employer boards           checks up to 60 boards (least-recently-checked first) — official postings
   5. Evaluate                  London check → exclusions → type → category → eligibility → dates → fit → CV
   6. Merge + dedupe            one record per company+role across all sources; official data wins
   7. Re-verify                 Reed detail checks; employer-board absence tracking
   8. Recalculate fit           every stored vacancy is re-scored from its saved advert text
   9. Status + change detection new / opened / closed / deadline moved → data/events/YYYY-MM.jsonl
  10. Gmail drafts              capped, deduplicated, priority-ordered
  11. Save (atomic) → commit data/ → build_dashboard.py → deploy to Pages
```

| Module | Responsibility |
|---|---|
| `jobsearch/config.py` | Profile, categories/tiers, CV mapping, query plan, location lists, exclusions, limits |
| `jobsearch/http.py` | Timeouts, retries with backoff, per-host rate limits, `FetchResult` (failure ≠ closed) |
| `jobsearch/sources/aggregators.py` | Adzuna and Reed connectors (official APIs) |
| `jobsearch/sources/ats.py` | Greenhouse, Lever, Ashby, SmartRecruiters board APIs + employer probing |
| `jobsearch/sources/registry.py` | Employer board registry, probe queue, rotation |
| `jobsearch/filters.py` | London/commuter/remote classification, exclusions, experience limits |
| `jobsearch/classify.py` | Category, opportunity type, work arrangement, cycle, start date |
| `jobsearch/eligibility.py` | Graduation years, master's/final-year, return-to-study, degree, tech, right-to-work |
| `jobsearch/dates.py` | Deadline/opening extraction with Confirmed / Indicative / Unconfirmed |
| `jobsearch/scoring.py` | Fit 1–5, reasons, gaps, recommended CV |
| `jobsearch/merge.py` | Deduplication and merging; field history |
| `jobsearch/status.py` | Open / Opens Soon / Verify / Watch / Closed rules |
| `jobsearch/changes.py` | Change detection and closing-soon list |
| `jobsearch/alerts.py` | Gmail drafts (`python -m jobsearch.alerts` makes a test draft) |
| `jobsearch/tracker.py` | Optional read-only access to the private tracker (suppresses alerts for applied roles) |
| `jobsearch/ai.py` | Optional, capped AI eligibility check (off by default) |
| `jobsearch/store.py` | Atomic JSON writes, backups, validation, event log |
| `build_dashboard.py` + `dashboard/template.html` | Self-contained dark dashboard |

## Sources — what's automated and what isn't

| Source | Access | Notes |
|---|---|---|
| **Adzuna** | Official free API (key) | Broad UK aggregator (includes many Indeed-syndicated and employer ads). Free tier ≈ 25 calls/min, ~2,500/month; the job tracks monthly usage and caps itself (`ADZUNA_CALLS_PER_RUN`, default 6 → ~2,200/month at 12 runs/day; a hard monthly cap of 2,400 stops it before the limit). |
| **Reed** | Official free API (key) | Search + per-vacancy re-verification. |
| **Greenhouse / Lever / Ashby** | Public employer job-board APIs (no key) | The employer's own postings: used for confirmed dates and closures. Registry grows automatically by probing employers found elsewhere. |
| **SmartRecruiters** | Public postings API | Supported when a board is added to `data/registry.json`. |
| Indeed, LinkedIn, Bright Network, targetjobs, Prospects, Gradcracker, RateMyPlacement, eFinancialCareers, Civil Service Jobs | **No permitted automated access** | Not scraped. Listed on the dashboard as one-click manual checks. |

Big banks and Big Four firms mostly use Workday/Oracle careers portals with no public API; their roles reach the dashboard through Adzuna/Reed when advertised there. If you find an employer on Greenhouse/Lever/Ashby, add it — see *Maintenance*.

## Rules that keep the data honest

* **Never invented:** deadlines, salaries (Adzuna's *predicted* salaries are discarded), eligibility. Unknown fields say "Not stated".
* **Date confidence:** *Confirmed* = stated with a year in the employer's own current UK/London posting; *Indicative* = aggregator advert or advert-expiry date, or year inferred; *Unconfirmed* = none. Rolling roles have no deadline. Dates earlier than the posting date (previous cycle) are ignored. Only London/UK-located postings are processed, so overseas cycles can't leak in.
* **Closing:** only on positive evidence — confirmed deadline passed; removed from the employer's board on two successful checks; Reed reports the job gone; aggregator advert past expiry and no longer listed. A timeout, 403 or 5xx **never** closes a role (it increments `verify_failures` → status *Verify*).
* **Location:** Greater London (boroughs, City, Canary Wharf…), commuter belt (labelled), UK-remote (labelled). Everything else is dropped.
* **Exclusions:** recruitment/talent/headhunting titles, commission-only/door-to-door/telesales, estate agency, hospitality/retail management, call centres, unpaid roles, senior/lead/manager titles, > 2 years' experience, software/data engineering. An analyst job advertised *by* an agency is kept.
* **Internship eligibility:** flags graduation-year mismatches, penultimate-year-only schemes and mandatory return to university (you finish your MSc in 2027). Uncertain cases are "Check eligibility", not assumed.

## Application tracker and privacy

GitHub Pages sites are public, so **nothing personal is published**: `roles.json` and the dashboard contain vacancy data only. The page never writes to `roles.json`.

Statuses (*Not Applied → Offer/Rejected*) and notes are saved:

1. **On the device** automatically (browser storage), and
2. **Optionally synced across laptop and phone** via a **private** GitHub repository you own:
   * create a private repo, e.g. `job-tracker-private`
   * create a fine-grained token: GitHub → Settings → Developer settings → Fine-grained tokens → *Only select repositories* → that repo → *Contents: Read and write*
   * on the dashboard click **Tracker sync**, enter `owner/job-tracker-private` and the token, on each device.

   The token is stored only in that browser and sent only to `api.github.com`. Anyone with access to your unlocked browser could read it — give it access to the tracker repo only, and set an expiry.
3. Optional: add secrets `TRACKER_REPO` and `TRACKER_TOKEN` (a *read-only* token for the same repo) so the scheduled job stops alerting about roles you've applied to. It only reads the tracker and never copies it anywhere.

Export/Import JSON buttons are in the sync dialog as a backup.

## Setup (one-off)

### 1. Secrets — repo Settings → Secrets and variables → Actions

| Secret | Required | |
|---|---|---|
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | yes | developer.adzuna.com |
| `REED_API_KEY` | yes | reed.co.uk/developers/jobseeker |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` | for alerts | see below |
| `GMAIL_TO` | optional | pre-fills the draft's To field |
| `TRACKER_REPO`, `TRACKER_TOKEN` | optional | alert suppression |
| `ANTHROPIC_API_KEY` | optional | only with variable `AI_MAX_CALLS_PER_RUN` > 0 |

Optional *variables* (same page, Variables tab): `ADZUNA_CALLS_PER_RUN`, `REED_CALLS_PER_RUN`, `AI_MAX_CALLS_PER_RUN`.

### 2. Pages — Settings → Pages → Source: **GitHub Actions**

### 3. Gmail drafts (OAuth)

1. https://console.cloud.google.com → create project → *APIs & Services → Library* → enable **Gmail API**.
2. *OAuth consent screen*: External; add your Gmail as a test user; add scope `.../auth/gmail.compose`. Then set **Publishing status → In production** — in *Testing* mode Google expires refresh tokens after 7 days. (You'll see "Google hasn't verified this app" when authorising; it's your own app — choose *Advanced → Go to …*.)
3. *Credentials → Create credentials → OAuth client ID → Desktop app* → download the JSON.
4. On your computer: `pip install google-auth-oauthlib` then `python scripts/gmail_auth.py client_secret.json` and paste the three printed values into secrets. Delete the downloaded JSON afterwards.
5. Actions → *Job search update* → *Run workflow* → tick **test_gmail**. A "[Job dashboard] Gmail test draft" should appear in Gmail Drafts.

`gmail.compose` technically allows sending (Google has no drafts-only scope); this code only calls `users.drafts.create`.

### Alert rules

Drafts are created (max 8 per run, highest priority first) for: confirmed deadlines ≤ 14 days away (fit ≥ 3); confirmed deadlines that move earlier; newly opened graduate schemes/internships (fit ≥ 3); new vacancies with fit ≥ 4. Each (alert type, role, deadline) is drafted once. Indicative/unconfirmed dates never trigger deadline alerts. Roles marked ineligible or already applied (if tracker secrets set) are skipped. The very first run (empty database) creates no "new" alerts, to avoid a flood.

## Optional AI eligibility check (off by default)

Set secret `ANTHROPIC_API_KEY` **and** variable `AI_MAX_CALLS_PER_RUN` (e.g. `5`). It reviews only new, full-text adverts whose eligibility the rules couldn't settle, and can only refine eligibility fields. Cost is bounded by the cap (≤ 60 calls/day at 5 per run). With the variable at 0 nothing is called.

## Maintenance

* **Run now:** Actions → *Job search update* → *Run workflow*.
* **Add an employer board:** edit `data/registry.json` → `boards`, e.g. `"greenhouse:examplefirm": {"platform": "greenhouse", "slug": "examplefirm", "company": "Example Firm", "status": "active", "fail_count": 0, "missing_count": 0, "last_checked": null, "last_ok": null}`. Or add the company name to `SEED_EMPLOYERS` in `jobsearch/sources/registry.py` to have it probed.
* **Tune searches/categories/exclusions/scoring:** `jobsearch/config.py`, `jobsearch/scoring.py`. Stored roles are re-scored on the next run.
* **Tests:** `python -m pytest` (or `python -m unittest`) — they run automatically on every code push.
* **History:** every run is a commit to `data/`; `data/events/` holds a monthly log of new/changed/closed roles.

## Troubleshooting

| Symptom | Check |
|---|---|
| "Searched N hours ago" turns amber/red | Actions tab for failed runs. GitHub delays schedules under load; persistent gaps → re-enable the workflow (GitHub disables schedules after 60 days with no repository activity — data commits normally prevent this). |
| Source shows *Failed* in Search health | Error text is in the table. 401/403 → key wrong/expired. 429 → lower `*_CALLS_PER_RUN`. |
| Adzuna "Monthly call cap reached" | Expected near month end; resumes on the 1st. |
| No Gmail drafts | Health panel shows "not configured" or errors; run with *test_gmail*. `invalid_grant` → refresh token expired/revoked: redo step 3.4 (and make sure the consent screen is *In production*). |
| Tracker sync failed | Token expired or lacks *Contents: Read and write* on the private repo; statuses remain on the device meanwhile. |
| Run failed but site still updated | By design: the dashboard republishes last good data and the run is marked failed in Actions. |
| `roles.json` corrupted | The loader falls back to `roles.bak.json`; otherwise `git checkout <earlier commit> -- data/roles.json`. |

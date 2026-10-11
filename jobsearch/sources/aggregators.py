"""Aggregator connectors using official, key-based APIs: Adzuna and Reed.

Both are free. Keys are read from environment variables (GitHub Actions
secrets); if a key is missing the source is recorded as "not configured".
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from ..config import SETTINGS
from ..http import Http
from ..models import RawJob, strip_html
from .base import SourceReport

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adzuna  (https://developer.adzuna.com/docs/search)
# ---------------------------------------------------------------------------
ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/gb/search/{page}"
_SENIORITY_WORDS = {"graduate", "junior", "entry", "level", "trainee", "scheme", "programme", "intern", "internship"}


def adzuna_search(http: Http, queries: list[tuple[str, str, str]], usage: dict) -> tuple[list[RawJob], SourceReport]:
    rep = SourceReport("Adzuna", "aggregator")
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        rep.ok = False
        rep.note = "Not configured (add ADZUNA_APP_ID and ADZUNA_APP_KEY secrets)"
        return [], rep

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    used = usage.setdefault("adzuna", {}).get(month, 0)
    budget = min(SETTINGS["adzuna_calls_per_run"], max(0, SETTINGS["adzuna_monthly_cap"] - used))
    if budget == 0:
        rep.note = f"Monthly call cap reached ({used})"
        return [], rep

    jobs: list[RawJob] = []
    per_query: list[str] = []
    for q, hint, _cat in queries[:budget]:
        # Adzuna's `what` needs every word to match, which made multi-word queries
        # ("graduate risk analyst") far too narrow. Keep the role words in `what`
        # and require at least one seniority word via `what_or`.
        words = q.split()
        core = [w for w in words if w.lower() not in _SENIORITY_WORDS]
        params = {
            "app_id": app_id, "app_key": app_key, "what": " ".join(core) or q, "where": "London",
            "distance": round(SETTINGS["search_radius_miles"] * 1.609), "results_per_page": 50,
            "max_days_old": SETTINGS["max_days_old"], "sort_by": "date", "content-type": "application/json",
        }
        if len(core) < len(words):
            params["what_or"] = "graduate graduates junior trainee entry intern internship placement"
        res = http.get(ADZUNA_URL.format(page=1), params=params)
        rep.calls += 1
        used += 1
        if not res.ok or res.status != 200:
            rep.fail(f"'{q}': {res.error or res.status}")
            continue
        data = res.data or {}
        results = data.get("results", []) if isinstance(data, dict) else []
        per_query.append(f"{q}: {len(results)}/{data.get('count', '?') if isinstance(data, dict) else '?'}")
        if isinstance(data, dict) and not results and set(data) - {"results", "count", "mean", "__CLASS__"}:
            rep.fail(f"'{q}': unexpected response keys {sorted(data)[:5]}")
        for r in results:
            company = (r.get("company") or {}).get("display_name") or ""
            loc = r.get("location") or {}
            area = loc.get("area") or []
            jobs.append(RawJob(
                source="adzuna", source_id=str(r.get("id")), company=company,
                title=strip_html(r.get("title")), location=loc.get("display_name") or ", ".join(area),
                url=r.get("redirect_url") or "", description=strip_html(r.get("description")),
                posted=r.get("created"), salary_min=r.get("salary_min"), salary_max=r.get("salary_max"),
                salary_predicted=str(r.get("salary_is_predicted")) == "1",
                employment_type=" ".join(filter(None, [r.get("contract_time"), r.get("contract_type")])),
                query_hint=hint, extra={"area": area, "category": (r.get("category") or {}).get("label")},
            ))
    usage["adzuna"][month] = used
    rep.note = f"{used} calls this month; per query (returned/total): " + "; ".join(per_query)
    rep.jobs_found = len(jobs)
    rep.ok = rep.calls > rep.failures
    return jobs, rep


# ---------------------------------------------------------------------------
# Reed  (https://www.reed.co.uk/developers/jobseeker)
# ---------------------------------------------------------------------------
REED_SEARCH = "https://www.reed.co.uk/api/1.0/search"
REED_DETAIL = "https://www.reed.co.uk/api/1.0/jobs/{id}"


def _reed_date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _reed_job(r: dict, hint: str, full: bool = False) -> RawJob:
    return RawJob(
        source="reed", source_id=str(r.get("jobId")), company=r.get("employerName") or "",
        title=r.get("jobTitle") or "", location=r.get("locationName") or "",
        url=r.get("externalUrl") or r.get("jobUrl") or f"https://www.reed.co.uk/jobs/{r.get('jobId')}",
        description=strip_html(r.get("jobDescription")), posted=_reed_date(r.get("date") or r.get("datePosted")),
        salary_min=r.get("minimumSalary"), salary_max=r.get("maximumSalary"),
        salary_text=r.get("salary") or "", expiry=_reed_date(r.get("expirationDate")),
        employment_type=" ".join(filter(None, [r.get("contractType"), r.get("jobType")])) if full else "",
        query_hint=hint, full_text=full,
        extra={"reed_url": r.get("jobUrl"), "employer_id": r.get("employerId")},
    )


def reed_search(http: Http, queries: list[tuple[str, str, str]]) -> tuple[list[RawJob], SourceReport]:
    rep = SourceReport("Reed", "aggregator")
    key = os.environ.get("REED_API_KEY")
    if not key:
        rep.ok = False
        rep.note = "Not configured (add REED_API_KEY secret)"
        return [], rep
    jobs: list[RawJob] = []
    for q, hint, _cat in queries[: SETTINGS["reed_calls_per_run"]]:
        params = {"keywords": q, "locationName": "London", "distanceFromLocation": SETTINGS["search_radius_miles"],
                  "resultsToTake": 100}
        if hint == "grad":
            params["graduate"] = "true"
        res = http.get(REED_SEARCH, params=params, auth=(key, ""))
        rep.calls += 1
        if not res.ok or res.status != 200:
            rep.fail(f"'{q}': {res.error or res.status}")
            continue
        for r in (res.data or {}).get("results", []):
            jobs.append(_reed_job(r, hint))
    rep.jobs_found = len(jobs)
    rep.ok = rep.calls > rep.failures
    return jobs, rep


def reed_detail(http: Http, job_id: str) -> tuple[str, RawJob | None]:
    """Re-check one Reed vacancy. Returns (state, job) where state is
    'live' | 'gone' | 'unknown'. 'unknown' (any failure) never closes a role."""
    key = os.environ.get("REED_API_KEY")
    if not key:
        return "unknown", None
    res = http.get(REED_DETAIL.format(id=job_id), auth=(key, ""))
    if res.not_found:
        return "gone", None
    if not res.ok or res.status != 200 or not isinstance(res.data, dict):
        return "unknown", None
    d = res.data
    if not d.get("jobId"):
        return "gone", None
    job = _reed_job(d, "", full=True)
    return "live", job

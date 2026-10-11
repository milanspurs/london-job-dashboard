"""Employer applicant-tracking-system (ATS) connectors.

Greenhouse, Lever, Ashby and SmartRecruiters each publish an official,
unauthenticated job-board API intended for embedding an employer's open roles
on other sites. These are the employer's own postings, so they count as the
official vacancy source for verification and dates.
"""
from __future__ import annotations

import logging
import re

from ..http import FetchResult, Http
from ..models import RawJob, norm_company, strip_html

log = logging.getLogger(__name__)

PLATFORMS = ("greenhouse", "lever", "ashby", "smartrecruiters")


def board_url(platform: str, slug: str) -> str:
    return {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
        "smartrecruiters": f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?country=gb&limit=100",
    }[platform]


def _parse_greenhouse(slug: str, company: str, data: dict) -> list[RawJob]:
    out = []
    for j in data.get("jobs", []):
        offices = ", ".join(o.get("name", "") for o in j.get("offices") or [])
        loc = (j.get("location") or {}).get("name") or offices
        out.append(RawJob(
            source=f"greenhouse:{slug}", source_id=str(j.get("id")), company=company, title=j.get("title") or "",
            location=f"{loc} {offices}".strip(), url=j.get("absolute_url") or "", description=strip_html(j.get("content")),
            posted=(j.get("first_published") or j.get("updated_at") or "")[:10] or None, official=True, full_text=True,
        ))
    return out


def _parse_lever(slug: str, company: str, data: list) -> list[RawJob]:
    out = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        locs = cats.get("allLocations") or [cats.get("location") or ""]
        desc = " ".join(filter(None, [j.get("descriptionPlain"), j.get("additionalPlain")] +
                                [strip_html(l.get("content")) + " " + (l.get("text") or "") for l in j.get("lists") or []]))
        sal = j.get("salaryRange") or {}
        created = j.get("createdAt")
        out.append(RawJob(
            source=f"lever:{slug}", source_id=str(j.get("id")), company=company, title=j.get("text") or "",
            location=", ".join(filter(None, locs)), url=j.get("hostedUrl") or j.get("applyUrl") or "", description=desc,
            posted=_ms_to_date(created), workplace=j.get("workplaceType") or "", employment_type=cats.get("commitment") or "",
            salary_min=sal.get("min"), salary_max=sal.get("max"),
            salary_text=f"{sal.get('currency','')} {sal.get('min','')}–{sal.get('max','')} {sal.get('interval','')}".strip() if sal else "",
            official=True, full_text=True,
        ))
    return out


def _parse_ashby(slug: str, company: str, data: dict) -> list[RawJob]:
    out = []
    for j in data.get("jobs", []) if isinstance(data, dict) else []:
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        out.append(RawJob(
            source=f"ashby:{slug}", source_id=str(j.get("id") or j.get("jobUrl")), company=company, title=j.get("title") or "",
            location=", ".join(filter(None, locs)), url=j.get("jobUrl") or j.get("applyUrl") or "",
            description=j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")),
            posted=(j.get("publishedAt") or "")[:10] or None, remote_flag=j.get("isRemote"),
            workplace=j.get("workplaceType") or "", employment_type=j.get("employmentType") or "",
            salary_text=comp, official=True, full_text=True,
        ))
    return out


def _parse_smartrecruiters(slug: str, company: str, data: dict) -> list[RawJob]:
    out = []
    for j in data.get("content", []) if isinstance(data, dict) else []:
        loc = j.get("location") or {}
        out.append(RawJob(
            source=f"smartrecruiters:{slug}", source_id=str(j.get("id")),
            company=(j.get("company") or {}).get("name") or company, title=j.get("name") or "",
            location=", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")])),
            url=f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}", description="",
            posted=(j.get("releasedDate") or "")[:10] or None, remote_flag=loc.get("remote"),
            employment_type=(j.get("typeOfEmployment") or {}).get("label") or "", official=True, full_text=False,
            extra={"detail_ref": j.get("ref")},
        ))
    return out


def _ms_to_date(ms) -> str | None:
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return None


PARSERS = {"greenhouse": _parse_greenhouse, "lever": _parse_lever, "ashby": _parse_ashby,
           "smartrecruiters": _parse_smartrecruiters}


def fetch_board(http: Http, platform: str, slug: str, company: str) -> tuple[str, list[RawJob], FetchResult]:
    """Returns (state, jobs, result). state: 'ok' | 'missing' (board does not exist) | 'error'."""
    res = http.get(board_url(platform, slug))
    if res.not_found:
        return "missing", [], res
    if not res.ok or res.status != 200 or res.data is None:
        return "error", [], res
    if platform == "lever" and isinstance(res.data, dict) and res.data.get("ok") is False:
        return "missing", [], res
    try:
        jobs = PARSERS[platform](slug, company, res.data)
    except Exception as e:  # malformed payload: treat as an error, never as "no jobs"
        res.error = f"parse error: {e}"
        return "error", [], res
    return "ok", jobs, res


def smartrecruiters_detail(http: Http, ref: str) -> str:
    res = http.get(ref)
    if not res.ok or not isinstance(res.data, dict):
        return ""
    secs = ((res.data.get("jobAd") or {}).get("sections") or {})
    return " ".join(strip_html((secs.get(k) or {}).get("text")) for k in
                    ("companyDescription", "jobDescription", "qualifications", "additionalInformation"))


# ---------------------------------------------------------------------------
# Probing: find whether a newly seen employer has a public board
# ---------------------------------------------------------------------------
def slug_candidates(company: str) -> list[str]:
    base = norm_company(company)
    if not base:
        return []
    words = base.split()
    cands = ["".join(words), "-".join(words)]
    if len(words) > 1:
        cands.append(words[0])
    seen, out = set(), []
    for c in cands:
        c = re.sub(r"[^a-z0-9-]", "", c)
        if len(c) >= 3 and c not in seen:
            seen.add(c)
            out.append(c)
    return out[:3]


def _name_matches(company: str, board_name: str) -> bool:
    a, b = norm_company(company), norm_company(board_name)
    return bool(a and b) and (a == b or a in b or b in a)


def probe_company(http: Http, company: str) -> list[dict]:
    """Try each platform/slug candidate. Returns boards found (possibly empty)."""
    found = []
    cands = slug_candidates(company)
    multiword = len(norm_company(company).split()) > 1
    for i, slug in enumerate(cands):
        for platform in ("greenhouse", "lever", "ashby"):
            if any(f["platform"] == platform for f in found):
                continue
            # The first-word-only guess is name-verified on Greenhouse; Lever/Ashby
            # expose no board name, so only full-name slugs are tried there.
            if platform != "greenhouse" and multiword and i == len(cands) - 1 and len(cands) == 3:
                continue
            if platform == "greenhouse":
                res = http.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}")
                if res.ok and res.status == 200 and isinstance(res.data, dict):
                    if _name_matches(company, res.data.get("name", "")):
                        found.append({"platform": platform, "slug": slug})
                continue
            res = http.get(board_url(platform, slug))
            if not (res.ok and res.status == 200):
                continue
            if platform == "lever" and isinstance(res.data, list) and res.data:
                found.append({"platform": platform, "slug": slug})
            elif platform == "ashby" and isinstance(res.data, dict) and res.data.get("jobs") is not None:
                # Ashby returns the org name in some responses; require jobs list to exist
                found.append({"platform": platform, "slug": slug})
    return found

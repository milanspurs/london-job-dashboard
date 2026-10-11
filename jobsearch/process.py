"""Turn a RawJob from any source into a scored, classified vacancy record."""
from __future__ import annotations

from .classify import categorise, entry_level_evidence, opportunity_type, recruitment_cycle, start_date, work_arrangement
from .config import CATEGORIES
from .dates import extract_dates
from .eligibility import assess
from .filters import classify_location, exclusion_reason, required_experience_years
from .models import RawJob, now_iso
from .scoring import recommend_cv, score


def format_salary(job: RawJob) -> str:
    if job.salary_predicted:
        return ""  # Adzuna estimates are not published salaries
    if job.salary_text and any(c.isdigit() for c in job.salary_text):
        return job.salary_text.strip()
    lo, hi = job.salary_min, job.salary_max
    if lo and hi and lo != hi:
        return f"£{lo:,.0f} – £{hi:,.0f}"
    if lo or hi:
        return f"£{(lo or hi):,.0f}"
    return ""


def evaluate(job: RawJob) -> tuple[dict | None, str | None]:
    """Returns (record, None) for a relevant London vacancy, or (None, reason) if rejected."""
    if not job.title or not job.company:
        return None, "missing title/company"
    loc_class, loc_conf = classify_location(job)
    if loc_class == "Excluded":
        return None, f"location not London ({job.location[:60]})"
    reason = exclusion_reason(job)
    if reason:
        return None, reason
    opp = opportunity_type(job)
    if opp == "Insight Programme":
        return None, "insight/spring week (aimed at earlier-year students)"
    entry_signal = None
    if opp == "Entry-Level":
        entry_signal = entry_level_evidence(job)
        if not entry_signal:
            return None, "not clearly entry-level (no junior/graduate signal)"

    text = job.description or ""
    cat, _hits = categorise(job)
    elig = assess(f"{job.title}\n{text}", opp, job.full_text)
    exp_years = required_experience_years(text)
    fit, why, gaps = score(cat=cat, title=job.title, text=text, opp_type=opp, elig=elig, location_class=loc_class,
                           experience_years=exp_years, full_text=job.full_text)
    dates = extract_dates(text, official=job.official, full_text=job.full_text, posted=job.posted, expiry=job.expiry)
    if entry_signal and entry_signal.startswith("aggregator"):
        gaps.append("Seniority not stated in the advert snippet — check it's entry-level")
    missing = list(dict.fromkeys(gaps + [i for i in elig["issues"] if i not in gaps]))

    ts = now_iso()
    rec = {
        "id": job.id,
        "company": job.company.strip(),
        "title": job.title.strip(),
        "category": cat,
        "category_label": CATEGORIES[cat]["label"],
        "tier": CATEGORIES[cat]["tier"],
        "type": opp,
        "location": job.location.strip() or "London (from London-area search)",
        "location_class": loc_class,
        "location_confidence": loc_conf,
        "work_arrangement": work_arrangement(job),
        "start_date": start_date(job),
        "opening_date": dates["opening_date"],
        "opening_confidence": dates["opening_confidence"],
        "deadline": None if dates["rolling"] and dates["deadline_confidence"] != "Confirmed" else dates["deadline"],
        "deadline_confidence": dates["deadline_confidence"] if not (dates["rolling"] and dates["deadline_confidence"] != "Confirmed") else "Unconfirmed",
        "deadline_evidence": dates["deadline_evidence"],
        "rolling": dates["rolling"],
        "cycle": recruitment_cycle(job, opp),
        "fit": fit,
        "why": why,
        "missing": missing[:6],
        "eligibility": elig,
        "experience_years": exp_years,
        "salary": format_salary(job),
        "employment_type": job.employment_type,
        "apply_url": job.url,
        "official": job.official,
        "official_source": job.source.split(":")[0] if job.official else "",
        "recommended_cv": recommend_cv(cat, job.title, text),
        "posted": job.posted,
        "excerpt": text[:500],
        "full_text": job.full_text,
        "sources": [{"source": job.source, "source_id": job.source_id, "url": job.url, "first_seen": ts, "last_seen": ts}],
        "first_discovered": ts,
        "last_verified": ts,
        "last_seen": ts,
        "status": "Open",
        "status_reason": "",
        "history": [],
    }
    return rec, None

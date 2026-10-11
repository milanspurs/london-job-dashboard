"""Location checks and hard exclusions."""
from __future__ import annotations

import re

from .config import (COMMUTER_TERMS, EXCLUDE_COMPANIES, EXCLUDE_TEXT_PATTERNS, EXCLUDE_TITLE_PATTERNS, LONDON_TERMS,
                     MANAGER_OK, MAX_EXPERIENCE_YEARS, NON_UK_TERMS)
from .models import RawJob

_TITLE_RX = [re.compile(p, re.I) for p in EXCLUDE_TITLE_PATTERNS]
_TEXT_RX = [re.compile(p, re.I) for p in EXCLUDE_TEXT_PATTERNS]
_MANAGER = re.compile(r"\bmanager\b", re.I)
_MANAGER_OK = re.compile(MANAGER_OK, re.I)
_UK_REMOTE = re.compile(r"\b(remote|home[- ]based|work from home)\b", re.I)
_UK = re.compile(r"\b(uk|united kingdom|england|great britain|gb)\b", re.I)

_EXPERIENCE = re.compile(
    r"(?:minimum of |at least |min\.? )?(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*years?['’]?\s*"
    r"(?:of\s+)?(?:relevant\s+|professional\s+|proven\s+|commercial\s+|industry\s+|post[- ]qualification\s+|work\s+)?experience",
    re.I)
_PQE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years?\s*)?pqe", re.I)


def classify_location(job: RawJob) -> tuple[str, str]:
    """Return (location_class, confidence).

    location_class: London | Commuter belt | Remote (UK) | Excluded
    confidence: High | Medium | Low
    """
    loc = (job.location or "").lower()
    area = " ".join(job.extra.get("area") or []).lower()
    hay = f"{loc} {area}"
    if any(t in hay for t in NON_UK_TERMS) and "london" not in hay.replace("london, on", "").replace("new london", ""):
        return "Excluded", "High"
    if any(re.search(rf"\b{re.escape(t)}\b", hay) for t in LONDON_TERMS):
        # "London, ON" (Canada) etc. caught above; aggregator searches are London-anchored
        return "London", "High" if (job.official or "london" in hay) else "Medium"
    if any(re.search(rf"\b{re.escape(t)}\b", hay) for t in COMMUTER_TERMS):
        return "Commuter belt", "High"
    remote = job.remote_flag or bool(_UK_REMOTE.search(hay)) or (job.workplace or "").lower() == "remote"
    if remote and (_UK.search(hay) or not hay.strip() or job.source in ("adzuna", "reed")):
        return "Remote (UK)", "Medium"
    if job.source in ("adzuna", "reed") and not hay.strip():
        return "London", "Low"  # result of a London-radius search with no location text
    return "Excluded", "Medium"


def required_experience_years(text: str) -> int | None:
    """Smallest 'N years experience' requirement stated, if any."""
    vals = []
    for m in _EXPERIENCE.finditer(text or ""):
        try:
            vals.append(int(m.group(1)))
        except ValueError:
            pass
    for m in _PQE.finditer(text or ""):
        vals.append(int(m.group(1)))
    vals = [v for v in vals if 0 < v < 30]
    return min(vals) if vals else None


def exclusion_reason(job: RawJob) -> str | None:
    title = job.title or ""
    comp = (job.company or "").lower()
    if any(c in comp for c in EXCLUDE_COMPANIES):
        return "training provider (paid course advertised as a job)"
    for rx in _TITLE_RX:
        if rx.search(title):
            # "Senior" in grad scheme titles is rare; keep "Graduate ... Lead" style out anyway
            return f"title matches excluded pattern '{rx.pattern}'"
    if _MANAGER.search(title) and not _MANAGER_OK.search(title):
        return "manager-level title"
    text = f"{title} {job.description}"
    for rx in _TEXT_RX:
        if rx.search(text):
            return f"text matches excluded pattern '{rx.pattern}'"
    yrs = required_experience_years(job.description)
    if yrs is not None and yrs > MAX_EXPERIENCE_YEARS:
        return f"requires {yrs}+ years' experience"
    return None

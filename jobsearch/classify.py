"""Category, opportunity type, work arrangement and cycle classification."""
from __future__ import annotations

import re

from .config import CATEGORIES
from .models import RawJob

_INTERN = re.compile(r"\b(intern(ship)?s?|summer (analyst|associate|programme|program|placement)|placement (student|year)|"
                     r"industrial placement|insight (week|programme)|spring (week|insight)|work experience)\b", re.I)
_OFFCYCLE = re.compile(r"\b(off[- ]cycle|winter intern|autumn intern|spring intern|6[- ]month intern|"
                       r"(3|6|12)[- ]month (internship|placement)|year[- ]in[- ]industry|placement year)\b", re.I)
_SUMMER = re.compile(r"\bsummer\b", re.I)
_GRAD = re.compile(r"\b(graduate|grad scheme|grad programme|graduate programme|graduate scheme|"
                   r"early careers?|trainee|analyst programme|rotational|class of 202[6-8]|"
                   r"202[78] (start|intake|graduate)|new grad|management trainee|apprentice(ship)? degree)\b", re.I)
_JUNIOR = re.compile(r"\b(junior|entry[- ]level|assistant|associate|analyst|executive|coordinator|officer|"
                     r"administrator|researcher|graduate)\b", re.I)
_SPRING_WEEK = re.compile(r"\b(spring week|spring insight|insight (week|day|programme)|open day)\b", re.I)


def opportunity_type(job: RawJob) -> str:
    t = job.title or ""
    text = f"{t} {job.description[:1500]}"
    if _SPRING_WEEK.search(t):
        return "Insight Programme"
    if _INTERN.search(t) or (job.query_hint == "intern" and _INTERN.search(text) and not _GRAD.search(t)):
        if _OFFCYCLE.search(text) or (not _SUMMER.search(text) and re.search(r"\b(6|12)[- ]month", text, re.I)):
            return "Off-cycle Internship"
        return "Summer Internship"
    if _GRAD.search(t) or re.search(r"graduate (scheme|programme|program)", text, re.I):
        return "Graduate"
    if "intern" in (job.employment_type or "").lower():
        return "Summer Internship" if _SUMMER.search(text) else "Off-cycle Internship"
    return "Entry-Level"


def work_arrangement(job: RawJob) -> str:
    w = (job.workplace or "").lower()
    text = f"{job.title} {job.location} {job.description[:3000]}".lower()
    if "hybrid" in w or re.search(r"\bhybrid\b", text):
        return "Hybrid"
    if w == "remote" or job.remote_flag or re.search(r"\b(fully remote|remote[- ]first|100% remote|work from home)\b", text):
        return "Remote"
    if w in ("onsite", "on-site", "office") or re.search(r"\b(office[- ]based|on[- ]site|in the office (5|five) days)\b", text):
        return "Office"
    return "Not stated"


# Words that say little about the field on their own ("Sustainability Consultant" is ESG)
GENERIC_KEYWORDS = {"consult", "strategy", "digital", "project", "planning", "power", "capital", "fund",
                    "analytics", "insight", "commercial", "operations", "programme", "markets"}


def categorise(job: RawJob) -> tuple[str, list[str]]:
    """Return (primary category key, matched keywords)."""
    title = f" {job.title.lower()} "
    body = f" {job.description.lower()[:4000]} "
    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    for key, c in CATEGORIES.items():
        s = 0.0
        for kw in c["keywords"]:
            if kw in title:
                s += 1.5 if kw in GENERIC_KEYWORDS else 3
                hits.setdefault(key, []).append(kw.strip())
            elif kw in body:
                s += 0.5
        # small tier preference so ties go to higher-priority categories
        scores[key] = s + (0.2 if c["tier"] == 1 else 0.1 if c["tier"] == 2 else 0)
    best = max(scores, key=scores.get)
    if scores[best] < 1:
        return "other", []
    return best, hits.get(best, [])


def recruitment_cycle(job: RawJob, opp_type: str) -> str:
    text = f"{job.title} {job.description[:3000]}"
    m = re.search(r"\b(20(2[6-9]))\b\s*(?:/\s*\d{2,4})?\s*(intake|start|cohort|graduate|programme|scheme|internship|summer)?", text, re.I)
    years = sorted({int(y) for y in re.findall(r"\b(202[6-9])\b", text)})
    if opp_type in ("Graduate", "Summer Internship", "Off-cycle Internship", "Insight Programme"):
        future = [y for y in years if y >= 2027]
        if future:
            return f"{future[0]} {'intake' if opp_type == 'Graduate' else 'cycle'}"
        if m:
            return f"{m.group(1)} cycle"
        return "Not stated"
    return "Rolling / immediate"


_START = re.compile(r"(?:start(?:ing)?(?: date)?|commenc\w+|join(?:ing)? us)\s*(?:in|on|:|from)?\s*"
                    r"((?:early |mid[- ]|late )?(?:january|february|march|april|may|june|july|august|september|october|"
                    r"november|december|spring|summer|autumn|winter)\s*(?:20\d\d)?|\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+20\d\d|asap|immediately)",
                    re.I)


def start_date(job: RawJob) -> str | None:
    m = _START.search(job.description or "")
    return m.group(1).strip().title() if m else None

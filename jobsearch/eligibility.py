"""Eligibility extraction against the candidate's situation.

Candidate: BSc Chemistry 2:1 (graduated 2024); MSc Risk Analytics, QMUL,
2026-27 (final-year master's student, graduating 2027, not returning to study
after summer 2027).

Nothing here is assumed: if the advert doesn't say, the field says "Not stated"
and the verdict becomes "Check eligibility".
"""
from __future__ import annotations

import re

from .config import PROFILE

_GRAD_YEARS = [
    re.compile(r"\b(20\d\d)\s*(?:,|or|and|/|&|-|–)\s*(20\d\d)\s+graduat", re.I),
    re.compile(r"graduat\w*\s+(?:in|between|from|during)?\s*(?:summer |autumn |)?(20\d\d)(?:\s*(?:or|and|/|-|–|&)\s*(20\d\d))?", re.I),
    re.compile(r"\b(20\d\d)\s+graduates?\b", re.I),
    re.compile(r"class of\s+(20\d\d)", re.I),
    re.compile(r"due to graduate\s+(?:in\s+)?(?:\w+\s+)?(20\d\d)", re.I),
]
_MASTERS = re.compile(r"\b(master'?s|msc|m\.sc|postgraduate|postgrad|pg students?)\b", re.I)
_UG_ONLY = re.compile(r"\b(undergraduates? only|undergraduate students only|must be an undergraduate)\b", re.I)
_FINAL_YEAR = re.compile(r"\bfinal[- ]year\b", re.I)
_PENULTIMATE = re.compile(r"\b(penultimate[- ]year|second[- ]year of a three|2nd year|first[- ]year students)\b", re.I)
_RETURN = re.compile(r"\b(return(?:ing)? to (?:university|study|studies|your studies|full[- ]time (?:study|education))|"
                     r"must (?:be|still be) (?:enrolled|studying|a student) (?:after|following)|"
                     r"have at least one (?:more )?year (?:of study )?remaining|continuing (?:your )?studies)\b", re.I)
_RECENT_GRAD = re.compile(r"graduated (?:with)?in the (?:last|past) (\w+) years?", re.I)
_CLASS = re.compile(r"\b(2[:.]1|upper second|first[- ]class|2[:.]2|lower second|minimum (?:of )?(?:a )?(?:2[:.]1|2[:.]2))\b", re.I)
_DEGREE_SUBJ = re.compile(r"degree in ((?:[A-Z][\w&]+(?:,? (?:or |and )?)?){1,6})", re.I)
_STEM = re.compile(r"\b(stem|numerate|quantitative (?:degree|discipline)|science,? technology|any (?:degree )?discipline|all degree disciplines|any subject)\b", re.I)
_UCAS = re.compile(r"(\d{2,3})\s*ucas (?:points|tariff)", re.I)
_RTW = re.compile(r"(right to work in the uk|unable to (?:offer|provide) (?:visa )?sponsorship|"
                  r"(?:do|does|can) not (?:offer|provide) (?:visa )?sponsorship|sponsorship (?:is )?(?:not )?available|"
                  r"visa sponsorship|skilled worker visa|graduate route visa)", re.I)
_TECH = {
    "Python": r"\bpython\b", "SQL": r"\bsql\b", "Excel": r"\bexcel\b", "VBA": r"\bvba\b", "R": r"\bR\b(?: programming|,| or python|/python)",
    "Power BI": r"\bpower ?bi\b", "Tableau": r"\btableau\b", "SAS": r"\bsas\b", "MATLAB": r"\bmatlab\b",
    "C++": r"c\+\+", "Java": r"\bjava\b", "Bloomberg": r"\bbloomberg terminal\b", "GIS": r"\b(gis|arcgis|qgis)\b",
    "Financial modelling": r"financial model(?:l)?ing", "Actuarial exams": r"\b(ifoa|actuarial exams?)\b",
    "CFA": r"\bcfa\b", "ACA/ACCA/CIMA": r"\b(aca|acca|cima)\b",
}
_STRONG = re.compile(r"(proficien|advanced|expert|strong|extensive|solid|demonstrable|hands[- ]on|required|essential|must have)", re.I)


def _sentence_around(text: str, start: int, end: int) -> str:
    a = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    b_dot, b_nl = text.find(".", end), text.find("\n", end)
    cands = [x for x in (b_dot, b_nl) if x != -1]
    b = min(cands) if cands else len(text)
    return text[a:b].strip()


def assess(text: str, opp_type: str, full_text: bool) -> dict:
    t = text or ""
    years: set[int] = set()
    for rx in _GRAD_YEARS:
        for m in rx.finditer(t):
            for g in m.groups():
                if g and g.isdigit() and 2020 <= int(g) <= 2030:
                    years.add(int(g))
    grad_years = sorted(years)

    masters = "Yes" if _MASTERS.search(t) and not _UG_ONLY.search(t) else ("No" if _UG_ONLY.search(t) else "Not stated")
    final_year = "Yes" if _FINAL_YEAR.search(t) else "Not stated"
    penultimate = bool(_PENULTIMATE.search(t))
    return_req = "Yes" if _RETURN.search(t) else "Not stated"
    cls = _CLASS.search(t)
    degree_class = cls.group(0) if cls else "Not stated"
    subj = _DEGREE_SUBJ.search(t)
    degree_subjects = subj.group(1).strip(" ,") if subj else ""
    stem_ok = bool(_STEM.search(t))
    rtw = sorted({m.group(0).strip().capitalize() for m in _RTW.finditer(t)})
    ucas = _UCAS.search(t)

    tech_req, tech_strong = [], []
    for name, pat in _TECH.items():
        m = re.search(pat, t, re.I if name != "R" else 0)
        if m:
            tech_req.append(name)
            if _STRONG.search(_sentence_around(t, m.start(), m.end())):
                tech_strong.append(name)

    issues: list[str] = []
    verdict = "Likely eligible"
    msc_year = PROFILE["msc_end_year"]

    if grad_years:
        if msc_year in grad_years or 2024 in grad_years:
            pass
        elif all(y > msc_year for y in grad_years):
            issues.append(f"Targets {', '.join(map(str, grad_years))} graduates; you graduate in {msc_year}")
            verdict = "Likely ineligible"
        elif all(y < msc_year for y in grad_years) and opp_type != "Entry-Level":
            issues.append(f"Targets {', '.join(map(str, grad_years))} graduates; check whether a {msc_year} MSc counts")
            verdict = "Check eligibility"

    if opp_type in ("Summer Internship", "Off-cycle Internship", "Insight Programme"):
        if return_req == "Yes":
            issues.append("Requires returning to university after the internship — you complete your MSc in 2027")
            verdict = "Likely ineligible"
        if penultimate and final_year == "Not stated" and masters != "Yes":
            issues.append("Aimed at penultimate-year students; final-year master's eligibility not stated")
            verdict = "Likely ineligible" if verdict != "Likely ineligible" else verdict
        if masters == "No":
            issues.append("Undergraduates only")
            verdict = "Likely ineligible"
        if verdict == "Likely eligible" and masters == "Not stated" and final_year == "Not stated" and not grad_years:
            issues.append("Graduation-year and master's eligibility not stated — confirm before applying")
            verdict = "Check eligibility"
    elif opp_type == "Graduate":
        if masters == "No":
            issues.append("Undergraduates only")
            verdict = "Likely ineligible"

    if re.search(r"first[- ]class", degree_class, re.I):
        issues.append("Asks for a First; you hold a 2:1")
        verdict = "Check eligibility" if verdict == "Likely eligible" else verdict
    if ucas:
        issues.append(f"States a UCAS requirement ({ucas.group(1)} points) — check against your A-levels/BTEC")
    if degree_subjects and not stem_ok:
        subjects = degree_subjects.lower()
        if not re.search(r"chem|science|stem|numerate|quantitative|any|risk|analytics|math|statist|physic", subjects):
            issues.append(f"Prefers a degree in {degree_subjects[:80]}")
            verdict = "Check eligibility" if verdict == "Likely eligible" else verdict
    if rtw:
        issues.append("States right-to-work/sponsorship terms: " + "; ".join(rtw)[:160])
    if not full_text and verdict == "Likely eligible":
        verdict = "Check eligibility"
        issues.append("Only an advert snippet was available — read the full posting for eligibility")

    return {
        "verdict": verdict,
        "graduation_years": grad_years,
        "masters_eligible": masters,
        "final_year_eligible": final_year,
        "return_to_study_required": return_req,
        "degree_class": degree_class,
        "degree_subjects": degree_subjects or ("STEM/any discipline" if stem_ok else "Not stated"),
        "technical_requirements": tech_req,
        "technical_strong": tech_strong,
        "right_to_work": rtw,
        "issues": issues,
    }

"""Fit scoring (1-5) and CV recommendation.

5  excellent match, credible eligibility, strong career alignment
4  strong match, minor gaps
3  reasonable, transferable strengths
2  stretch
1  weak match or significant eligibility doubt

Employer prestige plays no part in the score.
"""
from __future__ import annotations

import re

from .config import CATEGORIES, CV, PROFILE, SCIENCE_CV_TERMS

_ROTATIONAL = re.compile(r"\b(rotational|rotation|management (programme|trainee)|leadership programme|general management|"
                         r"business management programme|commercial graduate)\b", re.I)


def recommend_cv(cat: str, title: str, text: str) -> str:
    t = f"{title} {text[:2000]}".lower()
    if cat == "other":
        if any(k in t for k in SCIENCE_CV_TERMS):
            return CV["esg"]  # carries the full chemistry dissertation detail
        return CV["grad"]
    if _ROTATIONAL.search(title):
        return CV["grad"]
    if cat == "policy" and re.search(r"energy|climate|environment|net zero", t):
        return CV["energy"]
    if cat == "tech" and re.search(r"strategy|consult", t):
        return CV["strategy"]
    return CATEGORIES[cat]["cv"]


def score(*, cat: str, title: str, text: str, opp_type: str, elig: dict, location_class: str,
          experience_years: int | None, full_text: bool) -> tuple[int, list[str], list[str]]:
    """Returns (score, reasons it matches, gaps/risks)."""
    t = f"{title} {text}".lower()
    tier = CATEGORIES[cat]["tier"]
    why: list[str] = []
    gaps: list[str] = []

    s = {1: 3.4, 2: 3.0, 3: 2.6}[tier]
    why.append(f"{CATEGORIES[cat]['label']} (tier {tier} interest)")

    strengths = [k for k in PROFILE["strengths"] if k in t]
    bonus = min(len(strengths) * 0.15, 0.9)
    s += bonus
    if strengths:
        why.append("Draws on: " + ", ".join(sorted(set(strengths))[:6]))

    if re.search(r"\b(risk analytics|risk management|actuar|catastrophe model|climate risk)\b", t):
        s += 0.4
        why.append("Directly uses your MSc Risk Analytics study")
    if re.search(r"\b(chemistry|chemical|scientific background|science degree|stem)\b", t):
        s += 0.3
        why.append("Values a science/STEM degree like your Chemistry BSc")
    if re.search(r"\b(msc|master'?s|postgraduate)\b", t) and elig["masters_eligible"] == "Yes":
        s += 0.2
        why.append("Explicitly open to master's students")
    if opp_type == "Graduate":
        s += 0.4
    elif opp_type in ("Summer Internship", "Off-cycle Internship"):
        s += 0.2
    if re.search(r"(no (prior )?experience (is )?(required|necessary)|full training (is )?provided|training provided)", t):
        s += 0.2
        why.append("Training provided / no prior experience needed")

    # --- penalties
    if elig["verdict"] == "Likely ineligible":
        s -= 2.2
        gaps.extend(elig["issues"][:2])
    elif elig["verdict"] == "Check eligibility":
        s -= 0.4 if opp_type in ("Summer Internship", "Off-cycle Internship") else 0.15
    strong_missing = [x for x in elig["technical_strong"] if x.lower() in PROFILE["beginner_skills"]]
    hard_missing = [x for x in elig["technical_requirements"]
                    if any(m in x.lower() for m in ("vba", "tableau", "c++", "java", "matlab", "gis", "cfa", "aca", "financial modelling"))]
    if strong_missing:
        s -= 0.3 * len(strong_missing)
        gaps.append("Asks for strong " + ", ".join(strong_missing) + " (you're at beginner level)")
    if hard_missing:
        s -= 0.25 * min(len(hard_missing), 2)
        gaps.append("Mentions " + ", ".join(hard_missing) + " (not on your CV)")
    if experience_years == 2:
        s -= 0.4
        gaps.append("Asks for ~2 years' experience")
    elif experience_years == 1:
        s -= 0.15
        gaps.append("Prefers ~1 year of experience")
    if location_class == "Commuter belt":
        s -= 0.3
        gaps.append("Outside London (commuter belt)")
    elif location_class == "Remote (UK)":
        s -= 0.1
    if not full_text:
        s -= 0.2
    if opp_type == "Entry-Level" and not re.search(r"\b(junior|graduate|entry|trainee|assistant|analyst|associate|executive|researcher)\b", title, re.I):
        s -= 0.5
        gaps.append("Title doesn't clearly signal an entry-level role")

    final = max(1, min(5, round(s)))
    return final, why[:5], gaps[:5]

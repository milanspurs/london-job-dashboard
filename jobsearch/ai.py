"""OPTIONAL AI eligibility check (off by default).

Enabled only when BOTH the ANTHROPIC_API_KEY secret is set AND the
AI_MAX_CALLS_PER_RUN variable is > 0. Each call reviews one new vacancy whose
eligibility the rule-based parser couldn't settle. With the default model and
~2k-token adverts, cost is roughly a fraction of a penny per call; the per-run
cap bounds spend (e.g. 5 calls x 12 runs/day).

It can only ADD clarity to eligibility fields; it never creates vacancies,
deadlines or salaries.
"""
from __future__ import annotations

import json
import logging
import os

from .http import Http

log = logging.getLogger(__name__)
MODEL = os.environ.get("AI_MODEL", "claude-haiku-5-5")

PROMPT = """You check UK job adverts for one candidate's eligibility.
Candidate: BSc Chemistry 2:1 (graduated 2024); currently a final-year MSc Risk Analytics student at QMUL, graduating 2027; will NOT return to university after summer 2027.
Using ONLY the advert text, answer in JSON with keys:
graduation_years (list of ints stated, [] if none), masters_eligible ("Yes"/"No"/"Not stated"),
final_year_eligible ("Yes"/"No"/"Not stated"), return_to_study_required ("Yes"/"No"/"Not stated"),
verdict ("Likely eligible"/"Check eligibility"/"Likely ineligible"), reason (max 25 words).
Never guess: if the advert doesn't say, use "Not stated".

ADVERT:
"""


def refine(http: Http, records_with_text: list[tuple[dict, str]], max_calls: int) -> int:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or max_calls <= 0:
        return 0
    used = 0
    for rec, text in records_with_text:
        if used >= max_calls:
            break
        if rec["eligibility"]["verdict"] != "Check eligibility" or not rec.get("full_text"):
            continue
        res = http.post("https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": MODEL, "max_tokens": 300,
                              "messages": [{"role": "user", "content": PROMPT + text[:6000]}]})
        used += 1
        if not res.ok or res.status != 200:
            log.warning("AI check failed: %s", res.error or res.status)
            continue
        try:
            out = res.data["content"][0]["text"]
            data = json.loads(out[out.find("{"): out.rfind("}") + 1])
        except (KeyError, IndexError, ValueError):
            continue
        e = rec["eligibility"]
        for k in ("masters_eligible", "final_year_eligible", "return_to_study_required"):
            if e.get(k) == "Not stated" and data.get(k) in ("Yes", "No"):
                e[k] = data[k]
        if data.get("verdict") in ("Likely eligible", "Likely ineligible"):
            e["verdict"] = data["verdict"]
            e["issues"] = (e.get("issues") or []) + [f"AI check: {str(data.get('reason', ''))[:150]}"]
            e["ai_checked"] = True
    return used

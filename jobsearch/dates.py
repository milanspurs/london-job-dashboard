"""Deadline / opening-date extraction with confidence labels.

Confidence rules (never invent a date):
  Confirmed   - the date is stated, with a year, in the employer's own current
                posting for a UK/London role (an official ATS board).
  Indicative  - stated by an aggregator advert (incl. advert expiry dates), or
                stated without a year so the year had to be inferred.
  Unconfirmed - no date found. Rolling vacancies get no deadline at all.
"""
from __future__ import annotations

import re
from datetime import date, datetime

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

_D = r"(\d{1,2})(?:st|nd|rd|th)?"
_M = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_Y = r"(?:,?\s*(20\d\d))?"
DATE_PATTERNS = [
    re.compile(rf"{_D}\s+(?:of\s+)?{_M}\.?{_Y}", re.I),                 # 30 November 2026
    re.compile(rf"{_M}\.?\s+{_D}{_Y}", re.I),                            # November 30, 2026
    re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](20\d\d|\d\d)\b"),           # 30/11/2026 (UK order)
    re.compile(r"\b(20\d\d)-(\d{2})-(\d{2})\b"),                         # 2026-11-30
]

DEADLINE_CUES = re.compile(
    r"(closing date|closes? on|applications? (?:will )?close|deadline|apply by|apply before|submit .{0,40}by|"
    r"no later than|applications? must be (?:received|submitted) by|vacancy closes|ends? on)", re.I)
OPEN_CUES = re.compile(r"(applications? (?:will )?(?:open|re-?open)s?|opening date|open for applications? (?:on|from)|"
                       r"launch(?:es)? on|recruitment opens?)", re.I)
ROLLING = re.compile(r"\b(rolling basis|on a rolling|rolling recruitment|rolling applications|"
                     r"close (?:the|this) (?:vacancy|role|advert) early|may close early|"
                     r"until (?:the role is |positions are )?filled)\b", re.I)


def _parse_match(m: re.Match, idx: int, today: date) -> tuple[date | None, bool]:
    """Returns (date, year_inferred)."""
    try:
        if idx == 0:
            d, mon, y = int(m.group(1)), MONTHS[m.group(2).lower()[:3]], m.group(3)
        elif idx == 1:
            mon, d, y = MONTHS[m.group(1).lower()[:3]], int(m.group(2)), m.group(3)
        elif idx == 2:
            d, mon, y = int(m.group(1)), int(m.group(2)), m.group(3)
            y = y if len(y) == 4 else f"20{y}"
        else:
            y, mon, d = m.group(1), int(m.group(2)), int(m.group(3))
        if y:
            return date(int(y), mon, d), False
        cand = date(today.year, mon, d)
        if cand < today:
            cand = date(today.year + 1, mon, d)
        return cand, True
    except (ValueError, KeyError):
        return None, False


def _find_date_after(text: str, cue_rx: re.Pattern, today: date, window: int = 90):
    for cue in cue_rx.finditer(text):
        seg = text[cue.end(): cue.end() + window]
        best = None
        for idx, rx in enumerate(DATE_PATTERNS):
            m = rx.search(seg)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), m, idx)
        if best:
            d, inferred = _parse_match(best[1], best[2], today)
            if d:
                return d, inferred, text[max(0, cue.start() - 20): cue.end() + best[1].end()].strip()
    return None, False, ""


def extract_dates(text: str, *, official: bool, full_text: bool, posted: str | None = None,
                  expiry: str | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    text = text or ""
    out = {"deadline": None, "deadline_confidence": "Unconfirmed", "deadline_evidence": "",
           "opening_date": None, "opening_confidence": "Unconfirmed", "rolling": bool(ROLLING.search(text))}

    d, inferred, ev = _find_date_after(text, DEADLINE_CUES, today)
    posted_d = _to_date(posted)
    if d and posted_d and d < posted_d:
        d = None  # a date earlier than the posting is from a previous cycle; ignore
    if d and d.year > today.year + 2:
        d = None
    if d:
        out["deadline"] = d.isoformat()
        out["deadline_confidence"] = "Confirmed" if (official and not inferred) else "Indicative"
        out["deadline_evidence"] = ev[:160]
    elif expiry:
        out["deadline"] = expiry
        out["deadline_confidence"] = "Indicative"
        out["deadline_evidence"] = "Aggregator advert expiry date (not an employer-stated deadline)"

    od, oinf, oev = _find_date_after(text, OPEN_CUES, today)
    if od and od.year <= today.year + 2:
        out["opening_date"] = od.isoformat()
        out["opening_confidence"] = "Confirmed" if (official and not oinf) else "Indicative"
    return out


def _to_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")[:19]).date() if "T" in s else date.fromisoformat(s[:10])
    except ValueError:
        return None


def days_until(iso: str | None, today: date | None = None) -> int | None:
    d = _to_date(iso)
    return (d - (today or date.today())).days if d else None

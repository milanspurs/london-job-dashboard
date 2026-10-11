"""Data shapes shared across modules."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


_COMPANY_SUFFIX = re.compile(
    r"\b(ltd|limited|plc|llp|llc|inc|group|uk|international|holdings|the|and|&|co|company|services)\b\.?", re.I)


def norm_company(name: str) -> str:
    s = (name or "").lower()
    s = _COMPANY_SUFFIX.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_title(title: str) -> str:
    s = (title or "").lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\b(london|uk|hybrid|remote|2026|2027|2028|-|–|—)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def make_id(company: str, title: str) -> str:
    key = f"{norm_company(company)}|{norm_title(title)}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


@dataclass
class RawJob:
    """A vacancy as returned by one source, before processing."""
    source: str                 # e.g. "adzuna", "reed", "greenhouse:monzo"
    source_id: str
    company: str
    title: str
    location: str
    url: str
    description: str = ""
    posted: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_text: str = ""
    salary_predicted: bool = False
    expiry: str | None = None   # advert expiry from an aggregator (not an official deadline)
    remote_flag: bool | None = None
    workplace: str = ""
    employment_type: str = ""
    official: bool = False      # True when it comes straight from the employer's own ATS
    query_hint: str = ""        # grad | intern | entry
    full_text: bool = False     # True when description is the full advert (not a snippet)
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return make_id(self.company, self.title)

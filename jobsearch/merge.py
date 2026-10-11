"""Deduplication and merging of new observations into the database."""
from __future__ import annotations

import re

from .models import norm_company, norm_title, now_iso

# Fields owned by the most authoritative observation
DESCRIPTIVE = ("title", "category", "category_label", "tier", "type", "location", "location_class",
               "location_confidence", "work_arrangement", "start_date", "opening_date", "opening_confidence",
               "deadline", "deadline_confidence", "deadline_evidence", "rolling", "cycle", "fit", "why", "missing",
               "eligibility", "experience_years", "employment_type", "recommended_cv", "excerpt", "full_text",
               "apply_url", "official", "official_source")
TRACKED = ("deadline", "deadline_confidence", "opening_date", "fit", "type", "location_class")


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s))


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.85


class Index:
    def __init__(self, roles: list[dict]):
        self.by_id = {r["id"]: r for r in roles}
        self.by_source = {}
        self.by_company: dict[str, list[dict]] = {}
        for r in roles:
            self._add(r)

    def _add(self, r: dict) -> None:
        for s in r.get("sources", []):
            self.by_source[(s["source"], s["source_id"])] = r
        self.by_company.setdefault(norm_company(r["company"]), []).append(r)

    def find(self, rec: dict) -> dict | None:
        s = rec["sources"][0]
        hit = self.by_source.get((s["source"], s["source_id"])) or self.by_id.get(rec["id"])
        if hit:
            return hit
        nt = norm_title(rec["title"])
        for r in self.by_company.get(norm_company(rec["company"]), []):
            if _similar(norm_title(r["title"]), nt):
                return r
        return None

    def add(self, r: dict) -> None:
        self.by_id[r["id"]] = r
        self._add(r)


def _authority(rec: dict) -> int:
    return (2 if rec.get("official") else 0) + (1 if rec.get("full_text") else 0)


def merge_observation(db_roles: list[dict], idx: Index, rec: dict) -> tuple[dict, bool]:
    """Merge a freshly evaluated record. Returns (stored record, is_new)."""
    existing = idx.find(rec)
    ts = now_iso()
    if existing is None:
        db_roles.append(rec)
        idx.add(rec)
        return rec, True

    src = rec["sources"][0]
    for s in existing["sources"]:
        if s["source"] == src["source"] and s["source_id"] == src["source_id"]:
            s["last_seen"] = ts
            s["url"] = src["url"] or s["url"]
            break
    else:
        existing["sources"].append(src)
        idx.by_source[(src["source"], src["source_id"])] = existing

    if _authority(rec) >= _authority(existing):
        for f in DESCRIPTIVE:
            new, old = rec.get(f), existing.get(f)
            if f in TRACKED and new != old and old is not None:
                existing.setdefault("history", []).append({"at": ts, "field": f, "from": old, "to": new})
            # never replace a known deadline with "none found" from a weaker snippet
            if f in ("deadline", "deadline_confidence", "deadline_evidence") and rec.get("deadline") is None \
                    and existing.get("deadline") and existing.get("deadline_confidence") == "Confirmed":
                continue
            existing[f] = new
    if not existing.get("salary") and rec.get("salary"):
        existing["salary"] = rec["salary"]
    existing["last_seen"] = ts
    existing["last_verified"] = ts
    existing["verify_failures"] = 0
    existing["absent_count"] = 0
    existing.pop("closed_evidence", None)  # seen live again
    existing["history"] = existing.get("history", [])[-30:]
    return existing, False

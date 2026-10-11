"""Change detection between the start and end of a run."""
from __future__ import annotations

from .dates import days_until
from .models import now_iso


def snapshot(roles: list[dict]) -> dict:
    return {r["id"]: {k: r.get(k) for k in ("status", "deadline", "deadline_confidence", "fit", "opening_date")}
            for r in roles}


def diff(before: dict, roles: list[dict], new_ids: set[str]) -> list[dict]:
    ts = now_iso()
    events = []

    def ev(kind, r, **extra):
        events.append({"at": ts, "event": kind, "id": r["id"], "company": r["company"], "title": r["title"],
                       "type": r["type"], "fit": r["fit"], "status": r["status"], "deadline": r.get("deadline"),
                       "deadline_confidence": r.get("deadline_confidence"), **extra})

    for r in roles:
        if r["id"] in new_ids:
            ev("new", r)
            continue
        b = before.get(r["id"])
        if not b:
            continue
        if b["status"] != r["status"]:
            if r["status"] == "Open" and b["status"] in ("Opens Soon", "Watch", "Verify", "Closed"):
                ev("opened", r, previous=b["status"])
            elif r["status"] == "Closed":
                ev("closed", r, previous=b["status"], reason=r.get("status_reason"))
            else:
                ev("status_changed", r, previous=b["status"])
        if b["deadline"] and r.get("deadline") and b["deadline"] != r["deadline"]:
            kind = "deadline_earlier" if r["deadline"] < b["deadline"] else "deadline_later"
            ev(kind, r, previous=b["deadline"])
        elif not b["deadline"] and r.get("deadline"):
            ev("deadline_found", r)
        if b["fit"] != r["fit"]:
            ev("fit_changed", r, previous=b["fit"])
    return events


def closing_soon(roles: list[dict], days: int = 14) -> list[dict]:
    out = []
    for r in roles:
        if r["status"] != "Open" or r.get("deadline_confidence") != "Confirmed":
            continue
        d = days_until(r.get("deadline"))
        if d is not None and 0 <= d <= days:
            out.append(r)
    return out

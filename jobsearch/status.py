"""Status determination.

Open        live on at least one source, deadline (if any) not passed
Opens Soon  a future application opening date is stated
Verify      couldn't be checked reliably (source failing, location unclear, no readable content)
Watch       not seen in recent successful searches, but nothing proves it closed
Closed      positive evidence only: confirmed deadline passed, removed from the
            employer's own board on 2+ successful checks, removed from Reed, or an
            aggregator advert past its expiry and no longer appearing

A failed request NEVER closes a vacancy.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from .config import SETTINGS
from .dates import days_until


def _days_since(iso: str | None) -> float:
    if not iso:
        return 1e9
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 1e9
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def set_status(r: dict, today: date | None = None) -> None:
    today = today or date.today()
    prev = r.get("status")
    status, reason = "Open", "Listed on a live source"

    dl = days_until(r.get("deadline"), today)
    od = days_until(r.get("opening_date"), today)
    seen_days = _days_since(r.get("last_seen"))

    if r.get("closed_evidence"):
        status, reason = "Closed", r["closed_evidence"]
    elif dl is not None and dl < 0 and r.get("deadline_confidence") == "Confirmed":
        status, reason = "Closed", f"Confirmed deadline {r['deadline']} has passed"
    elif dl is not None and dl < 0 and r.get("deadline_confidence") == "Indicative" and seen_days > 3:
        status, reason = "Closed", f"Advert expired {r['deadline']} and no longer listed"
    elif od is not None and od > 0:
        status, reason = "Opens Soon", f"Applications open {r['opening_date']} ({r.get('opening_confidence')})"
    elif r.get("verify_failures", 0) >= 3:
        status, reason = "Verify", "Source could not be reached on the last checks — open the link to confirm"
    elif r.get("absent_count", 0) == 1:
        status, reason = "Watch", "Missing from the employer board on the latest check — will confirm next run"
    elif seen_days > SETTINGS["watch_after_days_unseen"]:
        status, reason = "Watch", f"Not seen in searches for {int(seen_days)} days — may have closed; check the link"
    elif r.get("location_confidence") == "Low":
        status, reason = "Verify", "Location not stated in the advert — confirm it's London-based"

    r["status"], r["status_reason"] = status, reason
    if prev and prev != status:
        r.setdefault("history", []).append({"at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                                            "field": "status", "from": prev, "to": status})
        r["history"] = r["history"][-30:]

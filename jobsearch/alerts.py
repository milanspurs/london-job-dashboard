"""Gmail draft alerts. Drafts only — this module never calls the send endpoint.

Credentials come from GitHub Actions secrets:
  GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN  (OAuth, scope gmail.compose)
  GMAIL_TO  (optional: address pre-filled in the draft's To field)
"""
from __future__ import annotations

import base64
import logging
import os
from email.message import EmailMessage

import requests

from .changes import closing_soon
from .config import SETTINGS
from .dates import days_until
from .models import now_iso

log = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
DRAFTS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
DONE_STATES = {"Applied", "Online Assessment", "Interview", "Offer", "Rejected"}

LABELS = {
    "deadline_soon": "Closing soon",
    "deadline_earlier": "Deadline moved earlier",
    "opened": "Applications open",
    "new": "New match",
}


def select_alerts(events: list[dict], roles: list[dict], sent: dict, tracker: dict, bootstrap: bool) -> list[tuple[str, dict, str]]:
    """Return [(kind, role, ledger_key)] in priority order, deduplicated against `sent`."""
    by_id = {r["id"]: r for r in roles}
    min_fit = SETTINGS["alert_min_fit"]
    cands: list[tuple[int, float, str, dict]] = []

    def eligible(r):
        return r["eligibility"]["verdict"] != "Likely ineligible" and tracker.get(r["id"], {}).get("status") not in DONE_STATES

    for r in closing_soon(roles):
        if r["fit"] >= 3 and eligible(r):
            cands.append((0, days_until(r["deadline"]) or 0, "deadline_soon", r))
    for e in events:
        r = by_id.get(e["id"])
        if not r or not eligible(r):
            continue
        if e["event"] == "deadline_earlier" and r.get("deadline_confidence") == "Confirmed" and r["status"] == "Open":
            cands.append((1, -r["fit"], "deadline_earlier", r))
        elif bootstrap:
            continue  # first population of the database: no "new"/"opened" flood
        elif e["event"] == "opened" and r["type"] != "Entry-Level" and r["fit"] >= 3:
            cands.append((2, -r["fit"], "opened", r))
        elif e["event"] == "new" and r["status"] in ("Open", "Opens Soon"):
            if r["fit"] >= min_fit or (r["type"] in ("Graduate", "Summer Internship") and r["fit"] >= min_fit - 1
                                       and r["status"] == "Open"):
                kind = "opened" if r["type"] in ("Graduate", "Summer Internship", "Off-cycle Internship") else "new"
                cands.append((2 if kind == "opened" else 3, -r["fit"], kind, r))

    cands.sort(key=lambda c: (c[0], c[1]))
    out, used = [], set()
    for _, _, kind, r in cands:
        key = f"{kind}:{r['id']}:{r.get('deadline') or ''}"
        if key in sent or r["id"] in used:
            continue
        used.add(r["id"])
        out.append((kind, r, key))
    return out


def compose(kind: str, r: dict) -> tuple[str, str]:
    deadline = "No confirmed deadline"
    if r.get("deadline") and r.get("deadline_confidence") == "Confirmed":
        d = days_until(r["deadline"])
        deadline = f"{r['deadline']} (confirmed{', ' + str(d) + ' days left' if d is not None else ''})"
    elif r.get("rolling"):
        deadline = "Rolling — apply early"
    type_label = {"Graduate": "Graduate", "Summer Internship": "Internship (summer)",
                  "Off-cycle Internship": "Internship (off-cycle)"}.get(r["type"], "Entry-Level")
    subject = f"[{LABELS[kind]}] {r['company']} — {r['title']}"[:140]
    lines = [
        f"{LABELS[kind]}",
        "",
        f"Company: {r['company']}",
        f"Role: {r['title']}",
        f"Type: {type_label}",
        f"Fit score: {r['fit']}/5",
        f"Deadline: {deadline}",
        f"Location: {r['location'][:60]} ({r['work_arrangement']})",
        f"Suggested CV: {r['recommended_cv']}",
    ]
    if r.get("salary"):
        lines.append(f"Pay: {r['salary']}")
    if r["eligibility"]["verdict"] != "Likely eligible":
        lines.append(f"Eligibility: {r['eligibility']['verdict']} — {(r['eligibility']['issues'] or [''])[0][:120]}")
    lines += ["", f"Apply: {r['apply_url']}"]
    body = "\n".join(lines)
    words = body.split()
    if len(words) >= 200:
        body = " ".join(words[:190])
    return subject, body


class Gmail:
    def __init__(self):
        self.client_id = os.environ.get("GMAIL_CLIENT_ID")
        self.client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
        self.refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")
        self.to = os.environ.get("GMAIL_TO", "")
        self._token = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def _access_token(self) -> str:
        if self._token:
            return self._token
        r = requests.post(TOKEN_URL, data={"client_id": self.client_id, "client_secret": self.client_secret,
                                           "refresh_token": self.refresh_token, "grant_type": "refresh_token"}, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"Gmail token refresh failed: HTTP {r.status_code} {r.text[:200]}")
        self._token = r.json()["access_token"]
        return self._token

    def create_draft(self, subject: str, body: str) -> str:
        msg = EmailMessage()
        if self.to:
            msg["To"] = self.to
        msg["Subject"] = subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = requests.post(DRAFTS_URL, headers={"Authorization": f"Bearer {self._access_token()}"},
                          json={"message": {"raw": raw}}, timeout=20)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Draft creation failed: HTTP {r.status_code} {r.text[:200]}")
        return r.json().get("id", "")


def test_draft() -> int:
    """Create a single clearly-labelled test draft (manual workflow run with test_gmail=true)."""
    g = Gmail()
    if not g.configured:
        print("Gmail secrets not set")
        return 1
    g.create_draft("[Job dashboard] Gmail test draft",
                   "This is a test draft from your London job dashboard workflow. Drafts only — nothing is sent.")
    print("Test draft created")
    return 0


def run_alerts(events: list[dict], roles: list[dict], state: dict, tracker: dict, bootstrap: bool,
               gmail: Gmail | None = None) -> dict:
    gmail = gmail or Gmail()
    sent = state.setdefault("alerts_sent", {})
    picks = select_alerts(events, roles, sent, tracker, bootstrap)
    report = {"configured": gmail.configured, "candidates": len(picks), "drafted": 0, "errors": [], "at": now_iso()}
    if not picks:
        return report
    if not gmail.configured:
        report["errors"].append("Gmail not configured — alerts selected but no drafts created")
        return report
    for kind, r, key in picks[: SETTINGS["max_alert_drafts_per_run"]]:
        subject, body = compose(kind, r)
        try:
            gmail.create_draft(subject, body)
        except Exception as e:  # keep going; un-drafted alerts retry next run
            report["errors"].append(str(e)[:200])
            if "token refresh failed" in str(e).lower():
                break
            continue
        sent[key] = now_iso()
        report["drafted"] += 1
    # keep the ledger bounded
    if len(sent) > 5000:
        for k in sorted(sent, key=sent.get)[: len(sent) - 5000]:
            del sent[k]
    return report


if __name__ == "__main__":
    import sys
    sys.exit(test_draft())

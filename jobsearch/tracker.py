"""Read-only access to the PRIVATE application tracker (optional).

Application statuses and notes live in a separate private repository
(tracker.json), written by the dashboard from your own browser. The scheduled
job only reads it — to avoid alerting about roles you've already applied to —
and never copies any of it into public files.

Secrets: TRACKER_TOKEN (fine-grained PAT, Contents: read on that repo only),
TRACKER_REPO (e.g. "yourname/job-tracker-private").
"""
from __future__ import annotations

import base64
import json
import logging
import os

import requests

log = logging.getLogger(__name__)


def load_private_tracker() -> tuple[dict, str]:
    token, repo = os.environ.get("TRACKER_TOKEN"), os.environ.get("TRACKER_REPO")
    if not (token and repo):
        return {}, "not configured"
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/tracker.json",
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, timeout=20)
    except requests.RequestException as e:
        return {}, f"error: {e}"[:120]
    if r.status_code == 404:
        return {}, "tracker.json not created yet"
    if r.status_code != 200:
        return {}, f"HTTP {r.status_code}"
    try:
        data = json.loads(base64.b64decode(r.json()["content"]).decode())
        return data.get("roles", {}), f"ok ({len(data.get('roles', {}))} tracked)"
    except (ValueError, KeyError) as e:
        return {}, f"unreadable: {e}"[:120]

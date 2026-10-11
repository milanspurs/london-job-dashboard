"""Build the self-contained dashboard (site/index.html) from data/roles.json.

Only public vacancy data is embedded. Application statuses and notes are never
read here: the page loads them in your browser from your PRIVATE tracker repo
(or keeps them on-device only), so nothing personal is ever published.

Usage:  python build_dashboard.py [--out site]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from jobsearch import store  # noqa: E402

PUBLIC_FIELDS = (
    "id", "company", "title", "category", "category_label", "tier", "type", "location", "location_class",
    "location_confidence", "work_arrangement", "start_date", "opening_date", "opening_confidence", "deadline",
    "deadline_confidence", "deadline_evidence", "rolling", "cycle", "status", "status_reason", "fit", "why",
    "missing", "salary", "employment_type", "apply_url", "official", "official_source", "recommended_cv", "posted",
    "excerpt", "first_discovered", "last_verified", "last_seen", "experience_years",
)
ELIG_FIELDS = ("verdict", "graduation_years", "masters_eligible", "final_year_eligible", "return_to_study_required",
               "degree_class", "degree_subjects", "technical_requirements", "right_to_work", "issues")


def public_role(r: dict) -> dict:
    out = {k: r.get(k) for k in PUBLIC_FIELDS}
    out["eligibility"] = {k: (r.get("eligibility") or {}).get(k) for k in ELIG_FIELDS}
    out["sources"] = [{"source": s["source"].split(":")[0], "url": s.get("url"), "last_seen": s.get("last_seen")}
                      for s in r.get("sources", [])]
    out["history"] = [h for h in r.get("history", []) if h.get("field") in ("deadline", "status")][-6:]
    return out


def build(out_dir: str) -> str:
    db = store.load_roles()
    status = store.load_json("run_status.json", dict)
    last = status.get("last_run", {})
    payload = {
        "roles": [public_role(r) for r in db["roles"]],
        "generated": db.get("meta", {}).get("saved_at"),
        "last_successful_search": status.get("last_successful_search"),
        "last_run": {k: last.get(k) for k in ("finished", "duration_s", "new_roles", "raw_jobs", "sources",
                                                 "manual_sources", "new_employer_boards", "boards_active",
                                                 "companies", "events", "bootstrap")},
        "alerts": {k: (last.get("alerts") or {}).get(k) for k in ("configured", "drafted", "candidates")},
        "alert_errors": bool((last.get("alerts") or {}).get("configured") and (last.get("alerts") or {}).get("errors")),
        "run_history": status.get("history", [])[-36:],
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open(os.path.join(ROOT, "dashboard", "template.html"), encoding="utf-8") as f:
        html = f.read()
    if "/*__DATA__*/null" not in html:
        raise SystemExit("template placeholder missing")
    html = html.replace("/*__DATA__*/null", data)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    # GitHub Pages: disable Jekyll processing
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "site"))
    args = ap.parse_args()
    path = build(args.out)
    print(f"Dashboard written to {path}")

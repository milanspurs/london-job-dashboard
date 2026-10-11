"""Scheduled pipeline entry point:  python -m jobsearch.run

One run = discover -> evaluate -> merge -> re-verify -> status -> detect changes
-> alert drafts -> save. Each source is isolated: one failing never stops the
others, and every source's outcome is written to data/run_status.json.
"""
from __future__ import annotations

import dataclasses
import logging
import sys
import time
from datetime import datetime, timezone

from . import ai, store
from .alerts import run_alerts
from .changes import diff, snapshot
from .config import QUERIES, SETTINGS
from .http import Http
from .merge import Index, _authority, merge_observation
from .models import RawJob, now_iso
from .process import evaluate
from .sources import ats, registry
from .sources.aggregators import adzuna_search, reed_detail, reed_search
from .sources.base import MANUAL_SOURCES, SourceReport
from .status import set_status
from .tracker import load_private_tracker

log = logging.getLogger("jobsearch")


def _rotate(state: dict, key: str, n: int) -> list:
    cur = state.get(key, 0) % len(QUERIES)
    picked = [QUERIES[(cur + i) % len(QUERIES)] for i in range(n)]
    state[key] = (cur + n) % len(QUERIES)
    return picked


def raw_to_dict(j: RawJob) -> dict:
    d = dataclasses.asdict(j)
    d["description"] = d["description"][:8000]
    return d


def main(http: Http | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    started = time.time()
    http = http or Http()

    db = store.load_roles()
    reg = store.load_json("registry.json", registry.empty_registry)
    state = store.load_json("state.json", dict)
    raw_store = store.load_json("raw.json", dict)
    registry.ensure_seeded(reg)
    roles = db["roles"]
    bootstrap = len(roles) == 0
    before = snapshot(roles)
    reports: list[SourceReport] = []
    raw_jobs: list[RawJob] = []

    # ---- 1. Aggregator discovery (rotating query plan) -----------------------
    az_q = _rotate(state, "adzuna_cursor", SETTINGS["adzuna_calls_per_run"])
    rd_q = _rotate(state, "reed_cursor", SETTINGS["reed_calls_per_run"])
    for fn, args in ((adzuna_search, (http, az_q, state.setdefault("usage", {}))), (reed_search, (http, rd_q))):
        try:
            jobs, rep = fn(*args)
        except Exception as e:  # defensive: a connector bug must not stop the run
            jobs, rep = [], SourceReport(fn.__name__, "aggregator", ok=False)
            rep.fail(f"crashed: {e}")
            log.exception("connector crashed")
        raw_jobs += jobs
        reports.append(rep)
        log.info("%s: %d jobs, %d/%d calls failed", rep.name, rep.jobs_found, rep.failures, rep.calls)

    # ---- 2. Queue newly seen employers for board probing ---------------------
    new_companies = registry.enqueue_companies(reg, [j.company for j in raw_jobs])

    # ---- 3. Probe employers for public ATS boards (discovery of new employers)
    probe_rep = SourceReport("Employer board discovery", "probe")
    new_boards: list[str] = []
    for key, name in registry.next_probes(reg, SETTINGS["ats_probes_per_run"]):
        try:
            found = ats.probe_company(http, name)
            probe_rep.calls += 1
            new_boards += registry.record_probe(reg, key, name, found, via="probe")
        except Exception as e:
            probe_rep.fail(f"{name}: {e}")
    probe_rep.jobs_found = len(new_boards)
    probe_rep.note = f"{len(new_boards)} new employer boards found; {len(reg['queue'])} employers queued"
    reports.append(probe_rep)

    # ---- 4. Check employer boards (new boards first, then least-recently checked)
    board_ids = list(dict.fromkeys(new_boards + registry.boards_for_run(reg, SETTINGS["ats_boards_per_run"])))
    board_rep = SourceReport("Employer ATS boards (Greenhouse/Lever/Ashby/SmartRecruiters)", "ats")
    boards_ok: dict[str, set[str]] = {}
    sr_detail_budget = 25
    for bid in board_ids:
        b = reg["boards"][bid]
        board_rep.calls += 1
        try:
            st, jobs, res = ats.fetch_board(http, b["platform"], b["slug"], b["company"])
        except Exception as e:
            st, jobs = "error", []
            res = None
            log.exception("board %s crashed", bid)
        registry.record_board_check(reg, bid, st)
        if st == "ok":
            boards_ok[bid] = {j.source_id for j in jobs}
            for j in jobs:
                if b["platform"] == "smartrecruiters" and sr_detail_budget > 0 and "london" in j.location.lower():
                    ref = j.extra.get("detail_ref")
                    if ref:
                        j.description = ats.smartrecruiters_detail(http, ref)
                        j.full_text = bool(j.description)
                        sr_detail_budget -= 1
            raw_jobs += jobs
            board_rep.jobs_found += len(jobs)
        elif st == "error":
            board_rep.fail(f"{bid}: {getattr(res, 'error', '') or getattr(res, 'status', '')}")
    board_rep.note = f"{len(board_ids)} boards checked; {sum(1 for b in reg['boards'].values() if b['status']=='active')} active boards in registry"
    reports.append(board_rep)

    # ---- 5. Evaluate + merge ---------------------------------------------------
    idx = Index(roles)
    new_ids: set[str] = set()
    rejected: dict[str, int] = {}
    for j in raw_jobs:
        rec, why = evaluate(j)
        if rec is None:
            k = why.split("'")[0].split("(")[0].strip()[:50]
            rejected[k] = rejected.get(k, 0) + 1
            continue
        stored, is_new = merge_observation(roles, idx, rec)
        if is_new:
            new_ids.add(stored["id"])
        prev = raw_store.get(stored["id"])
        if prev is None or _authority(rec) >= (2 if prev.get("official") else 0) + (1 if prev.get("full_text") else 0):
            raw_store[stored["id"]] = raw_to_dict(j)

    # ---- 6. Re-verify Reed vacancies not seen this run --------------------------
    seen_this_run = {r["id"] for r in roles if r.get("last_seen", "") >= datetime.fromtimestamp(started, timezone.utc).isoformat()[:19]}
    reed_rep = SourceReport("Reed re-verification", "aggregator")
    reed_targets = sorted(
        (r for r in roles if r["status"] != "Closed" and r["id"] not in seen_this_run
         and any(s["source"] == "reed" for s in r["sources"])),
        key=lambda r: r.get("last_verified", ""))[: SETTINGS["reed_detail_checks_per_run"]]
    for r in reed_targets:
        sid = next(s["source_id"] for s in r["sources"] if s["source"] == "reed")
        state_, job = reed_detail(http, sid)
        reed_rep.calls += 1
        if state_ == "live" and job:
            rec, _ = evaluate(job)
            if rec:
                merge_observation(roles, idx, rec)
                raw_store[r["id"]] = raw_to_dict(job) if not raw_store.get(r["id"], {}).get("official") else raw_store[r["id"]]
        elif state_ == "gone":
            r["closed_evidence"] = "Removed from Reed (job listing no longer exists)"
        else:
            r["verify_failures"] = r.get("verify_failures", 0) + 1
            reed_rep.fail(f"job {sid}: unreachable")
    if reed_rep.calls:
        reports.append(reed_rep)

    # ---- 7. Employer-board absence (only after a SUCCESSFUL board fetch) --------
    for r in roles:
        for s in r["sources"]:
            if s["source"] in boards_ok and s["source_id"] not in boards_ok[s["source"]]:
                r["absent_count"] = r.get("absent_count", 0) + 1
                if r["absent_count"] >= 2:
                    r["closed_evidence"] = "Removed from the employer's own job board (confirmed on 2 checks)"

    # ---- 8. Recalculate fit/eligibility for every stored vacancy ---------------
    for r in roles:
        raw = raw_store.get(r["id"])
        if not raw or r["id"] in new_ids:
            continue
        try:
            rec, _ = evaluate(RawJob(**raw))
        except TypeError:
            continue
        if rec:
            for f in ("fit", "why", "missing", "eligibility", "category", "category_label", "tier", "type",
                      "recommended_cv", "work_arrangement", "cycle"):
                if f == "fit" and r.get("fit") != rec["fit"]:
                    r.setdefault("history", []).append({"at": now_iso(), "field": "fit", "from": r.get("fit"), "to": rec["fit"]})
                r[f] = rec[f]

    # ---- 9. Optional AI eligibility refinement (capped; off by default) -------
    ai_calls = ai.refine(http, [(r, raw_store.get(r["id"], {}).get("description", "")) for r in roles if r["id"] in new_ids],
                         SETTINGS["ai_max_calls_per_run"])

    # ---- 10. Status, changes, alerts -------------------------------------------
    for r in roles:
        set_status(r)
    events = diff(before, roles, new_ids)
    tracker, tracker_note = load_private_tracker()
    alert_report = run_alerts(events, roles, state, tracker, bootstrap)

    # ---- 11. Save ----------------------------------------------------------------
    known_companies = {r["company"] for r in roles}
    status_doc = store.load_json("run_status.json", dict)
    finished = now_iso()
    any_source_ok = any(rep.to_dict()["ok"] and rep.calls > 0 for rep in reports)
    run_summary = {
        "started": datetime.fromtimestamp(started, timezone.utc).replace(microsecond=0).isoformat(),
        "finished": finished,
        "duration_s": round(time.time() - started, 1),
        "bootstrap": bootstrap,
        "raw_jobs": len(raw_jobs),
        "new_roles": len(new_ids),
        "new_companies_queued": new_companies,
        "new_employer_boards": len(new_boards),
        "rejected": dict(sorted(rejected.items(), key=lambda kv: -kv[1])[:12]),
        "events": {k: sum(1 for e in events if e["event"] == k) for k in {e["event"] for e in events}},
        "alerts": alert_report,
        "tracker": tracker_note,
        "ai_calls": ai_calls,
        "http_calls": http.calls,
        "sources": [rep.to_dict() for rep in reports],
        "manual_sources": [{"name": n, "url": u, "why": w} for n, u, w in MANUAL_SOURCES],
        "total_roles": len(roles),
        "companies": len(known_companies),
        "boards_active": sum(1 for b in reg["boards"].values() if b["status"] == "active"),
    }
    status_doc["last_run"] = run_summary
    if any_source_ok:
        status_doc["last_successful_search"] = finished
    status_doc["history"] = (status_doc.get("history", []) + [
        {"at": finished, "new": len(new_ids), "raw": len(raw_jobs), "ok": any_source_ok}])[-120:]

    # keep raw text only for vacancies still in the database
    live_ids = {r["id"] for r in roles}
    raw_store = {k: v for k, v in raw_store.items() if k in live_ids}

    try:
        store.save_roles(db)
    except ValueError as e:
        log.error("%s", e)
        status_doc["last_run"]["fatal"] = str(e)[:300]
        store.save_json("run_status.json", status_doc)
        return 1
    store.save_json("raw.json", raw_store)
    store.save_json("registry.json", reg)
    store.save_json("state.json", state)
    store.save_json("run_status.json", status_doc)
    store.append_events(events)
    log.info("Done: %d roles (%d new), %d events, %d drafts, %.0fs", len(roles), len(new_ids), len(events),
             alert_report["drafted"], time.time() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main())

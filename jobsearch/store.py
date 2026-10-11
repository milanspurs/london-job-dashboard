"""Durable JSON persistence.

* writes go to a temp file, are fsync'd and atomically renamed into place
* the previous version is kept as <name>.bak.json for recovery
* a corrupt file is recovered from its backup instead of being overwritten
* roles.json is validated before every write; an invalid database is never saved

GitHub Actions then commits the data/ directory back to the repository, so the
repository history itself is the long-term store (every run is a recoverable
commit).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone

from .config import DATA_DIR as _DEFAULT_DATA_DIR

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
REQUIRED_FIELDS = ("id", "company", "title", "category", "type", "status", "fit", "apply_url",
                   "first_discovered", "last_verified")
STATUSES = ("Open", "Opens Soon", "Verify", "Watch", "Closed")


def data_dir() -> str:
    return os.environ.get("JOBS_DATA_DIR", _DEFAULT_DATA_DIR)


def path(name: str) -> str:
    return os.path.join(data_dir(), name)


def load_json(name: str, default):
    p = path(name)
    for candidate in (p, p.replace(".json", ".bak.json")):
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, encoding="utf-8") as f:
                data = json.load(f)
            if candidate != p:
                log.warning("Recovered %s from backup", name)
            return data
        except (OSError, json.JSONDecodeError) as e:
            log.error("Could not read %s: %s", candidate, e)
    return default() if callable(default) else default


def save_json(name: str, data) -> None:
    os.makedirs(data_dir(), exist_ok=True)
    p = path(name)
    fd, tmp = tempfile.mkstemp(dir=data_dir(), prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(p):
            shutil.copy2(p, p.replace(".json", ".bak.json"))
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def validate_roles(db: dict) -> list[str]:
    errs = []
    if not isinstance(db, dict) or not isinstance(db.get("roles"), list):
        return ["roles.json must be an object with a 'roles' list"]
    seen = set()
    for i, r in enumerate(db["roles"]):
        for f in REQUIRED_FIELDS:
            if f not in r:
                errs.append(f"role {i} missing {f}")
        if r.get("status") not in STATUSES:
            errs.append(f"role {r.get('id')} bad status {r.get('status')}")
        if not isinstance(r.get("fit"), int) or not 1 <= r["fit"] <= 5:
            errs.append(f"role {r.get('id')} bad fit {r.get('fit')}")
        if r.get("id") in seen:
            errs.append(f"duplicate id {r.get('id')}")
        seen.add(r.get("id"))
    return errs[:20]


def load_roles() -> dict:
    db = load_json("roles.json", lambda: {"meta": {"schema": SCHEMA_VERSION}, "roles": []})
    db.setdefault("meta", {"schema": SCHEMA_VERSION})
    db.setdefault("roles", [])
    return db


def save_roles(db: dict) -> None:
    errs = validate_roles(db)
    if errs:
        raise ValueError("Refusing to save invalid roles.json: " + "; ".join(errs))
    db["meta"]["schema"] = SCHEMA_VERSION
    db["meta"]["count"] = len(db["roles"])
    db["meta"]["saved_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    save_json("roles.json", db)


def append_events(events: list[dict]) -> None:
    if not events:
        return
    os.makedirs(path("events"), exist_ok=True)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with open(path(f"events/{month}.jsonl"), "a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

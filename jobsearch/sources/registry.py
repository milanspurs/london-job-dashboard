"""Employer board registry: which employers have a public ATS board, and the
rotation that decides which boards are checked and which employers are probed
on each run.

The registry grows by itself: every employer seen in Adzuna/Reed results is
queued for probing, so the set of directly-monitored employers keeps expanding
beyond any fixed list.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..models import norm_company, now_iso

# Starter queue of London employers to probe (names only — the probe decides
# whether a public board exists). Big banks and Big Four firms mostly use
# Workday/Oracle portals with no public API; they are reached via Adzuna/Reed.
SEED_EMPLOYERS = [
    # consulting / advisory / boutiques
    "Oliver Wyman", "OC&C Strategy Consultants", "LEK Consulting", "Simon-Kucher", "Kearney", "Capco",
    "Elixirr", "Baringa Partners", "Credera", "Sia Partners", "Frontier Economics", "Oxera", "NERA Economic Consulting",
    "Cornerstone Research", "Analysis Group", "Charles River Associates", "Compass Lexecon", "FTI Consulting",
    "Alvarez & Marsal", "Berkeley Research Group", "Huron", "Cambridge Econometrics", "Economic Insight", "Europe Economics",
    "Newton Europe", "Moorhouse Consulting", "Bain", "Teneo", "Grant Thornton", "Mazars", "BDO",
    # finance / fintech / investment
    "Monzo", "GoCardless", "Wise", "Revolut", "Starling Bank", "Checkout.com", "Lendable", "Zopa", "Funding Circle",
    "Marshall Wace", "Man Group", "Schroders", "Ninety One", "M&G", "Legal & General", "Aviva Investors", "Baillie Gifford",
    "Jupiter Asset Management", "Liontrust", "Ruffer", "Brevan Howard", "Qube Research & Technologies", "Squarepoint Capital",
    "Gresham House", "Octopus Group", "Hargreaves Lansdown", "PIMCO", "Moody's", "S&P Global", "Fitch Ratings", "MSCI",
    "Morningstar", "LSEG", "Bloomberg", "Clearwater Analytics", "Preqin", "PitchBook", "Kroll",
    # insurance / reinsurance / risk
    "Beazley", "Hiscox", "Lloyd's", "Aon", "WTW", "Gallagher", "Howden", "Markel", "Chaucer", "Canopius", "Brit Insurance",
    "Arch Insurance", "Ascot Group", "Hamilton Insurance", "QBE", "Zurich", "Allianz", "AXA", "RMS", "Verisk",
    "Hymans Robertson", "Lane Clark & Peacock", "Barnett Waddingham", "Hannover Re", "Swiss Re", "Munich Re",
    "Cytora", "Concirrus", "Flock", "Marshmallow", "Zego", "Superscript",
    # energy / commodities / ESG
    "Octopus Energy", "OVO", "Ofgem", "National Grid", "Centrica", "SSE", "EDF Energy", "Ørsted", "RWE", "bp",
    "Shell", "Argus Media", "ICIS", "Wood Mackenzie", "Aurora Energy Research", "Cornwall Insight", "Kraken",
    "Sustainalytics", "Carbon Trust", "Anthesis", "ERM", "Ricardo", "Ramboll", "WSP", "Arup", "AECOM", "Mott MacDonald",
    "Jacobs", "Stantec", "Atkins", "Sweco", "Steer", "Systra", "Greengage", "Sylvera", "Watershed", "Normative",
    "Persefoni", "Planet Mark", "Accenture", "Trucost", "Climate Policy Initiative", "ClientEarth", "Ember",
    # research / insight / tech & product analytics
    "Ipsos", "YouGov", "Kantar", "Savanta", "Dynata", "Opinium", "GfK", "Euromonitor", "Mintel", "Oxford Economics",
    "Capital Economics", "Deliveroo", "Ocado", "Just Eat Takeaway", "Gousto", "Skyscanner", "Trainline", "Citymapper",
    "Bolt", "Faculty", "Palantir", "Thought Machine", "Tide", "Cleo", "Paddle", "Primer", "Multiverse", "Snyk",
    "ComplyAdvantage", "Quantexa", "Tractable", "Onfido", "Synthesia", "Wayve", "Graphcore", "Elliptic", "Chainalysis",
    # patents / science-led
    "Mewburn Ellis", "Marks & Clerk", "Venner Shipley", "J A Kemp", "Carpmaels & Ransford", "Withers & Rogers",
    "D Young & Co", "HGF", "Boult Wade Tennant", "Potter Clarkson", "Haseltine Lake Kempner", "Abel + Imray",
    # transport / infrastructure / public
    "Transport for London", "Network Rail", "HS2", "Heathrow", "National Highways", "Thames Water", "UK Power Networks",
    "Places for London", "Greater London Authority", "Bank of England", "Financial Conduct Authority", "Ofwat", "CMA",
    "Office for National Statistics", "Institute for Fiscal Studies", "Resolution Foundation", "NIESR",
]


def empty_registry() -> dict:
    return {"boards": {}, "probed": {}, "queue": []}


def ensure_seeded(reg: dict) -> None:
    known = set(reg["queue"]) | set(reg["probed"].keys())
    for name in SEED_EMPLOYERS:
        k = norm_company(name)
        if k and k not in known:
            reg["queue"].append(k)
            reg.setdefault("names", {})[k] = name
            known.add(k)


def enqueue_companies(reg: dict, companies: list[str]) -> int:
    """Queue employers seen in aggregator results for probing. Returns how many were new."""
    known = set(reg["queue"]) | set(reg["probed"].keys())
    added = 0
    for name in companies:
        k = norm_company(name)
        if not k or k in known or len(k) < 3:
            continue
        reg["queue"].append(k)
        reg.setdefault("names", {})[k] = name
        known.add(k)
        added += 1
    return added


def next_probes(reg: dict, n: int) -> list[tuple[str, str]]:
    """Pop up to n employers to probe; also re-probe misses older than 60 days."""
    out = []
    while reg["queue"] and len(out) < n:
        k = reg["queue"].pop(0)
        out.append((k, reg.get("names", {}).get(k, k)))
    if len(out) < n:
        cutoff = (date.today() - timedelta(days=60)).isoformat()
        stale = sorted((v["last"], k) for k, v in reg["probed"].items() if not v.get("found") and v["last"] < cutoff)
        for _, k in stale[: n - len(out)]:
            out.append((k, reg.get("names", {}).get(k, k)))
    return out


def record_probe(reg: dict, key: str, company: str, found: list[dict], via: str) -> list[str]:
    reg["probed"][key] = {"last": date.today().isoformat(), "found": [f"{f['platform']}:{f['slug']}" for f in found]}
    added = []
    for f in found:
        bid = f"{f['platform']}:{f['slug']}"
        if bid not in reg["boards"]:
            reg["boards"][bid] = {"platform": f["platform"], "slug": f["slug"], "company": company,
                                  "status": "active", "fail_count": 0, "missing_count": 0,
                                  "last_checked": None, "last_ok": None, "discovered": now_iso(), "via": via}
            added.append(bid)
    return added


def boards_for_run(reg: dict, n: int) -> list[str]:
    """Least-recently-checked active boards first, so every board is cycled."""
    active = [(b.get("last_checked") or "", bid) for bid, b in reg["boards"].items() if b["status"] == "active"]
    active.sort()
    return [bid for _, bid in active[:n]]


def record_board_check(reg: dict, bid: str, state: str) -> None:
    b = reg["boards"][bid]
    b["last_checked"] = now_iso()
    if state == "ok":
        b["last_ok"] = b["last_checked"]
        b["fail_count"] = 0
        b["missing_count"] = 0
    elif state == "missing":
        b["missing_count"] = b.get("missing_count", 0) + 1
        if b["missing_count"] >= 3:
            b["status"] = "removed"  # board deleted on the platform; definitive after 3 checks
    else:
        b["fail_count"] = b.get("fail_count", 0) + 1

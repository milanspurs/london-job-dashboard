"""Static configuration: candidate profile, categories, search queries, exclusions.

Nothing in this file is private. Contact details, application notes and
credentials never live in the repository.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Candidate profile (derived from the 10 tailored CVs; no contact details)
# ---------------------------------------------------------------------------
PROFILE = {
    "degrees": ["BSc Chemistry (2:1), 2024", "MSc Risk Analytics (QMUL), completing 2027"],
    "graduation_years": [2024, 2027],  # BSc finished 2024; MSc finishes 2027
    "msc_end_year": 2027,
    "degree_class": "2:1",
    "stem": True,
    "strengths": [
        "risk", "analytics", "data", "excel", "quantitative", "insurance", "actuarial",
        "financial", "markets", "chemistry", "science", "scientific", "research",
        "sustainability", "esg", "climate", "energy", "operations", "commercial",
        "pricing", "market research", "supervis", "stakeholder", "statistic",
        "optimisation", "optimization", "reporting", "business intelligence",
    ],
    # Skills present but at beginner level -> a "strong" requirement is a gap
    "beginner_skills": ["python", "sql", "power bi"],
    # Skills not held -> a hard requirement is a gap
    "missing_skills": ["vba", "tableau", "r programming", "c++", "java", "sas certified",
                       "cfa", "aca", "acca", "cima", "financial modelling experience",
                       "dcf", "lbo", "matlab", "gis", "arcgis", "autocad", "visum", "saturn"],
}

# ---------------------------------------------------------------------------
# Career categories, tiers and CV mapping
# ---------------------------------------------------------------------------
CV = {
    "strategy": "Strategy & Consulting CV",
    "data": "Data Analytics CV",
    "risk": "Risk Management CV",
    "finance": "Finance & Investment CV",
    "esg": "Sustainability & ESG CV",
    "energy": "Energy & Climate CV",
    "commercial": "Market Research & Commercial CV",
    "ops": "Operations & Project Management CV",
    "grad": "Graduate Programmes CV",
    "transport": "Transport & Infrastructure CV",
}

CATEGORIES = {
    "strategy": {
        "label": "Strategy & Management Consulting", "tier": 1, "cv": CV["strategy"],
        "keywords": ["consult", "strategy", "strategic", "advisory", "management consultant",
                     "deal advisory", "transaction services", "business advisory"],
    },
    "data": {
        "label": "Data Analytics & BI", "tier": 1, "cv": CV["data"],
        "keywords": ["data analyst", "data analytics", "business intelligence", " bi ", "insight analyst",
                     "reporting analyst", "mi analyst", "analytics", "power bi", "sql", "data science",
                     "data scientist"],
    },
    "risk": {
        "label": "Risk, Insurance & Actuarial", "tier": 1, "cv": CV["risk"],
        "keywords": ["risk", "actuar", "insurance", "underwrit", "reinsurance", "claims analyst",
                     "credit analyst", "compliance analyst", "lloyd", "catastrophe", "pricing analyst",
                     "exposure management", "model validation"],
    },
    "finance": {
        "label": "Finance, Investment & Asset Management", "tier": 1, "cv": CV["finance"],
        "keywords": ["investment", "asset management", "fund", "equity", "portfolio", "banking",
                     "financial analyst", "finance analyst", "markets", "trading", "wealth",
                     "private equity", "capital", "treasury", "audit", "valuation", "fp&a"],
    },
    "esg": {
        "label": "ESG, Sustainability & Environmental", "tier": 1, "cv": CV["esg"],
        "keywords": ["esg", "sustainab", "environmental", "climate", "net zero", "carbon",
                     "decarbon", "circular economy", "biodiversity", "responsible investment"],
    },
    "energy": {
        "label": "Energy, Utilities & Commodities", "tier": 2, "cv": CV["energy"],
        "keywords": ["energy", "renewable", "utilit", "power", "commodit", "oil", "gas", "lng",
                     "solar", "wind", "hydrogen", "electricity", "grid", "price reporter",
                     "battery", "metals", "petrochemical", "chemicals market"],
    },
    "commercial": {
        "label": "Commercial, Market Research & Insights", "tier": 2, "cv": CV["commercial"],
        "keywords": ["commercial", "market research", "research executive", "insight", "pricing",
                     "category analyst", "consumer", "customer insight", "revenue", "market analyst",
                     "competitive intelligence"],
    },
    "ops": {
        "label": "Operations, Transformation & Project Mgmt", "tier": 2, "cv": CV["ops"],
        "keywords": ["operations", "transformation", "project", "programme", "pmo", "process improvement",
                     "supply chain", "logistics", "change analyst", "business analyst", "procurement"],
    },
    "tech": {
        "label": "Technology Consulting & Product Analytics", "tier": 2, "cv": CV["data"],
        "keywords": ["technology consult", "digital", "product analyst", "product analytics", "tech consult",
                     "it consult", "digital transformation", "systems analyst"],
    },
    "transport": {
        "label": "Transport, Infrastructure & Planning", "tier": 3, "cv": CV["transport"],
        "keywords": ["transport", "infrastructure", "planning", "rail", "highways", "aviation",
                     "urban", "mobility", "transport planner", "property", "real estate", "construction"],
    },
    "policy": {
        "label": "Economic Research, Policy & Regulation", "tier": 3, "cv": CV["data"],
        "keywords": ["economist", "economic", "policy", "regulat", "public affairs", "research analyst",
                     "think tank", "government", "civil service", "ofgem", "fca", "ofwat", "statistician"],
    },
    "other": {
        "label": "Other Relevant (incl. science-led paths)", "tier": 3, "cv": CV["grad"],
        "keywords": ["patent", "technical analyst", "scientific", "chemist", "regulatory affairs",
                     "graduate scheme", "graduate programme", "rotational", "management trainee",
                     "graduate trainee", "chemical", "laboratory analyst", "qa analyst"],
    },
}

# Science-heavy "other" paths are better served by a CV with the full dissertation detail
SCIENCE_CV_TERMS = ["patent", "chemist", "chemical", "scientific", "regulatory affairs", "laboratory"]

# ---------------------------------------------------------------------------
# Search queries (rotated across runs). Each tuple: (query text, hint)
# hint: "grad" | "intern" | "entry"
# ---------------------------------------------------------------------------
_BASE_TITLES = {
    "strategy": ["graduate consultant", "junior consultant", "strategy analyst", "graduate management consultant",
                 "consulting analyst", "business advisory graduate"],
    "data": ["graduate data analyst", "junior data analyst", "business intelligence analyst graduate",
             "insight analyst graduate", "reporting analyst junior", "data analyst entry level"],
    "risk": ["graduate risk analyst", "junior risk analyst", "actuarial graduate", "insurance graduate scheme",
             "underwriting assistant", "graduate underwriter", "credit risk analyst graduate",
             "catastrophe modelling graduate", "operational risk analyst junior", "pricing analyst graduate"],
    "finance": ["graduate investment analyst", "junior investment analyst", "asset management graduate",
                "graduate financial analyst", "investment operations graduate", "junior analyst fund",
                "fund accounting graduate", "graduate analyst bank"],
    "esg": ["graduate sustainability consultant", "esg analyst graduate", "junior esg analyst",
            "environmental consultant graduate", "climate risk analyst", "sustainability analyst junior",
            "carbon analyst graduate"],
    "energy": ["energy analyst graduate", "junior energy analyst", "commodities analyst graduate",
               "price reporter graduate", "renewable energy graduate", "energy trading graduate",
               "utilities graduate scheme"],
    "commercial": ["research executive", "market research graduate", "commercial analyst graduate",
                   "junior commercial analyst", "pricing analyst junior", "insights executive"],
    "ops": ["graduate business analyst", "junior business analyst", "project analyst graduate",
            "operations analyst graduate", "transformation analyst graduate", "pmo analyst junior",
            "supply chain analyst graduate"],
    "tech": ["technology consultant graduate", "digital consultant graduate", "product analyst junior",
             "graduate technology analyst"],
    "transport": ["graduate transport planner", "transport consultant graduate", "infrastructure graduate",
                  "graduate infrastructure analyst"],
    "policy": ["graduate economist", "junior economist", "policy analyst graduate", "regulatory analyst graduate",
               "research analyst graduate", "junior research analyst"],
    "other": ["trainee patent attorney", "graduate scheme 2027", "graduate programme london",
              "management trainee graduate", "regulatory affairs graduate", "msc graduate analyst",
              "graduate analyst", "graduate trainee analyst"],
}

_INTERN_TERMS = ["summer internship 2027", "summer analyst 2027", "summer intern", "internship 2027",
                 "off-cycle internship", "summer associate", "placement 2027"]
_INTERN_AREAS = ["consulting", "risk", "investment", "data analytics", "sustainability", "energy",
                 "insurance", "commercial", "operations", "research", "infrastructure", "technology",
                 "actuarial", "asset management", "economics"]


def build_queries() -> list[tuple[str, str, str]]:
    """Return (query, hint, category) for the rotating search plan."""
    qs: list[tuple[str, str, str]] = []
    for cat, titles in _BASE_TITLES.items():
        for t in titles:
            hint = "grad" if "graduate" in t or "trainee" in t or "scheme" in t else "entry"
            qs.append((t, hint, cat))
    for area in _INTERN_AREAS:
        for term in ("summer internship", "internship 2027"):
            qs.append((f"{area} {term}", "intern", "other"))
    for term in _INTERN_TERMS:
        qs.append((term, "intern", "other"))
    # Tier-1 categories are searched twice as often
    tier1 = [q for q in qs if CATEGORIES[q[2]]["tier"] == 1]
    return qs + tier1


QUERIES = build_queries()

# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------
LONDON_TERMS = [
    "london", "city of london", "canary wharf", "westminster", "camden", "islington", "hackney",
    "tower hamlets", "southwark", "lambeth", "wandsworth", "hammersmith", "fulham", "kensington",
    "chelsea", "greenwich", "lewisham", "newham", "barking", "dagenham", "havering", "redbridge",
    "waltham forest", "haringey", "enfield", "barnet", "harrow", "brent", "ealing", "hounslow",
    "hillingdon", "richmond upon thames", "kingston upon thames", "merton", "sutton", "croydon",
    "bromley", "bexley", "stratford", "shoreditch", "holborn", "farringdon", "king's cross",
    "kings cross", "paddington", "victoria", "mayfair", "soho", "moorgate", "liverpool street",
    "bank", "aldgate", "southbank", "south bank", "battersea", "wembley", "uxbridge", "heathrow",
    "whitechapel", "clerkenwell", "fitzrovia", "marylebone", "st james", "covent garden",
]
# Practical commuter locations: kept, but labelled "Commuter belt"
COMMUTER_TERMS = [
    "watford", "st albans", "reading", "slough", "guildford", "woking", "epsom", "dartford",
    "brentwood", "chelmsford", "hemel hempstead", "welwyn", "hatfield", "stevenage", "luton",
    "maidenhead", "staines", "weybridge", "leatherhead", "redhill", "reigate", "sevenoaks",
    "tunbridge wells", "basildon", "harlow", "cheshunt", "bracknell", "crawley", "gatwick",
]
NON_UK_TERMS = ["new york", "united states", ", us", "usa", "dublin", "paris", "frankfurt",
                "amsterdam", "zurich", "singapore", "hong kong", "toronto", "london, on",
                "london, ontario", "london, ky", "london, oh", "new london", "dubai", "sydney"]

# ---------------------------------------------------------------------------
# Exclusions
# ---------------------------------------------------------------------------
EXCLUDE_TITLE_PATTERNS = [
    r"recruit(er|ment|ing)\b", r"talent acquisition", r"head ?hunt", r"resourcer", r"\bsourcer\b",
    r"talent partner", r"staffing", r"door[- ]to[- ]door", r"telesales", r"cold[- ]call",
    r"estate agent", r"lettings", r"property negotiator", r"sales negotiator", r"field sales",
    r"restaurant", r"\bchef\b", r"bar (staff|manager|supervisor)", r"waiter|waitress|barista",
    r"hospitality (manager|supervisor)", r"store manager", r"shop manager", r"retail (assistant|manager|supervisor)",
    r"sales assistant", r"call cent(re|er)", r"customer service (advisor|adviser|representative|agent)",
    r"contact cent(re|er)", r"sales (consultant|executive|representative|rep|advisor|adviser|associate|agent)",
    r"business development (representative|executive|associate)", r"\b(sdr|bdr)\b", r"account executive", r"\bsenior\b", r"\bsnr\b", r"\bsr\.?\b", r"\blead\b", r"\bprincipal\b",
    r"\bhead of\b", r"\bdirector\b", r"\bvp\b", r"vice president", r"\bchief\b", r"\bpartner\b(?! programme)",
    r"\bmanaging\b", r"\bexperienced\b",
    r"software (engineer|developer)", r"\bdeveloper\b", r"devops", r"site reliability", r"\bsre\b",
    r"back[- ]?end", r"front[- ]?end", r"full[- ]?stack", r"machine learning engineer", r"ml engineer",
    r"platform engineer", r"data engineer", r"cloud engineer", r"security engineer", r"infrastructure engineer",
    r"teacher", r"teaching assistant", r"nurse", r"care assistant", r"driver\b", r"warehouse",
    r"cleaner", r"security officer", r"receptionist",
]
# "manager" alone is senior unless clearly junior/trainee
MANAGER_OK = r"(graduate|trainee|assistant|junior|associate) .*manager|manager.*(graduate|trainee|programme)"

EXCLUDE_TEXT_PATTERNS = [
    r"commission[- ]only", r"commission based only", r"\bunpaid\b", r"expenses only", r"voluntary role",
    r"self[- ]employed sales", r"\b(outside|inside) ir35\b", r"\bper day\b|\bday rate\b",
]

MAX_EXPERIENCE_YEARS = 2

# ---------------------------------------------------------------------------
# Runtime settings (overridable via environment)
# ---------------------------------------------------------------------------
def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


SETTINGS = {
    "adzuna_calls_per_run": env_int("ADZUNA_CALLS_PER_RUN", 6),
    "adzuna_monthly_cap": env_int("ADZUNA_MONTHLY_CAP", 2400),
    "reed_calls_per_run": env_int("REED_CALLS_PER_RUN", 16),
    "reed_detail_checks_per_run": env_int("REED_DETAIL_CHECKS_PER_RUN", 40),
    "ats_boards_per_run": env_int("ATS_BOARDS_PER_RUN", 60),
    "ats_probes_per_run": env_int("ATS_PROBES_PER_RUN", 12),
    "max_alert_drafts_per_run": env_int("MAX_ALERT_DRAFTS_PER_RUN", 8),
    "alert_min_fit": env_int("ALERT_MIN_FIT", 4),
    "ai_max_calls_per_run": env_int("AI_MAX_CALLS_PER_RUN", 0),  # 0 = AI classification off
    "watch_after_days_unseen": env_int("WATCH_AFTER_DAYS_UNSEEN", 10),
    "search_radius_miles": env_int("SEARCH_RADIUS_MILES", 15),
    "max_days_old": env_int("MAX_DAYS_OLD", 21),
    "http_timeout": env_int("HTTP_TIMEOUT", 20),
}

DATA_DIR = os.environ.get("JOBS_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

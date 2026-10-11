"""Common pieces for source connectors."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import now_iso


@dataclass
class SourceReport:
    """What happened when we checked one source during this run."""
    name: str
    kind: str                 # aggregator | ats | probe | manual
    ok: bool = True
    calls: int = 0
    failures: int = 0
    jobs_found: int = 0
    errors: list = field(default_factory=list)
    note: str = ""
    checked_at: str = field(default_factory=now_iso)

    def fail(self, msg: str) -> None:
        self.failures += 1
        if len(self.errors) < 5:
            self.errors.append(msg[:200])

    def to_dict(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "ok": self.ok and (self.calls == 0 or self.failures < self.calls),
            "calls": self.calls, "failures": self.failures, "jobs_found": self.jobs_found,
            "errors": self.errors, "note": self.note, "checked_at": self.checked_at,
        }


# Sources that have no permitted automated access. Shown on the dashboard as
# manual-check links so they are recorded rather than silently skipped.
MANUAL_SOURCES = [
    ("Indeed", "https://uk.indeed.com/jobs?q=graduate+analyst&l=London", "No public search API; automated scraping prohibited by terms."),
    ("LinkedIn Jobs", "https://www.linkedin.com/jobs/search/?keywords=graduate%20analyst&location=London", "No permitted API for job search."),
    ("Bright Network", "https://www.brightnetwork.co.uk/search/?content_types=jobs", "No public API; terms restrict automated access."),
    ("targetjobs", "https://targetjobs.co.uk/search/graduate-jobs?location=london", "No public API."),
    ("Prospects", "https://www.prospects.ac.uk/graduate-jobs", "No public API."),
    ("Gradcracker", "https://www.gradcracker.com/search/all-disciplines/graduate-jobs", "No public API; STEM-focused, worth checking for science-led roles."),
    ("RateMyPlacement", "https://www.ratemyplacement.co.uk/search?jobType=internship", "No public API."),
    ("eFinancialCareers", "https://www.efinancialcareers.co.uk/jobs-UK-London-graduate.htm", "No public API."),
    ("Civil Service Jobs", "https://www.civilservicejobs.service.gov.uk/csr/index.cgi", "No public API; search requires a session."),
    ("Civil Service Fast Stream", "https://www.faststream.gov.uk/", "Official programme site; annual cycle."),
]

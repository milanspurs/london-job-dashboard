"""Synthetic API payloads used ONLY by tests (never written to the real data/ folder)."""
from __future__ import annotations

import os
import re
import tempfile
from datetime import date, timedelta

from jobsearch.http import FetchResult

FUTURE = (date.today() + timedelta(days=10))
FAR = (date.today() + timedelta(days=40))


def adzuna_payload():
    return {"results": [
        {"id": 111, "title": "Graduate Risk Analyst", "company": {"display_name": "Testco Insurance"},
         "location": {"display_name": "Canary Wharf, London", "area": ["UK", "London", "Canary Wharf"]},
         "description": "Join our 2027 graduate programme. Open to 2026 and 2027 graduates including MSc students...",
         "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/111", "created": "2026-10-09T10:00:00Z",
         "salary_min": 32000, "salary_max": 32000, "salary_is_predicted": "1"},
        {"id": 112, "title": "Senior Recruitment Consultant", "company": {"display_name": "Hire Ltd"},
         "location": {"display_name": "London", "area": ["UK", "London"]}, "description": "Uncapped commission",
         "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/112", "created": "2026-10-09T10:00:00Z"},
        {"id": 113, "title": "Junior Data Analyst", "company": {"display_name": "Alpha Analytics"},
         "location": {"display_name": "New York, US", "area": ["US", "New York"]}, "description": "x",
         "redirect_url": "https://www.adzuna.co.uk/jobs/land/ad/113", "created": "2026-10-09T10:00:00Z"},
    ]}


def reed_payload():
    return {"results": [
        {"jobId": 501, "employerName": "Greenbridge Consulting", "jobTitle": "Graduate Sustainability Consultant",
         "locationName": "London", "minimumSalary": 30000, "maximumSalary": 33000,
         "expirationDate": FAR.strftime("%d/%m/%Y"), "date": "09/10/2026",
         "jobDescription": "Graduate role for STEM graduates (2:1). Hybrid working in London.",
         "jobUrl": "https://www.reed.co.uk/jobs/graduate-sustainability-consultant/501"},
        {"jobId": 502, "employerName": "Bigcorp", "jobTitle": "Risk Analyst", "locationName": "London",
         "expirationDate": FAR.strftime("%d/%m/%Y"), "date": "09/10/2026",
         "jobDescription": "You will have 5+ years of experience in market risk.",
         "jobUrl": "https://www.reed.co.uk/jobs/risk-analyst/502"},
    ]}


def greenhouse_payload(include_intern=True):
    jobs = [{"id": 9001, "title": "Graduate Analyst, Strategy (2027 start)",
             "location": {"name": "London, UK"}, "absolute_url": "https://boards.greenhouse.io/examplefirm/jobs/9001",
             "updated_at": "2026-10-01T00:00:00Z", "first_published": "2026-10-01T00:00:00Z",
             "content": ("&lt;p&gt;Our graduate programme is open to final-year and master's students graduating in 2027. "
                         f"Applications close on {FUTURE.day} {FUTURE.strftime('%B %Y')}. Hybrid, London.&lt;/p&gt;")}]
    if include_intern:
        jobs.append({"id": 9002, "title": "Summer Analyst Internship 2027", "location": {"name": "London"},
                     "absolute_url": "https://boards.greenhouse.io/examplefirm/jobs/9002", "updated_at": "2026-10-01T00:00:00Z",
                     "content": "Penultimate-year students who will return to university after the internship. "
                                "Deadline: 30 November 2026."})
    jobs.append({"id": 9003, "title": "Graduate Analyst", "location": {"name": "Paris, France"},
                 "absolute_url": "https://boards.greenhouse.io/examplefirm/jobs/9003", "content": "Paris office"})
    return {"jobs": jobs}


class FakeHttp:
    """Routes URLs to canned responses. `down` makes every request fail."""

    def __init__(self, down=False, gh_intern=True):
        self.down = down
        self.gh_intern = gh_intern
        self.calls = {}
        self.log = []

    def get(self, url, **kw):
        self.log.append(url)
        if self.down:
            return FetchResult(ok=False, error="ConnectionError: simulated outage", attempts=3)
        if "adzuna" in url:
            return FetchResult(ok=True, status=200, data=adzuna_payload())
        if "reed.co.uk/api/1.0/search" in url:
            return FetchResult(ok=True, status=200, data=reed_payload())
        if "reed.co.uk/api/1.0/jobs/" in url:
            return FetchResult(ok=True, status=404)
        if re.search(r"greenhouse\.io/v1/boards/examplefirm/jobs", url):
            return FetchResult(ok=True, status=200, data=greenhouse_payload(self.gh_intern))
        if re.search(r"greenhouse\.io/v1/boards/examplefirm$", url):
            return FetchResult(ok=True, status=200, data={"name": "Example Firm"})
        return FetchResult(ok=True, status=404)

    def post(self, url, **kw):
        return FetchResult(ok=False, error="not used")


def temp_data_dir():
    d = tempfile.mkdtemp(prefix="jobs-test-")
    os.environ["JOBS_DATA_DIR"] = d
    return d

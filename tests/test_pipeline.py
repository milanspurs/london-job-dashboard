"""Test suite (runs with `python -m pytest` or `python -m unittest`)."""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fixtures import FUTURE, FakeHttp, temp_data_dir  # noqa: E402

from jobsearch import alerts, store  # noqa: E402
from jobsearch.dates import extract_dates  # noqa: E402
from jobsearch.eligibility import assess  # noqa: E402
from jobsearch.filters import classify_location, exclusion_reason  # noqa: E402
from jobsearch.merge import Index, merge_observation  # noqa: E402
from jobsearch.models import RawJob  # noqa: E402
from jobsearch.process import evaluate  # noqa: E402
from jobsearch.status import set_status  # noqa: E402


def job(title="Graduate Analyst", company="Acme", location="London", desc="", **kw):
    return RawJob(source=kw.pop("source", "reed"), source_id=kw.pop("source_id", "1"), company=company, title=title,
                  location=location, url=kw.pop("url", "https://example.com/1"), description=desc, **kw)


class TestFilters(unittest.TestCase):
    def test_exclusions(self):
        for t in ["Recruitment Consultant", "Talent Acquisition Partner", "Senior Risk Analyst", "Software Engineer",
                  "Restaurant Manager", "Call Centre Advisor", "Head of Strategy", "Estate Agent", "Recruiter"]:
            self.assertIsNotNone(exclusion_reason(job(t)), t)
        for t in ["Graduate Risk Analyst", "Junior Data Analyst", "Summer Analyst", "Graduate Management Trainee",
                  "Assistant Project Manager"]:
            self.assertIsNone(exclusion_reason(job(t)), t)

    def test_agency_advertised_analyst_kept(self):
        self.assertIsNone(exclusion_reason(job("Junior Pricing Analyst", company="Hays Recruitment",
                                               desc="Our client, an insurer, seeks a junior analyst")))

    def test_experience(self):
        self.assertIsNotNone(exclusion_reason(job("Risk Analyst", desc="You have 3+ years of experience")))
        self.assertIsNone(exclusion_reason(job("Risk Analyst", desc="0-2 years experience welcome")))
        self.assertIsNotNone(exclusion_reason(job("Analyst", desc="Unpaid internship, expenses only")))

    def test_location(self):
        self.assertEqual(classify_location(job(location="Canary Wharf"))[0], "London")
        self.assertEqual(classify_location(job(location="Reading, Berkshire"))[0], "Commuter belt")
        self.assertEqual(classify_location(job(location="New York, US"))[0], "Excluded")
        self.assertEqual(classify_location(job(location="London, ON, Canada"))[0], "Excluded")
        self.assertEqual(classify_location(job(location="Manchester", source="greenhouse:x"))[0], "Excluded")
        self.assertEqual(classify_location(job(location="London; New York"))[0], "London")


class TestDates(unittest.TestCase):
    def test_confirmed_only_from_official(self):
        txt = f"Applications close on {FUTURE.day} {FUTURE.strftime('%B %Y')}."
        self.assertEqual(extract_dates(txt, official=True, full_text=True)["deadline_confidence"], "Confirmed")
        self.assertEqual(extract_dates(txt, official=False, full_text=True)["deadline_confidence"], "Indicative")

    def test_no_invented_deadline(self):
        d = extract_dates("Great graduate role in London.", official=True, full_text=True)
        self.assertIsNone(d["deadline"])
        self.assertEqual(d["deadline_confidence"], "Unconfirmed")

    def test_year_inferred_is_indicative(self):
        d = extract_dates("Closing date: 30 November", official=True, full_text=True)
        self.assertEqual(d["deadline_confidence"], "Indicative")

    def test_previous_cycle_ignored(self):
        d = extract_dates("Deadline: 1 January 2026", official=True, full_text=True, posted="2026-10-01")
        self.assertIsNone(d["deadline"])

    def test_rolling(self):
        d = extract_dates("We review applications on a rolling basis.", official=True, full_text=True)
        self.assertTrue(d["rolling"])

    def test_uk_numeric(self):
        d = extract_dates("Apply by 05/12/2026", official=True, full_text=True, today=date(2026, 10, 11))
        self.assertEqual(d["deadline"], "2026-12-05")


class TestEligibility(unittest.TestCase):
    def test_return_to_university(self):
        e = assess("Summer internship for students who will return to university in September", "Summer Internship", True)
        self.assertEqual(e["verdict"], "Likely ineligible")

    def test_grad_years(self):
        self.assertEqual(assess("Open to 2026 and 2027 graduates", "Graduate", True)["verdict"], "Likely eligible")
        self.assertEqual(assess("For students graduating in 2028", "Summer Internship", True)["verdict"], "Likely ineligible")

    def test_unstated_internship_flagged(self):
        self.assertEqual(assess("A great summer internship", "Summer Internship", True)["verdict"], "Check eligibility")

    def test_masters(self):
        e = assess("Final-year and master's students graduating in 2027 may apply", "Summer Internship", True)
        self.assertEqual(e["masters_eligible"], "Yes")
        self.assertEqual(e["verdict"], "Likely eligible")


class TestEvaluateScoring(unittest.TestCase):
    def test_types_and_cv(self):
        r, _ = evaluate(job("Graduate Risk Analyst", desc="Insurance risk graduate scheme for MSc students", full_text=True))
        self.assertEqual(r["type"], "Graduate")
        self.assertEqual(r["category"], "risk")
        self.assertEqual(r["recommended_cv"], "Risk Management CV")
        self.assertGreaterEqual(r["fit"], 4)
        r2, _ = evaluate(job("Summer Analyst Internship 2027", desc="Return to university afterwards", full_text=True))
        self.assertEqual(r2["type"], "Summer Internship")
        self.assertLessEqual(r2["fit"], 2)
        r3, _ = evaluate(job("Trainee Patent Attorney (Chemistry)", desc="Chemistry degree required", full_text=True))
        self.assertIn(r3["recommended_cv"], ("Sustainability & ESG CV",))

    def test_predicted_salary_not_shown(self):
        r, _ = evaluate(job(salary_min=30000, salary_max=30000, salary_predicted=True))
        self.assertEqual(r["salary"], "")


class TestMergeAndStatus(unittest.TestCase):
    def test_dedupe_across_sources_prefers_official(self):
        roles = []
        idx = Index(roles)
        a, _ = evaluate(job("Graduate Analyst", company="Example Firm Ltd", source="adzuna", source_id="a1"))
        b, _ = evaluate(job("Graduate Analyst - London", company="Example Firm", source="greenhouse:examplefirm",
                            source_id="g1", official=True, full_text=True, url="https://boards.greenhouse.io/x/1"))
        merge_observation(roles, idx, a)
        _, is_new = merge_observation(roles, idx, b)
        self.assertFalse(is_new)
        self.assertEqual(len(roles), 1)
        self.assertTrue(roles[0]["official"])
        self.assertEqual(roles[0]["apply_url"], "https://boards.greenhouse.io/x/1")
        self.assertEqual(len(roles[0]["sources"]), 2)

    def test_failure_never_closes(self):
        r, _ = evaluate(job())
        r["verify_failures"] = 10
        set_status(r)
        self.assertNotEqual(r["status"], "Closed")

    def test_confirmed_deadline_passed_closes(self):
        r, _ = evaluate(job())
        r["deadline"] = (date.today() - timedelta(days=1)).isoformat()
        r["deadline_confidence"] = "Confirmed"
        set_status(r)
        self.assertEqual(r["status"], "Closed")

    def test_unconfirmed_past_date_recently_seen_stays_open(self):
        r, _ = evaluate(job())
        r["deadline"] = (date.today() - timedelta(days=1)).isoformat()
        r["deadline_confidence"] = "Indicative"
        set_status(r)
        self.assertEqual(r["status"], "Open")


class TestAlerts(unittest.TestCase):
    def _role(self, **kw):
        r, _ = evaluate(job("Graduate Risk Analyst", desc="Insurance risk graduate scheme for MSc students graduating in 2027",
                            full_text=True))
        r.update(kw)
        return r

    def test_indicative_deadline_never_urgent(self):
        r = self._role(deadline=(date.today() + timedelta(days=3)).isoformat(), deadline_confidence="Indicative")
        self.assertEqual(alerts.select_alerts([], [r], {}, {}, bootstrap=False), [])

    def test_confirmed_soon_and_dedupe(self):
        r = self._role(deadline=(date.today() + timedelta(days=3)).isoformat(), deadline_confidence="Confirmed")
        picks = alerts.select_alerts([], [r], {}, {}, bootstrap=False)
        self.assertEqual(picks[0][0], "deadline_soon")
        sent = {picks[0][2]: "x"}
        self.assertEqual(alerts.select_alerts([], [r], sent, {}, bootstrap=False), [])

    def test_applied_roles_suppressed(self):
        r = self._role(deadline=(date.today() + timedelta(days=3)).isoformat(), deadline_confidence="Confirmed")
        self.assertEqual(alerts.select_alerts([], [r], {}, {r["id"]: {"status": "Applied"}}, bootstrap=False), [])

    def test_bootstrap_no_flood(self):
        r = self._role()
        ev = [{"event": "new", "id": r["id"]}]
        self.assertEqual(alerts.select_alerts(ev, [r], {}, {}, bootstrap=True), [])
        self.assertEqual(len(alerts.select_alerts(ev, [r], {}, {}, bootstrap=False)), 1)

    def test_email_short(self):
        subject, body = alerts.compose("new", self._role())
        self.assertLess(len(body.split()), 200)
        for needle in ("Company:", "Role:", "Type:", "Fit score:", "Deadline:", "Apply:"):
            self.assertIn(needle, body)


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.dir = temp_data_dir()
        os.environ.update({"ADZUNA_APP_ID": "x", "ADZUNA_APP_KEY": "y", "REED_API_KEY": "z"})
        for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "TRACKER_TOKEN"):
            os.environ.pop(k, None)
        reg = {"boards": {"greenhouse:examplefirm": {"platform": "greenhouse", "slug": "examplefirm",
                                                     "company": "Example Firm", "status": "active", "fail_count": 0,
                                                     "missing_count": 0, "last_checked": None, "last_ok": None}},
               "probed": {}, "queue": []}
        store.save_json("registry.json", reg)

    def tearDown(self):
        os.environ.pop("JOBS_DATA_DIR", None)

    def test_full_cycle(self):
        from jobsearch import run
        self.assertEqual(run.main(http=FakeHttp()), 0)
        db = store.load_roles()
        titles = {r["title"] for r in db["roles"]}
        self.assertIn("Graduate Risk Analyst", titles)
        self.assertIn("Graduate Sustainability Consultant", titles)
        self.assertIn("Graduate Analyst, Strategy (2027 start)", titles)
        self.assertNotIn("Senior Recruitment Consultant", titles)      # excluded
        self.assertNotIn("Junior Data Analyst", titles)                # New York
        self.assertNotIn("Risk Analyst", titles)                       # 5+ years
        self.assertEqual(sum(1 for r in db["roles"] if r["title"] == "Graduate Analyst"), 0)  # Paris
        gh = next(r for r in db["roles"] if r["title"].startswith("Graduate Analyst, Strategy"))
        self.assertEqual(gh["deadline_confidence"], "Confirmed")
        self.assertEqual(gh["deadline"], FUTURE.isoformat())
        intern = next(r for r in db["roles"] if r["type"] == "Summer Internship")
        self.assertEqual(intern["eligibility"]["verdict"], "Likely ineligible")
        status = store.load_json("run_status.json", dict)
        self.assertTrue(status["last_run"]["bootstrap"])
        self.assertIn("last_successful_search", status)
        n1 = len(db["roles"])

        # Run 2: everything unreachable -> nothing closed, nothing lost
        self.assertEqual(run.main(http=FakeHttp(down=True)), 0)
        db2 = store.load_roles()
        self.assertEqual(len(db2["roles"]), n1)
        self.assertFalse(any(r["status"] == "Closed" for r in db2["roles"]))

        # Runs 3 & 4: intern removed from the employer board -> Watch, then Closed (positive evidence)
        run.main(http=FakeHttp(gh_intern=False))
        i3 = next(r for r in store.load_roles()["roles"] if r["id"] == intern["id"])
        self.assertEqual(i3["status"], "Watch")
        run.main(http=FakeHttp(gh_intern=False))
        i4 = next(r for r in store.load_roles()["roles"] if r["id"] == intern["id"])
        self.assertEqual(i4["status"], "Closed")
        events = open(os.path.join(self.dir, "events", sorted(os.listdir(os.path.join(self.dir, "events")))[0])).read()
        self.assertIn('"event": "closed"', events)

    def test_corrupt_file_recovered_from_backup(self):
        from jobsearch import run
        run.main(http=FakeHttp())
        run.main(http=FakeHttp())  # creates roles.bak.json
        with open(store.path("roles.json"), "w") as f:
            f.write("{corrupt")
        self.assertGreater(len(store.load_roles()["roles"]), 0)

    def test_dashboard_has_no_private_data(self):
        from jobsearch import run
        os.environ["GMAIL_TO"] = "private@example.com"
        run.main(http=FakeHttp())
        import build_dashboard
        out = build_dashboard.build(os.path.join(self.dir, "site"))
        html = open(out, encoding="utf-8").read()
        self.assertIn("Graduate Risk Analyst", html)
        for secret in ("private@example.com", "ADZUNA", "app_key", "REED_API_KEY", "07825"):
            self.assertNotIn(secret, html)
        data = json.loads(html.split("const DATA = ")[1].split(";\nconst APP_STATES")[0].replace("<\\/", "</"))
        self.assertNotIn("notes", data["roles"][0])
        os.environ.pop("GMAIL_TO")


if __name__ == "__main__":
    unittest.main()

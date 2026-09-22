"""Run with:  python -m unittest discover tests"""
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import requests

from app import classify, fresher, normalize, verify
from app.config import load_config
from app.sources import adzuna, ats

CFG = load_config()


def job(title, desc="", company="Acme", city="Pune"):
    return {"title": title, "description": desc, "company": company, "city": city, "source": "t", "posted_date": ""}


class FresherRules(unittest.TestCase):
    def label(self, title, desc=""):
        return fresher.label_fresher(job(title, desc), CFG)["is_fresher"]

    def test_clear_fresher(self):
        self.assertEqual(self.label("Graduate Trainee"), 1)
        self.assertEqual(self.label("Developer", "Experience: 0-1 years"), 1)
        self.assertEqual(self.label("Analyst", "0-2 years experience"), 1)

    def test_not_fresher(self):
        self.assertEqual(self.label("Senior Developer", "0-1 years"), 0)
        self.assertEqual(self.label("Developer", "5+ years of relevant experience"), 0)
        self.assertEqual(self.label("Developer", "1-3 years"), 0)

    def test_ambiguous(self):
        self.assertIsNone(self.label("Software Engineer", "Build cool things."))

    def test_no_partial_word_match(self):
        self.assertIsNone(self.label("Engineer", "Work on internal tools."))  # 'internal' is not 'intern'


class Dedupe(unittest.TestCase):
    def test_same_job_two_sources(self):
        a = {**job("Data Analyst", company="Acme Pvt Ltd", city="Bangalore"), "source": "a"}
        b = {**job("Data  Analyst", company="ACME", city="Bengaluru"), "source": "b"}
        unique, stats, seen = normalize.normalize_and_dedupe([a, b])
        self.assertEqual(len(unique), 1)
        self.assertEqual(stats["duplicates_removed"], 1)
        self.assertEqual(set(seen), {"a", "b"})


class Classify(unittest.TestCase):
    def test_domains_and_skills(self):
        j = classify.classify_job(job("Junior Java Developer", "Spring Boot, SQL, Git"), classify.build_matchers(CFG))
        self.assertEqual(j["domain"], "Software Development")
        self.assertIn("sql", j["skills"])
        self.assertIn("java", j["skills"])

    def test_other(self):
        j = classify.classify_job(job("Pilot", "Fly planes"), classify.build_matchers(CFG))
        self.assertEqual(j["domain"], "Other")


class Sources(unittest.TestCase):
    @patch("app.sources.adzuna.env", side_effect=lambda k, d="": "x")
    @patch("app.sources.adzuna.requests.get")
    def test_adzuna_parse(self, get, _env):
        resp = MagicMock()
        resp.json.return_value = {"results": [{
            "title": "Graduate Engineer", "company": {"display_name": "Acme"},
            "location": {"display_name": "Pune, Maharashtra", "area": ["India", "Maharashtra", "Pune"]},
            "created": "2026-09-15T08:00:00Z", "redirect_url": "http://x", "description": "desc",
            "salary_min": 300000, "salary_max": 400000}]}
        get.return_value = resp
        cfg = {**CFG, "search_keywords": ["fresher"], "cities": []}
        jobs = adzuna.fetch(cfg)
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0].company, jobs[0].city, jobs[0].posted_date), ("Acme", "Pune", "2026-09-15"))

    @patch("app.sources.ats.requests.get")
    def test_greenhouse_and_lever_parse(self, get):
        gh, lv = MagicMock(), MagicMock()
        gh.json.return_value = {"jobs": [{"title": "Intern", "location": {"name": "Remote"}, "updated_at": "2026-09-10T00:00:00Z",
                                          "absolute_url": "http://g", "content": "<p>Hello <b>world</b></p>"}]}
        lv.json.return_value = [{"text": "Graduate", "hostedUrl": "http://l", "createdAt": 1789000000000,
                                 "categories": {"location": "Pune"}, "descriptionPlain": "plain"}]
        get.side_effect = [gh, lv]
        cfg = {**CFG, "company_boards": {"greenhouse": ["acme"], "lever": ["beta"]}}
        g, l = ats.fetch_greenhouse(cfg), ats.fetch_lever(cfg)
        self.assertEqual(g[0].description, "Hello world")
        self.assertEqual(l[0].city, "Pune")

    @patch("app.sources.ats.requests.get")
    def test_ashby_and_workday_parse(self, get):
        ashby, workday = MagicMock(), MagicMock()
        ashby.json.return_value = {"jobs": [{"title": "Graduate Engineer", "location": {"city": "Bengaluru"},
                                             "createdAt": 1789000000000, "jobUrl": "http://a", "description": "<p>Build</p>"}]}
        workday.text = '<a href="https://acme.workdayjobs.com/en-us/job/123">Software Engineer</a>'
        get.side_effect = [ashby, workday]
        cfg = {**CFG, "company_boards": {"ashby": ["acme"], "workday": ["acme"]}}
        a, w = ats.fetch_ashby(cfg), ats.fetch_workday(cfg)
        self.assertEqual(a[0].city, "Bengaluru")
        self.assertEqual(a[0].url, "http://a")
        self.assertEqual(w[0].title, "Software Engineer")
        self.assertIn("acme.workdayjobs.com", w[0].url)

    @patch("app.sources.ats.requests.get")
    def test_invalid_greenhouse_board_is_skipped(self, get):
        exc = requests.HTTPError(response=MagicMock(status_code=404))
        get.side_effect = exc
        cfg = {**CFG, "company_boards": {"greenhouse": ["does-not-exist"]}}
        self.assertEqual(ats.fetch_greenhouse(cfg), [])

    @patch("app.sources.ats.requests.get")
    def test_invalid_workday_domain_is_skipped(self, get):
        get.side_effect = requests.exceptions.ConnectionError("DNS failed")
        cfg = {**CFG, "company_boards": {"workday": ["totally-unknown-company"]}}
        self.assertEqual(ats.fetch_workday(cfg), [])


class Config(unittest.TestCase):
    def test_company_boards_csv_is_loaded(self):
        cfg = load_config()
        boards = cfg.get("company_boards", {})
        self.assertIn("greenhouse", boards)
        self.assertIn("google", boards["greenhouse"])
        self.assertIn("microsoft", boards["ashby"])
        self.assertGreater(sum(len(v) for v in boards.values() if isinstance(v, list)), 0)

    def test_company_board_summary_counts_loaded_slugs(self):
        cfg = load_config()
        summary = {source: len(vals) for source, vals in cfg["company_boards"].items() if isinstance(vals, list)}
        self.assertIn("greenhouse", summary)
        self.assertGreater(summary["greenhouse"], 0)
        self.assertGreater(summary["workday"], 0)

    def test_company_board_cap_is_400(self):
        cfg = load_config()
        total = sum(len(vals) for vals in cfg["company_boards"].values() if isinstance(vals, list))
        self.assertLessEqual(total, 400)

    @patch("app.config.PdfReader")
    def test_pdf_company_names_are_imported(self, reader_cls):
        from app import config

        class FakePage:
            def extract_text(self):
                return "Company Name\nAcme Corp\nBeta Labs\nhttps://example.com\nNot provided\n"

        reader_cls.return_value.pages = [FakePage()]
        names = config.extract_company_names_from_pdf(Path("dummy.pdf"))
        self.assertIn("Acme Corp", names)
        self.assertIn("Beta Labs", names)

        merged = config.refresh_company_boards_from_pdf(Path("dummy.pdf"))
        self.assertTrue(any("acme-corp" in slug for slug in merged.get("greenhouse", [])))
        self.assertTrue(any("beta-labs" in slug for slug in merged.get("lever", [])))


class Verify(unittest.TestCase):
    def test_failed_source_triggers_retry_then_stops(self):
        m = {"empty": False, "fresher_now": 100, "fresher_prev": 90, "fresher_change_pct": 11,
             "other_domain_share": 0.05, "ambiguous_in_db": 0}
        st = {"a": {"fetched": 0, "error": "boom", "retryable": True}}
        self.assertEqual(verify.verify(m, CFG, st, {}, attempt=0)["retry_sources"], ["a"])
        self.assertEqual(verify.verify(m, CFG, st, {}, attempt=CFG["verify"]["max_retries"])["retry_sources"], [])

    def test_tiny_samples_do_not_trigger_spike_warning(self):
        m = {"empty": False, "fresher_now": 10, "fresher_prev": 2, "fresher_change_pct": 400,
             "other_domain_share": 0.0, "ambiguous_in_db": 0}
        v = verify.verify(m, CFG, {}, {}, 0)
        self.assertEqual(len(v["issues"]), 1)
        self.assertIn("Small sample", "\n".join(v["issues"]))
        self.assertNotIn("Large swing", "\n".join(v["issues"]))
        self.assertEqual(v["confidence"], "Low")

    def test_graduate_engineer_trainee_is_not_other(self):
        j = classify.classify_job(job("Graduate Engineer Trainee", "Java, SQL, Git"), classify.build_matchers(CFG))
        self.assertNotEqual(j["domain"], "Other")
        self.assertIn("Software Development", j["domain"])


if __name__ == "__main__":
    unittest.main()

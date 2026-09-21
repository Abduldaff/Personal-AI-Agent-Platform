"""Run with:  python -m unittest discover tests"""
import unittest
from unittest.mock import patch, MagicMock

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

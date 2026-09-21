"""Synthetic job feed so the whole pipeline runs with no API keys.

NOTE: this data is randomly generated. It is only for testing the agent.
"""
import random
from datetime import date, timedelta

from ..models import Job

COMPANIES = [
    "Northwind Systems", "Bluepeak Software", "Lumen Analytics", "Cedar Cloud", "Ironleaf Security",
    "Quanta Retail", "Helix Health IT", "Orbit Fintech", "Pinecone Learning", "Vertex Manufacturing",
    "Skyline Telecom", "Aster Consulting", "Nimbus Labs", "Redwood Bank Tech", "Fable Games",
    "Harbor Logistics", "Sparrow AI", "Maple Insurance", "Zenith Support Services", "Kite Commerce",
    "Atlas Engineering Works", "Solstice Media", "Tidal Payments", "Greenfield Pharma IT", "Copper Devices",
]
CITIES = ["Hyderabad", "Bengaluru", "Pune", "Chennai", "Mumbai", "Delhi NCR", "Kolkata", "Ahmedabad"]
CITY_W = [22, 26, 16, 12, 10, 9, 3, 2]

# domain -> (titles, weight)
ROLES = {
    "Software Development": (["Software Engineer Trainee", "Junior Java Developer", "Graduate Full Stack Developer",
                              "Associate Software Engineer", "React Frontend Developer (Fresher)"], 30),
    "Data & Analytics": (["Data Analyst Trainee", "Junior Business Analyst", "Graduate Data Engineer",
                          "Power BI Analyst - Entry Level"], 16),
    "AI / ML": (["Machine Learning Intern", "Graduate AI Engineer", "Junior Data Scientist"], 9),
    "Cloud & DevOps": (["DevOps Engineer Trainee", "Junior Cloud Engineer (AWS)", "Graduate Site Reliability Engineer"], 8),
    "Cybersecurity": (["SOC Analyst Trainee", "Junior Security Analyst"], 4),
    "QA & Testing": (["QA Engineer - Fresher", "Junior Automation Tester (Selenium)", "Software Test Engineer Trainee"], 9),
    "IT Support": (["IT Support Executive (Freshers)", "Junior System Administrator", "Technical Support Trainee"], 6),
    "Sales & Business Development": (["Business Development Associate - Entry Level", "Inside Sales Executive (Fresher)"], 6),
    "Marketing": (["Digital Marketing Trainee", "Junior SEO Executive"], 3),
    "Finance & Accounting": (["Graduate Accountant", "Junior Financial Analyst"], 4),
    "HR & Recruitment": (["HR Recruiter Trainee", "Junior Talent Acquisition Executive"], 3),
    "Customer Support": (["Customer Support Executive - Freshers", "Voice Process Trainee", "Chat Support Associate"], 11),
    "Core Engineering": (["Graduate Engineer Trainee (Mechanical)", "Embedded Systems Trainee", "Junior Electrical Engineer"], 4),
}
SENIOR_TITLES = ["Senior Software Engineer", "Lead Data Engineer", "Engineering Manager", "Principal Architect",
                 "Senior DevOps Engineer", "Sales Manager"]
AMBIGUOUS_TITLES = ["Software Engineer", "Data Analyst", "QA Engineer", "Support Engineer", "Business Analyst"]
SKILL_TEXT = {
    "Software Development": "Java, Spring Boot, React, SQL, Git, REST API, problem solving",
    "Data & Analytics": "SQL, Excel, Power BI, Tableau, Python, communication",
    "AI / ML": "Python, machine learning, deep learning, NLP, problem solving",
    "Cloud & DevOps": "AWS, Linux, Docker, Kubernetes, Git",
    "Cybersecurity": "Linux, networking, security tools, communication",
    "QA & Testing": "Selenium, SQL, Java, Git, problem solving",
    "IT Support": "Windows, Linux, communication, ticketing tools",
    "Sales & Business Development": "communication, CRM tools, Excel",
    "Marketing": "SEO, content, communication, Excel",
    "Finance & Accounting": "Excel, accounting, communication",
    "HR & Recruitment": "communication, sourcing, Excel",
    "Customer Support": "communication, typing, problem solving",
    "Core Engineering": "mechanical design, embedded C, electronics, communication",
}


def _make(rng: random.Random, n: int) -> list[Job]:
    today = date.today()
    doms = list(ROLES)
    dom_w = [ROLES[d][1] for d in doms]
    jobs: list[Job] = []
    for _ in range(n):
        # more postings in the most recent week -> visible week-over-week growth
        age = rng.choices(range(14), weights=[9, 9, 8, 8, 8, 7, 7, 5, 5, 5, 4, 4, 4, 3])[0]
        posted = (today - timedelta(days=age)).isoformat()
        city = rng.choices(CITIES, weights=CITY_W)[0]
        company = rng.choice(COMPANIES)
        kind = rng.random()
        if kind < 0.72:  # clear fresher role
            dom = rng.choices(doms, weights=dom_w)[0]
            title = rng.choice(ROLES[dom][0])
            exp = rng.choice(["0-1 years", "0-2 years", "Freshers welcome", "0 years"])
        elif kind < 0.86:  # senior role
            dom = rng.choices(doms, weights=dom_w)[0]
            title = rng.choice(SENIOR_TITLES)
            exp = rng.choice(["5+ years", "7-10 years", "4-6 years"])
        else:  # ambiguous title, sometimes with experience text
            dom = rng.choices(doms, weights=dom_w)[0]
            title = rng.choice(AMBIGUOUS_TITLES)
            exp = rng.choice(["", "", "1-3 years", "0-1 years", "2-5 years"])
        desc = (f"{company} is hiring for {title} in {city}. Experience: {exp}. "
                f"Skills: {SKILL_TEXT[dom]}. Apply now.").replace("Experience: .", "")
        jobs.append(Job(title=title, company=company, city=city, country="in", posted_date=posted,
                        url=f"https://example.com/jobs/{rng.randint(10**6, 10**7)}",
                        description=desc, salary_text=""))
    return jobs


def fetch(cfg: dict, source: str, attempt: int = 0) -> list[Job]:
    """source is 'mock_board_a' or 'mock_board_b'. Set MOCK_FAIL_ONCE=1 to test the retry loop."""
    import os
    if source == "mock_board_b" and os.getenv("MOCK_FAIL_ONCE") == "1" and attempt == 0:
        raise ConnectionError("simulated outage on mock_board_b")
    rng = random.Random(42 if source == "mock_board_a" else 7)
    jobs = _make(rng, 260 if source == "mock_board_a" else 160)
    # second board re-posts ~30 jobs from the first board -> exercises dedupe
    if source == "mock_board_b":
        jobs += _make(random.Random(42), 260)[:30]
    for j in jobs:
        j.source = source
    return jobs

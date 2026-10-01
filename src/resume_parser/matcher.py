"""
Job matching for SmartHire.

Each candidate is scored against each job on three factors:
    skills      50%  share of the job's required skills the candidate has
    experience  30%  candidate years vs the job's minimum years
    education   20%  highest degree found vs a bachelor's baseline
"""

import re
from typing import Any, Dict, List

SKILL_WEIGHT = 0.5
EXP_WEIGHT = 0.3
EDU_WEIGHT = 0.2

# Different spellings of the same skill map to one canonical name
SKILL_SYNONYMS = {
    "javascript": ["js", "javascript", "ecmascript", "es6"],
    "typescript": ["ts", "typescript"],
    "python": ["python", "python3", "py"],
    "java": ["java", "java8", "java11", "java17"],
    "c++": ["c++", "cpp"],
    "c#": ["c#", "csharp"],
    "react": ["react", "reactjs", "react.js"],
    "angular": ["angular", "angularjs", "angular.js"],
    "vue": ["vue", "vuejs", "vue.js"],
    "next.js": ["next", "nextjs", "next.js"],
    "node.js": ["node", "nodejs", "node.js"],
    "express": ["express", "expressjs", "express.js"],
    "mongodb": ["mongodb", "mongo"],
    "postgresql": ["postgresql", "postgres"],
    "sql": ["sql", "mysql", "sqlite"],
    "aws": ["aws", "amazon web services"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "kubernetes": ["kubernetes", "k8s"],
    "machine learning": ["ml", "machine learning"],
    "artificial intelligence": ["ai", "artificial intelligence"],
    "deep learning": ["dl", "deep learning"],
    "natural language processing": ["nlp", "natural language processing"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    "git": ["git", "github", "gitlab"],
    "rest api": ["rest", "rest api", "restful", "restful api", "rest apis"],
    "ci/cd": ["ci/cd", "cicd", "ci cd"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "tensorflow": ["tensorflow", "tf"],
    "pytorch": ["pytorch", "torch"],
}
_CANONICAL = {alias: name for name, aliases in SKILL_SYNONYMS.items() for alias in aliases}

EDUCATION_LEVELS = {
    "phd": 5, "ph.d": 5, "doctorate": 5,
    "master": 4, "m.tech": 4, "mtech": 4, "m.sc": 4, "msc": 4, "mca": 4, "mba": 4, "m.e": 4,
    "bachelor": 3, "b.tech": 3, "btech": 3, "b.e": 3, "b.sc": 3, "bsc": 3, "bca": 3, "b.com": 3,
    "diploma": 2,
    "certificat": 1,
}
BASELINE_EDUCATION = 3  # bachelor's


def canonical_skill(skill: str) -> str:
    s = re.sub(r"\s+", " ", str(skill).lower().strip())
    return _CANONICAL.get(s, s)


def extract_years(text) -> float:
    """'3 years', '2-4 yrs', '18 months', '1.5' -> years as a float."""
    if text is None:
        return 0.0
    if isinstance(text, (int, float)):
        return float(text)
    text = str(text).lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+|-|to)?\s*\d*\s*(years?|yrs?|months?|mos?)?", text)
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2) or "years"
    years = round(value / 12, 1) if unit.startswith("mo") else value
    return years if years <= 50 else 0.0  # a stray year like "2023" is not experience


def education_level(education) -> int:
    if isinstance(education, str):
        education = [education]
    text = " ".join(str(e) for e in (education or [])).lower()
    return max((lvl for kw, lvl in EDUCATION_LEVELS.items() if kw in text), default=0)


def score_candidate_for_job(candidate: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
    candidate_skills = {canonical_skill(s) for s in (candidate.get("skills") or []) if s}
    job_skills = [s for s in (job.get("skills") or []) if s]

    matched = [s for s in job_skills if canonical_skill(s) in candidate_skills]
    missing = [s for s in job_skills if canonical_skill(s) not in candidate_skills]
    skill_score = len(matched) / len(job_skills) if job_skills else 1.0

    required_years = float(job.get("min_experience") or 0)
    candidate_years = extract_years(candidate.get("experience"))
    exp_score = 1.0 if required_years <= 0 else min(1.0, candidate_years / required_years)

    level = education_level(candidate.get("education"))
    edu_score = min(1.0, level / BASELINE_EDUCATION) if level else 0.5

    final = SKILL_WEIGHT * skill_score + EXP_WEIGHT * exp_score + EDU_WEIGHT * edu_score

    return {
        "id": job.get("id", ""),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "experience_required": job.get("experience", ""),
        "match_percentage": round(final * 100, 1),
        "scores": {
            "skill": round(skill_score, 3),
            "experience": round(exp_score, 3),
            "education": round(edu_score, 3),
            "final": round(final, 3),
        },
        "skill_matches": matched,
        "missing_skills": missing,
    }


def match_jobs(candidate: Dict[str, Any], jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Score a candidate against every active job, best match first."""
    active = [j for j in jobs if j.get("status", "active") == "active"]
    results = [score_candidate_for_job(candidate, job) for job in active]
    results.sort(key=lambda r: r["match_percentage"], reverse=True)
    return results

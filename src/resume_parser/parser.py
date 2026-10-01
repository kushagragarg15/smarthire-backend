"""
Resume parsing for SmartHire.

Uses OpenAI when OPENAI_API_KEY is set; otherwise (or if the API call fails)
falls back to a regex/keyword parser so uploads always work.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
_client = None


def _openai_client():
    global _client
    if _client is None and os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60, max_retries=1)
        except Exception as e:
            logger.warning(f"Could not initialise OpenAI client: {e}")
    return _client


PROMPT = """Extract these fields from the resume below and return a JSON object:
- name: full name (string)
- email: email address (string)
- phone: phone number (string)
- skills: technical skills, tools and programming languages (array of short strings)
- education: one string per degree, e.g. "B.Tech Computer Science, LNMIIT, 2026" (array of strings)
- experience: total professional experience, e.g. "2 years" or "6 months"; "0 years" for freshers (string)
- location: city and state/country (string)
- ats_score: integer 0-100 rating the resume's quality for applicant tracking systems:
  structure 20, skills 25, experience 25, education 15, contact info 10, presentation 5
Use null for anything not present.

Resume:
\"\"\"
{text}
\"\"\""""


def parse_resume(text: str) -> dict:
    client = _openai_client()
    if client is not None:
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise resume parser. Reply with JSON only."},
                    {"role": "user", "content": PROMPT.format(text=text[:15000])},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            data = json.loads(response.choices[0].message.content)
            profile = _normalise(data)
            # The model occasionally misreads contact details; regex is exact for these
            fallback = fallback_parse(text)
            profile["email"] = profile["email"] or fallback["email"]
            profile["phone"] = profile["phone"] or fallback["phone"]
            profile["parsed_by"] = "openai"
            return profile
        except Exception as e:
            logger.error(f"OpenAI parsing failed, using fallback parser: {e}")

    return fallback_parse(text)


def _as_text(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return ", ".join(str(v) for v in value.values() if v)
    value = str(value).strip()
    return value or None


def _normalise(data: dict) -> dict:
    skills = data.get("skills") or []
    education = data.get("education") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",")]
    if not isinstance(education, list):
        education = [education]
    try:
        ats = max(0, min(100, int(data.get("ats_score"))))
    except (TypeError, ValueError):
        ats = None
    profile = {
        "name": _as_text(data.get("name")),
        "email": (_as_text(data.get("email")) or "").lower() or None,
        "phone": _as_text(data.get("phone")),
        "skills": [s for s in (_as_text(x) for x in skills) if s],
        "education": [e for e in (_as_text(x) for x in education) if e],
        "experience": _as_text(data.get("experience")),
        "location": _as_text(data.get("location")),
    }
    profile["ats_score"] = ats if ats is not None else heuristic_ats_score(profile)
    return profile


# ---------------------------------------------------------------------------
# Fallback parser (no API key needed)
# ---------------------------------------------------------------------------

SKILL_KEYWORDS = [
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "C", "Go", "Rust", "Kotlin", "Swift",
    "PHP", "Ruby", "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "SQLite", "Firebase",
    "React", "Angular", "Vue", "Next.js", "Node.js", "Express", "Django", "Flask", "FastAPI",
    "Spring", "Spring Boot", "HTML", "CSS", "Tailwind", "Bootstrap", "Redux", "GraphQL", "REST API",
    "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Linux", "Git", "GitHub", "Jenkins", "CI/CD",
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "Data Science", "Data Analysis",
    "TensorFlow", "PyTorch", "Keras", "Scikit-learn", "Pandas", "NumPy", "Matplotlib", "OpenCV",
    "Power BI", "Tableau", "Excel", "Figma", "Agile", "Scrum", "Microservices", "DSA",
]
# Single letters / short words need case-sensitive matching to avoid false hits
CASE_SENSITIVE = {"C", "Go"}

EDUCATION_WORDS = [
    "bachelor", "master", "b.tech", "btech", "m.tech", "mtech", "b.e.", "m.e.", "b.sc", "m.sc",
    "bca", "mca", "mba", "phd", "ph.d", "diploma", "university", "institute", "college",
]

CITIES = [
    "Mumbai", "Delhi", "New Delhi", "Bangalore", "Bengaluru", "Hyderabad", "Chennai", "Kolkata",
    "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Kanpur", "Nagpur", "Indore", "Bhopal", "Patna",
    "Chandigarh", "Noida", "Gurgaon", "Gurugram", "Ghaziabad", "Faridabad", "Surat", "Vadodara",
    "Coimbatore", "Kochi", "Thiruvananthapuram", "Visakhapatnam", "Bhubaneswar", "Guwahati",
    "Dehradun", "Jodhpur", "Udaipur", "Kota", "Agra", "Varanasi", "Ludhiana", "Amritsar", "Mysore",
    "New York", "San Francisco", "Seattle", "London", "Toronto", "Singapore", "Dubai", "Remote",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,5}")
EXP_RE = re.compile(r"(\d+(?:\.\d+)?)\+?\s*(years?|yrs?|months?)\s+(?:of\s+)?(?:\w+\s+){0,3}experience", re.I)
HEADINGS = {"resume", "curriculum vitae", "cv", "profile", "summary", "contact", "objective"}


def _find_skills(text: str):
    found = []
    for skill in SKILL_KEYWORDS:
        flags = 0 if skill in CASE_SENSITIVE else re.I
        if re.search(r"(?<![\w+#.])" + re.escape(skill) + r"s?(?![\w+#-])", text, flags):
            found.append(skill)
    return found


def _find_name(lines):
    for line in lines[:8]:
        clean = line.strip().strip("|•-").strip()
        words = clean.split()
        if (
            1 < len(words) <= 4
            and clean.lower() not in HEADINGS
            and not re.search(r"[\d@:/|]", clean)
            and all(w[0].isupper() for w in words if w[0].isalpha())
        ):
            return clean.title() if clean.isupper() else clean
    return None


def fallback_parse(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)

    education = []
    for line in lines:
        if any(w in line.lower() for w in EDUCATION_WORDS) and len(line) < 150 and line not in education:
            education.append(line)

    exp = EXP_RE.search(text)
    experience = f"{exp.group(1)} {'months' if exp.group(2).lower().startswith('m') else 'years'}" if exp else None

    location = next(
        (c for c in CITIES if re.search(r"\b" + re.escape(c) + r"\b", "\n".join(lines[:15]))), None
    ) or next((c for c in CITIES if re.search(r"\b" + re.escape(c) + r"\b", text)), None)

    profile = {
        "name": _find_name(lines),
        "email": email.group(0).lower() if email else None,
        "phone": phone.group(0).strip() if phone else None,
        "skills": _find_skills(text),
        "education": education[:5],
        "experience": experience,
        "location": location,
        "parsed_by": "fallback",
    }
    profile["ats_score"] = heuristic_ats_score(profile)
    return profile


def heuristic_ats_score(profile: dict) -> int:
    score = 0
    score += 10 if profile.get("email") else 0
    score += 5 if profile.get("phone") else 0
    score += 5 if profile.get("name") else 0
    score += min(35, 3 * len(profile.get("skills") or []))
    score += 20 if profile.get("education") else 0
    score += 20 if profile.get("experience") else 5
    score += 5 if profile.get("location") else 0
    return min(100, score)

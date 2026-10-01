"""
SmartHire backend: a small Flask API for resume upload, parsing and job matching.

Public:     GET /health, GET /jobs, POST /parse_resume, POST /login, POST /verify-token,
            GET /resume_file/<email>
Recruiter:  GET /resume_matches, POST /update_status, DELETE /resumes/<email>,
            POST /add_job, PUT /jobs/<id>, DELETE /jobs/<id>
            (send "Authorization: Bearer <token>" from /login)
"""

import io
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.utils import secure_filename

load_dotenv()

from src.core.storage import PROJECT_ROOT, Storage  # noqa: E402
from src.resume_parser.extract_text import extract_text_from_pdf  # noqa: E402
from src.resume_parser.matcher import match_jobs  # noqa: E402
from src.resume_parser.parser import parse_resume  # noqa: E402

log_handlers = [logging.StreamHandler()]
try:
    os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)
    log_handlers.append(logging.FileHandler(os.path.join(PROJECT_ROOT, "logs", "smarthire.log"), encoding="utf-8"))
except OSError:
    pass  # read-only filesystem (e.g. Vercel): log to stdout only
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=log_handlers,
)
logger = logging.getLogger("smarthire")

app = Flask(__name__)
# Vercel rejects request bodies over 4.5 MB, so keep uploads under that everywhere
MAX_UPLOAD_MB = 4
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# Auth uses a Bearer header, not cookies, so allowing any origin is safe.
# Set CORS_ORIGINS="https://a.app,https://b.app" to restrict it anyway.
cors_origins = os.getenv("CORS_ORIGINS", "*")
CORS(app, origins="*" if cors_origins == "*" else [o.strip() for o in cors_origins.split(",")])

store = Storage()

VALID_STATUSES = ["Pending", "Under Review", "Shortlisted", "Rejected"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    # Random per run: logins reset on restart. Set SECRET_KEY in .env to keep them.
    SECRET_KEY = os.urandom(32).hex()
    logger.warning("SECRET_KEY not set; recruiters will need to log in again after each restart")
TOKEN_MAX_AGE = 7 * 24 * 3600  # one week
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="smarthire-auth")

# Override with RECRUITER_USERS="user1:pass1,user2:pass2"
DEFAULT_USERS = "recruiter:smartHire2024,admin:admin123,hr:hr@2024"
USERS = dict(
    pair.split(":", 1) for pair in os.getenv("RECRUITER_USERS", DEFAULT_USERS).split(",") if ":" in pair
)


def user_from_token(token):
    try:
        return serializer.loads(token, max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired, TypeError):
        return None


def require_auth(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else None
        if not token or not user_from_token(token):
            return jsonify({"error": "Please log in again"}), 401
        return view(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if USERS.get(username) != password or not username:
        return jsonify({"error": "Invalid username or password"}), 401
    token = serializer.dumps({"username": username})
    return jsonify({
        "success": True,
        "message": "Login successful",
        "user": {"username": username, "role": "recruiter", "token": token},
    })


@app.route("/verify-token", methods=["POST"])
def verify_token():
    data = request.get_json(silent=True) or {}
    user = user_from_token(data.get("token"))
    return (jsonify({"valid": True, "user": user}), 200) if user else (jsonify({"valid": False}), 401)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value, limit=2000):
    return re.sub(r"[<>]", "", str(value or "")).strip()[:limit]


def parse_skills(raw):
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list):
        return []
    seen, skills = set(), []
    for s in raw:
        s = clean_text(s, 60).lower()
        if s and s not in seen:
            seen.add(s)
            skills.append(s)
    return skills


def min_years(experience):
    match = re.search(r"\d+(?:\.\d+)?", str(experience or ""))
    return float(match.group(0)) if match else 0


def job_from_request(data):
    """Validate a job payload. Returns (job_fields, error_message)."""
    title = clean_text(data.get("title"), 150)
    skills = parse_skills(data.get("skills"))
    experience = clean_text(data.get("experience"), 50)
    missing = [name for name, val in (("title", title), ("skills", skills), ("experience", experience)) if not val]
    if missing:
        return None, f"Missing required field(s): {', '.join(missing)}"
    return {
        "title": title,
        "company": clean_text(data.get("company"), 150) or "Company Not Specified",
        "location": clean_text(data.get("location"), 150) or "Location Not Specified",
        "description": clean_text(data.get("description")) or title,
        "requirements": clean_text(data.get("requirements")) or ", ".join(skills),
        "salary": clean_text(data.get("salary"), 100) or "Salary Not Specified",
        "skills": skills,
        "experience": experience,
        "min_experience": min_years(experience),
        "updated_at": now(),
    }, None


def public_resume(resume):
    return {k: v for k, v in resume.items() if k not in ("_id", "file_content")}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "message": "SmartHire backend is running!",
        "storage": store.backend,
        "openai": "configured" if os.getenv("OPENAI_API_KEY") else "not configured (using fallback parser)",
        "timestamp": now(),
    })


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@app.route("/jobs", methods=["GET"])
def list_jobs():
    jobs = sorted(store.jobs.all(), key=lambda j: str(j.get("created_at", "")), reverse=True)
    return jsonify({"jobs": jobs, "source": store.backend})


@app.route("/add_job", methods=["POST"])
@app.route("/jobs", methods=["POST"])
@require_auth
def add_job():
    job, error = job_from_request(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    job.update({
        "id": str(uuid.uuid4()),
        "status": "active",
        "education_keywords": ["bachelor", "btech", "b.e", "master", "mca", "msc"],
        "created_at": now(),
    })
    store.jobs.upsert(job)
    logger.info(f"Job added: {job['title']}")
    return jsonify({"message": "Job added successfully", "job": job}), 201


@app.route("/jobs/<job_id>", methods=["PUT"])
@require_auth
def update_job(job_id):
    fields, error = job_from_request(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    if not store.jobs.update(job_id, fields):
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"message": "Job updated successfully"})


@app.route("/jobs/<job_id>", methods=["DELETE"])
@require_auth
def delete_job(job_id):
    if not store.jobs.delete(job_id):
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"message": "Job deleted successfully"})


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------

@app.route("/parse_resume", methods=["POST"])
def upload_resume():
    file = request.files.get("resume")
    if not file or not file.filename:
        return jsonify({"error": "Please choose a resume file"}), 400
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    pdf_bytes = file.read()
    try:
        text = extract_text_from_pdf(pdf_bytes)
    except Exception as e:
        logger.warning(f"Could not read PDF {file.filename}: {e}")
        return jsonify({"error": "This file could not be read as a PDF"}), 400
    if len(text.strip()) < 50:
        return jsonify({
            "error": "No readable text found in this PDF. Scanned/image PDFs are not supported; "
                     "please upload a text-based PDF."
        }), 400

    profile = parse_resume(text)
    email = (profile.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({
            "error": "We couldn't find an email address in your resume. Please add one and upload again.",
            "profile": profile,
        }), 422
    profile["email"] = email
    profile["name"] = profile.get("name") or email.split("@")[0]

    existing = store.resumes.get(email)
    file_id = f"{uuid.uuid4().hex}_{secure_filename(file.filename) or 'resume.pdf'}"
    store.save_file(file_id, pdf_bytes)
    if existing and existing.get("file_id"):
        store.delete_file(existing["file_id"])

    applied_jobs = list((existing or {}).get("applied_jobs") or [])
    job_id = request.form.get("job_id")
    if job_id:
        job = store.jobs.get(job_id)
        if job and not any(a.get("id") == job_id for a in applied_jobs):
            applied_jobs.append({"id": job_id, "title": job.get("title"), "applied_at": now()})

    resume = {
        **profile,
        "status": (existing or {}).get("status", "Pending"),
        "applied_jobs": applied_jobs,
        "original_filename": file.filename,
        "file_id": file_id,
        "file_size": len(pdf_bytes),
        "created_at": (existing or {}).get("created_at", now()),
        "updated_at": now(),
    }
    store.resumes.upsert(resume)
    logger.info(f"Resume stored for {email} (parsed by {profile.get('parsed_by')})")
    return jsonify({"message": "Resume parsed and stored successfully", "profile": public_resume(resume)})


@app.route("/resume_matches", methods=["GET"])
@require_auth
def resume_matches():
    jobs = store.jobs.all()
    results = []
    for resume in store.resumes.all():
        results.append({
            "candidate": resume,
            "matches": match_jobs(resume, jobs),
            "status": resume.get("status", "Pending"),
        })
    results.sort(key=lambda r: str(r["candidate"].get("updated_at", "")), reverse=True)
    return jsonify(results)


@app.route("/update_status", methods=["POST"])
@require_auth
def update_status():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    status = data.get("status")
    if not email or status not in VALID_STATUSES:
        return jsonify({"error": f"Provide an email and a status from: {', '.join(VALID_STATUSES)}"}), 400
    if not store.resumes.update(email, {"status": status, "updated_at": now()}):
        return jsonify({"error": "Candidate not found"}), 404
    return jsonify({"message": "Status updated successfully"})


@app.route("/resume_file/<path:email>", methods=["GET"])
def resume_file(email):
    resume = store.resumes.get(email.strip().lower())
    if not resume:
        return jsonify({"error": "Resume not found"}), 404
    data = store.load_file(resume)
    if data is None:
        return jsonify({"error": "The PDF for this candidate is no longer stored. Ask them to re-upload."}), 404
    return send_file(
        io.BytesIO(data),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=resume.get("original_filename") or "resume.pdf",
    )


@app.route("/resumes/<path:email>", methods=["DELETE"])
@require_auth
def delete_resume(email):
    email = email.strip().lower()
    resume = store.resumes.get(email)
    if not resume:
        return jsonify({"error": "Candidate not found"}), 404
    store.resumes.delete(email)
    store.delete_file(resume.get("file_id"))
    return jsonify({"message": "Candidate deleted"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(_):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": f"File too large. Maximum size is {MAX_UPLOAD_MB} MB"}), 413


@app.errorhandler(Exception)
def unhandled(e):
    if hasattr(e, "code") and hasattr(e, "description"):  # normal HTTP errors
        return jsonify({"error": e.description}), e.code
    logger.exception("Unhandled error")
    return jsonify({"error": "Something went wrong on the server"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG") == "1")

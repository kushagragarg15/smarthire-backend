from flask import Flask, request, jsonify, send_file
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from resume_parser.extract_text import extract_text_from_pdf
from resume_parser.parser import parse_resume
from resume_parser.matcher import match_jobs
import spacy
from flask_cors import CORS
import json
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from werkzeug.utils import secure_filename
import uuid
import re
from typing import Optional, Dict, Any, List

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('smarthire.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Configure CORS for both local development and production
allowed_origins = [
    "http://localhost:3000",  # Local development
    "https://smarthire-frontend.netlify.app",  # Netlify production
    "https://smarthire.vercel.app",  # Vercel production (if you switch)
]
CORS(app, origins=allowed_origins, methods=["GET", "POST", "PUT", "DELETE"], supports_credentials=True)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'pdf'}

# Load spaCy model with error handling
try:
    nlp = spacy.load("en_core_web_sm")
    logger.info("SpaCy model loaded successfully")
except OSError:
    logger.warning("SpaCy model not found. Install with: python -m spacy download en_core_web_sm")
    nlp = None

# Folder to store uploaded resumes
UPLOAD_FOLDER = 'resumes'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database connection with retry logic
def connect_to_mongodb(max_retries: int = 3) -> Optional[MongoClient]:
    """Connect to MongoDB with retry logic"""
    for attempt in range(max_retries):
        try:
            client = MongoClient(
                "mongodb+srv://23ucc564:2zc3Oys67uarz4W7@smarthire.ud6wo4p.mongodb.net/?retryWrites=true&w=majority&tls=true",
                serverSelectionTimeoutMS=5000,
                maxPoolSize=10,
                minPoolSize=1
            )
            # Test connection
            client.admin.command('ping')
            logger.info("MongoDB connection established successfully")
            return client
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.warning(f"MongoDB connection attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                logger.error("Failed to connect to MongoDB after all retries")
                return None
    return None

# Initialize database connection
client = connect_to_mongodb()
if client:
    db = client["smarthire"]
    resumes_collection = db["resumes"]
    jobs_collection = db["jobs"]
else:
    db = None
    resumes_collection = None
    jobs_collection = None

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent injection attacks"""
    if not text:
        return ""
    # Remove potentially dangerous characters
    text = re.sub(r'[<>"\\]', '', text)
    return text.strip()

def validate_email(email: str) -> bool:
    """Validate email format with more lenient pattern"""
    if not email:
        return False
    
    # Clean the email first
    email = email.strip().lower()
    
    # Remove common prefixes/suffixes that might be parsed incorrectly
    email = email.replace('email:', '').replace('e-mail:', '').replace('mail:', '').replace('contact:', '').replace('phone:', '')
    
    # Basic email pattern - more lenient
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$'
    
    # If the pattern doesn't match, try to extract email from the string
    if not re.match(pattern, email):
        # Look for email pattern within the string
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]+\.[a-zA-Z]{2,}', email)
        if email_match:
            email = email_match.group(0)
            return True
        return False
    
    return True

def validate_resume_data(data: Dict[str, Any]) -> List[str]:
    """Validate resume data before saving"""
    required_fields = ['name', 'email', 'skills']
    errors = []
    for field in required_fields:
        if not data.get(field):
            errors.append(f"Missing required field: {field}")
    if data.get('email'):
        email = data['email'].strip()
        if not validate_email(email):
            errors.append("Invalid email format")
        else:
            # Clean up common parsing errors and update the email
            cleaned_email = email.strip().lower()
            # Remove common prefixes/suffixes
            cleaned_email = cleaned_email.replace('email:', '').replace('e-mail:', '').replace('mail:', '').replace('contact:', '').replace('phone:', '')
            # Extract email if it's embedded in other text
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]+\.[a-zA-Z]{2,}', cleaned_email)
            if email_match:
                data['email'] = email_match.group(0)
            else:
                data['email'] = cleaned_email
    if data.get('skills') and not isinstance(data['skills'], list):
        errors.append("Skills must be a list")
    # Sanitize text fields
    if data.get('name'):
        data['name'] = sanitize_input(data['name'])
    if data.get('location'):
        data['location'] = sanitize_input(data['location'])
    return errors

def validate_job_data(data: Dict[str, Any]) -> List[str]:
    """Validate job data before saving"""
    errors = []
    required_fields = ['title', 'skills', 'experience']
    for field in required_fields:
        if not data.get(field):
            errors.append(f"Missing required field: {field}")
    # Sanitize text fields
    if data.get('title'):
        data['title'] = sanitize_input(data['title'])
    if data.get('company'):
        data['company'] = sanitize_input(data['company'])
    if data.get('location'):
        data['location'] = sanitize_input(data['location'])
    if data.get('description'):
        data['description'] = sanitize_input(data['description'])
    if data.get('requirements'):
        data['requirements'] = sanitize_input(data['requirements'])
    if data.get('salary'):
        data['salary'] = sanitize_input(data['salary'])
    if data.get('experience'):
        data['experience'] = sanitize_input(data['experience'])
    return errors

# -------------------------------
# Endpoint: Parse resume text (for testing)
# -------------------------------
@app.route('/parse_text', methods=['POST'])
def parse_text_endpoint():
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'No text provided'}), 400

        resume_text = data['text']
        if not resume_text or len(resume_text.strip()) < 10:
            return jsonify({'error': 'Text too short or empty'}), 400
        logger.info(f"Parsing text: {len(resume_text)} characters")
        
        # Parse using our GPT-powered parser
        candidate_profile = parse_resume(resume_text)
        logger.info(f"Parsed profile: {candidate_profile}")

        return jsonify({
            "message": "Text parsed successfully",
            "profile": candidate_profile
        })

    except Exception as e:
        logger.error(f"ERROR in parse_text_endpoint: {str(e)}")
        return jsonify({'error': f'Error parsing text: {str(e)}'}), 500

# -------------------------------
# Endpoint: Upload and parse resume
# -------------------------------
@app.route('/parse_resume', methods=['POST'])
def parse_resume_endpoint():
    try:
        logger.info("=== RESUME UPLOAD STARTED ===")

        # Check if MongoDB is available
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503

        if 'resume' not in request.files:
            logger.error("No resume file provided")
            return jsonify({'error': 'No resume file provided'}), 400

        file = request.files['resume']
        
        # Validate file
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are allowed'}), 400

        # Generate secure filename
        original_filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{original_filename}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        logger.info(f"Processing file: {original_filename}")

        # Save file
        file.save(filepath)
        logger.info(f"File saved to: {filepath}")

        try:
            # Step 1: Extract raw text from PDF
            logger.info("Extracting text from PDF...")
            resume_text = extract_text_from_pdf(filepath)
            
            if not resume_text or len(resume_text.strip()) < 50:
                return jsonify({'error': 'Could not extract meaningful text from PDF. Please ensure the PDF contains readable text.'}), 400
                
            logger.info(f"Extracted text length: {len(resume_text)} characters")

            # Step 2: Parse using NLP
            logger.info("Parsing resume with NLP...")
            candidate_profile = parse_resume(resume_text)
            
            # Validate parsed data
            validation_errors = validate_resume_data(candidate_profile)
            if validation_errors:
                logger.warning(f"Validation errors: {validation_errors}")
                return jsonify({
                    'error': 'Resume parsing incomplete',
                    'details': validation_errors,
                    'profile': candidate_profile
                }), 422

            # Add metadata
            candidate_profile.update({
                "status": "Pending",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "original_filename": original_filename,
                "file_id": unique_filename
            })

            logger.info(f"Parsed profile for: {candidate_profile.get('email', 'Unknown')}")

            # Step 3: Save to MongoDB
            if candidate_profile.get("email"):
                existing = resumes_collection.find_one({"email": candidate_profile["email"]})
                if existing:
                    logger.info(f"Updating existing resume for: {candidate_profile['email']}")
                    candidate_profile["updated_at"] = datetime.utcnow()
                    result = resumes_collection.update_one(
                        {"email": candidate_profile["email"]},
                        {"$set": candidate_profile}
                    )
                    if not result.modified_count:
                        logger.error("Failed to update resume in database")
                        return jsonify({'error': 'Failed to update resume data'}), 500
                else:
                    logger.info(f"Inserting new resume for: {candidate_profile['email']}")
                    result = resumes_collection.insert_one(candidate_profile)
                    if not result.inserted_id:
                        logger.error("Failed to insert resume into database")
                        return jsonify({'error': 'Failed to save resume data'}), 500
                # Verify save
                saved_resume = resumes_collection.find_one({"email": candidate_profile["email"]})
                if not saved_resume:
                    logger.error("Failed to save resume to database")
                    return jsonify({'error': 'Failed to save resume data'}), 500
            else:
                logger.warning("No email found in resume - saving without email")
                result = resumes_collection.insert_one(candidate_profile)
                if not result.inserted_id:
                    logger.error("Failed to insert resume into database")
                    return jsonify({'error': 'Failed to save resume data'}), 500

        finally:
            # Keep the file for viewing - don't delete it
            # The file is needed for the "View Resume" functionality
            logger.info(f"Resume file kept at: {filepath} for viewing purposes")

        logger.info("=== RESUME UPLOAD COMPLETED ===")
        return jsonify({
            "message": "Resume parsed and stored successfully",
            "profile": {k: v for k, v in candidate_profile.items() if k not in ['file_id', '_id']}
        })

    except Exception as e:
        logger.error(f"ERROR in parse_resume_endpoint: {str(e)}")
        return jsonify({'error': f'Error parsing resume: {str(e)}'}), 500

# -------------------------------
# Endpoint: Match resume to jobs
# -------------------------------
@app.route('/match_jobs', methods=['POST'])
def match_jobs_endpoint():
    try:
        data = request.get_json()

        if not data or 'skills' not in data:
            return jsonify({'error': 'No skills provided for matching'}), 400

        if not isinstance(data['skills'], list):
            return jsonify({'error': 'Skills must be a list'}), 400

        matched_jobs = match_jobs(data)

        return jsonify({
            "message": "Job matching successful",
            "matches": matched_jobs
        })
    except Exception as e:
        logger.error(f"Error in match_jobs_endpoint: {e}")
        return jsonify({'error': f'Error matching jobs: {str(e)}'}), 500

# -------------------------------
# Endpoint: Add new job
# -------------------------------
@app.route('/add_job', methods=['POST'])
def add_job():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        # Validate job data
        validation_errors = validate_job_data(data)
        if validation_errors:
            return jsonify({'error': 'Validation failed', 'details': validation_errors}), 400

        # Process skills - ensure it's a list
        skills = data.get('skills')
        if isinstance(skills, str):
            skills = [s.strip().lower() for s in skills.split(',') if s.strip()]
        elif isinstance(skills, list):
            skills = [s.strip().lower() for s in skills if s.strip()]
        else:
            return jsonify({'error': 'Skills must be a string or list'}), 400

        job = {
            "id": str(uuid.uuid4()),
            "title": data.get('title').strip(),
            "company": data.get('company', '').strip() or "Company Not Specified",
            "location": data.get('location', '').strip() or "Location Not Specified", 
            "description": data.get('description', '').strip() or data.get('title').strip(),
            "requirements": data.get('requirements', '').strip() or ', '.join(skills),
            "salary": data.get('salary', '').strip() or "Salary Not Specified",
            "skills": skills,
            "experience": data.get('experience').strip(),
            "min_experience": extract_min_experience(data.get('experience', '')),
            "education_keywords": ["btech", "b.e", "bachelor", "master", "mca", "msc"],
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        # Try to use MongoDB first, fallback to JSON
        if jobs_collection is not None:
            try:
                result = jobs_collection.insert_one(job)
                if result.inserted_id:
                    logger.info(f"Job added to MongoDB: {job['title']}")
                    # Sync JSON file with MongoDB
                    sync_json_with_mongodb()
                else:
                    logger.error("Failed to insert job into MongoDB")
                    return jsonify({"error": "Failed to save job to database"}), 500
            except Exception as mongo_error:
                logger.warning(f"MongoDB insert failed, using JSON fallback: {mongo_error}")
                # Fallback to JSON file
                save_job_to_json(job)
        else:
            save_job_to_json(job)

        return jsonify({
            "message": "Job added successfully",
            "job": {k: v for k, v in job.items() if k != '_id'}
        })

    except Exception as e:
        logger.error(f"Error adding job: {e}")
        return jsonify({"error": "Failed to add job", "details": str(e)}), 500

def extract_min_experience(experience_str: str) -> int:
    """Extract minimum experience years from experience string"""
    if not experience_str:
        return 0
    
    # Look for patterns like "2-4 years", "3+ years", "5 years", etc.
    patterns = [
        r'(\d+)\s*-\s*\d+\s*years?',  # "2-4 years"
        r'(\d+)\+?\s*years?',         # "3+ years" or "3 years"
        r'(\d+)\s*to\s*\d+\s*years?', # "2 to 4 years"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, experience_str.lower())
        if match:
            return int(match.group(1))
    
    return 0

def save_job_to_json(job: Dict[str, Any]) -> None:
    """Save job to JSON file as fallback"""
    try:
        # Load existing jobs
        try:
            with open("jobs.json", "r") as f:
                jobs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            jobs = []

        # Add new job
        jobs.append(job)

        # Save updated jobs
        with open("jobs.json", "w") as f:
            json.dump(jobs, f, indent=2, default=str)
            
        logger.info(f"Job saved to JSON: {job['title']}")
    except Exception as e:
        logger.error(f"Failed to save job to JSON: {e}")
        raise

def sync_json_with_mongodb() -> None:
    """Sync jobs.json file with MongoDB database"""
    try:
        if jobs_collection is None:
            logger.warning("MongoDB not available, skipping JSON sync")
            return
            
        # Get all active jobs from MongoDB
        mongo_jobs = list(jobs_collection.find({"status": "active"}, {"_id": 0}))
        
        # Save to JSON file
        with open("jobs.json", "w") as f:
            json.dump(mongo_jobs, f, indent=2, default=str)
            
        logger.info(f"Synced {len(mongo_jobs)} jobs from MongoDB to JSON")
    except Exception as e:
        logger.error(f"Failed to sync JSON with MongoDB: {e}")

# -------------------------------
# Endpoint: Sync JSON with MongoDB
# -------------------------------
@app.route('/sync_jobs', methods=['POST'])
def sync_jobs_endpoint():
    try:
        sync_json_with_mongodb()
        return jsonify({"message": "Jobs synced successfully"})
    except Exception as e:
        logger.error(f"Error syncing jobs: {e}")
        return jsonify({"error": "Failed to sync jobs", "details": str(e)}), 500

# -------------------------------
# Endpoint: Get all jobs
# -------------------------------
@app.route('/jobs', methods=['GET'])
def get_jobs():
    try:
        # Get query parameters
        limit = request.args.get('limit', 50, type=int)
        limit = min(limit, 100) # Cap at 100 results
        
        # Try MongoDB first, fallback to JSON
        if jobs_collection is not None:
            try:
                jobs = list(jobs_collection.find({}, {"_id": 0}))
                logger.info(f"Retrieved {len(jobs)} jobs from MongoDB")
                return jsonify({"jobs": jobs, "source": "mongodb"})
            except Exception as mongo_error:
                logger.warning(f"MongoDB query failed, using JSON fallback: {mongo_error}")
        
        # Fallback to JSON file
        try:
            with open("jobs.json", "r") as f:
                jobs = json.load(f)
            jobs = jobs[:limit] # Apply limit
            logger.info(f"Retrieved {len(jobs)} jobs from JSON")
            return jsonify({"jobs": jobs, "source": "json"})
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify({"jobs": [], "source": "json"})
            
    except Exception as e:
        logger.error(f"Error getting jobs: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Endpoint: Update job
# -------------------------------
@app.route('/jobs/<job_id>', methods=['PUT'])
def update_job(job_id: str):
    try:
        if not job_id:
            return jsonify({'error': 'Job ID is required'}), 400
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        # Validate job data
        validation_errors = validate_job_data(data)
        if validation_errors:
            return jsonify({'error': 'Validation failed', 'details': validation_errors}), 400

        # Process skills
        skills = data.get('skills')
        if isinstance(skills, str):
            skills = [s.strip().lower() for s in skills.split(',') if s.strip()]
        elif isinstance(skills, list):
            skills = [s.strip().lower() for s in skills if s.strip()]

        updated_job = {
            "title": data.get('title').strip(),
            "company": data.get('company', '').strip() or "Company Not Specified",
            "location": data.get('location', '').strip() or "Location Not Specified",
            "description": data.get('description', '').strip() or data.get('title').strip(),
            "requirements": data.get('requirements', '').strip() or ', '.join(skills),
            "salary": data.get('salary', '').strip() or "Salary Not Specified",
            "skills": skills,
            "experience": data.get('experience').strip(),
            "min_experience": extract_min_experience(data.get('experience', '')),
            "updated_at": datetime.utcnow().isoformat()
        }

        # Try MongoDB first
        if jobs_collection is not None:
            try:
                result = jobs_collection.update_one(
                    {"id": job_id},
                    {"$set": updated_job}
                )
                if result.modified_count > 0:
                    logger.info(f"Job updated in MongoDB: {job_id}")
                    # Sync JSON file with MongoDB
                    sync_json_with_mongodb()
                    return jsonify({"message": "Job updated successfully"})
                else:
                    return jsonify({"error": "Job not found"}), 404
            except Exception as mongo_error:
                logger.warning(f"MongoDB update failed: {mongo_error}")

        # Fallback to JSON
        return update_job_in_json(job_id, updated_job)

    except Exception as e:
        logger.error(f"Error updating job: {e}")
        return jsonify({"error": "Failed to update job", "details": str(e)}), 500

# -------------------------------
# Endpoint: Delete job
# -------------------------------
@app.route('/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id: str):
    try:
        if not job_id:
            return jsonify({'error': 'Job ID is required'}), 400
        # Try MongoDB first
        if jobs_collection is not None:
            try:
                result = jobs_collection.delete_one({"id": job_id})
                if result.deleted_count > 0:
                    logger.info(f"Job deleted from MongoDB: {job_id}")
                    # Sync JSON file with MongoDB
                    sync_json_with_mongodb()
                    return jsonify({"message": "Job deleted successfully"})
                else:
                    return jsonify({"error": "Job not found"}), 404
            except Exception as mongo_error:
                logger.warning(f"MongoDB delete failed: {mongo_error}")

        # Fallback to JSON
        return delete_job_from_json(job_id)

    except Exception as e:
        logger.error(f"Error deleting job: {e}")
        return jsonify({"error": "Failed to delete job", "details": str(e)}), 500

def update_job_in_json(job_id: str, updated_job: Dict[str, Any]):
    """Update job in JSON file"""
    try:
        with open("jobs.json", "r") as f:
            jobs = json.load(f)
        
        for i, job in enumerate(jobs):
            if job.get('id') == job_id:
                jobs[i].update(updated_job)
                with open("jobs.json", "w") as f:
                    json.dump(jobs, f, indent=2, default=str)
                logger.info(f"Job updated in JSON: {job_id}")
                # Try to sync with MongoDB if available
                try:
                    sync_json_with_mongodb()
                except:
                    pass  # Ignore sync errors in fallback mode
                return jsonify({"message": "Job updated successfully"})
        
        return jsonify({"error": "Job not found"}), 404
    except Exception as e:
        logger.error(f"Failed to update job in JSON: {e}")
        raise

def delete_job_from_json(job_id: str):
    """Delete job from JSON file"""
    try:
        with open("jobs.json", "r") as f:
            jobs = json.load(f)
        
        original_length = len(jobs)
        jobs = [job for job in jobs if job.get('id') != job_id]
        
        if len(jobs) < original_length:
            with open("jobs.json", "w") as f:
                json.dump(jobs, f, indent=2, default=str)
            logger.info(f"Job deleted from JSON: {job_id}")
            # Try to sync with MongoDB if available
            try:
                sync_json_with_mongodb()
            except:
                pass  # Ignore sync errors in fallback mode
            return jsonify({"message": "Job deleted successfully"})
        else:
            return jsonify({"error": "Job not found"}), 404
    except Exception as e:
        logger.error(f"Failed to delete job from JSON: {e}")
        raise

# -------------------------------
# Endpoint: Get all parsed resumes
# -------------------------------
@app.route('/resumes', methods=['GET'])
def get_resumes():
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503
            
        # Get query parameters
        limit = request.args.get('limit', 50, type=int)
        limit = min(limit, 100) # Cap at 100 results
        
        resumes = list(resumes_collection.find({}, {"_id": 0}))  # exclude Mongo _id
        return jsonify(resumes)
    except Exception as e:
        logger.error(f"Error getting resumes: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Endpoint: Update resume status
# -------------------------------
@app.route('/update_status', methods=['POST'])
def update_status():
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        email = data.get("email")
        new_status = data.get("status")

        if not email or not new_status:
            return jsonify({"error": "Missing email or status"}), 400

        # Validate status
        valid_statuses = ['Pending', 'Shortlisted', 'Rejected', 'Under Review']
        if new_status not in valid_statuses:
            return jsonify({'error': f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400
        # Sanitize email
        email = sanitize_input(email)

        result = resumes_collection.update_one(
            {"email": email},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow()}}
        )

        if result.modified_count > 0:
            logger.info(f"Status updated for {email}: {new_status}")
            return jsonify({"message": "Status updated successfully"})
        else:
            return jsonify({"message": "No matching resume found or status already set"})

    except Exception as e:
        logger.error(f"Error updating status: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Endpoint: Get all resume matches
# -------------------------------
@app.route('/resume_matches', methods=['GET'])
def get_resume_matches():
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503
        
        logger.info("=== FETCHING RESUME MATCHES ===")
        resumes = list(resumes_collection.find({}, {"_id": 0}))
        logger.info(f"Found {len(resumes)} resumes in database")

        requested_method = request.args.get('method', 'keyword')  # Default to keyword matching
        
        results = []
        for resume in resumes:
            logger.info(f"Processing resume for: {resume.get('email', 'No email')}")
            try:
                # Check if candidate has applied for any jobs
                applications_collection = db['applications']
                candidate_applications = list(applications_collection.find(
                    {'candidate_email': resume.get('email')},
                    {'job_id': 1}
                ))
                
                # Get all potential job matches for this candidate
                all_matches = match_jobs(resume)
                
                if candidate_applications:
                    # Mark jobs that the candidate has applied for
                    applied_job_ids = [app['job_id'] for app in candidate_applications]
                    for match in all_matches:
                        match['applied'] = match.get('id') in applied_job_ids
                    
                    logger.info(f"Found {len(all_matches)} potential matches, {len(applied_job_ids)} applied jobs")
                else:
                    # No applications found - still show all potential matches
                    for match in all_matches:
                        match['applied'] = False
                    logger.info(f"Found {len(all_matches)} potential matches, no job applications")
                
                # Always show all potential matches
                matches = all_matches
                
                actual_method = "keyword"
                fallback = False
                response_time = None
                error_msg = None
                total_found = len(matches) if matches else 0
                returned = len(matches) if matches else 0
                cached = False
                result_item = {
                    "candidate": resume,
                    "matches": matches,
                    "status": resume.get("status", "Pending"),
                    "matching_metadata": {
                        "requested_method": requested_method,
                        "actual_method": actual_method,
                        "fallback": fallback,
                        "response_time": response_time,
                        "error": error_msg,
                        "total_found": total_found,
                        "returned": returned,
                        "cached": cached
                    }
                }
                results.append(result_item)
                logger.info(f"Added {len(matches)} matches for {resume.get('email', 'No email')} using method {actual_method} (fallback: {fallback}, cached: {cached}, response_time: {response_time}, error: {error_msg})")
            except Exception as match_error:
                logger.error(f"Error matching jobs for {resume.get('email', 'No email')}: {match_error}")
                # Continue with other resumes even if one fails
                result_item = {
                    "candidate": resume,
                    "matches": [],
                    "status": resume.get("status", "Pending"),
                    "matching_metadata": {
                        "requested_method": requested_method,
                        "actual_method": None,
                        "fallback": False,
                        "response_time": None,
                        "error": str(match_error),
                        "total_found": None,
                        "returned": None,
                        "cached": False
                    }
                }
                results.append(result_item)

        logger.info(f"Returning {len(results)} results")
        logger.info("=== RESUME MATCHES FETCHED ===")
        
        # Convert datetime objects to strings for JSON serialization
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_datetime(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetime(item) for item in obj]
            else:
                return obj
        
        serializable_results = convert_datetime(results)
        return jsonify(serializable_results)

    except Exception as e:
        logger.error(f"ERROR in get_resume_matches: {str(e)}")
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Endpoint: Get resume statistics
# -------------------------------
@app.route('/stats', methods=['GET'])
def get_stats():
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503

        # Get basic counts
        total_resumes = resumes_collection.count_documents({})
        shortlisted = resumes_collection.count_documents({"status": "Shortlisted"})
        rejected = resumes_collection.count_documents({"status": "Rejected"})
        pending = resumes_collection.count_documents({"status": {"$in": ["Pending", None]}})

        # Get top skills
        pipeline = [
            {"$unwind": "$skills"},
            {"$group": {"_id": "$skills", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        top_skills = list(resumes_collection.aggregate(pipeline))

        # Get location distribution
        location_pipeline = [
            {"$group": {"_id": "$location", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        locations = list(resumes_collection.aggregate(location_pipeline))

        return jsonify({
            "total_resumes": total_resumes,
            "shortlisted": shortlisted,
            "rejected": rejected,
            "pending": pending,
            "top_skills": top_skills,
            "top_locations": locations
        })

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Endpoint: Search resumes
# -------------------------------
@app.route('/search_resumes', methods=['GET'])
def search_resumes():
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503

        # Get query parameters
        query = request.args.get('q', '').strip()
        skills = request.args.get('skills', '').strip()
        location = request.args.get('location', '').strip()
        status = request.args.get('status', '').strip()
        limit = min(int(request.args.get('limit', 50)), 100)  # Max 100 results

        # Build MongoDB query
        mongo_query = {}
        
        if query:
            mongo_query["$or"] = [
                {"name": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}},
                {"skills": {"$regex": query, "$options": "i"}}
            ]
        
        if skills:
            skill_list = [s.strip().lower() for s in skills.split(',')]
            mongo_query["skills"] = {"$in": skill_list}
        
        if location:
            mongo_query["location"] = {"$regex": location, "$options": "i"}
        
        if status:
            mongo_query["status"] = status

        # Execute query
        results = list(resumes_collection.find(mongo_query, {"_id": 0}).limit(limit))
        
        return jsonify({
            "results": results,
            "count": len(results),
            "query": {
                "text": query,
                "skills": skills,
                "location": location,
                "status": status
            }
        })

    except Exception as e:
        logger.error(f"Error searching resumes: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Endpoint: Bulk update resume status
# -------------------------------
@app.route('/bulk_update_status', methods=['POST'])
def bulk_update_status():
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        emails = data.get('emails', [])
        new_status = data.get('status')

        if not emails or not new_status:
            return jsonify({'error': 'Missing emails or status'}), 400

        if new_status not in ['Pending', 'Shortlisted', 'Rejected', 'Under Review']:
            return jsonify({'error': 'Invalid status'}), 400

        # Validate emails
        if not isinstance(emails, list):
            return jsonify({'error': 'Emails must be a list'}), 400
        # Sanitize emails
        emails = [sanitize_input(email) for email in emails if email]

        # Update multiple documents
        result = resumes_collection.update_many(
            {"email": {"$in": emails}},
            {"$set": {"status": new_status, "updated_at": datetime.utcnow()}}
        )

        logger.info(f"Bulk updated {result.modified_count} resumes to status: {new_status}")
        return jsonify({
            "message": f"Updated {result.modified_count} resumes",
            "modified_count": result.modified_count
        })

    except Exception as e:
        logger.error(f"Error bulk updating status: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Endpoint: Get resume file
# -------------------------------
@app.route('/resume_file/<email>', methods=['GET'])
def get_resume_file(email: str):
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503

        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Sanitize email
        email = sanitize_input(email)
        logger.info(f"Serving resume file for: {email}")
        
        # Find the resume document
        resume = resumes_collection.find_one({"email": email})
        if not resume:
            logger.warning(f"Resume not found for email: {email}")
            return jsonify({'error': 'Resume not found'}), 404
        
        # Check if file_id exists
        file_id = resume.get('file_id')
        if not file_id:
            logger.warning(f"No file_id found for email: {email}")
            return jsonify({'error': 'Resume file not available - file was not saved'}), 404
        
        # Construct file path
        file_path = os.path.join(UPLOAD_FOLDER, file_id)
        logger.info(f"Looking for file at: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"Resume file not found on server: {file_path}")
            return jsonify({
                'error': 'Resume file not found on server',
                'details': f'Expected file: {file_id}'
            }), 404
        
        # Get original filename for download
        original_filename = resume.get('original_filename', 'resume.pdf')
        
        logger.info(f"Serving file: {file_path} as {original_filename}")
        
        # Return the file for viewing (not as attachment for browser viewing)
        return send_file(
            file_path,
            as_attachment=False,  # Changed to False so it opens in browser
            download_name=original_filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Error serving resume file for {email}: {e}")
        return jsonify({"error": f"Failed to serve resume file: {str(e)}"}), 500

# -------------------------------
# Endpoint: Delete resume
# -------------------------------
@app.route('/resumes/<email>', methods=['DELETE'])
def delete_resume(email: str):
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503

        if not email:
            return jsonify({'error': 'Email is required'}), 400
        # Sanitize email
        email = sanitize_input(email)

        result = resumes_collection.delete_one({"email": email})
        
        if result.deleted_count > 0:
            logger.info(f"Resume deleted: {email}")
            return jsonify({"message": "Resume deleted successfully"})
        else:
            return jsonify({"error": "Resume not found"}), 404

    except Exception as e:
        logger.error(f"Error deleting resume: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------------
# Endpoint: Health check with system info
# -------------------------------
@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET'])
def health_check():
    try:
        # Check MongoDB connection
        mongo_status = "connected" if client and client.admin.command('ping') else "disconnected"
    except:
        mongo_status = "disconnected"

    # Check OpenAI API
    openai_status = "configured" if os.getenv("OPENAI_API_KEY") else "not configured"

    return jsonify({
        "message": "SmartHire backend is running!",
        "status": "healthy",
        "version": "1.0.0",
        "services": {
            "mongodb": mongo_status,
            "openai": openai_status,
            "spacy": "loaded" if nlp else "not loaded"
        },
        "timestamp": datetime.utcnow().isoformat()
    })

# -------------------------------
# Error handlers
# -------------------------------
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "File too large. Maximum size is 16MB"}), 413

@app.errorhandler(500)
def internal_server_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# -------------------------------
# Endpoint: Apply for a job
# -------------------------------
@app.route('/apply_job', methods=['POST'])
def apply_job():
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        candidate_email = data.get('candidate_email')
        job_id = data.get('job_id')
        cover_letter = data.get('cover_letter', '')
        
        if not candidate_email or not job_id:
            return jsonify({'error': 'candidate_email and job_id are required'}), 400
        
        # Validate that candidate exists
        candidate = resumes_collection.find_one({'email': candidate_email})
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
        
        # Validate that job exists
        job = jobs_collection.find_one({'id': job_id}) if jobs_collection else None
        if not job:
            # Try JSON fallback
            try:
                with open('jobs.json', 'r') as f:
                    jobs = json.load(f)
                job = next((j for j in jobs if j.get('id') == job_id), None)
            except:
                job = None
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Create application record
        applications_collection = db['applications']
        application = {
            'candidate_email': candidate_email,
            'candidate_name': candidate.get('name', 'Unknown'),
            'job_id': job_id,
            'job_title': job.get('title', 'Unknown'),
            'company': job.get('company', 'Unknown'),
            'applied_at': datetime.utcnow(),
            'status': 'applied',
            'cover_letter': cover_letter,
            'application_source': 'web'
        }
        
        try:
            # Check if already applied
            existing = applications_collection.find_one({
                'candidate_email': candidate_email,
                'job_id': job_id
            })
            
            if existing:
                return jsonify({'error': 'Already applied for this job'}), 409
            
            # Insert application
            result = applications_collection.insert_one(application)
            if result.inserted_id:
                logger.info(f"Job application created: {candidate_email} -> {job_id}")
                return jsonify({
                    'message': 'Application submitted successfully',
                    'application_id': str(result.inserted_id),
                    'job_title': job.get('title'),
                    'company': job.get('company')
                })
            else:
                return jsonify({'error': 'Failed to submit application'}), 500
                
        except Exception as e:
            logger.error(f"Error creating application: {e}")
            return jsonify({'error': 'Failed to submit application'}), 500
        
    except Exception as e:
        logger.error(f"Error in apply_job: {e}")
        return jsonify({'error': str(e)}), 500

# -------------------------------
# Endpoint: Get candidate's applications with fitness scores
# -------------------------------
@app.route('/my_applications/<candidate_email>', methods=['GET'])
def get_my_applications(candidate_email):
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503
        
        # Get candidate data
        candidate = resumes_collection.find_one({'email': candidate_email}, {'_id': 0})
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
        
        # Get candidate's applications
        applications_collection = db['applications']
        applications = list(applications_collection.find(
            {'candidate_email': candidate_email},
            {'_id': 0}
        ))
        
        if not applications:
            return jsonify({
                'candidate': candidate,
                'applications': [],
                'message': 'No applications found'
            })
        
        # Get fitness scores for applied jobs only
        results = []
        for application in applications:
            job_id = application['job_id']
            
            # Get job details
            job = jobs_collection.find_one({'id': job_id}, {'_id': 0}) if jobs_collection else None
            if not job:
                # Try JSON fallback
                try:
                    with open('jobs.json', 'r') as f:
                        jobs = json.load(f)
                    job = next((j for j in jobs if j.get('id') == job_id), None)
                except:
                    job = None
            
            if job:
                # Calculate fitness score for this specific job
                job_matches = match_jobs(candidate)
                job_match = next((match for match in job_matches if match.get('id') == job_id), None)
                
                if job_match:
                    fitness_score = job_match.get('match_percentage', 0)
                    scores_breakdown = job_match.get('scores', {})
                    skill_matches = job_match.get('skill_matches', [])
                    missing_skills = job_match.get('missing_skills', [])
                else:
                    # Fallback: calculate basic fitness
                    fitness_score = 0
                    scores_breakdown = {}
                    skill_matches = []
                    missing_skills = job.get('skills', [])
                
                result = {
                    'application': application,
                    'job_details': job,
                    'fitness_score': fitness_score,
                    'scores_breakdown': scores_breakdown,
                    'skill_matches': skill_matches,
                    'missing_skills': missing_skills
                }
                results.append(result)
        
        # Sort by fitness score (highest first)
        results.sort(key=lambda x: x['fitness_score'], reverse=True)
        
        return jsonify({
            'candidate': candidate,
            'applications': results,
            'total_applications': len(results)
        })
        
    except Exception as e:
        logger.error(f"Error in get_my_applications: {e}")
        return jsonify({'error': str(e)}), 500

# -------------------------------
# Endpoint: Get all applications (for HR/admin)
# -------------------------------
@app.route('/all_applications', methods=['GET'])
def get_all_applications():
    try:
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503
        
        applications_collection = db['applications']
        applications = list(applications_collection.find({}, {'_id': 0}))
        
        # Group by job
        job_applications = {}
        for app in applications:
            job_id = app['job_id']
            if job_id not in job_applications:
                job_applications[job_id] = {
                    'job_id': job_id,
                    'job_title': app['job_title'],
                    'company': app['company'],
                    'applications': []
                }
            
            # Get candidate details and fitness score
            candidate = resumes_collection.find_one({'email': app['candidate_email']}, {'_id': 0})
            if candidate:
                # Calculate fitness for this job
                job_matches = match_jobs(candidate)
                job_match = next((match for match in job_matches if match.get('id') == job_id), None)
                fitness_score = job_match.get('match_percentage', 0) if job_match else 0
                
                app_with_fitness = {
                    **app,
                    'candidate_details': candidate,
                    'fitness_score': fitness_score
                }
                job_applications[job_id]['applications'].append(app_with_fitness)
        
        # Sort applications within each job by fitness score
        for job_id in job_applications:
            job_applications[job_id]['applications'].sort(
                key=lambda x: x['fitness_score'], reverse=True
            )
        
        return jsonify({
            'job_applications': list(job_applications.values()),
            'total_jobs_with_applications': len(job_applications),
            'total_applications': len(applications)
        })
        
    except Exception as e:
        logger.error(f"Error in get_all_applications: {e}")
        return jsonify({'error': str(e)}), 500

# -------------------------------
# Initialize application
# -------------------------------
def initialize_app():
    """Initialize the application and sync jobs if needed"""
    try:
        logger.info("Initializing SmartHire application...")
        
        # Sync JSON file with MongoDB on startup
        if jobs_collection is not None:
            try:
                sync_json_with_mongodb()
                logger.info("Jobs synced successfully on startup")
            except Exception as e:
                logger.warning(f"Failed to sync jobs on startup: {e}")
        else:
            logger.warning("MongoDB not available, skipping startup sync")
            
    except Exception as e:
        logger.error(f"Error during app initialization: {e}")

# -------------------------------
# Run the Flask App
# -------------------------------
if __name__ == '__main__':
    initialize_app()
    logger.info("Starting SmartHire backend server...")
    app.run(debug=True, host='0.0.0.0', port=5000)

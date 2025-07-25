from flask import Flask, request, jsonify, send_file, Response
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from src.resume_parser.extract_text import extract_text_from_pdf
from src.resume_parser.parser import parse_resume
from src.resume_parser.matcher import match_jobs
import spacy
from flask_cors import CORS
import json
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from werkzeug.utils import secure_filename
import uuid
import re
import base64
from typing import Optional, Dict, Any, List

# Load environment variables
load_dotenv()

# Configure logging
# Ensure logs directory exists
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'smarthire.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Configure CORS for both local development and production
allowed_origins = [
    "http://localhost:3000",  # Local development
    "https://ipca.netlify.app",  # Your Netlify production domain
    "https://smarthire-frontend.vercel.app",  # Vercel production
    "https://smarthire-frontend.netlify.app",  # Alternative Netlify domain
    "https://ipca.netlify.app/",  # With trailing slash
    "*"  # Allow all origins during development (remove in production)
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
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'resumes')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database connection with retry logic
def connect_to_mongodb(max_retries: int = 3) -> Optional[MongoClient]:
    """Connect to MongoDB with retry logic"""
    for attempt in range(max_retries):
        try:
            # Get MongoDB URI from environment variable
            mongodb_uri = os.getenv('MONGODB_URI')
            
            if not mongodb_uri:
                logger.warning("MongoDB URI not found in environment variables")
                return None
                
            client = MongoClient(
                mongodb_uri,
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
# Endpoint: Save parsed resume data
# -------------------------------
@app.route('/save_resume', methods=['POST'])
def save_resume_endpoint():
    try:
        data = request.get_json()
        if not data or 'profile' not in data:
            return jsonify({'error': 'No profile data provided'}), 400

        candidate_profile = data['profile']
        
        # Add metadata
        candidate_profile.update({
            "status": "Pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

        # Validate parsed data
        validation_errors = validate_resume_data(candidate_profile)
        if validation_errors:
            logger.warning(f"Validation errors: {validation_errors}")
            return jsonify({
                'error': 'Resume data incomplete',
                'details': validation_errors,
                'profile': candidate_profile
            }), 422

        # Save to MongoDB or JSON fallback
        saved_successfully = False
        
        if resumes_collection is not None:
            # Try MongoDB first
            try:
                if candidate_profile.get("email"):
                    existing = resumes_collection.find_one({"email": candidate_profile["email"]})
                    if existing:
                        logger.info(f"Updating existing resume for: {candidate_profile['email']}")
                        candidate_profile["updated_at"] = datetime.utcnow()
                        result = resumes_collection.update_one(
                            {"email": candidate_profile["email"]},
                            {"$set": candidate_profile}
                        )
                        saved_successfully = result.modified_count > 0
                    else:
                        logger.info(f"Inserting new resume for: {candidate_profile['email']}")
                        result = resumes_collection.insert_one(candidate_profile)
                        saved_successfully = result.inserted_id is not None
                else:
                    logger.warning("No email found in resume - saving without email")
                    result = resumes_collection.insert_one(candidate_profile)
                    saved_successfully = result.inserted_id is not None
                    
                if saved_successfully:
                    logger.info("Resume saved to MongoDB successfully")
            except Exception as mongo_error:
                logger.warning(f"MongoDB save failed: {mongo_error}")
                saved_successfully = False
        
        # Fallback to JSON file storage if MongoDB failed or not available
        if not saved_successfully:
            try:
                save_resume_to_json(candidate_profile)
                saved_successfully = True
                logger.info("Resume saved to JSON file successfully")
            except Exception as json_error:
                logger.error(f"JSON save also failed: {json_error}")
                return jsonify({'error': 'Failed to save resume data'}), 500
        
        if not saved_successfully:
            return jsonify({'error': 'Failed to save resume data'}), 500

        return jsonify({
            "message": "Resume saved successfully",
            "profile": {k: v for k, v in candidate_profile.items() if k not in ['_id']}
        })

    except Exception as e:
        logger.error(f"ERROR in save_resume_endpoint: {str(e)}")
        return jsonify({'error': f'Error saving resume: {str(e)}'}), 500

# -------------------------------
# Endpoint: Upload and parse resume
# -------------------------------
@app.route('/parse_resume', methods=['POST'])
def parse_resume_endpoint():
    try:
        logger.info("=== RESUME UPLOAD STARTED ===")

        # Ensure upload directory exists
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        # MongoDB is optional - we can work with file storage

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
        
        # Ensure upload directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        logger.info(f"Processing file: {original_filename}")

        # Save file to local filesystem (temporary for processing)
        file.save(filepath)
        logger.info(f"File saved to: {filepath}")
        
        # Also store file content in database for persistence
        try:
            with open(filepath, 'rb') as f:
                file_content = f.read()
                file_base64 = base64.b64encode(file_content).decode('utf-8')
                logger.info(f"File encoded to base64, size: {len(file_base64)} characters")
        except Exception as e:
            logger.error(f"Failed to encode file to base64: {e}")
            file_base64 = None

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

            # Add metadata including file content for persistence
            candidate_profile.update({
                "status": "Pending",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "original_filename": original_filename,
                "file_id": unique_filename,
                "file_content": file_base64,  # Store file in database
                "file_size": len(file_content) if file_base64 else 0,
                "storage_type": "base64"
            })

            logger.info(f"Parsed profile for: {candidate_profile.get('email', 'Unknown')}")

            # Step 3: Save to MongoDB or JSON fallback
            saved_successfully = False
            
            if resumes_collection is not None:
                # Try MongoDB first
                try:
                    if candidate_profile.get("email"):
                        existing = resumes_collection.find_one({"email": candidate_profile["email"]})
                        if existing:
                            logger.info(f"Updating existing resume for: {candidate_profile['email']}")
                            candidate_profile["updated_at"] = datetime.utcnow()
                            result = resumes_collection.update_one(
                                {"email": candidate_profile["email"]},
                                {"$set": candidate_profile}
                            )
                            saved_successfully = result.modified_count > 0
                        else:
                            logger.info(f"Inserting new resume for: {candidate_profile['email']}")
                            result = resumes_collection.insert_one(candidate_profile)
                            saved_successfully = result.inserted_id is not None
                    else:
                        logger.warning("No email found in resume - saving without email")
                        result = resumes_collection.insert_one(candidate_profile)
                        saved_successfully = result.inserted_id is not None
                        
                    if saved_successfully:
                        logger.info("Resume saved to MongoDB successfully")
                except Exception as mongo_error:
                    logger.warning(f"MongoDB save failed: {mongo_error}")
                    saved_successfully = False
            
            # Fallback to JSON file storage if MongoDB failed or not available
            if not saved_successfully:
                try:
                    save_resume_to_json(candidate_profile)
                    saved_successfully = True
                    logger.info("Resume saved to JSON file successfully")
                except Exception as json_error:
                    logger.error(f"JSON save also failed: {json_error}")
                    return jsonify({'error': 'Failed to save resume data'}), 500
            
            if not saved_successfully:
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
        # Ensure data directory exists
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        os.makedirs(data_dir, exist_ok=True)
        jobs_file = os.path.join(data_dir, 'jobs.json')
        
        # Load existing jobs
        try:
            with open(jobs_file, "r") as f:
                jobs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            jobs = []

        # Add new job
        jobs.append(job)

        # Save updated jobs
        with open(jobs_file, "w") as f:
            json.dump(jobs, f, indent=2, default=str)
            
        logger.info(f"Job saved to JSON: {job['title']}")
    except Exception as e:
        logger.error(f"Failed to save job to JSON: {e}")
        raise

def save_resume_to_json(resume: Dict[str, Any]) -> None:
    """Save resume to JSON file as fallback when MongoDB is not available"""
    try:
        # Ensure data directory exists
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        os.makedirs(data_dir, exist_ok=True)
        resumes_file = os.path.join(data_dir, 'resumes.json')
        
        # Load existing resumes
        try:
            with open(resumes_file, "r") as f:
                resumes = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            resumes = []

        # Check if resume already exists (by email)
        email = resume.get('email')
        if email:
            # Update existing resume
            for i, existing_resume in enumerate(resumes):
                if existing_resume.get('email') == email:
                    resumes[i] = resume
                    logger.info(f"Updated existing resume in JSON for: {email}")
                    break
            else:
                # Add new resume
                resumes.append(resume)
                logger.info(f"Added new resume to JSON for: {email}")
        else:
            # No email, just add it
            resumes.append(resume)
            logger.info("Added resume to JSON without email")

        # Save updated resumes
        with open(resumes_file, "w") as f:
            json.dump(resumes, f, indent=2, default=str)
            
        logger.info(f"Resume saved to JSON successfully")
    except Exception as e:
        logger.error(f"Failed to save resume to JSON: {e}")
        raise

def sync_json_with_mongodb() -> None:
    """Sync jobs.json file with MongoDB database"""
    try:
        if jobs_collection is None:
            logger.warning("MongoDB not available, skipping JSON sync")
            return
            
        # Get all active jobs from MongoDB
        mongo_jobs = list(jobs_collection.find({"status": "active"}, {"_id": 0}))
        
        # Ensure data directory exists
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        os.makedirs(data_dir, exist_ok=True)
        jobs_file = os.path.join(data_dir, 'jobs.json')
        
        # Save to JSON file
        with open(jobs_file, "w") as f:
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
            # Ensure data directory exists
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
            jobs_file = os.path.join(data_dir, 'jobs.json')
            
            with open(jobs_file, "r") as f:
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
        # Ensure data directory exists
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        jobs_file = os.path.join(data_dir, 'jobs.json')
        
        with open(jobs_file, "r") as f:
            jobs = json.load(f)
        
        for i, job in enumerate(jobs):
            if job.get('id') == job_id:
                jobs[i].update(updated_job)
                with open(jobs_file, "w") as f:
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
        # Ensure data directory exists
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        jobs_file = os.path.join(data_dir, 'jobs.json')
        
        with open(jobs_file, "r") as f:
            jobs = json.load(f)
        
        original_length = len(jobs)
        jobs = [job for job in jobs if job.get('id') != job_id]
        
        if len(jobs) < original_length:
            with open(jobs_file, "w") as f:
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
# Authentication endpoints
# -------------------------------
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        username = data.get('username')
        password = data.get('password')
        
        # Simple hardcoded authentication (replace with database in production)
        valid_credentials = {
            'recruiter': 'smartHire2024',
            'admin': 'admin123',
            'hr': 'hr@2024'
        }
        
        if username in valid_credentials and valid_credentials[username] == password:
            # In production, use JWT tokens or sessions
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'user': {
                    'username': username,
                    'role': 'recruiter',
                    'token': f'token_{username}_{datetime.utcnow().timestamp()}'
                }
            })
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
            
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@app.route('/verify-token', methods=['POST'])
def verify_token():
    try:
        data = request.get_json()
        token = data.get('token')
        
        # Simple token validation (replace with proper JWT validation in production)
        if token and token.startswith('token_'):
            return jsonify({'valid': True})
        else:
            return jsonify({'valid': False}), 401
            
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return jsonify({'valid': False}), 500

# -------------------------------
# Endpoint: Apply for a job
# -------------------------------
@app.route('/apply_for_job', methods=['POST'])
def apply_for_job():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        candidate_email = data.get('candidate_email')
        job_id = data.get('job_id')
        
        if not candidate_email or not job_id:
            return jsonify({'error': 'Missing candidate_email or job_id'}), 400
            
        # Check if candidate exists
        if resumes_collection is None:
            return jsonify({'error': 'Database connection not available'}), 503
            
        candidate = resumes_collection.find_one({"email": candidate_email})
        if not candidate:
            return jsonify({'error': 'Candidate not found'}), 404
            
        # Check if job exists
        job = jobs_collection.find_one({"id": job_id}) if jobs_collection else None
        if not job:
            # Try to find in JSON fallback
            try:
                data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
                jobs_file = os.path.join(data_dir, 'jobs.json')
                with open(jobs_file, 'r') as f:
                    jobs = json.load(f)
                job = next((j for j in jobs if j.get('id') == job_id), None)
            except:
                pass
                
        if not job:
            return jsonify({'error': 'Job not found'}), 404
            
        # Create application record
        application = {
            "candidate_email": candidate_email,
            "job_id": job_id,
            "job_title": job.get('title', 'Unknown'),
            "applied_at": datetime.utcnow(),
            "status": "Applied"
        }
        
        # Store application in database
        if db:
            applications_collection = db['applications']
            # Check if already applied
            existing = applications_collection.find_one({
                "candidate_email": candidate_email,
                "job_id": job_id
            })
            
            if existing:
                return jsonify({'message': 'Already applied to this job'}), 200
                
            applications_collection.insert_one(application)
            
        return jsonify({
            'message': 'Application submitted successfully',
            'application': {
                'job_title': job.get('title'),
                'applied_at': application['applied_at'].isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error in apply_job: {e}")
        return jsonify({'error': 'Failed to submit application'}), 500

# -------------------------------
# Endpoint: Get candidate applications
# -------------------------------
@app.route('/candidate_applications/<email>', methods=['GET'])
def get_candidate_applications(email):
    try:
        if not email:
            return jsonify({'error': 'Email is required'}), 400
            
        if db is None:
            return jsonify({'applications': []}), 200
            
        applications_collection = db['applications']
        applications = list(applications_collection.find(
            {"candidate_email": email},
            {"_id": 0}
        ))
        
        return jsonify({'applications': applications})
        
    except Exception as e:
        logger.error(f"Error getting candidate applications: {e}")
        return jsonify({'error': 'Failed to get applications'}), 500

# -------------------------------
# Resume matches endpoint - using the working version below

@app.route('/resume_matches', methods=['GET'])
def get_resume_matches():
    try:
        logger.info("=== FETCHING RESUME MATCHES WITH ATS SCORES ===")
        
        # Load resumes from JSON file (simple and reliable)
        try:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
            resumes_file = os.path.join(data_dir, 'resumes.json')
            if os.path.exists(resumes_file):
                with open(resumes_file, 'r') as f:
                    resumes = json.load(f)
                logger.info(f"Found {len(resumes)} resumes in JSON file")
            else:
                logger.info("No resumes.json file found")
                return jsonify([])
        except Exception as e:
            logger.error(f"Could not load resumes from JSON: {e}")
            return jsonify([])
        
        # Create simple results
        results = []
        for resume in resumes:
            result_item = {
                "candidate": resume,
                "ats_score": resume.get("ats_score", 0),
                "applied_jobs": [],
                "status": resume.get("status", "Pending"),
                "total_applications": 0
            }
            results.append(result_item)
        
        logger.info(f"Returning {len(results)} results")
        return jsonify(results)
        resumes = list(resumes_collection.find({}, {"_id": 0}))
        logger.info(f"Found {len(resumes)} resumes in database")
        
        results = []
        for resume in resumes:
            logger.info(f"Processing resume for: {resume.get('email', 'No email')}")
            try:
                # Calculate ATS score by matching against all available jobs
                try:
                    job_matches = match_jobs(resume)
                    
                    # Calculate overall ATS score (average of top 3 matches or best match)
                    if job_matches:
                        top_matches = job_matches[:3]  # Top 3 matches
                        ats_score = sum(match.get('match_percentage', 0) for match in top_matches) / len(top_matches)
                        ats_score = round(ats_score, 1)
                    else:
                        ats_score = resume.get("ats_score", 0)  # Use existing ATS score if no matches
                except Exception as match_error:
                    logger.warning(f"Job matching failed for {resume.get('email', 'No email')}: {match_error}")
                    job_matches = []
                    ats_score = resume.get("ats_score", 0)  # Use existing ATS score from resume
                
                # Get candidate's applications (only if MongoDB is available)
                candidate_applications = []
                if db is not None:
                    try:
                        applications_collection = db['applications']
                        candidate_applications = list(applications_collection.find(
                            {'candidate_email': resume.get('email')},
                            {'job_id': 1, 'job_title': 1, 'applied_at': 1, 'status': 1, '_id': 0}
                        ))
                    except Exception as e:
                        logger.warning(f"Could not fetch applications: {e}")
                        candidate_applications = []
                
                # Get job details for applied jobs
                applied_jobs = []
                if candidate_applications:
                    applied_job_ids = [app['job_id'] for app in candidate_applications]
                    
                    # Get job details from MongoDB or JSON
                    if jobs_collection is not None:
                        try:
                            jobs_cursor = jobs_collection.find(
                                {"id": {"$in": applied_job_ids}}, 
                                {"_id": 0}
                            )
                            applied_jobs = list(jobs_cursor)
                        except Exception as e:
                            logger.warning(f"Could not fetch jobs from MongoDB: {e}")
                            applied_jobs = []
                    else:
                        # Fallback to JSON
                        try:
                            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
                            jobs_file = os.path.join(data_dir, 'jobs.json')
                            with open(jobs_file, 'r') as f:
                                all_jobs = json.load(f)
                            applied_jobs = [job for job in all_jobs if job.get('id') in applied_job_ids]
                        except:
                            applied_jobs = []
                    
                    # Merge application data with job details and add match scores
                    for job in applied_jobs:
                        app_data = next((app for app in candidate_applications if app['job_id'] == job.get('id')), {})
                        job['application_status'] = app_data.get('status', 'Applied')
                        job['applied_at'] = app_data.get('applied_at')
                        
                        # Add match score for this specific job
                        job_match = next((match for match in job_matches if match.get('id') == job.get('id')), None)
                        if job_match:
                            job['match_percentage'] = job_match.get('match_percentage', 0)
                            job['match_scores'] = job_match.get('scores', {})
                        else:
                            job['match_percentage'] = 0
                            job['match_scores'] = {}
                
                logger.info(f"Found {len(applied_jobs)} applied jobs for {resume.get('email', 'No email')}")
                
                # Update resume with calculated ATS score (only if MongoDB is available)
                if resumes_collection is not None:
                    try:
                        resumes_collection.update_one(
                            {"email": resume.get('email')},
                            {"$set": {"ats_score": ats_score, "updated_at": datetime.utcnow()}}
                        )
                    except Exception as e:
                        logger.warning(f"Could not update resume ATS score in MongoDB: {e}")
                
                # Create result with calculated ATS score and applied jobs
                result_item = {
                    "candidate": resume,
                    "ats_score": ats_score,  # Calculated ATS score
                    "applied_jobs": applied_jobs,  # Only jobs they applied for
                    "status": resume.get("status", "Pending"),
                    "total_applications": len(candidate_applications),
                    "top_job_matches": job_matches[:3]  # Include top 3 job matches for reference
                }
                results.append(result_item)
                logger.info(f"Added candidate {resume.get('email', 'No email')} with calculated ATS score: {ats_score} and {len(applied_jobs)} applied jobs")
                
            except Exception as match_error:
                logger.error(f"Error processing candidate {resume.get('email', 'No email')}: {match_error}")
                # Continue with other resumes even if one fails
                result_item = {
                    "candidate": resume,
                    "ats_score": 0,
                    "applied_jobs": [],
                    "status": resume.get("status", "Pending"),
                    "total_applications": 0,
                    "error": str(match_error)
                }
                results.append(result_item)

        logger.info(f"Returning {len(results)} results")
        logger.info("=== RESUME MATCHES FETCHED (ATS SCORE ONLY) ===")
        
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
            
            # Check if resumes folder exists
            if not os.path.exists(UPLOAD_FOLDER):
                logger.error(f"Upload folder does not exist: {UPLOAD_FOLDER}")
                return jsonify({
                    'error': 'Resume storage folder not found',
                    'details': f'Upload folder missing: {UPLOAD_FOLDER}'
                }), 500
            
            # List available files for debugging
            available_files = os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else []
            logger.info(f"Available files in {UPLOAD_FOLDER}: {available_files}")
            
            return jsonify({
                'error': 'Resume file not found on server',
                'details': f'Expected file: {file_id}',
                'suggestion': 'The file may have been lost during server restart or deployment. Please re-upload your resume.',
                'available_files_count': len(available_files)
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
# Endpoint: Clear all candidate data (for fresh start)
# -------------------------------
@app.route('/clear_candidates', methods=['DELETE'])
def clear_candidates():
    try:
        deleted_count = 0
        
        # Clear from MongoDB if available
        if resumes_collection is not None:
            try:
                result = resumes_collection.delete_many({})
                deleted_count = result.deleted_count
                
                # Also clear applications if they exist
                try:
                    applications_collection = db['applications']
                    app_result = applications_collection.delete_many({})
                    logger.info(f"Cleared {app_result.deleted_count} applications from MongoDB")
                except Exception as e:
                    logger.warning(f"Could not clear applications from MongoDB: {e}")
                    
                logger.info(f"Cleared {deleted_count} candidate records from MongoDB")
            except Exception as e:
                logger.warning(f"MongoDB clear failed: {e}")
        else:
            logger.info("MongoDB not available, skipping database clear")
        
        # Clear uploaded resume files
        files_cleared = 0
        try:
            if os.path.exists(UPLOAD_FOLDER):
                for filename in os.listdir(UPLOAD_FOLDER):
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        files_cleared += 1
                logger.info(f"Cleared {files_cleared} uploaded resume files")
        except Exception as e:
            logger.warning(f"Could not clear uploaded files: {e}")
        
        return jsonify({
            "message": "Candidate data cleared successfully",
            "deleted_resumes": deleted_count,
            "files_cleared": files_cleared,
            "status": "success",
            "note": "MongoDB not available - working with file storage only" if resumes_collection is None else "MongoDB cleared successfully"
        })

    except Exception as e:
        logger.error(f"Error clearing candidate data: {e}")
        return jsonify({"error": str(e)}), 500

# Duplicate login endpoint removed

# Login endpoints already exist above

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
                    with open('data/jobs.json', 'r') as f:
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

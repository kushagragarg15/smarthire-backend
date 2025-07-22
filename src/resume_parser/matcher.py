import json
import re
import os
import sys
from difflib import SequenceMatcher
from typing import List, Dict, Any, Tuple
import math

# Enhanced Weights - More balanced approach
SKILL_WEIGHT = 0.5
EXP_WEIGHT = 0.3
EDU_WEIGHT = 0.2

# Skill synonyms and variations for better matching
SKILL_SYNONYMS = {
    'javascript': ['js', 'javascript', 'ecmascript', 'node.js', 'nodejs'],
    'python': ['python', 'python3', 'py'],
    'java': ['java', 'java8', 'java11', 'java17'],
    'react': ['react', 'reactjs', 'react.js'],
    'angular': ['angular', 'angularjs', 'angular2+'],
    'vue': ['vue', 'vuejs', 'vue.js'],
    'node.js': ['node', 'nodejs', 'node.js'],
    'mongodb': ['mongodb', 'mongo', 'nosql'],
    'mysql': ['mysql', 'sql'],
    'postgresql': ['postgresql', 'postgres', 'sql'],
    'aws': ['aws', 'amazon web services', 'cloud'],
    'docker': ['docker', 'containerization'],
    'kubernetes': ['kubernetes', 'k8s'],
    'machine learning': ['ml', 'machine learning', 'artificial intelligence', 'ai'],
    'data science': ['data science', 'data analysis', 'analytics'],
    'html': ['html', 'html5'],
    'css': ['css', 'css3', 'styling'],
    'git': ['git', 'version control', 'github', 'gitlab'],
    'rest api': ['rest', 'api', 'restful', 'web services'],
    'graphql': ['graphql', 'graph ql'],
    'typescript': ['typescript', 'ts'],
    'express': ['express', 'expressjs', 'express.js'],
    'django': ['django', 'python web framework'],
    'flask': ['flask', 'python web framework'],
    'spring': ['spring', 'spring boot', 'java framework'],
    'devops': ['devops', 'ci/cd', 'deployment'],
    'agile': ['agile', 'scrum', 'kanban'],
    'testing': ['testing', 'unit testing', 'integration testing', 'qa'],
    'frontend': ['frontend', 'front-end', 'ui', 'user interface'],
    'backend': ['backend', 'back-end', 'server-side'],
    'fullstack': ['fullstack', 'full-stack', 'full stack']
}

# Education level mapping
EDUCATION_LEVELS = {
    'phd': 5, 'doctorate': 5,
    'master': 4, 'msc': 4, 'mtech': 4, 'mba': 4, 'm.e': 4,
    'bachelor': 3, 'btech': 3, 'b.e': 3, 'bsc': 3, 'b.e.': 3,
    'diploma': 2,
    'certification': 1, 'certificate': 1
}

def extract_years(exp_text: str) -> float:
    """Enhanced experience extraction with better pattern matching"""
    if not exp_text:
        return 0
    
    exp_text = exp_text.lower()
    
    # Multiple patterns for experience extraction
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*years?',  # "2-4 years" or "2 to 4 years"
        r'(\d+(?:\.\d+)?)\+?\s*years?',  # "3+ years" or "3 years"
        r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*months?',  # months
        r'(\d+(?:\.\d+)?)\s*months?',  # single months
        r'over\s+(\d+(?:\.\d+)?)\s*years?',  # "over 3 years"
        r'more\s+than\s+(\d+(?:\.\d+)?)\s*years?',  # "more than 2 years"
        r'(\d+(?:\.\d+)?)\s*yr?s?',  # "3yrs" or "3yr"
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, exp_text)
        if matches:
            if len(matches[0]) == 2:  # Range pattern
                min_exp, max_exp = matches[0]
                return float(min_exp)  # Use minimum experience
            else:
                exp_value = float(matches[0])
                # Convert months to years if needed
                if 'month' in pattern:
                    exp_value = exp_value / 12
                return exp_value
    
    return 0

def normalize_skills(skills: List[str]) -> List[str]:
    """Enhanced skill normalization with synonym handling"""
    if not skills:
        return []
    
    normalized = set()
    
    for skill in skills:
        if not skill:
            continue
            
        # Clean and normalize
        skill = skill.lower().strip()
        skill = re.sub(r'[^\w\s\.\+\-]', '', skill)  # Remove special chars except common ones
        skill = skill.replace('.js', '').replace('.py', '')
        
        # Add original skill
        normalized.add(skill)
        
        # Add synonyms
        for base_skill, synonyms in SKILL_SYNONYMS.items():
            if skill in synonyms:
                normalized.update(synonyms)
                break
    
    return list(normalized)

def calculate_skill_similarity(candidate_skills: List[str], job_skills: List[str]) -> float:
    """Enhanced skill matching with multiple similarity measures"""
    if not candidate_skills or not job_skills:
        return 0.0
    
    candidate_set = set(normalize_skills(candidate_skills))
    job_set = set(normalize_skills(job_skills))
    
    # 1. Exact matches (highest weight)
    exact_matches = len(candidate_set & job_set)
    exact_score = exact_matches / len(job_set) if job_set else 0
    
    # 2. Fuzzy matches for remaining skills
    fuzzy_score = 0
    unmatched_job_skills = job_set - candidate_set
    unmatched_candidate_skills = candidate_set - job_set
    
    if unmatched_job_skills and unmatched_candidate_skills:
        fuzzy_matches = 0
        for job_skill in unmatched_job_skills:
            best_match = 0
            for candidate_skill in unmatched_candidate_skills:
                similarity = SequenceMatcher(None, job_skill, candidate_skill).ratio()
                if similarity > 0.8:  # High threshold for fuzzy matching
                    best_match = max(best_match, similarity)
            if best_match > 0:
                fuzzy_matches += best_match
        
        fuzzy_score = fuzzy_matches / len(unmatched_job_skills) if unmatched_job_skills else 0
    
    # 3. Coverage score (how many job requirements are covered)
    coverage_score = (exact_matches + fuzzy_score * len(unmatched_job_skills)) / len(job_set)
    
    # 4. Bonus for having more skills than required
    bonus = min(0.1, (len(candidate_set) - len(job_set)) * 0.02) if len(candidate_set) > len(job_set) else 0
    
    # Combine scores with weights
    final_score = (exact_score * 0.7) + (fuzzy_score * 0.2) + (coverage_score * 0.1) + bonus
    
    return min(1.0, final_score)

def calculate_experience_score(candidate_exp: float, required_exp: float) -> float:
    """More forgiving experience scoring."""
    if required_exp == 0:
        return 1.0  # Perfect score if no experience is needed
    if candidate_exp >= required_exp:
        # Bonus for being overqualified, but with diminishing returns
        bonus = min(0.1, (candidate_exp - required_exp) * 0.05)
        return min(1.0, 1.0 + bonus) # Cap at 1.0, bonus is small
    else:
        ratio = candidate_exp / required_exp
        return ratio ** 0.5

def apply_scoring_curve(score: float) -> float:
    """
    Applies a modified sigmoid curve to stretch scores.
    - A score of 0.5 becomes ~73%
    - A score of 0.7 becomes ~88%
    - Lower scores are pushed down, higher scores are pushed up.
    """
    k = 6
    x0 = 0.5
    curved_score = 1 / (1 + math.exp(-k * (score - x0)))
    return curved_score

def calculate_education_score(candidate_edu: List[str], job_edu_keywords: List[str]) -> float:
    """Enhanced education matching with level consideration"""
    if not job_edu_keywords:
        return 1.0  # No education requirement
    
    if not candidate_edu:
        return 0.4  # Some base score for missing education info
    
    candidate_text = ' '.join(candidate_edu).lower()
    max_candidate_level = 0
    max_required_level = 0
    
    # Find highest education level for candidate
    for edu_line in candidate_edu:
        edu_line = edu_line.lower()
        for level, value in EDUCATION_LEVELS.items():
            if level in edu_line:
                max_candidate_level = max(max_candidate_level, value)
    
    # Find required education level
    for keyword in job_edu_keywords:
        keyword = keyword.lower()
        for level, value in EDUCATION_LEVELS.items():
            if level in keyword:
                max_required_level = max(max_required_level, value)
    
    # Direct keyword matching
    keyword_matches = 0
    for keyword in job_edu_keywords:
        if keyword.lower() in candidate_text:
            keyword_matches += 1
    
    keyword_score = keyword_matches / len(job_edu_keywords) if job_edu_keywords else 0
    
    # Level-based scoring
    if max_candidate_level >= max_required_level:
        level_score = 1.0
    elif max_candidate_level > 0:
        level_score = max_candidate_level / max_required_level
    else:
        level_score = 0.5  # No clear level found
    
    # Combine scores
    return max(keyword_score, level_score)

def load_jobs_data() -> List[Dict[str, Any]]:
    """Load jobs from MongoDB or JSON fallback"""
    try:
        # Try to import and use MongoDB first
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
        import os
        
        # Get MongoDB URI from environment variable
        mongodb_uri = os.getenv('MONGODB_URI')
        if not mongodb_uri:
            print("MongoDB URI not found in environment variables")
            raise ValueError("MongoDB URI not available")
            
        # Use the MongoDB connection from environment
        client = MongoClient(
            mongodb_uri,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=10,
            minPoolSize=1
        )
        
        # Test connection
        client.admin.command('ping')
        db = client["smarthire"]
        jobs_collection = db["jobs"]
        
        jobs = list(jobs_collection.find({"status": "active"}, {"_id": 0}))
        if jobs:
            print(f"Loaded {len(jobs)} jobs from MongoDB")
            return jobs
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        pass  # Fall back to JSON
    
    # Fallback to JSON file
    try:
        # Get the project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        jobs_file = os.path.join(project_root, 'data', 'jobs.json')
        
        with open(jobs_file, 'r') as f:
            jobs = json.load(f)
            active_jobs = [job for job in jobs if job.get('status', 'active') == 'active']
            print(f"Loaded {len(active_jobs)} jobs from JSON fallback")
            return active_jobs
    except FileNotFoundError:
        print("No jobs.json file found")
        return []

def match_jobs(candidate_profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Job matching with a more realistic scoring algorithm"""
    candidate_skills = candidate_profile.get("skills", [])
    candidate_exp = extract_years(candidate_profile.get("experience", ""))
    candidate_edu = candidate_profile.get("education", [])
    candidate_location = candidate_profile.get("location", "").lower()
    jobs = load_jobs_data()
    if not jobs:
        return []
    job_results = []
    for job in jobs:
        try:
            job_skills = job.get("skills", [])
            job_exp_required = job.get("min_experience", 0)
            job_edu_keywords = job.get("education_keywords", [])
            job_location = job.get("location", "").lower()
            skill_score = calculate_skill_similarity(candidate_skills, job_skills)
            exp_score = calculate_experience_score(candidate_exp, job_exp_required)
            edu_score = calculate_education_score(candidate_edu, job_edu_keywords)
            location_bonus = 0
            if candidate_location and job_location:
                if any(word in job_location for word in candidate_location.split() if len(word) > 2):
                    location_bonus = 0.05
            # 1. Calculate the raw linear score
            raw_final_score = (
                SKILL_WEIGHT * skill_score +
                EXP_WEIGHT * exp_score +
                EDU_WEIGHT * edu_score +
                location_bonus
            )
            raw_final_score = min(1.0, raw_final_score)
            # 2. Apply the non-linear curve to get the final display score
            final_score = apply_scoring_curve(raw_final_score)
            job_result = {
                "id": job.get("id", ""),
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "match_percentage": round(final_score * 100, 1),
                "scores": {
                    "skill": round(skill_score, 3),
                    "experience": round(exp_score, 3),
                    "education": round(edu_score, 3),
                    "raw_final": round(raw_final_score, 3),
                    "final": round(final_score, 3)
                },
            }
            job_results.append(job_result)
        except Exception as e:
            print(f"Error processing job {job.get('title', 'Unknown')}: {e}")
            continue
    job_results.sort(key=lambda x: x["scores"]["final"], reverse=True)
    return job_results

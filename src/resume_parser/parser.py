import openai
import os
import json
import re
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# Load OpenAI API key from environment variable
api_key = os.getenv("OPENAI_API_KEY")
client = None
if api_key:
    try:
        client = openai.OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.warning(f"Could not initialize OpenAI client: {e}")
        client = None
else:
    logger.warning("OpenAI API key not found in environment variables")

def parse_resume(text):
    """
    Parse resume text using OpenAI GPT-3.5-turbo for accurate extraction and ATS scoring
    """
    logger.info(f"Starting resume parsing for text of length: {len(text)}")
    
    if client is None:
        logger.warning("OpenAI client not available, using fallback parser")
        return fallback_parse(text)

    try:
        prompt = f"""
        Extract the following fields from the resume text below and return as a JSON object.
        Also calculate an ATS (Applicant Tracking System) score from 0-100 based on resume quality.

        Fields to extract:
        - name: Full name of the person
        - email: Email address
        - phone: Phone number
        - skills: Array of technical skills and programming languages
        - education: Array of education details (degree, institution, year)
        - experience: Experience in years (e.g., "3 years" or "2.5 years")
        - location: City, state, or country
        - ats_score: Score from 0-100 based on:
          * Resume formatting and structure (20 points)
          * Skills relevance and quantity (25 points)
          * Experience clarity and duration (25 points)
          * Education background (15 points)
          * Contact information completeness (10 points)
          * Overall professional presentation (5 points)

        Resume Text:
        """
        {text}
        """

        Return only valid JSON with these exact field names. If a field is not found, use null.
        Example format:
        {{
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "+1-555-123-4567",
            "skills": ["Python", "JavaScript", "React"],
            "education": ["Bachelor of Science in Computer Science, University of XYZ, 2020"],
            "experience": "3 years",
            "location": "New York, NY",
            "ats_score": 85
        }}
        """

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert resume parser. Extract information accurately and return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1000
        )

        result_text = response.choices[0].message.content.strip()

        # Clean up the response and parse JSON
        # Remove any markdown formatting if present
        if result_text.startswith('```json'):
            result_text = result_text.replace('```json', '').replace('```', '').strip()
        elif result_text.startswith('```'):
            result_text = result_text.replace('```', '').strip()

        parsed_data = json.loads(result_text)

        # Ensure all required fields exist and validate arrays
        skills = parsed_data.get("skills", [])
        education = parsed_data.get("education", [])
        
        # Ensure skills and education are non-empty arrays as required by schema
        if not skills or len(skills) == 0:
            skills = ["General"]  # Default skill if none found
        
        if not education or len(education) == 0:
            education = ["Education details not specified"]  # Default education if none found
        
        return {
            "name": parsed_data.get("name"),
            "email": parsed_data.get("email"),
            "phone": parsed_data.get("phone"),
            "skills": skills,
            "education": education,
            "experience": parsed_data.get("experience"),
            "location": parsed_data.get("location"),
            "ats_score": parsed_data.get("ats_score", 75)  # Default ATS score if not provided
        }

    except Exception as e:
        logger.error(f"Error parsing resume with OpenAI: {e}")
        logger.info("Falling back to regex-based parsing")
        # Fallback to basic parsing if OpenAI fails
        return fallback_parse(text)

def fallback_parse(text):
    """
    Enhanced fallback parsing method using regex patterns and text analysis
    """
    # Basic regex patterns for fallback
    email_pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
    phone_pattern = r'(\+?\d[\d\- ]{9,15})'

    # Enhanced skill detection
    skill_keywords = [
        "python", "javascript", "java", "c++", "c#", "php", "ruby", "go", "rust", "swift",
        "react", "angular", "vue", "node.js", "express", "django", "flask", "spring",
        "mongodb", "mysql", "postgresql", "redis", "elasticsearch",
        "docker", "kubernetes", "aws", "azure", "gcp", "git", "jenkins",
        "html", "css", "bootstrap", "tailwind", "sass", "less",
        "machine learning", "ai", "data science", "nlp", "computer vision",
        "agile", "scrum", "devops", "ci/cd", "microservices", "rest api", "graphql"
    ]

    # Education keywords
    education_keywords = [
        "bachelor", "master", "phd", "btech", "mtech", "b.e", "b.e.", "m.e", "m.e.",
        "b.sc", "m.sc", "bca", "mca", "mba", "diploma", "certification"
    ]

    # Experience patterns
    experience_patterns = [
        r'(\d+\.?\d*)\s+(years?|months?)',
        r'(\d+)\s*-\s*(\d+)\s+(years?|months?)',
        r'experience.*?(\d+)\s+(years?|months?)'
    ]

    # Extract basic info
    email = re.search(email_pattern, text)
    phone = re.search(phone_pattern, text)

    # Extract location (look for common location patterns)
    location = None

    # Common Indian cities and states
    indian_cities = [
        "mumbai", "delhi", "bangalore", "hyderabad", "chennai", "kolkata", "pune", "ahmedabad",
        "jaipur", "lucknow", "kanpur", "nagpur", "indore", "thane", "bhopal", "visakhapatnam",
        "patna", "vadodara", "ghaziabad", "ludhiana", "agra", "nashik", "faridabad", "meerut",
        "rajkot", "kalyan", "vasai", "srinagar", "aurangabad", "dhanbad", "amritsar", "allahabad",
        "ranchi", "howrah", "coimbatore", "jabalpur", "gwalior", "vijayawada", "jodhpur", "madurai",
        "raipur", "kota", "guwahati", "chandigarh", "solapur", "hubli", "mysore", "bareilly",
        "gurgaon", "noida", "greater noida", "faridabad", "ghaziabad", "gurugram", "palwal"
    ]

    indian_states = [
        "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa", "gujarat",
        "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala", "madhya pradesh",
        "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland", "odisha", "punjab",
        "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura", "uttar pradesh",
        "uttarakhand", "west bengal", "delhi", "jammu and kashmir", "ladakh", "chandigarh",
        "dadra and nagar haveli", "daman and diu", "lakshadweep", "puducherry", "andaman and nicobar"
    ]

    # International cities
    international_cities = [
        "new york", "los angeles", "chicago", "houston", "phoenix", "philadelphia", "san antonio",
        "san diego", "dallas", "san jose", "austin", "jacksonville", "fort worth", "columbus",
        "charlotte", "san francisco", "indianapolis", "seattle", "denver", "washington", "boston",
        "el paso", "nashville", "detroit", "oklahoma city", "portland", "las vegas", "memphis",
        "louisville", "baltimore", "milwaukee", "albuquerque", "tucson", "fresno", "sacramento",
        "atlanta", "kansas city", "long beach", "colorado springs", "raleigh", "miami", "virginia beach",
        "omaha", "oakland", "minneapolis", "tulsa", "arlington", "tampa", "new orleans", "wichita",
        "cleveland", "bakersfield", "aurora", "anaheim", "honolulu", "santa ana", "corpus christi",
        "riverside", "lexington", "stockton", "henderson", "saint paul", "st. louis", "milwaukee",
        "cincinnati", "anchorage", "greensboro", "plano", "newark", "lincoln", "orlando", "irvine",
        "durham", "chula vista", "toledo", "fort wayne", "st. petersburg", "laredo", "jersey city",
        "chandler", "madison", "lubbock", "scottsdale", "reno", "buffalo", "gilbert", "glendale",
        "north las vegas", "winston-salem", "chesapeake", "norfolk", "fremont", "garland", "irving",
        "hialeah", "richmond", "boise", "spokane", "baton rouge", "tacoma", "san bernardino",
        "grand rapids", "huntsville", "salt lake city", "fresno", "yuma", "dayton", "lubbock",
        "montgomery", "laredo", "akron", "little rock", "augusta", "port st. lucie", "grand prairie",
        "tallahassee", "overland park", "tempe", "mckinney", "mobile", "cape coral", "shreveport",
        "frisco", "knoxville", "worcester", "brownsville", "vancouver", "fort lauderdale", "sioux falls",
        "ontario", "chatanooga", "providence", "newport news", "rancho cucamonga", "santa clarita",
        "pearland", "east los angeles", "fullerton", "clarksville", "mckinney", "springfield",
        "murfreesboro", "columbia", "killeen", "sterling heights", "new haven", "topeka", "thousand oaks",
        "el monte", "waco", "bellevue", "independence", "peoria", "inland empire", "columbus",
        "charleston", "denton", "visalia", "simi valley", "hartford", "roseville", "thornton",
        "pasadena", "evansville", "salem", "victorville", "cary", "aberdeen", "fargo", "norman",
        "albany", "boulder", "burbank", "clearwater", "davenport", "downey", "elgin", "elizabeth",
        "flint", "fort collins", "fort wayne", "fremont", "frisco", "garland", "gilbert", "glendale",
        "grand prairie", "grand rapids", "greensboro", "henderson", "hialeah", "high point",
        "huntsville", "independence", "irvine", "irving", "jacksonville", "jersey city", "kansas city",
        "knoxville", "laredo", "las vegas", "lexington", "lincoln", "little rock", "long beach",
        "louisville", "lubbock", "madison", "memphis", "mesa", "miami", "milwaukee", "minneapolis",
        "mobile", "montgomery", "moreno valley", "nashville", "new orleans", "newark", "newport news",
        "norfolk", "north las vegas", "oakland", "oklahoma city", "omaha", "orlando", "overland park",
        "oxnard", "palmdale", "paris", "pasadena", "paterson", "pearland", "peoria", "philadelphia",
        "phoenix", "pittsburgh", "plano", "pomona", "port st. lucie", "portland", "providence",
        "raleigh", "rancho cucamonga", "reno", "richmond", "riverside", "rochester", "sacramento",
        "salem", "salinas", "salt lake city", "san antonio", "san bernardino", "san diego",
        "san francisco", "san jose", "santa ana", "santa clarita", "santa rosa", "savannah",
        "scottsdale", "seattle", "shreveport", "sioux falls", "spokane", "springfield", "st. louis",
        "st. paul", "st. petersburg", "stockton", "sunnyvale", "syracuse", "tacoma", "tallahassee",
        "tampa", "tempe", "thornton", "toledo", "topeka", "toronto", "tucson", "tulsa", "tyler",
        "vallejo", "vancouver", "vancouver wa", "ventura", "victorville", "virginia beach",
        "visalia", "waco", "warren", "washington", "waterbury", "west covina", "west valley city",
        "wichita", "wilmington", "winston-salem", "worcester", "yuma"
    ]

    # Look for location patterns in the text
    text_lower = text.lower()

    # Enhanced location patterns for better detection
    location_patterns = [
        r'([A-Z][a-z]+,\s*[A-Z][a-z]+)',  # City, State like "Jaipur, Rajasthan"
        r'([A-Z][a-z]+,\s*[A-Z]{2})',     # City, State (US) like "New York, NY"
        r'([A-Z][a-z]+\s+[A-Z][a-z]+,\s*[A-Z][a-z]+)',  # Multi-word city like "New Delhi, India"
    ]

    for pattern in location_patterns:
        match = re.search(pattern, text)
        if match:
            potential_location = match.group(1)
            # Validate that this doesn't contain skill keywords or common resume words
            location_lower = potential_location.lower()
            skill_indicators = ['python', 'javascript', 'react', 'node', 'mongodb', 'aws', 'html', 'css', 'java', 'sql', 'typescript', 'angular', 'vue', 'systems', 'technology', 'engineering', 'computer', 'science', 'software', 'development']
            if not any(skill in location_lower for skill in skill_indicators):
                location = potential_location
                break

    # If no pattern match, look for city names in the text (prioritize this for Indian cities)
    if not location:
        # Split text into lines and look for location keywords
        lines = text.split('\n')
        for line in lines:
            line_lower = line.lower().strip()

            # Skip lines that are clearly not locations
            if any(skip_word in line_lower for skip_word in ['email', 'phone', 'skills', 'experience', 'education', 'resume', 'cv']):
                continue

            # Check for Indian cities
            for city in indian_cities:
                if city in line_lower:
                    # Extract the full location text
                    location = line.strip()
                    break

            # Check for Indian states
            for state in indian_states:
                if state in line_lower:
                    location = line.strip()
                    break

            # Check for international cities
            for city in international_cities:
                if city in line_lower:
                    location = line.strip()
                    break

            if location:
                break

    # If still no location found, try to find any location-like text
    if not location:
        # Look for lines that might contain location info
        lines = text.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line and len(line) < 50:  # Reasonable length for location
                # Skip if it contains email, phone, or other non-location indicators
                if not any(indicator in line.lower() for indicator in ['@', '+', 'phone', 'email', 'skills', 'experience']):
                    # Check if it looks like a location (contains common location words)
                    if any(word in line.lower() for word in ['city', 'town', 'village', 'district', 'state', 'country', 'india', 'usa', 'uk']):
                        location = line
                        break

    # Final validation: make sure location doesn't contain skill keywords
    if location:
        location_lower = location.lower()
        # If location contains skill keywords, it's probably not a real location
        skill_indicators = ['python', 'javascript', 'react', 'node', 'mongodb', 'aws', 'html', 'css', 'java', 'sql']
        # But allow if it's a known city name
        known_cities = ['bangalore', 'mumbai', 'delhi', 'hyderabad', 'chennai', 'kolkata', 'pune', 'ahmedabad', 'jaipur', 'lucknow', 'kanpur', 'nagpur', 'indore', 'thane', 'bhopal', 'visakhapatnam', 'patna', 'vadodara', 'ghaziabad', 'ludhiana', 'agra', 'nashik', 'faridabad', 'meerut', 'rajkot', 'kalyan', 'vasai', 'srinagar', 'aurangabad', 'dhanbad', 'amritsar', 'allahabad', 'ranchi', 'howrah', 'coimbatore', 'jabalpur', 'gwalior', 'vijayawada', 'jodhpur', 'madurai', 'raipur', 'kota', 'guwahati', 'chandigarh', 'solapur', 'hubli', 'mysore', 'bareilly', 'gurgaon', 'noida', 'greater noida', 'faridabad', 'ghaziabad', 'gurugram']
        # Check if it's a known city first
        is_known_city = any(city in location_lower for city in known_cities)
        # Only filter out if it contains skill keywords AND is not a known city
        if any(skill in location_lower for skill in skill_indicators) and not is_known_city:
            location = None

    # Extract skills (enhanced skill detection from actual resume content)
    skills = []
    text_lower = text.lower()
    
    # Look for skills section first
    skills_section = None
    lines = text.split('\n')
    
    # Find skills section
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if any(keyword in line_lower for keyword in ['skills', 'technical skills', 'technologies', 'programming languages']):
            # Found skills section, extract next few lines
            skills_section = '\n'.join(lines[i:i+10])  # Take next 10 lines
            break
    
    # If no dedicated skills section, use the whole text
    if not skills_section:
        skills_section = text
    
    # Enhanced skill keywords for detection
    skill_keywords = [
        "python", "javascript", "java", "c++", "c#", "php", "ruby", "go", "rust", "swift",
        "react", "angular", "vue", "node.js", "nodejs", "express", "django", "flask", "spring",
        "mongodb", "mysql", "postgresql", "redis", "elasticsearch",
        "docker", "kubernetes", "aws", "azure", "gcp", "git", "jenkins",
        "html", "css", "bootstrap", "tailwind", "sass", "less", "scss",
        "machine learning", "ai", "data science", "nlp", "computer vision",
        "agile", "scrum", "devops", "ci/cd", "microservices", "rest api", "graphql",
        "typescript", "reactjs", "nextjs", "vuejs", "angularjs", "jquery",
        "firebase", "heroku", "netlify", "vercel", "github", "gitlab",
        "linux", "ubuntu", "windows", "macos", "bash", "powershell",
        "tensorflow", "pytorch", "pandas", "numpy", "matplotlib", "scikit-learn"
    ]
    
    skills_section_lower = skills_section.lower()
    
    for skill in skill_keywords:
        if skill in skills_section_lower:
            # Make sure this skill is not part of the location
            if location and skill in location.lower():
                continue
            # Avoid duplicates and format properly
            formatted_skill = skill.replace('.js', 'JS').replace('js', 'JS').title()
            # Handle special cases for common duplicates
            if 'react' in skill.lower():
                formatted_skill = 'React'
            elif 'node' in skill.lower():
                formatted_skill = 'Node.js'
            elif 'angular' in skill.lower():
                formatted_skill = 'Angular'
            elif 'vue' in skill.lower():
                formatted_skill = 'Vue.js'
            
            if formatted_skill not in skills:
                skills.append(formatted_skill)

    # Extract education
    education = []
    lines = text.split('\n')
    for line in lines:
        line_lower = line.lower()
        for keyword in education_keywords:
            if keyword in line_lower:
                education.append(line.strip())
                break

    # Extract experience
    experience = None
    for pattern in experience_patterns:
        match = re.search(pattern, text.lower())
        if match:
            if len(match.groups()) == 2:
                value, unit = match.groups()
                if "month" in unit:
                    years = round(float(value) / 12, 1)
                    experience = f"{years} years"
                else:
                    experience = f"{value} years"
            break

    # Extract name (simple approach - first line that looks like a name)
    name = None
    for line in lines[:5]:  # Check first 5 lines
        line = line.strip()
        if line and len(line.split()) <= 4 and not '@' in line and not re.search(r'\d', line):
            # Simple heuristic: looks like a name
            name = line
            break

    # Ensure skills and education are non-empty arrays as required by schema
    if not skills or len(skills) == 0:
        skills = ["General"]  # Default skill if none found
    
    if not education or len(education) == 0:
        education = ["Education details not specified"]  # Default education if none found

    # Calculate basic ATS score based on available information
    ats_score = calculate_ats_score(name, email.group() if email else None, phone.group() if phone else None, skills, education, experience, location)

    return {
        "name": name,
        "email": email.group() if email else None,
        "phone": phone.group() if phone else None,
        "skills": skills,
        "education": education,
        "experience": experience,
        "location": location,
        "ats_score": ats_score
    }

def calculate_ats_score(name, email, phone, skills, education, experience, location):
    """
    Calculate ATS score based on resume completeness and quality
    """
    score = 0
    
    # Contact information completeness (30 points)
    if name: score += 10
    if email: score += 10
    if phone: score += 10
    
    # Skills assessment (25 points)
    if skills and len(skills) > 0:
        if len(skills) >= 5: score += 25
        elif len(skills) >= 3: score += 20
        elif len(skills) >= 1: score += 15
    
    # Education background (20 points)
    if education and len(education) > 0:
        education_text = ' '.join(education).lower()
        if any(degree in education_text for degree in ['bachelor', 'master', 'phd', 'btech', 'mtech']):
            score += 20
        elif any(degree in education_text for degree in ['diploma', 'certification']):
            score += 15
        else:
            score += 10
    
    # Experience clarity (15 points)
    if experience:
        score += 15
    
    # Location information (10 points)
    if location: score += 10
    
    # Ensure score is within 0-100 range
    return min(100, max(0, score))

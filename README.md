# SmartHire Backend

SmartHire is an AI-powered job matching platform that helps recruiters find the perfect candidates and job seekers discover ideal opportunities. This repository contains the backend API built with Flask and MongoDB.

## 🚀 Features

- **Resume Parsing**: Extract information from PDF resumes using AI
- **Job Matching**: Match candidates with job postings based on skills and experience
- **RESTful API**: Well-documented API endpoints for frontend integration
- **MongoDB Integration**: Flexible data storage with JSON fallback
- **OpenAI Integration**: AI-powered resume parsing and analysis

## 📋 Requirements

- Python 3.8+
- MongoDB 4.4+
- OpenAI API key

## 🛠️ Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/smarthire-backend.git
cd smarthire-backend
```

### 2. Create a virtual environment

```bash
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r config/requirements.txt
```

### 4. Set up environment variables

Create a `.env` file in the project root with the following variables:

```
# MongoDB Connection
MONGODB_URI=mongodb://localhost:27017/

# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Application Settings
DEBUG=True
PORT=5000
HOST=0.0.0.0
```

### 5. Install spaCy model

```bash
python -m spacy download en_core_web_sm
```

### 6. Run the application

```bash
# On Windows
scripts\start_backend.bat

# On macOS/Linux
bash scripts/start_backend.sh

# Or directly with Python
python main.py
```

## 📚 API Documentation

### Resume Management

- `POST /parse_resume` - Upload and parse resume
- `GET /resumes` - Get all resumes
- `GET /resume_matches` - Get resumes with job matches
- `POST /update_status` - Update candidate status

### Job Management

- `POST /add_job` - Create new job posting
- `GET /jobs` - Get all jobs
- `PUT /jobs/<job_id>` - Update job
- `DELETE /jobs/<job_id>` - Delete job

### Matching & Analytics

- `POST /match_jobs` - Match candidate with jobs

### System

- `GET /health` - Health check with system status

## 🧪 Testing

```bash
# Run tests
python -m pytest tests/

# Check database connection
python tests/check_database.py
```

## 📁 Project Structure

See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for a detailed overview of the project structure.

## 🔄 Migration

See [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) for details on the recent project restructuring.

## 🐳 Docker

A Dockerfile is provided in the `config` directory for containerization:

```bash
# Build the Docker image
docker build -t smarthire-backend -f config/Dockerfile .

# Run the container
docker run -p 5000:5000 --env-file .env smarthire-backend
```

## 📄 License

This project is licensed under the MIT License.
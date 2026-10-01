@echo off
REM SmartHire Backend Startup Script (Windows)

echo 🚀 Starting SmartHire Backend...

REM Check if virtual environment exists
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📚 Installing dependencies...
pip install -r requirements.txt


REM Create necessary directories
echo 📁 Creating directories...
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "resumes" mkdir resumes


REM Check for .env file
if not exist ".env" (
    echo ⚠️  Warning: .env file not found. Please copy .env.example to .env and configure your settings.
    echo 📋 Creating .env from example...
    copy .env.example .env
)

echo ✅ Setup complete! Starting server...
python main.py

pause

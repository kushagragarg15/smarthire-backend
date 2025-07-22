@echo off
REM Start the SmartHire backend server
echo Starting SmartHire backend server...

REM Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Python is not installed or not in PATH. Please install Python and try again.
    exit /b 1
)

REM Check if virtual environment exists, if not create one
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r config\requirements.txt

REM Check if MongoDB is running
echo Checking MongoDB connection...
python tests\check_database.py

REM Start the Flask application
echo Starting Flask application...
python main.py
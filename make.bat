@echo off
setlocal

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="install" goto install
if "%1"=="dev" goto dev
if "%1"=="test" goto test
if "%1"=="run" goto run
if "%1"=="setup" goto setup
if "%1"=="clean" goto clean
if "%1"=="lint" goto lint
if "%1"=="format" goto format
goto help

:help
echo SmartHire Development Commands
echo ==============================
echo install    - Install dependencies
echo dev        - Install development dependencies
echo test       - Run tests
echo run        - Run the application
echo setup      - Initial setup (create venv, install deps)
echo clean      - Clean up temporary files
echo lint       - Run linting
echo format     - Format code
goto end

:setup
echo Creating virtual environment...
python -m venv venv
echo Upgrading pip...
call venv\Scripts\activate.bat && python -m pip install --upgrade pip
echo Installing dependencies...
call venv\Scripts\activate.bat && pip install -r config\requirements.txt
goto end

:install
echo Installing dependencies...
pip install -r config\requirements.txt
goto end

:dev
echo Installing dependencies...
pip install -r config\requirements.txt
echo Installing development dependencies...
pip install pytest black flake8 mypy
goto end

:test
echo Running tests...
python -m pytest tests\ -v
goto end

:run
echo Running application...
python main.py
goto end

:clean
echo Cleaning up temporary files...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
for /r . %%f in (*.pyc) do @del "%%f"
for /d /r . %%d in (*.egg-info) do @if exist "%%d" rd /s /q "%%d"
if exist build rd /s /q build
if exist dist rd /s /q dist
goto end

:lint
echo Running linting...
flake8 src\ tests\
mypy src\
goto end

:format
echo Formatting code...
black src\ tests\ main.py setup.py
goto end

:end
endlocal
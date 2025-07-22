#!/bin/bash

# Start the SmartHire backend server
echo "Starting SmartHire backend server..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3 and try again."
    exit 1
fi

# Check if virtual environment exists, if not create one
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r config/requirements.txt

# Check if MongoDB is running
echo "Checking MongoDB connection..."
python tests/check_database.py

# Start the Flask application
echo "Starting Flask application..."
python main.py
#!/bin/bash

# SmartHire Backend Startup Script (Production)

echo "🚀 Starting SmartHire Backend (Production Mode)..."

# Set production environment
export FLASK_ENV=production

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
mkdir -p data logs resumes

# Initialize data files

# Start the application
echo "✅ Starting SmartHire Backend..."
python main.py
#!/bin/bash

# SmartHire Backend Startup Script

echo "🚀 Starting SmartHire Backend..."

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
echo "📁 Creating directories..."
mkdir -p data
mkdir -p logs
mkdir -p resumes

# Initialize empty data files if they don't exist
if [ ! -f "data/jobs.json" ]; then
    echo "[]" > data/jobs.json
fi

if [ ! -f "data/resumes.json" ]; then
    echo "[]" > data/resumes.json
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found. Please copy .env.example to .env and configure your settings."
    echo "📋 Creating .env from example..."
    cp .env.example .env
fi

echo "✅ Setup complete! Starting server..."
python main.py
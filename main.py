#!/usr/bin/env python3
"""
SmartHire Application Entry Point
=================================

This is the main entry point for the SmartHire application.
It imports and runs the Flask application from the organized source structure.
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the main application
if __name__ == '__main__':
    from src.core.main import app
    app.run(debug=True, host='0.0.0.0', port=5000)

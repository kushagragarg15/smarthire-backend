#!/usr/bin/env python3
"""SmartHire entry point: python main.py"""

import os

from src.core.main import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG") == "1")

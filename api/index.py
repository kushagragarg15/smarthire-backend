"""Vercel serverless entry point: every request is routed here (see vercel.json)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.main import app  # noqa: E402,F401

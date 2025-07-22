"""
SmartHire Setup Configuration
============================

Setup script for the SmartHire AI-powered job matching system.
"""

from setuptools import setup, find_packages

try:
    with open("docs/README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()
except FileNotFoundError:
    # Fallback if README.md is not found in docs directory
    long_description = "SmartHire - AI-powered job matching system"

with open("config/requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="smarthire",
    version="1.0.0",
    author="SmartHire Team",
    author_email="team@smarthire.com",
    description="AI-powered job matching system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/smarthire",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "smarthire=src.core.main:app",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.json", "*.txt", "*.md"],
    },
)

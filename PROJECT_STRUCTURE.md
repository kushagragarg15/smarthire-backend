# Project Structure

This document outlines the professional directory structure of the SmartHire application.

```
SmartHire/
├── src/                    # Source code
│   ├── __init__.py
│   ├── core/              # Core application logic
│   │   ├── __init__.py
│   │   └── main.py        # Main application entry point
│   ├── resume_parser/     # Resume parsing functionality
│   │   ├── __init__.py
│   │   ├── extract_text.py
│   │   ├── matcher.py
│   │   └── parser.py
│   └── api/               # API endpoints (future expansion)
│       └── __init__.py
├── tests/                 # Test files
│   ├── __init__.py
│   ├── check_database.py
│   ├── test_frontend_changes.js
│   └── test_job_matching.py
├── docs/                  # Documentation
│   ├── README.md
│   ├── deployment_guide.md
│   ├── frontend_changes_summary.md
│   └── vercel_deployment_guide.md
├── config/                # Configuration files
│   ├── requirements.txt
│   └── Dockerfile
├── scripts/               # Utility scripts
│   └── start_backend.sh
├── data/                  # Data files
│   ├── jobs.json
│   └── resumes/          # Resume files
├── logs/                  # Log files
│   └── smarthire.log
├── assets/                # Static assets
│   └── gradient.svg
└── .gitignore
```

## Directory Descriptions

- **src/**: Contains all source code organized by functionality
- **tests/**: All test files and testing utilities
- **docs/**: Project documentation and guides
- **config/**: Configuration files and environment setup
- **scripts/**: Utility and deployment scripts
- **data/**: Data files, datasets, and user uploads
- **logs/**: Application logs and debugging information
- **assets/**: Static files like images, icons, and stylesheets

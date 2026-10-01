# SmartHire - AI-Powered Resume Matching

Candidates browse open positions and upload a PDF resume. SmartHire parses it (OpenAI, with a built-in
keyword parser as fallback), gives it an ATS score and matches it against every posted job.
Recruiters log in to a dashboard to review candidates, shortlist/reject them and manage job postings.

## Quick start

**Backend** (Python 3.9+), from the project root:

```bash
pip install -r requirements.txt
cp .env.example .env        # everything in it is optional
python main.py              # http://localhost:5000
```

**Frontend** (Node 18+):

```bash
cd smarthire-frontend
npm install
npm start                   # http://localhost:3000, talks to http://localhost:5000
```

Recruiter logins (change them with `RECRUITER_USERS` in `.env`):
`recruiter / smartHire2024`, `admin / admin123`, `hr / hr@2024`.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | not set | GPT resume parsing. Without it (or if the key has no credit) the keyword parser is used. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for parsing |
| `MONGODB_URI` | not set | Use MongoDB. Without it data goes to `data/*.json` and PDFs to `resumes/`. |
| `SECRET_KEY` | random per run | Signs login tokens. Set it so recruiters stay logged in across restarts. |
| `RECRUITER_USERS` | see above | `user:password` pairs, comma-separated |
| `CORS_ORIGINS` | `*` | Comma-separated frontend URLs allowed to call the API |

Frontend: `REACT_APP_API_URL` in `smarthire-frontend/.env.development` (for `npm start`) and
`smarthire-frontend/.env` (for `npm run build`).

## Match score

Each candidate is scored against each active job:

- **Skills, 50%**: share of the job's skills found in the resume (synonyms such as `js`/`javascript` count)
- **Experience, 30%**: candidate years ÷ job's minimum years, capped at 100%
- **Education, 20%**: highest degree found vs a bachelor's baseline

The **ATS score** (0-100) rates the resume itself (structure, skills, experience, education, contact info).

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | | Status, storage backend, OpenAI configured |
| POST | `/login` | | `{username, password}` → `{user: {token}}` |
| POST | `/verify-token` | | `{token}` → `{valid}` |
| GET | `/jobs` | | All jobs |
| POST | `/parse_resume` | | multipart `resume` (PDF) and optional `job_id` |
| GET | `/resume_file/<email>` | | The candidate's PDF |
| GET | `/resume_matches` | ✔ | Candidates with job matches |
| POST | `/update_status` | ✔ | `{email, status}`, status ∈ Pending, Under Review, Shortlisted, Rejected |
| DELETE | `/resumes/<email>` | ✔ | Delete a candidate |
| POST | `/add_job` | ✔ | `{title, skills, experience, company?, location?, description?, salary?}` |
| PUT / DELETE | `/jobs/<id>` | ✔ | Update / delete a job |

Authenticated routes need `Authorization: Bearer <token>`.

## Project structure

```
main.py                      entry point
src/core/main.py             Flask routes
src/core/storage.py          MongoDB or JSON-file storage
src/resume_parser/           PDF text extraction, parsing, matching
smarthire-frontend/src/      React app (App.js = careers page, RecruiterDashboard.js, JobPostingForm.js)
```

## Deployment

- Backend: `Dockerfile` (gunicorn), or any Python host running `gunicorn -w 1 main:app`. Set `MONGODB_URI`
  and `SECRET_KEY` on hosts with temporary disks (Render, Railway) so data and uploaded PDFs survive restarts.
- Frontend: `npm run build` and deploy `build/` (Vercel/Netlify) with `REACT_APP_API_URL` set to the backend URL.

## Tests

```bash
cd smarthire-frontend && npm test
```

## License

MIT, see [LICENSE](LICENSE).

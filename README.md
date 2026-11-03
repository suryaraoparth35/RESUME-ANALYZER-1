# Rolefit — AI Resume Analyzer

Rolefit compares a resume with a specific job description and gives a transparent fit score, prioritized skills gaps, and recommendations grounded in the resume. It runs locally with a React/Vite/Tailwind frontend and a FastAPI backend. Resume files are processed in memory and are not stored in a database or written to disk.

## Features

- PDF and DOCX resume uploads, up to 5 MB.
- PDF/DOCX text extraction, section detection, contact details, and LinkedIn/GitHub link detection.
- A curated taxonomy of 460+ skills across programming, web, data, cloud, security, product, and professional skills, with common aliases such as JS/JavaScript and ML/Machine Learning.
- Live job description counter and validation: at least 80 words, placeholder and repetition checks, English word-frequency screening, job-related signals, and recognizable role skills. The backend repeats the authoritative validation before analysis.
- A 0–100 score with the requested transparent weights:

| Category | Weight | What it measures |
|---|---:|---|
| Structure & sections | 20 | Contact details and summary, experience, education, skills, projects, certifications |
| Priority skill match | 30 | JD skills weighted by requirement wording and repetition |
| Experience relevance | 20 | TF-IDF/cosine relevance between experience evidence and the JD |
| Quantified achievements | 10 | Measurable numbers and outcomes in resume lines |
| Action verbs & writing | 10 | Clear action-led lines and less passive phrasing |
| Formatting & length | 10 | Word count, page count, contact details, and long paragraphs |

- Personalized recommendations, skill priorities, matched/missing skill lists, and an evidence-based score explanation.
- Existing interview practice prompts, job-posting safety scan, and local feedback ranking.
- Optional Claude recommendation wording. The checkbox is opt-in; by default the app uses local rule-based recommendations. Claude receives the job description and analysis highlights, not the original resume file. Add an API key only if you want to enable this option.
- No database, account, or resume file storage.

The score is a coaching estimate, not an ATS score or a hiring prediction. A high score does not guarantee an interview.

## Project structure

```text
resume-analyzer/
├── app/
│   ├── main.py                  # FastAPI, validation, parsing, scoring, recommendations
│   ├── skills_taxonomy.json     # 460+ curated canonical skills and aliases
│   ├── feedback.py              # Resume/JD-specific recommendation rules
│   ├── interview.py             # Interview practice prompts
│   └── job_safety.py             # Job-posting safety heuristics
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js            # Vite dev proxy to FastAPI
│   └── src/
│       ├── App.jsx               # Upload, live validation, results, feedback
│       ├── main.jsx
│       └── styles.css            # Tailwind CSS v4 entry and base styles
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.11–3.13 recommended.
- Node.js 20.19+ or 22.12+ and npm for the Vite frontend.
- A modern browser.

## Setup and run

Run the backend and frontend in separate terminals.

### 1. Install backend dependencies

From the repository root:

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Then install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

The spaCy model improves contact-name extraction. If it is unavailable, the app uses spaCy's built-in English tokenizer and continues to work.

### 2. Start FastAPI

From the repository root:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

The API is at `http://127.0.0.1:8000`; interactive API documentation is at `http://127.0.0.1:8000/docs`.

### 3. Install and start React/Vite

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite forwards `/api` requests to the FastAPI server on port 8000.

### Optional: enable Claude

Copy `.env.example` to `.env` in the repository root and set `ANTHROPIC_API_KEY` to your key. Restart FastAPI. The UI then shows an opt-in checkbox. Analysis still works if the API key is missing or Claude is unavailable; rule-based coaching is used as the fallback.

### Production frontend

Build the static frontend:

```bash
cd frontend
npm run build
```

Then run FastAPI from the repository root. FastAPI serves the generated `frontend/dist` application at `http://127.0.0.1:8000`.

## API endpoints

- `GET /api/health` — service and optional Claude configuration status.
- `POST /api/validate-jd` — live job description validation; form field `job_description`.
- `POST /api/analyze` — multipart fields `resume`, `job_description`, and optional `use_llm`.

## Privacy notes

The backend reads uploaded file bytes into memory, extracts text, analyzes it, and returns JSON. It does not save uploaded files or results. If Claude is configured and a user selects Claude assistance, the application sends the job description and a compact analysis summary (which can include quoted resume evidence) to Anthropic to rewrite recommendations. Do not enable that option for confidential documents unless you are comfortable sharing those excerpts with the configured provider.

Scanned/image-only PDFs need OCR and are not supported yet. DOCX page counts are estimated from word count because the document format does not reliably expose rendered page count.

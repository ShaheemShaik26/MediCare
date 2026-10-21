# MediCare

MediCare is a privacy-first personal health information platform. The initial implementation focuses on a coherent vertical slice: secure account management, medical document upload, extracted facts, direct editing, and a longitudinal health timeline.

## Stack

- Frontend: React + TypeScript + Vite + React Router + TanStack Query
- Backend: FastAPI + SQLAlchemy + Pydantic + PostgreSQL-ready configuration
- Storage: private local file storage in development, compatible with private object storage later
- Testing: pytest for the API layer

## Run locally

1. Create or activate the Python virtual environment.
2. Install backend dependencies from the repository root. The requirements pin the CPU-only PyTorch build:
   - Windows: `python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements.txt`
   - macOS/Linux: `python3 -m pip install --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements.txt`
3. Install frontend dependencies with `npm install` in `frontend`.
4. Change to `backend` and run database migrations:
   - `cd backend`
   - Windows: `..\.venv\Scripts\python -m alembic upgrade head`
   - macOS/Linux: `../.venv/bin/python -m alembic upgrade head`
5. Start the backend from `backend`:
   - `../.venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
6. Start the frontend:
   - `cd frontend`
   - `npm run dev -- --host 0.0.0.0`
7. Open the app at `http://localhost:5173`.

The migrations preserve existing account and document data while adding session-versioning and the optional lifestyle profile table. Back up production data before applying schema changes. Run migrations once as a deployment step, not concurrently from every application worker.

## Core workflow

- Register or log in as a user.
- Upload a document (PDF, PNG, JPEG, TXT, or MD; maximum 10 MB).
- Extracted and manually entered details appear on the timeline immediately. Extractions are labeled as such; manual entries are labeled as added by you. Both remain unconfirmed until you confirm them. Use the timeline’s Edit detail action to correct the type, value, or explicitly stated event date. Dismiss an incorrect extraction from Health records. Existing uploads with no facts can be re-extracted from Health records. Common labeled diagnoses, symptoms, medications, allergies, lab/vital rows, procedures/providers, and lifestyle details are recognized; extraction remains conservative and may miss other document layouts.
- View a searchable, category-filterable timeline ordered by explicit clinical event date when available. Undated facts are labeled “Date not recorded” rather than assigned an upload date. Each item keeps its source document/page/excerpt.
- Search reviewed records with the local, keyword-based “Ask your records” feature. It returns matching facts with source citations, reports missing evidence, and flags differing entries; it is not a generative medical advisor.
- Search general health topics using attributed MedlinePlus public articles. Only the topic you type is sent to MedlinePlus; do not enter personal details or record text. Results are education, not personal medical advice.
- Optionally complete the self-reported Lifestyle profile. It is stored as a separate current snapshot, not dated clinical history. The Lifestyle page also displays source-linked lifestyle details extracted from documents; they appear on the timeline immediately and can be edited there.
- Download your original document from your account.
- Export account data as a ZIP containing JSON records and original uploaded files.
- Permanently delete the account and private files after re-entering the account password.

Images and textless PDF pages use local Tesseract OCR when it is installed and configured on the backend host. OCR-derived facts are labeled as extracted, appear on the timeline immediately, and can be edited or dismissed; OCR may misread medical details. If OCR is unavailable or finds no text, the document is marked for manual review without inferred facts. See `docs/data-sources.md` for the verified local setup.

PDF text and detected table rows are extracted with PyMuPDF; PDFium remains responsible for rasterizing scanned pages for Tesseract OCR. The local `d4data/biomedical-ner-all` DistilBERT model supplements conservative labeled-field extraction with source-linked suggestions. On first use it downloads its public weights from Hugging Face; document text is processed locally and is not sent to Hugging Face. Model suggestions are not clinically validated; they are clearly marked as extracted and remain editable or dismissible. The model is English-only; set `MEDICAL_NER_ENABLED=false` to disable NER and use rule-based extraction only. Tesseract is a separate system executable, not a Python package. The backend checks `TESSERACT_CMD`, `PATH`, and the standard Windows Program Files location. Configure `OCR_LANGUAGES` (default `eng`) or set `OCR_ENABLED=false` in the backend environment as needed.

PyMuPDF is dual-licensed under AGPL-3.0 or commercial terms. This project uses the AGPL-3.0 option; verify the license obligations before distributing or hosting the application.

## Security and privacy

- Passwords are hashed with bcrypt.
- Browser sessions use a short-lived, HttpOnly, SameSite=Lax cookie; the JWT is not returned in the login response or stored in localStorage.
- Unsafe requests made with the session cookie require a matching CSRF cookie/header pair.
- Logout increments a server-side token version, revoking all outstanding tokens for that account.
- Unsafe API requests with an Origin or Referer must match `CORS_ORIGINS`; browser requests using the session cookie must include one.
- API responses include baseline content, framing, referrer, and permissions security headers.
- Login, registration, uploads, and health-topic search have in-process request limits (10/minute, 5/hour, 20/minute, and 10/minute per client address respectively). MedlinePlus lookup also has a 60-request/minute process-wide cap and 12-hour cache; production multi-worker deployments need a shared limiter.
- Set `SECURE_COOKIES=true` when serving over HTTPS; local HTTP development may use `false`.
- Access is scoped to the authenticated user.
- Uploaded files are saved under a private local storage directory.
- The system does not fabricate medical diagnoses or evidence.
- Use the Vite development proxy (`/api` to `http://127.0.0.1:8000`) so the browser app and API share an origin.

## Data-source note

Personal health history relies on user-uploaded documents and locally derived structured facts. The separate general-education search uses the free MedlinePlus Web Service; it does not receive personal record contents. See `docs/data-sources.md` for source limitations.

This is still a development implementation, not a production security or compliance assessment. Review `docs/threat-model.md` before deploying with real health information.
The built-in rate limiter is per-process and is not a substitute for a shared gateway/Redis limiter in multi-worker production. Configure trusted client-address forwarding only at a controlled reverse proxy; forwarded headers are not trusted by this application. Production hosting must also configure TLS, secure secret management, request-body limits, frontend security headers, log redaction, encrypted storage/backups, and retention/deletion policies.

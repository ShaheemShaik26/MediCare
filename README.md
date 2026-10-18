# MediCare

MediCare is a privacy-first personal health intelligence platform. The initial implementation focuses on a coherent vertical slice: secure account management, medical document upload, extracted facts, user review, and a longitudinal health timeline.

## Stack

- Frontend: React + TypeScript + Vite + React Router + TanStack Query
- Backend: FastAPI + SQLAlchemy + Pydantic + PostgreSQL-ready configuration
- Storage: private local file storage in development, compatible with private object storage later
- Testing: pytest for the API layer

## Run locally

1. Create or activate the Python virtual environment.
2. Install backend dependencies from `backend/requirements.txt`.
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

The initial migration is safe to run against an existing MediCare database: it preserves the existing account/document tables and adds the session-version column needed for revocation. Back up production data before applying schema changes. Run migrations once as a deployment step, not concurrently from every application worker.

## Core workflow

- Register or log in as a user.
- Upload a document (PDF, PNG, JPEG, TXT, or MD; maximum 10 MB).
- Review the extracted facts and accept or reject them.
- View the timeline of accepted health events.
- Download your original document from your account.
- Export account data as a ZIP containing JSON records and original uploaded files.
- Permanently delete the account and private files after re-entering the account password.

Images and textless PDF pages use local Tesseract OCR when it is installed and configured on the backend host. OCR-derived facts are labeled and require your review; OCR may misread medical details. If OCR is unavailable or finds no text, the document is marked for manual review without inferred facts. See `docs/data-sources.md` for the verified local setup.

Tesseract is a separate system executable, not a Python package. The backend checks `TESSERACT_CMD`, `PATH`, and the standard Windows Program Files location. Configure `OCR_LANGUAGES` (default `eng`) or set `OCR_ENABLED=false` in the backend environment as needed.

## Security and privacy

- Passwords are hashed with bcrypt.
- Browser sessions use a short-lived, HttpOnly, SameSite=Lax cookie; the JWT is not returned in the login response or stored in localStorage.
- Unsafe requests made with the session cookie require a matching CSRF cookie/header pair.
- Logout increments a server-side token version, revoking all outstanding tokens for that account.
- Unsafe API requests with an Origin or Referer must match `CORS_ORIGINS`; browser requests using the session cookie must include one.
- API responses include baseline content, framing, referrer, and permissions security headers.
- Login, registration, and uploads have in-process request limits (10/minute, 5/hour, and 20/minute per client address respectively).
- Set `SECURE_COOKIES=true` when serving over HTTPS; local HTTP development may use `false`.
- Access is scoped to the authenticated user.
- Uploaded files are saved under a private local storage directory.
- The system does not fabricate medical diagnoses or evidence.
- Use the Vite development proxy (`/api` to `http://127.0.0.1:8000`) so the browser app and API share an origin.

## Data-source note

The initial version relies on user-uploaded documents and locally derived structured facts. External medical sources are documented in `docs/data-sources.md` and are intentionally optional for the first working slice.

This is still a development implementation, not a production security or compliance assessment. Review `docs/threat-model.md` before deploying with real health information.
The built-in rate limiter is per-process and is not a substitute for a shared gateway/Redis limiter in multi-worker production. Configure trusted client-address forwarding only at a controlled reverse proxy; forwarded headers are not trusted by this application. Production hosting must also configure TLS, secure secret management, request-body limits, frontend security headers, log redaction, encrypted storage/backups, and retention/deletion policies.

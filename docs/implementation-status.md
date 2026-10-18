# Implementation status

## Current milestone: secure account workflow + upload + fact review + timeline

### Completed

- Repository scaffolded for a full-stack application.
- FastAPI backend created with auth, file upload, fact review, and timeline endpoints.
- SQLAlchemy models for users, uploaded documents, and medical facts.
- Private document storage in the local development environment.
- Upload validation based on file signatures, supported extensions, image decoding, size limits, and PDF parsing.
- Owner-scoped document download with private/no-store response headers.
- Local Tesseract OCR is configured for images and textless PDF pages; OCR-derived facts are explicitly labeled and remain unreviewed until user action.
- OCR processing stays on the backend host, renders PDF pages only when needed, and applies page-count, pixel, process-time, and document-time bounds.
- Short-lived JWT browser sessions are stored in HttpOnly, SameSite=Lax cookies; unsafe cookie-authenticated requests require a CSRF header.
- Logout increments a persisted per-account token version and invalidates all previously issued sessions.
- Alembic migrations replace implicit `create_all` schema setup; the initial migration adopts existing tables and adds token-version support without dropping records.
- Unsafe API requests validate supplied Origin/Referer values; cookie-authenticated unsafe requests require an origin source.
- API security headers and basic per-process rate limits cover login, registration, and uploads.
- Login responses no longer expose tokens to JavaScript or localStorage; logout clears the session and CSRF cookies.
- Account export downloads a private ZIP with JSON records and original files.
- Account deletion requires password confirmation and removes the account records and private document directory.
- React + Vite frontend with login, registration, document upload, and timeline dashboard.
- API tests covering register, login, document upload, fact review, and cross-user access denial.
- Documentation for data sources, architecture, and implementation notes.

### Next priorities

- Introduce external medical source retrieval behind an explicit evidence layer.
- Extend the timeline with dates and record grouping.
- Replace per-process rate limits with a shared gateway or Redis limiter for multi-worker deployments.
- Add isolated document-processing workers, deployment log redaction, backup/retention policies, and operational monitoring.

### Validation status

The targeted backend API tests pass, and the React app builds and lints cleanly.

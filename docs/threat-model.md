# Threat model: document intake and review

## Scope

This milestone covers account authentication, export/deletion, medical document uploads, extracted facts, and original-document downloads in a local development deployment. It is not a regulatory or compliance assessment.

## Assets

- Uploaded medical documents and their extracted text.
- User accounts, password hashes, access tokens, and ownership relationships.
- User-confirmed facts and their source excerpts/page references.

## Threats and current controls

| Threat | Current control | Remaining limitation |
|---|---|---|
| Oversized upload exhausting resources | Upload is read in bounded chunks and rejected above the configured 10 MB limit. PDF pages and image pixel counts are capped. | Request-body limits should also be configured at the reverse proxy in a deployment. |
| Spoofed MIME type or extension | The backend checks supported extensions and file signatures; images and PDFs are parsed before storage. | Parser vulnerabilities remain possible; keep dependencies patched and isolate processing for production. |
| Malformed or encrypted PDF | Strict PDF parsing rejects unreadable/encrypted files with a clear client error. | No sandboxed worker or asynchronous processing queue is implemented. |
| Cross-account document access | Download and fact endpoints query by both resource ID and authenticated owner; inaccessible resources return 404. | Sharing with explicitly authorized recipients is not implemented. |
| Unauthorized account deletion | Deletion requires an authenticated session and password re-entry; session-authenticated DELETE requests require CSRF validation. | No delayed-deletion window or account recovery process is implemented. |
| Incomplete data export | Export includes structured account/document/fact data plus original uploaded documents; missing or out-of-scope files fail the export. | Export archives are generated on local disk for the duration of the response and rely on host filesystem protections. |
| Public exposure or browser caching | Files are outside the frontend static directory and served through an authenticated route with `private, no-store` and `nosniff` headers. | Local disk is not encrypted by the app; protect the host filesystem and backups. |
| Token theft through script-readable storage | The session JWT is stored in an HttpOnly cookie and not exposed to JavaScript. | XSS can still perform requests as the user; CSP and broader XSS hardening remain necessary. |
| Cross-site request forgery | Cookie-authenticated unsafe requests require a random CSRF cookie copied to a request header; cookies are SameSite=Lax. Unsafe requests also validate supplied Origin/Referer values and reject cookie requests missing both. | Review the complete browser/session threat model and production origin list before deployment. |
| Stolen or logged-out bearer/session token | Tokens include a per-account version checked against the database; logout increments the version and revokes all outstanding tokens for that account. | Logging out one device revokes all devices; short token expiry remains a second defense. |
| Cross-origin state-changing requests | Unsafe API requests with Origin/Referer headers must match configured `CORS_ORIGINS`; session-cookie requests without either header are rejected. | Confirm the production origin list and reverse-proxy behavior; non-browser requests without origin headers are still supported when they do not use session cookies. |
| Login, registration, or upload abuse | In-process request limits cover these endpoints and responses return 429/Retry-After. | Limits are not shared between workers/hosts; deploy a shared gateway or Redis-backed limiter and configure trusted client IP forwarding. |
| Browser content execution/framing | API responses include CSP (`default-src 'none'`), `nosniff`, frame-denial, referrer and permissions policies; HSTS is emitted when secure cookies are enabled. | The frontend host must independently send and validate its own production CSP/security headers. |
| Schema drift on updates | Alembic migrations run as an explicit deployment step; initial baseline preserves pre-existing tables while adding the token-version field. | Apply migrations once, back up production databases, and review every future migration before rollout. |
| False claims from scanned or narrative records | Local Tesseract OCR and local biomedical NER produce labeled, source-linked extracted details. They appear immediately on the timeline but remain visually distinguished from user-confirmed facts and can be edited or dismissed. Model weights are downloaded from Hugging Face, but personal document text is processed locally and not sent to a model provider. | OCR and model output are not clinically validated; English is the only configured language. NER can misread negation/context. Immediate visibility means users may see incorrect extracted content before correcting or dismissing it. Parser, OCR, and model processing are not isolated in a resource-limited worker. |
| Third-party disclosure through font/model requests | The frontend uses system fonts and does not fetch fonts from a third party. The local NER downloads public model files only; personal record content remains local. | First-use model-weight download requires internet access; verify deployment egress policy and model-cache protection. |

## Trust boundaries

1. The browser and upload metadata are untrusted.
2. The API authenticates users and derives ownership from the token, never the submitted file or resource identifiers alone.
3. The private storage adapter is trusted only for local development; production storage, encryption, backup retention, and deletion need deployment-specific design.
4. Extracted text is untrusted user data. It is not clinical confirmation and is displayed as sourced material for user review.

## Production blockers

- Configure HTTPS, secure secret management, rate limiting, security headers, request-body limits, and log redaction.
- Decide on encrypted private object storage, retention, backup, export, and deletion processes.
- Isolate untrusted PDF/image processing and add operational monitoring.
- Replace per-process rate limits with shared infrastructure and add resource-limited asynchronous OCR workers before processing real-user documents at scale.
- Complete a jurisdiction-specific privacy and regulatory assessment before making any compliance claims.

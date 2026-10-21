# Implementation status

Status reviewed: 2026-10-19

MediCare is an early full-stack prototype. It is not the complete AI-assisted platform described in the product proposal, and it is not ready to be represented as a clinically validated or production healthcare service.

## Product feature status

| Proposed feature | Status | Current behavior and remaining work |
|---|---|---|
| Smart medical document processing | Partial prototype | Accepts PDF, PNG, JPEG, TXT, and MD uploads; extracts PDF text and tables with PyMuPDF and can run local English Tesseract OCR. A local DistilBERT biomedical NER model supplements conservative labeled-field extraction with source-linked suggestions for diagnoses, symptoms, medications, and procedures. Extracted candidates are immediately visible and editable on the timeline, but remain labeled unreviewed; users can edit or dismiss them at any time. The model does not decide dates or infer lifestyle. Model output is not clinically validated and may misread negation/context. Arbitrary layouts, ambiguity, duplicate reconciliation, and extraction accuracy are not solved. |
| Personal health timeline | Partial | Displays extracted, user-entered, and confirmed facts immediately, with unreviewed extraction distinguished from user-confirmed content. Preserves source document/excerpt with an original-document action and supports inline editing of type, value, and explicit event date. Orders by explicit event date when available; undated details are clearly labeled and are not assigned upload dates. Users can filter by category and search text/source filenames. It does not group facts into encounters, reconcile conflicting records, or guarantee clinically complete history. |
| Personal health records Q&A | Basic local prototype | An authenticated keyword search over accepted facts returns source excerpts/document/page/event-date citations, explicitly reports when no matching reviewed fact exists, and flags differing values among matching facts. No LLM or external service is called. It is not semantic retrieval, does not search raw documents/unreviewed facts, and does not provide a natural-language clinical explanation. |
| Trusted health knowledge assistant | Basic public-source lookup | Authenticated keyword search of MedlinePlus health topics returns sanitized snippets and HTTPS links with source attribution. Only the user-entered topic is sent externally, never account or record content. This is not AI reasoning, personalized advice, or a comprehensive evidence assistant; timeout, no-result, caching, and rate-limit behavior are handled. |
| Medical claim verification | Not implemented | No claim intake, URL/image processing, evidence retrieval, or supported/contradicted/uncertain assessment. |
| Doctor-ready health summary | Not implemented | No summary generation, review workflow, or explicit sharing authorization. |
| Symptom checker and safe triage | Not implemented | No symptom intake or validated triage rules. |
| Personalized wellness profile | Partial | A private, optional self-reported lifestyle questionnaire can save activity, sleep, diet, tobacco, and alcohol details. Lifestyle facts extracted from uploaded records appear on the main timeline immediately, marked unconfirmed, and are editable there; the Lifestyle page also provides a separate confirmation list. The self-reported profile remains a separate current snapshot and is not presented as dated clinical history. Neither creates AI recommendations or health scores. |
| Medical and emotional support chat | Not implemented | No conversational support feature. |
| MCP server integration | Not implemented | No MCP server or tools. |

## Engineering and data status

- Authentication, owner-scoped API access, upload validation, private local file storage, CSRF/origin protections, and account export/deletion are implemented for the prototype.
- The database uses Alembic migrations. Apply migrations as a deployment step before running a database with the latest code.
- Document extraction combines local rule-based parsing with optional-to-disable local DistilBERT NER. The model downloads from Hugging Face on first use, then performs inference on the backend; record text is not sent to Hugging Face or another model provider. Model candidates require a complete word-boundary match in their source context to filter tokenizer fragments. Tesseract OCR is local and English-only by default. OCR and NER results are surfaced immediately for user checking, not treated as clinically verified.
- The NER model is `d4data/biomedical-ner-all` (DistilBERT, 66.4M parameters, Hub card marked Apache-2.0). Its training data and benchmark results do not establish accuracy on MediCare's uploaded records. Keep `MEDICAL_NER_ENABLED=false` to run only the conservative rule-based extractor.
- PDF text/table processing uses PyMuPDF, which is AGPL-3.0 or commercially licensed; distribution must comply with the selected license.
- The timeline displays unreviewed extracted facts immediately. Its edit control preserves the fact’s confirmation state; users can also explicitly confirm or dismiss facts from Health records. Confirmation is user-provided, not clinical verification. Original source excerpts remain attached when a user edits a fact.
- Synthetic fixtures and API tests cover uploads, PyMuPDF table rows, common lab-row extraction, preservation of compound values, explicit date handling, manual source-linked fact entry, review/timeline behavior, account isolation, and lifestyle-profile storage. They do not establish extraction accuracy, clinical safety, or retrieval quality.
- Other external medical sources are documented as future options. The current public health-topic integration is limited to MedlinePlus; see [data-sources.md](./data-sources.md).
- MedlinePlus keyword search is integrated for general health education. Its provider requests attribution, recommends 12–24-hour caching, and documents 85 requests/minute/IP. The app caches for 12 hours and limits itself to 60 requests/minute per process, but a distributed limiter is still needed for multi-worker production.
- No personal clinical dataset is bundled. Use synthetic records for development and label them as synthetic.

## Initial end-to-end milestone

| Milestone step | Status |
|---|---|
| Upload a sample medical document | Implemented for supported local files. |
| Extract available facts with source references | PyMuPDF PDF text/table extraction, local OCR, conservative labeled fields, and local NER suggestions; broad layout coverage and accuracy evaluation remain outstanding. |
| Display facts for review and correction | Extracted facts appear on the timeline immediately, with source details; inline correction of type/value/event date and accept/dismiss are implemented. Existing documents with no extracted facts can be reprocessed. |
| Persist reviewed facts securely | Accepted status is stored with account ownership and source references. |
| Display facts chronologically | Orders by explicitly extracted/reviewed event date where available; otherwise labels the date as not recorded and sorts by creation time. Conflicts are not resolved. |
| Ask a question about uploaded records and cite supporting sources | Basic deterministic keyword search across accepted facts only, with document/page/excerpt citations and a missing-evidence response. No generative answer or semantic retrieval. |
| Test missing information, extraction errors, authorization boundaries, and conflicting records | API tests cover missing results, conflicting accepted values, source citations, basic upload/OCR failure cases, validation, and owner isolation. No extraction-accuracy evaluation, semantic retrieval benchmark, or clinical review. |

## Validation and production readiness

The API test suite, frontend production build, and frontend lint have passed in local development. A synthetic CPU smoke test observed 24.8 seconds for cold NER model loading plus first inference and 0.13 seconds for a second short inference on this workstation; this small sample is not a response-latency benchmark. These checks demonstrate basic software behavior only; they are not clinical validation, a security/compliance certification, an extraction-accuracy evaluation, or a performance guarantee. The core records workflow sends no record text externally. The separate MedlinePlus lookup sends only its user-entered public health topic.

Before real health information or production deployment, the system still needs appropriate clinical and privacy review, verified event-date and fact-correction workflows, extraction evaluation on representative consented samples, conflict/missing-data behavior, operational monitoring, production storage and key management, deployment security controls, and a validated plan for any external medical evidence integration. Do not use the prototype to make diagnosis or treatment decisions.

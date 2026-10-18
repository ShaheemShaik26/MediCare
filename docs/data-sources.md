# Data sources and verification status

## Summary

The first working slice of MediCare depends primarily on user-uploaded personal health documents and locally derived structured facts. This avoids fabricating clinical data or assuming access to restricted medical datasets.

## Verified and accessible

### 1. User-uploaded documents (local private storage)
- Status: VERIFIED AND ACCESSIBLE
- Date checked: 2026-10-18
- URL: local private storage within the application runtime, not a public web source
- Access method: direct file upload through the application
- Verified fields: file name, MIME type, upload timestamp, document preview text, derived fact values
- License: user-owned content; app stores it privately and does not redistribute it
- Cost: no direct fee in development
- Limitations: extracted details depend on the document quality and may be incomplete or uncertain
- Upload checks: 10 MB maximum by default; supported content is PDF, PNG, JPEG, UTF-8 TXT, and UTF-8 MD; content signatures are checked instead of trusting the client MIME type
- OCR: local Tesseract 5.4.0.20240606 with English (`eng`) language data and orientation/script detection (`osd`); images and textless PDF pages are OCR-processed locally when enabled; OCR-derived facts are marked for review, and unreadable/unavailable documents remain manual review
- OCR installation source: [UB-Mannheim Tesseract 5.4.0.20240606 Windows installer](https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe); SHA-256: `c885fff6998e0608ba4bb8ab51436e1c6775c2bafc2559a19b423e18678b60c9`; installer manifest declares Apache-2.0
- PDF rasterization: pypdfium2, based on PDFium; package metadata identifies BSD-3-Clause and Apache-2.0 licensing
- Local smoke test: generated synthetic PNG and image-backed PDF both returned the expected text on 2026-10-18; this is not an OCR accuracy benchmark
- Limitations: OCR runs on the backend host and may misread text; English is the only configured OCR language; OCR is not clinical validation and never auto-accepts facts
- Features dependent on this source: account-scoped document upload, extraction review, timeline, user records

### 2. Local synthetic fixtures for development
- Status: VERIFIED AND ACCESSIBLE
- Date checked: 2026-10-18
- URL: local fixtures kept in repository test data or generated during tests
- Access method: code-based and environment-local
- Verified fields: deterministic sample text and record metadata
- License: internal development use only
- Cost: none
- Limitations: not real clinical records
- Features dependent on this source: developer tests and demonstration flows

## Documented but not tested

### 3. Public medical education sources (optional future feature)
- Status: DOCUMENTED BUT NOT TESTED
- Date checked: 2026-10-18
- URL: official sources such as health agencies and medical societies
- Access method: API or website fetches
- Verified fields: source title, canonical URL, broad topic coverage
- License: variable; must be individually reviewed before integration
- Cost: usually free, but some sources may require formal access or attribution
- Limitations: not yet wired into the product and not required for the first vertical slice

## Data availability classification

The current application model uses the following classification:

1. Directly available: document metadata, user account metadata, extracted text snippets, fact values from uploaded content
2. Derivable through transformation: notes extracted from document text into diagnosis, medication, allergy, and lab categories
3. Optional or frequently missing: dates, exact medication instructions, provider details, and longitudinal histories across documents
4. Unavailable: guaranteed clinical validation, linked patient identities from public datasets, hidden or restricted source data

The platform intentionally does not claim medical certainty from raw extracted text. All facts remain reviewable and user-confirmed before they appear in the longitudinal timeline.

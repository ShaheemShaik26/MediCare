# Data sources and verification status

## Summary

The first working slice of MediCare depends primarily on user-uploaded personal health documents and locally derived structured facts. This avoids fabricating clinical data or assuming access to restricted medical datasets.

## Verified and accessible

### 1. User-uploaded documents (local private storage)
- Status: VERIFIED AND ACCESSIBLE
- Date checked: 2026-10-18
- URL: local private storage within the application runtime, not a public web source
- Access method: direct file upload through the application
- Verified fields: file name, MIME type, upload timestamp, document preview text, explicitly labeled derived fact values, page number, source excerpt, and an event date only when it is explicitly labeled in supported date formats
- License: user-owned content; app stores it privately and does not redistribute it
- Cost: no direct fee in development
- Limitations: extraction remains a prototype, not general medical-document understanding. PyMuPDF adds reading-order text and detected table rows; rules recognize a limited vocabulary of labeled diagnosis, symptom, medication, allergy, common test/vital, provider/procedure, and lifestyle fields; local NER supplements selected categories. It still misses arbitrary layouts, unfamiliar labels, and unlabeled values, and does not reliably interpret negation or reconcile conflicts. Extracted values require user review and correction.
- Measurement handling: numeric/unit display is limited to a single unambiguous value/unit pair. Compound values such as blood pressure remain intact as text and are not reduced to a misleading single number. The parser does not validate clinical units or meaning.
- Date handling: clinical event dates are assigned only when an event/collection/service-type label is explicitly present. A single explicit date on a page may be associated with its extracted facts; if multiple distinct event dates are present, facts are not assigned an ambiguous page-level date. Generic document metadata dates are not inferred from a date of birth.
- Upload checks: 10 MB maximum by default; supported content is PDF, PNG, JPEG, UTF-8 TXT, and UTF-8 MD; content signatures are checked instead of trusting the client MIME type
- OCR: local Tesseract 5.4.0.20240606 with English (`eng`) language data and orientation/script detection (`osd`); images and textless PDF pages are OCR-processed locally when enabled; OCR-derived facts are marked for review, and unreadable/unavailable documents remain manual review
- OCR installation source: [UB-Mannheim Tesseract 5.4.0.20240606 Windows installer](https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe); SHA-256: `c885fff6998e0608ba4bb8ab51436e1c6775c2bafc2559a19b423e18678b60c9`; installer manifest declares Apache-2.0
- PDF rasterization: pypdfium2, based on PDFium; package metadata identifies BSD-3-Clause and Apache-2.0 licensing
- PDF text/layout extraction: [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/about.html) extracts text in reading order and supplemental table rows; it is dual-licensed under AGPL-3.0 and commercial terms. The project uses the AGPL-3.0 option; assess compliance before distributing or hosting modified versions.
- AI-assisted candidate extraction: [d4data/biomedical-ner-all](https://huggingface.co/d4data/biomedical-ner-all), local DistilBERT token-classification model (66,427,476 parameters; model card metadata says Apache-2.0). The model card states it was trained on MACCROBAT2018 case reports and supports biomedical entity labels including disease/disorder, sign/symptom, medication, procedure, and clinical event. Its reported training corpus is not representative evidence of accuracy on MediCare records, and the model card provides no evaluation results establishing clinical extraction accuracy. It runs on the backend CPU; the first use downloads public model files from Hugging Face. Only model files are downloaded—personal document text remains in local backend inference and is not sent to Hugging Face.
- AI candidate policy: only selected NER categories above a configurable 0.85 model score are proposed, remain unreviewed, and include source context. Candidate spans must match a complete word-boundary phrase in their source context to reject tokenizer fragments. Scores are not calibrated probabilities. NER does not set event dates, generate diagnoses, or auto-accept facts. Disable with `MEDICAL_NER_ENABLED=false` to use rule-based extraction only.
- Local smoke tests: a generated synthetic PNG returned the expected OCR text; a generated ruled PDF table preserved HbA1c and glucose rows. These are functionality checks, not OCR or table-extraction accuracy benchmarks.
- NER runtime smoke test: on this Windows CPU environment, one synthetic narrative took 24.8 seconds including cold model loading and first inference; a second short synthetic narrative took 0.13 seconds. This single-process sample is not a representative latency benchmark or accuracy evaluation.
- Limitations: OCR runs on the backend host and may misread text; English is the only configured OCR language; OCR is not clinical validation and never auto-accepts facts
- Features dependent on this source: account-scoped document upload, extraction review, timeline, user records

Records Q&A uses only facts explicitly accepted by the signed-in user. The current implementation is local keyword matching over those facts and returns stored excerpts/document/page citations or a missing-evidence response. It does not send record contents to an external AI provider and does not constitute clinical advice.

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

## Integrated public source

### 3. MedlinePlus health-topic search
- Status: INTEGRATED; API behavior covered with mocked provider responses
- Date checked: 2026-10-19
- URL: [MedlinePlus Web Service](https://medlineplus.gov/about/developers/webservices/) and `https://wsearch.nlm.nih.gov/ws/query`
- Access method: server-side keyword search against the English `healthTopics` database; only the topic typed into the Health information page is sent. No account identifier, uploaded record, or accepted fact is included.
- Verified fields: public topic title, summary/snippet, and canonical MedlinePlus URL
- License/cost: free public web service; no registration or license required. Results must be attributed, and inclusion does not imply MedlinePlus endorsement.
- Limitations: keyword search, not a medical reasoning or personalized recommendation service. The service is external and can be unavailable or return no results. Only HTTPS MedlinePlus-domain links are shown. The app strips markup from result text, limits result count and response size, uses an 8-second timeout, caches results in process for 12 hours, and limits requests in process to 60/minute. The API also limits per-client requests. These in-process limits are not shared across multiple workers/instances; a production multi-worker deployment needs a shared gateway or distributed rate limiter to enforce the provider's documented limit of 85 requests/minute/IP.
- Features dependent on this source: general health-topic lookup with source attribution and links to full articles

## Documented but not integrated or tested

### 4. Other public medical education sources
- Status: DOCUMENTED BUT NOT INTEGRATED
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

The platform intentionally does not claim medical certainty from raw extracted text. Extracted facts appear in the longitudinal timeline immediately but remain explicitly marked as unconfirmed and editable; user confirmation is separate from clinical verification.

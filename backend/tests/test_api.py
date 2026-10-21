from __future__ import annotations

import atexit
import os
import shutil
import sys
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

test_db = ROOT / f"medicare_test_{uuid.uuid4().hex}.db"
test_storage = ROOT / f"test_storage_{uuid.uuid4().hex}"
os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef"
os.environ["UPLOAD_DIR"] = str(test_storage)
os.environ["SECURE_COOKIES"] = "false"
os.environ["MEDICAL_NER_ENABLED"] = "false"

migration_config = Config(str(ROOT / "backend" / "alembic.ini"))
migration_config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"].replace("%", "%%"))
command.upgrade(migration_config, "head")


def cleanup_test_artifacts():
    from app.database import engine

    engine.dispose()
    test_db.unlink(missing_ok=True)
    shutil.rmtree(test_storage, ignore_errors=True)


atexit.register(cleanup_test_artifacts)

from fastapi.testclient import TestClient

from app.main import _rate_limit_entries, _rate_limit_lock, app

client = TestClient(app)


def setup_function():
    with _rate_limit_lock:
        _rate_limit_entries.clear()


def login_token(email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.cookies.get("medicare_session")
    assert token
    client.cookies.clear()
    return token


def test_register_and_login():
    response = client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "password": "StrongPass123!", "full_name": "Alice Example"},
    )
    assert response.status_code == 200, response.text

    login = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "StrongPass123!"},
    )
    assert login.status_code == 200, login.text
    assert "access_token" not in login.json()
    session_cookie = login.cookies.get("medicare_session")
    csrf_cookie = login.cookies.get("medicare_csrf")
    assert session_cookie
    assert csrf_cookie
    set_cookies = login.headers.get_list("set-cookie")
    session_header = next(cookie.lower() for cookie in set_cookies if cookie.startswith("medicare_session="))
    csrf_header = next(cookie.lower() for cookie in set_cookies if cookie.startswith("medicare_csrf="))
    assert "httponly" in session_header
    assert "samesite=lax" in session_header
    assert "httponly" not in csrf_header
    assert client.cookies.get("medicare_session") == session_cookie

    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "alice@example.com"

    login_csrf = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "StrongPass123!"},
    )
    assert login_csrf.status_code == 403

    missing_csrf = client.post("/api/auth/logout")
    assert missing_csrf.status_code == 403

    logout = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf_cookie, "Origin": "http://localhost:5173"},
    )
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    revoked_bearer = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer " + session_cookie},
    )
    assert revoked_bearer.status_code == 401


def test_origin_validation_and_security_headers(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "secure_cookies", True)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    assert health.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"

    payload = {"email": "origin@example.com", "password": "StrongPass123!", "full_name": "Origin Check"}
    rejected = client.post(
        "/api/auth/register",
        json=payload,
        headers={"Origin": "https://attacker.example"},
    )
    assert rejected.status_code == 403

    malformed_origin = client.post(
        "/api/auth/register",
        json=payload,
        headers={"Origin": "http://["},
    )
    assert malformed_origin.status_code == 403

    accepted = client.post(
        "/api/auth/register",
        json=payload,
        headers={"Referer": "http://localhost:5173/account/register"},
    )
    assert accepted.status_code == 200, accepted.text


def test_sensitive_endpoints_are_rate_limited():
    payload = {"email": "missing@example.com", "password": "incorrect"}
    responses = [
        client.post("/api/auth/login", json=payload)
        for _ in range(11)
    ]
    assert all(response.status_code == 401 for response in responses[:10])
    assert responses[-1].status_code == 429
    assert int(responses[-1].headers["retry-after"]) > 0


def test_initial_migration_adds_token_version_to_existing_database(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect, text

    legacy_database = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{legacy_database}")
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE, "
                "full_name VARCHAR(255) NOT NULL, password_hash VARCHAR(255) NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users (id, email, full_name, password_hash, created_at) "
                "VALUES (1, 'existing@example.com', 'Existing User', 'preserved-hash', CURRENT_TIMESTAMP)"
            )
        )
    legacy_engine.dispose()

    config = Config(str(ROOT / "backend" / "alembic.ini"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{legacy_database}")
    command.upgrade(config, "head")

    migrated_engine = create_engine(f"sqlite:///{legacy_database}")
    with migrated_engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        user = connection.execute(
            text("SELECT email, password_hash, auth_token_version FROM users WHERE id = 1")
        ).one()
    migrated_engine.dispose()

    assert "auth_token_version" in columns
    assert user == ("existing@example.com", "preserved-hash", 0)


def test_document_upload_and_timeline():
    register = client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "password": "StrongPass123!", "full_name": "Bob Example"},
    )
    assert register.status_code == 200, register.text
    token = login_token("bob@example.com", "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}

    payload = (
        b"Visit Summary\nProvider: Dr. Sarah Chen\nDate: 2025-09-15\n"
        b"Event date: September 14, 2025\n"
        b"Diagnosis: Type 2 diabetes. Medication: Metformin 500 mg twice daily. Allergy: Penicillin.\n"
        b"HbA1c: 6.8 %\nExercise: Walking 30 minutes most days.\n"
        b"Tobacco use: Never.\nDiet: Mostly home-cooked meals.\nAlcohol use: Occasionally.\nSleep duration: 7 hours."
    )
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("record.txt", payload, "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    doc_json = upload.json()
    assert doc_json["document_type"] == "Visit Summary"
    assert doc_json["document_date"] == "2025-09-15"
    assert doc_json["provider_name"] == "Dr. Sarah Chen"
    document_id = doc_json["id"]

    facts = client.get(f"/api/documents/{document_id}/facts", headers=headers)
    assert facts.status_code == 200, facts.text
    items = facts.json()
    assert any(item["fact_type"] == "diagnosis" for item in items)
    assert any(item["fact_type"] == "medication" and "Metformin" in item["value"] for item in items)
    assert any(item["fact_type"] == "allergy" and "Penicillin" in item["value"] for item in items)
    assert any(item["fact_type"] == "lifestyle_activity" for item in items)
    assert any(item["fact_type"] == "lifestyle_tobacco" for item in items)
    assert any(item["fact_type"] == "lifestyle_diet" for item in items)
    assert any(item["fact_type"] == "lifestyle_alcohol" for item in items)
    assert any(item["fact_type"] == "lifestyle_sleep" for item in items)
    hba1c = next(item for item in items if item["fact_type"] == "lab")
    assert hba1c["numeric_value"] == 6.8
    assert hba1c["unit"] == "%"
    assert hba1c["event_date"] == "2025-09-14"

    diagnosis = next(item for item in items if item["fact_type"] == "diagnosis")
    review = client.post(
        f"/api/facts/{diagnosis['id']}/review",
        headers=headers,
        json={
            "status": "accepted",
            "fact_type": "diagnosis",
            "value": "Type 2 diabetes (reviewed)",
            "event_date": "2025-09-14",
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "accepted"
    assert review.json()["value"] == "Type 2 diabetes (reviewed)"
    assert review.json()["event_date"] == "2025-09-14"

    timeline = client.get("/api/timeline", headers=headers)
    assert timeline.status_code == 200, timeline.text
    assert len(timeline.json()) >= 1

    download = client.get(f"/api/documents/{document_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == payload
    assert download.headers["cache-control"] == "private, no-store"


def test_manual_fact_from_document_appears_on_timeline_before_confirmation():
    email = f"manual-fact-{uuid.uuid4().hex}@example.com"
    register = client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Manual Fact"},
    )
    assert register.status_code == 200, register.text
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}

    upload = client.post(
        "/api/documents/upload",
        files={"file": ("scan.txt", b"Document reviewed manually.", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    document_id = upload.json()["id"]

    created = client.post(
        f"/api/documents/{document_id}/facts",
        headers=headers,
        json={
            "fact_type": "lab",
            "value": "HbA1c: 6.8 %",
            "event_date": "2025-01-12",
            "page_number": 1,
        },
    )
    assert created.status_code == 201, created.text
    fact = created.json()
    assert fact["status"] == "unreviewed"
    assert fact["event_date"] == "2025-01-12"
    assert fact["page_number"] == 1
    assert fact["source_excerpt"].startswith("User-entered from scan.txt")
    assert fact["numeric_value"] == 6.8
    assert fact["unit"] == "%"
    initial_timeline = client.get("/api/timeline", headers=headers)
    assert initial_timeline.status_code == 200
    assert [item["id"] for item in initial_timeline.json()] == [fact["id"]]
    original_source_excerpt = fact["source_excerpt"]

    edited = client.post(
        f"/api/facts/{fact['id']}/review",
        headers=headers,
        json={
            "status": "unreviewed",
            "value": "HbA1c: 6.9 %",
            "event_date": "2025-01-13",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "unreviewed"
    assert edited.json()["source_excerpt"] == original_source_excerpt
    assert edited.json()["value"] == "HbA1c: 6.9 %"
    assert edited.json()["event_date"] == "2025-01-13"
    assert client.get("/api/timeline", headers=headers).json()[0]["value"] == "HbA1c: 6.9 %"

    accepted = client.post(
        f"/api/facts/{fact['id']}/review",
        headers=headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    timeline = client.get("/api/timeline", headers=headers)
    assert timeline.status_code == 200
    assert timeline.json()[0]["value"] == "HbA1c: 6.9 %"
    assert timeline.json()[0]["event_date"] == "2025-01-13"

    rejected = client.post(
        f"/api/documents/{document_id}/facts",
        headers=headers,
        json={"fact_type": "symptom", "value": "Unwanted extracted detail"},
    )
    assert rejected.status_code == 201
    assert client.post(
        f"/api/facts/{rejected.json()['id']}/review",
        headers=headers,
        json={"status": "rejected"},
    ).status_code == 200
    final_timeline = client.get("/api/timeline", headers=headers)
    assert [item["id"] for item in final_timeline.json()] == [fact["id"]]

    blank = client.post(
        f"/api/documents/{document_id}/facts",
        headers=headers,
        json={"fact_type": "lab", "value": "   "},
    )
    assert blank.status_code == 422

    other_email = f"manual-fact-other-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": other_email, "password": "StrongPass123!", "full_name": "Other User"},
    )
    other_headers = {"Authorization": "Bearer " + login_token(other_email, "StrongPass123!")}
    unauthorized = client.post(
        f"/api/documents/{document_id}/facts",
        headers=other_headers,
        json={"fact_type": "lab", "value": "Not authorized"},
    )
    assert unauthorized.status_code == 404


def test_existing_document_can_be_reextracted_without_duplicate_facts(monkeypatch):
    from app.api.routes import documents as document_routes
    from app.services.document_service import ExtractedFactCandidate

    email = f"reextract-{uuid.uuid4().hex}@example.com"
    register = client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Re-extract"},
    )
    assert register.status_code == 200, register.text
    headers = {"Authorization": "Bearer " + login_token(email, "StrongPass123!")}
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("older.txt", b"Previously uploaded clinical record.", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    document_id = upload.json()["id"]

    candidate = ExtractedFactCandidate(
        fact_type="diagnosis",
        value="Asthma",
        confidence=0.8,
        source_excerpt="Diagnosis: Asthma",
        page_number=1,
        event_date=None,
        numeric_value=None,
        unit=None,
    )
    monkeypatch.setattr(document_routes, "extract_fact_candidates", lambda *args: [candidate])

    response = client.post(f"/api/documents/{document_id}/extract", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["extracted_fact_count"] == 1
    timeline = client.get("/api/timeline", headers=headers)
    assert timeline.status_code == 200
    assert len(timeline.json()) == 1
    assert timeline.json()[0]["status"] == "unreviewed"
    assert timeline.json()[0]["source_excerpt"] == "Diagnosis: Asthma"

    repeated = client.post(f"/api/documents/{document_id}/extract", headers=headers)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["extracted_fact_count"] == 0
    assert len(client.get("/api/timeline", headers=headers).json()) == 1

    other_email = f"reextract-other-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": other_email, "password": "StrongPass123!", "full_name": "Other User"},
    )
    other_headers = {"Authorization": "Bearer " + login_token(other_email, "StrongPass123!")}
    unauthorized = client.post(f"/api/documents/{document_id}/extract", headers=other_headers)
    assert unauthorized.status_code == 404


def test_extraction_handles_common_lab_rows_and_keeps_compound_values_intact():
    email = f"extraction-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Extraction Review"},
    )
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}
    content = (
        b"Lab Results\nDate of Birth: 1985-01-01\nCollection date: 10/06/2025\n"
        b"WBC 6.2 x10^9/L\nHemoglobin 13.4 g/dL\n"
        b"Blood Pressure 120/80 mmHg\n"
        b"Glucose = 100 mg/dL\n"
        b"Medication: Metformin 500 mg on 2025-01-02\n"
        b"Symptoms: occasional dizziness\n"
        b"Exercise frequency: 3 days/week\n"
    )
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("lab-results.txt", content, "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["document_date"] == "10/06/2025"
    facts = client.get(f"/api/documents/{upload.json()['id']}/facts", headers=headers)
    assert facts.status_code == 200, facts.text
    items = facts.json()
    wbc = next(item for item in items if item["value"].startswith("WBC:"))
    hemoglobin = next(item for item in items if item["value"].startswith("Hemoglobin:"))
    blood_pressure = next(item for item in items if item["value"].startswith("Blood Pressure:"))
    glucose = next(item for item in items if item["value"].startswith("Glucose:"))
    medication = next(item for item in items if item["fact_type"] == "medication")
    symptom = next(item for item in items if item["fact_type"] == "symptom")
    activity = next(item for item in items if item["fact_type"] == "lifestyle_activity")

    assert wbc["numeric_value"] == 6.2
    assert wbc["unit"] == "x10^9/L"
    assert hemoglobin["numeric_value"] == 13.4
    assert hemoglobin["unit"] == "g/dL"
    assert blood_pressure["value"] == "Blood Pressure: 120/80 mmHg"
    assert blood_pressure["numeric_value"] is None
    assert glucose["numeric_value"] == 100
    assert glucose["unit"] == "mg/dL"
    assert medication["value"] == "Metformin 500 mg on 2025-01-02"
    assert symptom["value"] == "occasional dizziness"
    assert activity["value"] == "3 days/week"
    assert all(
        item["event_date"] == "2025-10-06"
        for item in (wbc, hemoglobin, blood_pressure, glucose, medication, symptom, activity)
    )

    sentence_upload = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "sentence-record.txt",
                b"Medication: Metformin 500 mg twice daily. The patient reports intermittent dizziness.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert sentence_upload.status_code == 200, sentence_upload.text
    sentence_facts = client.get(
        f"/api/documents/{sentence_upload.json()['id']}/facts",
        headers=headers,
    )
    assert sentence_facts.status_code == 200
    sentence_medication = next(
        item for item in sentence_facts.json() if item["fact_type"] == "medication"
    )
    assert sentence_medication["value"] == "Metformin 500 mg twice daily."
    assert "dizziness" not in sentence_medication["value"]

    ambiguous_dates = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "multi-date.txt",
                b"Event date: 2025-01-01\nDiagnosis: Asthma\nCollection date: 2025-02-02\nGlucose: 95 mg/dL",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert ambiguous_dates.status_code == 200, ambiguous_dates.text
    ambiguous_facts = client.get(
        f"/api/documents/{ambiguous_dates.json()['id']}/facts",
        headers=headers,
    )
    assert ambiguous_facts.status_code == 200
    ambiguous_items = ambiguous_facts.json()
    diagnosis = next(item for item in ambiguous_items if item["fact_type"] == "diagnosis")
    glucose = next(item for item in ambiguous_items if item["value"].startswith("Glucose:"))
    assert diagnosis["event_date"] == "2025-01-01"
    assert glucose["event_date"] == "2025-02-02"
    assert diagnosis["document_id"] == ambiguous_dates.json()["id"]
    assert diagnosis["page_number"] == 1
    assert diagnosis["source_excerpt"] == "Diagnosis: Asthma"

    accepted = client.post(
        f"/api/facts/{activity['id']}/review",
        headers=headers,
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200
    timeline = client.get("/api/timeline", headers=headers)
    assert timeline.status_code == 200
    assert any(item["id"] == activity["id"] for item in timeline.json())


def test_pdf_table_extraction_preserves_lab_row_values():
    import pymupdf

    from app.services.document_service import extract_document_pages

    document = pymupdf.open()
    page = document.new_page()
    x_positions = (50, 170, 280)
    y_positions = (50, 80, 110)
    for x_position in x_positions:
        page.draw_line((x_position, y_positions[0]), (x_position, y_positions[-1]))
    for y_position in y_positions:
        page.draw_line((x_positions[0], y_position), (x_positions[-1], y_position))
    page.insert_text((60, 70), "HbA1c")
    page.insert_text((180, 70), "6.8 %")
    page.insert_text((60, 100), "Glucose")
    page.insert_text((180, 100), "100 mg/dL")
    content = document.tobytes()
    document.close()

    extracted = extract_document_pages(content, "application/pdf")

    assert "HbA1c\t6.8 %" in extracted.pages[0]
    assert "Glucose\t100 mg/dL" in extracted.pages[0]


def test_local_ner_candidates_are_unreviewed_cited_and_never_auto_accepted(monkeypatch):
    from app.config import settings
    from app.services import document_service
    from app.services.medical_ner_service import MedicalEntity

    monkeypatch.setattr(settings, "medical_ner_enabled", True)
    monkeypatch.setattr(
        document_service,
        "recognize_medical_entities",
        lambda text: [
            MedicalEntity("Disease_disorder", "asthma", 0.96, "History of asthma noted during this visit."),
            MedicalEntity("Sign_symptom", "shortness of breath", 0.91, "Reports shortness of breath after exertion."),
            MedicalEntity("Sign_symptom", "headache", 0.91, "Reports headaches after activity."),
            MedicalEntity("Medication", "albuterol", 0.89, "Uses albuterol as needed."),
            MedicalEntity("Medication", "medication", 0.99, "Medication: albuterol as needed."),
            MedicalEntity("Medication", "li", 0.99, "Treatment includes lisinopril."),
            MedicalEntity("Medication", "##sin", 0.99, "Treatment includes lisinopril."),
            MedicalEntity("Date", "2025-04-02", 0.99, "Encounter date: 2025-04-02."),
            MedicalEntity("Disease_disorder", "low score condition", 0.72, "A low score condition."),
        ],
    )
    email = f"ner-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "NER Review"},
    )
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}
    upload = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "narrative.txt",
                b"Clinical note\nEncounter date: 2025-04-02\nNo additional explicitly labeled facts.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    facts = client.get(f"/api/documents/{upload.json()['id']}/facts", headers=headers)
    assert facts.status_code == 200
    items = facts.json()
    assert {item["fact_type"] for item in items} == {"diagnosis", "symptom", "medication"}
    assert any(item["value"] == "headache" for item in items)
    assert all(item["status"] == "unreviewed" for item in items)
    assert all(item["source_excerpt"].startswith("AI suggestion:") for item in items)
    assert all(item["event_date"] == "2025-04-02" for item in items)
    timeline = client.get("/api/timeline", headers=headers)
    assert timeline.status_code == 200
    assert {item["id"] for item in timeline.json()} == {item["id"] for item in items}


def test_records_question_returns_citations_conflicts_and_insufficient_evidence():
    email = f"records-qa-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Records Q&A"},
    )
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}

    documents = []
    for file_name, content in (
        ("record-one.txt", b"Event date: 2024-02-01\nDiagnosis: Type 2 diabetes."),
        ("record-two.txt", b"Event date: 2025-06-12\nDiagnosis: Type 1 diabetes."),
    ):
        upload = client.post(
            "/api/documents/upload",
            files={"file": (file_name, content, "text/plain")},
            headers=headers,
        )
        assert upload.status_code == 200, upload.text
        document_id = upload.json()["id"]
        documents.append(document_id)
        facts = client.get(f"/api/documents/{document_id}/facts", headers=headers)
        assert facts.status_code == 200
        for fact in facts.json():
            accepted = client.post(
                f"/api/facts/{fact['id']}/review",
                headers=headers,
                json={"status": "accepted"},
            )
            assert accepted.status_code == 200

    answer = client.post(
        "/api/records/ask",
        headers=headers,
        json={"question": "What diagnosis is in my records?"},
    )
    assert answer.status_code == 200, answer.text
    result = answer.json()
    assert result["insufficient_evidence"] is False
    assert result["possible_conflict"] is True
    assert len(result["citations"]) == 2
    assert {citation["document_id"] for citation in result["citations"]} == set(documents)
    assert {citation["event_date"] for citation in result["citations"]} == {"2024-02-01", "2025-06-12"}
    timeline = client.get("/api/timeline", headers=headers)
    assert timeline.status_code == 200
    assert [item["event_date"] for item in timeline.json()] == ["2025-06-12", "2024-02-01"]

    missing = client.post(
        "/api/records/ask",
        headers=headers,
        json={"question": "What medication did I take?"},
    )
    assert missing.status_code == 200
    assert missing.json()["insufficient_evidence"] is True
    assert missing.json()["citations"] == []
    assert "does not mean" in missing.json()["answer"]

    unauthenticated = client.post(
        "/api/records/ask",
        json={"question": "What diagnosis is in my records?"},
    )
    assert unauthenticated.status_code == 401

    other_email = f"records-qa-other-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": other_email, "password": "StrongPass123!", "full_name": "Other Records Owner"},
    )
    other_token = login_token(other_email, "StrongPass123!")
    other_answer = client.post(
        "/api/records/ask",
        headers={"Authorization": "Bearer " + other_token},
        json={"question": "What diagnosis is in my records?"},
    )
    assert other_answer.status_code == 200
    assert other_answer.json()["insufficient_evidence"] is True
    assert other_answer.json()["citations"] == []


def test_lifestyle_profile_is_private_persisted_and_validated():
    email = f"lifestyle-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Lifestyle Owner"},
    )
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}

    empty_profile = client.get("/api/lifestyle", headers=headers)
    assert empty_profile.status_code == 200
    assert empty_profile.json() is None

    payload = {
        "activity_frequency": "3-4 days/week",
        "diet_notes": "Mostly home-cooked meals",
        "sleep_hours": 7.5,
        "tobacco_use": "prefer_not_to_say",
        "alcohol_frequency": "occasionally",
        "notes": None,
    }
    saved = client.put("/api/lifestyle", json=payload, headers=headers)
    assert saved.status_code == 200, saved.text
    assert {key: saved.json()[key] for key in payload} == payload

    persisted = client.get("/api/lifestyle", headers=headers)
    assert persisted.status_code == 200
    assert {key: persisted.json()[key] for key in payload} == payload
    assert persisted.json()["updated_at"]

    invalid = client.put(
        "/api/lifestyle",
        json={**payload, "sleep_hours": 25},
        headers=headers,
    )
    assert invalid.status_code == 422

    other_email = f"lifestyle-other-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": other_email, "password": "StrongPass123!", "full_name": "Other Owner"},
    )
    other_token = login_token(other_email, "StrongPass123!")
    other_profile = client.get("/api/lifestyle", headers={"Authorization": "Bearer " + other_token})
    assert other_profile.status_code == 200
    assert other_profile.json() is None


def test_upload_validation_and_private_document_download():
    email = f"upload-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Upload Owner"},
    )
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": f"Bearer {token}"}

    mismatch = client.post(
        "/api/documents/upload",
        files={"file": ("record.pdf", b"Diagnosis: asthma", "application/pdf")},
        headers=headers,
    )
    assert mismatch.status_code == 422

    malformed_pdf = client.post(
        "/api/documents/upload",
        files={"file": ("record.pdf", b"%PDF-1.7\ninvalid", "application/pdf")},
        headers=headers,
    )
    assert malformed_pdf.status_code == 422

    text = b"Diagnosis: asthma"
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("private.txt", text, "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    document_id = upload.json()["id"]
    own_download = client.get(f"/api/documents/{document_id}/download", headers=headers)
    assert own_download.status_code == 200
    assert own_download.content == text

    other_email = f"other-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": other_email, "password": "StrongPass123!", "full_name": "Other User"},
    )
    other_token = login_token(other_email, "StrongPass123!")
    other_download = client.get(
        f"/api/documents/{document_id}/download",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_download.status_code == 404

    anonymous_download = client.get(f"/api/documents/{document_id}/download")
    assert anonymous_download.status_code == 401


def test_upload_rejects_files_over_size_limit():
    email = f"large-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Upload Owner"},
    )
    token = login_token(email, "StrongPass123!")
    response = client.post(
        "/api/documents/upload",
        files={"file": ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 413


def test_image_upload_is_marked_for_manual_review_when_ocr_is_unavailable(monkeypatch):
    from io import BytesIO

    from PIL import Image
    from pypdf import PdfWriter

    from app.services import document_service

    monkeypatch.setattr(document_service, "_get_ocr_engine", lambda: None)
    email = f"image-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Image Owner"},
    )
    token = login_token(email, "StrongPass123!")
    image_data = BytesIO()
    Image.new("RGB", (8, 8), color="white").save(image_data, format="PNG")

    upload = client.post(
        "/api/documents/upload",
        files={"file": ("scan.png", image_data.getvalue(), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["status"] == "manual_review"
    assert upload.json()["preview_text"] is None
    facts = client.get(
        f"/api/documents/{upload.json()['id']}/facts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert facts.status_code == 200
    assert facts.json() == []

    pdf_data = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(pdf_data)
    scanned_pdf = client.post(
        "/api/documents/upload",
        files={"file": ("scan.pdf", pdf_data.getvalue(), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert scanned_pdf.status_code == 200, scanned_pdf.text
    assert scanned_pdf.json()["status"] == "manual_review"
    assert scanned_pdf.json()["preview_text"] is None


def test_ocr_extraction_is_labeled_and_keeps_page_provenance(monkeypatch):
    from io import BytesIO

    from PIL import Image
    from pypdf import PdfWriter

    from app.services import document_service

    monkeypatch.setattr(document_service, "_get_ocr_engine", lambda: ("fake-tesseract", ""))
    monkeypatch.setattr(
        document_service,
        "_recognize_image",
        lambda image, engine, deadline: "Diagnosis: asthma",
    )
    email = f"ocr-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "OCR Owner"},
    )
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}

    image_data = BytesIO()
    Image.new("RGB", (32, 32), color="white").save(image_data, format="PNG")
    image_upload = client.post(
        "/api/documents/upload",
        files={"file": ("scan.png", image_data.getvalue(), "image/png")},
        headers=headers,
    )
    assert image_upload.status_code == 200, image_upload.text
    assert image_upload.json()["status"] == "ocr_review"
    image_facts = client.get(f"/api/documents/{image_upload.json()['id']}/facts", headers=headers)
    assert image_facts.status_code == 200
    assert image_facts.json()[0]["source_excerpt"] == "OCR text: Diagnosis: asthma"
    assert image_facts.json()[0]["page_number"] == 1

    pdf_data = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(pdf_data)
    pdf_upload = client.post(
        "/api/documents/upload",
        files={"file": ("scan.pdf", pdf_data.getvalue(), "application/pdf")},
        headers=headers,
    )
    assert pdf_upload.status_code == 200, pdf_upload.text
    assert pdf_upload.json()["status"] == "ocr_review"
    pdf_facts = client.get(f"/api/documents/{pdf_upload.json()['id']}/facts", headers=headers)
    assert pdf_facts.status_code == 200
    assert pdf_facts.json()[0]["source_excerpt"] == "OCR text: Diagnosis: asthma"
    assert pdf_facts.json()[0]["page_number"] == 1


def test_ocr_failure_is_reported_and_document_is_not_saved(monkeypatch):
    from io import BytesIO

    from PIL import Image

    from app.services import document_service

    monkeypatch.setattr(document_service, "_get_ocr_engine", lambda: ("fake-tesseract", ""))

    def fail_ocr(image, engine, deadline):
        raise document_service.DocumentProcessingError("OCR failed.")

    monkeypatch.setattr(document_service, "_recognize_image", fail_ocr)
    email = f"ocr-failure-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "OCR Failure"},
    )
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}

    image_data = BytesIO()
    Image.new("RGB", (32, 32), color="white").save(image_data, format="PNG")
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("scan.png", image_data.getvalue(), "image/png")},
        headers=headers,
    )
    assert upload.status_code == 503
    assert upload.json()["detail"] == "OCR failed."
    assert client.get("/api/documents", headers=headers).json() == []


def test_account_export_and_password_confirmed_deletion():
    import io
    import json
    import zipfile

    email = f"account-{uuid.uuid4().hex}@example.com"
    password = "StrongPass123!"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Account Owner"},
    )
    token = login_token(email, password)
    headers = {"Authorization": f"Bearer {token}"}
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("summary.txt", b"Diagnosis: asthma", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    document_id = upload.json()["id"]
    lifestyle = client.put(
        "/api/lifestyle",
        headers=headers,
        json={
            "activity_frequency": "rarely",
            "diet_notes": None,
            "sleep_hours": 8,
            "tobacco_use": "never",
            "alcohol_frequency": None,
            "notes": None,
        },
    )
    assert lifestyle.status_code == 200, lifestyle.text

    export = client.get("/api/account/export", headers=headers)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        assert "records.json" in archive.namelist()
        records = json.loads(archive.read("records.json"))
        assert records["account"]["email"] == email
        assert "password_hash" not in records["account"]
        assert records["documents"][0]["id"] == document_id
        assert archive.read(f"documents/{document_id}_summary.txt") == b"Diagnosis: asthma"
        assert records["lifestyle_profile"]["tobacco_use"] == "never"

    bad_password = client.request(
        "DELETE",
        "/api/account",
        headers=headers,
        json={"password": "incorrect-password"},
    )
    assert bad_password.status_code == 401

    deletion = client.request(
        "DELETE",
        "/api/account",
        headers=headers,
        json={"password": password},
    )
    assert deletion.status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.get("/api/lifestyle", headers=headers).status_code == 401
    assert not (test_storage / f"user_{records['account']['id']}").exists()


def test_user_scope_protection():
    client.post(
        "/api/auth/register",
        json={"email": "charlie@example.com", "password": "StrongPass123!", "full_name": "Charlie Example"},
    )
    client.post(
        "/api/auth/register",
        json={"email": "dana@example.com", "password": "StrongPass123!", "full_name": "Dana Example"},
    )

    token_a = login_token("charlie@example.com", "StrongPass123!")
    token_b = login_token("dana@example.com", "StrongPass123!")

    upload = client.post(
        "/api/documents/upload",
        files={"file": ("private.txt", b"Diagnosis: asthma", "text/plain")},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    doc_id = upload.json()["id"]

    other = client.get(f"/api/documents/{doc_id}/facts", headers={"Authorization": f"Bearer {token_b}"})
    assert other.status_code == 404, other.text


def test_medlineplus_search_requires_auth_and_returns_attributed_topics(monkeypatch):
    from app.api.routes import knowledge
    from app.schemas.knowledge import HealthTopic
    from app.services.medlineplus_service import MedicalKnowledgeUnavailable

    unauthenticated = client.post("/api/knowledge/search", json={"query": "blood pressure"})
    assert unauthenticated.status_code == 401

    email = f"knowledge-{uuid.uuid4().hex}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "full_name": "Knowledge Search"},
    )
    token = login_token(email, "StrongPass123!")
    headers = {"Authorization": "Bearer " + token}
    sent_queries = []

    def search(query):
        sent_queries.append(query)
        return [HealthTopic(
            title="Blood Pressure",
            summary="A public health topic.",
            url="https://medlineplus.gov/bloodpressure.html",
            source="MedlinePlus.gov",
        )]

    monkeypatch.setattr(knowledge, "search_medlineplus", search)
    result = client.post("/api/knowledge/search", headers=headers, json={"query": "blood pressure"})
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "private, no-store"
    assert sent_queries == ["blood pressure"]
    assert result.json() == [{
        "title": "Blood Pressure",
        "summary": "A public health topic.",
        "url": "https://medlineplus.gov/bloodpressure.html",
        "source": "MedlinePlus.gov",
    }]

    def unavailable(query):
        raise MedicalKnowledgeUnavailable("Source unavailable")

    monkeypatch.setattr(knowledge, "search_medlineplus", unavailable)
    response = client.post("/api/knowledge/search", headers=headers, json={"query": "blood pressure"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Source unavailable"


def test_medlineplus_response_is_sanitized_and_links_are_restricted():
    from app.services.medlineplus_service import _parse_topics

    xml = b"""<?xml version="1.0"?>
    <nlmSearchResult><list>
      <document url="https://medlineplus.gov/healthyaging.html" title="Healthy &amp; Aging"
        snippet="Learn about &lt;b&gt;healthy aging&lt;/b&gt;.">
        <content name="title">Healthy &amp; Aging</content>
        <content name="snippet">Learn about &lt;b&gt;healthy aging&lt;/b&gt;.</content>
      </document>
      <document url="https://example.org/fake.html" title="Untrusted result"
        snippet="Should not be included." />
      <document url="http://medlineplus.gov/insecure.html" title="Insecure result"
        snippet="Should not be included." />
    </list></nlmSearchResult>"""

    topics = _parse_topics(xml)
    assert len(topics) == 1
    assert topics[0].title == "Healthy & Aging"
    assert topics[0].summary == "Learn about healthy aging."
    assert topics[0].url == "https://medlineplus.gov/healthyaging.html"
    assert topics[0].source == "MedlinePlus.gov"


def test_medlineplus_search_caches_provider_response(monkeypatch):
    from io import BytesIO

    from app.services import medlineplus_service

    with medlineplus_service._service_lock:
        medlineplus_service._cache.clear()
        medlineplus_service._request_times.clear()
    calls = []
    xml = b"""<nlmSearchResult><list><document
      url="https://medlineplus.gov/sleepdisorders.html" title="Sleep Disorders"
      snippet="Learn about sleep."><content name="title">Sleep Disorders</content>
      <content name="snippet">Learn about sleep.</content></document></list></nlmSearchResult>"""

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return BytesIO(xml)

    monkeypatch.setattr(medlineplus_service, "urlopen", fake_urlopen)
    first = medlineplus_service.search_medlineplus("  sleep   disorders ")
    second = medlineplus_service.search_medlineplus("sleep disorders")
    assert first == second
    assert len(calls) == 1
    assert "term=sleep+disorders" in calls[0][0]
    assert calls[0][1] == 8
    assert first[0].title == "Sleep Disorders"

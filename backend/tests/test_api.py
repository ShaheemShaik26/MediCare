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
        b"Diagnosis: Type 2 diabetes. Medication: Metformin 500 mg twice daily. Allergy: Penicillin."
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

    fact_id = items[0]["id"]
    review = client.post(
        f"/api/facts/{fact_id}/review",
        headers=headers,
        json={"status": "accepted"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "accepted"

    timeline = client.get("/api/timeline", headers=headers)
    assert timeline.status_code == 200, timeline.text
    assert len(timeline.json()) >= 1

    download = client.get(f"/api/documents/{document_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == payload
    assert download.headers["cache-control"] == "private, no-store"


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

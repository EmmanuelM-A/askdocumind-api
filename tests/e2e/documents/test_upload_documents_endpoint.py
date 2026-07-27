"""
End-to-end tests for POST /api/documents (upload documents to a chat
session). No dependency is mocked anywhere in this file - uploads run
through the real docling parser and the real OpenAI embeddings API.

Settings this file exercises the boundaries of (see src/config/configs.py):
- MAX_FILE_SIZE_MB = 0.5 (per-file size cap)
- MAX_FILES_PER_CHAT_MB = 1 (total size cap per chat)
- MAX_DOCUMENTS_PER_CHAT = 10
- UploadDocumentsRequest.documents has min_length=1, max_length=5 per request
- MAX_UPLOAD_REQUESTS_PER_MINUTE = 5 (shared by list/upload/delete) - tests
  use a fresh user per test and keep same-user call counts low to stay
  clear of this limit.
"""

import io
import json
from uuid import uuid4

import fitz
from docx import Document as DocxDocument

from src.config.configs import settings

ENDPOINT = "/api/documents"
COOKIE_NAME = settings.auth.COOKIE_NAME


def _txt(name: str, text: str = "Hello world, this is a test document.") -> tuple:
    return ("documents", (name, text.encode("utf-8"), "text/plain"))


def _pdf(name: str, text: str = "Hello world, this is a test document.") -> tuple:
    """Builds a real, valid single-page PDF (via PyMuPDF) - not just a
    file with a .pdf extension, so docling's real PDF backend runs."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return ("documents", (name, pdf_bytes, "application/pdf"))


def _docx(name: str, text: str = "Hello world, this is a test document.") -> tuple:
    """Builds a real, valid DOCX (via python-docx)."""
    buf = io.BytesIO()
    docx_doc = DocxDocument()
    docx_doc.add_paragraph(text)
    docx_doc.save(buf)
    return (
        "documents",
        (
            name,
            buf.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    )


def _md(
    name: str, text: str = "# Heading\n\nHello world, this is a test document."
) -> tuple:
    return ("documents", (name, text.encode("utf-8"), "text/markdown"))


def _json(name: str, data: dict | None = None) -> tuple:
    payload = json.dumps(data or {"title": "Test", "body": "Hello world."}).encode(
        "utf-8"
    )
    return ("documents", (name, payload, "application/json"))


def _html(name: str, text: str = "Hello world, this is a test document.") -> tuple:
    content = f"<html><body><p>{text}</p></body></html>".encode("utf-8")
    return ("documents", (name, content, "text/html"))


def _csv(name: str, rows: list[tuple[str, str]] | None = None) -> tuple:
    rows = rows or [("name", "animal"), ("Rex", "dog"), ("Whiskers", "cat")]
    content = "\n".join(",".join(row) for row in rows).encode("utf-8")
    return ("documents", (name, content, "text/csv"))


# ============================ Happy path ============================


async def test_upload_single_document_returns_201(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_txt("doc1.txt")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Successfully uploaded 1 document(s)."


async def test_upload_multiple_documents_in_one_request(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_txt("a.txt"), _txt("b.txt"), _txt("c.txt")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Successfully uploaded 3 document(s)."


async def test_upload_persists_document_with_correct_metadata(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    app_client.post(
        ENDPOINT,
        files=[_txt("metadata-check.txt", "Some content for metadata checking.")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    from src.database.repository.interfaces import DocumentSearchCriteria

    stored = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )

    assert len(stored) == 1
    assert stored[0].source == "metadata-check.txt"
    assert stored[0].source_size == len("Some content for metadata checking.".encode())


async def test_upload_creates_real_document_chunks(
    app_client,
    seed_user,
    seed_chat_session,
    auth_cookie,
    document_repo,
    document_chunk_repo,
):
    """End-to-end pipeline check: real docling parse -> real chunking ->
    real embedding -> chunks actually persisted."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    app_client.post(
        ENDPOINT,
        files=[
            _txt("chunked.txt", "Cats are wonderful pets. Dogs are loyal companions.")
        ],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    from src.database.repository.interfaces import DocumentSearchCriteria

    [document] = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )
    chunks = await document_chunk_repo.list_by_document_id(document.id)

    assert len(chunks) >= 1
    assert chunks[0].embedding is not None


# ==================== Multi-format support ====================
#
# The docstring on the route advertises "Allowed formats: .pdf, .docx, .txt,
# .md" but nothing in the code actually enforces an extension allowlist -
# whatever docling can parse goes through. These tests use *real*, valid
# files for each format (not just a renamed .txt) so the real docling
# backend for each format actually runs, including PDF's real layout/OCR
# pipeline (downloads its models on first run, then cached - this test is
# noticeably slower the first time).


async def test_upload_pdf_document_succeeds_and_creates_chunks(
    app_client,
    seed_user,
    seed_chat_session,
    auth_cookie,
    document_repo,
    document_chunk_repo,
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_pdf("real.pdf", "Cats are wonderful pets. Dogs are loyal companions.")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Successfully uploaded 1 document(s)."

    from src.database.repository.interfaces import DocumentSearchCriteria

    [document] = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )
    chunks = await document_chunk_repo.list_by_document_id(document.id)
    assert len(chunks) >= 1


async def test_upload_docx_document_succeeds_and_creates_chunks(
    app_client,
    seed_user,
    seed_chat_session,
    auth_cookie,
    document_repo,
    document_chunk_repo,
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[
            _docx("real.docx", "Cats are wonderful pets. Dogs are loyal companions.")
        ],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Successfully uploaded 1 document(s)."

    from src.database.repository.interfaces import DocumentSearchCriteria

    [document] = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )
    chunks = await document_chunk_repo.list_by_document_id(document.id)
    assert len(chunks) >= 1


async def test_upload_md_document_succeeds_and_creates_chunks(
    app_client,
    seed_user,
    seed_chat_session,
    auth_cookie,
    document_repo,
    document_chunk_repo,
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_md("real.md")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 201

    from src.database.repository.interfaces import DocumentSearchCriteria

    [document] = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )
    chunks = await document_chunk_repo.list_by_document_id(document.id)
    assert len(chunks) >= 1


async def test_upload_html_document_succeeds_and_creates_chunks(
    app_client,
    seed_user,
    seed_chat_session,
    auth_cookie,
    document_repo,
    document_chunk_repo,
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[
            _html("real.html", "Cats are wonderful pets. Dogs are loyal companions.")
        ],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Successfully uploaded 1 document(s)."

    from src.database.repository.interfaces import DocumentSearchCriteria

    [document] = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )
    chunks = await document_chunk_repo.list_by_document_id(document.id)
    assert len(chunks) >= 1


async def test_upload_csv_document_succeeds_and_creates_chunks(
    app_client,
    seed_user,
    seed_chat_session,
    auth_cookie,
    document_repo,
    document_chunk_repo,
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_csv("real.csv")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Successfully uploaded 1 document(s)."

    from src.database.repository.interfaces import DocumentSearchCriteria

    [document] = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )
    chunks = await document_chunk_repo.list_by_document_id(document.id)
    assert len(chunks) >= 1


async def test_upload_json_document_rejected_by_extension_allowlist(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """docling *registers* a .json backend (InputFormat.JSON_DOCLING), but
    it's specifically for docling's own DoclingDocument export schema, not
    arbitrary/generic JSON - so .json is deliberately excluded from
    ALLOWED_DOCUMENT_EXTENSIONS and rejected up front, rather than being
    accepted and then failing unpredictably inside the real docling
    backend."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_json("data.json", {"title": "Test", "body": "Cats and dogs."})],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


async def test_upload_generic_unsupported_extension_rejected(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """Even a format docling itself can genuinely parse (e.g. .xlsx) is
    rejected if it's outside this app's settings.files.ALLOED_FILE_EXTENSIONS
    allowlist - distinct from the dedicated JSON test above, this proves the
    allowlist is doing real work beyond just blocking JSON specifically."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[
            (
                "documents",
                (
                    "spreadsheet.xlsx",
                    b"not a real xlsx, but extension is rejected before content is read",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            )
        ],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


async def test_upload_mixed_formats_in_one_request(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[
            _txt("plain.txt"),
            _md("notes.md"),
            _docx("word.docx"),
        ],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Successfully uploaded 3 document(s)."


# ==================== Validation ====================


async def test_upload_no_files_returns_422(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT, data={"chat_id": str(chat_id)}, headers=auth_cookie(user_id)
    )

    assert response.status_code == 422


async def test_upload_more_than_five_files_returns_422(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_txt(f"doc{i}.txt") for i in range(6)],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422


async def test_upload_double_extension_filename_returns_422(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_txt("sneaky.txt.exe")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FILE_EXTENSION"


async def test_upload_file_exceeding_size_limit_returns_422(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    oversized_content = b"x" * (
        int(settings.files.MAX_FILE_SIZE_MB * 1024 * 1024) + 1024
    )

    response = app_client.post(
        ENDPOINT,
        files=[("documents", ("too-big.txt", oversized_content, "text/plain"))],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FILE_SIZE_LIMIT_EXCEEDED"


async def test_upload_missing_chat_id_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, files=[_txt("doc.txt")], headers=auth_cookie(user_id)
    )

    assert response.status_code == 422


async def test_upload_invalid_chat_id_format_returns_422(
    app_client, seed_user, auth_cookie
):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT,
        files=[_txt("doc.txt")],
        data={"chat_id": "not-a-uuid"},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422


async def test_upload_unparseable_file_content_returns_500(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """A .pdf-named file with garbage bytes is not caught by any
    pre-validation - it fails inside the real docling converter and
    propagates as an unhandled 500."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[
            (
                "documents",
                ("bad.pdf", b"not a real pdf file content", "application/pdf"),
            )
        ],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 500
    assert response.json()["success"] is False


# ==================== Duplicates & limits ====================


async def test_upload_duplicate_filenames_in_same_request_returns_409(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_txt("dup.txt"), _txt("dup.txt")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_DOCUMENTS_IN_REQUEST"


async def test_upload_filename_already_exists_in_chat_returns_409(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    headers = auth_cookie(user_id)

    first = app_client.post(
        ENDPOINT,
        files=[_txt("repeat.txt")],
        data={"chat_id": str(chat_id)},
        headers=headers,
    )
    assert first.status_code == 201

    second = app_client.post(
        ENDPOINT,
        files=[_txt("repeat.txt")],
        data={"chat_id": str(chat_id)},
        headers=headers,
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DOCUMENT_ALREADY_EXISTS"


async def test_upload_exceeding_max_documents_per_chat_returns_409(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    headers = auth_cookie(user_id)
    limit = settings.files.MAX_DOCUMENTS_PER_CHAT

    # Upload in batches of 5 (the per-request max) until the limit is reached.
    uploaded = 0
    batch_num = 0
    while uploaded < limit:
        batch_size = min(5, limit - uploaded)
        files = [_txt(f"batch{batch_num}-{i}.txt") for i in range(batch_size)]
        resp = app_client.post(
            ENDPOINT, files=files, data={"chat_id": str(chat_id)}, headers=headers
        )
        assert resp.status_code == 201
        uploaded += batch_size
        batch_num += 1

    response = app_client.post(
        ENDPOINT,
        files=[_txt("one-too-many.txt")],
        data={"chat_id": str(chat_id)},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MAX_DOCUMENTS_PER_CHAT_EXCEEDED"


# ==================== Not found / ownership ====================


async def test_upload_to_nonexistent_chat_returns_404(
    app_client, seed_user, auth_cookie
):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT,
        files=[_txt("doc.txt")],
        data={"chat_id": str(uuid4())},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_upload_to_chat_owned_by_another_user_returns_404(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    owner_id = await seed_user()
    other_user_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)

    response = app_client.post(
        ENDPOINT,
        files=[_txt("doc.txt")],
        data={"chat_id": str(chat_id)},
        headers=auth_cookie(other_user_id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


# ==================== Auth failure matrix ====================


async def test_upload_no_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT, files=[_txt("doc.txt")], data={"chat_id": str(chat_id)}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_COOKIE_VALUE"


async def test_upload_garbage_cookie_returns_422(
    app_client, seed_user, seed_chat_session
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        files=[_txt("doc.txt")],
        data={"chat_id": str(chat_id)},
        headers={"Cookie": f"{COOKIE_NAME}=garbage"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_upload_valid_signature_nonexistent_user_returns_404(
    app_client, token_manager, seed_user, seed_chat_session
):
    owner_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)
    cookie_token = token_manager.create_token(uuid4())

    response = app_client.post(
        ENDPOINT,
        files=[_txt("doc.txt")],
        data={"chat_id": str(chat_id)},
        headers={"Cookie": f"{COOKIE_NAME}={cookie_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== HTTP-layer edges ====================


async def test_upload_put_method_not_allowed(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.put(ENDPOINT, headers=auth_cookie(user_id))

    assert response.status_code == 405

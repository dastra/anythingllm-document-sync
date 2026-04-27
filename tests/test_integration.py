"""
Integration tests against a running local AnythingLLM instance (http://localhost:3001).

Tests are organised into sections:
  1. fetch_local_documents — purely local logic, no API required
  2. Database — purely local logic, no API required
  3. API-level — individual AnythingLLM API methods
  4. Sync logic (single document)
  5. Sync logic (multiple documents)
  6. Sync logic (edge cases)
  7. Full end-to-end cycle via main()

Run with: pytest tests/test_integration.py -v
"""

import os
import time
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from anythingllm_loader.config import AnythingLLMConfig
from anythingllm_loader.anythingllm_api import AnythingLLM
from anythingllm_loader.database import DocumentDatabase, AnythingLLMDocument
from ingest_anythingllm_docs import (
    fetch_local_documents,
    upload_new_documents,
    embed_new_documents,
    remove_embedded_documents,
    remove_loaded_documents,
    main,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def config():
    return AnythingLLMConfig.load_config()


@pytest.fixture(scope="module")
def api(config):
    client = AnythingLLM(config)
    assert client.authenticate(), (
        "Could not authenticate with AnythingLLM. "
        "Check that AnythingLLM is running and ~/.anythingllm-sync/config.yaml is correct."
    )
    return client


@pytest.fixture
def test_file(tmp_path):
    f = tmp_path / "anythingllm_integration_test.txt"
    f.write_text("This is an integration test document for AnythingLLM.")
    return f


@pytest.fixture
def test_files(tmp_path):
    """Three temporary text files for multi-document tests."""
    files = []
    for i in range(3):
        f = tmp_path / f"test_doc_{i}.txt"
        f.write_text(f"Test document {i} for AnythingLLM integration testing.")
        files.append(f)
    return files


@pytest.fixture
def db(tmp_path):
    """A fresh temporary database, isolated from the real one."""
    db_path = tmp_path / "test.db"
    with patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        database = DocumentDatabase()
        database.initialize_database()
        yield database


@pytest.fixture
def uploaded(api, test_file):
    """Upload a document and clean it up after the test regardless of outcome."""
    result = api.upload_document(str(test_file))
    assert result is not None, f"Failed to upload {test_file}"
    yield result
    api.unembed_document(result["location"])
    time.sleep(0.5)
    api.unload_document(result["location"])


# ---------------------------------------------------------------------------
# 1. fetch_local_documents (no API required)
# ---------------------------------------------------------------------------

def _config_for(tmp_path, directory_excludes=None, file_excludes=None):
    return AnythingLLMConfig(
        api_key="dummy",
        file_paths=[str(tmp_path)],
        directory_excludes=directory_excludes or [],
        file_excludes=file_excludes or [],
        workspace_slug="test",
    )


def test_fetch_local_documents_finds_supported_files(tmp_path):
    (tmp_path / "doc.txt").write_text("content")
    (tmp_path / "doc.md").write_text("content")
    (tmp_path / "doc.pdf").write_text("content")

    docs = fetch_local_documents(_config_for(tmp_path))

    assert str(tmp_path / "doc.txt") in docs
    assert str(tmp_path / "doc.md") in docs
    assert str(tmp_path / "doc.pdf") in docs


def test_fetch_local_documents_excludes_unsupported_types(tmp_path):
    (tmp_path / "doc.txt").write_text("content")
    (tmp_path / "doc.xyz").write_text("content")
    (tmp_path / "doc.csv").write_text("content")

    docs = fetch_local_documents(_config_for(tmp_path))

    assert str(tmp_path / "doc.txt") in docs
    assert str(tmp_path / "doc.xyz") not in docs
    assert str(tmp_path / "doc.csv") not in docs


def test_fetch_local_documents_scans_subdirectories(tmp_path):
    subdir = tmp_path / "sub" / "nested"
    subdir.mkdir(parents=True)
    (subdir / "deep.txt").write_text("content")

    docs = fetch_local_documents(_config_for(tmp_path))

    assert str(subdir / "deep.txt") in docs


def test_fetch_local_documents_excludes_directories(tmp_path):
    (tmp_path / "included").mkdir()
    (tmp_path / "excluded_dir").mkdir()
    (tmp_path / "included" / "doc.txt").write_text("content")
    (tmp_path / "excluded_dir" / "doc.txt").write_text("content")

    docs = fetch_local_documents(_config_for(tmp_path, directory_excludes=["excluded_dir"]))

    assert str(tmp_path / "included" / "doc.txt") in docs
    assert str(tmp_path / "excluded_dir" / "doc.txt") not in docs


def test_fetch_local_documents_excludes_files(tmp_path):
    (tmp_path / "keep.txt").write_text("content")
    (tmp_path / "ignore.txt").write_text("content")

    docs = fetch_local_documents(_config_for(tmp_path, file_excludes=["ignore"]))

    assert str(tmp_path / "keep.txt") in docs
    assert str(tmp_path / "ignore.txt") not in docs


def test_fetch_local_documents_multiple_paths(tmp_path):
    path1 = tmp_path / "dir1"
    path2 = tmp_path / "dir2"
    path1.mkdir()
    path2.mkdir()
    (path1 / "doc1.txt").write_text("content")
    (path2 / "doc2.txt").write_text("content")

    config = AnythingLLMConfig(
        api_key="dummy",
        file_paths=[str(path1), str(path2)],
        directory_excludes=[],
        file_excludes=[],
        workspace_slug="test",
    )

    docs = fetch_local_documents(config)

    assert str(path1 / "doc1.txt") in docs
    assert str(path2 / "doc2.txt") in docs


def test_fetch_local_documents_ignores_directories_as_files(tmp_path):
    """rglob returns both files and directories — only files should be included."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "doc.txt").write_text("content")

    docs = fetch_local_documents(_config_for(tmp_path))

    assert str(tmp_path / "subdir") not in docs
    assert str(tmp_path / "doc.txt") in docs


# ---------------------------------------------------------------------------
# 2. Database (no API required)
# ---------------------------------------------------------------------------

def _make_doc(local_path, location="custom-documents/file.json"):
    return AnythingLLMDocument(
        local_path,
        datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        location,
        "{}",
    )


def test_database_starts_empty(db):
    assert db.get_documents() == []


def test_database_add_and_retrieve_document(db):
    db.add_document(_make_doc("/path/to/file.txt", "custom-documents/file.txt-uuid.json"))

    docs = db.get_documents()
    assert len(docs) == 1
    assert docs[0].local_file_path == "/path/to/file.txt"
    assert docs[0].anythingllm_document_location == "custom-documents/file.txt-uuid.json"


def test_database_remove_document_by_local_path(db):
    db.add_document(_make_doc("/path/to/file.txt"))
    assert len(db.get_documents()) == 1

    db.remove_document("/path/to/file.txt")
    assert db.get_documents() == []


def test_database_remove_document_ignores_wrong_key(db):
    """remove_document deletes by local_file_path — passing anythingllm_document_location must not delete the record."""
    db.add_document(_make_doc("/path/to/file.txt", "custom-documents/file.txt-uuid.json"))

    db.remove_document("custom-documents/file.txt-uuid.json")
    assert len(db.get_documents()) == 1  # still present

    db.remove_document("/path/to/file.txt")
    assert db.get_documents() == []


def test_database_multiple_documents(db):
    for i in range(3):
        db.add_document(_make_doc(f"/path/to/file{i}.txt", f"custom-documents/file{i}.json"))

    docs = db.get_documents()
    assert len(docs) == 3
    assert {d.local_file_path for d in docs} == {
        "/path/to/file0.txt", "/path/to/file1.txt", "/path/to/file2.txt"
    }


def test_database_timestamp_roundtrip(db):
    original = datetime(2026, 3, 15, 10, 30, 45, tzinfo=timezone.utc)
    db.add_document(AnythingLLMDocument("/path/file.txt", original, "custom-documents/x.json", "{}"))

    retrieved = db.get_documents()[0].upload_timestamp
    assert retrieved.year == 2026
    assert retrieved.month == 3
    assert retrieved.day == 15
    assert retrieved.hour == 10
    assert retrieved.minute == 30
    assert retrieved.second == 45


# ---------------------------------------------------------------------------
# 3. API-level tests
# ---------------------------------------------------------------------------

def test_authenticate(api):
    assert api.authenticate()


def test_upload_document(api, test_file):
    result = api.upload_document(str(test_file))
    assert result is not None
    assert "location" in result
    assert result["location"].startswith("custom-documents/")
    api.unload_document(result["location"])


def test_upload_empty_file_returns_none(api, tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    assert api.upload_document(str(empty)) is None


def test_upload_unsupported_type_returns_none(api, tmp_path):
    unsupported = tmp_path / "file.xyz"
    unsupported.write_text("content")
    assert api.upload_document(str(unsupported)) is None


def test_uploaded_document_appears_in_loaded_list(api, uploaded):
    loaded = api.fetch_loaded_documents_from_anythingllm()
    loaded_locations = {f"custom-documents/{name}" for name in loaded}
    assert uploaded["location"] in loaded_locations


def test_unloaded_document_disappears_from_loaded_list(api, test_file):
    result = api.upload_document(str(test_file))
    assert result is not None

    assert api.unload_document(result["location"])

    loaded = api.fetch_loaded_documents_from_anythingllm()
    loaded_locations = {f"custom-documents/{name}" for name in loaded}
    assert result["location"] not in loaded_locations


def test_embed_document(api, uploaded):
    api.embed_new_document(uploaded["location"])
    time.sleep(1)
    assert uploaded["location"] in api.fetch_embedded_workspace_documents()
    api.unembed_document(uploaded["location"])
    time.sleep(0.5)


def test_unembed_document(api, uploaded):
    api.embed_new_document(uploaded["location"])
    time.sleep(1)
    assert uploaded["location"] in api.fetch_embedded_workspace_documents()

    api.unembed_document(uploaded["location"])
    time.sleep(1)
    assert uploaded["location"] not in api.fetch_embedded_workspace_documents()


def test_unload_document(api, test_file):
    result = api.upload_document(str(test_file))
    assert result is not None
    assert api.unload_document(result["location"])

    loaded = api.fetch_loaded_documents_from_anythingllm()
    loaded_locations = {f"custom-documents/{name}" for name in loaded}
    assert result["location"] not in loaded_locations


# ---------------------------------------------------------------------------
# 4. Sync logic — single document
# ---------------------------------------------------------------------------

def test_sync_uploads_new_document(api, db, test_file):
    upload_new_documents(api, db, [str(test_file)], db.get_documents())

    saved = db.get_documents()
    assert len(saved) == 1
    assert saved[0].local_file_path == str(test_file)
    assert saved[0].anythingllm_document_location.startswith("custom-documents/")

    api.unload_document(saved[0].anythingllm_document_location)


def test_sync_skips_unchanged_document(api, db, test_file):
    upload_new_documents(api, db, [str(test_file)], db.get_documents())
    original_location = db.get_documents()[0].anythingllm_document_location

    upload_new_documents(api, db, [str(test_file)], db.get_documents())

    saved = db.get_documents()
    assert len(saved) == 1
    assert saved[0].anythingllm_document_location == original_location

    api.unload_document(original_location)


def test_sync_reuploads_modified_document(api, db, test_file):
    upload_new_documents(api, db, [str(test_file)], db.get_documents())
    original_location = db.get_documents()[0].anythingllm_document_location

    test_file.write_text("Modified content.")
    future_mtime = time.time() + 10
    os.utime(test_file, (future_mtime, future_mtime))

    upload_new_documents(api, db, [str(test_file)], db.get_documents())

    saved = db.get_documents()
    assert len(saved) == 1
    assert saved[0].anythingllm_document_location != original_location

    loaded = api.fetch_loaded_documents_from_anythingllm()
    loaded_locations = {f"custom-documents/{name}" for name in loaded}
    assert original_location not in loaded_locations

    api.unload_document(saved[0].anythingllm_document_location)


def test_sync_embeds_loaded_documents(api, db, test_file):
    upload_new_documents(api, db, [str(test_file)], db.get_documents())
    loaded = db.get_documents()
    location = loaded[0].anythingllm_document_location

    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(1)

    assert location in api.fetch_embedded_workspace_documents()

    api.unembed_document(location)
    time.sleep(0.5)
    api.unload_document(location)


def test_sync_does_not_embed_already_embedded_document(api, db, test_file):
    upload_new_documents(api, db, [str(test_file)], db.get_documents())
    loaded = db.get_documents()
    location = loaded[0].anythingllm_document_location

    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(1)
    assert api.fetch_embedded_workspace_documents().count(location) == 1

    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(1)
    assert api.fetch_embedded_workspace_documents().count(location) == 1

    api.unembed_document(location)
    time.sleep(0.5)
    api.unload_document(location)


def test_sync_removes_document_deleted_locally(api, db, test_file):
    upload_new_documents(api, db, [str(test_file)], db.get_documents())
    loaded = db.get_documents()
    location = loaded[0].anythingllm_document_location

    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(1)
    assert location in api.fetch_embedded_workspace_documents()

    # Simulate local deletion by passing empty local_docs
    remove_embedded_documents(api, [], db.get_documents(), api.fetch_embedded_workspace_documents())
    time.sleep(1)
    assert location not in api.fetch_embedded_workspace_documents()

    remove_loaded_documents(api, db, [], db.get_documents())
    assert db.get_documents() == []

    loaded_in_llm = api.fetch_loaded_documents_from_anythingllm()
    assert location not in {f"custom-documents/{n}" for n in loaded_in_llm}


# ---------------------------------------------------------------------------
# 5. Sync logic — multiple documents
# ---------------------------------------------------------------------------

def test_sync_uploads_multiple_documents(api, db, test_files):
    local_docs = [str(f) for f in test_files]

    upload_new_documents(api, db, local_docs, db.get_documents())

    saved = db.get_documents()
    assert len(saved) == 3
    assert {d.local_file_path for d in saved} == set(local_docs)

    for doc in saved:
        api.unload_document(doc.anythingllm_document_location)


def test_sync_embeds_multiple_documents(api, db, test_files):
    local_docs = [str(f) for f in test_files]
    upload_new_documents(api, db, local_docs, db.get_documents())
    loaded = db.get_documents()

    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(2)

    embedded = api.fetch_embedded_workspace_documents()
    for doc in loaded:
        assert doc.anythingllm_document_location in embedded

    for doc in loaded:
        api.unembed_document(doc.anythingllm_document_location)
        time.sleep(0.5)
    for doc in loaded:
        api.unload_document(doc.anythingllm_document_location)


def test_sync_skips_unchanged_among_multiple(api, db, test_files):
    """After initial upload, a second sync should not re-upload any of the unchanged files."""
    local_docs = [str(f) for f in test_files]
    upload_new_documents(api, db, local_docs, db.get_documents())
    original_locations = {d.local_file_path: d.anythingllm_document_location for d in db.get_documents()}

    upload_new_documents(api, db, local_docs, db.get_documents())

    saved = db.get_documents()
    assert len(saved) == 3
    for doc in saved:
        assert doc.anythingllm_document_location == original_locations[doc.local_file_path]

    for doc in saved:
        api.unload_document(doc.anythingllm_document_location)


def test_sync_removes_only_deleted_among_multiple(api, db, test_files):
    """When only one of several local files is deleted, only that document should be removed."""
    local_docs = [str(f) for f in test_files]
    upload_new_documents(api, db, local_docs, db.get_documents())
    loaded = db.get_documents()

    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(2)

    deleted_path = local_docs[0]
    deleted_location = next(d.anythingllm_document_location for d in loaded if d.local_file_path == deleted_path)
    remaining_docs = local_docs[1:]

    remove_embedded_documents(api, remaining_docs, db.get_documents(), api.fetch_embedded_workspace_documents())
    time.sleep(1)
    remove_loaded_documents(api, db, remaining_docs, db.get_documents())

    # Deleted doc should be gone
    assert deleted_location not in api.fetch_embedded_workspace_documents()
    assert len(db.get_documents()) == 2

    # Remaining docs should still be present
    embedded = api.fetch_embedded_workspace_documents()
    for doc in db.get_documents():
        assert doc.anythingllm_document_location in embedded

    # Cleanup
    for doc in db.get_documents():
        api.unembed_document(doc.anythingllm_document_location)
        time.sleep(0.5)
    for doc in db.get_documents():
        api.unload_document(doc.anythingllm_document_location)


# ---------------------------------------------------------------------------
# 6. Sync logic — edge cases
# ---------------------------------------------------------------------------

def test_remove_embedded_document_not_in_db(api, db, test_file):
    """
    A document embedded in the workspace but absent from the local DB should be
    unembedded. This exercises the `embedded_document_local_path is None` branch
    (fixed by adding `continue` so the document isn't also added for being 'not found locally').
    """
    result = api.upload_document(str(test_file))
    assert result is not None
    location = result["location"]

    api.embed_new_document(location)
    time.sleep(1)
    assert location in api.fetch_embedded_workspace_documents()

    # DB has no record of this document
    assert db.get_documents() == []

    remove_embedded_documents(api, [str(test_file)], db.get_documents(), api.fetch_embedded_workspace_documents())
    time.sleep(1)

    assert location not in api.fetch_embedded_workspace_documents()
    api.unload_document(location)


def test_remove_embedded_document_not_in_db_not_added_twice(api, db, test_file):
    """
    The same document should only appear once in documents_to_unembed even when
    it is both absent from the DB and absent locally — the `continue` prevents
    it being appended a second time via the 'not found locally' path.
    """
    result = api.upload_document(str(test_file))
    assert result is not None
    location = result["location"]

    api.embed_new_document(location)
    time.sleep(1)

    unembed_calls = []
    original_unembed = api.unembed_document
    api.unembed_document = lambda loc: unembed_calls.append(loc) or original_unembed(loc)

    remove_embedded_documents(api, [], db.get_documents(), api.fetch_embedded_workspace_documents())
    time.sleep(1)

    api.unembed_document = original_unembed
    assert unembed_calls.count(location) == 1, "unembed_document should be called exactly once per document"
    api.unload_document(location)


def test_sync_ignores_files_not_in_local_docs(api, db, test_files):
    """upload_new_documents should only process files in local_documents, not all DB entries."""
    local_docs = [str(f) for f in test_files]
    upload_new_documents(api, db, local_docs, db.get_documents())
    assert len(db.get_documents()) == 3

    # Second sync with only the first file — the other two should be untouched
    upload_new_documents(api, db, [local_docs[0]], db.get_documents())
    assert len(db.get_documents()) == 3  # still 3 in DB, no re-uploads

    for doc in db.get_documents():
        api.unload_document(doc.anythingllm_document_location)


# ---------------------------------------------------------------------------
# 7. Full end-to-end cycle via main()
# ---------------------------------------------------------------------------

def test_main_uploads_and_embeds_configured_files(tmp_path):
    """
    Run main() end-to-end with a patched config pointing to a temp directory
    and an isolated database. Verifies all documents are uploaded and embedded.
    """
    doc = tmp_path / "main_test.txt"
    doc.write_text("Full cycle test document for main().")

    test_config = AnythingLLMConfig(
        api_key="TRMW9CQ-VK0MG2T-GR2P7SE-8DN7GEA",
        file_paths=[str(tmp_path)],
        directory_excludes=[],
        file_excludes=[],
        workspace_slug="test",
    )
    db_path = tmp_path / "test.db"

    with patch.object(AnythingLLMConfig, "load_config", return_value=test_config), \
         patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        main()

    client = AnythingLLM(test_config)
    embedded = client.fetch_embedded_workspace_documents()

    with patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        database = DocumentDatabase()
        saved = database.get_documents()

    assert len(saved) == 1
    assert saved[0].anythingllm_document_location in embedded

    # Cleanup
    client.unembed_document(saved[0].anythingllm_document_location)
    time.sleep(0.5)
    client.unload_document(saved[0].anythingllm_document_location)


def test_main_removes_deleted_files_on_second_run(tmp_path):
    """
    Running main() twice — once with a file present, once without — should
    result in the document being unembedded and unloaded on the second run.
    """
    doc = tmp_path / "ephemeral.txt"
    doc.write_text("This document will be deleted before the second run.")

    test_config = AnythingLLMConfig(
        api_key="TRMW9CQ-VK0MG2T-GR2P7SE-8DN7GEA",
        file_paths=[str(tmp_path)],
        directory_excludes=[],
        file_excludes=[],
        workspace_slug="test",
    )
    db_path = tmp_path / "test.db"

    # First run — upload and embed
    with patch.object(AnythingLLMConfig, "load_config", return_value=test_config), \
         patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        main()

    with patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        saved = DocumentDatabase().get_documents()
    assert len(saved) == 1
    location = saved[0].anythingllm_document_location

    client = AnythingLLM(test_config)
    time.sleep(1)
    assert location in client.fetch_embedded_workspace_documents()

    # Delete the file and run again
    doc.unlink()
    with patch.object(AnythingLLMConfig, "load_config", return_value=test_config), \
         patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        main()

    time.sleep(1)
    assert location not in client.fetch_embedded_workspace_documents()
    assert location not in {f"custom-documents/{n}" for n in client.fetch_loaded_documents_from_anythingllm()}

    with patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        assert DocumentDatabase().get_documents() == []

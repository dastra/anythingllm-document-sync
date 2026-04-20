"""
Integration tests against a running local AnythingLLM instance.

Requires ~/.anythingllm-sync/config.yaml to be present and AnythingLLM
to be running at http://localhost:3001.

Run with: pytest tests/test_integration.py -v
"""

import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch

from anythingllm_loader.config import AnythingLLMConfig
from anythingllm_loader.anythingllm_api import AnythingLLM
from anythingllm_loader.database import DocumentDatabase, AnythingLLMDocument
from ingest_anythingllm_docs import (
    upload_new_documents,
    embed_new_documents,
    remove_embedded_documents,
    remove_loaded_documents,
)


# ---------------------------------------------------------------------------
# Fixtures
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
    """A temporary text file to use as a test document."""
    f = tmp_path / "anythingllm_integration_test.txt"
    f.write_text("This is an integration test document for AnythingLLM.")
    return f


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
# API-level tests
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
    # fetch_loaded_documents_from_anythingllm returns filenames without the
    # custom-documents/ prefix; reconstruct for comparison
    loaded_locations = {f"custom-documents/{name}" for name in loaded}
    assert uploaded["location"] in loaded_locations


def test_embed_document(api, uploaded):
    location = uploaded["location"]

    api.embed_new_document(location)
    time.sleep(1)

    embedded = api.fetch_embedded_workspace_documents()
    assert location in embedded

    api.unembed_document(location)
    time.sleep(0.5)


def test_unembed_document(api, uploaded):
    location = uploaded["location"]

    api.embed_new_document(location)
    time.sleep(1)
    assert location in api.fetch_embedded_workspace_documents()

    api.unembed_document(location)
    time.sleep(1)
    assert location not in api.fetch_embedded_workspace_documents()


def test_unload_document(api, test_file):
    result = api.upload_document(str(test_file))
    assert result is not None

    assert api.unload_document(result["location"])

    loaded = api.fetch_loaded_documents_from_anythingllm()
    loaded_locations = {f"custom-documents/{name}" for name in loaded}
    assert result["location"] not in loaded_locations


# ---------------------------------------------------------------------------
# Sync logic tests
# ---------------------------------------------------------------------------

def test_sync_uploads_new_document(api, db, test_file):
    local_docs = [str(test_file)]

    upload_new_documents(api, db, local_docs, db.get_documents())

    saved = db.get_documents()
    assert len(saved) == 1
    assert saved[0].local_file_path == str(test_file)
    assert saved[0].anythingllm_document_location.startswith("custom-documents/")

    api.unload_document(saved[0].anythingllm_document_location)


def test_sync_skips_unchanged_document(api, db, test_file):
    local_docs = [str(test_file)]

    upload_new_documents(api, db, local_docs, db.get_documents())
    first_upload = db.get_documents()
    assert len(first_upload) == 1
    original_location = first_upload[0].anythingllm_document_location

    # Second sync — file unchanged, should not re-upload
    upload_new_documents(api, db, local_docs, db.get_documents())
    second_upload = db.get_documents()
    assert len(second_upload) == 1
    assert second_upload[0].anythingllm_document_location == original_location

    api.unload_document(original_location)


def test_sync_reuploads_modified_document(api, db, test_file):
    local_docs = [str(test_file)]

    # Initial upload
    upload_new_documents(api, db, local_docs, db.get_documents())
    saved = db.get_documents()
    assert len(saved) == 1
    original_location = saved[0].anythingllm_document_location

    # Modify the file and push its mtime into the future
    test_file.write_text("Modified content.")
    future_mtime = time.time() + 10
    os.utime(test_file, (future_mtime, future_mtime))

    # Second sync — should remove old version and re-upload
    upload_new_documents(api, db, local_docs, db.get_documents())
    saved = db.get_documents()
    assert len(saved) == 1
    assert saved[0].anythingllm_document_location != original_location

    # Original should be gone from AnythingLLM
    loaded = api.fetch_loaded_documents_from_anythingllm()
    loaded_locations = {f"custom-documents/{name}" for name in loaded}
    assert original_location not in loaded_locations

    api.unload_document(saved[0].anythingllm_document_location)


def test_sync_embeds_loaded_documents(api, db, test_file):
    local_docs = [str(test_file)]

    upload_new_documents(api, db, local_docs, db.get_documents())
    loaded = db.get_documents()
    location = loaded[0].anythingllm_document_location

    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(1)

    assert location in api.fetch_embedded_workspace_documents()

    api.unembed_document(location)
    time.sleep(0.5)
    api.unload_document(location)


def test_sync_removes_document_deleted_locally(api, db, test_file):
    local_docs = [str(test_file)]

    # Upload and embed
    upload_new_documents(api, db, local_docs, db.get_documents())
    loaded = db.get_documents()
    location = loaded[0].anythingllm_document_location

    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(1)
    assert location in api.fetch_embedded_workspace_documents()

    # Simulate local deletion by passing empty local_docs
    embedded = api.fetch_embedded_workspace_documents()
    remove_embedded_documents(api, [], db.get_documents(), embedded)
    time.sleep(1)
    assert location not in api.fetch_embedded_workspace_documents()

    remove_loaded_documents(api, db, [], db.get_documents())
    assert db.get_documents() == []

    loaded_in_llm = api.fetch_loaded_documents_from_anythingllm()
    loaded_locations = {f"custom-documents/{name}" for name in loaded_in_llm}
    assert location not in loaded_locations


def test_sync_does_not_embed_already_embedded_document(api, db, test_file):
    local_docs = [str(test_file)]

    upload_new_documents(api, db, local_docs, db.get_documents())
    loaded = db.get_documents()
    location = loaded[0].anythingllm_document_location

    # Embed once
    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(1)

    embedded_before = api.fetch_embedded_workspace_documents()
    assert embedded_before.count(location) == 1

    # Embed again — should be a no-op
    embed_new_documents(api, loaded, api.fetch_embedded_workspace_documents())
    time.sleep(1)

    embedded_after = api.fetch_embedded_workspace_documents()
    assert embedded_after.count(location) == 1

    api.unembed_document(location)
    time.sleep(0.5)
    api.unload_document(location)

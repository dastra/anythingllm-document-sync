"""
Unit tests that run without a live AnythingLLM instance.
All API calls are mocked using unittest.mock.

Run with: pytest tests/test_unit.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, call

import requests as requests_lib

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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    return AnythingLLMConfig(
        api_key="test-api-key",
        file_paths=["/test/path"],
        directory_excludes=[],
        file_excludes=[],
        workspace_slug="test-workspace",
    )


@pytest.fixture
def api(config):
    return AnythingLLM(config)


@pytest.fixture
def mock_api():
    return MagicMock(spec=AnythingLLM)


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    with patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        database = DocumentDatabase()
        database.initialize_database()
        yield database


@pytest.fixture
def test_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Test content")
    return f


def _doc(local_path, location, ts=None):
    """Helper to create an AnythingLLMDocument with a controllable timestamp."""
    return AnythingLLMDocument(
        local_path,
        ts or datetime(2020, 1, 1, 0, 0, 0),
        location,
        "{}",
    )


def _ok_response(body=None):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = body or {}
    return r


def _error_response(status=500, text="Server error"):
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


# ---------------------------------------------------------------------------
# AnythingLLM.authenticate
# ---------------------------------------------------------------------------

def test_authenticate_returns_true_on_success(api):
    with patch("requests.get", return_value=_ok_response({"authenticated": True})):
        assert api.authenticate() is True


def test_authenticate_returns_false_on_non_200(api):
    with patch("requests.get", return_value=_error_response(403)):
        assert api.authenticate() is False


def test_authenticate_returns_false_when_not_authenticated(api):
    with patch("requests.get", return_value=_ok_response({"authenticated": False})):
        assert api.authenticate() is False


def test_authenticate_sends_api_key_header(api):
    with patch("requests.get", return_value=_ok_response({"authenticated": True})) as mock_get:
        api.authenticate()
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-api-key"


# ---------------------------------------------------------------------------
# AnythingLLM.supported_file_types
# ---------------------------------------------------------------------------

def test_supported_file_types_includes_common_text_formats():
    types = AnythingLLM.supported_file_types()
    for expected in ["txt", "md", "pdf", "docx", "html"]:
        assert expected in types


def test_supported_file_types_excludes_removed_formats():
    types = AnythingLLM.supported_file_types()
    for excluded in ["xlsx", "pptx", "wav", "mp3", "mp4", "csv"]:
        assert excluded not in types


# ---------------------------------------------------------------------------
# AnythingLLM.upload_document
# ---------------------------------------------------------------------------

def test_upload_document_returns_first_document_on_success(api, test_file):
    body = {
        "success": True,
        "error": None,
        "documents": [{"location": "custom-documents/test.txt-uuid.json", "title": "test.txt"}],
    }
    with patch("requests.post", return_value=_ok_response(body)):
        result = api.upload_document(str(test_file))
    assert result["location"] == "custom-documents/test.txt-uuid.json"


def test_upload_document_returns_none_for_empty_file(api, tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    assert api.upload_document(str(empty)) is None


def test_upload_document_returns_none_for_unsupported_type(api, tmp_path):
    f = tmp_path / "file.xyz"
    f.write_text("content")
    assert api.upload_document(str(f)) is None


def test_upload_document_returns_none_on_non_200(api, test_file):
    with patch("requests.post", return_value=_error_response(500)):
        result = api.upload_document(str(test_file))
    assert result is None


def test_upload_document_returns_none_on_api_error_in_body(api, test_file):
    body = {"success": False, "error": "Processing failed", "documents": []}
    with patch("requests.post", return_value=_ok_response(body)):
        result = api.upload_document(str(test_file))
    assert result is None


def test_upload_document_sends_file_as_multipart(api, test_file):
    body = {
        "success": True, "error": None,
        "documents": [{"location": "custom-documents/test.txt-uuid.json"}],
    }
    with patch("requests.post", return_value=_ok_response(body)) as mock_post:
        api.upload_document(str(test_file))
    assert "files" in mock_post.call_args.kwargs


# ---------------------------------------------------------------------------
# AnythingLLM.fetch_loaded_documents_from_anythingllm
# ---------------------------------------------------------------------------

def test_fetch_loaded_documents_returns_filenames(api):
    body = {
        "localFiles": {
            "name": "documents", "type": "folder",
            "items": [
                {"type": "file", "name": "doc1.txt-uuid.json"},
                {"type": "file", "name": "doc2.txt-uuid.json"},
            ],
        }
    }
    with patch("requests.get", return_value=_ok_response(body)):
        result = api.fetch_loaded_documents_from_anythingllm()
    assert "doc1.txt-uuid.json" in result
    assert "doc2.txt-uuid.json" in result


def test_fetch_loaded_documents_traverses_nested_folders(api):
    body = {
        "localFiles": {
            "name": "documents", "type": "folder",
            "items": [
                {
                    "type": "folder", "name": "subfolder",
                    "items": [{"type": "file", "name": "nested.txt-uuid.json"}],
                },
                {"type": "file", "name": "top.txt-uuid.json"},
            ],
        }
    }
    with patch("requests.get", return_value=_ok_response(body)):
        result = api.fetch_loaded_documents_from_anythingllm()
    assert "nested.txt-uuid.json" in result
    assert "top.txt-uuid.json" in result


def test_fetch_loaded_documents_returns_empty_list_when_none(api):
    body = {"localFiles": {"name": "documents", "type": "folder", "items": []}}
    with patch("requests.get", return_value=_ok_response(body)):
        result = api.fetch_loaded_documents_from_anythingllm()
    assert result == []


# ---------------------------------------------------------------------------
# AnythingLLM.fetch_embedded_workspace_documents
# ---------------------------------------------------------------------------

def test_fetch_embedded_workspace_documents_returns_docpaths(api):
    body = {"workspace": [{"documents": [
        {"docpath": "custom-documents/doc1.json"},
        {"docpath": "custom-documents/doc2.json"},
    ]}]}
    with patch("requests.get", return_value=_ok_response(body)):
        result = api.fetch_embedded_workspace_documents()
    assert "custom-documents/doc1.json" in result
    assert "custom-documents/doc2.json" in result


def test_fetch_embedded_workspace_documents_deduplicates(api):
    body = {"workspace": [{"documents": [
        {"docpath": "custom-documents/doc.json"},
        {"docpath": "custom-documents/doc.json"},
    ]}]}
    with patch("requests.get", return_value=_ok_response(body)):
        result = api.fetch_embedded_workspace_documents()
    assert result.count("custom-documents/doc.json") == 1


def test_fetch_embedded_workspace_documents_uses_workspace_slug(api):
    body = {"workspace": [{"documents": []}]}
    with patch("requests.get", return_value=_ok_response(body)) as mock_get:
        api.fetch_embedded_workspace_documents()
    assert "test-workspace" in mock_get.call_args.args[0]


# ---------------------------------------------------------------------------
# AnythingLLM.embed_new_document
# ---------------------------------------------------------------------------

def test_embed_new_document_posts_to_correct_endpoint(api):
    with patch("requests.post", return_value=_ok_response({"workspace": {}})) as mock_post, \
         patch("time.sleep"):
        api.embed_new_document("custom-documents/doc.txt-uuid.json")
    url = mock_post.call_args.args[0]
    assert "/api/v1/workspace/test-workspace/update-embeddings" in url


def test_embed_new_document_sends_adds_key(api):
    with patch("requests.post", return_value=_ok_response({"workspace": {}})) as mock_post, \
         patch("time.sleep"):
        api.embed_new_document("custom-documents/doc.txt-uuid.json")
    assert mock_post.call_args.kwargs["json"]["adds"] == ["custom-documents/doc.txt-uuid.json"]


def test_embed_new_document_sleeps_after_success(api):
    with patch("requests.post", return_value=_ok_response({"workspace": {}})), \
         patch("time.sleep") as mock_sleep:
        api.embed_new_document("custom-documents/doc.txt-uuid.json")
    mock_sleep.assert_called_once_with(0.5)


def test_embed_new_document_handles_exception_without_raising(api):
    with patch("requests.post", side_effect=requests_lib.exceptions.ReadTimeout("timed out")):
        # Should catch and print, not raise
        api.embed_new_document("custom-documents/doc.txt-uuid.json")


def test_embed_new_document_does_not_sleep_on_error(api):
    with patch("requests.post", return_value=_error_response(500)), \
         patch("time.sleep") as mock_sleep:
        api.embed_new_document("custom-documents/doc.txt-uuid.json")
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# AnythingLLM.unload_document
# ---------------------------------------------------------------------------

def test_unload_document_uses_delete_method(api):
    with patch("requests.delete", return_value=_ok_response()) as mock_delete:
        api.unload_document("custom-documents/doc.txt-uuid.json")
    mock_delete.assert_called_once()


def test_unload_document_sends_names_key(api):
    with patch("requests.delete", return_value=_ok_response()) as mock_delete:
        api.unload_document("custom-documents/doc.txt-uuid.json")
    assert "names" in mock_delete.call_args.kwargs["json"]
    assert "deletes" not in mock_delete.call_args.kwargs["json"]


def test_unload_document_returns_true_on_success(api):
    with patch("requests.delete", return_value=_ok_response()):
        assert api.unload_document("custom-documents/doc.txt-uuid.json") is True


def test_unload_document_returns_false_on_non_200(api):
    with patch("requests.delete", return_value=_error_response(500)):
        assert api.unload_document("custom-documents/doc.txt-uuid.json") is False


def test_unload_document_includes_api_prefix_in_url(api):
    with patch("requests.delete", return_value=_ok_response()) as mock_delete:
        api.unload_document("custom-documents/doc.txt-uuid.json")
    url = mock_delete.call_args.args[0]
    assert "/api/v1/system/remove-documents" in url


# ---------------------------------------------------------------------------
# AnythingLLM.unembed_document
# ---------------------------------------------------------------------------

def test_unembed_document_posts_to_workspace_endpoint(api):
    with patch("requests.post", return_value=_ok_response()) as mock_post:
        api.unembed_document("custom-documents/doc.txt-uuid.json")
    url = mock_post.call_args.args[0]
    assert "/api/v1/workspace/test-workspace/update-embeddings" in url


def test_unembed_document_sends_deletes_key(api):
    with patch("requests.post", return_value=_ok_response()) as mock_post:
        api.unembed_document("custom-documents/doc.txt-uuid.json")
    assert mock_post.call_args.kwargs["json"]["deletes"] == ["custom-documents/doc.txt-uuid.json"]


def test_unembed_document_url_has_slash_before_slug(api):
    """Regression: URL was missing '/' before workspace slug."""
    with patch("requests.post", return_value=_ok_response()) as mock_post:
        api.unembed_document("custom-documents/doc.txt-uuid.json")
    url = mock_post.call_args.args[0]
    assert "/workspace/test-workspace/" in url


# ---------------------------------------------------------------------------
# upload_new_documents
# ---------------------------------------------------------------------------

def test_upload_new_documents_uploads_new_file(mock_api, db, test_file):
    mock_api.upload_document.return_value = {"location": "custom-documents/test.json", "title": "test.txt"}
    upload_new_documents(mock_api, db, [str(test_file)], [])
    mock_api.upload_document.assert_called_once_with(str(test_file))
    assert len(db.get_documents()) == 1


def test_upload_new_documents_skips_unchanged_file(mock_api, db, test_file):
    # Timestamp far in the future → file appears older than the DB record
    existing = _doc(str(test_file), "custom-documents/existing.json", datetime(2099, 1, 1))
    db.add_document(existing)
    upload_new_documents(mock_api, db, [str(test_file)], db.get_documents())
    mock_api.upload_document.assert_not_called()
    assert len(db.get_documents()) == 1


def test_upload_new_documents_reuploads_modified_file(mock_api, db, test_file):
    existing = _doc(str(test_file), "custom-documents/old.json", datetime(2000, 1, 1))
    db.add_document(existing)
    mock_api.unload_document.return_value = True
    mock_api.upload_document.return_value = {"location": "custom-documents/new.json", "title": "test.txt"}

    upload_new_documents(mock_api, db, [str(test_file)], db.get_documents())

    mock_api.unload_document.assert_called_once_with("custom-documents/old.json")
    mock_api.upload_document.assert_called_once()
    saved = db.get_documents()
    assert len(saved) == 1
    assert saved[0].anythingllm_document_location == "custom-documents/new.json"


def test_upload_new_documents_reuploads_even_when_unload_fails(mock_api, db, test_file):
    """document_loaded = False when unload fails, so upload is still attempted."""
    existing = _doc(str(test_file), "custom-documents/old.json", datetime(2000, 1, 1))
    db.add_document(existing)
    mock_api.unload_document.return_value = False
    mock_api.upload_document.return_value = {"location": "custom-documents/new.json", "title": "test.txt"}

    upload_new_documents(mock_api, db, [str(test_file)], db.get_documents())

    mock_api.upload_document.assert_called_once()


def test_upload_new_documents_does_not_save_to_db_on_upload_failure(mock_api, db, test_file):
    mock_api.upload_document.return_value = None
    upload_new_documents(mock_api, db, [str(test_file)], [])
    assert db.get_documents() == []


def test_upload_new_documents_handles_empty_local_docs(mock_api, db):
    upload_new_documents(mock_api, db, [], [])
    mock_api.upload_document.assert_not_called()


def test_upload_new_documents_uploads_all_new_files(mock_api, db, tmp_path):
    files = []
    for i in range(3):
        f = tmp_path / f"doc{i}.txt"
        f.write_text(f"content {i}")
        files.append(str(f))
    mock_api.upload_document.side_effect = [
        {"location": f"custom-documents/doc{i}.json", "title": f"doc{i}.txt"} for i in range(3)
    ]
    upload_new_documents(mock_api, db, files, [])
    assert mock_api.upload_document.call_count == 3
    assert len(db.get_documents()) == 3


# ---------------------------------------------------------------------------
# embed_new_documents
# ---------------------------------------------------------------------------

def test_embed_new_documents_embeds_unembedded_document(mock_api):
    doc = _doc("/path/doc.txt", "custom-documents/doc.json")
    embed_new_documents(mock_api, [doc], [])
    mock_api.embed_new_document.assert_called_once_with("custom-documents/doc.json")


def test_embed_new_documents_skips_already_embedded(mock_api):
    doc = _doc("/path/doc.txt", "custom-documents/doc.json")
    embed_new_documents(mock_api, [doc], ["custom-documents/doc.json"])
    mock_api.embed_new_document.assert_not_called()


def test_embed_new_documents_only_embeds_missing_ones(mock_api):
    doc1 = _doc("/path/doc1.txt", "custom-documents/doc1.json")
    doc2 = _doc("/path/doc2.txt", "custom-documents/doc2.json")
    doc3 = _doc("/path/doc3.txt", "custom-documents/doc3.json")
    already_embedded = ["custom-documents/doc1.json", "custom-documents/doc3.json"]

    embed_new_documents(mock_api, [doc1, doc2, doc3], already_embedded)

    mock_api.embed_new_document.assert_called_once_with("custom-documents/doc2.json")


def test_embed_new_documents_handles_empty_inputs(mock_api):
    embed_new_documents(mock_api, [], [])
    mock_api.embed_new_document.assert_not_called()


# ---------------------------------------------------------------------------
# remove_embedded_documents
# ---------------------------------------------------------------------------

def test_remove_embedded_unembeds_doc_not_in_db(mock_api):
    remove_embedded_documents(mock_api, [], [], ["custom-documents/orphan.json"])
    mock_api.unembed_document.assert_called_once_with("custom-documents/orphan.json")


def test_remove_embedded_doc_not_in_db_unembedded_exactly_once(mock_api):
    """Regression: the continue fix prevents double-appending to documents_to_unembed."""
    calls = []
    mock_api.unembed_document.side_effect = lambda loc: calls.append(loc)
    remove_embedded_documents(mock_api, [], [], ["custom-documents/orphan.json"])
    assert calls.count("custom-documents/orphan.json") == 1


def test_remove_embedded_unembeds_doc_not_present_locally(mock_api):
    doc = _doc("/path/deleted.txt", "custom-documents/deleted.json")
    remove_embedded_documents(mock_api, [], [doc], ["custom-documents/deleted.json"])
    mock_api.unembed_document.assert_called_once_with("custom-documents/deleted.json")


def test_remove_embedded_keeps_doc_present_locally(mock_api):
    doc = _doc("/path/kept.txt", "custom-documents/kept.json")
    remove_embedded_documents(mock_api, ["/path/kept.txt"], [doc], ["custom-documents/kept.json"])
    mock_api.unembed_document.assert_not_called()


def test_remove_embedded_mixed_documents(mock_api):
    kept = _doc("/path/kept.txt", "custom-documents/kept.json")
    deleted = _doc("/path/deleted.txt", "custom-documents/deleted.json")
    embedded = ["custom-documents/kept.json", "custom-documents/deleted.json"]

    remove_embedded_documents(mock_api, ["/path/kept.txt"], [kept, deleted], embedded)

    mock_api.unembed_document.assert_called_once_with("custom-documents/deleted.json")


def test_remove_embedded_handles_empty_inputs(mock_api):
    remove_embedded_documents(mock_api, [], [], [])
    mock_api.unembed_document.assert_not_called()


# ---------------------------------------------------------------------------
# remove_loaded_documents
# ---------------------------------------------------------------------------

def test_remove_loaded_unloads_and_removes_from_db(mock_api, db):
    doc = _doc("/path/gone.txt", "custom-documents/gone.json")
    db.add_document(doc)
    mock_api.unload_document.return_value = True

    remove_loaded_documents(mock_api, db, [], [doc])

    mock_api.unload_document.assert_called_once_with("custom-documents/gone.json")
    assert db.get_documents() == []


def test_remove_loaded_keeps_locally_present_document(mock_api, db):
    doc = _doc("/path/kept.txt", "custom-documents/kept.json")
    db.add_document(doc)

    remove_loaded_documents(mock_api, db, ["/path/kept.txt"], [doc])

    mock_api.unload_document.assert_not_called()
    assert len(db.get_documents()) == 1


def test_remove_loaded_does_not_remove_from_db_when_unload_fails(mock_api, db):
    """DB record must be preserved if the API unload call fails."""
    doc = _doc("/path/gone.txt", "custom-documents/gone.json")
    db.add_document(doc)
    mock_api.unload_document.return_value = False

    remove_loaded_documents(mock_api, db, [], [doc])

    assert len(db.get_documents()) == 1


def test_remove_loaded_uses_local_file_path_for_db_removal(mock_api, db):
    """Regression: remove_document must be called with local_file_path, not anythingllm_document_location."""
    doc = _doc("/path/gone.txt", "custom-documents/gone.json")
    db.add_document(doc)
    mock_api.unload_document.return_value = True

    remove_loaded_documents(mock_api, db, [], [doc])

    # If the bug were present (passing anythingllm_document_location), the record would survive
    assert db.get_documents() == []


def test_remove_loaded_mixed_documents(mock_api, db):
    kept = _doc("/path/kept.txt", "custom-documents/kept.json")
    gone = _doc("/path/gone.txt", "custom-documents/gone.json")
    db.add_document(kept)
    db.add_document(gone)
    mock_api.unload_document.return_value = True

    remove_loaded_documents(mock_api, db, ["/path/kept.txt"], [kept, gone])

    mock_api.unload_document.assert_called_once_with("custom-documents/gone.json")
    remaining = db.get_documents()
    assert len(remaining) == 1
    assert remaining[0].local_file_path == "/path/kept.txt"


def test_remove_loaded_handles_empty_inputs(mock_api, db):
    remove_loaded_documents(mock_api, db, [], [])
    mock_api.unload_document.assert_not_called()


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def test_main_exits_early_on_auth_failure(tmp_path):
    mock_api_instance = MagicMock()
    mock_api_instance.authenticate.return_value = False
    test_config = AnythingLLMConfig("key", [str(tmp_path)], [], [], "slug")
    db_path = tmp_path / "test.db"

    with patch.object(AnythingLLMConfig, "load_config", return_value=test_config), \
         patch("ingest_anythingllm_docs.AnythingLLM", return_value=mock_api_instance), \
         patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        main()

    mock_api_instance.upload_document.assert_not_called()
    mock_api_instance.embed_new_document.assert_not_called()


def test_main_exits_early_on_db_init_failure(tmp_path):
    mock_api_instance = MagicMock()
    mock_api_instance.authenticate.return_value = True
    test_config = AnythingLLMConfig("key", [str(tmp_path)], [], [], "slug")
    db_path = tmp_path / "test.db"

    with patch.object(AnythingLLMConfig, "load_config", return_value=test_config), \
         patch("ingest_anythingllm_docs.AnythingLLM", return_value=mock_api_instance), \
         patch("anythingllm_loader.database.DATABASE_FILENAME", db_path), \
         patch.object(DocumentDatabase, "initialize_database", return_value=False):
        main()

    mock_api_instance.upload_document.assert_not_called()


def _patch_api_class(mock_api_instance):
    """
    Return a configured mock for the AnythingLLM class itself (not just an instance).
    supported_file_types() must return the real list so fetch_local_documents works correctly —
    MagicMock's __contains__ defaults to False, which would cause every file to appear unsupported.
    """
    mock_class = MagicMock()
    mock_class.return_value = mock_api_instance
    mock_class.supported_file_types.return_value = AnythingLLM.supported_file_types()
    return mock_class


def test_main_uploads_and_embeds_documents(tmp_path):
    doc = tmp_path / "test.txt"
    doc.write_text("content")
    test_config = AnythingLLMConfig("key", [str(tmp_path)], [], [], "slug")
    db_path = tmp_path / "test.db"

    mock_api_instance = MagicMock()
    mock_api_instance.authenticate.return_value = True
    mock_api_instance.upload_document.return_value = {
        "location": "custom-documents/test.txt-uuid.json",
        "title": "test.txt",
    }
    mock_api_instance.fetch_embedded_workspace_documents.return_value = []

    with patch.object(AnythingLLMConfig, "load_config", return_value=test_config), \
         patch("ingest_anythingllm_docs.AnythingLLM", _patch_api_class(mock_api_instance)), \
         patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        main()

    mock_api_instance.upload_document.assert_called_once()
    mock_api_instance.embed_new_document.assert_called_once_with("custom-documents/test.txt-uuid.json")


def test_main_does_not_upload_unsupported_files(tmp_path):
    (tmp_path / "file.csv").write_text("a,b,c")
    (tmp_path / "file.xyz").write_text("content")
    test_config = AnythingLLMConfig("key", [str(tmp_path)], [], [], "slug")
    db_path = tmp_path / "test.db"

    mock_api_instance = MagicMock()
    mock_api_instance.authenticate.return_value = True
    mock_api_instance.fetch_embedded_workspace_documents.return_value = []

    with patch.object(AnythingLLMConfig, "load_config", return_value=test_config), \
         patch("ingest_anythingllm_docs.AnythingLLM", _patch_api_class(mock_api_instance)), \
         patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        main()

    mock_api_instance.upload_document.assert_not_called()


def test_main_removes_embedded_docs_missing_locally(tmp_path):
    test_config = AnythingLLMConfig("key", [str(tmp_path)], [], [], "slug")
    db_path = tmp_path / "test.db"

    mock_api_instance = MagicMock()
    mock_api_instance.authenticate.return_value = True
    mock_api_instance.fetch_embedded_workspace_documents.return_value = [
        "custom-documents/orphan.json"
    ]

    with patch.object(AnythingLLMConfig, "load_config", return_value=test_config), \
         patch("ingest_anythingllm_docs.AnythingLLM", _patch_api_class(mock_api_instance)), \
         patch("anythingllm_loader.database.DATABASE_FILENAME", db_path):
        main()

    mock_api_instance.unembed_document.assert_called_with("custom-documents/orphan.json")

from datetime import datetime, timezone

import yaml

from anythingllm_loader import config as config_module
from anythingllm_loader.config import AnythingLLMConfig
from anythingllm_loader.database import AnythingLLMDocument, DocumentDatabase


def _profile(name):
    return {
        "workspace-slug": name,
        "file-paths": [f"/archive/{name}"],
        "directory-excludes": [],
        "file-excludes": [],
    }


def test_named_projects_have_independent_state_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({
        "api-key": "key",
        "projects": {"mml": _profile("mml"), "cmi": _profile("cmi")},
    }))

    mml = AnythingLLMConfig.load_config("mml")
    cmi = AnythingLLMConfig.load_config("cmi")

    assert mml.workspace_slug == "mml"
    assert cmi.workspace_slug == "cmi"
    assert mml.state_directory != cmi.state_directory
    assert mml.state_directory == tmp_path / "projects" / "mml"


def test_document_databases_are_isolated(tmp_path):
    mml = DocumentDatabase(tmp_path / "mml" / "uploaded-docs.db")
    cmi = DocumentDatabase(tmp_path / "cmi" / "uploaded-docs.db")
    assert mml.initialize_database() is True
    assert cmi.initialize_database() is True

    mml.add_document(AnythingLLMDocument(
        "/archive/mml/a.md", datetime.now(timezone.utc), "mml-location", "{}"
    ))

    assert len(mml.get_documents()) == 1
    assert cmi.get_documents() == []

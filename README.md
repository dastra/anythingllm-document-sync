# AnythingLLM Document Sync

A Python utility for syncing local documents into an AnythingLLM workspace.
It scans configured directories, uploads new or modified files, embeds them into
the workspace, and removes documents that have been deleted locally.

## Features

- **Automatic document discovery**: Recursively scans directories for supported document types
- **Smart sync**: Only uploads new or modified documents; skips unchanged ones
- **Document tracking**: Maintains a local SQLite database to track uploaded files
- **Cleanup**: Unembeds and removes documents from AnythingLLM when deleted locally
- **Configurable**: Supports file and directory exclusions

## Supported file types

`txt`, `md`, `org`, `adoc`, `rst`, `html`, `docx`, `odt`, `odp`, `pdf`, `mbox`, `epub`, `pptx`

PowerPoint files are converted locally to temporary Markdown containing slide text,
table text, speaker notes, and the original source path. The temporary files are
removed after upload; the original presentations are never modified.

## Requirements

- Python 3.12 or newer
- AnythingLLM Desktop (or server) running locally at `http://localhost:3001`

## Before the first synchronization

Prepare the AnythingLLM instance before configuring this synchronizer:

1. Install and start AnythingLLM Desktop (or start the server instance).
2. Configure the DESY Assistant as the LLM provider. Use the OpenAI-compatible
   endpoint, model name, and provider credentials supplied for your DESY
   Assistant deployment. Do not put these credentials into this repository or
   into the synchronizer configuration unless the deployment explicitly
   requires it.
3. Select local embeddings and a local vector database if document content
   must remain on the workstation or within the approved DESY environment.
4. Create one AnythingLLM workspace for each independent document project.
5. Generate an AnythingLLM Developer API key and keep it in the local config
   file or another approved secret store. Never commit it.

The LLM provider configuration is separate from `anythingllm-url`: the latter
points to the local AnythingLLM API used by this tool, normally
`http://localhost:3001`. For DESY-specific endpoint names, model identifiers,
and access requirements, use the current instructions provided by the DESY
Assistant service administrator.

## Installation

### From a Git checkout

```shell
python3 --version  # must be 3.12 or newer
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install .
```

For development, install the test dependencies as well:

```shell
python3 -m pip install -r requirements.txt
```

### With pipx

`pipx` installs the command and its dependencies in an isolated environment:

```shell
pipx install git+ssh://gitlab.example.org/group/anythingllm-document-sync.git
```

## Configuration

If you plan to synchronize more than one independent archive or AnythingLLM
workspace, use the named multi-project configuration shown below. Consider this
format before creating the configuration file; each project gets its own
workspace settings and synchronization database. The single-project format
below remains suitable for a simple installation.

Create `~/.anythingllm-sync/config.yaml`:

```yaml
api-key: YOUR-API-KEY
workspace-slug: your-workspace
anythingllm-url: http://localhost:3001  # optional, defaults to http://localhost:3001
file-paths:
  - /Users/username/Documents/
directory-excludes:
  - .obsidian
file-excludes:
  - .DS_Store
```

**API key**: AnythingLLM Desktop → spanner icon (bottom right) → Developer API → Generate New API Key

**Workspace slug**: Click workspace → settings cog → Vector Database tab → Vector database identifier

**AnythingLLM URL**: Set `anythingllm-url` if your instance is not at `http://localhost:3001` — e.g. a Docker container on a custom port: `http://localhost:8080`

For multiple independent projects, use named profiles. Each profile gets its own
AnythingLLM workspace and synchronization state:

```yaml
api-key: YOUR-API-KEY
anythingllm-url: http://localhost:3001

projects:
  mml:
    workspace-slug: mml
    file-paths:
      - /Users/username/Documents/MML
    directory-excludes: []
    file-excludes:
      - .DS_Store

  cmi:
    workspace-slug: cmi
    file-paths:
      - /Users/username/Documents/CMI
    directory-excludes: []
    file-excludes:
      - .DS_Store
```

Run a profile with:

```shell
anythingllm-document-sync --project cmi
```

The module-style invocation remains available when working from a checkout:

```shell
python3 ingest_anythingllm_docs.py --project cmi
```

Each profile stores its database under
`~/.anythingllm-sync/projects/<project>/uploaded-docs.db`. The legacy single-project
configuration continues to use `~/.anythingllm-sync/uploaded-docs.db`.

## Usage

```shell
python3 ingest_anythingllm_docs.py
```

Each run:
1. Scans `file-paths` for supported documents (respecting exclusions)
2. Uploads new or modified documents to AnythingLLM
3. Embeds uploaded-but-not-yet-embedded documents into the workspace
4. Unembeds documents no longer present locally
5. Removes unembedded documents from AnythingLLM's document store
6. Cleans up the local tracking database

Document upload state is tracked in `~/.anythingllm-sync/uploaded-docs.db` (SQLite).

## Running the tests

**Unit tests** (no AnythingLLM instance required — all API calls are mocked):

```shell
python3 -m pytest tests/test_unit.py -v
```

**Integration tests** (requires AnythingLLM running and a valid `~/.anythingllm-sync/config.yaml`):

```shell
python3 -m pytest tests/test_integration.py -v
```

Run all tests:

```shell
python3 -m pytest tests/ -v
```

## Project structure

```
ingest_anythingllm_docs.py   Main script — orchestrates the sync cycle
anythingllm_loader/
  anythingllm_api.py         AnythingLLM REST API client
  config.py                  Config file loader (~/.anythingllm-sync/config.yaml)
  database.py                SQLite wrapper (~/.anythingllm-sync/uploaded-docs.db)
tests/
  test_unit.py               Unit tests (mocked API, no live instance needed)
  test_integration.py        Integration tests (requires live AnythingLLM)
docs/
  openapi.json               AnythingLLM OpenAPI specification
```

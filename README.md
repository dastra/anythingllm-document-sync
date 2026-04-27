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

`txt`, `md`, `org`, `adoc`, `rst`, `html`, `docx`, `odt`, `odp`, `pdf`, `mbox`, `epub`

## Requirements

- Python 3.12.7
- AnythingLLM Desktop (or server) running locally at `http://localhost:3001`
- `pyenv` and `sqlite` (macOS: `brew install pyenv sqlite`)

## Installation

```shell
pyenv install 3.12.7
pyenv local 3.12.7
pyenv exec python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration

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

## Usage

```shell
python ingest_anythingllm_docs.py
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
pytest tests/test_unit.py -v
```

**Integration tests** (requires AnythingLLM running and a valid `~/.anythingllm-sync/config.yaml`):

```shell
pytest tests/test_integration.py -v
```

Run all tests:

```shell
pytest tests/ -v
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

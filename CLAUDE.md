# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```shell
pyenv install 3.12.7
pyenv local 3.12.7
pyenv exec python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Running

```shell
python ingest_anythingllm_docs.py
```

Requires `~/.anythingllm-sync/config.yaml`:

```yaml
api-key: <key>
workspace-slug: <slug>
file-paths:
  - /path/to/documents/
directory-excludes:
  - .obsidian
file-excludes:
  - .DS_Store
```

## Architecture

The tool syncs local files into an AnythingLLM workspace. There are two distinct states a document can be in:

1. **Loaded** — uploaded to AnythingLLM's document store (tracked in local SQLite DB at `~/.anythingllm-sync/uploaded-docs.db`)
2. **Embedded** — ingested into the workspace vector store (queryable by the LLM)

`ingest_anythingllm_docs.py` orchestrates a full sync cycle:
1. Discover local files matching configured paths/extensions
2. Upload new/modified files → record in SQLite DB
3. Embed loaded-but-not-embedded documents into the workspace
4. Unembed documents no longer present locally
5. Delete documents from AnythingLLM's store that are no longer present locally

`anythingllm_loader/anythingllm_api.py` — wraps the AnythingLLM REST API (assumed running at `http://localhost:3001`). Key distinction: `unload_document` calls `/v1/system/remove-documents` (deletes from store), while `unembed_document` calls `/api/v1/workspace/{slug}/update-embeddings` with `deletes` (removes from workspace only).

`anythingllm_loader/database.py` — SQLite wrapper tracking the mapping from local file path → AnythingLLM document location (`custom-documents/<name>-<uuid>.json`).

`anythingllm_loader/config.py` — loads `~/.anythingllm-sync/config.yaml`.

## Known limitations / TODOs

- Embeddings are done one at a time with a 0.5s sleep to avoid overloading AnythingLLM
- `embed_new_document` does not surface non-200 responses as a return value, so embedding failures are printed but not acted on by the caller
- Supported file types: `txt`, `md`, `org`, `adoc`, `rst`, `html`, `docx`, `odt`, `odp`, `pdf`, `mbox`, `epub`

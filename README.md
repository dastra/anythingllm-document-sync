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

1. Install and start AnythingLLM Desktop. Confirm that its local API is
   reachable at `http://localhost:3001` (or record the actual local URL).
2. In **AI Providers → LLM**, configure an approved LLM provider. If it is
   OpenAI-compatible, choose **Generic OpenAI** and enter its base URL, model
   name, and provider API key in AnythingLLM's provider settings. Keep provider
   credentials out of this repository and out of the synchronizer config unless
   the deployment explicitly requires it.
3. In **AI Providers → Embedder**, select the local embedding provider/model
   used by the AnythingLLM installation. Do not select a remote embedding
   service for confidential archives unless it is explicitly approved.
4. In **AI Providers → Vector Database**, select the local vector database
   configured for the installation. This keeps the indexed document content
   in the local AnythingLLM data directory.
5. Create one AnythingLLM workspace for each independent document project,
   for example **CMI** and **My research project**. The workspace slug in this
   tool's config must match the workspace's vector-database identifier.
6. In **Tools → Developer API**, generate an AnythingLLM Developer API key.
   Put this key in the local synchronizer config or another approved secret
   store; never commit it. This is the key used by the synchronizer to call
   the local AnythingLLM API.

The LLM provider is configured inside AnythingLLM and is used for answer
generation. The synchronizer's `anythingllm-url` is separate: it points to the
local AnythingLLM API, normally `http://localhost:3001`.

## Installation

### With pipx

`pipx` installs the command and its dependencies in an isolated environment:

```shell
pipx install git+ssh://gitlab.example.org/group/anythingllm-document-sync.git
```

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

## Configuration

If you plan to synchronize more than one independent archive or AnythingLLM
workspace, use the named multi-project configuration shown below. Consider this
format before creating the configuration file; each project gets its own
workspace settings and synchronization database. The single-project format
below remains suitable for a simple installation.

### Single-project configuration

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

### Multi-project configuration

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

Use `--dry-run` before a long synchronization to inspect planned additions,
changes, and deletions without modifying AnythingLLM. Add `--limit 20` for a
small diagnostic sample. The limit is deliberately rejected for a real run,
because a partial source list could otherwise look like deleted documents.

```shell
python3 ingest_anythingllm_docs.py --project cmi --dry-run --limit 20
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

### Scheduled operation with macOS LaunchAgents

On macOS, a LaunchAgent can run one project periodically. Keep the deployment
code, configuration, databases, and logs below `~/.anythingllm-sync/`, and run
the deployed command rather than an arbitrary development checkout. For
example, save this as
`~/Library/LaunchAgents/org.anythingllm.sync.project.plist` and replace the
placeholder paths and project name:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.anythingllm.sync.project</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/username/.local/bin/anythingllm-document-sync</string>
    <string>--project</string>
    <string>project</string>
  </array>
  <key>StartInterval</key>
  <integer>28800</integer>
  <key>StandardOutPath</key>
  <string>/Users/username/.anythingllm-sync/logs/project.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/username/.anythingllm-sync/logs/project.stderr.log</string>
</dict>
</plist>
```

`StartInterval` is in seconds; `28800` runs the project every eight hours.
Use a distinct label, project argument, and log files for each workspace. Load,
run, inspect, and unload the agent with:

```shell
launchctl bootstrap gui/$(id -u) \
  ~/Library/LaunchAgents/org.anythingllm.sync.project.plist
launchctl kickstart -k gui/$(id -u)/org.anythingllm.sync.project
launchctl print gui/$(id -u)/org.anythingllm.sync.project
tail -f ~/.anythingllm-sync/logs/project.stdout.log
launchctl bootout gui/$(id -u)/org.anythingllm.sync.project
```

Stop or restart the agent before changing its plist or deployment code, and do
not modify the original document archive while a synchronization is running.

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

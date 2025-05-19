# AnythingLLM Document Loader

A Python utility for managing document ingestion into AnythingLLM workspaces. 
This tool automates the process of uploading, embedding, and managing documents for use with AnythingLLM.

## Features

- **Automatic Document Discovery**: Recursively scans directories for supported document types
- **Smart Document Management**: Only uploads new or modified documents
- **Document Tracking**: Maintains a local database to track document status
- **Cleanup Functionality**: Removes documents from AnythingLLM that no longer exist locally
- **Configurable**: Supports file and directory exclusions

## Requirements

- Tested with Python 3.12.7
- AnythingLLM instance
- Required Python packages:
  - requests
  - PyYAML

## Installation

Instructions below are for macOS.

1. Install prerequisites

```shell
# Data about the files which have been uploaded is stored in an sqlite database
brew install sqlite
# Python virtual environments
brew install pyenv
```

2. Create and activate a python virtual environment

```shell
pyenv install 3.12.7 
pyenv local 3.12.7
pyenv exec python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

2. Install python libraries

```shell
pip install -r requirements.txt
```

## Configuration

Create a configuration file in ~/.anythingllm-sync/config.yaml.

```yaml
api-key: WFSDFD-ASDAFDFD-Q8M53TR-AAAAS48
workspace-slug: aws
file-paths:
 - /Users/username/Documents/
directory-excludes:
 - .obsidian
file-excludes:
 - .DS_Store
```

To fetch the API Key, from the AnythingLLM Desktop application:
1. Click on the spanner icon at the bottom right of the left-hand navigation, to open settings
2. Under the Tools heading, select Developer API
3. Click on "Generate New API Key"

To fetch the workspace slug:
1. From the AnythingLLM start screen, click the workspace in the left-hand navigation, and then click on the settings cog icon
2. Click the "Vector Database" tab
3. The "Vector database identifier" is the same as the workspace slug

## Usage

Run the main script to process documents:

```shell
python ingest_anythingllm_docs.py
```

The script will:
1. Scan configured directories (configured as file-paths) for documents
2. Upload new or modified documents to AnythingLLM.  The script stores a sqlite database in ~/.anythingllm-sync/uploaded-docs.db to keep a record of uploaded files.
3. Embed documents that have been uploaded but not yet embedded
4. Remove documents from AnythingLLM that no longer exist locally

## Project Structure

- `ingest_anythingllm_docs.py`: Main script for document processing
- `anythingllm_loader/`: Package containing core functionality
  - `anythingllm_api.py`: API client for AnythingLLM
  - `config.py`: Configuration handling
  - `database.py`: Local document tracking database
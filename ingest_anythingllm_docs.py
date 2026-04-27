import json
import pathlib
from datetime import datetime, timezone

from anythingllm_loader.database import DocumentDatabase, AnythingLLMDocument
from anythingllm_loader.anythingllm_api import AnythingLLM
from anythingllm_loader.config import AnythingLLMConfig


# From the file paths described in the config, find all files.
def fetch_local_documents(config: AnythingLLMConfig):
    local_documents = []
    for file_path in config.file_paths:
        # Find all files
        for file in pathlib.Path(file_path).rglob("*"):
            exclude = False
            for filename_to_exclude in config.file_excludes:
                if filename_to_exclude in file.name:
                    exclude = True
                    break

            for directory_to_exclude in config.directory_excludes:
                if directory_to_exclude in str(file.absolute()):
                    exclude = True
                    break

            if file.name.split('.')[-1] not in AnythingLLM.supported_file_types():
                exclude = True

            if file.is_file() and not exclude:
                # Add full file path to local_documents
                local_documents.append(str(file.absolute()))

    return local_documents


def upload_new_documents(anything_llm: AnythingLLM, database: DocumentDatabase, local_documents: list[str],
                         loaded_documents: list[AnythingLLMDocument]):

    loaded_by_path = {doc.local_file_path: doc for doc in loaded_documents}

    for local_document in local_documents:
        local_document_modified_timestamp = datetime.fromtimestamp(pathlib.Path(local_document).stat().st_mtime, tz=timezone.utc)
        loaded_document = loaded_by_path.get(local_document)

        if loaded_document is not None:
            # if the date of the file is after the time that the loaded_document.upload_timestamp the load again
            if int(local_document_modified_timestamp.strftime('%Y%m%d%H%M%S')) > int(
                    loaded_document.upload_timestamp.strftime('%Y%m%d%H%M%S')):
                # Remove old version from AnythingLLM before uploading the new one
                if anything_llm.unload_document(loaded_document.anythingllm_document_location):
                    database.remove_document(loaded_document.local_file_path)
                else:
                    print('Failed to remove old version of document from AnythingLLM: ' + local_document)
                # fall through to re-upload regardless of whether unload succeeded
            else:
                continue  # file unchanged, skip upload

        # upload the document
        anything_llm_response = anything_llm.upload_document(local_document)
        if anything_llm_response is not None:
            database.add_document(AnythingLLMDocument(local_document, local_document_modified_timestamp,
                                                      anything_llm_response['location'], json.dumps(anything_llm_response)
            ))


def embed_new_documents(anything_llm: AnythingLLM, loaded_documents: list[AnythingLLMDocument], embedded_documents: list):
    embedded_set = set(embedded_documents)

    # embedding one at a time as larger batches seem to max out CPU
    for loaded_document in loaded_documents:
        if loaded_document.anythingllm_document_location not in embedded_set:
            anything_llm.embed_new_document(loaded_document.anythingllm_document_location)


def remove_embedded_documents(anything_llm: AnythingLLM, local_documents: list, loaded_documents: list[AnythingLLMDocument],
                              embedded_documents: list):
    local_path_by_location = {doc.anythingllm_document_location: doc.local_file_path for doc in loaded_documents}
    local_documents_set = set(local_documents)

    for embedded_document in embedded_documents:
        # embedded_document is the loaded path:
        # "custom-documents/How-To.md-750a5515-ed82-4c2c-96b7-583463bab449.json"
        local_path = local_path_by_location.get(embedded_document)

        if local_path is None or local_path not in local_documents_set:
            anything_llm.unembed_document(embedded_document)


def remove_loaded_documents(anything_llm: AnythingLLM, database: DocumentDatabase, local_documents: list,
                            loaded_documents: list[AnythingLLMDocument]):
    local_documents_set = set(local_documents)

    for loaded_document in loaded_documents:
        if loaded_document.local_file_path not in local_documents_set:
            if anything_llm.unload_document(loaded_document.anythingllm_document_location):
                database.remove_document(loaded_document.local_file_path)


def main():
    # Fetching config
    config = AnythingLLMConfig.load_config()

    # Setting up connection to AnythingLLM
    anything_llm = AnythingLLM(config)
    if not anything_llm.authenticate():
        print("Failed to authenticate with local AnythingLLM API. Please check your API key.")
        return

    # Setting up local SQLite database which will store the map of local filename to doc path in AmythingLLM
    database = DocumentDatabase()
    if not database.initialize_database():
        print("Failed to initialise database.")
        return

    # These are the documents on our local disk
    local_documents = fetch_local_documents(config)

    # These are documents which have been loaded into AnythingLLM, but not embedded and loaded into the workspace
    loaded_documents = database.get_documents()
    # Upload any documents which exist on disk but are not yet loaded into AnythingLLM
    upload_new_documents(anything_llm, database, local_documents, loaded_documents)

    # Documents which are embedded into the workspace
    embedded_documents = anything_llm.fetch_embedded_workspace_documents()
    loaded_documents = database.get_documents()

    embed_new_documents(anything_llm, loaded_documents, embedded_documents)

    # Remove any documents which are embedded but not present locally
    embedded_documents = anything_llm.fetch_embedded_workspace_documents()
    remove_embedded_documents(anything_llm, local_documents, loaded_documents, embedded_documents)

    # Remove any documents which are loaded but not present locally
    remove_loaded_documents(anything_llm, database, local_documents, loaded_documents)


if __name__ == "__main__":
    main()

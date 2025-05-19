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

    # compare the list of local documents with embedded documents to find the local documents that need embedding
    for local_document in local_documents:
        # local_document is a file path string

        document_loaded = False
        local_document_modified_timestamp = datetime.fromtimestamp(pathlib.Path(local_document).stat().st_mtime, tz=timezone.utc)
        for loaded_document in loaded_documents:
            if loaded_document.local_file_path == local_document:

                # if the date of the file is after the time that the loaded_document.upload_timestamp the load again
                if int(local_document_modified_timestamp.strftime('%Y%m%d%H%M%S')) > int(
                        loaded_document.upload_timestamp.strftime('%Y%m%d%H%M%S')):
                    # Update the document
                    print("TODO: Upload document " + local_document)
                else:
                    document_loaded = True
                    break

        if not document_loaded:
            # upload the document
            anything_llm_response = anything_llm.upload_document(local_document)
            if anything_llm_response is not None:
                database.add_document(AnythingLLMDocument(local_document, local_document_modified_timestamp,
                                                          anything_llm_response['location'], json.dumps(anything_llm_response)
                ))


def embed_new_documents(anything_llm: AnythingLLM, loaded_documents: list[AnythingLLMDocument], embedded_documents: list):
    documents_to_embed = []

    # Work out which documents are loaded but not yet embedded
    for loaded_document in loaded_documents:
        document_embedded = False
        for embedded_document in embedded_documents:
            if embedded_document == loaded_document.anythingllm_document_location:
                document_embedded = True
                break

        if not document_embedded:
            documents_to_embed.append(loaded_document.anythingllm_document_location)

    # embedding one at a time as larger batches seem to max out CPU
    for document_to_embed in documents_to_embed:
        anything_llm.embed_new_document(document_to_embed)


def remove_embedded_documents(anything_llm: AnythingLLM, local_documents: list, loaded_documents: list[AnythingLLMDocument],
                              embedded_documents: list):
    documents_to_unembed = []

    for embedded_document in embedded_documents:
        # embedded_document is the loaded path:
        # "custom-documents/How-To.md-750a5515-ed82-4c2c-96b7-583463bab449.json"

        embedded_document_local_path = None
        for loaded_document in loaded_documents:
            if loaded_document.anythingllm_document_location == embedded_document:
                embedded_document_local_path = loaded_document.local_file_path
                break

        if embedded_document_local_path is None:
            # If the document path isn't in the database of local files, then delete it
            documents_to_unembed.append(embedded_document)
            break

        embedded_document_found_locally = False
        for local_document in local_documents:
            if embedded_document_local_path == local_document:
                embedded_document_found_locally = True
                break

        if not embedded_document_found_locally:
            documents_to_unembed.append(embedded_document)

    for document_to_unembed in documents_to_unembed:
        anything_llm.unembed_document(document_to_unembed)


def remove_loaded_documents(anything_llm: AnythingLLM, database: DocumentDatabase, local_documents: list,
                            loaded_documents: list[AnythingLLMDocument]):
    documents_to_unload = []

    for loaded_document in loaded_documents:
        document_present_locally = False

        for local_document in local_documents:
            if loaded_document.local_file_path == local_document:
                document_present_locally = True
                break

        if not document_present_locally:
            # If the document path isn't in the database of local files, then delete it
            documents_to_unload.append(loaded_document.anythingllm_document_location)

    for document_to_unload in documents_to_unload:
        if anything_llm.unload_document(document_to_unload):
            database.remove_document(document_to_unload)


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

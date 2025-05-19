import os
import re

import requests
from requests import Response
from .config import AnythingLLMConfig
import time


# Endpoints are documented here: https://github.com/Mintplex-Labs/anything-llm/blob/d1b1a98a60388b23c9c03fee8b2bd174f61970f5/server/endpoints/api/document/index.js
# See docs/openapi.json for openapi spec

class AnythingLLM:

    def __init__(self, config: AnythingLLMConfig):
        self.config = config

    # Authenticate with local AnythingLLM API
    # curl -X 'GET' \
    #   'http://localhost:3001/api/v1/auth' \
    #   -H 'accept: application/json' \
    #   -H 'Authorization: Bearer $api-key
    def authenticate(self):
        response = requests.get('http://localhost:3001/api/v1/auth', headers={
            'accept': 'application/json',
            'Authorization': 'Bearer ' + self.config.api_key
        })
        # Response looks like this. { "authenticated": true }.  Return true if HTTP 200 returned and authenticated = true
        return response.status_code == 200 and response.json()["authenticated"]

    # The list of file types which it's valid to upload to anythingllm
    # from https://github.com/Mintplex-Labs/anything-llm/collector/utils/constants.js
    @staticmethod
    def supported_file_types():
        # Removed 'xlsx' as there doesn't seem to be much useful content to be gained from uploading spreadsheets.
        # Removed 'pptx' as every pptx we attempt to upload gets the error 'No text content found'
        # Removed 'wav', 'mp3', 'mp4', 'mpeg' as this is targetting text
        return ['txt', 'md', 'org', 'adoc', 'rst', 'html', 'docx', 'odt', 'odp', 'pdf', 'mbox', 'epub']

    def upload_document(self, local_document_path):
        # Test if the document is empty
        if os.path.getsize(local_document_path) == 0:
            return

        # Test if the document is a supported file type
        if local_document_path.split('.')[-1] not in self.supported_file_types():
            print(local_document_path + " is not a supported file type. Skipping.")
            return

        response: Response = requests.post('http://localhost:3001/api/v1/document/upload', headers={
            'accept': 'application/json',
            'Authorization': 'Bearer ' + self.config.api_key
        }, files={
            'file': open(local_document_path, 'rb')
        })

        # Response looks like this
        # {
        #   "success": true,
        #   "error": null,
        #   "documents": [
        #     {
        #         'id': '750a5515-ed82-4c2c-96b7-583463bab449',
        #         'url': 'file:///Users/username/Library/Application Support/anythingllm-desktop/storage/hotdir/How-to.md',
        #         'title': 'How-to.md',
        #         'docAuthor': 'Unknown',
        #         'description': 'Unknown',
        #         'docSource': 'a text file uploaded by the user.',
        #         'chunkSource': '',
        #         'published': '26/01/2025, 21:22:20',
        #         'wordCount': 480,
        #         'pageContent': '........',
        #         'token_count_estimate': 1152,
        #         'location': 'custom-documents/How-to.md-750a5515-ed82-4c2c-96b7-583463bab449.json'
        #     }
        #   ]
        # }

        # throw an error if the response is not 200
        if response.status_code != 200:
            print('Failed to upload document: ' + local_document_path + ": " + response.text)
            return

        response_dict = response.json()

        # Throw an error if  the response is not successful
        if not response_dict['success']:
            print('Failed to upload document: ' + local_document_path + ": " + response_dict["error"])
            return

        return response_dict["documents"][0]

    # Fetch all documents uploaded to AnythingLLM, but not neccessarily embedded into the workspace.
    # curl -X 'GET' \
    #   'http://localhost:3001/api/v1/documents' \
    #   -H 'accept: application/json'
    #   -H 'Authorization: Bearer $api-key
    def fetch_loaded_documents_from_anythingllm(self):
        response = requests.get('http://localhost:3001/api/v1/documents', headers={
            'accept': 'application/json',
            'Authorization': 'Bearer ' + self.config.api_key
        })

        # Response looks like this:
        # {
        #     "localFiles": {
        #         "name": "documents",
        #         "type": "folder",
        #         "items": [
        #             {
        #                 "name": "How-To.md-750a5515-ed82-4c2c-96b7-583463bab449.json",
        #                 "type": "file",
        #                 "id": "750a5515-ed82-4c2c-96b7-583463bab449",
        #                 "url": "file:///Users/usernam/Library/Application Support/anythingllm-desktop/storage/hotdir/How-To.md",
        #                 "title": "How-To.md",
        #                 "docAuthor": "Unknown",
        #                 "description": "Unknown",
        #                 "docSource": "a text file uploaded by the user.",
        #                 "chunkSource": "localfile:///Users/username/Documents/Amazon/Process/Hiring/How-To.md",
        #                 "published": "18/10/2024, 15:18:19",
        #                 "wordCount": 2575,
        #                 "token_count_estimate": 3685,
        #                 "cached": true,
        #                 "canWatch": true,
        #                 "pinnedWorkspaces": [],
        #                 "watched": false
        #             }
        #         ]
        #     }
        # }
        loaded_documents = []
        for document in response.json()["localFiles"]["items"]:
            self.parse_loaded_document(document, loaded_documents)

        return loaded_documents

    # The document name is the unique identifier here.
    # "name": "How-To.md-750a5515-ed82-4c2c-96b7-583463bab449.json",
    def parse_loaded_document(self, item, loaded_documents):
        if item["type"] == "folder":
            for document in item["items"]:
                self.parse_loaded_document(document, loaded_documents)
        elif item["type"] == "file":
            loaded_documents.append(item["name"])
        else:
            print("Unknown type: " + item["type"])

    def unload_document(self, document_to_unload: str):
        # remove the document
        # curl -X 'DELETE' \
        #   'http://localhost:3001/v1/system/remove-documents' \
        #   -H 'accept: application/json' \
        #   -H 'Content-Type: application/json' \
        #   -d '{[
        #       "custom-documents/How-to.md-750a5515-ed82-4c2c-96b7-583463bab449.json",
        #   ]}'

        print("Removing document: " + document_to_unload)

        # Extract the excel spreadsheet name from the anythingllm_document_location
        # Excel spreadsheet looks like this: aws-game-day-and-re-invent-recap-sign-up-(responses).xlsx-2ce4/sheet-Form-responses-1.json
        # If the document to unload is an excel spreadsheet, then we need to remove the entire spreadsheet
        if re.search(r".*\.xlsx-\w+\/sheet.*", document_to_unload):
            document_to_unload = document_to_unload.split('/')[-2]

        # Delete the document.
        response: Response = requests.post('http://localhost:3001/v1/system/remove-documents',
                                           headers={
                                               'accept': 'application/json',
                                               'Content-Type': 'application/json',
                                               'Authorization': 'Bearer ' + self.config.api_key
                                           }, json={
                "deletes": [document_to_unload]
            },
                                           timeout=60)
        # throw an error if the response is not 200
        if response.status_code != 200:
            print('Failed to remove documents: ' + response.text)
            return False

        return True

    def embed_new_document(self, document_to_embed):
        # embed the document
        # curl -X 'POST' \
        #   'http://localhost:3001/api/v1/workspace/aws/update-embeddings' \
        #   -H 'accept: application/json' \
        #   -H 'Content-Type: application/json' \
        #   -d '{
        #   "adds": [
        #     "custom-documents/my-pdf.pdf-hash.json"
        #   ],
        #   "deletes": [
        #     "custom-documents/anythingllm.txt-hash.json"
        #   ]
        # }'
        # Embed the documents
        try:
            response: Response = requests.post(
                'http://localhost:3001/api/v1/workspace/' + self.config.workspace_slug + '/update-embeddings',
                headers={
                    'accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + self.config.api_key
                }, json={
                    "adds": [document_to_embed]
                },
                timeout=60)
            # throw an error if the response is not 200
            if response.status_code != 200:
                print('Failed to embed documents: ' + response.text)
                return
        except Exception as e:
            print(f'Exception occurred while embedding {str(document_to_embed)}: {str(e)}')
            return

        # Response body looks like this
        # {
        #     "workspace": {
        #         "id": 1,
        #         "name": "AWS",
        #         "slug": "aws",
        #         "vectorTag": null,
        #         "createdAt": "2024-10-18T13:15:03.450Z",
        #         "openAiTemp": 0.7,
        #         "openAiHistory": 20,
        #         "lastUpdatedAt": "2024-10-18T13:15:03.450Z",
        #         "openAiPrompt": "You are an assistant for answering questions.  You are given the extracted parts of a long document and a question. Provide a conversational answer. If you can't find the answer in the extract, just say \"I do not know.\" Don't make up an answer or answer from your own knowledge.",
        #         "similarityThreshold": 0.25,
        #         "chatProvider": null,
        #         "chatModel": null,
        #         "topN": 4,
        #         "chatMode": "query",
        #         "pfpFilename": null,
        #         "agentProvider": "anythingllm_ollama",
        #         "agentModel": "llama3.1:latest",
        #         "queryRefusalResponse": "There is no relevant information in this workspace to answer your query.",
        #         "vectorSearchMode": "rerank",
        #         "documents": [
        #             {},...
        #         ]
        #     }
        # }

        # Pause.  We don't want to overload anythingllm
        time.sleep(0.5)

    # Fetch all documents which have been embedded into the workspace
    def fetch_embedded_workspace_documents(self):
        response = requests.get('http://localhost:3001/api/v1/workspace/' + self.config.workspace_slug, headers={
            'accept': 'application/json',
            'Authorization': 'Bearer ' + self.config.api_key
        })

        # Response looks like this:
        # {
        #   "workspace": [
        #     {
        #       "id": 79,
        #       "name": "My workspace",
        #       "slug": "my-workspace-123",
        #       "createdAt": "2023-08-17 00:45:03",
        #       "openAiTemp": null,
        #       "lastUpdatedAt": "2023-08-17 00:45:03",
        #       "openAiHistory": 20,
        #       "openAiPrompt": null,
        #       "documents": [
        #           {
        #               "id": 1469,
        #               "docId": "95ed64c6-017c-4a55-b4b1-85265eedf0ad",
        #               "filename": "How-To.md-750a5515-ed82-4c2c-96b7-583463bab449.json",
        #               "docpath": "custom-documents/How-To.md-750a5515-ed82-4c2c-96b7-583463bab449.json",
        #               "workspaceId": 1,
        #               "metadata": "{\"id\":\"750a5515-ed82-4c2c-96b7-583463bab449\",\"url\":\"file:///Users/username/Library/Application Support/anythingllm-desktop/storage/hotdir/How-To.md\",\"title\":\"How-To.md\",\"docAuthor\":\"Unknown\",\"description\":\"Unknown\",\"docSource\":\"a text file uploaded by the user.\",\"chunkSource\":\"localfile:///Users/username/Documents/Amazon/Process/Hiring/How-To.md\",\"published\":\"18/10/2024, 15:18:19\",\"wordCount\":2575,\"token_count_estimate\":3685}",
        #               "pinned": false,
        #               "watched": false,
        #               "createdAt": "2025-01-20T13:43:30.401Z",
        #               "lastUpdatedAt": "2025-01-20T13:43:30.401Z"
        #           }
        #       ],
        #       "threads": []
        #     }
        #   ]
        # }
        embedded_document_paths = []
        for document in response.json()['workspace'][0]['documents']:
            # json decode the metadata value
            embedded_document_paths.append(document["docpath"])

        # unique
        return list(set(embedded_document_paths))

    def unembed_document(self, document_to_unembed: str):
        # remove the document
        # curl -X 'POST' \
        #   'http://localhost:3001/api/v1/workspace' \
        #   -H 'accept: application/json' \
        #   -H 'Content-Type: application/json' \
        #   -d '{
        #   "adds": [
        #     "custom-documents/my-pdf.pdf-hash.json"
        #   ],
        #   "deletes": [
        #     "custom-documents/anythingllm.txt-hash.json"
        #   ]
        # }'

        # Embed the documents
        response: Response = requests.post(
            'http://localhost:3001/api/v1/workspace' + self.config.workspace_slug + '/update-embeddings',
            headers={
                'accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + self.config.api_key
            }, json={
                "deletes": [document_to_unembed]
            },
            timeout=60)
        # throw an error if the response is not 200
        if response.status_code != 200:
            print('Failed to unembed documents: ' + response.text)

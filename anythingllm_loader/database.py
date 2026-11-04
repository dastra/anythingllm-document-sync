from datetime import datetime
import pathlib
import sqlite3
import os

CONFIG_DIR = pathlib.Path.home() / ".anythingllm-sync"
DATABASE_FILENAME = CONFIG_DIR / 'uploaded-docs.db'


class AnythingLLMDocument:

    def __init__(self, local_file_path: str, upload_timestamp: datetime, anythingllm_document_location: str, content: str):
        self.local_file_path = local_file_path
        self.upload_timestamp = upload_timestamp
        self.anythingllm_document_location = anythingllm_document_location
        self.content = content


class DocumentDatabase:

    def __init__(self, database_filename=None):
        self.database_filename = pathlib.Path(database_filename or DATABASE_FILENAME)

    def initialize_database(self):
        # if the ~/.anythingllm-sync/ directory doesn't exist, create it
        self.database_filename.parent.mkdir(parents=True, exist_ok=True)

        """Initialize the database and create tables if they don't exist."""
        if not self.database_filename.exists():
            try:
                with sqlite3.connect(self.database_filename) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        CREATE TABLE documents (
                            id INTEGER PRIMARY KEY,
                            local_file_path TEXT,
                            upload_timestamp DATETIME,
                            anythingllm_document_location TEXT,
                            content TEXT
                        )
                    ''')
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Error creating database: {e}")
                return False
        return True

    def get_connection(self):
        """Get a database connection."""
        return sqlite3.connect(self.database_filename)

    def add_document(self, anything_llm_document: AnythingLLMDocument):
        """Add a document to the database."""
        conn = self.get_connection()
        try:
            c = conn.cursor()

            # Store the local document path as a key and the document as a value in sqllite
            c.execute("INSERT INTO documents (local_file_path, upload_timestamp, anythingllm_document_location, "
                      "content) VALUES (?, ?, ?, ?)",
                      (
                          anything_llm_document.local_file_path,
                          anything_llm_document.upload_timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                          anything_llm_document.anythingllm_document_location,
                          anything_llm_document.content
                      ))

            # Commit and close database connection
            conn.commit()
        finally:
            if conn:
                conn.close()

    def remove_document(self, local_document_path):
        """Remove a document from the database."""
        conn = self.get_connection()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM documents WHERE local_file_path = ?", (local_document_path,))
            conn.commit()
        finally:
            if conn:
                conn.close()

    def get_documents(self) -> list[AnythingLLMDocument]:
        conn = self.get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT local_file_path, strftime('%Y-%m-%d %H:%M:%S', upload_timestamp), anythingllm_document_location, content FROM documents")
            rows = c.fetchall()
            loaded_documents = []

            for row in rows:
                upload_timestamp = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S')
                loaded_documents.append(AnythingLLMDocument(row[0], upload_timestamp, row[2], row[3]))
            c.close()
            return loaded_documents
        finally:
            if conn:
                conn.close()

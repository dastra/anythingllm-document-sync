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

    @staticmethod
    def initialize_database():
        # if the ~/.anythingllm-sync/ directory doesn't exist, create it
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)

        """Initialize the database and create tables if they don't exist."""
        if not os.path.exists(DATABASE_FILENAME):
            try:
                with sqlite3.connect(DATABASE_FILENAME) as conn:
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
            finally:
                if conn:
                    conn.close()
        return True

    @staticmethod
    def get_connection():
        """Get a database connection."""
        return sqlite3.connect(DATABASE_FILENAME)

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

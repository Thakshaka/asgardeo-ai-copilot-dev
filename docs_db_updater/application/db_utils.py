"""
Database utility functions for the docs_db_updater application.

This module provides utility functions for database operations that work with both Milvus and pgvector.
"""

import os
import logging
from docs_db_updater.application import constants as const

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def delete_records(filename, db_client):
    """
    Delete records associated with a specific filename from the collection.

    Args:
        filename: The filename to delete records for.
        db_client: The database client (either MilvusClient or PGVectorClient).

    Returns:
        A message indicating the number of records deleted.
    """
    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()

    if db_type == "pgvector":
        # For pgvector, we need to use SQL-style filtering
        primary_keys = []

        # Define a function to execute within the connection pool
        def _delete_records_func(conn, filename):
            nonlocal primary_keys
            with conn.cursor() as cursor:
                # Use PGVECTOR_EMBEDDING_TABLE for pgvector
                collection_name = const.PGVECTOR_EMBEDDING_TABLE
                cursor.execute(
                    f"SELECT collection_id FROM {collection_name} WHERE cmetadata->>'filename' = %s",
                    (filename,)
                )
                results = cursor.fetchall()
                for result in results:
                    primary_keys.append(result[0])

                if primary_keys:
                    placeholders = ', '.join(['%s'] * len(primary_keys))
                    cursor.execute(
                        f"DELETE FROM {collection_name} WHERE collection_id IN ({placeholders})",
                        primary_keys
                    )
            return len(primary_keys)

        # Execute the function using the connection pool
        try:
            db_client._execute_with_retry("delete_records", _delete_records_func, filename)
            return f"Successfully deleted {len(primary_keys)} records of {filename}"
        except Exception as e:
            logger.error(f"Failed to delete records for {filename}: {e}")
            return f"Failed to delete records for {filename}: {e}"
    else:
        # For Milvus
        primary_keys = []
        filtered_records = db_client.query(
            collection_name=os.environ.get(const.DOCS_COLLECTION),
            filter=f"{const.METADATA}['{const.FILE_NAME}'] == '{filename}'",
            output_fields=["pk"]
        )
        for filtered_record in filtered_records:
            primary_keys.append(filtered_record["pk"])

        if primary_keys:
            db_client.delete(
                collection_name=os.environ.get(const.DOCS_COLLECTION),
                filter=f"pk in {primary_keys}"
            )
        return f"Successfully deleted {len(filtered_records)} records of {filename}"

def add_records(filename, file_content, db_client, embed):
    """
    Add records from file content to the collection.

    Args:
        filename: The filename to add records for.
        file_content: The content of the file.
        db_client: The database client (either MilvusClient or PGVectorClient).
        embed: The embedding function.

    Returns:
        A message indicating the number of records added.
    """
    from docs_db_updater.application import utils

    chunked_docs = utils.chunk_docs(filename, file_content, embed, update=True)
    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()

    if db_type == "pgvector":
        # For pgvector, we need to convert the data format
        from langchain_community.vectorstores import PGVector

        # Check if connection string is provided
        if os.environ.get(const.PGVECTOR_CONNECTION_STRING):
            connection_string = os.environ.get(const.PGVECTOR_CONNECTION_STRING)
        else:
            # Build connection string from individual parameters
            host = os.environ.get(const.PGVECTOR_HOST, "localhost")
            port = os.environ.get(const.PGVECTOR_PORT, "5432")
            database = os.environ.get(const.PGVECTOR_DATABASE, "postgres")
            user = os.environ.get(const.PGVECTOR_USER, "postgres")
            password = os.environ.get(const.PGVECTOR_PASSWORD, "postgres")
            connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"

        # Convert chunked_docs to langchain Document objects
        from langchain_core.documents import Document
        documents = []
        for chunk in chunked_docs:
            metadata = chunk[const.METADATA]
            text = chunk[const.TEXT]
            documents.append(Document(page_content=text, metadata=metadata))

        # Use PGVector to add the documents
        PGVector.from_documents(
            documents,
            embed,
            collection_name=const.PGVECTOR_EMBEDDING_TABLE,
            connection_string=connection_string,
        )
    else:
        # For Milvus
        db_client.insert(collection_name=os.environ.get(const.DOCS_COLLECTION), data=chunked_docs)

    return f"Successfully added {len(chunked_docs)} records from {filename}"

def process_changes(added, modified, deleted, db_client, embed):
    """
    Process changes (added, modified, deleted files) in the collection.

    Args:
        added: List of (filename, content) tuples for added files.
        modified: List of (filename, content) tuples for modified files.
        deleted: List of filenames for deleted files.
        db_client: The database client (either MilvusClient or PGVectorClient).
        embed: The embedding function.
    """
    for filename, content in added:
        msg = add_records(filename, content, db_client, embed)
        logger.info(msg)
    for filename, content in modified:
        msg = delete_records(filename, db_client)
        logger.info(msg)
        msg = add_records(filename, content, db_client, embed)
        logger.info(msg)
    for filename in deleted:
        msg = delete_records(filename, db_client)
        logger.info(msg)

    logger.info(f"File operation summary: {len(added)} added, {len(modified)} modified, {len(deleted)} deleted")

def process_repo_changes(added, deleted, db_client, embed):
    """
    Process changes in the repository.

    Args:
        added: List of filenames for added or modified files.
        deleted: List of filenames for deleted files.
        db_client: The database client (either MilvusClient or PGVectorClient).
        embed: The embedding function.
    """
    from docs_db_updater.application import utils

    for file in added:
        msg = delete_records(file, db_client)
        logger.info(msg)
        file_content = utils.retrieve_content(file)
        msg = add_records(file, file_content, db_client, embed)
        logger.info(msg)
    for file in deleted:
        msg = delete_records(file, db_client)
        logger.info(msg)

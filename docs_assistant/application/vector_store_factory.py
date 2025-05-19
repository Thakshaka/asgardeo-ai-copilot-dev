"""
Vector store factory module for the docs_assistant application.

This module provides a factory for creating vector stores based on the configured database type.
"""

import os
import logging
from langchain_community.vectorstores import Milvus
from langchain_community.vectorstores import PGVector
from docs_assistant.application import constants as const

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_vector_store(embedding_function):
    """
    Get a vector store based on the configured database type.

    Args:
        embedding_function: The embedding function to use for the vector store.

    Returns:
        A vector store instance (either Milvus or PGVector).
    """
    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()

    if db_type == "milvus":
        logger.info("Using Milvus as the vector store")
        return Milvus(
            collection_name=os.environ.get(const.DOCS_COLLECTION),
            embedding_function=embedding_function,
            connection_args={
                "uri": os.environ.get(const.ZILLIZ_CLOUD_URI),
                "token": os.environ.get(const.ZILLIZ_CLOUD_API_KEY),
                "secure": True,
            },
        )
    elif db_type == "pgvector":
        logger.info("Using PGVector as the vector store")

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

        return PGVector(
            collection_name=os.environ.get(const.DOCS_COLLECTION),
            embedding_function=embedding_function,
            connection_string=connection_string,
        )
    else:
        logger.warning(f"Unknown database type: {db_type}. Falling back to PGVector.")

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
            
        return PGVector(
            collection_name=os.environ.get(const.DOCS_COLLECTION),
            embedding_function=embedding_function,
            connection_string=connection_string
        )

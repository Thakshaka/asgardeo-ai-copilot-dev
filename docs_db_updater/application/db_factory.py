"""
Database factory module for the docs_db_updater application.

This module provides a factory for creating database clients based on the configured database type.
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from pymilvus import MilvusClient
from docs_db_updater.application import constants as const
from docs_db_updater.application.pgvector_client import PGVectorClient

# Global client instance to ensure we reuse the same connection
_db_client = None

def get_db_client():
    """
    Get a database client based on the configured database type.

    Returns:
        A database client instance (either MilvusClient or PGVectorClient).
    """
    global _db_client

    # If we already have a client, return it
    if _db_client is not None:
        return _db_client

    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()

    if db_type == "milvus":
        logger.info("Using Milvus as the vector database")
        _db_client = MilvusClient(
            uri=os.environ.get(const.ZILLIZ_CLOUD_URI),
            token=os.environ.get(const.ZILLIZ_CLOUD_API_KEY)
        )
    elif db_type == "pgvector":
        logger.info("Using PGVector as the vector database")
        _db_client = PGVectorClient()
    else:
        logger.warning(f"Unknown database type: {db_type}. Falling back to Milvus.")
        _db_client = MilvusClient(
            uri=os.environ.get(const.ZILLIZ_CLOUD_URI),
            token=os.environ.get(const.ZILLIZ_CLOUD_API_KEY)
        )

    return _db_client

"""
PGVector commit cache module for the docs_db_updater application.

This module provides functions for managing commit information in a PostgreSQL database with pgvector.
"""

import logging
import os
import random
import time
from docs_db_updater.application import constants as const
from docs_db_updater.application.pgvector_client import PGVectorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_commits_collection(db_client):
    """
    Create a collection to store the last updated commit information.
    """
    schema = db_client.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
    )
    schema.add_field(field_name=const.PRODUCT, datatype="VARCHAR", is_primary=True, max_length=100)
    schema.add_field(field_name=const.LAST_UPDATED_COMMIT, datatype="VARCHAR", max_length=100)
    schema.add_field(field_name=const.LAST_UPDATER_VERSION, datatype="VARCHAR", max_length=100)
    schema.add_field(field_name=const.VECTOR, datatype="FLOAT_VECTOR", dim=1536)
    index_params = db_client.prepare_index_params()

    index_params.add_index(
        field_name=const.VECTOR,
        index_type="HNSW",
        metric_type="L2"
    )

    db_client.create_collection(
        collection_name=os.environ.get(const.COMMITS_COLLECTION),
        metric_type="COSINE",
        schema=schema,
        index_params=index_params
    )

def retrieve_last_updated_commit(db_client):
    """
    Retrieve the last updated commit information from the collection.
    """
    retries = 3
    sleep = 1
    attempt = 0
    while attempt < retries:
        try:
            # Use lowercase column names in the filter and output fields
            cached_commit = db_client.query(
                collection_name=os.environ.get(const.COMMITS_COLLECTION),
                filter=f"'{const.PRODUCT}' = '{const.ASGARDEO}'",
                output_fields=["last_updated_commit", "last_updater_version"]
            )
            if cached_commit:
                # Map the lowercase column names back to the constant keys for consistency
                return {
                    const.LAST_UPDATED_COMMIT: cached_commit[0]["last_updated_commit"],
                    const.LAST_UPDATER_VERSION: cached_commit[0]["last_updater_version"]
                }
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed with error: {e}")
            sleep = sleep*2
            time.sleep(sleep)
            attempt += 1
    logger.error(f"All {retries} retries failed for querying collection {os.environ.get(const.COMMITS_COLLECTION)}")
    return None

def update_last_updated_commit(commit_sha, db_client):
    """
    Update the last updated commit information in the collection.
    """
    random.seed(0)
    dummy_vector = [random.random() for _ in range(1536)]

    # Create payload with lowercase keys to match PostgreSQL column names
    payload = {
        "product": const.ASGARDEO,
        "vector": dummy_vector,
        "last_updated_commit": commit_sha,
        "last_updater_version": const.UPDATER_VERSION
    }

    response = db_client.upsert(collection_name=os.environ.get(const.COMMITS_COLLECTION), data=payload)
    logger.info(f"Latest commit sha {commit_sha} was updated successfully with response {response}")

def check_collection_existence(db_client):
    """
    Check if the commits collection exists.
    """
    has = db_client.has_collection(collection_name=os.environ.get(const.COMMITS_COLLECTION))
    if not has:
        return False
    return True

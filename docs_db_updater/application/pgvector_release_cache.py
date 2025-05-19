"""
PGVector release cache module for the docs_db_updater application.

This module provides functions for managing release information in a PostgreSQL database with pgvector.
"""

import logging
import os
import random
import time
from docs_db_updater.application import constants as const
from docs_db_updater.application.pgvector_client import PGVectorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_releases_collection(db_client):
    """
    Create a collection to store the last updated release information.
    """
    schema = db_client.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
    )
    schema.add_field(field_name=const.PRODUCT, datatype="VARCHAR", is_primary=True, max_length=100)
    schema.add_field(field_name=const.LAST_UPDATED_RELEASE, datatype="VARCHAR", max_length=100)
    schema.add_field(field_name=const.LAST_UPDATER_VERSION, datatype="VARCHAR", max_length=100)
    schema.add_field(field_name=const.VECTOR, datatype="FLOAT_VECTOR", dim=1536)
    index_params = db_client.prepare_index_params()

    index_params.add_index(
        field_name=const.VECTOR,
        index_type="HNSW",
        metric_type="COSINE"
    )

    db_client.create_collection(
        collection_name=os.environ.get(const.RELEASES_COLLECTION),
        metric_type="COSINE",
        schema=schema,
        index_params=index_params
    )

def retrieve_last_updated_release(db_client):
    """
    Retrieve the last updated release information from the collection.
    """
    retries = 3
    sleep = 1
    attempt = 0
    while attempt < retries:
        try:
            cached_release = db_client.query(
                collection_name=os.environ.get(const.RELEASES_COLLECTION),
                filter=f"{const.PRODUCT} = '{const.ASGARDEO}'",
                output_fields=["last_updated_release", "last_updater_version"]
            )
            if cached_release:
                return {
                    const.LAST_UPDATED_RELEASE: cached_release[0]["last_updated_release"],
                    const.LAST_UPDATER_VERSION: cached_release[0]["last_updater_version"]
                }
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed with error: {e}")
            sleep = sleep*2
            time.sleep(sleep)
            attempt += 1
    logger.error(f"All {retries} retries failed for querying collection {os.environ.get(const.RELEASES_COLLECTION)}")
    return None

def update_last_updated_release(latest_release_tag, db_client):
    """
    Update the last updated release information in the collection.
    """
    random.seed(0)
    dummy_vector = [random.random() for _ in range(1536)]

    # Create payload with lowercase keys to match PostgreSQL column names
    payload = {
        "product": const.ASGARDEO,
        "vector": dummy_vector,
        "last_updated_release": latest_release_tag,
        "last_updater_version": const.UPDATER_VERSION
    }

    response = db_client.upsert(collection_name=os.environ.get(const.RELEASES_COLLECTION), data=payload)
    logger.info(f"Latest release tag {latest_release_tag} was updated successfully with response {response}")

def check_collection_existence(db_client):
    """
    Check if the releases collection exists.
    """
    has = db_client.has_collection(collection_name=os.environ.get(const.RELEASES_COLLECTION))
    if not has:
        return False
    return True

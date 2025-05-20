import logging
import os
import random
import time
from pymilvus import DataType
from docs_db_updater.application import constants as const

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_commits_collection(milvus_client):
    """
    Create a collection to store the last updated commit information.
    """
    schema = milvus_client.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
    )
    schema.add_field(field_name=const.PRODUCT, datatype=DataType.VARCHAR, is_primary=True, max_length=100)
    schema.add_field(field_name=const.LAST_UPDATED_REF, datatype=DataType.VARCHAR, max_length=100)
    schema.add_field(field_name=const.LAST_UPDATER_VERSION, datatype=DataType.VARCHAR, max_length=100)
    schema.add_field(field_name=const.VECTOR, datatype=DataType.FLOAT_VECTOR, dim=1536)
    index_params = milvus_client.prepare_index_params()

    index_params.add_index(
        field_name=const.VECTOR,
        index_type="AUTOINDEX",
        metric_type="L2"
    )

    milvus_client.create_collection(
        collection_name=const.TRACKING_COLLECTION,
        metric_type="COSINE",
        schema=schema,
        index_params=index_params
    )


def retrieve_last_updated_commit(milvus_client):
    """
    Retrieve the last updated commit information from the collection.
    """
    retries = 3
    sleep = 1
    attempt = 0
    while attempt < retries:
        try:
            cached_commit = milvus_client.query(
                collection_name=const.TRACKING_COLLECTION,
                filter=f"{const.PRODUCT} == '{os.environ.get(const.PRODUCT_NAME)}'",
                output_fields=[const.LAST_UPDATED_REF, const.LAST_UPDATER_VERSION]
            )
            if cached_commit:
                return cached_commit[0]
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed with error: {e}")
            sleep = sleep*2
            time.sleep(sleep)
            attempt += 1
    logger.error(f"All {retries} retries failed for querying collection {const.TRACKING_COLLECTION}")
    return None


def update_last_updated_commit(commit_sha, milvus_client):
    """
    Update the last updated commit information in the collection.
    """
    random.seed(0)
    dummy_vector = [random.random() for _ in range(1536)]
    payload = {
        const.PRODUCT: os.environ.get(const.PRODUCT_NAME),
        const.VECTOR: dummy_vector,
        const.LAST_UPDATED_REF: commit_sha,
        const.LAST_UPDATER_VERSION: const.UPDATER_VERSION
    }
    response = milvus_client.upsert(collection_name=const.TRACKING_COLLECTION, data=payload)
    logger.info(f"Latest commit sha {commit_sha} was updated successfully with response {response}")


def check_collection_existence(milvus_client):
    """
    Check if the commits collection exists.
    """
    has = milvus_client.has_collection(collection_name=const.TRACKING_COLLECTION)
    if not has:
        return False
    return True

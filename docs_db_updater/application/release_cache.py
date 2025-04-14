import logging
import os
import random
import time
from pymilvus import DataType, MilvusClient
from docs_db_updater.application import constants as const

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_releases_collection(milvus_client):
    schema = MilvusClient.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
    )
    schema.add_field(field_name=const.PRODUCT, datatype=DataType.VARCHAR, is_primary=True, max_length=100)
    schema.add_field(field_name=const.LAST_UPDATED_RELEASE, datatype=DataType.VARCHAR, max_length=100)
    schema.add_field(field_name=const.LAST_UPDATER_VERSION, datatype=DataType.VARCHAR, max_length=100)
    schema.add_field(field_name=const.VECTOR, datatype=DataType.FLOAT_VECTOR, dim=1536)
    index_params = milvus_client.prepare_index_params()

    index_params.add_index(
        field_name=const.VECTOR,
        index_type="AUTOINDEX",
        metric_type="COSINE"
    )

    milvus_client.create_collection(
        collection_name=os.environ.get(const.RELEASES_COLLECTION),
        metric_type="COSINE",
        schema=schema,
        index_params=index_params
    )

def retrieve_last_updated_release(milvus_client):
    retries = 3
    sleep = 1
    attempt = 0
    while attempt < retries:
        try:
            cached_release = milvus_client.query(
                collection_name=os.environ.get(const.RELEASES_COLLECTION),
                filter=f"{const.PRODUCT} == '{const.ASGARDEO}'",
                output_fields=[const.LAST_UPDATED_RELEASE, const.LAST_UPDATER_VERSION]
            )
            if cached_release:
                return cached_release[0]
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed with error: {e}")
            sleep = sleep*2
            time.sleep(sleep)
            attempt += 1
    logger.error(f"All {retries} retries failed for querying collection {os.environ.get(const.RELEASES_COLLECTION)}")
    return None

def update_last_updated_release(latest_release_tag, milvus_client):
    random.seed(0)
    dummy_vector = [random.random() for _ in range(1536)]
    payload = {
        const.PRODUCT: const.ASGARDEO,
        const.VECTOR: dummy_vector,
        const.LAST_UPDATED_RELEASE: latest_release_tag,
        const.LAST_UPDATER_VERSION: const.UPDATER_VERSION
    }
    response = milvus_client.upsert(collection_name=os.environ.get(const.RELEASES_COLLECTION), data=payload)
    logger.info(f"Latest release tag {latest_release_tag} was updated successfully with response {response}")

def check_collection_existence(milvus_client):
    has = milvus_client.has_collection(collection_name=os.environ.get(const.RELEASES_COLLECTION))
    if not has:
        return False
    return True

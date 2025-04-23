import logging
import os
from langchain_community.vectorstores import Milvus
from langchain_openai import AzureOpenAIEmbeddings
from dotenv import load_dotenv
from pymilvus import MilvusClient
from docs_db_updater.application import constants as const
from docs_db_updater.application import utils
from docs_db_updater.application import release_cache

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

embed = AzureOpenAIEmbeddings(azure_deployment=const.ASGARDEO_AI_EMBEDDING,
                              openai_api_version=const.DEPLOYMENT_VERSION,
                              azure_endpoint=os.environ.get(const.AZURE_OPENAI_ENDPOINT),
                              openai_api_key=os.environ.get(const.AZURE_OPENAI_API_KEY))

milvus_client = MilvusClient(uri=os.environ.get(const.ZILLIZ_CLOUD_URI),
                             token=os.environ.get(const.ZILLIZ_CLOUD_API_KEY))

def insert_collection(latest_release_tag, assets):
    asset = next((a for a in assets if a["name"].startswith("asgardeo-docs")), None)

    if not asset:
        return
    
    logger.info(f"Latest release tag: {latest_release_tag}")
    
    docs = utils.get_chunked_docs(asset, embed)
    batch_size = const.BATCH_SIZE

    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        Milvus.from_documents(
            batch,
            embed,
            drop_old=(i == 0),
            collection_name=os.environ.get(const.DOCS_COLLECTION),
            metadata_field=const.ASGARDEO_METADATA,
            connection_args={
                "uri": os.environ.get(const.ZILLIZ_CLOUD_URI),
                "token": os.environ.get(const.ZILLIZ_CLOUD_API_KEY),
                "secure": True,
            },
        )

def update_collection(latest_release_tag, assets):
    asset = next((a for a in assets if a["name"].startswith("asgardeo-docs")), None)
    cache_history = release_cache.retrieve_last_updated_release(milvus_client)   

    logger.info(f"Latest release tag: {latest_release_tag}")
    logger.info(f"Last updated release tag: {cache_history[const.LAST_UPDATED_RELEASE]}") 

    if not asset or cache_history[const.LAST_UPDATED_RELEASE] == latest_release_tag:
        return
    
    def check_drop_collection():
        #  We will use docs_db_updater version to specify if there are code changes
        #  First we check if the docs_db_updater version field is in the RELEASES_COLLECTION
        collections_stats = milvus_client.describe_collection(collection_name=os.environ.get(const.RELEASES_COLLECTION))
        has_updater_field = False
        for field in collections_stats["fields"]:
            if field["name"] == const.LAST_UPDATER_VERSION:
                has_updater_field = True
        if not has_updater_field:
            logger.info(f"Dropping {os.environ.get(const.RELEASES_COLLECTION)} to create new schema")
            milvus_client.drop_collection(collection_name=os.environ.get(const.RELEASES_COLLECTION))
            return True
        if cache_history is None:
            logger.info("Replaced the whole collection since the last release was missing")
            return True
        if cache_history[const.LAST_UPDATER_VERSION] != const.UPDATER_VERSION:
            logger.info("Dropping and inserting the docs collection")
            return True
    if check_drop_collection():
        insert_collection(latest_release_tag, assets)
    else:
        added, modified, deleted = utils.compare_releases(cache_history[const.LAST_UPDATED_RELEASE], latest_release_tag)
        utils.process_changes(added, modified, deleted, milvus_client, embed)

def update_docs_db():
    logger.info('Starting the docs db updater task')
    has = milvus_client.has_collection(collection_name=os.environ.get(const.DOCS_COLLECTION))
    latest_release_tag, assets = utils.get_latest_release_data()
    if has:
        logger.info(f"Updating the collection {os.environ.get(const.DOCS_COLLECTION)}")
        update_collection(latest_release_tag, assets)
    else:
        logger.info(f"Inserting collection {os.environ.get(const.DOCS_COLLECTION)}")
        insert_collection(latest_release_tag, assets)    
    if not release_cache.check_collection_existence(milvus_client):
        release_cache.create_releases_collection(milvus_client)
    release_cache.update_last_updated_release(latest_release_tag, milvus_client)

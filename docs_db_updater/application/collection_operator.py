import logging
import os
from langchain_community.vectorstores import Milvus
from langchain_openai import AzureOpenAIEmbeddings
from dotenv import load_dotenv
from pymilvus import MilvusClient
from docs_db_updater.application import constants as const
from docs_db_updater.application import utils
from docs_db_updater.application import release_cache
from docs_db_updater.application import commit_cache

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
    """
    Insert documents from release assets into the collection.
    """
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
    """
    Update the collection with changes from the latest release.
    """
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

# Repository-based document processing functions
def insert_repo_collection():
    """
    Insert documents from the repository into the collection.
    """
    filenames = utils.load_md_files_from_repo()
    docs = utils.get_chunked_docs_from_repo(filenames, embed)
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

def update_repo_collection(latest_commit):
    """
    Update the collection with changes from the repository.
    """
    cache_history = commit_cache.retrieve_last_updated_commit(milvus_client)

    logger.info(f"Latest commit: {latest_commit}")

    if cache_history is None:
        logger.info("No previous commit found, inserting all documents")
        insert_repo_collection()
        return

    logger.info(f"Last updated commit: {cache_history[const.LAST_UPDATED_COMMIT]}")

    if cache_history[const.LAST_UPDATED_COMMIT] == latest_commit:
        logger.info("No changes since last update")
        return

    def check_drop_collection():
        # Check if we need to drop the collection and reinsert all documents
        if cache_history is None:
            logger.info("Replaced the whole collection since the last commit was missing")
            return True
        if cache_history[const.LAST_UPDATER_VERSION] != const.UPDATER_VERSION:
            logger.info("Dropping and inserting the docs collection due to version change")
            return True
        return False

    if check_drop_collection():
        insert_repo_collection()
    else:
        commits_files = utils.compare_commits(str(cache_history[const.LAST_UPDATED_COMMIT]), latest_commit)
        added, deleted = utils.get_diff_from_commits(commits_files)
        utils.process_repo_changes(added, deleted, milvus_client, embed)

def update_docs_db():
    """
    Update the docs database based on the configured processing mode.
    """
    logger.info('Starting docs db updater task')

    # Get the document processing mode from environment variables
    processing_mode = os.environ.get(const.DOC_PROCESSING_MODE, const.DEFAULT_PROCESSING_MODE)
    logger.info(f"Using document processing mode: {processing_mode}")

    has = milvus_client.has_collection(collection_name=os.environ.get(const.DOCS_COLLECTION))

    if processing_mode == const.REPOSITORY_MODE:
        # Repository-based approach
        latest_commit = utils.get_latest_commit()
        if has:
            logger.info(f"Updating the collection {os.environ.get(const.DOCS_COLLECTION)}")
            update_repo_collection(latest_commit)
        else:
            logger.info(f"Inserting collection {os.environ.get(const.DOCS_COLLECTION)}")
            insert_repo_collection()

        if not commit_cache.check_collection_existence(milvus_client):
            commit_cache.create_commits_collection(milvus_client)
        commit_cache.update_last_updated_commit(latest_commit, milvus_client)
    else:
        # Release-based approach
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

    logger.info('Docs db updater task completed successfully')

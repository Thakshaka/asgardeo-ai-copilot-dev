import logging
import os
from langchain_community.vectorstores import Milvus, PGVector
from langchain_openai import AzureOpenAIEmbeddings
from dotenv import load_dotenv
from docs_db_updater.application import constants as const
from docs_db_updater.application import utils
from docs_db_updater.application import release_cache
from docs_db_updater.application import commit_cache
from docs_db_updater.application import pgvector_release_cache
from docs_db_updater.application import pgvector_commit_cache
from docs_db_updater.application import db_utils
from docs_db_updater.application.db_factory import get_db_client

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

embed = AzureOpenAIEmbeddings(azure_deployment=os.environ.get(const.AI_EMBEDDING),
                              openai_api_version=os.environ.get(const.DEPLOYMENT_VERSION),
                              azure_endpoint=os.environ.get(const.AZURE_OPENAI_ENDPOINT),
                              openai_api_key=os.environ.get(const.AZURE_OPENAI_API_KEY))

# Get the appropriate database client based on configuration
db_client = get_db_client()

def insert_collection(latest_release_tag, assets):
    """
    Insert documents from release assets into the collection.
    """
    asset = next((a for a in assets if a["name"].startswith(os.environ.get(const.ASSET_NAME))), None)

    if not asset:
        return

    logger.info(f"Latest release tag: {latest_release_tag}")

    docs = utils.get_chunked_docs(asset, embed)
    batch_size = int(os.environ.get(const.BATCH_SIZE))

    # Determine which database type we're using
    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()

    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]

        if db_type == "pgvector":
            # Use PGVector
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

            PGVector.from_documents(
                batch,
                embed,
                collection_name=os.environ.get(const.DOCS_COLLECTION),
                connection_string=connection_string,
                pre_delete_collection=(i == 0),  # Only delete on first batch
            )
        else:
            # Use Milvus
            Milvus.from_documents(
                batch,
                embed,
                drop_old=(i == 0),
                collection_name=os.environ.get(const.DOCS_COLLECTION),
                metadata_field=const.METADATA,
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
    asset = next((a for a in assets if a["name"].startswith(os.environ.get(const.ASSET_NAME))), None)

    # Use the appropriate cache module based on the database type
    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()
    if db_type == "pgvector":
        cache_history = pgvector_release_cache.retrieve_last_updated_release(db_client)
    else:
        cache_history = release_cache.retrieve_last_updated_release(db_client)

    logger.info(f"Latest release tag: {latest_release_tag}")
    logger.info(f"Last updated release tag: {cache_history[const.LAST_UPDATED_REF] if cache_history else 'None'}")

    if not asset or cache_history[const.LAST_UPDATED_REF] == latest_release_tag:
        return

    def check_drop_collection():
        #  We will use docs_db_updater version to specify if there are code changes
        #  First we check if the docs_db_updater version field is in the TRACKING_COLLECTION
        collections_stats = db_client.describe_collection(collection_name=const.TRACKING_COLLECTION)
        has_updater_field = False
        for field in collections_stats["fields"]:
            if field["name"] == const.LAST_UPDATER_VERSION:
                has_updater_field = True
        if not has_updater_field:
            logger.info(f"Dropping {const.TRACKING_COLLECTION} to create new schema")
            db_client.drop_collection(collection_name=const.TRACKING_COLLECTION)
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
        added, modified, deleted = utils.compare_releases(cache_history[const.LAST_UPDATED_REF], latest_release_tag)
        db_utils.process_changes(added, modified, deleted, db_client, embed)

# Repository-based document processing functions
def insert_repo_collection():
    """
    Insert documents from the repository into the collection.
    """
    filenames = utils.load_md_files_from_repo()
    docs = utils.get_chunked_docs_from_repo(filenames, embed)
    batch_size = os.environ.get(const.BATCH_SIZE)

    # Determine which database type we're using
    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()

    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]

        if db_type == "pgvector":
            # Use PGVector
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

            PGVector.from_documents(
                batch,
                embed,
                collection_name=os.environ.get(const.DOCS_COLLECTION),
                connection_string=connection_string,
                pre_delete_collection=(i == 0),  # Only delete on first batch
            )
        else:
            # Use Milvus
            Milvus.from_documents(
                batch,
                embed,
                drop_old=(i == 0),
                collection_name=os.environ.get(const.DOCS_COLLECTION),
                metadata_field=const.METADATA,
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
    # Use the appropriate cache module based on the database type
    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()
    if db_type == "pgvector":
        cache_history = pgvector_commit_cache.retrieve_last_updated_commit(db_client)
    else:
        cache_history = commit_cache.retrieve_last_updated_commit(db_client)

    logger.info(f"Latest commit: {latest_commit}")

    if cache_history is None:
        logger.info("No previous commit found, inserting all documents")
        insert_repo_collection()
        return

    logger.info(f"Last updated commit: {cache_history[const.LAST_UPDATED_REF]}")

    if cache_history[const.LAST_UPDATED_REF] == latest_commit:
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
        commits_files = utils.compare_commits(str(cache_history[const.LAST_UPDATED_REF]), latest_commit)
        added, deleted = utils.get_diff_from_commits(commits_files)
        db_utils.process_repo_changes(added, deleted, db_client, embed)

def update_docs_db():
    """
    Update the docs database based on the configured processing mode.
    """
    logger.info('Starting docs db updater task')

    # Get the document processing mode from environment variables
    processing_mode = os.environ.get(const.DOC_PROCESSING_MODE, const.DEFAULT_PROCESSING_MODE)
    logger.info(f"Using document processing mode: {processing_mode}")

    # Determine which database type we're using
    db_type = os.environ.get(const.VECTOR_DB_TYPE, const.DEFAULT_VECTOR_DB_TYPE).lower()

    if db_type == "pgvector":
        if (db_client.has_collection(collection_name=const.PGVECTOR_COLLECTION_REGISTRY_TABLE)):
            # Check if the collection registry table contains a row with the name matching DOCS_COLLECTION
            collection_registry_table = const.PGVECTOR_COLLECTION_REGISTRY_TABLE
            docs_collection_name = os.environ.get(const.DOCS_COLLECTION)
            has = db_client.query(
                collection_name=collection_registry_table,
                filter=f"name = '{docs_collection_name}'",
                output_fields=["name"]
            ) != []
        else:
            has = False
    else:
        has = db_client.has_collection(collection_name=os.environ.get(const.DOCS_COLLECTION))

    if processing_mode == const.REPOSITORY_MODE:
        # Repository-based approach
        latest_commit = utils.get_latest_commit()
        if has:
            logger.info(f"Updating the collection {os.environ.get(const.DOCS_COLLECTION)}")
            update_repo_collection(latest_commit)
        else:
            logger.info(f"Inserting collection {os.environ.get(const.DOCS_COLLECTION)}")
            insert_repo_collection()

        # Use the appropriate cache module based on the database type
        if db_type == "pgvector":
            if not pgvector_commit_cache.check_collection_existence(db_client):
                pgvector_commit_cache.create_commits_collection(db_client)
            pgvector_commit_cache.update_last_updated_commit(latest_commit, db_client)
        else:
            if not commit_cache.check_collection_existence(db_client):
                commit_cache.create_commits_collection(db_client)
            commit_cache.update_last_updated_commit(latest_commit, db_client)
    else:
        # Release-based approach
        latest_release_tag, assets = utils.get_latest_release_data()
        if has:
            logger.info(f"Updating the collection {os.environ.get(const.DOCS_COLLECTION)}")
            update_collection(latest_release_tag, assets)
        else:
            logger.info(f"Inserting collection {os.environ.get(const.DOCS_COLLECTION)}")
            insert_collection(latest_release_tag, assets)

        # Use the appropriate cache module based on the database type
        if db_type == "pgvector":
            if not pgvector_release_cache.check_collection_existence(db_client):
                pgvector_release_cache.create_releases_collection(db_client)
            pgvector_release_cache.update_last_updated_release(latest_release_tag, db_client)
        else:
            if not release_cache.check_collection_existence(db_client):
                release_cache.create_releases_collection(db_client)
            release_cache.update_last_updated_release(latest_release_tag, db_client)

    logger.info('Docs db updater task completed successfully')

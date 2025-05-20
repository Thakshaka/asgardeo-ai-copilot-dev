# Vector Database Type
VECTOR_DB_TYPE = "VECTOR_DB_TYPE"
DEFAULT_VECTOR_DB_TYPE = "pgvector"

# Milvus Configuration
ZILLIZ_CLOUD_URI = "ZILLIZ_CLOUD_URI"
ZILLIZ_CLOUD_API_KEY = "ZILLIZ_CLOUD_API_KEY"

# PGVector Configuration
PGVECTOR_CONNECTION_STRING = "PGVECTOR_CONNECTION_STRING"
PGVECTOR_HOST = "PGVECTOR_HOST"
PGVECTOR_PORT = "PGVECTOR_PORT"
PGVECTOR_DATABASE = "PGVECTOR_DATABASE"
PGVECTOR_USER = "PGVECTOR_USER"
PGVECTOR_PASSWORD = "PGVECTOR_PASSWORD"

# Collection Names
DOCS_COLLECTION = "DOCS_COLLECTION"
TRACKING_COLLECTION = "tracking_collection"
PGVECTOR_EMBEDDING_TABLE = "langchain_pg_embedding"
PGVECTOR_COLLECTION_REGISTRY_TABLE = "langchain_pg_collection"
ASSET_NAME = "ASSET_NAME"

# Azure OpenAI
AZURE_OPENAI_ENDPOINT = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_API_KEY = "AZURE_OPENAI_API_KEY"
GITHUB_TOKEN = "GITHUB_TOKEN"
DOC_PROCESSING_MODE = "DOC_PROCESSING_MODE"

# GitHub Repository Configuration
REPO_NAME = "REPO_NAME"
BRANCH = "BRANCH"
AUTHORIZATION = "Authorization"
ACCEPT = "Accept"
TIMEOUT = (10, 60)

# Product Information
PRODUCT = "product"
PRODUCT_NAME = "PRODUCT_NAME"
UPDATER_VERSION = "1.0"
LAST_UPDATED_REF = "last_updated_ref"
LAST_UPDATER_VERSION = "last_updater_version"

# Document Processing Modes
RELEASE_MODE = "release"
REPOSITORY_MODE = "repository"
DEFAULT_PROCESSING_MODE = RELEASE_MODE

# File System and Paths
PATH = "path"
TREE = "tree"
FILE_NAME = "filename"
MD_FORMAT = ".md"
MAIN_DIR = "MAIN_DIR"
DOC_PATH = "DOC_PATH"
WEB_PATH = "WEB_PATH"
DOC_LINK = "doc_link"
IGNORE_FILES = "IGNORE_FILES"
IGNORE_REL_PATHS = "IGNORE_REL_PATHS"

# Document Processing
headers_to_split_on = [
    ("#", "Header1"),
    ("##", "Header2"),
    # ("###", "Header3"),  # uncomment this line if we want to switch to the table with splitting on header 3
]
HEADER1 = "Header1"
HEADER2 = "Header2"
HEADER3 = "Header3"
TEXT = "text"

# Vector Database and AI
METADATA = "metadata"
AI_EMBEDDING = "AI_EMBEDDING"
DEPLOYMENT_VERSION = "DEPLOYMENT_VERSION"
VECTOR = "vector"
STATUS = "status"
BATCH_SIZE = "BATCH_SIZE"

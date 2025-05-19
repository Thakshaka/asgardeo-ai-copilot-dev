# ==============================
# Environment Variables
# ==============================
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
RELEASES_COLLECTION = "RELEASES_COLLECTION"
COMMITS_COLLECTION = "COMMITS_COLLECTION"

# Azure OpenAI
AZURE_OPENAI_ENDPOINT = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_API_KEY = "AZURE_OPENAI_API_KEY"
GITHUB_TOKEN = "GITHUB_TOKEN"
DOC_PROCESSING_MODE = "DOC_PROCESSING_MODE"

# ==============================
# GitHub Repository Configuration
# ==============================
REPO_NAME = "wso2/docs-is"  # changed to wso2/docs-is
BRANCH = "master"  # changed to master
AUTHORIZATION = "Authorization"
ACCEPT = "Accept"
TIMEOUT = (10, 60)

# ==============================
# Product Information
# ==============================
PRODUCT = "product"
ASGARDEO = "Asgardeo"
UPDATER_VERSION = "1.0"
LAST_UPDATED_RELEASE = "last_updated_release"
LAST_UPDATED_COMMIT = "last_updated_commit"
LAST_UPDATER_VERSION = "last_updater_version"

# ==============================
# Document Processing Modes
# ==============================
RELEASE_MODE = "release"
REPOSITORY_MODE = "repository"
DEFAULT_PROCESSING_MODE = RELEASE_MODE

# ==============================
# File System and Paths
# ==============================
PATH = "path"
TREE = "tree"
FILE_NAME = "filename"
MD_FORMAT = ".md"
MAIN_DIR = "en/asgardeo/"  # changed to en/asgardeo
DOC_PATH = "en/asgardeo/docs/"  # changed to en/asgardeo/docs
WEB_PATH = "https://wso2.com/asgardeo/docs/"  # changed to asgardeo
DOC_LINK = "doc_link"
IGNORE_FILES = ['vs-code', 'index', 'page-not-found', 'asgardeo-cli']  # changed to asgardeo-cli
IGNORE_REL_PATHS = ("out-prod/asgardeo/docs/index.html", "out-prod/asgardeo/docs/404.html")

# ==============================
# Document Processing
# ==============================
headers_to_split_on = [
    ("#", "Header1"),
    ("##", "Header2"),
    # ("###", "Header3"),  # uncomment this line if we want to switch to the table with splitting on header 3
]
HEADER1 = "Header1"
HEADER2 = "Header2"
HEADER3 = "Header3"
TEXT = "text"

# ==============================
# Vector Database and AI
# ==============================
ASGARDEO_METADATA = "AsgardeoMetadata"
ASGARDEO_AI_EMBEDDING = "ada"
DEPLOYMENT_VERSION = "2025-01-01-preview"
VECTOR = "vector"
STATUS = "status"
BATCH_SIZE = 200

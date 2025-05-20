import os
import re
import zipfile
import shutil
import hashlib
import tempfile
import logging
import requests
import base64
from langchain.text_splitter import MarkdownHeaderTextSplitter
import markdownify
from bs4 import BeautifulSoup
from docs_db_updater.application import constants as const

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=const.headers_to_split_on)

def text_to_anchor(text):
    """
    Convert text to an HTML anchor format.
    """
    anchor = text.lower()
    anchor = anchor.replace(" ", "-")
    anchor = re.sub("[^0-9a-zA-Z-]", "", anchor)
    anchor = "#" + anchor
    return anchor

def create_formatted_chunk(chunk, file_name, doc_link, embed):
    """
    Create a formatted chunk with metadata for vector storage.
    """
    formatted_chunk = {const.METADATA: {}}
    formatted_chunk[const.METADATA][const.FILE_NAME] = file_name
    formatted_chunk[const.METADATA][const.DOC_LINK] = doc_link
    if const.HEADER3 in chunk.metadata.keys():
        formatted_chunk[const.METADATA][const.HEADER3] = chunk.metadata[const.HEADER3]
    if const.HEADER2 in chunk.metadata.keys():
        formatted_chunk[const.METADATA][const.HEADER2] = chunk.metadata[const.HEADER2]
    if const.HEADER1 in chunk.metadata.keys():
        formatted_chunk[const.METADATA][const.HEADER1] = chunk.metadata[const.HEADER1]
    formatted_chunk[const.TEXT] = chunk.page_content
    formatted_chunk[const.VECTOR] = embed.embed_query(chunk.page_content)
    return formatted_chunk

def chunk_docs(file_name, file_content, embed, update=False):
    """
    Split markdown content into chunks and process them.
    """
    data = []
    chunked_doc = markdown_splitter.split_text(file_content)
    for chunk in chunked_doc:
        suffix = ""
        if const.HEADER3 in chunk.metadata.keys():
            suffix = text_to_anchor(chunk.metadata[const.HEADER3])
        elif const.HEADER2 in chunk.metadata.keys():
            suffix = text_to_anchor(chunk.metadata[const.HEADER2])
        doc_link = os.environ.get(const.WEB_PATH)+file_name[len(os.environ.get(const.DOC_PATH)):-3]+"/"+suffix
        chunk.metadata[const.FILE_NAME] = file_name
        chunk.metadata[const.DOC_LINK] = doc_link
        chunk.page_content = chunk.page_content.replace("../../", f"{os.environ.get(const.WEB_PATH)}")
        chunk.page_content = chunk.page_content.replace("../", f"{os.environ.get(const.WEB_PATH)}")
        chunk.page_content = chunk.page_content.replace(".md", "")
        chunk.page_content = chunk.page_content.replace("{.cInlineImage-full}", "")
        header1_text = '#' + chunk.metadata[const.HEADER1] if const.HEADER1 in chunk.metadata.keys() else ''
        header2_text = '\n##' + chunk.metadata[const.HEADER2] if const.HEADER2 in chunk.metadata.keys() else ''
        header3_text = '\n###' + chunk.metadata[const.HEADER3] if const.HEADER3 in chunk.metadata.keys() else ''
        content_text = '\n' + chunk.page_content
        chunk.page_content = f"{header1_text}{header2_text}{header3_text}{content_text}"
        if update:
            chunk = create_formatted_chunk(chunk, file_name, doc_link, embed)
        data.append(chunk)
    return data

def delete_records(filename, milvus_client):
    """
    Delete records associated with a specific filename from the collection.
    """
    primary_keys = []
    filtered_records = milvus_client.query(collection_name=os.environ.get(const.DOCS_COLLECTION),
                                           filter=f"{const.METADATA}['{const.FILE_NAME}'] == '{filename}'",
                                           output_fields=["pk"])
    for filtered_record in filtered_records:
        primary_keys.append(filtered_record["pk"])
    milvus_client.delete(collection_name=os.environ.get(const.DOCS_COLLECTION), filter=f"pk in {primary_keys}")
    return f"Successfully deleted {len(filtered_records)} records of {filename}"

def add_records(filename, file_content, milvus_client, embed):
    """
    Add records from file content to the collection.
    """
    chunked_docs = chunk_docs(filename, file_content, embed, update=True)
    milvus_client.insert(collection_name=os.environ.get(const.DOCS_COLLECTION), data=chunked_docs)
    return f"Successfully added {len(chunked_docs)} records from {filename}"

def process_changes(added, modified, deleted, milvus_client, embed):
    """
    Process changes (added, modified, deleted files) in the collection.
    """
    for filename, content in added:
        msg = add_records(filename, content, milvus_client, embed)
        logger.info(msg)
    for filename, content in modified:
        msg = delete_records(filename, milvus_client)
        logger.info(msg)
        msg = add_records(filename, content, milvus_client, embed)
        logger.info(msg)
    for filename in deleted:
        msg = delete_records(filename, milvus_client)
        logger.info(msg)

    logger.info(f"File operation summary: {len(added)} added, {len(modified)} modified, {len(deleted)} deleted")

def get_latest_release_data():
    """
    Get the latest release tag and assets from the repository.
    """
    url = f"https://api.github.com/repos/{os.environ.get(const.REPO_NAME)}/releases/latest"
    headers = {
        const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
        const.ACCEPT: "application/vnd.github.v3+json"
    }
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()

    release_data = response.json()
    return release_data["tag_name"], release_data.get("assets", [])

def download_and_extract(url, extract_path):
    """
    Download a file from a URL and extract it to the specified path.
    """
    headers = {
        const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
        const.ACCEPT: "application/octet-stream"
    }
    response = requests.get(url, headers=headers, stream=True, timeout=const.TIMEOUT)
    response.raise_for_status()

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name

        with zipfile.ZipFile(temp_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        logger.info(f"Extracted release to {extract_path}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.info(f"Removed temp zip file {temp_path}")

def create_formatted_file_path(path):
    """
    Convert a file path to a standardized format.
    """
    file_path = path.replace(os.path.sep, "/")
    file_path = file_path.replace("out-prod/", "en/")
    file_path = file_path.replace("/index.html", ".md")
    return file_path

def get_markdown(html):
    """
    Convert HTML content to markdown format.
    """
    soup = BeautifulSoup(html, "html.parser")
    content_inner = soup.find("article")
    if not content_inner:
        return None # No <article> tag found in the HTML content
    markdown = markdownify.markdownify(str(content_inner), heading_style="ATX")
    return markdown

def get_chunked_docs(asset, embed):
    """
    Download and process documents from a release asset.
    """
    chunked_docs = []
    logger.info(f"Downloading latest release from: {asset['browser_download_url']}")
    temp_dir = tempfile.mkdtemp()
    download_and_extract(asset["browser_download_url"], temp_dir)

    for root, _, files in os.walk(temp_dir):
        for file in files:
            if file.endswith(".html"):
                file_path = os.path.join(root, file)

                rel_path = os.path.relpath(file_path, temp_dir)
                if rel_path.replace(os.path.sep, "/") in os.environ.get(const.IGNORE_REL_PATHS, ()):
                    continue

                with open(file_path, "r", encoding="utf-8") as f:
                    html = f.read()
                    markdown = get_markdown(html)
                    if not markdown:
                        continue
                    filename = create_formatted_file_path(rel_path)
                    chunks = chunk_docs(filename, markdown, embed)
                    chunked_docs.extend(chunks)
    return chunked_docs

def hash_file(file_path):
    """
    Generate a SHA-256 hash of a file.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file:
        hasher.update(file.read())
    return hasher.hexdigest()

def get_release_assets(tag):
    """
    Get assets from a specific release tag.
    """
    url = f"https://api.github.com/repos/{os.environ.get(const.REPO_NAME)}/releases/tags/{tag}"
    headers = {const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
               const.ACCEPT: "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()

    return response.json().get("assets", [])

def compare_releases(last_updated_release_tag, latest_release_tag):
    """
    Compare two releases and identify added, modified, and deleted files.
    """
    logger.info(f"Comparing releases: {last_updated_release_tag} -> {latest_release_tag}")

    last_updated_release_assets = get_release_assets(last_updated_release_tag)
    latest_release_assets = get_release_assets(latest_release_tag)

    last_updated_release_zip_url = last_updated_release_assets[0]["browser_download_url"]
    latest_release_zip_url = latest_release_assets[0]["browser_download_url"]

    last_updated_release_extract_path = tempfile.mkdtemp()
    latest_release_extract_path = tempfile.mkdtemp()

    try:
        download_and_extract(last_updated_release_zip_url, last_updated_release_extract_path)
        download_and_extract(latest_release_zip_url, latest_release_extract_path)

        last_updated_release_files = {
            os.path.relpath(os.path.join(dp, f), last_updated_release_extract_path): hash_file(os.path.join(dp, f))
            for dp, _, filenames in os.walk(last_updated_release_extract_path)
            for f in filenames
            if f.endswith(".html") and f.replace(os.path.sep, "/") not in os.environ.get(const.IGNORE_REL_PATHS, ())
        }
        latest_release_files = {
            os.path.relpath(os.path.join(dp, f), latest_release_extract_path): hash_file(os.path.join(dp, f))
            for dp, _, filenames in os.walk(latest_release_extract_path)
            for f in filenames
            if f.endswith(".html") and f.replace(os.path.sep, "/") not in os.environ.get(const.IGNORE_REL_PATHS, ())
        }

        added, modified, deleted = [], [], []

        for f in latest_release_files:
            filename = create_formatted_file_path(f)

            if f not in last_updated_release_files:
                with open(os.path.join(latest_release_extract_path, f), "r", encoding="utf-8") as file:
                    html = file.read()
                    markdown = get_markdown(html)
                    if not markdown:
                        continue
                    added.append((filename, markdown))
            elif latest_release_files[f] != last_updated_release_files[f]:
                with open(os.path.join(latest_release_extract_path, f), "r", encoding="utf-8") as file:
                    html = file.read()
                    markdown = get_markdown(html)
                    if not markdown:
                        continue
                    modified.append((filename, markdown))

        for f in last_updated_release_files:
            filename = create_formatted_file_path(f)

            if f not in latest_release_files:
                deleted.append(filename)

        return added, modified, deleted

    # Remove temp extracted zip files after processing is complete
    # This is to free up space when running locally
    finally:
        shutil.rmtree(last_updated_release_extract_path)
        logger.info(f"Removed temp extracted zip file {last_updated_release_extract_path}")
        shutil.rmtree(latest_release_extract_path)
        logger.info(f"Removed temp extracted zip file {latest_release_extract_path}")

# ==============================
# Repository-based document processing functions
# ==============================

def retrieve_content(filename):
    """
    Retrieve the content of a file from the repository.
    """
    url = f"https://api.github.com/repos/{os.environ.get(const.REPO_NAME)}/contents/{filename}?ref={os.environ.get(const.BRANCH)}"
    headers = {const.AUTHORIZATION: f'token {os.environ.get(const.GITHUB_TOKEN)}',
               const.ACCEPT: 'application/vnd.github.v3.raw'}
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()
    if 'base64' in response.headers.get('Content-Encoding', ''):
        try:
            return base64.b64decode(response.content).decode('utf-8')
        except UnicodeDecodeError:
            logger.warning(f"UnicodeDecodeError occurred while decoding {response.content}")
            return ""
    return response.text

def load_md_files_from_repo():
    """
    Load all markdown files from the repository.
    """
    url = f"https://api.github.com/repos/{os.environ.get(const.REPO_NAME)}/git/trees/{os.environ.get(const.BRANCH)}?recursive=1"
    headers = {const.AUTHORIZATION: f'token {os.environ.get(const.GITHUB_TOKEN)}',
               const.ACCEPT: 'application/vnd.github.v3+json'}
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()
    file_names = [item[const.PATH] for item in response.json().get(const.TREE, [])
                  if item[const.PATH].endswith(const.MD_FORMAT) and os.environ.get(const.MAIN_DIR) in item[const.PATH] and
                  not any(ignore_file in item[const.PATH] for ignore_file in os.environ.get(const.IGNORE_FILES, []))]
    return file_names

def get_chunked_docs_from_repo(filenames, embed):
    """
    Get chunked documents from the repository.
    """
    chunked_docs = []
    for filename in filenames:
        content = retrieve_content(filename)
        chunks = chunk_docs(filename, content, embed)
        chunked_docs.extend(chunks)
    return chunked_docs

def get_latest_commit():
    """
    Get the latest commit SHA from the repository.
    """
    url = f"https://api.github.com/repos/{os.environ.get(const.REPO_NAME)}/branches/{os.environ.get(const.BRANCH)}"
    headers = {const.AUTHORIZATION: f'token {os.environ.get(const.GITHUB_TOKEN)}',
               const.ACCEPT: 'application/vnd.github.v3+json'}
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()
    return response.json()['commit']['sha']

def compare_commits(base_sha, head_sha):
    """
    Compare two commits and return the files that have changed.
    """
    url = f"https://api.github.com/repos/{os.environ.get(const.REPO_NAME)}/compare/{base_sha}...{head_sha}"
    headers = {const.AUTHORIZATION: f'token {os.environ.get(const.GITHUB_TOKEN)}',
               const.ACCEPT: 'application/vnd.github.v3+json'}
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()
    return list(response.json()['files'])

def get_diff_from_commits(files):
    """
    Get the diff between two commits.
    """
    added = []
    deleted = []
    for file in files:
        if any(ignore_file in file[const.FILE_NAME] for ignore_file in os.environ.get(const.IGNORE_FILES)):
            continue
        if os.environ.get(const.MAIN_DIR) in file[const.FILE_NAME] and file[const.FILE_NAME].endswith('.md'):
            if file['status'] in ['added', 'modified']:
                added.append(file[const.FILE_NAME])
            elif file['status'] == 'removed':
                deleted.append(file[const.FILE_NAME])
    return added, deleted

def process_repo_changes(added, deleted, milvus_client, embed):
    """
    Process changes in the repository.
    """
    for file in added:
        msg = delete_records(file, milvus_client)
        logger.info(msg)
        msg = add_repo_records(file, milvus_client, embed)
        logger.info(msg)
    for file in deleted:
        msg = delete_records(file, milvus_client)
        logger.info(msg)

def add_repo_records(filename, milvus_client, embed):
    """
    Add records from a repository file.
    """
    file_content = retrieve_content(filename)
    chunked_docs = chunk_docs(filename, file_content, embed, update=True)
    milvus_client.insert(collection_name=os.environ.get(const.DOCS_COLLECTION), data=chunked_docs)
    return f"Successfully added {len(chunked_docs)} records from {filename}"

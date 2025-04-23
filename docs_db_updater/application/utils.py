import os
import re
import zipfile
import shutil
import hashlib
import tempfile
import logging
import requests
from langchain.text_splitter import MarkdownHeaderTextSplitter
import markdownify
from bs4 import BeautifulSoup
from docs_db_updater.application import constants as const

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=const.headers_to_split_on)

def text_to_anchor(text):
    anchor = text.lower()
    anchor = anchor.replace(" ", "-")
    anchor = re.sub("[^0-9a-zA-Z-]", "", anchor)
    anchor = "#" + anchor
    return anchor

def create_formatted_chunk(chunk, file_name, doc_link, embed):
    formatted_chunk = {const.ASGARDEO_METADATA: {}}
    formatted_chunk[const.ASGARDEO_METADATA][const.FILE_NAME] = file_name
    formatted_chunk[const.ASGARDEO_METADATA][const.DOC_LINK] = doc_link
    if const.HEADER3 in chunk.metadata.keys():
        formatted_chunk[const.ASGARDEO_METADATA][const.HEADER3] = chunk.metadata[const.HEADER3]
    if const.HEADER2 in chunk.metadata.keys():
        formatted_chunk[const.ASGARDEO_METADATA][const.HEADER2] = chunk.metadata[const.HEADER2]
    if const.HEADER1 in chunk.metadata.keys():
        formatted_chunk[const.ASGARDEO_METADATA][const.HEADER1] = chunk.metadata[const.HEADER1]
    formatted_chunk[const.TEXT] = chunk.page_content
    formatted_chunk[const.VECTOR] = embed.embed_query(chunk.page_content)
    return formatted_chunk

def chunk_docs(file_name, file_content, embed, update=False):
    data = []
    chunked_doc = markdown_splitter.split_text(file_content)
    for chunk in chunked_doc:
        suffix = ""
        if const.HEADER3 in chunk.metadata.keys():
            suffix = text_to_anchor(chunk.metadata[const.HEADER3])
        elif const.HEADER2 in chunk.metadata.keys():
            suffix = text_to_anchor(chunk.metadata[const.HEADER2])
        doc_link = const.WEB_PATH+file_name[len(const.DOC_PATH):-3]+"/"+suffix
        chunk.metadata[const.FILE_NAME] = file_name
        chunk.metadata[const.DOC_LINK] = doc_link
        chunk.page_content = chunk.page_content.replace("../../", f"{const.WEB_PATH}")
        chunk.page_content = chunk.page_content.replace("../", f"{const.WEB_PATH}")
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
    primary_keys = []
    filtered_records = milvus_client.query(collection_name=os.environ.get(const.DOCS_COLLECTION),
                                           filter=f"{const.ASGARDEO_METADATA}['{const.FILE_NAME}'] == '{filename}'",
                                           output_fields=["pk"])
    for filtered_record in filtered_records:
        primary_keys.append(filtered_record["pk"])
    milvus_client.delete(collection_name=os.environ.get(const.DOCS_COLLECTION), filter=f"pk in {primary_keys}")
    return f"Successfully deleted {len(filtered_records)} records of {filename}"

def add_records(filename, file_content, milvus_client, embed):
    chunked_docs = chunk_docs(filename, file_content, embed, update=True)
    milvus_client.insert(collection_name=os.environ.get(const.DOCS_COLLECTION), data=chunked_docs)
    return f"Successfully added {len(chunked_docs)} records from {filename}"

def process_changes(added_modified, deleted, milvus_client, embed):
    for filename, content in added_modified:
        msg = delete_records(filename, milvus_client)
        logger.info(msg)
        msg = add_records(filename, content, milvus_client, embed)
        logger.info(msg)
    for filename in deleted:
        msg = delete_records(filename, milvus_client)
        logger.info(msg)

def get_latest_release_data():
    url = f"https://api.github.com/repos/{const.REPO_NAME}/releases/latest"
    headers = {
        const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
        const.ACCEPT: "application/vnd.github.v3+json"
    }
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()

    release_data = response.json()
    return release_data["tag_name"], release_data.get("assets", [])

def download_and_extract(url, extract_path):
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
    file_path = path.replace(os.path.sep, "/")
    file_path = file_path.replace("out-prod/", "en/")
    file_path = file_path.replace("/index.html", ".md")
    return file_path

def get_markdown(html):
    soup = BeautifulSoup(html, "html.parser")
    content_inner = soup.find("article")
    if not content_inner:
        return None # No <article> tag found in the HTML content
    markdown = markdownify.markdownify(str(content_inner), heading_style="ATX")
    return markdown

def get_chunked_docs(asset, embed):
    chunked_docs = []
    logger.info(f"Downloading latest release from: {asset['browser_download_url']}")
    temp_dir = tempfile.mkdtemp()
    download_and_extract(asset["browser_download_url"], temp_dir)

    for root, _, files in os.walk(temp_dir):
        for file in files:
            if file.endswith(".html"):
                file_path = os.path.join(root, file)

                rel_path = os.path.relpath(file_path, temp_dir)
                if rel_path.replace(os.path.sep, "/") in const.IGNORE_REL_PATHS:
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
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file:
        hasher.update(file.read())
    return hasher.hexdigest()

def get_release_assets(tag):
    url = f"https://api.github.com/repos/{const.REPO_NAME}/releases/tags/{tag}"
    headers = {const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
               const.ACCEPT: "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()
    
    return response.json().get("assets", [])

def compare_releases(last_updated_release_tag, latest_release_tag):
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
            if f.endswith(".html") and f.replace(os.path.sep, "/") not in const.IGNORE_REL_PATHS
        }
        latest_release_files = {
            os.path.relpath(os.path.join(dp, f), latest_release_extract_path): hash_file(os.path.join(dp, f))
            for dp, _, filenames in os.walk(latest_release_extract_path)
            for f in filenames
            if f.endswith(".html") and f.replace(os.path.sep, "/") not in const.IGNORE_REL_PATHS
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

        return added + modified, deleted
    
    # Remove temp extracted zip files after processing is complete
    # This is to free up space when running locally
    finally:
        shutil.rmtree(last_updated_release_extract_path)
        logger.info(f"Removed temp extracted zip file {last_updated_release_extract_path}")
        shutil.rmtree(latest_release_extract_path)
        logger.info(f"Removed temp extracted zip file {latest_release_extract_path}")

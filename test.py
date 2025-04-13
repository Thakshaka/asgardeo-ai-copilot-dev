# import markdownify

# def convert_html_file_to_markdown(input_file: str, output_file: str):
#     """
#     Converts an HTML file to Markdown and saves it to an output file.
#     :param input_file: The path to the input HTML file.
#     :param output_file: The path to save the converted Markdown file.
#     """
#     with open(input_file, 'r', encoding='utf-8') as html_file:
#         html_content = html_file.read()
        
#     markdown_content = markdownify.markdownify(html_content, heading_style="ATX")
    
#     with open(output_file, 'w', encoding='utf-8') as markdown_file:
#         markdown_file.write(markdown_content)

# if __name__ == "__main__":
#     input_html_file = "index.html"  # Replace with your HTML file path
#     output_markdown_file = "output.md"  # Replace with your desired Markdown file path
#     convert_html_file_to_markdown(input_html_file, output_markdown_file)
#     print(f"Conversion complete! Markdown saved to {output_markdown_file}")

# import os
# import markdownify

# def convert_html_to_markdown(input_folder: str, output_folder: str):
#     """
#     Recursively converts all HTML files in a folder to Markdown and maintains the folder structure.
#     :param input_folder: The root folder containing HTML files.
#     :param output_folder: The root folder where Markdown files will be saved.
#     """
#     for root, _, files in os.walk(input_folder):
#         # Create the corresponding output directory
#         relative_path = os.path.relpath(root, input_folder)
#         output_dir = os.path.join(output_folder, relative_path)
#         os.makedirs(output_dir, exist_ok=True)

#         for file in files:
#             if file.endswith(".html"):
#                 input_file_path = os.path.join(root, file)
#                 output_file_path = os.path.join(output_dir, file.replace(".html", ".md"))

#                 with open(input_file_path, "r", encoding="utf-8") as html_file:
#                     html_content = html_file.read()
                
#                 markdown_content = markdownify.markdownify(html_content, heading_style="ATX")
                
#                 with open(output_file_path, "w", encoding="utf-8") as markdown_file:
#                     markdown_file.write(markdown_content)

#                 print(f"Converted: {input_file_path} -> {output_file_path}")

# if __name__ == "__main__":
#     input_html_folder = "input_files"  # Replace with the path to your HTML folder
#     output_markdown_folder = "output_files"  # Replace with the desired output folder
#     convert_html_to_markdown(input_html_folder, output_markdown_folder)
#     print("Conversion complete!")

import os
import requests
import zipfile
import hashlib
import tempfile
import logging
import markdownify
from bs4 import BeautifulSoup
from docs_db_updater.application import constants as const
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            logger.info(f"Removed temp file {temp_path}")

def hash_file(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file:
        hasher.update(file.read())
    return hasher.hexdigest()

def get_latest_release_data():
    url = f"https://api.github.com/repos/{const.REPO_NAME}/releases/latest"
    headers = {const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
               const.ACCEPT: "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()

    release_data = response.json()
    return release_data["tag_name"], release_data.get("assets", [])

def compare_releases(last_updated_release_tag, latest_release_tag):
    last_updated_release_assets = get_release_assets(last_updated_release_tag)
    latest_release_assets = get_release_assets(latest_release_tag)
    
    last_updated_release_zip_url = last_updated_release_assets[0]["browser_download_url"]
    latest_release_zip_url = latest_release_assets[0]["browser_download_url"]
    
    last_updated_release_extract_path = tempfile.mkdtemp()
    latest_release_extract_path = tempfile.mkdtemp()
    
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
    
    added = []
    modified = []
    deleted = []
    
    # Compare files
    for f in latest_release_files:
        # Apply path modifications
        filename = f.replace(os.path.sep, "/")
        filename = filename.replace("out-prod/", "en/")
        filename = filename.replace("/index.html", ".md")

        if f not in last_updated_release_files:
            # New file added
            with open(os.path.join(latest_release_extract_path, f), "r", encoding="utf-8") as file:
                html = file.read()
                soup = BeautifulSoup(html, "html.parser")
                article = soup.find("article")
                if not article:
                    continue
                markdown = markdownify.markdownify(str(article), heading_style="ATX")
                # added.append((filename, markdown))
                added.append(filename)
        elif f in last_updated_release_files and latest_release_files[f] != last_updated_release_files[f]:
            # File modified
            with open(os.path.join(latest_release_extract_path, f), "r", encoding="utf-8") as file:
                html = file.read()
                soup = BeautifulSoup(html, "html.parser")
                article = soup.find("article")
                if not article:
                    continue
                markdown = markdownify.markdownify(str(article), heading_style="ATX")
                # modified.append((filename, markdown))
                modified.append(filename)
    
    # Check for deleted files
    for f in last_updated_release_files:
        filename = f.replace(os.path.sep, "/")
        filename = filename.replace("out-prod/", "en/")
        filename = filename.replace("/index.html", ".md")
        
        if f not in latest_release_files:
            deleted.append(filename)

    # return added + modified, deleted
    return {"added": added, "modified": modified, "deleted": deleted, "len_added": len(added), "len_modified": len(modified), "len_deleted": len(deleted)}

def get_release_assets(tag):
    url = f"https://api.github.com/repos/{const.REPO_NAME}/releases/tags/{tag}"
    headers = {const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
               const.ACCEPT: "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
    response.raise_for_status()
    
    return response.json().get("assets", [])

last_updated_release_tag = "v0.0.505-prod"
latest_release_tag, latest_release_assets = get_latest_release_data()
if latest_release_tag is not last_updated_release_tag and latest_release_assets[0]["name"].startswith("asgardeo-docs"):
    logger.info(f"Latest release tag: {latest_release_tag}")
    result = compare_releases(last_updated_release_tag, latest_release_tag)
    print(result)

# import os
# import requests
# import zipfile
# import tempfile
# import logging
# from dotenv import load_dotenv
# import markdownify
# from updater.application import constants as const

# load_dotenv()

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# def download_and_extract(url, extract_path):
#     headers = {
#         const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
#         const.ACCEPT: "application/octet-stream"
#     }
#     response = requests.get(url, headers=headers, stream=True, timeout=const.TIMEOUT)
#     response.raise_for_status()

#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
#             temp_file.write(response.content)
#             temp_path = temp_file.name

#         with zipfile.ZipFile(temp_path, "r") as zip_ref:
#             zip_ref.extractall(extract_path)
#         logger.info(f"Extracted release to {extract_path}")
#     finally:
#         if os.path.exists(temp_path):
#             os.remove(temp_path)
#             logger.info(f"Removed temp file {temp_path}")

# def get_latest_release_data():
#     url = f"https://api.github.com/repos/{const.REPO_NAME}/releases/latest"
#     headers = {
#         const.AUTHORIZATION: f'token {os.environ.get("GITHUB_TOKEN")}',
#         const.ACCEPT: "application/vnd.github.v3+json"
#     }
#     response = requests.get(url, headers=headers, timeout=const.TIMEOUT)
#     response.raise_for_status()

#     release_data = response.json()
#     return release_data["tag_name"], release_data.get("assets", [])

# def print_html_and_markdown_from_latest_release():
#     latest_tag, assets = get_latest_release_data()
#     asset = next((a for a in assets if a["name"].startswith("asgardeo-docs")), None)

#     if not asset:
#         print("No matching asset found in latest release.")
#         return

#     print(f"Downloading latest release from: {asset['browser_download_url']}")
#     temp_dir = tempfile.mkdtemp()
#     download_and_extract(asset["browser_download_url"], temp_dir)

#     for root, _, files in os.walk(temp_dir):
#         for file in files:
#             if file.endswith(".html"):
#                 file_path = os.path.join(root, file)
#                 with open(file_path, "r", encoding="utf-8") as f:
#                     html = f.read()
#                     markdown = markdownify.markdownify(html, heading_style="ATX")

#                     print("\n==========================")
#                     print("📄 File:", os.path.relpath(file_path, temp_dir))
#                     print("------ HTML Content ------")
#                     print(html)
#                     print("------ Markdown Content ------")
#                     print(markdown)

# if __name__ == "__main__":
#     print_html_and_markdown_from_latest_release()

# import os
# from langchain.text_splitter import MarkdownHeaderTextSplitter

# # Define the headers to split on (Header1, Header2, etc.)
# headers_to_split_on = [
#     ("#", "Header1"),
#     ("##", "Header2"),
#     # Uncomment the next line to include splitting by Header3
#     # ("###", "Header3"),
# ]

# # Create a MarkdownHeaderTextSplitter instance
# markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

# def convert_md_to_chunks(input_md_file, output_folder):
#     """
#     Convert a markdown file to chunks and save them as separate files in a folder.
    
#     :param input_md_file: The path to the input markdown file.
#     :param output_folder: The folder where chunk files will be saved.
#     """
#     # Ensure the output folder exists
#     os.makedirs(output_folder, exist_ok=True)
    
#     # Read the markdown file content
#     with open(input_md_file, 'r', encoding='utf-8') as f:
#         file_content = f.read()
    
#     # Split the content into chunks using markdown_splitter
#     chunked_docs = markdown_splitter.split_text(file_content)
    
#     # Save each chunk as a separate file
#     for i, chunk in enumerate(chunked_docs):
#         # Extract the text content from the Document object
#         chunk_text = chunk.page_content if hasattr(chunk, 'page_content') else str(chunk)
        
#         # Create a filename for the chunk (e.g., chunk_1.md, chunk_2.md, etc.)
#         chunk_filename = f"chunk_{i+1}.md"
#         chunk_filepath = os.path.join(output_folder, chunk_filename)
        
#         # Write the chunk to the corresponding file
#         with open(chunk_filepath, 'w', encoding='utf-8') as chunk_file:
#             chunk_file.write(chunk_text)
        
#         print(f"Saved chunk {i+1} to {chunk_filepath}")

# if __name__ == "__main__":
#     # Input markdown file path
#     input_md_file = "index.md"  # Replace with your actual markdown file path
    
#     # Output folder to save the chunk files
#     output_folder = "chunks_output"  # Replace with your desired folder path
    
#     # Convert the markdown file to chunks and save them
#     convert_md_to_chunks(input_md_file, output_folder)

"""
Main entry point for the docs_db_updater module.

This module updates the vector database with documentation content.
It supports two different document processing approaches:
1. Release-based: Downloads and processes HTML files from release assets
2. Repository-based: Directly loads and processes markdown files from the repository
"""

from docs_db_updater.application import collection_operator

if __name__ == '__main__':
    collection_operator.update_docs_db()

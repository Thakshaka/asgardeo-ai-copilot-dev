import base64
import logging
from typing import Optional, Any
from langchain_community.vectorstores import Milvus
from typing import List, Tuple
from langchain_core.documents import Document
import requests

OUTPUT_FIELDS = ["AsgardeoMetaData", "text", "pk"]

class MilvusProxy(Milvus):
    def __init__(self, embeddings, proxy_connection, collection_name, org_id, client_id, client_secret, token_endpoint):
        self.embedding_func = embeddings
        self.collection_name = collection_name
        self.proxy_connection = proxy_connection
        self.timeout: Optional[float] = 10000
        self.consistency_level: str = "Session"
        self.search_params: Optional[str] = ""
        self.drop_old: Optional[bool] = False
        self.auto_id: bool = False
        self.primary_field: str = "pk"
        self.text_field: str = "text"
        self.vector_field: str = "vector"
        self.replica_number: int = 1
        self.fields: list[str] = OUTPUT_FIELDS
        self.org_id = org_id

        self._embeddings = None
        self._vector_field = ''
        self._text_field = self.text_field
        self._metadata_field = None

        self.client_id = client_id
        self.client_secret = client_secret
        self.token_endpoint = token_endpoint

    @property
    def embeddings(self):
        return self._embeddings

    @embeddings.setter
    def embeddings(self, value):
        self._embeddings = value

    def similarity_search(
            self,
            query: str,
            k: int = 4,
            expr: Optional[str] = None,
            timeout: Optional[float] = None,
            **kwargs: Any,
    ) -> List[Document]:
        timeout = self.timeout or timeout
        embedding = self.embedding_func.embed_query(query)
        res = self.similarity_search_with_score_by_vector(
            embedding=embedding, k=k, expr=expr, timeout=timeout, **kwargs
        )
        return [doc for doc, _ in res]

    def similarity_search_with_score_by_vector(
            self,
            embedding: List[float],
            k: int = 4,
            param: Optional[dict] = None,
            expr: Optional[str] = None,
            timeout: Optional[float] = None,
            **kwargs: Any,
    ) -> List[Tuple[Document, float]]:
        # Determine result metadata fields with PK.
        output_fields = self.fields
        timeout = self.timeout or timeout
        client_id = self.client_id
        client_secret = self.client_secret
        token_endpoint = self.token_endpoint

        # get access token
        token_req_request_body = {
            'grant_type': 'client_credentials'
        }

        token_req_credentials = f"{client_id}:{client_secret}".encode('utf-8')
        token_req_encoded_credentials = base64.b64encode(token_req_credentials).decode('utf-8')

        token_req_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {token_req_encoded_credentials}'
        }

        try:
            response = requests.post(token_endpoint, data=token_req_request_body, headers=token_req_headers)
            response.raise_for_status()  # Raise an exception for non-2xx status codes
            data = response.json()
            access_token = f"Bearer {data['access_token']}"

        except requests.exceptions.RequestException as error:
            logging.exception(f"Failed to fetch access token: {error}")
            return []

        endpoint_url = f"{self.proxy_connection['uri']}/doc_search"
        headers = {'Authorization': access_token, "org-id": self.org_id}
        res = requests.post(endpoint_url,
                            headers=headers,
                            json={
                                "data": [embedding],
                                "anns_field": self._vector_field,
                                "limit": k,
                                "output_fields": output_fields,
                                "timeout": timeout,
                                "collection_name": self.collection_name
                            })

        ret = []
        for result in res.json()[0]:
            data = {x: result.get('entity').get(x) for x in output_fields}
            doc = self._parse_document(data)
            pair = (doc, result.get('distance'))
            ret.append(pair)

        return ret

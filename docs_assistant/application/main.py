import os
from contextlib import asynccontextmanager
from distutils.util import strtobool
import tiktoken
from langchain.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_cohere import CohereRerank
from fastapi import FastAPI
from fastapi.logger import logger
from langchain_openai import AzureChatOpenAI
from langchain_openai import AzureOpenAIEmbeddings
from docs_assistant.application.milvus_proxy import MilvusProxy
from langchain_community.vectorstores import Milvus
from docs_assistant.application import constants as const
from docs_assistant.application.service import router
from dotenv import load_dotenv

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    llm, encodings, db, reranker, reranked_retriever = None, None, None, None, None
    reranker_enabled = strtobool(os.environ.get(const.ENABLED_RERANKER, "False"))
    app.state.system_prompt = """You are a docbot that helps users understand more about Asgardeo product usage by answering
    their questions. Information from docs is provided to you to help you answer the questions. If the information from the
    docs is not relevant to your answer, do not use it to construct your answer. You do not have to use all the information
    in the docs to construct your answer. Do not make up your own answer. If you don't have enough information to answer,
    refuse politely to answer the question. Do not hallucinate! Some docs might be from the same file. You can verify this
    through the filename or the doc_link in the metadata. If the docs are from the same file, then you can use the step numbers
    to get an idea of the workflow.
    Asgardeo is an identity-as-a-service (IDaaS) platform that provides seamless and secure authentication and authorization
    solutions for applications. It offers features such as Single Sign-On (SSO), OAuth2, OpenID Connect, SAML, JWT authentication,
    role-based access control, and multi-factor authentication. Asgardeo enables users to configure identity providers, manage user roles,
    and define application-level access policies. It provides a developer-friendly interface for integrating identity management into applications
    and supports both low-code and custom configurations. Asgardeo also includes options for monitoring user activity, auditing, and customizing login flows.
    You must carefully identify which part of the docs corresponds to the user's question and provide a comprehensive answer.
    Be cautious not to mix steps or concepts from unrelated features. Construct your answer ACCURATELY! ALWAYS construct your answer
    with generic names for applications or services without using specific names like 'Employee Portal' (use the term 'your application' in this case).
    The information given contains markdown images, bullet-points, and tables, etc. You can make use of them by adding them to the response
    in markdown format. Make sure answers are structured enough to follow through and descriptive. In your answer, always give the links to the most
    relevant doc from which you got the answer. You can use the doc_link metadata in the docs you are provided. Do not give fake links of your own.
    Do not always ask the user to refer to the docs. Give a comprehensive answer to how to do it or what it is before you direct the user to the docs with the links.
    The answer you give is very critical. Asgardeo may not support all types of applications or configurations, and users might ask about unsupported scenarios.
    If you do not have enough information from the docs, refuse to answer politely. Do not include steps to sign in to Asgardeo.
    Users are already signed in while asking you this question, so you don't have to direct them to Asgardeo again.
    You can use the question's context to understand more about the user's question."""

    app.state.user_prompt_template = """User's Question: %s
    Question's context: %s
    Information from docs:%s"""
    try:
        llm = AzureChatOpenAI(
            azure_deployment=os.environ.get(const.AZURE_DEPLOYMENT_CHAT, const.DEFAULT_AZURE_DEPLOYMENT_CHAT),
            openai_api_version=os.environ.get(const.OPENAI_API_VERSION, const.DEFAULT_OPENAI_API_VERSION),
            azure_endpoint=os.environ.get(const.AZURE_OPENAI_ENDPOINT)
        )
        encodings = tiktoken.encoding_for_model(const.GPT_MODEL_NAME)
        logger.info("Creating LLM instance")
        embeddings = AzureOpenAIEmbeddings(
            azure_deployment=os.environ.get(const.AZURE_DEPLOYMENT_EMBEDDING, const.DEFAULT_AZURE_DEPLOYMENT_EMBEDDING),
            openai_api_version=os.environ.get(const.OPENAI_API_VERSION, const.DEFAULT_OPENAI_API_VERSION),
            azure_endpoint=os.environ.get(const.CP_AZURE_OPENAI_ENDPOINT),
            openai_api_key=os.environ.get(const.CP_AZURE_OPENAI_API_KEY)
        )

        # db = MilvusProxy(
        #     embeddings=embeddings,
        #     proxy_connection={
        #         "uri": os.getenv(const.PROXY_URL),
        #         "token": os.getenv(const.PROXY_TOKEN),
        #     },
        #     collection_name=os.environ.get(const.COLLECTION_NAME),
        #     org_id=os.getenv('ORGANIZATION_ID'),
        #     client_id=os.getenv('PROXY_CONSUMER_KEY'),
        #     client_secret=os.getenv('PROXY_CONSUMER_SECRET'),
        #     token_endpoint=os.getenv('ASGARDEO_TOKEN_ENDPOINT')
        # )
        db = Milvus(
            collection_name=os.environ.get(const.DOCS_COLLECTION),
            embedding_function=embeddings,
            connection_args={
                "uri": os.environ.get(const.ZILLIZ_CLOUD_URI),
                "token": os.environ.get(const.ZILLIZ_CLOUD_API_KEY),
                "secure": True,
            },
        )
        if reranker_enabled:
            reranker = CohereRerank(cohere_api_key=os.environ.get(const.COHERE_API_KEY),
                                    model=const.COHERE_MODEL, top_n=const.TOP_DOCS)
            retriever = db.as_retriever(search_kwargs={"k": const.K_NEIGHBOURS})
            reranked_retriever = ContextualCompressionRetriever(base_compressor=reranker, base_retriever=retriever)
        logger.info("Creating DB instance")
    finally:
        if not llm:
            raise Exception("Failed to create llm instance")
        app.state.llm = llm
        if not encodings:
            raise Exception("Invalid model name")
        app.state.encodings = encodings
        if not db:
            raise Exception("Failed to create db instance")
        app.state.db = db
        if reranker_enabled:
            if not reranker:
                raise Exception("Failed to create reranker instance")
            if not reranked_retriever:
                raise Exception("Failed to instantiate reranked retriever")
            app.state.reranked_retriever = reranked_retriever
    yield

app = FastAPI(title="Docs Assistant", version="0.1.0", lifespan=lifespan)
app.include_router(router, tags=["docs-assistant"])

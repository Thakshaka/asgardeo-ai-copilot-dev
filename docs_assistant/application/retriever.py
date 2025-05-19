import asyncio
import os
import re
import logging
from distutils.util import strtobool
from fastapi import HTTPException
from docs_assistant.application import constants as const

logger = logging.getLogger(__name__)

async def get_docs(state, questions, count, x_request_id):
    db = state.db
    k = count
    if count == 0:
        k = const.K_NEIGHBOURS
    tasks = []
    reranker_enabled = strtobool(os.environ.get(const.ENABLED_RERANKER, "False"))
    try:
        if reranker_enabled:
            reranked_retriever = state.reranked_retriever
            for question in questions:
                tasks.append(reranked_retriever.ainvoke(question))
        else:
            for question in questions:
                tasks.append(db.asimilarity_search(question, k=k))
        results = await asyncio.gather(*tasks)
        results = [item for sublist in results for item in sublist]
        return results
    except Exception as e:
        logger.error(f"Error while retrieving the docs: {e}, id = {x_request_id}")
        return []

async def get_chat_prompt(state, questions, count, x_request_id, question_context):
    user_prompt_template = state.user_prompt_template
    encodings = state.encodings
    cleaned_questions = [re.sub(r"in asgardeo", "", question, flags=re.IGNORECASE) for question in questions]
    results = await get_docs(state, cleaned_questions, count, x_request_id)

    docs_content = ""
    if len(results) == 0:
        docs_content = "No docs found for the question"
    else:
        for result in results:
            doc_content = f"Document: {{content: {result.page_content}, metadata:{result.metadata}}}\n"
            if len(encodings.encode(docs_content + doc_content)) > const.MAX_PROMPT_SIZE:
                break
            docs_content += doc_content

    user_prompt = user_prompt_template % (str(cleaned_questions), str(question_context), docs_content.strip())

    return user_prompt

async def bulk_response(state, questions, x_request_id, question_context):
    llm, encodings = state.llm, state.encodings
    system_prompt = state.system_prompt
    user_prompt = await get_chat_prompt(state, questions, 0, x_request_id, question_context)
    prompt_tokens = len(encodings.encode(system_prompt)) + len(encodings.encode(user_prompt))
    try:
        response = await llm.ainvoke([
            {"role": const.SYSTEM, "content": system_prompt},
            {"role": const.USER, "content": user_prompt}
        ])
        answer = response.content
    except Exception as e:
        logger.error(f"Error while generating llm response: {e}, id = {x_request_id}")
        answer = "Error while processing your request. Please try again later"
        raise HTTPException(status_code=500, detail=answer)
    completion_tokens = len(encodings.encode(answer))
    output_schema = {
        "content": answer,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }}
    return output_schema

async def stream_response(state, questions, x_request_id, question_context):
    llm = state.llm
    system_prompt = state.system_prompt
    user_prompt = await get_chat_prompt(state, questions, 0, x_request_id, question_context)
    try:
        async for chunk in llm.astream([
            {"role": const.SYSTEM, "content": system_prompt},
            {"role": const.USER, "content": user_prompt}
        ]):
            yield chunk.content
    except Exception as e:
        logger.error(f"Error while generating llm response: {e}, id = {x_request_id}")
        answer = "Error while processing your request. Please try again later"
        raise HTTPException(status_code=500, detail=answer)

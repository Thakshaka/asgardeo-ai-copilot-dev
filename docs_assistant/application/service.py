from typing import List, Optional, Union
from fastapi import Request, APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from docs_assistant.application import retriever
from docs_assistant.application import health_check

router = APIRouter(tags=["docs-assistant"])

class ChatRequest(BaseModel):
    questions: Union[List[str], str]
    question_context: Optional[str] = None


def validate_inputs(questions: Union[List[str], str], question_context: Optional[str]):
    if not questions:
        raise HTTPException(status_code=400, detail="'questions' parameter must be provided and not be empty")
    if isinstance(questions, str):
        questions = [questions]
    if not question_context and questions:
        question_context = questions[0]

    return questions, question_context

@router.post('/docs-assistant/stream')
async def stream(request: Request, body: ChatRequest, x_request_id: Optional[str] = Header(None)):
    questions, question_context = validate_inputs(body.questions, body.question_context)
    if not x_request_id:
        x_request_id = ""
    response_stream = retriever.stream_response(request.app.state, questions, x_request_id, question_context)
    return StreamingResponse(response_stream, media_type='text/event-stream')

@router.post('/docs-assistant/chat')
async def chat(request: Request, body: ChatRequest, x_request_id: Optional[str] = Header(None)):
    questions, question_context = validate_inputs(body.questions, body.question_context)
    if not x_request_id:
        x_request_id = ""
    response = await retriever.bulk_response(request.app.state, questions, x_request_id, question_context)
    return JSONResponse(response)

@router.get('/docs-assistant/docs')
async def get_documents(request: Request, question: str, count: Optional[int] = 0,
                        x_request_id: Optional[str] = Header(None)):
    if not question:
        raise HTTPException(status_code=400, detail="'question' parameter must be provided")
    if not x_request_id:
        x_request_id = ""
    response = await retriever.get_docs(request.app.state, [question], count, x_request_id)
    return {"docs": response}

@router.get('/liveness')
def check_liveness():
    return health_check.run_health_check()

@router.get('/readiness')
def check_readiness():
    return health_check.run_health_check()

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from RAG.retrieval import create_retrieval_resources, find_suitable_documents, normalize_retrieval_response
from RAG.acces_controll import adaptive_threshold_filter, filter_documents_by_permissions


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    index, model = create_retrieval_resources()
    app.state.index = index
    app.state.model = model
    yield


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    chat: str


TEST_USER_PREMISSIONS = ["finance"]


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest):

    chat = payload.chat

    retrieval_response = find_suitable_documents(
        app.state.index,
        app.state.model,
        chat,
    )

    matches = normalize_retrieval_response(retrieval_response)
    relevant_matches = adaptive_threshold_filter(matches)
    allowed_matches = filter_documents_by_permissions(relevant_matches, TEST_USER_PREMISSIONS)



    return {
        "Success": "Ok boss",
    }

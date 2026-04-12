import asyncio
import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel, Field

from API.auth import create_access_token, get_current_user, hash_password, verify_password
from DB.db import Db
from LLM.llm import chat_with_model, create_llm_resources, generate_chat_name, preprocess_rag_data
from RAG.acces_controll import adaptive_threshold_filter, filter_documents_by_permissions
from RAG.retrieval import find_suitable_documents, normalize_retrieval_response
from RAG.upsert import create_upsert_resources, upsert_all_documents_from_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    app.state.db = Db(init_schema_on_start=False)
    index, model = create_upsert_resources()
    app.state.index = index
    app.state.model = model
    app.state.llm_resources = create_llm_resources()
    yield
    app.state.db.close()


app = FastAPI(lifespan=lifespan)
K_LATEST_MESSAGES = 10

_CHAT_ML_LOCK = threading.Lock()#lock for embedding inside LLM step to prevent race conditions

def _chat_rag_and_llm_sync(
    index: object,
    embed_model: object,
    llm_resources: dict | None,
    user_question: str,
    previous_messages: list[dict[str, str]],
    groups: list[str],
    should_generate_name: bool,
) -> dict:
    retrieval_response = find_suitable_documents(
        index,
        embed_model,
        user_question,
        encode_lock=_CHAT_ML_LOCK,
    )

    matches = normalize_retrieval_response(retrieval_response)
    relevant_matches = adaptive_threshold_filter(matches)
    allowed_matches, groups_to_contact = filter_documents_by_permissions(
        relevant_matches, groups
    )

    relevant_matches_len = len(relevant_matches)
    num_not_allowed = relevant_matches_len - len(allowed_matches)

    llm_succeeded = False
    chat_name: str | None = None
    llm_mode = (llm_resources or {}).get("llm_mode")

    if relevant_matches_len > 0 and num_not_allowed == relevant_matches_len:
        user_message_with_context = user_question
        if groups_to_contact:
            llm_response = (
                "V indeksu so na voljo relevantni dokumenti, vaš račun pa do njih nima dostopa. "
                "Obrnite se na skrbnika ali člane teh skupin: "
                + ", ".join(groups_to_contact)
                + "."
            )
        else:
            llm_response = (
                "Obstajajo ujemanja z dokumenti, vendar vaš račun nima dostopa; "
                "iz metapodatkov ni bilo mogoče določiti kontaktnih skupin."
            )
    else:
        messages = preprocess_rag_data(
            question=user_question,
            allowed_matches=allowed_matches,
            previous_messages=previous_messages,
        )
        user_message_with_context = messages[-1]["content"]

        try:
            if llm_mode == "local":
                with _CHAT_ML_LOCK:
                    llm_response = chat_with_model(llm_resources, messages)
            else:
                llm_response = chat_with_model(llm_resources, messages)
            llm_succeeded = True
        except RuntimeError as exc:
            if llm_mode == "api":
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Napaka ponudnika LLM: {exc}",
                ) from exc
            raise

        if should_generate_name and llm_succeeded:
            if llm_mode == "local":
                with _CHAT_ML_LOCK:
                    chat_name = generate_chat_name(llm_resources, prompt=user_question)
            else:
                chat_name = generate_chat_name(llm_resources, prompt=user_question)

    return {
        "user_message_with_context": user_message_with_context,
        "llm_response": llm_response,
        "llm_succeeded": llm_succeeded,
        "allowed_matches": allowed_matches,
        "groups_to_contact": groups_to_contact,
        "num_not_allowed": num_not_allowed,
        "chat_name": chat_name,
    }


class ChatRequest(BaseModel):
    chat_id: int
    chat: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str

@app.get("/schema/init")
async def schema_init_endpoint():
    app.state.db.init_schema()
    return {"status": "ok", "message": "Schema initialized."}


@app.get("/schema/restart")
async def schema_restart_endpoint():
    app.state.db.reset_schema()
    return {"status": "ok", "message": "Schema restarted (wiped and re-initialized)."}


@app.get("/schema/seed")
async def seed_endpoint():
    summary = app.state.db.seed(password_hash=hash_password("testing"))
    return {"status": "ok", "message": "Seed data inserted.", "summary": summary}


@app.post("/index/clear")
async def clear_index_endpoint():
    try:
        app.state.index.delete(delete_all=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear index: {exc}",
        ) from exc

    return {"status": "ok", "message": "Index cleared."}


@app.get("/upsert/all")
async def upsert_all_endpoint():
    summary = upsert_all_documents_from_db(
        db=app.state.db,
        index=app.state.index,
        model=app.state.model,
    )
    return {"status": "ok", "summary": summary}


@app.post("/auth/register")
async def register_endpoint(payload: RegisterRequest):
    password_hash = hash_password(payload.password)

    try:
        user_id = app.state.db.create_user(payload.username, password_hash)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
        ) from exc

    return {
        "id": user_id,
        "name": payload.username,
    }


@app.post("/auth/login")
async def login_endpoint(payload: LoginRequest):
    user = app.state.db.get_user_for_login(payload.username)

    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    access_token, expires_in = create_access_token(user["id"])

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
    }


@app.post("/auth/logout")
async def logout_endpoint(current_user: dict = Depends(get_current_user)):
    app.state.db.revoke_token(current_user["token_jti"], current_user["token_exp"])

    return {"status": "ok", "message": "Logged out."}


@app.get("/auth/me")
async def me_endpoint(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "groups": current_user["groups"],
    }

@app.get("/chat/list")
async def list_chats_endpoint(current_user: dict = Depends(get_current_user)):
    chats = app.state.db.list_user_chats(current_user["id"])
    return {
        "status": "ok",
        "chats": chats,
    }


@app.post("/chat/create")
async def create_chat_endpoint(current_user: dict = Depends(get_current_user)):
    chat_id = app.state.db.create_chat(current_user["id"])
    return {
        "status": "ok",
        "chat_id": chat_id,
    }


@app.delete("/chat/delete/{chat_id}")
async def delete_chat_endpoint(chat_id: int, current_user: dict = Depends(get_current_user)):
    deletion_status = app.state.db.delete_chat_for_user(chat_id=chat_id, user_id=current_user["id"])

    if deletion_status == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat with id {chat_id} not found.",
        )

    if deletion_status == "forbidden":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chat does not belong to current user.",
        )

    return {
        "status": "ok",
        "message": f"Chat {chat_id} deleted.",
    }


@app.get("/chat/get/{chat_id}")
async def get_chat_endpoint(chat_id: int, current_user: dict = Depends(get_current_user)):
    result = app.state.db.get_chat_for_user(chat_id=chat_id, user_id=current_user["id"])
    if result["status"] == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat with id {chat_id} not found.",
        )
    if result["status"] == "forbidden":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chat does not belong to current user.",
        )
    return {"status": "ok", "chat": result["chat"]}


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    chat_meta = app.state.db.get_chat_meta(payload.chat_id)
    if chat_meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat with id {payload.chat_id} not found.",
        )
    if chat_meta["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chat does not belong to current user.",
        )

    previous_messages = app.state.db.fetch_latest_chat_messages(payload.chat_id, K_LATEST_MESSAGES)
    should_generate_name = chat_meta.get("name") is None and len(previous_messages) == 0

    worker = await asyncio.to_thread(
        _chat_rag_and_llm_sync,
        app.state.index,
        app.state.model,
        app.state.llm_resources,
        payload.chat,
        previous_messages,
        current_user["groups"],
        should_generate_name,
    )

    user_message_with_context = worker["user_message_with_context"]
    llm_response = worker["llm_response"]
    llm_succeeded = worker["llm_succeeded"]
    allowed_matches = worker["allowed_matches"]
    groups_to_contact = worker["groups_to_contact"]
    num_not_allowed = worker["num_not_allowed"]
    chat_name = worker["chat_name"]

    app.state.db.insert_chat_message(payload.chat_id, "user", user_message_with_context)
    assistant_message_id = app.state.db.insert_chat_message(payload.chat_id, "assistant", llm_response)
    allowed_document_ids = app.state.db.extract_unique_allowed_document_ids(allowed_matches)
    app.state.db.insert_chat_message_documents(assistant_message_id, allowed_document_ids)

    if chat_name:
        app.state.db.set_chat_name(payload.chat_id, chat_name)

    return {
        "status": "ok",
        "chat_id": payload.chat_id,
        "user": {
            "id": current_user["id"],
            "name": current_user["name"],
            "groups": current_user["groups"],
        },
        "allowed_matches": allowed_matches,
        "response": llm_response,
        "num_docs_not_allowed": num_not_allowed,
        "groups_to_contact": groups_to_contact,
    }


@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/ui/", status_code=302)


_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")

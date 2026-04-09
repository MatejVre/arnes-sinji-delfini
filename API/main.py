import sqlite3
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from API.auth import create_access_token, get_current_user, hash_password, verify_password
from DB.db import Db
from RAG.acces_controll import adaptive_threshold_filter, filter_documents_by_permissions
from RAG.retrieval import (
    create_retrieval_resources,
    find_suitable_documents,
    normalize_retrieval_response,
)
from RAG.upsert import upsert_all_documents_from_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    app.state.db = Db(init_schema_on_start=False)
    index, model = create_retrieval_resources()
    app.state.index = index
    app.state.model = model
    yield
    app.state.db.close()


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
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


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    retrieval_response = find_suitable_documents(
        app.state.index,
        app.state.model,
        payload.chat,
    )

    matches = normalize_retrieval_response(retrieval_response)
    relevant_matches = adaptive_threshold_filter(matches)
    allowed_matches = filter_documents_by_permissions(relevant_matches, current_user["groups"])

    # pass this to LLM
    



    return {
        "status": "ok",
        "user": {
            "id": current_user["id"],
            "name": current_user["name"],
            "groups": current_user["groups"],
        },
        "allowed_matches": allowed_matches,
    }

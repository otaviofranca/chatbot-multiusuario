"""API do chatbot multiusuário (FastAPI)."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .llm import LLMError, get_provider
from .sessions import SessionStore

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

store = SessionStore(
    ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "1800")),
    max_history=int(os.getenv("MAX_HISTORY_MESSAGES", "20")),
)
provider = None


async def _cleanup_loop():
    while True:
        await asyncio.sleep(60)
        store.cleanup_expired()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global provider
    provider = get_provider()
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(
    title="Chatbot Multiusuário",
    description="Protótipo 1 – TPCA (Equipe D). Sessões isoladas por ID único.",
    version="1.0.0",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    messages_in_session: int


@app.get("/health")
def health():
    return {"status": "ok", "model": provider.model, "active_sessions": len(store)}


@app.post("/sessions", status_code=201)
def create_session():
    """Gera um ID único para o cliente que acabou de se conectar."""
    session = store.create()
    return {"session_id": session.id}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session = store.get(req.session_id)
    if session is None:
        raise HTTPException(404, "Sessão não encontrada ou expirada. Crie uma nova em POST /sessions.")

    # Lock apenas da própria sessão: usuários diferentes são atendidos em paralelo.
    async with session.lock:
        session.history.append({"role": "user", "text": req.message})
        try:
            answer = await provider.reply(list(session.history))
        except LLMError as exc:
            session.history.pop()  # não deixa pergunta sem resposta no histórico
            raise HTTPException(502, str(exc))
        session.history.append({"role": "model", "text": answer})
        store.trim(session)
        return ChatResponse(
            session_id=session.id, reply=answer, messages_in_session=len(session.history)
        )


@app.get("/sessions/{session_id}/history")
def get_history(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(404, "Sessão não encontrada ou expirada.")
    return {"session_id": session.id, "history": session.history}


@app.delete("/sessions/{session_id}", status_code=204)
def end_session(session_id: str):
    if not store.delete(session_id):
        raise HTTPException(404, "Sessão não encontrada.")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

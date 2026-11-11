import os
os.environ["LLM_PROVIDER"] = "mock"

import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app


def test_sessoes_isoladas():
    with TestClient(app) as c:
        a = c.post("/sessions").json()["session_id"]
        b = c.post("/sessions").json()["session_id"]
        assert a != b
        c.post("/chat", json={"session_id": a, "message": "oi A"})
        c.post("/chat", json={"session_id": a, "message": "outra A"})
        rb = c.post("/chat", json={"session_id": b, "message": "oi B"}).json()
        assert rb["messages_in_session"] == 2           # B só tem a própria conversa
        hist_a = c.get(f"/sessions/{a}/history").json()["history"]
        assert len(hist_a) == 4 and all("B" not in m["text"].split()[-1] for m in hist_a if m["role"] == "user")


def test_sessao_inexistente_e_encerramento():
    with TestClient(app) as c:
        assert c.post("/chat", json={"session_id": "x", "message": "oi"}).status_code == 404
        sid = c.post("/sessions").json()["session_id"]
        assert c.delete(f"/sessions/{sid}").status_code == 204
        assert c.get(f"/sessions/{sid}/history").status_code == 404


def test_validacao():
    with TestClient(app) as c:
        sid = c.post("/sessions").json()["session_id"]
        assert c.post("/chat", json={"session_id": sid, "message": ""}).status_code == 422


@pytest.mark.asyncio
async def test_concorrencia_50_usuarios():
    from asgi_lifespan import LifespanManager
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            async def usuario(i):
                sid = (await c.post("/sessions")).json()["session_id"]
                r = (await c.post("/chat", json={"session_id": sid, "message": f"pergunta {i}"})).json()
                return i, r["reply"]
            res = await asyncio.gather(*(usuario(i) for i in range(50)))
            for i, reply in res:
                assert f"pergunta {i}'" in reply   # cada resposta volta ao usuário certo

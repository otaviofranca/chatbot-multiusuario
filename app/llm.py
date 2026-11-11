"""Camada de acesso ao LLM. Provedores: 'gemini' (real) e 'mock' (testes/demonstração offline)."""
import asyncio
import os

SYSTEM_PROMPT = (
    "Você é um assistente prestativo e objetivo. Responda sempre no idioma do usuário "
    "(por padrão, português do Brasil), de forma clara e concisa."
)


class LLMError(Exception):
    pass


class GeminiProvider:
    def __init__(self):
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise LLMError("GEMINI_API_KEY não definida.")
        self._types = types
        self._client = genai.Client(api_key=api_key)
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    async def reply(self, history: list[dict]) -> str:
        """history já inclui a última mensagem do usuário."""
        types = self._types
        contents = [
            types.Content(role=m["role"], parts=[types.Part.from_text(text=m["text"])])
            for m in history
        ]
        try:
            resp = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT, temperature=0.7
                    ),
                ),
                timeout=60,
            )
        except Exception as exc:  # erros de rede/cota/etc.
            raise LLMError(f"Falha ao consultar o modelo: {exc}") from exc
        text = (resp.text or "").strip()
        if not text:
            raise LLMError("O modelo não retornou texto (possível bloqueio de segurança).")
        return text


class MockProvider:
    """Responde ecoando a pergunta e o tamanho do histórico — útil p/ testar isolamento de sessões."""

    model = "mock"

    async def reply(self, history: list[dict]) -> str:
        await asyncio.sleep(0.2)  # simula latência para exercitar concorrência
        user_msgs = [m["text"] for m in history if m["role"] == "user"]
        return f"[mock] Você disse: '{user_msgs[-1]}'. Mensagens suas nesta sessão: {len(user_msgs)}."


def get_provider():
    name = os.getenv("LLM_PROVIDER", "gemini").lower()
    if name == "mock":
        return MockProvider()
    if name == "gemini":
        return GeminiProvider()
    raise LLMError(f"Provedor desconhecido: {name}")

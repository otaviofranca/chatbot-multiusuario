# Chatbot Multiusuário — Protótipo 1 (TPCA, Equipe D)

Equipe: João Pedro Monteiro da Silva Barros · Lucas Herlon dos Santos Moreira Cunha · Otávio da Conceição França · Francielio Evangelista dos Santos Castro

Chatbot simplificado em que vários usuários conversam ao mesmo tempo com um LLM, cada um com **sessão e histórico isolados**.

## Decisões técnicas (justificativa)
| Escolha | Por quê |
|---|---|
| **FastAPI + uvicorn** (Python) | Assíncrono nativo (`async/await`): uma chamada lenta ao LLM de um usuário não bloqueia os demais. Gera documentação Swagger automática em `/docs`. |
| **Google Gemini (`gemini-2.5-flash`) via `google-genai`** | Camada gratuita para estudantes, baixa latência, bom desempenho em português e SDK oficial com cliente assíncrono. Modelo configurável por variável de ambiente. |
| **Vanilla Python (sem LangChain)** | O histórico é uma lista simples enviada a cada chamada; para um chatbot de turnos não há necessidade de uma camada extra de abstração. Menos dependências, código mais claro. |
| **Sessões em memória** | O enunciado aceita histórico efêmero. Cada sessão tem UUID, histórico próprio, TTL de inatividade (30 min) e limite de mensagens. |

## Como o requisito de sessões é atendido
- `POST /sessions` gera um **UUID** no momento da conexão do cliente.
- Cada `Session` guarda o próprio histórico; o `/chat` só lê/escreve na sessão do `session_id` informado → a resposta sempre volta ao usuário correto.
- Um `asyncio.Lock` **por sessão** evita que duas mensagens simultâneas do mesmo usuário embaralhem o histórico, sem bloquear outros usuários.
- Sessões inativas expiram (`SESSION_TTL_SECONDS`) e são removidas por uma tarefa em segundo plano.
- Limitação conhecida: com memória local, usar vários workers/instâncias exigiria um store compartilhado (ex.: Redis). Rodamos 1 processo assíncrono, que atende a concorrência pedida.

## Rodar localmente
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # edite e coloque sua GEMINI_API_KEY (https://aistudio.google.com/apikey)
set -a; source .env; set +a
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Abra `http://localhost:8000` (interface web) ou `http://localhost:8000/docs` (Swagger).
Sem chave? Use `LLM_PROVIDER=mock` para testar o fluxo sem LLM.

## Documentação da API
Base URL: `http://<IP_PUBLICO_DA_EC2>` (ou `:8000` localmente)

| Método | Rota | Descrição |
|---|---|---|
| POST | `/sessions` | Cria sessão → `201 {"session_id": "..."}` |
| POST | `/chat` | Envia pergunta → `{"session_id","reply","messages_in_session"}` |
| GET | `/sessions/{id}/history` | Histórico da sessão |
| DELETE | `/sessions/{id}` | Encerra a sessão (`204`) |
| GET | `/health` | Status, modelo e nº de sessões ativas |

Erros: `404` sessão inexistente/expirada · `422` mensagem vazia ou > 4000 caracteres · `502` falha do LLM.

Exemplo:
```bash
SID=$(curl -s -X POST http://HOST/sessions | python3 -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s -X POST http://HOST/chat -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"message\":\"Quem descobriu o Brasil?\"}"
curl -s -X POST http://HOST/chat -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"message\":\"E em que ano foi isso?\"}"   # usa o contexto anterior
```

## Testes
```bash
pip install pytest pytest-asyncio asgi-lifespan httpx
python -m pytest -q
```
Cobrem isolamento entre sessões, sessão inexistente, validação e **50 usuários simultâneos** (cada resposta volta ao usuário certo).

## Deploy na AWS EC2 (ponto extra)
1. Console AWS → EC2 → *Launch instance*: **Ubuntu 24.04**, tipo `t3.micro`/`t2.micro`, crie/baixe o par de chaves `.pem`.
2. **Security Group**: entrada TCP **22** (seu IP), **80** (0.0.0.0/0).
3. Conecte e instale:
```bash
ssh -i chave.pem ubuntu@<IP_PUBLICO>
sudo apt update && sudo apt install -y python3-venv git
git clone https://github.com/<usuario>/<repo>.git chatbot-multiusuario && cd chatbot-multiusuario
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env      # coloque a GEMINI_API_KEY
```
4. Serviço que sobe sozinho e reinicia em falha:
```bash
sudo cp deploy/chatbot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now chatbot
sudo systemctl status chatbot          # logs: journalctl -u chatbot -f
```
5. Acesse `http://<IP_PUBLICO>` e `http://<IP_PUBLICO>/docs`.
   Dica: associe um **Elastic IP** para o endereço não mudar entre reinícios da instância.

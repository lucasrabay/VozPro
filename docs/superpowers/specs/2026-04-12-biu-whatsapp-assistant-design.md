# Biu — Assistente de Emprego via WhatsApp — Design

**Data:** 2026-04-12
**Autor:** Miguel Queiroz (brainstorming com Claude)
**Status:** Aprovado para implementação

## Visão geral

Biu é um assistente que conversa por **áudio no WhatsApp** com pessoas de baixo letramento para (1) montar o currículo profissional da pessoa e (2) sugerir vagas reais compatíveis. O sistema é um pipeline: mensagem chega pelo WhatsApp → STT + LLM respondem → TTS gera áudio → PDF do currículo é gerado quando a conversa chega ao fim → tudo volta pelo WhatsApp.

Público-alvo: trabalhadores brasileiros desempregados, frequentemente com dificuldade de letramento. Linguagem PT-BR, tom acolhedor, frases curtas.

## Decisões de arquitetura (congeladas)

| # | Decisão | Escolha |
|---|---|---|
| 1 | Linguagens | Híbrido Node (gateway WhatsApp) + Python (brain) |
| 2 | Estado da conversa | Histórico completo em SQLite, LLM conduz o fluxo |
| 3 | STT | Áudio direto pro Gemini 3 Flash (multimodal, uma chamada) |
| 4 | Sugestão de vagas | Gemini com Grounding (Google Search) |
| 5 | PDF | Jinja2 + WeasyPrint, template Harvard |
| 6 | Deploy | Docker Compose, 2 serviços |
| 7 | Escopo | 1 número WhatsApp, PT-BR, aceita áudio/texto, sempre responde em áudio+texto |
| 8 | LGPD | Retenção 90 dias, comando `apagar meus dados` |
| 9 | Testes | Unitários (parsers, PDF, SQLite) + E2E manual |

## Arquitetura

```
┌─────────────────────┐
│   WhatsApp Cloud    │
└──────────┬──────────┘
           │
  ┌────────▼────────┐
  │  gateway (Node) │  whatsapp-web.js
  │  - recebe msg   │  - detecta tipo (áudio/texto/mídia)
  │  - envia msg    │  - baixa áudio → bytes
  │  - envia PDF    │  - encaminha pro brain via HTTP
  └────────┬────────┘
           │ POST /message
  ┌────────▼────────────────┐
  │   brain (Python FastAPI)│
  │  - carrega histórico    │
  │  - chama Gemini 3 Flash │
  │  - parseia resposta JSON│
  │  - grava histórico      │
  │  - se curriculo → PDF   │
  │  - chama TTS            │
  └─┬───────┬──────────┬────┘
    │       │          │
    ▼       ▼          ▼
  SQLite  Gemini   WeasyPrint
  (biu.db) API     (PDF)
```

Dois containers Docker Compose:

- **`gateway`** (Node): única responsabilidade é falar com o WhatsApp. Recebe mensagem → repassa pro `brain` via HTTP → recebe áudio/texto/PDF → envia pro usuário.
- **`brain`** (Python/FastAPI): cérebro. Gerencia conversas, chama Gemini, gera PDF, faz TTS. Expõe `POST /message` e `POST /forget`.

Rede interna do Compose resolve `http://brain:8000`, nenhuma porta pública.

### Volumes persistentes

- `./data/sqlite/` → `biu.db`
- `./data/wwebjs-auth/` → sessão WhatsApp (evita re-escanear QR)
- `./data/pdfs/` → PDFs gerados
- `./data/logs/` → logs estruturados

## Componentes

### `gateway/` (Node.js)

```
gateway/
├── src/
│   ├── index.js          # bootstrap whatsapp-web.js client
│   ├── handler.js        # recebe msg, classifica, chama brain
│   ├── brainClient.js    # HTTP client → POST /message
│   └── mediaUtils.js     # baixa áudio, valida tipo
├── Dockerfile
└── package.json
```

Responsabilidades:
- Autenticação WhatsApp (QR code na primeira vez, persistido)
- Event loop: `message` → baixa mídia se áudio → POST brain → envia reply (áudio + texto; PDF se vier)
- Fila FIFO por telefone em memória (`Map<phone, Promise>`) pra serializar mensagens do mesmo usuário
- Zero lógica de negócio

### `brain/` (Python)

```
brain/
├── app/
│   ├── main.py               # FastAPI: /message, /forget
│   ├── conversation.py       # get_history, append_turn, forget
│   ├── gemini_chat.py        # Gemini 3 Flash (áudio/texto in, JSON out)
│   ├── gemini_jobs.py        # Gemini com grounding (Google Search)
│   ├── tts.py                # Gemini 2.5 Flash Preview TTS → WAV
│   ├── pdf.py                # Jinja2 + WeasyPrint
│   ├── prompt.py             # carrega system prompt do Biu
│   ├── db.py                 # SQLite (WAL mode, retry em lock)
│   └── models.py             # pydantic schemas
├── templates/
│   └── curriculo.html        # template Harvard
├── static/
│   └── curriculo.css
├── prompts/
│   └── biu_system.md         # prompt do Biu (editável sem rebuild)
├── tests/
│   ├── test_parsers.py
│   ├── test_pdf.py
│   ├── test_conversation.py
│   └── test_prompt.py
├── Dockerfile
└── pyproject.toml
```

O prompt do Biu fica em `prompts/biu_system.md` (montado como volume read-only no compose) para permitir iteração no tom/fluxo sem rebuild do container.

## Modelo de dados

### SQLite — `biu.db`

```sql
CREATE TABLE conversations (
  phone         TEXT PRIMARY KEY,
  history_json  TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active',  -- active|completed|abandoned
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE curriculos (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  phone          TEXT NOT NULL,
  curriculo_json TEXT NOT NULL,
  pdf_path       TEXT NOT NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (phone) REFERENCES conversations(phone)
);

CREATE INDEX idx_conversations_updated ON conversations(updated_at);
CREATE INDEX idx_curriculos_phone ON curriculos(phone);
```

`history_json` é uma lista serializada:
```json
[
  {"role": "user", "text": "oi", "ts": "2026-04-12T10:00:00Z"},
  {"role": "model", "text": "Oi! Eu sou o Biu...", "type": "saudacao", "ts": "..."}
]
```

Armazena **texto** de ambos os lados (não áudio bruto). Para entrada de áudio, a transcrição é extraída do campo `user_transcript` que o Gemini inclui na resposta estruturada — isso evita chamadas extras de STT e mantém o histórico leve (em turnos subsequentes passamos texto, não reenviamos o áudio).

SQLite rodará em `journal_mode=WAL` para permitir leitura concorrente com escrita.

### Pydantic schemas

```python
class BiuReply(BaseModel):
    user_transcript: str   # o que o Biu entendeu do input do usuário (texto ou áudio)
    response: str
    type: Literal["saudacao","pergunta","confirmacao","correcao",
                  "curriculo","vagas","despedida"]
    generate_pdf: bool = False

class DadosPessoais(BaseModel):
    nome: str
    telefone: str
    email: Optional[str] = None
    cidade: str
    bairro: Optional[str] = None

class Curso(BaseModel):
    nome: str
    instituicao: Optional[str] = None
    ano: Optional[str] = None
    carga_horaria: Optional[str] = None

class Educacao(BaseModel):
    escolaridade: str
    instituicao: Optional[str] = None
    ano_conclusao: Optional[str] = None
    cursos: list[Curso] = []

class Experiencia(BaseModel):
    cargo: str
    empresa: str
    cidade: Optional[str] = None
    periodo: Optional[str] = None
    descricao: list[str] = []

class Habilidades(BaseModel):
    tecnicas: list[str] = []
    idiomas: list[str] = []
    interesses: list[str] = []

class Atividade(BaseModel):
    atividade: str
    descricao: str

class Curriculo(BaseModel):
    dados_pessoais: DadosPessoais
    objetivo: str
    educacao: Educacao
    experiencia: list[Experiencia] = []
    habilidades: Habilidades
    atividades: list[Atividade] = []
```

O Gemini é chamado com `response_schema` do `BiuReply`. Quando `type == "curriculo"`, o campo `response` contém o JSON do currículo como string — parseado manualmente contra `Curriculo`.

## Fluxo de dados

### Caso 1 — áudio no meio da conversa

```
1. WhatsApp → gateway     : "audio msg de +5581..."
2. gateway                : baixa ogg/mp3 → bytes; detecta mime
3. gateway → brain        : POST /message
                             { phone, kind: "audio",
                               mime: "audio/ogg", data_b64: "..." }
4. brain.conversation     : history = get_history(phone)
5. brain.gemini_chat      : contents = system_prompt + history + audio_part
                             → Gemini 3 Flash (response_schema=BiuReply)
                             → { response, type, generate_pdf }
6. brain.conversation     : append_turn user (reply.user_transcript)
                             append_turn model (reply.response)
7. brain.tts              : reply.response → WAV bytes
8. brain → gateway        : { text, audio_b64, pdf_path: null }
9. gateway → WhatsApp     : envia áudio primeiro, texto depois
```

### Caso 2 — confirmação → currículo + vagas

```
5a. brain detecta type=="curriculo" e generate_pdf=true
5b. parseia reply.response (string) → Curriculo (pydantic)
5c. brain.pdf.render(curriculo) → bytes → salva em data/pdfs/{phone}_{ts}.pdf
5d. grava em tabela `curriculos`
5e. dispara 2ª chamada Gemini com grounding:
      prompt = "Com base neste currículo e objetivo {objetivo} na cidade {cidade},
                busque 3-4 vagas REAIS em portais brasileiros (Indeed, Catho,
                Gupy, SINE, Vagas.com). Retorne título, empresa, link."
    → resposta + grounding_metadata.grounding_chunks (URLs reais)
5f. formata resposta de vagas (type: "vagas") com links
5g. brain.tts(texto de vagas)
5h. brain → gateway → WhatsApp:
      (a) áudio "Seu currículo ficou pronto!"
      (b) documento PDF
      (c) texto com vagas + links clicáveis
```

Ordem no WhatsApp **sempre**: áudio → PDF (se houver) → texto.

### Caso 3 — `apagar meus dados`

Gateway detecta string case-insensitive (com/sem acento): "apagar meus dados", "apaga meus dados", "apagar dados" → `POST /forget` → `DELETE FROM conversations/curriculos WHERE phone=?` + `rm data/pdfs/{phone}_*.pdf` → confirmação síncrona.

### Caso 4 — primeira mensagem

`get_history(phone)` retorna `[]` → sem histórico, só system_prompt + input inicial. Modelo responde com `type: "saudacao"`.

### Concorrência

Fila FIFO por telefone no gateway (`Map<phone, Promise>`). Segunda mensagem do mesmo número espera a primeira terminar. Timeout de 60s — se estourar, responde "to meio lento, reenvia por favor".

## Tratamento de erros

| # | Cenário | Ação |
|---|---|---|
| 1 | Gemini JSON malformado | `ValidationError` → 1 retry com prompt corretivo → fallback textual |
| 2 | Gemini timeout / 5xx / rate limit | Retry backoff exp (1s, 3s, 8s), max 3 tentativas → "tenta daqui a uns minutinhos" |
| 3 | Áudio inaudível | Confiar no prompt do Biu (não trata no MVP) |
| 4 | Mídia não-suportada (figurinha, localização) | Gateway responde sem chamar brain: "só áudio ou texto" |
| 5 | WeasyPrint falha | Envia resposta textual + "me manda 'gerar de novo'". Currículo JSON fica salvo pra retry manual |
| 6 | Grounding sem resultado | Fallback: URLs de busca formatados (indeed.com.br, etc) |
| 7 | WhatsApp desconecta | Log warning, tenta reconectar; se QR novo, log bem visível |
| 8 | 2 msgs paralelas do mesmo número | Fila FIFO por phone |
| 9 | `apagar meus dados` | Síncrono, apaga DB + PDFs |
| 10 | SQLite locked | WAL mode + retry 3x (100ms) |
| 11 | Disco cheio | Cron diário apaga PDFs > 30 dias; warning em < 500MB livres |
| 12 | Conversa abandonada | Nada automático; cron 90 dias limpa |

Logging estruturado (JSON) com `phone` truncado (`+5581****1234`), `turn_id`, `event`, `duration_ms`. Arquivo rotativo em `data/logs/brain.log`.

## Testes

### Unitários (pytest)

```
brain/tests/
├── test_parsers.py       # BiuReply + Curriculo parse, casos válidos/inválidos
├── test_pdf.py           # render(curriculo_mock) produz PDF > 1KB válido
├── test_conversation.py  # get/append/forget SQLite em :memory:
├── test_prompt.py        # biu_system.md carrega, tem seções-chave
└── fixtures/
    ├── curriculo_maria.json
    └── biu_replies.json
```

Mock do Gemini: `FakeGeminiClient` retorna respostas pré-gravadas. Gemini real só no E2E.

### E2E manual (`E2E.md`)

1. `docker compose up` → QR, escaneia celular de teste.
2. "oi" por texto → saudação em áudio+texto.
3. Áudio com dados pessoais → avança pra escolaridade.
4. Fluxo completo até confirmação.
5. Confirmar → áudio "pronto!" + PDF + texto com vagas + links.
6. Abrir PDF: nome correto, seções Harvard, bullets com verbos de ação.
7. "apagar meus dados" → confirma, DB e PDF limpos.
8. Mandar figurinha → mensagem educada.
9. Derrubar `brain` → gateway responde "probleminha".

## Estrutura do repo

```
VozPro/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── E2E.md
├── docs/superpowers/specs/
├── gateway/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
└── brain/
    ├── Dockerfile
    ├── pyproject.toml
    ├── app/
    ├── templates/
    ├── static/
    ├── prompts/
    └── tests/
```

`data/` é gitignored; volumes são montados em runtime.

## Docker Compose

```yaml
services:
  brain:
    build: ./brain
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - BIU_DATA_RETENTION_DAYS=90
      - BIU_PDF_RETENTION_DAYS=30
      - BIU_LOG_LEVEL=INFO
    volumes:
      - ./data/sqlite:/app/data/sqlite
      - ./data/pdfs:/app/data/pdfs
      - ./data/logs:/app/data/logs
      - ./brain/prompts:/app/prompts:ro
    expose: ["8000"]
    restart: unless-stopped

  gateway:
    build: ./gateway
    environment:
      - BRAIN_URL=http://brain:8000
    volumes:
      - ./data/wwebjs-auth:/app/.wwebjs_auth
      - ./data/pdfs:/app/pdfs:ro
    depends_on: [brain]
    restart: unless-stopped
```

## Variáveis de ambiente

```
GEMINI_API_KEY=...
BIU_DATA_RETENTION_DAYS=90
BIU_PDF_RETENTION_DAYS=30
BIU_LOG_LEVEL=INFO
BRAIN_URL=http://brain:8000        # gateway only
```

## Ordem de implementação

1. Brain mínimo: FastAPI com `/message` fake que ecoa string.
2. Gateway mínimo: conecta WhatsApp, ecoa texto via brain.
3. SQLite + `conversation.py` + histórico.
4. Gemini 3 Flash chat (texto only) + prompt do Biu.
5. STT: áudio multimodal (input áudio direto).
6. TTS: sempre responde em áudio.
7. Parsing `Curriculo` + PDF (Jinja2 + WeasyPrint).
8. Envio do PDF pelo WhatsApp.
9. Gemini grounding para vagas.
10. Fila por telefone + `apagar meus dados`.
11. Tratamento de erros, retries, logs estruturados.
12. Cron de retenção.
13. E2E manual completo.

## Prompt do Biu

Arquivo `brain/prompts/biu_system.md` — conteúdo idêntico ao prompt fornecido pelo usuário (sem alterações). Não replicado aqui para evitar desincronia; a fonte de verdade é o arquivo no repo.

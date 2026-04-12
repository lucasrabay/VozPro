# Biu — Assistente de Emprego via WhatsApp

<p align="center">
  <img src="docs/WhatsApp%20Image%202026-04-12%20at%2008.48.20.jpeg" alt="Logo do Biu" width="350"/>
</p>

> "Oi! Eu sou o Biu, seu assistente de emprego. Vou te ajudar a montar um currículo bem bonito. É rapidinho!"

Biu é um assistente conversacional que ajuda pessoas de **baixa escolaridade e baixo letramento digital** a:

1. **Montar um currículo profissional** (no padrão Harvard, PDF pronto pra imprimir) através de uma conversa por áudio no WhatsApp — sem formulários, sem digitação, sem fricção.
2. **Encontrar vagas reais** compatíveis com o perfil, com links diretos pros principais portais de emprego brasileiros.

A conversa é em português brasileiro, tom de amigo, uma pergunta por vez.

---

## Sumário

- [Como funciona](#como-funciona)
- [Arquitetura](#arquitetura)
- [Requisitos](#requisitos)
- [Como rodar (passo a passo)](#como-rodar-passo-a-passo)
- [Testar a conversa](#testar-a-conversa)
- [Logs e troubleshooting](#logs-e-troubleshooting)
- [Desenvolvimento local](#desenvolvimento-local)
- [Configuração](#configuração)
- [Comandos do usuário](#comandos-do-usuário)
- [Privacidade e LGPD](#privacidade-e-lgpd)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Documentos relacionados](#documentos-relacionados)

---

## Como funciona

```
┌─────────────────┐
│ Pessoa manda    │   Áudio ou texto no WhatsApp
│ "oi" pro Biu    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Biu pergunta    │   "Me fala seu nome, cidade e telefone"
│ dados pessoais  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Biu conduz 6    │   Dados → Escolaridade → Experiência → Habilidades
│ etapas de coleta│   → Atividades → Objetivo
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Biu resume e    │   "Vamos confirmar: Nome: X, Telefone: Y..."
│ pede confirmação│
└────────┬────────┘
         │ "pode gerar"
         ▼
┌─────────────────┐
│ Biu gera PDF    │   Currículo Harvard + áudio "tá pronto!"
│ + busca vagas   │   + 3-4 vagas reais com links clicáveis
└─────────────────┘
```

Biu transcreve o áudio automaticamente, converte linguagem coloquial em texto profissional no formato Harvard ("fazia bolo" → "Produziu e comercializou aproximadamente 30 bolos por semana"), e responde sempre em áudio com voz amigável.

Exemplo de conversa completa no [spec do design](docs/superpowers/specs/2026-04-12-biu-whatsapp-assistant-design.md).

---

## Arquitetura

Dois serviços Docker conversando via HTTP numa rede interna:

```
                   ┌───────────────────────┐
                   │     WhatsApp Cloud    │
                   └───────────┬───────────┘
                               │ (QR code na 1ª vez)
                ┌──────────────▼──────────────┐
                │       gateway (Node.js)     │
                │       whatsapp-web.js       │
                │  ─ recebe áudio/texto        │
                │  ─ detecta "apagar dados"    │
                │  ─ fila FIFO por telefone    │
                │  ─ envia reply (áudio+PDF)   │
                └──────────────┬──────────────┘
                               │ POST /message
                               │ POST /forget
                ┌──────────────▼──────────────┐
                │     brain (Python/FastAPI)  │
                │  ─ histórico da conversa    │
                │  ─ retries + logs estrut.   │
                │  ─ orquestra Gemini + PDF   │
                └─┬──────┬──────┬──────┬──────┘
                  │      │      │      │
    Gemini 3 Flash│      │      │      │Gemini 2.5 Flash TTS
    (STT + chat   │      │      │      │(voz "Algenib")
    multimodal)   ▼      ▼      ▼      ▼
              SQLite  Gemini 3  Jinja2 +
             (biu.db)  Flash +  WeasyPrint
                      Grounding   (PDF)
                      (vagas)
```

**Por que duas linguagens?** `whatsapp-web.js` é a biblioteca não-oficial mais madura pro WhatsApp (Node); WeasyPrint, FastAPI e a SDK do Gemini são mais limpos em Python. O custo é um HTTP hop local — desprezível.

**Stack resumida:**

| Componente | Tecnologia |
|---|---|
| Gateway WhatsApp | Node.js 20 + `whatsapp-web.js` + Chromium headless |
| API | Python 3.12 + FastAPI + `uvicorn` |
| LLM (conversa + STT) | Gemini 3 Flash Preview, multimodal (aceita áudio direto) |
| Busca de vagas | Gemini 3 Flash + Grounding com Google Search |
| TTS | Gemini 2.5 Flash Preview TTS, voz "Algenib" |
| PDF | Jinja2 (template) + WeasyPrint (HTML→PDF) |
| Persistência | SQLite (WAL mode), arquivo único |
| Observabilidade | `structlog` (JSON), arquivo rotativo em `data/logs/` |
| Deploy | Docker Compose (2 serviços) |

Design completo (decisões, trade-offs, tratamento de erros, fluxos) em [`docs/superpowers/specs/2026-04-12-biu-whatsapp-assistant-design.md`](docs/superpowers/specs/2026-04-12-biu-whatsapp-assistant-design.md).

---

## Requisitos

- **Docker Desktop** 24+ e **Docker Compose** v2+
- **Chave de API do Gemini** — pega grátis em [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
- **Um celular de teste com WhatsApp** — precisa ser um número **diferente do seu principal**, porque o WhatsApp só aceita **uma sessão Web ativa por vez** (se você usa WhatsApp Web no navegador, vai ter que escolher)
- **~2 GB de espaço em disco** pras imagens Docker (Python + Node + Chromium + libs nativas)

---

## Como rodar (passo a passo)

### 1. Clone e configure as variáveis de ambiente

```bash
git clone <este-repo>
cd VozPro

cp .env.example .env
```

Edite `.env` e preencha sua chave Gemini:

```env
GEMINI_API_KEY=AIza...sua_chave_aqui
BIU_DATA_RETENTION_DAYS=90
BIU_PDF_RETENTION_DAYS=30
BIU_LOG_LEVEL=INFO
```

### 2. Suba os containers

```bash
docker compose up --build
```

O que acontece na primeira vez:

- **Build do `brain`** (~3-5 min): instala Python 3.12, libs nativas do WeasyPrint (Pango, Cairo, HarfBuzz), dependências do `pyproject.toml`.
- **Build do `gateway`** (~2-3 min): instala Node 20, Chromium headless, `whatsapp-web.js`.
- **`brain` sobe primeiro** e fica disponível em `http://brain:8000` na rede interna do Compose.
- **`gateway` inicia** e tenta se conectar ao WhatsApp.

As próximas vezes que você rodar `docker compose up` são quase instantâneas (cache de layer).

### 3. Escaneie o QR code

No terminal onde você rodou `docker compose up`, o container `gateway` vai imprimir um QR code ASCII:

```
[gateway] scan this QR code with the WhatsApp app:
██████████████  ████  ██  ██████████████
██          ██  ██ ████    ██          ██
██  ██████  ██  ██      ██  ██  ██████  ██
...
```

No **celular de teste**:

1. Abra o WhatsApp → **Configurações → Dispositivos conectados**
2. Toque em **Conectar um dispositivo**
3. Aponte a câmera para o QR no terminal

Quando o log mostrar:

```
[gateway] authenticated
[gateway] ready — connected to WhatsApp
```

...o Biu tá pronto pra receber mensagens.

A sessão fica persistida em `./data/wwebjs-auth/` — **você não precisa escanear de novo** enquanto esse diretório existir.

### 4. Pronto

Manda uma mensagem pro número conectado e o Biu responde. Veja [Testar a conversa](#testar-a-conversa) abaixo.

### 5. Parar os containers

```bash
# no terminal onde rodou `docker compose up`: Ctrl+C
# ou, de outro terminal:
docker compose down
```

`docker compose down` para os containers **mantendo os volumes** (sessão WhatsApp, banco SQLite, PDFs). Para zerar tudo:

```bash
docker compose down -v
rm -rf data/
```

---

## Testar a conversa

Com os containers rodando e o QR escaneado, mande mensagens de qualquer contato **para o número conectado**. Exemplo de fluxo:

| Você manda | Biu responde (áudio + texto) |
|---|---|
| "oi" (texto) | Saudação: "Oi! Eu sou o Biu, seu assistente de emprego..." |
| áudio: "meu nome é João, moro em SP, 11 99999-0000" | "Prazer, João! Você estudou até que série?..." |
| áudio: "terminei o ensino médio" | "Agora me conta: onde você já trabalhou?..." |
| *(continua etapa a etapa)* | *(Biu conduz até o final)* |
| "pode gerar" | Áudio "tá pronto!" + **PDF do currículo** + texto com 3-4 vagas reais |

Checklist E2E completo em [`E2E.md`](E2E.md).

---

## Logs e troubleshooting

Em outro terminal (enquanto `docker compose up` roda):

```bash
docker compose logs -f              # os dois serviços
docker compose logs -f brain        # só o brain
docker compose logs -f gateway      # só o gateway
```

Os logs do brain também ficam em `./data/logs/brain.log` (JSON estruturado).

### Problemas comuns

| Problema | Solução |
|---|---|
| Build falha com erro de `libpango`, `cairo`, `harfbuzz` | Tente de novo: `docker compose build --no-cache brain` |
| QR code não aparece | `docker compose logs gateway` — se travou, `docker compose restart gateway` |
| "auth failure" depois de escanear | Sessão corrompida: `rm -rf data/wwebjs-auth` e suba de novo |
| Biu não responde nada | `docker compose logs brain` — geralmente `GEMINI_API_KEY` inválida ou sem quota |
| PDF não chega no WhatsApp | Veja log do gateway. Se for erro de caminho, confira se tem arquivo em `data/pdfs/` |
| Gemini retorna 429 (rate limit) | O código já faz retry com backoff. Se persistir, espere alguns minutos |
| Quero editar o prompt sem rebuild | Edite `brain/prompts/biu_system.md` e rode `docker compose restart brain` (o arquivo é montado como volume read-only) |
| WhatsApp desconectou sozinho | Normal depois de dias sem uso. Reconecta automaticamente; se pedir QR novo, logs do gateway mostram |

---

## Desenvolvimento local

### Brain (Python)

Pra rodar testes unitários fora do Docker:

```bash
cd brain
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -e ".[dev]"
pytest
```

Suite de 16 testes cobrindo parsers Pydantic, conversa+SQLite, PDF, endpoints FastAPI (com `FakeGeminiClient`).

Se você estiver no Windows e não conseguir instalar WeasyPrint localmente (tem deps nativas chatas), rode só os leves:

```bash
pytest tests/test_parsers.py tests/test_conversation.py tests/test_prompt.py
```

### Gateway (Node.js)

```bash
cd gateway
npm install
BRAIN_URL=http://localhost:8000 node src/index.js
```

⚠️ Pra isso funcionar você precisa expor a porta 8000 do brain — comente `expose` e use `ports: ["8000:8000"]` no `docker-compose.yml` temporariamente.

### Editar o prompt do Biu em tempo real

O prompt fica em `brain/prompts/biu_system.md` e é montado como **volume read-only** no container. Então você pode editar esse arquivo do host e só reiniciar:

```bash
docker compose restart brain
```

Sem rebuild. Ideal pra iterar no tom, no fluxo, ou nas regras de transformação.

---

## Configuração

Todas as variáveis ficam no `.env` (ou no ambiente do sistema):

| Variável | Padrão | Descrição |
|---|---|---|
| `GEMINI_API_KEY` | — | **Obrigatória**. Chave da API do Gemini. |
| `BIU_DATA_RETENTION_DAYS` | `90` | Dias antes de apagar conversas inativas |
| `BIU_PDF_RETENTION_DAYS` | `30` | Dias antes de apagar PDFs gerados |
| `BIU_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `BIU_CHAT_MODEL` | `gemini-3-flash-preview` | Modelo do chat |
| `BIU_JOBS_MODEL` | `gemini-3-flash-preview` | Modelo da busca de vagas |
| `BIU_TTS_MODEL` | `gemini-2.5-flash-preview-tts` | Modelo de TTS |
| `BIU_TTS_VOICE` | `Algenib` | Voz do TTS (nomes prebuilt do Gemini) |

---

## Comandos do usuário

Dentro da conversa, a pessoa pode usar:

- **Áudio ou texto** em qualquer momento — Biu aceita os dois
- **"apagar meus dados"** (ou "apaga meus dados", "apagar dados") — limpa histórico e PDFs imediatamente; resposta de confirmação no WhatsApp

Qualquer outra mídia (figurinha, imagem, localização, contato) recebe a resposta educada: *"Oi! Por enquanto eu só entendo áudio ou texto. Manda assim que eu te ajudo!"*

---

## Privacidade e LGPD

- **Armazenamento local**: tudo fica em `./data/` no seu host (SQLite + PDFs + sessão WhatsApp). Nenhum banco externo, nenhum terceiro além da Google (Gemini API).
- **Telefone hash-mascarado nos logs**: `+5581****1234` em vez do número completo.
- **Retenção automática**: conversas apagadas após 90 dias, PDFs após 30 (configurável).
- **Apagar a pedido**: comando `apagar meus dados` no próprio WhatsApp executa delete imediato.
- **Sem áudio persistido**: armazenamos a transcrição textual, não os bytes do áudio.

A chave `GEMINI_API_KEY` fica no `.env`, que está no `.gitignore` — **nunca commite**.

---

## Estrutura do repositório

```
VozPro/
├── docker-compose.yml          # 2 serviços: brain + gateway
├── .env.example                # template (copiar pra .env)
├── README.md                   # este arquivo
├── E2E.md                      # checklist de teste manual
│
├── brain/                      # Python/FastAPI
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py             # FastAPI: /message, /forget, /health
│   │   ├── models.py           # pydantic: BiuReply, Curriculo, etc
│   │   ├── db.py               # SQLite com WAL
│   │   ├── conversation.py     # histórico, forget, save_curriculo
│   │   ├── prompt.py           # carrega biu_system.md
│   │   ├── gemini_chat.py      # Gemini 3 Flash (texto/áudio → BiuReply)
│   │   ├── gemini_jobs.py      # Gemini + grounding (busca de vagas)
│   │   ├── tts.py              # Gemini 2.5 Flash TTS → WAV
│   │   ├── pdf.py              # Jinja2 + WeasyPrint
│   │   ├── retry.py            # backoff exponencial
│   │   ├── retention.py        # cron de limpeza
│   │   └── logging_config.py   # structlog JSON
│   ├── templates/
│   │   └── curriculo.html      # template Harvard
│   ├── static/
│   │   └── curriculo.css       # estilos do PDF
│   ├── prompts/
│   │   └── biu_system.md       # PROMPT DO BIU (editável sem rebuild)
│   └── tests/
│       ├── test_parsers.py
│       ├── test_conversation.py
│       ├── test_prompt.py
│       ├── test_pdf.py
│       ├── test_main.py
│       └── fixtures/
│
├── gateway/                    # Node.js/whatsapp-web.js
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── index.js            # bootstrap whatsapp-web.js + eventos
│       ├── handler.js          # recebe mensagem, chama brain, envia reply
│       ├── brainClient.js      # HTTP client → POST /message, /forget
│       ├── mediaUtils.js       # classificar tipo, detectar "apagar dados"
│       └── phoneQueue.js       # fila FIFO por número (serializa mensagens)
│
├── data/                       # [gitignored] volumes Docker
│   ├── sqlite/biu.db           # histórico + currículos
│   ├── pdfs/                   # PDFs gerados
│   ├── logs/brain.log          # logs JSON
│   └── wwebjs-auth/            # sessão WhatsApp
│
└── docs/superpowers/specs/
    └── 2026-04-12-biu-whatsapp-assistant-design.md   # design completo
```

---

## Documentos relacionados

- [`docs/superpowers/specs/2026-04-12-biu-whatsapp-assistant-design.md`](docs/superpowers/specs/2026-04-12-biu-whatsapp-assistant-design.md) — decisões de arquitetura, fluxos, modelo de dados, tratamento de erros
- [`E2E.md`](E2E.md) — checklist de teste manual end-to-end
- [`brain/prompts/biu_system.md`](brain/prompts/biu_system.md) — o prompt do Biu em si (personalidade, fluxo, regras de transformação)

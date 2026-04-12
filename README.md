# Biu — Assistente de Emprego via WhatsApp

Biu conversa com pessoas por áudio no WhatsApp para montar currículo e sugerir vagas reais de emprego. Feito para pessoas desempregadas, com linguagem simples e tom acolhedor.

## Arquitetura

```
WhatsApp → gateway (Node.js, whatsapp-web.js) → brain (Python, FastAPI)
                                                  ├─ Gemini 3 Flash (STT + chat multimodal)
                                                  ├─ Gemini 3 Flash + grounding (busca de vagas)
                                                  ├─ Gemini 2.5 Flash TTS (voz "Algenib")
                                                  ├─ Jinja2 + WeasyPrint (PDF)
                                                  └─ SQLite (histórico + currículos)
```

Spec completa: [`docs/superpowers/specs/2026-04-12-biu-whatsapp-assistant-design.md`](docs/superpowers/specs/2026-04-12-biu-whatsapp-assistant-design.md).

## Requisitos

- Docker + Docker Compose
- API key do Gemini ([aistudio.google.com](https://aistudio.google.com/apikey))
- Um número WhatsApp de teste (a sessão é persistida após escanear o QR code pela primeira vez)

## Setup

```bash
cp .env.example .env
# edite .env e coloque sua GEMINI_API_KEY

docker compose up --build
```

Na primeira vez, o log do container `gateway` mostra um QR code. Escaneie com o WhatsApp do número que vai receber as mensagens (Configurações → Dispositivos conectados → Conectar dispositivo).

A sessão fica salva em `data/wwebjs-auth/` — não precisa escanear de novo enquanto esse volume persistir.

## Desenvolvimento

### Brain (Python)

```bash
cd brain
pip install -e ".[dev]"
pytest
```

Para editar o prompt do Biu sem reconstruir o container, edite `brain/prompts/biu_system.md` e reinicie o `brain`:

```bash
docker compose restart brain
```

### Gateway (Node.js)

```bash
cd gateway
npm install
BRAIN_URL=http://localhost:8000 node src/index.js
```

## Comandos do usuário

- **Áudio ou texto em qualquer momento** → Biu conduz a conversa
- **"apagar meus dados"** (variações: "apaga meus dados", "apagar dados") → limpa histórico e currículos salvos

## Logs

Logs estruturados (JSON) em `data/logs/brain.log` e no stdout dos containers:

```bash
docker compose logs -f brain
docker compose logs -f gateway
```

## Retenção de dados (LGPD)

- Conversas: apagadas automaticamente após `BIU_DATA_RETENTION_DAYS` dias (padrão 90)
- PDFs: apagados após `BIU_PDF_RETENTION_DAYS` dias (padrão 30)
- Comando `apagar meus dados` remove tudo imediatamente

## Testes

```bash
cd brain && pytest
```

Para E2E manual, veja [`E2E.md`](E2E.md).

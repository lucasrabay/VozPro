# Checklist E2E manual — Biu

Rode antes de cada release. Use um celular de teste (não o principal).

## Preparação

- [ ] `.env` tem `GEMINI_API_KEY` válido
- [ ] `docker compose up --build` sobe sem erro
- [ ] Log do `gateway` mostra QR code
- [ ] Escaneia QR com WhatsApp → log mostra `ready — connected to WhatsApp`

## Fluxo feliz

- [ ] Manda **texto** "oi" → recebe áudio + texto de saudação do Biu
- [ ] Manda **áudio** "meu nome é João, moro em São Paulo, bairro Campo Limpo, telefone 11 99999-0000" → avança pra pergunta sobre escolaridade
- [ ] Continua respondendo as etapas (escolaridade → experiência → follow-up → habilidades → atividades → objetivo)
- [ ] Biu apresenta resumo e pergunta "Posso gerar o seu currículo baseado nisso?"
- [ ] Confirma ("isso, pode gerar") → recebe **nessa ordem**:
  - áudio "Seu currículo ficou pronto!"
  - **documento PDF** anexado
  - texto com 3-4 vagas + links reais

## Verificação do PDF

- [ ] Nome correto no topo
- [ ] Seções: Objetivo, Educação, Experiência, Habilidades, Atividades
- [ ] Bullets de experiência começam com verbo de ação (Realizou, Executou, etc)
- [ ] Nenhum campo quebrado ou "None"/"null" aparente
- [ ] Formatação OK em tela de celular (abrir o PDF no WhatsApp)

## Comandos de controle

- [ ] Manda "apagar meus dados" → recebe confirmação "Pronto! Apaguei tudo."
- [ ] Confirma que `data/sqlite/biu.db` não tem mais o número:
  ```
  sqlite3 data/sqlite/biu.db "SELECT phone FROM conversations;"
  ```
- [ ] PDFs correspondentes sumiram de `data/pdfs/`

## Mídia não-suportada

- [ ] Manda figurinha → recebe "Por enquanto eu só entendo áudio ou texto"
- [ ] Manda localização → mesma resposta
- [ ] Manda imagem → mesma resposta

## Resiliência

- [ ] Derruba `brain`: `docker compose stop brain`
- [ ] Manda áudio → gateway responde "Tô com um problema aqui agora, tenta daqui a uns minutinhos"
- [ ] Sobe de novo: `docker compose start brain`
- [ ] Manda áudio novo → funciona normalmente

## Concorrência

- [ ] Manda 2 áudios seguidos (sem esperar resposta) → recebe respostas em ordem, sem duplicatas no histórico

## Persistência

- [ ] `docker compose down` + `docker compose up` → sessão WhatsApp não pede QR de novo
- [ ] Conversas em andamento continuam de onde pararam

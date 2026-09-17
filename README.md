# Bot de atendimento para clínica

Bot de WhatsApp para uma clínica odontológica (fictícia) que responde as dúvidas mais comuns, recebe pedidos de consulta e passa a conversa para a recepção quando precisa de uma pessoa.

Demonstração: https://bot-atendimento-clinica.vercel.app

Na demonstração o chat roda no navegador. O mesmo motor de conversa atende pelo webhook oficial do WhatsApp (Cloud API da Meta), que fica desligado enquanto as credenciais não são configuradas.

## O que ele faz

- Responde dúvidas sobre convênios, valores, horário, endereço, urgência, pagamento etc., sempre com base no arquivo `knowledge/odonto-prado.md`
- Quando não sabe, diz que não sabe e oferece chamar a recepção, em vez de inventar
- Coleta pedido de consulta: nome, motivo, dia e período, com validação (domingo fechado, sábado só de manhã, data dentro de 60 dias)
- Em caso de dor ou urgência, avisa a recepção na hora e repassa a orientação de pronto-socorro
- A qualquer momento o paciente pode digitar `menu` ou pedir pra falar com uma pessoa

## Como as respostas são geradas

Tem dois modos, escolhidos pela presença de `ANTHROPIC_API_KEY`:

- **Com chave:** a pergunta vai para o Claude (`claude-opus-5`) junto com a base da clínica. A resposta volta em JSON (`answer`, `found`), então o código sabe quando a IA não encontrou a informação. O prompt proíbe inventar valores e ignora pedidos pra mudar de função. Se a API falhar, cai para o modo local.
- **Sem chave:** busca por palavra-chave na base, com sinônimos e peso maior pra palavras raras. Responde só quando a correspondência é boa o bastante.

A demonstração pública roda sem chave, então não gera custo.

Menu, agendamento e passagem pra recepção são regras fixas, não IA. É mais previsível e mais barato pra fluxo que tem sempre os mesmos passos.

## Estrutura

```
app/
  main.py        rotas FastAPI: demo, webhook do WhatsApp, headers de segurança
  engine.py      fluxo da conversa (menu, dúvidas, agendamento, recepção)
  answer.py      respostas com Claude ou busca local
  knowledge.py   leitura e busca na base da clínica
  state.py       estado assinado (demo) e SQLite (WhatsApp)
  whatsapp.py    assinatura do webhook, leitura e envio de mensagens
  ratelimit.py   limite de mensagens por IP
knowledge/       base de conhecimento em Markdown
public/          página de demonstração
tests/           43 testes
```

## Rodando local

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/Mac: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # opcional, pra usar IA ou WhatsApp

python -m pytest
uvicorn app.main:app --reload
```

Abra http://localhost:8000.

## Ligando no WhatsApp

1. Crie um app em developers.facebook.com e adicione o produto WhatsApp
2. Preencha no `.env`: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET` e um `WHATSAPP_VERIFY_TOKEN` inventado por você
3. Configure o webhook apontando pra `https://seu-dominio/webhook/whatsapp` e assine o campo `messages`

O estado das conversas do WhatsApp fica em SQLite, então precisa de um servidor com disco persistente (VPS, Railway, Fly.io etc.). Em função serverless o arquivo não sobrevive entre execuções.

## Segurança

- Webhook só aceita requisição com `X-Hub-Signature-256` válido (HMAC com o app secret, comparação em tempo constante)
- Mensagens repetidas do WhatsApp são ignoradas pelo id, pra não responder duas vezes
- Na demo, o estado da conversa vai assinado com HMAC e expira em 2 horas; estado adulterado é descartado
- Telefone do paciente é salvo só como hash, e conversas com mais de 30 dias são apagadas
- Limite de 20 mensagens por minuto por IP na demo, corpo da requisição limitado a 64 KB, texto a 500 caracteres
- Limite de chamadas à IA por conversa
- Caracteres de controle removidos da entrada; na página, tudo é inserido com `textContent`
- CSP sem script inline, HSTS, `X-Frame-Options`, `/docs` desligado
- Chaves só por variável de ambiente, `.env` fora do Git
- Actions fixadas por hash de commit e `pip-audit` no CI

O limite por IP fica na memória de cada instância. Para produção com várias instâncias, o ideal é um Redis ou o firewall da própria hospedagem.

## Stack

Python 3.12+, FastAPI, SDK da Anthropic, httpx, SQLite, pytest. Front em HTML, CSS e JavaScript sem framework. Deploy na Vercel.

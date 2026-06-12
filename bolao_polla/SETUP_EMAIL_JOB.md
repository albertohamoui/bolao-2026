# Job de email dos bolões — setup

Recebe, **~30 min antes de cada jogo**, um email com todos os jogos do dia:
palpites dos 3 bolões (Zap, Cli, Polla), resultado real (puxado automaticamente
quando o jogo começa/termina) e a pontuação de cada bolão por jogo + total
acumulado.

## Arquitetura

```
GitHub Actions (cron a cada 10 min)
        │
        ├─ lê  bolao_polla/palpites.csv        (seus palpites consolidados)
        ├─ lê  API football-data.org           (cronograma + placares reais)
        ├─ calcula pontos (scripts/scoring.py)
        └─ envia email via Gmail SMTP           (só p/ jogos a ~30 min do início)
```

- **Roda na nuvem** — não depende do seu PC ligado.
- **Resultados automáticos** — não precisa digitar nada; a API preenche.
- **1 email por jogo** (dedup por `bolao_polla/.sent_state.json`).

## Passo 1 — Token da API de futebol (grátis)

1. Crie conta em https://www.football-data.org/client/register
2. Copie seu **API token** (recebe por email).
3. Plano grátis cobre a Copa do Mundo (competição `WC`), 10 req/min — suficiente.

## Passo 2 — Senha de app do Gmail

1. Ative a verificação em 2 etapas na sua conta Google.
2. Vá em https://myaccount.google.com/apppasswords
3. Gere uma senha de app (16 caracteres). Guarde-a.

## Passo 3 — Secrets no GitHub

No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
Crie os 4:

| Secret | Valor |
|--------|-------|
| `FOOTBALL_DATA_TOKEN` | o token do passo 1 |
| `GMAIL_USER` | seu email Gmail (ex: `voce@gmail.com`) |
| `GMAIL_APP_PASSWORD` | a senha de app de 16 dígitos do passo 2 |
| `EMAIL_TO` | destinatário(s), separados por vírgula |

> Os secrets ficam criptografados; nunca aparecem no código nem nos logs.

## Passo 4 — Ligar o workflow

O arquivo `.github/workflows/palpites-email.yml` já está no repo. Workflows
agendados rodam sozinhos no branch `main`. Para testar na hora:
**Actions → "Email palpites boloes Copa 2026" → Run workflow**.

## Fuso horário

Padrão **Brasil (-03:00)**. Para Panamá (-05:00), edite `BOLAO_UTC_OFFSET` no
workflow para `"-5"`.

## Quando mudar palpites

Os palpites vêm de `bolao_polla/palpites.csv`. Se você alterar o
`Controle_Boloes_Copa2026.xlsx`, rode novamente para reexportar e commite:

```bash
python scripts/export_palpites.py
git add bolao_polla/palpites.csv && git commit -m "update palpites" && git push
```

## Testar localmente (sem enviar)

```bash
# usa um mock offline e um horário fixo; imprime o email no terminal
python scripts/enviar_palpites_email.py --mock scripts/_mock_wc.json \
  --now 2026-06-12T15:30 --dry-run
```

## Mata-mata

`palpites.csv` cobre os 72 jogos de grupos. Quando os jogos do mata-mata forem
definidos e você consolidar esses palpites, dá pra estender o mesmo job (a
pontuação do Zap dobra no mata-mata; Cli e Polla mantêm os mesmos valores).

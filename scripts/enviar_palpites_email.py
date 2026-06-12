"""
Job de email dos boloes da Copa 2026.

Dispara ~30 min antes de cada jogo e envia um email com TODOS os jogos do dia:
palpites dos 3 boloes (Zap, Cli, Polla), resultado real (puxado da API quando o
jogo ja comecou/terminou) e a pontuacao de cada bolao por jogo, alem do total
acumulado no torneio.

Fonte de dados:
  - Palpites: bolao_polla/palpites.csv (gerado por export_palpites.py)
  - Cronograma + resultados: API football-data.org (competicao WC), via
    header X-Auth-Token = $FOOTBALL_DATA_TOKEN
  - Envio: Gmail SMTP (STARTTLS) com $GMAIL_USER / $GMAIL_APP_PASSWORD,
    destinatarios em $EMAIL_TO (separados por virgula)

Idempotencia: cada jogo dispara o email uma unica vez (state em
bolao_polla/.sent_state.json). O workflow do GitHub Actions roda em intervalo
curto e usa a janela [agora+25min, agora+35min] como "30 min antes".

Uso:
  python scripts/enviar_palpites_email.py            # producao (envia)
  python scripts/enviar_palpites_email.py --dry-run  # imprime o email, nao envia
  python scripts/enviar_palpites_email.py --mock m.json --now 2026-06-12T15:30 --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import smtplib
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from scoring import cli_points, polla_points, zap_points

ROOT = Path(__file__).resolve().parent.parent
PALPITES_CSV = ROOT / "bolao_polla" / "palpites.csv"
STATE_FILE = ROOT / "bolao_polla" / ".sent_state.json"
API_URL = "https://api.football-data.org/v4/competitions/WC/matches"
# Offset fixo (Brasil -3 nao tem mais horario de verao; Panama -5). Configuravel
# por env BOLAO_UTC_OFFSET. Offset fixo evita depender do tzdata no Windows.
LOCAL_TZ = timezone(timedelta(hours=float(os.environ.get("BOLAO_UTC_OFFSET", "-3"))))
# Janela de disparo: kickoff entre +20 e +40 min. Com cron a cada 10 min, cada
# jogo cai na janela de >=2 execucoes (robusto a atraso do Actions); o dedup por
# estado garante 1 email por jogo. Disparo efetivo ~30 min antes.
WINDOW_BEFORE_MIN = 20
WINDOW_AFTER_MIN = 40

# Aliases de nomes da API -> nome canonico usado no palpites.csv.
API_ALIASES = {
    "korearepublic": "South Korea",
    "iriran": "Iran",
    "cotedivoire": "Ivory Coast",
    "turkiye": "Turkey",
    "czechrepublic": "Czechia",
    "caboverde": "Cape Verde",
    "congodr": "DR Congo",
    "drcongo": "DR Congo",
    "usa": "United States",
    "unitedstatesofamerica": "United States",
}


def norm(name: str) -> str:
    """Chave normalizada: sem acento, minuscula, so letras/numeros."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum())


def canonical(api_name: str) -> str:
    return API_ALIASES.get(norm(api_name), api_name)


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
def load_palpites() -> dict[frozenset, dict]:
    """frozenset({home,away}) -> linha de palpite (com home/away orientados)."""
    out = {}
    with open(PALPITES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = frozenset({norm(row["home"]), norm(row["away"])})
            out[key] = row
    return out


def fetch_matches(token: str | None, mock: str | None) -> list[dict]:
    if mock:
        return json.loads(Path(mock).read_text(encoding="utf-8"))["matches"]
    import requests  # import tardio: so necessario em producao
    if not token:
        raise SystemExit("ERRO: FOOTBALL_DATA_TOKEN vazio. Configure o secret.")
    resp = requests.get(API_URL, headers={"X-Auth-Token": token}, timeout=30)
    if resp.status_code != 200:
        raise SystemExit(
            f"ERRO API football-data {resp.status_code}: {resp.text[:300]}")
    return resp.json()["matches"]


def parse_match(m: dict) -> dict:
    """Extrai campos relevantes de um match da API."""
    ko = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
    ft = m.get("score", {}).get("fullTime", {})
    home_g, away_g = ft.get("home"), ft.get("away")
    has_result = home_g is not None and away_g is not None
    return {
        "id": m["id"],
        "kickoff_utc": ko,
        "kickoff_local": ko.astimezone(LOCAL_TZ),
        "status": m.get("status", ""),
        "api_home": canonical(m["homeTeam"]["name"]),
        "api_away": canonical(m["awayTeam"]["name"]),
        "home_g": home_g,
        "away_g": away_g,
        "has_result": has_result,
    }


# ---------------------------------------------------------------------------
# Pontuacao por jogo
# ---------------------------------------------------------------------------
def real_oriented(match: dict, pal: dict):
    """Retorna (real_home_palpite, real_away_palpite) na orientacao do palpite."""
    if not match["has_result"]:
        return None
    if norm(match["api_home"]) == norm(pal["home"]):
        return match["home_g"], match["away_g"]
    return match["away_g"], match["home_g"]


def points_for(pal: dict, real, knockout: bool) -> dict:
    if real is None or not pal:
        return {"Zap": None, "Cli": None, "Polla": None}
    rh, ra = real
    return {
        "Zap": zap_points((int(pal["zap_h"]), int(pal["zap_a"])), (rh, ra), knockout),
        "Cli": cli_points((int(pal["cli_h"]), int(pal["cli_a"])), (rh, ra), knockout),
        "Polla": polla_points((int(pal["polla_h"]), int(pal["polla_a"])), (rh, ra), knockout),
    }


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def fmt_score(real) -> str:
    return "-" if real is None else f"{real[0]}x{real[1]}"


def _p(v) -> str:
    return "-" if v is None else str(v)


def render_email(day_local, day_matches, totals, trigger) -> tuple[str, str]:
    t = trigger
    subj = (f"[Boloes Copa] {t['api_home']} x {t['api_away']} "
            f"as {t['kickoff_local']:%H:%M} - palpites do dia {day_local:%d/%m}")

    head = """
    <style>
      body{font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222}
      table{border-collapse:collapse;width:100%;margin:8px 0}
      th,td{border:1px solid #ccc;padding:6px 8px;text-align:center}
      th{background:#1F4E78;color:#fff}
      .pts{font-weight:bold}
      .live{color:#b30000;font-weight:bold}
    </style>"""

    rows = []
    for m in day_matches:
        pal, real, pts = m["pal"], m["real"], m["pts"]
        live = "" if not m["has_result"] else (
            " (final)" if m["status"] == "FINISHED" else " (ao vivo)")
        cls = "" if (m["status"] == "FINISHED" or not m["has_result"]) else ' class="live"'
        if pal:
            zap = f'{pal["zap_h"]}x{pal["zap_a"]}'
            cli = f'{pal["cli_h"]}x{pal["cli_a"]}'
            pol = f'{pal["polla_h"]}x{pal["polla_a"]}'
        else:
            zap = cli = pol = "?"
        rows.append(f"""
        <tr>
          <td>{m['kickoff_local']:%H:%M}</td>
          <td>{m['api_home']} x {m['api_away']}</td>
          <td>{zap} <span class="pts">[{_p(pts['Zap'])}]</span></td>
          <td>{cli} <span class="pts">[{_p(pts['Cli'])}]</span></td>
          <td>{pol} <span class="pts">[{_p(pts['Polla'])}]</span></td>
          <td{cls}>{fmt_score(real)}{live}</td>
        </tr>""")

    body = f"""<html><head>{head}</head><body>
    <h2>Jogos de {day_local:%d/%m/%Y}</h2>
    <p>Disparo: 30 min antes de <b>{t['api_home']} x {t['api_away']}</b>
       ({t['kickoff_local']:%H:%M} BRT).</p>
    <table>
      <tr><th>Hora</th><th>Jogo</th><th>Zap [pts]</th><th>Cli [pts]</th>
          <th>Polla [pts]</th><th>Real</th></tr>
      {''.join(rows)}
    </table>
    <h3>Total acumulado no torneio</h3>
    <table>
      <tr><th>Bolao do Zap</th><th>Bolao do Cli</th><th>Polla 26</th></tr>
      <tr><td class="pts">{totals['Zap']}</td><td class="pts">{totals['Cli']}</td>
          <td class="pts">{totals['Polla']}</td></tr>
    </table>
    <p style="color:#888;font-size:12px">Resultados via football-data.org.
       Pontos recalculam sozinhos conforme os jogos terminam.</p>
    </body></html>"""
    return subj, body


# ---------------------------------------------------------------------------
# Estado / envio
# ---------------------------------------------------------------------------
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def send_email(subj: str, html: str) -> None:
    user = os.environ["GMAIL_USER"]
    pwd = os.environ["GMAIL_APP_PASSWORD"]
    to = [x.strip() for x in os.environ["EMAIL_TO"].split(",") if x.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"] = user
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls()
        s.login(user, pwd)
        s.sendmail(user, to, msg.as_string())


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------
def build_day_view(matches, palpites, day_local):
    day = []
    for m in matches:
        if m["kickoff_local"].date() != day_local:
            continue
        key = frozenset({norm(m["api_home"]), norm(m["api_away"])})
        pal = palpites.get(key)
        real = real_oriented(m, pal) if pal else None
        enriched = {**m, "pal": pal, "real": real,
                    "pts": points_for(pal, real, knockout=False)}
        day.append(enriched)
    day.sort(key=lambda x: x["kickoff_local"])
    return day


def compute_totals(matches, palpites) -> dict:
    tot = {"Zap": 0, "Cli": 0, "Polla": 0}
    for m in matches:
        if not m["has_result"]:
            continue
        key = frozenset({norm(m["api_home"]), norm(m["api_away"])})
        pal = palpites.get(key)
        if not pal:
            continue
        pts = points_for(pal, real_oriented(m, pal), knockout=False)
        for k in tot:
            if pts[k] is not None:
                tot[k] += pts[k]
    return tot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignora dedup")
    ap.add_argument("--now", help="ISO local p/ teste (ex 2026-06-12T15:30)")
    ap.add_argument("--mock", help="JSON com {'matches':[...]} p/ teste offline")
    args = ap.parse_args()

    if args.now:
        now = datetime.fromisoformat(args.now).replace(tzinfo=LOCAL_TZ)
    else:
        now = datetime.now(timezone.utc).astimezone(LOCAL_TZ)

    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    palpites = load_palpites()
    raw = fetch_matches(token, args.mock)
    matches = [parse_match(m) for m in raw]

    lo = now + timedelta(minutes=WINDOW_BEFORE_MIN)
    hi = now + timedelta(minutes=WINDOW_AFTER_MIN)
    triggers = [m for m in matches if lo <= m["kickoff_local"] <= hi]

    state = load_state()
    fired = 0
    for trig in sorted(triggers, key=lambda x: x["kickoff_local"]):
        mid = str(trig["id"])
        if not args.force and mid in state:
            continue
        day_local = trig["kickoff_local"].date()
        day_matches = build_day_view(matches, palpites, day_local)
        totals = compute_totals(matches, palpites)
        subj, html = render_email(day_local, day_matches, totals, trig)

        if args.dry_run:
            print(f"\n===== EMAIL (dry-run) =====\nASSUNTO: {subj}\n")
            print(html)
        else:
            send_email(subj, html)
            state[mid] = now.isoformat()
        fired += 1

    if not args.dry_run:
        save_state(state)
    print(f"now={now:%Y-%m-%d %H:%M %Z} | triggers={len(triggers)} | enviados={fired}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

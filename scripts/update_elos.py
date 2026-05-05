#!/usr/bin/env python3
"""
Bot de atualizacao de Elo ratings via eloratings.net (TSV endpoints).

Fontes:
    https://www.eloratings.net/en.teams.tsv  (mapeamento codigo -> nome)
    https://www.eloratings.net/World.tsv     (ranking com Elos)

Outputs:
    data/elo_ratings_latest.csv              (sobrescrito a cada update)
    data/elo_history/elo_ratings_YYYY-MM-DD.csv  (snapshot)

Uso:
    python3 scripts/update_elos.py           # roda o bot
    python3 scripts/update_elos.py --check   # valida CSV existente sem baixar

Nao requer Playwright — usa endpoints TSV publicos via requests.
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, date
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
HISTORY_DIR = os.path.join(DATA_DIR, "elo_history")
LATEST_CSV = os.path.join(DATA_DIR, "elo_ratings_latest.csv")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ELO_TEAMS_TSV = "https://www.eloratings.net/en.teams.tsv"
ELO_WORLD_TSV = "https://www.eloratings.net/World.tsv"
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}

MIN_TEAMS = 200
SANITY_TOP_10 = {"Spain", "Argentina", "France"}
MAX_DELTA_WARNING = 150

# Mapeamento de nomes: eloratings.net -> results.csv
# O CSV salva os nomes ORIGINAIS do eloratings.net.
# Este mapping e usado na LEITURA pra alinhar com results.csv.
# Mapeamento bidirecional de nomes.
# Tres namespaces: eloratings.net, results.csv, GROUPS/modelo.
# O CSV salva nomes originais do eloratings.net. Na leitura, aplica-se
# mapping para alinhar com results.csv ou GROUPS conforme necessario.

# eloratings.net -> results.csv
ELO_TO_CSV_NAME_MAP = {
    "China": "China PR",
    "Czechia": "Czech Republic",
    "Ireland": "Republic of Ireland",
    "East Timor": "Timor-Leste",
    "Curaçao": "Curaçao",                         # results.csv usa com acento
    "Sao Tome and Principe": "São Tomé and Príncipe",  # results.csv usa com acentos
}

# GROUPS/modelo -> eloratings.net (para validacao de cobertura da Copa)
# Nomes em GROUPS que diferem dos nomes no eloratings.net:
MODEL_TO_ELO_NAME_MAP = {
    "Curacao": "Curaçao",
}

# Inverso de ELO_TO_CSV
CSV_TO_ELO_NAME_MAP = {v: k for k, v in ELO_TO_CSV_NAME_MAP.items()}

# As 48 selecoes da Copa 2026 (nomes como em results.csv / GROUPS)
WORLD_CUP_TEAMS = [
    "Mexico", "South Korea", "South Africa", "Czechia",
    "Canada", "Switzerland", "Qatar", "Bosnia and Herzegovina",
    "Brazil", "Morocco", "Scotland", "Haiti",
    "United States", "Australia", "Paraguay", "Turkey",
    "Germany", "Ecuador", "Ivory Coast", "Curacao",
    "Netherlands", "Japan", "Tunisia", "Sweden",
    "Belgium", "Iran", "Egypt", "New Zealand",
    "Spain", "Uruguay", "Saudi Arabia", "Cape Verde",
    "France", "Senegal", "Norway", "Iraq",
    "Argentina", "Austria", "Algeria", "Jordan",
    "Portugal", "Colombia", "Uzbekistan", "DR Congo",
    "England", "Croatia", "Panama", "Ghana",
]


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def _fix_encoding(s: str) -> str:
    """Corrige encoding duplo UTF-8 que o TSV do eloratings.net as vezes tem.

    Ex: 'CuraÃ§ao' -> 'Curaçao', 'Sao Tome and PrÃ­ncipe' -> 'São Tomé and Príncipe'.
    """
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def fetch_elo_ratings() -> dict[str, int]:
    """Fetch all Elo ratings from eloratings.net TSV endpoints.

    Returns dict {team_name: elo_rating} with original eloratings.net names
    (encoding corrigido).
    """
    # Fetch team code -> name mapping
    resp = requests.get(ELO_TEAMS_TSV, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    code_to_name: dict[str, str] = {}
    for line in resp.text.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and "_loc" not in parts[0]:
            code_to_name[parts[0].strip()] = _fix_encoding(parts[1].strip())

    # Fetch world rankings
    resp = requests.get(ELO_WORLD_TSV, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    elo_by_name: dict[str, int] = {}
    for line in resp.text.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        code = parts[2].strip()
        try:
            rating = int(parts[3].strip())
        except ValueError:
            continue
        name = code_to_name.get(code, code)
        elo_by_name[name] = rating

    return elo_by_name


def elo_name_to_csv_name(elo_name: str) -> str:
    """Converte nome do eloratings.net para nome do results.csv."""
    return ELO_TO_CSV_NAME_MAP.get(elo_name, elo_name)


def csv_name_to_elo_name(csv_name: str) -> str:
    """Converte nome do results.csv para nome do eloratings.net."""
    return CSV_TO_ELO_NAME_MAP.get(csv_name, csv_name)


def model_name_to_elo_name(model_name: str) -> str:
    """Converte nome do GROUPS/modelo para nome do eloratings.net."""
    return MODEL_TO_ELO_NAME_MAP.get(model_name, model_name)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_scraped(
    elo_data: dict[str, int],
    previous_csv: Optional[str] = None,
) -> tuple[bool, list[str]]:
    """Valida dados scraped. Retorna (ok, mensagens)."""
    messages = []
    ok = True

    # Check minimum count
    if len(elo_data) < MIN_TEAMS:
        messages.append(
            f"ERRO: Apenas {len(elo_data)} selecoes extraidas "
            f"(minimo: {MIN_TEAMS}). Abortando."
        )
        ok = False

    # Check top 10 sanity
    sorted_teams = sorted(elo_data.items(), key=lambda x: x[1], reverse=True)
    top10_names = {t for t, _ in sorted_teams[:10]}
    missing_top = SANITY_TOP_10 - top10_names
    if missing_top:
        messages.append(
            f"ERRO: {missing_top} nao estao no top 10. "
            f"Top 10 atual: {[t for t, _ in sorted_teams[:10]]}. Abortando."
        )
        ok = False

    # Check cup team coverage (via name mapping)
    missing_cup = []
    for team in WORLD_CUP_TEAMS:
        elo_name = model_name_to_elo_name(team)
        if elo_name not in elo_data:
            missing_cup.append(f"{team} (procurado como '{elo_name}')")
    if missing_cup:
        messages.append(
            f"ERRO: {len(missing_cup)} selecoes da Copa sem Elo: "
            + ", ".join(missing_cup)
        )
        ok = False

    # Compare with previous version (warnings only, don't abort)
    if previous_csv and os.path.exists(previous_csv):
        prev = load_csv_as_dict(previous_csv)
        outliers = []
        for name, new_elo in elo_data.items():
            if name in prev:
                delta = abs(new_elo - prev[name])
                if delta > MAX_DELTA_WARNING:
                    outliers.append(f"{name}: {prev[name]} -> {new_elo} ({delta:+d})")
        if outliers:
            messages.append(
                f"WARNING: {len(outliers)} selecoes com delta > "
                f"{MAX_DELTA_WARNING}:"
            )
            for o in outliers:
                messages.append(f"  {o}")

    return ok, messages


def validate_name_coverage(elo_data: dict[str, int]) -> list[str]:
    """Verifica cobertura de nomes entre Elo e results.csv."""
    messages = []

    # Check all 48 cup teams
    missing_cup = []
    for team in WORLD_CUP_TEAMS:
        elo_name = model_name_to_elo_name(team)
        if elo_name not in elo_data:
            missing_cup.append(team)
    if missing_cup:
        messages.append(f"Selecoes da Copa sem Elo: {missing_cup}")
    else:
        messages.append(f"Todas as 48 selecoes da Copa tem Elo: OK")

    # Check results.csv teams (those with games vs cup teams since 2022)
    csv_path = os.path.join(PROJECT_DIR, "results.csv")
    if os.path.exists(csv_path):
        from datetime import datetime as dt
        cutoff = dt(2022, 1, 1).toordinal()
        csv_teams = set()
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    d = dt.strptime(row["date"], "%Y-%m-%d")
                    if d.toordinal() >= cutoff:
                        csv_teams.add(row["home_team"])
                        csv_teams.add(row["away_team"])
                except (ValueError, KeyError):
                    continue

        elo_csv_names = {elo_name_to_csv_name(n) for n in elo_data}
        unmapped = csv_teams - elo_csv_names
        # Filter to only teams with games vs cup teams
        cup_set = set(WORLD_CUP_TEAMS)
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            relevant_unmapped = set()
            for row in reader:
                try:
                    d = dt.strptime(row["date"], "%Y-%m-%d")
                    if d.toordinal() < cutoff:
                        continue
                    h, a = row["home_team"], row["away_team"]
                    if h in unmapped and a in cup_set:
                        relevant_unmapped.add(h)
                    if a in unmapped and h in cup_set:
                        relevant_unmapped.add(a)
                except (ValueError, KeyError):
                    continue

        if relevant_unmapped:
            messages.append(
                f"WARNING: {len(relevant_unmapped)} times do results.csv "
                f"(com jogos vs Copa) sem Elo:"
            )
            for t in sorted(relevant_unmapped):
                messages.append(f"  {t}")
        else:
            messages.append(
                "Todos os times relevantes do results.csv tem Elo: OK"
            )

    return messages


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def load_csv_as_dict(path: str) -> dict[str, int]:
    """Le CSV (elo_name, rating) e retorna dict com nomes originais."""
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                result[row["team"]] = int(row["elo"])
            except (ValueError, KeyError):
                continue
    return result


def save_csv(elo_data: dict[str, int], path: str) -> None:
    """Salva dict de Elos como CSV ordenado por rating decrescente."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sorted_data = sorted(elo_data.items(), key=lambda x: x[1], reverse=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["team", "elo"])
        for name, rating in sorted_data:
            writer.writerow([name, rating])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_update() -> bool:
    """Executa o bot. Retorna True se sucesso."""
    print("=" * 60)
    print("  ATUALIZACAO DE ELO RATINGS — eloratings.net")
    print("=" * 60)

    # Fetch
    print("\nBaixando dados de eloratings.net...")
    try:
        elo_data = fetch_elo_ratings()
    except requests.RequestException as e:
        print(f"ERRO: Falha ao acessar eloratings.net: {e}")
        return False

    print(f"  {len(elo_data)} selecoes extraidas")
    top5 = sorted(elo_data.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"  Top 5: {[(t, e) for t, e in top5]}")

    # Validate
    print("\nValidando...")
    ok, messages = validate_scraped(elo_data, LATEST_CSV)
    for msg in messages:
        print(f"  {msg}")

    if not ok:
        print("\nValidacao falhou. CSV NAO sobrescrito.")
        return False

    # Name coverage
    print("\nVerificando cobertura de nomes...")
    coverage_msgs = validate_name_coverage(elo_data)
    for msg in coverage_msgs:
        print(f"  {msg}")

    # Save
    today = date.today().isoformat()
    snapshot_path = os.path.join(HISTORY_DIR, f"elo_ratings_{today}.csv")

    save_csv(elo_data, LATEST_CSV)
    save_csv(elo_data, snapshot_path)

    print(f"\nSalvo:")
    print(f"  {LATEST_CSV}")
    print(f"  {snapshot_path}")
    print(f"\nUpdate concluido com sucesso.")
    return True


def run_check() -> None:
    """Valida CSV existente sem baixar."""
    print("=" * 60)
    print("  VALIDACAO DO CSV DE ELO RATINGS")
    print("=" * 60)

    if not os.path.exists(LATEST_CSV):
        print(f"\nERRO: {LATEST_CSV} nao encontrado.")
        print("Rode sem --check para baixar.")
        sys.exit(1)

    elo_data = load_csv_as_dict(LATEST_CSV)
    print(f"\n  {len(elo_data)} selecoes no CSV")

    mtime = os.path.getmtime(LATEST_CSV)
    mdate = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    print(f"  Ultima modificacao: {mdate}")

    ok, messages = validate_scraped(elo_data)
    for msg in messages:
        print(f"  {msg}")

    coverage_msgs = validate_name_coverage(elo_data)
    for msg in coverage_msgs:
        print(f"  {msg}")

    if ok:
        print("\nCSV valido.")
    else:
        print("\nCSV tem problemas.")


def main():
    if "--check" in sys.argv:
        run_check()
    else:
        success = run_update()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

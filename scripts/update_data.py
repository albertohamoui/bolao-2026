"""
Scraper de Elo ratings e Transfermarkt values para os 48 times da Copa 2026.

Fontes:
    Elo:  eloratings.net (TSV endpoints)
    TM:   transfermarkt.com (pagina de participantes da Copa)

Uso standalone:
    python3 scripts/update_data.py

Uso como biblioteca:
    from scripts.update_data import update_elo_ratings, update_transfermarkt_values
    result = update_elo_ratings(target_teams)
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz, process

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ELO_WORLD_TSV = "https://www.eloratings.net/World.tsv"
ELO_TEAMS_TSV = "https://www.eloratings.net/en.teams.tsv"

TM_PARTICIPANTS_URL = (
    "https://www.transfermarkt.com/weltmeisterschaft/teilnehmer"
    "/pokalwettbewerb/FIWC/saison_id/2025"
)

FUZZY_THRESHOLD = 85
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ALIASES_PATH = os.path.join(SCRIPT_DIR, "team_aliases.json")


# ---------------------------------------------------------------------------
# ScrapeResult
# ---------------------------------------------------------------------------

@dataclass
class ScrapeResult:
    source: str                                   # "elo" | "tm"
    success: dict[str, int | float] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    unmatched_external: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    total_in_source: int = 0


# ---------------------------------------------------------------------------
# Aliases
# ---------------------------------------------------------------------------

def load_aliases(aliases_path: str = DEFAULT_ALIASES_PATH) -> dict:
    """Carrega o JSON de aliases. Cria vazio se nao existir."""
    if not os.path.exists(aliases_path):
        data = {"elo": {}, "tm": {}}
        os.makedirs(os.path.dirname(aliases_path) or ".", exist_ok=True)
        with open(aliases_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data
    with open(aliases_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_alias(
    canonical: str,
    external: str,
    source: str,
    aliases_path: str = DEFAULT_ALIASES_PATH,
) -> None:
    """Adiciona/atualiza alias. canonical = nome no modelo, external = nome no site."""
    data = load_aliases(aliases_path)
    if source not in data:
        data[source] = {}
    data[source][canonical] = external
    with open(aliases_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Name resolution
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def resolve_team_name(
    canonical: str,
    candidates: list[str],
    aliases: dict,
    source: str,
) -> Optional[str]:
    """
    Tenta resolver canonical -> nome externo usando 5 camadas:
    1. Match exato
    2. Case-insensitive
    3. Sem acentos
    4. Alias salvo
    5. Fuzzy match
    """
    # 1. Exato
    if canonical in candidates:
        return canonical

    # 2. Case-insensitive
    lower_map = {c.lower(): c for c in candidates}
    if canonical.lower() in lower_map:
        return lower_map[canonical.lower()]

    # 3. Sem acentos
    stripped = _strip_accents(canonical).lower()
    for c in candidates:
        if _strip_accents(c).lower() == stripped:
            return c

    # 4. Alias salvo
    source_aliases = aliases.get(source, {})
    alias_name = source_aliases.get(canonical)
    if alias_name and alias_name in candidates:
        return alias_name
    # Tambem checa alias sem acento / case-insensitive
    if alias_name:
        alias_stripped = _strip_accents(alias_name).lower()
        for c in candidates:
            if _strip_accents(c).lower() == alias_stripped:
                return c

    # 5. Fuzzy match
    result = process.extractOne(
        canonical, candidates, scorer=fuzz.token_sort_ratio,
        score_cutoff=FUZZY_THRESHOLD,
    )
    if result:
        return result[0]

    return None


# ---------------------------------------------------------------------------
# Elo scraper
# ---------------------------------------------------------------------------

def update_elo_ratings(
    target_teams: list[str],
    aliases_path: str = DEFAULT_ALIASES_PATH,
) -> ScrapeResult:
    """Busca Elo ratings atualizados do eloratings.net via TSV."""
    result = ScrapeResult(source="elo")
    aliases = load_aliases(aliases_path)

    # --- Fetch team name mapping (code -> name) ---
    try:
        log.info("Fetching %s", ELO_TEAMS_TSV)
        resp = requests.get(ELO_TEAMS_TSV, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        result.errors.append(f"Erro ao buscar en.teams.tsv: {e}")
        result.failed = list(target_teams)
        return result

    code_to_name: dict[str, str] = {}
    for line in resp.text.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and "_loc" not in parts[0]:
            code = parts[0].strip()
            name = parts[1].strip()
            code_to_name[code] = name

    log.info("  %d codigos de time carregados", len(code_to_name))

    # --- Fetch world rankings ---
    try:
        log.info("Fetching %s", ELO_WORLD_TSV)
        resp = requests.get(ELO_WORLD_TSV, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        result.errors.append(f"Erro ao buscar World.tsv: {e}")
        result.failed = list(target_teams)
        return result

    # Parse: col[2] = country code, col[3] = elo rating
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

    result.total_in_source = len(elo_by_name)
    log.info("  %d times com Elo parseados", result.total_in_source)

    # --- Match against target teams ---
    external_names = list(elo_by_name.keys())
    matched_external = set()

    for team in target_teams:
        match = resolve_team_name(team, external_names, aliases, "elo")
        if match and match in elo_by_name:
            result.success[team] = elo_by_name[match]
            matched_external.add(match)
        else:
            result.failed.append(team)

    result.unmatched_external = [
        n for n in external_names if n not in matched_external
    ]

    if result.failed:
        log.warning("  %d times nao encontrados: %s", len(result.failed), result.failed)
    log.info("  %d/%d times atualizados com sucesso",
             len(result.success), len(target_teams))

    return result


# ---------------------------------------------------------------------------
# Transfermarkt scraper
# ---------------------------------------------------------------------------

def _parse_tm_value(text: str) -> Optional[int]:
    """Converte '€1.62bn', '€864.50m', '€55.40m' etc pra inteiro em milhoes."""
    text = text.strip().replace("\xa0", "").replace(" ", "")
    # Remove simbolo de euro
    text = text.replace("€", "").replace("$", "")

    m = re.match(r"([\d.,]+)\s*(bn|m|k|Mrd\.|Mio\.|Tsd\.)?", text, re.IGNORECASE)
    if not m:
        return None

    num_str = m.group(1).replace(",", ".")
    # Handle cases like "1.62" where comma was already a dot
    # If there are multiple dots, keep only the last as decimal
    dots = num_str.count(".")
    if dots > 1:
        parts = num_str.split(".")
        num_str = "".join(parts[:-1]) + "." + parts[-1]

    try:
        num = float(num_str)
    except ValueError:
        return None

    suffix = (m.group(2) or "").lower().rstrip(".")
    if suffix in ("bn", "mrd"):
        return round(num * 1000)  # bilhoes -> milhoes
    elif suffix in ("m", "mio"):
        return round(num)
    elif suffix in ("k", "tsd"):
        return max(1, round(num / 1000))
    else:
        # Sem sufixo — assume milhoes se > 1, senao ignora
        if num > 1:
            return round(num)
        return None


def update_transfermarkt_values(
    target_teams: list[str],
    aliases_path: str = DEFAULT_ALIASES_PATH,
) -> ScrapeResult:
    """Busca valores de elenco atualizados do Transfermarkt."""
    result = ScrapeResult(source="tm")
    aliases = load_aliases(aliases_path)

    try:
        log.info("Fetching %s", TM_PARTICIPANTS_URL)
        resp = requests.get(
            TM_PARTICIPANTS_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        result.errors.append(f"Erro ao buscar pagina TM: {e}")
        result.failed = list(target_teams)
        return result

    soup = BeautifulSoup(resp.text, "html.parser")

    # A tabela de participantes tem class="items"
    table = soup.find("table", class_="items")
    if not table:
        result.errors.append("Tabela 'items' nao encontrada na pagina")
        result.failed = list(target_teams)
        return result

    tbody = table.find("tbody")
    if not tbody:
        result.errors.append("tbody nao encontrado na tabela")
        result.failed = list(target_teams)
        return result

    # Parse cada linha da tabela
    tm_by_name: dict[str, int] = {}
    rows = tbody.find_all("tr")

    for row in rows:
        # Nome do time: dentro de <td class="hauptlink"> ou <a> dentro de td
        name_cell = row.find("td", class_="hauptlink")
        if not name_cell:
            # Tenta alternativa: primeiro <a> com title
            link = row.find("a", title=True)
            if link:
                team_name = link.get("title", "").strip()
            else:
                continue
        else:
            link = name_cell.find("a")
            team_name = link.get_text(strip=True) if link else name_cell.get_text(strip=True)

        if not team_name:
            continue

        # Valor: ultima celula com class="rechts" que contem € ou cifra
        value_cells = row.find_all("td", class_="rechts")
        value = None
        for vc in value_cells:
            txt = vc.get_text(strip=True)
            if "€" in txt or "bn" in txt or "m" in txt.lower():
                value = _parse_tm_value(txt)
                if value is not None:
                    break

        if value is not None:
            tm_by_name[team_name] = value

    result.total_in_source = len(tm_by_name)
    log.info("  %d times com valor parseados", result.total_in_source)

    if not tm_by_name:
        result.errors.append("Nenhum time parseado da tabela — possivel mudanca de layout")
        result.failed = list(target_teams)
        return result

    # --- Match against target teams ---
    external_names = list(tm_by_name.keys())
    matched_external = set()

    for team in target_teams:
        match = resolve_team_name(team, external_names, aliases, "tm")
        if match and match in tm_by_name:
            result.success[team] = tm_by_name[match]
            matched_external.add(match)
        else:
            result.failed.append(team)

    result.unmatched_external = [
        n for n in external_names if n not in matched_external
    ]

    if result.failed:
        log.warning("  %d times nao encontrados: %s", len(result.failed), result.failed)
    log.info("  %d/%d times atualizados com sucesso",
             len(result.success), len(target_teams))

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_diff(label: str, scraped: dict[str, int], defaults: dict[str, int],
                threshold: int = 10) -> None:
    """Imprime diff entre valores scrapeados e defaults."""
    changes = []
    for team in sorted(scraped.keys()):
        old = defaults.get(team)
        new = scraped[team]
        if old is not None and abs(new - old) >= threshold:
            delta = new - old
            changes.append((team, old, new, delta))

    if not changes:
        print(f"  Nenhuma mudanca >= {threshold} vs defaults")
        return

    changes.sort(key=lambda x: abs(x[3]), reverse=True)
    print(f"\n  Diff vs {label} (mudancas >= {threshold}):")
    for team, old, new, delta in changes:
        sign = "+" if delta > 0 else ""
        print(f"    {team:<30} {old:>6} -> {new:>6} ({sign}{delta})")


def main():
    import sys
    sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
    from bolao2026 import (
        DEFAULT_ELO_RATINGS,
        DEFAULT_TRANSFERMARKT_VALUES,
        GROUPS,
    )

    target_teams = sorted({t for g in GROUPS.values() for t in g})

    print("=" * 60)
    print("  ATUALIZANDO ELO")
    print("=" * 60)

    elo_result = update_elo_ratings(target_teams)

    print(f"\n  Fonte: eloratings.net | {elo_result.total_in_source} times na fonte")
    print(f"  Sucesso: {len(elo_result.success)}/{len(target_teams)}")
    if elo_result.failed:
        print(f"  Falharam: {elo_result.failed}")
    if elo_result.errors:
        print(f"  Erros: {elo_result.errors}")

    if elo_result.success:
        _print_diff("DEFAULT_ELO_RATINGS", elo_result.success, DEFAULT_ELO_RATINGS)

    print()
    print("=" * 60)
    print("  ATUALIZANDO TRANSFERMARKT")
    print("=" * 60)

    tm_result = update_transfermarkt_values(target_teams)

    print(f"\n  Fonte: transfermarkt.com | {tm_result.total_in_source} times na fonte")
    print(f"  Sucesso: {len(tm_result.success)}/{len(target_teams)}")
    if tm_result.failed:
        print(f"  Falharam: {tm_result.failed}")
    if tm_result.errors:
        print(f"  Erros: {tm_result.errors}")

    if tm_result.success:
        _print_diff("DEFAULT_TRANSFERMARKT_VALUES", tm_result.success,
                     DEFAULT_TRANSFERMARKT_VALUES, threshold=5)

    # Resumo de unmatched pra ajudar a popular aliases
    if elo_result.unmatched_external:
        print(f"\n  [Elo] Nomes no site sem match ({len(elo_result.unmatched_external)} "
              f"de {elo_result.total_in_source}):")
        # So mostra os que tem alguma relevancia (fuzzy > 50 com algum target)
        for ext in sorted(elo_result.unmatched_external):
            best = process.extractOne(ext, target_teams, scorer=fuzz.token_sort_ratio)
            if best and best[1] > 50:
                print(f"    '{ext}' ~> '{best[0]}' ({best[1]}%)")

    if tm_result.unmatched_external:
        print(f"\n  [TM] Nomes no site sem match ({len(tm_result.unmatched_external)} "
              f"de {tm_result.total_in_source}):")
        for ext in sorted(tm_result.unmatched_external):
            best = process.extractOne(ext, target_teams, scorer=fuzz.token_sort_ratio)
            if best and best[1] > 50:
                print(f"    '{ext}' ~> '{best[0]}' ({best[1]}%)")

    print()
    print("=" * 60)
    print("  CONCLUIDO")
    print("=" * 60)
    print(f"  Elo:  {len(elo_result.success)}/{len(target_teams)} ok"
          f" | {len(elo_result.failed)} falhas | {len(elo_result.errors)} erros")
    print(f"  TM:   {len(tm_result.success)}/{len(target_teams)} ok"
          f" | {len(tm_result.failed)} falhas | {len(tm_result.errors)} erros")


if __name__ == "__main__":
    main()

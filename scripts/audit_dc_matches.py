#!/usr/bin/env python3
"""
Auditoria do filtro de jogos do Dixon-Coles fitting.

Replica exatamente a cadeia de filtros que o pipeline de producao aplica
antes dos jogos entrarem na MLE, reporta contagens e salva CSVs.

Uso:
    python scripts/audit_dc_matches.py
"""

import csv
import os
import sys
from datetime import datetime
from collections import Counter

# Garante import do modulo principal
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)

from bolao2026 import load_config


def main():
    config_path = os.path.join(PROJECT_DIR, "config.json")
    csv_path = os.path.join(PROJECT_DIR, "results.csv")

    cal = load_config(config_path)
    model_teams = set(cal.elo_ratings.keys())

    # =====================================================================
    # Filtro exato do codigo de producao
    # =====================================================================
    print("=" * 70)
    print("  AUDITORIA DO FILTRO DE JOGOS — DIXON-COLES FITTING")
    print("=" * 70)

    print("\n--- Filtro aplicado pelo pipeline de producao ---\n")

    print("1. load_matches(filepath):")
    print("   Descarta linhas com date, home_score ou away_score invalidos")
    print("   (ValueError/KeyError no parse). Perde a coluna 'tournament'.")
    print()
    print("2. Pipeline (run_full_pipeline):")
    print("   recent = [m for m in matches if m[4] >= cutoff]")
    print(f"   cutoff = datetime.strptime('{cal.date_cutoff}', '%Y-%m-%d').toordinal()")
    print()
    print("3. fit():")
    print("   valid = [(h,a,hg,ag,d) for h,a,hg,ag,d in matches")
    print("            if h in self.team_idx and a in self.team_idx]")
    print(f"   self.team_idx = {{t: i for i, t in enumerate(sorted(cal.elo_ratings.keys()))}}")
    print(f"   ({len(model_teams)} times no modelo)")
    print()
    print("4. _log_likelihood():")
    print("   for i, (home, away, hg, ag, _) in enumerate(matches):")
    print("       hi = self.team_idx.get(home)")
    print("       ai = self.team_idx.get(away)")
    print("       if hi is None or ai is None: continue")
    print("   (Redundante com filtro #3 — mesma condicao)")

    # =====================================================================
    # Carregar dados com campo tournament preservado
    # =====================================================================
    cutoff_dt = datetime.strptime(cal.date_cutoff, "%Y-%m-%d")
    cutoff_ord = cutoff_dt.toordinal()

    all_rows = []
    parse_errors = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = datetime.strptime(row["date"], "%Y-%m-%d")
                hg = int(row["home_score"])
                ag = int(row["away_score"])
                all_rows.append({
                    "date": row["date"],
                    "date_ordinal": d.toordinal(),
                    "home": row["home_team"],
                    "away": row["away_team"],
                    "home_score": hg,
                    "away_score": ag,
                    "tournament": row.get("tournament", ""),
                })
            except (ValueError, KeyError):
                parse_errors += 1

    total_csv = len(all_rows) + parse_errors

    # Filtro 2: data
    after_date = [r for r in all_rows if r["date_ordinal"] >= cutoff_ord]

    # Filtro 3: ambos os times no modelo
    included = []
    excluded = []
    for r in after_date:
        h_in = r["home"] in model_teams
        a_in = r["away"] in model_teams
        if h_in and a_in:
            included.append(r)
        else:
            reasons = []
            if not h_in:
                reasons.append(f"home '{r['home']}' nao esta em elo_ratings")
            if not a_in:
                reasons.append(f"away '{r['away']}' nao esta em elo_ratings")
            r["motivo_exclusao"] = "; ".join(reasons)
            excluded.append(r)

    # =====================================================================
    # Contagens
    # =====================================================================
    print("\n" + "=" * 70)
    print("  CONTAGENS")
    print("=" * 70)

    print(f"\n  Total de linhas em results.csv:            {total_csv:>7,}")
    print(f"  Linhas com parse error (descartadas):       {parse_errors:>7,}")
    print(f"  Jogos parseados com sucesso:                {len(all_rows):>7,}")
    print(f"  Apos filtro de data (>= {cal.date_cutoff}): {len(after_date):>7,}")
    print(f"  Passam no filtro do fit() (ambos times):    {len(included):>7,}")
    print(f"  Excluidos pelo fit() (time fora do modelo): {len(excluded):>7,}")

    # Times distintos
    teams_in_included = set()
    for r in included:
        teams_in_included.add(r["home"])
        teams_in_included.add(r["away"])

    print(f"\n  Times distintos nos jogos incluidos:        {len(teams_in_included):>7}")
    print(f"  Times no elo_ratings:                       {len(model_teams):>7}")

    # Times do elo_ratings sem jogos
    missing = model_teams - teams_in_included
    if missing:
        print(f"\n  Times do elo_ratings SEM nenhum jogo na lista filtrada:")
        for t in sorted(missing):
            print(f"    - {t}")
    else:
        print(f"\n  Todos os times do elo_ratings aparecem em pelo menos 1 jogo.")

    # =====================================================================
    # Contagem por selecao
    # =====================================================================
    print("\n" + "=" * 70)
    print("  JOGOS POR SELECAO")
    print("=" * 70)

    # Jogos no fit (included)
    fit_count = Counter()
    for r in included:
        fit_count[r["home"]] += 1
        fit_count[r["away"]] += 1

    # Jogos totais apos cutoff (independente de entrar no fit)
    total_count = Counter()
    for r in after_date:
        total_count[r["home"]] += 1
        total_count[r["away"]] += 1

    rows_per_team = []
    for t in sorted(model_teams):
        fc = fit_count.get(t, 0)
        tc = total_count.get(t, 0)
        rows_per_team.append((t, fc, tc, tc - fc))

    # Ordena por diferenca decrescente
    rows_per_team.sort(key=lambda x: x[3], reverse=True)

    print(f"\n  {'Selecao':<30} {'No fit':>7} {'Total':>7} {'Diferenca':>10}")
    print(f"  {'-'*58}")
    for t, fc, tc, diff in rows_per_team:
        flag = "  <<" if diff > 20 else ""
        print(f"  {t:<30} {fc:>7} {tc:>7} {diff:>+10}{flag}")

    # =====================================================================
    # Salvar CSVs
    # =====================================================================
    audits_dir = os.path.join(PROJECT_DIR, "audits")
    os.makedirs(audits_dir, exist_ok=True)
    included_path = os.path.join(audits_dir, "audit_dc_matches.csv")
    excluded_path = os.path.join(audits_dir, "audit_dc_excluded.csv")

    with open(included_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "home", "away", "home_score", "away_score", "tournament"
        ])
        writer.writeheader()
        for r in sorted(included, key=lambda x: x["date"]):
            writer.writerow({
                "date": r["date"],
                "home": r["home"],
                "away": r["away"],
                "home_score": r["home_score"],
                "away_score": r["away_score"],
                "tournament": r["tournament"],
            })

    with open(excluded_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "home", "away", "home_score", "away_score",
            "tournament", "motivo_exclusao"
        ])
        writer.writeheader()
        for r in sorted(excluded, key=lambda x: x["date"]):
            writer.writerow({
                "date": r["date"],
                "home": r["home"],
                "away": r["away"],
                "home_score": r["home_score"],
                "away_score": r["away_score"],
                "tournament": r["tournament"],
                "motivo_exclusao": r["motivo_exclusao"],
            })

    print(f"\n  CSVs salvos:")
    print(f"    {included_path} ({len(included)} jogos)")
    print(f"    {excluded_path} ({len(excluded)} jogos)")

    # Top 10 times excluidos mais frequentes
    excluded_teams = Counter()
    for r in excluded:
        if r["home"] not in model_teams:
            excluded_teams[r["home"]] += 1
        if r["away"] not in model_teams:
            excluded_teams[r["away"]] += 1

    if excluded_teams:
        print(f"\n  Top 15 times fora do modelo mais frequentes nos jogos excluidos:")
        for t, c in excluded_teams.most_common(15):
            print(f"    {t:<30} {c:>5} jogos")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Backtest do modelo contra a Copa do Mundo 2022 no Catar.

Valida empiricamente se o modelo acerta mais pontos de bolao que
estrategias-baseline quando aplicado a uma Copa com resultados conhecidos.

Uso:
    python scripts/backtest_2022.py

Limitacoes documentadas:
    - Elos e Transfermarkt usam valores ATUAIS (2026), nao de novembro/2022.
      Isso e data leakage que pode favorecer ou prejudicar o modelo.
    - O modelo foi calibrado com a mesma arquitetura DC+blend usada em producao,
      mas com cutoff temporal pre-Copa 2022.
"""

import csv
import os
import sys
from datetime import datetime
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)

import numpy as np
from bolao2026 import (
    Calibration,
    DixonColesModel,
    WORLD_CUP_TEAM_LIST as WC2026_TEAMS,
    _EXTERNAL_TO_MODEL_NAME,
    bolao_points,
    ev_optimal_score,
    load_config,
    load_matches,
    load_world_elo,
)

# =============================================================================
# DADOS DA COPA 2022
# =============================================================================

GROUPS_2022 = {
    "A": ["Qatar", "Ecuador", "Senegal", "Netherlands"],
    "B": ["England", "Iran", "United States", "Wales"],
    "C": ["Argentina", "Saudi Arabia", "Mexico", "Poland"],
    "D": ["France", "Australia", "Denmark", "Tunisia"],
    "E": ["Spain", "Costa Rica", "Germany", "Japan"],
    "F": ["Belgium", "Canada", "Morocco", "Croatia"],
    "G": ["Brazil", "Serbia", "Switzerland", "Cameroon"],
    "H": ["Portugal", "Ghana", "Uruguay", "South Korea"],
}

WC2022_TEAMS = sorted({t for g in GROUPS_2022.values() for t in g})
WC2022_CUTOFF_DATE = "2022-11-20"
WC2022_TRAIN_CUTOFF = "2018-01-01"

# Confederacoes (para analise de erros)
CONFEDERATIONS_2022 = {
    "Qatar": "AFC", "Ecuador": "CONMEBOL", "Senegal": "CAF", "Netherlands": "UEFA",
    "England": "UEFA", "Iran": "AFC", "United States": "CONCACAF", "Wales": "UEFA",
    "Argentina": "CONMEBOL", "Saudi Arabia": "AFC", "Mexico": "CONCACAF", "Poland": "UEFA",
    "France": "UEFA", "Australia": "AFC", "Denmark": "UEFA", "Tunisia": "CAF",
    "Spain": "UEFA", "Costa Rica": "CONCACAF", "Germany": "UEFA", "Japan": "AFC",
    "Belgium": "UEFA", "Canada": "CONCACAF", "Morocco": "CAF", "Croatia": "UEFA",
    "Brazil": "CONMEBOL", "Serbia": "UEFA", "Switzerland": "UEFA", "Cameroon": "CAF",
    "Portugal": "UEFA", "Ghana": "CAF", "Uruguay": "CONMEBOL", "South Korea": "AFC",
}


def load_wc2022_results(csv_path):
    """Carrega resultados reais da Copa 2022 do results.csv."""
    group_results = []
    knockout_results = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "FIFA World Cup" not in row.get("tournament", ""):
                continue
            if row["date"] < WC2022_CUTOFF_DATE or row["date"] > "2022-12-18":
                continue

            home = _EXTERNAL_TO_MODEL_NAME.get(row["home_team"], row["home_team"])
            away = _EXTERNAL_TO_MODEL_NAME.get(row["away_team"], row["away_team"])
            hg = int(row["home_score"])
            ag = int(row["away_score"])
            date = row["date"]

            match = {"home": home, "away": away, "hg": hg, "ag": ag, "date": date}

            # Primeiros 48 jogos = fase de grupos, restantes = mata-mata
            if len(group_results) < 48:
                group_results.append(match)
            else:
                knockout_results.append(match)

    return group_results, knockout_results


def train_model_pre2022(csv_path, config_path):
    """Treina o modelo com dados anteriores a Copa 2022."""
    # Carrega config base e ajusta para backtest
    cal = load_config(config_path)
    cal.date_cutoff = WC2022_TRAIN_CUTOFF

    # Carrega Elos (atuais - limitacao documentada)
    world_elo = load_world_elo()

    # O blend bayesiano itera sobre WORLD_CUP_TEAM_LIST (48 da Copa 2026),
    # entao cal.elo_ratings precisa ter TODOS esses 48 times.
    # Isso nao afeta o backtest — previsoes sao feitas so pros 32 da Copa 2022.
    cup_elo_full = {t: world_elo[t] for t in WC2026_TEAMS if t in world_elo}
    cal.elo_ratings = cup_elo_full

    # Modelo DC com universo amplo
    all_teams = list(world_elo.keys())
    model = DixonColesModel(all_teams, cal, world_elo=world_elo)

    # Carregar jogos e filtrar para antes da Copa
    matches = load_matches(csv_path)
    cutoff_dt = datetime.strptime(WC2022_CUTOFF_DATE, "%Y-%m-%d")
    cutoff_ord = cutoff_dt.toordinal()
    train_cutoff_dt = datetime.strptime(WC2022_TRAIN_CUTOFF, "%Y-%m-%d")
    train_cutoff_ord = train_cutoff_dt.toordinal()

    pre_wc = [m for m in matches if m[4] >= train_cutoff_ord and m[4] < cutoff_ord]
    print(f"Jogos de treino ({WC2022_TRAIN_CUTOFF} a {WC2022_CUTOFF_DATE}): {len(pre_wc):,}")

    model.fit(pre_wc)
    return model, cal


def generate_predictions(model, cal):
    """Gera previsoes EV-optimal para todos os jogos da fase de grupos."""
    predictions = {}

    for gname, teams in sorted(GROUPS_2022.items()):
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                h, a = teams[i], teams[j]
                pred = model.predict_match(h, a, host_adv=0.0)
                ev_score, ev_pts = ev_optimal_score(pred["score_matrix"], knockout=False)

                key = f"{h} vs {a}"
                predictions[key] = {
                    "home": h,
                    "away": a,
                    "group": gname,
                    "bet": ev_score,
                    "ev_pts": ev_pts,
                    "score_matrix": pred["score_matrix"],
                    "lambdas": pred["lambdas"],
                }

    return predictions


def generate_knockout_predictions(model, knockout_results):
    """Gera previsoes EV-optimal para jogos de mata-mata."""
    predictions = []
    for m in knockout_results:
        h, a = m["home"], m["away"]
        try:
            pred = model.predict_match(h, a, host_adv=0.0)
            ev_score, ev_pts = ev_optimal_score(pred["score_matrix"], knockout=True)
            predictions.append({
                "home": h,
                "away": a,
                "bet": ev_score,
                "ev_pts": ev_pts,
            })
        except KeyError:
            # Time sem parametros (nao estava no fit)
            predictions.append({
                "home": h,
                "away": a,
                "bet": (1, 0),
                "ev_pts": 0,
            })
    return predictions


def baseline_elo_favorite(home, away, elo, score):
    """Retorna aposta no favorito Elo com placar dado."""
    elo_h = elo.get(home, 1500)
    elo_a = elo.get(away, 1500)
    if elo_h >= elo_a:
        return score  # home favorito
    else:
        return (score[1], score[0])  # away favorito


def score_strategy(bets, results, knockout=False):
    """Pontua uma lista de apostas contra resultados reais."""
    total = 0
    details = []
    for bet_info, result in zip(bets, results):
        bet = bet_info if isinstance(bet_info, tuple) else bet_info["bet"]
        actual = (result["hg"], result["ag"])
        pts = bolao_points(bet, actual, knockout=knockout)
        total += pts
        details.append({
            "home": result["home"],
            "away": result["away"],
            "bet": f"{bet[0]}x{bet[1]}",
            "actual": f"{actual[0]}x{actual[1]}",
            "pts": pts,
        })
    return total, details


def match_predictions_to_results(predictions, group_results):
    """Alinha previsoes com resultados na mesma ordem."""
    bets = []
    for result in group_results:
        h, a = result["home"], result["away"]
        # Procurar nos dois sentidos
        key1 = f"{h} vs {a}"
        key2 = f"{a} vs {h}"
        if key1 in predictions:
            bets.append(predictions[key1]["bet"])
        elif key2 in predictions:
            # Inverter o placar
            pred_bet = predictions[key2]["bet"]
            bets.append((pred_bet[1], pred_bet[0]))
        else:
            print(f"WARNING: Jogo nao encontrado nas previsoes: {h} vs {a}")
            bets.append((1, 1))
    return bets


def main():
    csv_path = os.path.join(PROJECT_DIR, "results.csv")
    config_path = os.path.join(PROJECT_DIR, "config.json")

    print("=" * 70)
    print("  BACKTEST — Copa do Mundo 2022 (Catar)")
    print("=" * 70)

    # --- Etapa 1: Carregar resultados reais ---
    print("\n--- Etapa 1: Carregando resultados reais ---")
    group_results, knockout_results = load_wc2022_results(csv_path)
    print(f"Jogos fase de grupos: {len(group_results)}")
    print(f"Jogos mata-mata: {len(knockout_results)}")

    # --- Etapa 2: Treinar modelo ---
    print("\n--- Etapa 2: Treinando modelo (dados pre-Copa 2022) ---")
    model, cal = train_model_pre2022(csv_path, config_path)
    world_elo = load_world_elo()

    # --- Etapa 3: Gerar previsoes ---
    print("\n--- Etapa 3: Gerando previsoes ---")
    predictions = generate_predictions(model, cal)
    knockout_predictions = generate_knockout_predictions(model, knockout_results)
    print(f"Previsoes fase de grupos: {len(predictions)} jogos")
    print(f"Previsoes mata-mata: {len(knockout_predictions)} jogos")

    # --- Etapa 4: Pontuar todas as estrategias ---
    print("\n--- Etapa 4: Pontuando estrategias ---")

    # Modelo EV-optimal
    model_bets_groups = match_predictions_to_results(predictions, group_results)
    model_pts_groups, model_details_groups = score_strategy(
        model_bets_groups, group_results, knockout=False
    )
    model_pts_ko, model_details_ko = score_strategy(
        knockout_predictions, knockout_results, knockout=True
    )

    # Baselines (fase de grupos)
    b1_bets = [baseline_elo_favorite(r["home"], r["away"], world_elo, (1, 0))
               for r in group_results]
    b2_bets = [baseline_elo_favorite(r["home"], r["away"], world_elo, (2, 1))
               for r in group_results]
    b3_bets = [(1, 1) for _ in group_results]

    b1_pts_groups, b1_details = score_strategy(b1_bets, group_results, knockout=False)
    b2_pts_groups, b2_details = score_strategy(b2_bets, group_results, knockout=False)
    b3_pts_groups, b3_details = score_strategy(b3_bets, group_results, knockout=False)

    # Baselines (mata-mata)
    b1_ko_bets = [{"bet": baseline_elo_favorite(r["home"], r["away"], world_elo, (1, 0))}
                  for r in knockout_results]
    b2_ko_bets = [{"bet": baseline_elo_favorite(r["home"], r["away"], world_elo, (2, 1))}
                  for r in knockout_results]
    b3_ko_bets = [{"bet": (1, 1)} for _ in knockout_results]

    b1_pts_ko, _ = score_strategy(b1_ko_bets, knockout_results, knockout=True)
    b2_pts_ko, _ = score_strategy(b2_ko_bets, knockout_results, knockout=True)
    b3_pts_ko, _ = score_strategy(b3_ko_bets, knockout_results, knockout=True)

    # =================================================================
    # RELATORIO
    # =================================================================

    print("\n" + "=" * 70)
    print("  RELATORIO DE BACKTEST — Copa do Mundo 2022")
    print("=" * 70)

    # --- 1. Pontuacao total por estrategia ---
    print("\n--- 1. PONTUACAO TOTAL POR ESTRATEGIA ---\n")
    print(f"{'Estrategia':<35} {'Grupos':>8} {'Mata-mata':>10} {'TOTAL':>8}")
    print("-" * 65)
    print(f"{'Modelo (EV-optimal)':<35} {model_pts_groups:>8} {model_pts_ko:>10} {model_pts_groups + model_pts_ko:>8}")
    print(f"{'Baseline-1 (Favorito 1x0)':<35} {b1_pts_groups:>8} {b1_pts_ko:>10} {b1_pts_groups + b1_pts_ko:>8}")
    print(f"{'Baseline-2 (Favorito 2x1)':<35} {b2_pts_groups:>8} {b2_pts_ko:>10} {b2_pts_groups + b2_pts_ko:>8}")
    print(f"{'Baseline-3 (Sempre 1x1)':<35} {b3_pts_groups:>8} {b3_pts_ko:>10} {b3_pts_groups + b3_pts_ko:>8}")

    # --- 2. Detalhamento por jogo (fase de grupos) ---
    print("\n--- 2. DETALHAMENTO POR JOGO (FASE DE GRUPOS) ---\n")
    print(f"{'Jogo':<35} {'Aposta':>7} {'Real':>7} {'Pts':>5}  {'B1':>4} {'B2':>4} {'B3':>4}")
    print("-" * 75)
    for i, (md, b1d, b2d, b3d) in enumerate(zip(
            model_details_groups, b1_details, b2_details, b3_details)):
        game = f"{md['home']} vs {md['away']}"
        print(f"{game:<35} {md['bet']:>7} {md['actual']:>7} {md['pts']:>5}  "
              f"{b1d['pts']:>4} {b2d['pts']:>4} {b3d['pts']:>4}")

    # --- 3. Distribuicao de pontos do modelo ---
    print("\n--- 3. DISTRIBUICAO DE ACERTOS (MODELO, GRUPOS) ---\n")

    exact_score = 0
    draw_exact_count = 0
    draw_wrong_count = 0
    diff_count = 0
    winner_goals = 0
    loser_goals = 0
    winner_only = 0
    zero = 0

    for d in model_details_groups:
        bh, ba = map(int, d["bet"].split("x"))
        rh, ra = map(int, d["actual"].split("x"))
        pts = d["pts"]
        if bh == ba:  # bet is draw
            if rh == ra:
                if bh == rh:
                    draw_exact_count += 1
                else:
                    draw_wrong_count += 1
            else:
                zero += 1
        else:
            if (bh, ba) == (rh, ra):
                exact_score += 1
            elif pts == 6:
                diff_count += 1
            elif pts == 5:
                winner_goals += 1
            elif pts == 4:
                loser_goals += 1
            elif pts == 3:
                winner_only += 1
            elif pts == 0:
                zero += 1

    total_games = len(model_details_groups)
    print(f"  Placar exato (vitoria):  {exact_score:>3} / {total_games}  ({exact_score/total_games*100:.1f}%)")
    print(f"  Empate exato:            {draw_exact_count:>3} / {total_games}  ({draw_exact_count/total_games*100:.1f}%)")
    print(f"  Diferenca de gols:       {diff_count:>3} / {total_games}")
    print(f"  Empate placar errado:    {draw_wrong_count:>3} / {total_games}")
    print(f"  Gols do vencedor:        {winner_goals:>3} / {total_games}")
    print(f"  Gols do perdedor:        {loser_goals:>3} / {total_games}")
    print(f"  So o vencedor:           {winner_only:>3} / {total_games}")
    print(f"  Zero (errou tudo):       {zero:>3} / {total_games}  ({zero/total_games*100:.1f}%)")

    # --- 4. Analise de erros sistematicos ---
    print("\n--- 4. ANALISE DE ERROS SISTEMATICOS ---\n")

    # 4a. Favorito claro vs equilibrado
    print("  4a. Por diferenca de Elo entre os times:\n")
    elo_bands = [
        ("Grande (>200 Elo)", lambda h, a: abs(world_elo.get(h, 1500) - world_elo.get(a, 1500)) > 200),
        ("Media (100-200)", lambda h, a: 100 < abs(world_elo.get(h, 1500) - world_elo.get(a, 1500)) <= 200),
        ("Pequena (<100)", lambda h, a: abs(world_elo.get(h, 1500) - world_elo.get(a, 1500)) <= 100),
    ]

    for label, cond in elo_bands:
        matching = [(d, b1) for d, b1 in zip(model_details_groups, b1_details)
                    if cond(d["home"], d["away"])]
        if matching:
            n = len(matching)
            model_avg = sum(d[0]["pts"] for d in matching) / n
            b1_avg = sum(d[1]["pts"] for d in matching) / n
            print(f"    {label:<25}  n={n:>2}  modelo={model_avg:.1f} pts/jogo  baseline1={b1_avg:.1f}")

    # 4b. Por confederacao
    print("\n  4b. Por confederacao do adversario:\n")
    confed_stats = defaultdict(lambda: {"n": 0, "model_pts": 0, "b1_pts": 0})
    for md, b1d in zip(model_details_groups, b1_details):
        for team in [md["home"], md["away"]]:
            conf = CONFEDERATIONS_2022.get(team, "?")
            confed_stats[conf]["n"] += 1
            confed_stats[conf]["model_pts"] += md["pts"]
            confed_stats[conf]["b1_pts"] += b1d["pts"]

    # Cada jogo conta 2x (uma por time), normalizar
    for conf in sorted(confed_stats.keys()):
        s = confed_stats[conf]
        n = s["n"]
        print(f"    {conf:<10}  aparicoes={n:>3}  "
              f"modelo={s['model_pts']/n:.1f} pts/aparicao  "
              f"b1={s['b1_pts']/n:.1f}")

    # --- 5. Comparacao direta ---
    print("\n--- 5. COMPARACAO DIRETA ---\n")

    model_total = model_pts_groups + model_pts_ko
    b1_total = b1_pts_groups + b1_pts_ko
    b2_total = b2_pts_groups + b2_pts_ko
    b3_total = b3_pts_groups + b3_pts_ko

    for name, baseline_total in [
        ("Baseline-1 (Favorito 1x0)", b1_total),
        ("Baseline-2 (Favorito 2x1)", b2_total),
        ("Baseline-3 (Sempre 1x1)", b3_total),
    ]:
        diff = model_total - baseline_total
        if diff > 50:
            verdict = "MODELO VENCE (significativo)"
        elif diff > 20:
            verdict = "MODELO VENCE (marginal)"
        elif diff > 0:
            verdict = "MODELO VENCE (pequeno)"
        elif diff > -20:
            verdict = "EMPATE TECNICO"
        elif diff > -50:
            verdict = "BASELINE VENCE (marginal)"
        else:
            verdict = "BASELINE VENCE (significativo)"
        print(f"  Modelo vs {name}")
        print(f"    {model_total} vs {baseline_total} = {diff:+d} pts  ->  {verdict}")
        print()

    # --- 6. Conclusao ---
    print("--- 6. LIMITACOES ---\n")
    print("  - Elos e Transfermarkt sao de 2026, nao de novembro/2022.")
    print("    Isso constitui data leakage: o modelo 'sabe' a forca futura")
    print("    dos times (ex: Marrocos subiu muito apos a Copa 2022).")
    print("  - O backtest cobre apenas 1 Copa. N=1 nao permite conclusoes")
    print("    estatisticamente robustas sobre superioridade do modelo.")
    print("  - A Copa 2022 teve resultados atipicos (Argentina perdendo pra")
    print("    Arabia Saudita, Japao vencendo Alemanha e Espanha, Marrocos")
    print("    nas semis). Qualquer modelo teria dificuldade nesses jogos.")
    print()

    return {
        "model": model_total,
        "b1": b1_total,
        "b2": b2_total,
        "b3": b3_total,
    }


if __name__ == "__main__":
    main()

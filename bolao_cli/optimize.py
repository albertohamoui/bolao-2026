#!/usr/bin/env python3
"""
Bolao do Cli — Smart Baseline Optimizer.

Grid search sobre thresholds e placares, pontuando com regras do Bolao do Cli.
Testa em backtests 2018 e 2022.

Diferenças vs Bolao Zap:
  - Exato: 5 pts (+ bonus gols)
  - Empate errado: 3 pts
  - Vencedor errado placar: 2 pts
  - Bonus: 5 gols totais +1, 6+ gols +2 (so se exato)
  - Max 40 resultados iguais

Uso:
    python3 bolao_cli/optimize.py
"""

import os
import sys
import time
from itertools import product
from contextlib import redirect_stdout
from io import StringIO
from typing import Tuple, Dict
from collections import Counter

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import importlib.util

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

bt2018 = _load_module("bt2018", os.path.join(PROJECT_DIR, "backtests", "wc2018", "run_backtest.py"))
bt2022 = _load_module("bt2022", os.path.join(PROJECT_DIR, "backtests", "wc2022", "run_backtest.py"))

from bolao_cli.pontuacao import bolao_cli_points


# =============================================================================
# SMART BET LOGIC (same as backtests/smart_baseline.py)
# =============================================================================

def compute_match_probs(score_matrix) -> dict:
    n = score_matrix.shape[0]
    p_draw = sum(score_matrix[i, i] for i in range(n))
    return {"p_draw": p_draw}


def smart_bet(
    score_matrix,
    lambdas: Tuple[float, float],
    draw_threshold: float,
    draw_score: Tuple[int, int],
    big_win_lambda_diff: float,
    big_win_score: Tuple[int, int],
    normal_win_score: Tuple[int, int],
) -> Tuple[int, int]:
    probs = compute_match_probs(score_matrix)
    lh, la = lambdas

    if probs["p_draw"] > draw_threshold:
        return draw_score

    home_is_fav = lh >= la
    diff = abs(lh - la)

    if diff > big_win_lambda_diff:
        score = big_win_score
    else:
        score = normal_win_score

    if home_is_fav:
        return score
    else:
        return (score[1], score[0])


# =============================================================================
# GRID — mais opcoes de placar alto (bonus gols) e empate
# =============================================================================

GRID = {
    "draw_threshold": [0.20, 0.25, 0.28, 0.30, 0.32, 0.35],
    "draw_score": [(0, 0), (1, 1), (2, 2)],
    "big_win_lambda_diff": [0.3, 0.5, 0.7, 0.9],
    "big_win_score": [(2, 0), (2, 1), (3, 0), (3, 1), (3, 2), (4, 1)],
    "normal_win_score": [(1, 0), (2, 1), (2, 0)],
}


def generate_combos(grid: dict) -> list:
    keys = list(grid.keys())
    vals = [grid[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in product(*vals)]


# =============================================================================
# SCORING
# =============================================================================

def _score_matches(model, match_results, params, knockout=False):
    total = 0
    bets = []
    for result in match_results:
        h, a = result["home"], result["away"]
        try:
            pred = model.predict_match(h, a, host_adv=0.0)
            bet = smart_bet(pred["score_matrix"], pred["lambdas"], **params)
        except KeyError:
            bet = (1, 0)
        actual = (result["hg"], result["ag"])
        pts = bolao_cli_points(bet, actual)
        total += pts
        bets.append(bet)
    return total, bets


def check_40_limit(all_bets: list) -> bool:
    """Check if any single scoreline appears > 40 times."""
    counts = Counter(all_bets)
    return all(c <= 40 for c in counts.values())


# =============================================================================
# TRAIN MODELS
# =============================================================================

def train_model_2018(cal_params=None):
    if cal_params is None:
        cal_params = {"w_dc": 1.0, "w_elo": 0.0, "w_tm": 0.0, "xi": 0.0005,
                      "dc_quality_filter_enabled": False, "date_cutoff": "2014-01-01"}
    cal = bt2018.make_calibration_2018(**cal_params)
    return bt2018.train_model(cal)


def train_model_2022(cal_params=None):
    if cal_params is None:
        cal_params = {"w_dc": 1.0, "w_elo": 0.0, "w_tm": 0.0, "xi": 0.0003,
                      "dc_quality_filter_enabled": True, "date_cutoff": "2016-01-01"}
    cal = bt2022.make_calibration_2022(**cal_params)
    return bt2022.train_model(cal)


def run_2018(model, params):
    group_results, ko_results = bt2018.load_wc2018_results()
    pts_grp, bets_grp = _score_matches(model, group_results, params)
    pts_ko, bets_ko = _score_matches(model, ko_results, params, knockout=True)
    return pts_grp + pts_ko, bets_grp + bets_ko


def run_2022(model, params):
    group_results, ko_results = bt2022.load_wc2022_results()
    pts_grp, bets_grp = _score_matches(model, group_results, params)
    pts_ko, bets_ko = _score_matches(model, ko_results, params, knockout=True)
    return pts_grp + pts_ko, bets_grp + bets_ko


# =============================================================================
# MAIN
# =============================================================================

def main():
    combos = generate_combos(GRID)
    print("=" * 90)
    print("  BOLAO DO CLI — Smart Baseline Optimizer")
    print("  Pontuacao: exato=5 (+bonus gols), empate=3, vencedor=2")
    print("=" * 90)
    print(f"\n  Combinacoes a testar: {len(combos)}")

    print("\n  Treinando modelo 2018...")
    model_2018 = train_model_2018()
    print("  Treinando modelo 2022...")
    f = StringIO()
    with redirect_stdout(f):
        model_2022 = train_model_2022()
    print("  Modelos treinados. Iniciando grid search...\n")

    results = []
    t0 = time.time()

    for i, params in enumerate(combos):
        pts_2018, bets_2018 = run_2018(model_2018, params)
        pts_2022, bets_2022 = run_2022(model_2022, params)
        combined = pts_2018 + pts_2022

        valid_2018 = check_40_limit(bets_2018)
        valid_2022 = check_40_limit(bets_2022)

        results.append({
            "params": params,
            "pts_2018": pts_2018,
            "pts_2022": pts_2022,
            "combined": combined,
            "valid_40": valid_2018 and valid_2022,
        })

        elapsed = time.time() - t0
        eta = (elapsed / (i + 1)) * (len(combos) - i - 1)

        p = params
        flag = "" if (valid_2018 and valid_2022) else " [>40!]"
        label = (f"draw>{p['draw_threshold']:.2f}->{p['draw_score'][0]}x{p['draw_score'][1]}  "
                 f"big>{p['big_win_lambda_diff']:.1f}->{p['big_win_score'][0]}x{p['big_win_score'][1]}  "
                 f"norm->{p['normal_win_score'][0]}x{p['normal_win_score'][1]}")

        print(f"  [{i+1:>4}/{len(combos)}] 2018={pts_2018:>3}  2022={pts_2022:>3}  "
              f"comb={combined:>3}  ({eta:.0f}s)  {label}{flag}")

    total_time = time.time() - t0

    valid_results = [r for r in results if r["valid_40"]]
    valid_results.sort(key=lambda r: r["combined"], reverse=True)
    results.sort(key=lambda r: r["combined"], reverse=True)

    print("\n" + "=" * 90)
    print("  TOP 15 — RANKING POR SOMA (2018 + 2022) — respeitando limite 40")
    print("=" * 90)
    print(f"\n{'#':>3} {'2018':>6} {'2022':>6} {'SOMA':>6}  Config")
    print("-" * 105)

    for i, r in enumerate(valid_results[:15]):
        p = r["params"]
        config = (f"draw>{p['draw_threshold']:.2f}->{p['draw_score'][0]}x{p['draw_score'][1]}  "
                  f"big>{p['big_win_lambda_diff']:.1f}->{p['big_win_score'][0]}x{p['big_win_score'][1]}  "
                  f"norm->{p['normal_win_score'][0]}x{p['normal_win_score'][1]}")
        print(f"{i+1:>3} {r['pts_2018']:>6} {r['pts_2022']:>6} {r['combined']:>6}  {config}")

    for year, key in [("2018", "pts_2018"), ("2022", "pts_2022")]:
        ranked = sorted(valid_results, key=lambda r: r[key], reverse=True)
        print(f"\n  TOP 5 — {year} apenas:")
        for i, r in enumerate(ranked[:5]):
            p = r["params"]
            config = (f"draw>{p['draw_threshold']:.2f}->{p['draw_score'][0]}x{p['draw_score'][1]}  "
                      f"big>{p['big_win_lambda_diff']:.1f}->{p['big_win_score'][0]}x{p['big_win_score'][1]}  "
                      f"norm->{p['normal_win_score'][0]}x{p['normal_win_score'][1]}")
            print(f"    {i+1}. {r[key]:>3} pts  {config}")

    # Baselines
    print(f"\n  --- REFERENCIA (baselines burros, Bolao Cli pts) ---")
    elo_2018 = bt2018.load_elo_2018()
    elo_2022 = bt2022.load_elo_2022()
    grp18, ko18 = bt2018.load_wc2018_results()
    grp22, ko22 = bt2022.load_wc2022_results()

    for bname, score in [("Fav 1x0", (1, 0)), ("Fav 2x1", (2, 1)), ("Sempre 1x1", (1, 1))]:
        pts18 = 0
        for r in grp18 + ko18:
            if bname == "Sempre 1x1":
                bet = (1, 1)
            else:
                elo = elo_2018
                if elo.get(r["home"], 1500) >= elo.get(r["away"], 1500):
                    bet = score
                else:
                    bet = (score[1], score[0])
            pts18 += bolao_cli_points(bet, (r["hg"], r["ag"]))

        pts22 = 0
        for r in grp22 + ko22:
            if bname == "Sempre 1x1":
                bet = (1, 1)
            else:
                elo = elo_2022
                if elo.get(r["home"], 1500) >= elo.get(r["away"], 1500):
                    bet = score
                else:
                    bet = (score[1], score[0])
            pts22 += bolao_cli_points(bet, (r["hg"], r["ag"]))

        print(f"  {bname:<15}: 2018={pts18:>3}  2022={pts22:>3}  soma={pts18+pts22}")

    if valid_results:
        best = valid_results[0]
        p = best["params"]
        print(f"\n  --- MELHOR SMART BASELINE (Bolao Cli) ---")
        print(f"  draw_threshold: {p['draw_threshold']}")
        print(f"  draw_score: {p['draw_score'][0]}x{p['draw_score'][1]}")
        print(f"  big_win_lambda_diff: {p['big_win_lambda_diff']}")
        print(f"  big_win_score: {p['big_win_score'][0]}x{p['big_win_score'][1]}")
        print(f"  normal_win_score: {p['normal_win_score'][0]}x{p['normal_win_score'][1]}")
        print(f"\n  2018: {best['pts_2018']} pts")
        print(f"  2022: {best['pts_2022']} pts")
        print(f"  Soma: {best['combined']} pts")

    # Sensitivity
    print("\n" + "=" * 90)
    print("  ANALISE DE SENSIBILIDADE")
    print("=" * 90)

    for var_name in GRID:
        value_scores = {}
        for r in valid_results:
            val = str(r["params"][var_name])
            if val not in value_scores:
                value_scores[val] = []
            value_scores[val].append(r["combined"])

        print(f"\n  {var_name}:")
        for val, scores in sorted(value_scores.items(), key=lambda x: -sum(x[1]) / len(x[1])):
            avg = sum(scores) / len(scores)
            best_v = max(scores)
            print(f"    {val:>12}: avg={avg:.1f}  best={best_v}  n={len(scores)}")

    print(f"\nTempo total: {total_time:.1f} segundos")
    print(f"Combinacoes validas (limite 40): {len(valid_results)}/{len(results)}")

    # Save
    import json
    save_path = os.path.join(PROJECT_DIR, "bolao_cli", "results.json")
    serializable = []
    for r in valid_results:
        sr = dict(r)
        sr["params"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in r["params"].items()}
        serializable.append(sr)
    with open(save_path, "w") as fp:
        json.dump(serializable, fp, indent=2)
    print(f"Resultados salvos em {save_path}")


if __name__ == "__main__":
    main()

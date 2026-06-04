#!/usr/bin/env python3
"""
Smart Baseline: usa probabilidades do Dixon-Coles para escolher placares
baseado em thresholds sobre P(empate) e força do favorito.

Grid search sobre thresholds e placares, testado nos backtests 2018 e 2022.

Uso:
    python3 backtests/smart_baseline.py
"""

import os
import sys
import time
from itertools import product
from contextlib import redirect_stdout
from io import StringIO
from typing import Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from bolao2026 import bolao_points

import importlib.util

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

bt2018 = _load_module("bt2018", os.path.join(PROJECT_DIR, "backtests", "wc2018", "run_backtest.py"))
bt2022 = _load_module("bt2022", os.path.join(PROJECT_DIR, "backtests", "wc2022", "run_backtest.py"))


# =============================================================================
# SMART BASELINE LOGIC
# =============================================================================

def compute_match_probs(score_matrix) -> dict:
    """Extrai probabilidades agregadas da score_matrix."""
    n = score_matrix.shape[0]
    p_draw = sum(score_matrix[i, i] for i in range(n))
    p_home = sum(score_matrix[i, j] for i in range(n) for j in range(n) if i > j)
    p_away = sum(score_matrix[i, j] for i in range(n) for j in range(n) if i < j)
    return {"p_draw": p_draw, "p_home": p_home, "p_away": p_away}


def smart_bet(
    score_matrix,
    lambdas: Tuple[float, float],
    draw_threshold: float,
    draw_score: Tuple[int, int],
    big_win_lambda_diff: float,
    big_win_score: Tuple[int, int],
    normal_win_score: Tuple[int, int],
) -> Tuple[int, int]:
    """
    Decide o placar usando DC probabilities.

    1. Se P(empate) > draw_threshold -> aposta empate (draw_score)
    2. Se |lambda_h - lambda_a| > big_win_lambda_diff -> big_win_score pro favorito
    3. Senao -> normal_win_score pro favorito
    """
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
# GRID
# =============================================================================

GRID = {
    "draw_threshold": [0.20, 0.25, 0.28, 0.30, 0.32, 0.35],
    "draw_score": [(0, 0), (1, 1)],
    "big_win_lambda_diff": [0.3, 0.5, 0.7, 0.9],
    "big_win_score": [(2, 0), (2, 1), (3, 0), (3, 1)],
    "normal_win_score": [(1, 0), (2, 1)],
}


def generate_combos(grid: dict) -> list:
    keys = list(grid.keys())
    vals = [grid[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in product(*vals)]


# =============================================================================
# RUN ON EACH WORLD CUP
# =============================================================================

def _score_matches(model, match_results, params, knockout=False):
    """Score smart baseline bets against actual results."""
    total = 0
    for result in match_results:
        h, a = result["home"], result["away"]
        try:
            pred = model.predict_match(h, a, host_adv=0.0)
            bet = smart_bet(pred["score_matrix"], pred["lambdas"], **params)
        except KeyError:
            bet = (1, 0)
        actual = (result["hg"], result["ag"])
        total += bolao_points(bet, actual, knockout=knockout)
    return total


def run_2018(model, params):
    group_results, ko_results = bt2018.load_wc2018_results()
    pts_grp = _score_matches(model, group_results, params, knockout=False)
    pts_ko = _score_matches(model, ko_results, params, knockout=True)
    return pts_grp + pts_ko


def run_2022(model, params):
    group_results, ko_results = bt2022.load_wc2022_results()
    pts_grp = _score_matches(model, group_results, params, knockout=False)
    pts_ko = _score_matches(model, ko_results, params, knockout=True)
    return pts_grp + pts_ko


def train_model_2018():
    cal = bt2018.make_calibration_2018(
        w_dc=1.0, w_elo=0.0, w_tm=0.0, xi=0.0005,
        dc_quality_filter_enabled=False, date_cutoff="2014-01-01",
    )
    return bt2018.train_model(cal)


def train_model_2022():
    cal = bt2022.make_calibration_2022(
        w_dc=1.0, w_elo=0.0, w_tm=0.0, xi=0.0003,
        dc_quality_filter_enabled=True, date_cutoff="2016-01-01",
    )
    return bt2022.train_model(cal)


# =============================================================================
# MAIN
# =============================================================================

def main():
    combos = generate_combos(GRID)
    print("=" * 80)
    print("  SMART BASELINE — Grid Search (DC-based thresholds)")
    print("=" * 80)
    print(f"\n  Combinacoes a testar: {len(combos)}")

    # Train models once
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
        pts_2018 = run_2018(model_2018, params)
        pts_2022 = run_2022(model_2022, params)
        combined = pts_2018 + pts_2022

        results.append({
            "params": params,
            "pts_2018": pts_2018,
            "pts_2022": pts_2022,
            "combined": combined,
        })

        elapsed = time.time() - t0
        eta = (elapsed / (i + 1)) * (len(combos) - i - 1)

        p = params
        label = (f"draw>{p['draw_threshold']:.2f}->{p['draw_score'][0]}x{p['draw_score'][1]}  "
                 f"big>{p['big_win_lambda_diff']:.1f}->{p['big_win_score'][0]}x{p['big_win_score'][1]}  "
                 f"norm->{p['normal_win_score'][0]}x{p['normal_win_score'][1]}")

        print(f"  [{i+1:>4}/{len(combos)}] 2018={pts_2018:>3}  2022={pts_2022:>3}  "
              f"comb={combined:>3}  ({eta:.0f}s)  {label}")

    total_time = time.time() - t0

    # =================================================================
    # RANKING BY COMBINED SCORE
    # =================================================================
    results.sort(key=lambda r: r["combined"], reverse=True)

    print("\n" + "=" * 80)
    print("  TOP 15 — RANKING POR SOMA (2018 + 2022)")
    print("=" * 80)
    print(f"\n{'#':>3} {'2018':>6} {'2022':>6} {'SOMA':>6}  Config")
    print("-" * 100)

    for i, r in enumerate(results[:15]):
        p = r["params"]
        config = (f"draw>{p['draw_threshold']:.2f}->{p['draw_score'][0]}x{p['draw_score'][1]}  "
                  f"big>{p['big_win_lambda_diff']:.1f}->{p['big_win_score'][0]}x{p['big_win_score'][1]}  "
                  f"norm->{p['normal_win_score'][0]}x{p['normal_win_score'][1]}")
        print(f"{i+1:>3} {r['pts_2018']:>6} {r['pts_2022']:>6} {r['combined']:>6}  {config}")

    # =================================================================
    # TOP 5 BY EACH CUP
    # =================================================================
    for year, key in [("2018", "pts_2018"), ("2022", "pts_2022")]:
        ranked = sorted(results, key=lambda r: r[key], reverse=True)
        print(f"\n  TOP 5 — {year} apenas:")
        for i, r in enumerate(ranked[:5]):
            p = r["params"]
            config = (f"draw>{p['draw_threshold']:.2f}->{p['draw_score'][0]}x{p['draw_score'][1]}  "
                      f"big>{p['big_win_lambda_diff']:.1f}->{p['big_win_score'][0]}x{p['big_win_score'][1]}  "
                      f"norm->{p['normal_win_score'][0]}x{p['normal_win_score'][1]}")
            print(f"    {i+1}. {r[key]:>3} pts  {config}")

    # =================================================================
    # REFERENCE
    # =================================================================
    print(f"\n  --- REFERENCIA ---")
    print(f"  Baseline 'Fav 2x1':    2018=229  2022=223  soma=452")
    print(f"  Baseline 'Fav 1x0':    2018=239  2022=202  soma=441")
    print(f"  Modelo EV (sem GI):    2018=236  2022=201  soma=437")
    print(f"  Modelo EV (GI=1.20):   2018=259  2022=209  soma=468")

    best = results[0]
    print(f"\n  --- MELHOR SMART BASELINE ---")
    p = best["params"]
    print(f"  draw_threshold: {p['draw_threshold']}")
    print(f"  draw_score: {p['draw_score'][0]}x{p['draw_score'][1]}")
    print(f"  big_win_lambda_diff: {p['big_win_lambda_diff']}")
    print(f"  big_win_score: {p['big_win_score'][0]}x{p['big_win_score'][1]}")
    print(f"  normal_win_score: {p['normal_win_score'][0]}x{p['normal_win_score'][1]}")
    print(f"\n  2018: {best['pts_2018']} pts")
    print(f"  2022: {best['pts_2022']} pts")
    print(f"  Soma: {best['combined']} pts")

    # =================================================================
    # SENSIBILIDADE
    # =================================================================
    print("\n" + "=" * 80)
    print("  ANALISE DE SENSIBILIDADE")
    print("=" * 80)

    for var_name in GRID:
        value_scores = {}
        for r in results:
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

    # Save
    import json
    save_path = os.path.join(PROJECT_DIR, "backtests", "saved_results", "smart_baseline.json")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    serializable = []
    for r in results:
        sr = dict(r)
        sr["params"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in r["params"].items()}
        serializable.append(sr)
    with open(save_path, "w") as fp:
        json.dump(serializable, fp, indent=2)
    print(f"Resultados salvos em {save_path}")


if __name__ == "__main__":
    main()

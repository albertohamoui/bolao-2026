#!/usr/bin/env python3
"""
Smart Baseline + Calibration Grid Search.

Fixa os thresholds do smart baseline (ja otimizados) e varia a calibracao
do modelo DC (blend weights, xi, cutoff, etc.) para encontrar qual modelo
gera os melhores lambdas para as decisoes do smart baseline.

Uso:
    python3 backtests/smart_baseline_calibration.py
"""

import os
import sys
import time
from contextlib import redirect_stdout
from io import StringIO

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

from bolao2026 import bolao_points
from backtests.smart_baseline import smart_bet

# =============================================================================
# SMART BASELINE PARAMS (fixos — ja otimizados)
# =============================================================================
SB_PARAMS = {
    "draw_threshold": 0.35,
    "draw_score": (1, 1),
    "big_win_lambda_diff": 0.5,
    "big_win_score": (2, 0),
    "normal_win_score": (2, 1),
}

# =============================================================================
# CALIBRATION GRID
# =============================================================================
CAL_GRID = {
    "blend_weights": [
        (1.00, 0.00, 0.00),  # DC puro
        (0.70, 0.20, 0.10),  # DC dominante
        (0.60, 0.25, 0.15),
        (0.50, 0.30, 0.20),
        (0.45, 0.30, 0.25),  # default
        (0.30, 0.40, 0.30),  # ELO dominante
        (0.00, 1.00, 0.00),  # ELO puro
    ],
    "xi": [0.0003, 0.0005, 0.001, 0.003],
    "dc_qf_enabled": [True, False],
}

CUTOFFS_2018 = ["2012-01-01", "2014-01-01"]
CUTOFFS_2022 = ["2016-01-01", "2018-01-01"]


def generate_cal_combos():
    combos = []
    for bw in CAL_GRID["blend_weights"]:
        for xi in CAL_GRID["xi"]:
            for qf in CAL_GRID["dc_qf_enabled"]:
                combos.append({
                    "w_dc": bw[0], "w_elo": bw[1], "w_tm": bw[2],
                    "xi": xi, "dc_qf_enabled": qf,
                })
    return combos


def _score_matches(model, match_results, knockout=False):
    total = 0
    for result in match_results:
        h, a = result["home"], result["away"]
        try:
            pred = model.predict_match(h, a, host_adv=0.0)
            bet = smart_bet(pred["score_matrix"], pred["lambdas"], **SB_PARAMS)
        except KeyError:
            bet = (1, 0)
        actual = (result["hg"], result["ag"])
        total += bolao_points(bet, actual, knockout=knockout)
    return total


def run_combo(combo):
    """Run one calibration combo on both WCs. Returns best per WC."""
    results = {}

    for year, bt_mod, cutoffs in [
        ("2018", bt2018, CUTOFFS_2018),
        ("2022", bt2022, CUTOFFS_2022),
    ]:
        best_pts = 0
        best_cut = cutoffs[0]
        make_cal = bt_mod.make_calibration_2018 if year == "2018" else bt_mod.make_calibration_2022
        load_results = bt_mod.load_wc2018_results if year == "2018" else bt_mod.load_wc2022_results

        for cutoff in cutoffs:
            f = StringIO()
            with redirect_stdout(f):
                cal = make_cal(
                    w_dc=combo["w_dc"], w_elo=combo["w_elo"], w_tm=combo["w_tm"],
                    xi=combo["xi"], dc_quality_filter_enabled=combo["dc_qf_enabled"],
                    date_cutoff=cutoff,
                )
                model = bt_mod.train_model(cal)

            group_results, ko_results = load_results()
            pts = _score_matches(model, group_results, knockout=False)
            pts += _score_matches(model, ko_results, knockout=True)

            if pts > best_pts:
                best_pts = pts
                best_cut = cutoff

        results[year] = {"pts": best_pts, "cutoff": best_cut}

    return results["2018"]["pts"], results["2022"]["pts"], results["2018"]["cutoff"], results["2022"]["cutoff"]


def main():
    combos = generate_cal_combos()
    print("=" * 90)
    print("  SMART BASELINE + CALIBRATION GRID SEARCH")
    print("  SB fixo: draw>0.35->1x1 | big>0.5->2x0 | normal->2x1")
    print("=" * 90)
    print(f"\n  Calibracoes: {len(combos)} x 2 cutoffs x 2 copas")

    results = []
    t0 = time.time()

    for i, combo in enumerate(combos):
        pts_2018, pts_2022, cut_2018, cut_2022 = run_combo(combo)
        combined = pts_2018 + pts_2022

        results.append({
            "combo": combo,
            "pts_2018": pts_2018,
            "pts_2022": pts_2022,
            "combined": combined,
            "cut_2018": cut_2018,
            "cut_2022": cut_2022,
        })

        elapsed = time.time() - t0
        eta = (elapsed / (i + 1)) * (len(combos) - i - 1)

        c = combo
        label = (f"DC={c['w_dc']:.2f} ELO={c['w_elo']:.2f} TM={c['w_tm']:.2f} "
                 f"xi={c['xi']:.4f} qf={'ON' if c['dc_qf_enabled'] else 'OFF'}")

        print(f"  [{i+1:>3}/{len(combos)}] 2018={pts_2018:>3}  2022={pts_2022:>3}  "
              f"comb={combined:>3}  ({eta:.0f}s)  {label}")

    total_time = time.time() - t0

    results.sort(key=lambda r: r["combined"], reverse=True)

    print("\n" + "=" * 90)
    print("  TOP 15 — RANKING POR SOMA (2018 + 2022)")
    print("=" * 90)
    print(f"\n{'#':>3} {'2018':>6} {'2022':>6} {'SOMA':>6}  Config")
    print("-" * 100)

    for i, r in enumerate(results[:15]):
        c = r["combo"]
        config = (f"DC={c['w_dc']:.2f} ELO={c['w_elo']:.2f} TM={c['w_tm']:.2f} "
                  f"xi={c['xi']:.4f} qf={'ON' if c['dc_qf_enabled'] else 'OFF'} "
                  f"cut18={r['cut_2018']} cut22={r['cut_2022']}")
        print(f"{i+1:>3} {r['pts_2018']:>6} {r['pts_2022']:>6} {r['combined']:>6}  {config}")

    print(f"\n  --- REFERENCIA ---")
    print(f"  Smart BL + DC puro:    2018=252  2022=253  soma=505")
    print(f"  Modelo EV (GI=1.20):   2018=259  2022=209  soma=468")
    print(f"  Baseline Fav 2x1:      2018=229  2022=223  soma=452")

    best = results[0]
    c = best["combo"]
    print(f"\n  --- MELHOR ---")
    print(f"  DC={c['w_dc']:.2f} ELO={c['w_elo']:.2f} TM={c['w_tm']:.2f}")
    print(f"  xi={c['xi']:.4f} qf={'ON' if c['dc_qf_enabled'] else 'OFF'}")
    print(f"  cutoff 2018: {best['cut_2018']}, cutoff 2022: {best['cut_2022']}")
    print(f"  2018: {best['pts_2018']}  2022: {best['pts_2022']}  Soma: {best['combined']}")

    print("\n" + "=" * 90)
    print("  ANALISE DE SENSIBILIDADE")
    print("=" * 90)

    for var_name, key_fn in [
        ("DC weight", lambda c: f"{c['w_dc']:.2f}"),
        ("xi", lambda c: f"{c['xi']:.4f}"),
        ("Quality filter", lambda c: "ON" if c['dc_qf_enabled'] else "OFF"),
    ]:
        value_scores = {}
        for r in results:
            val = key_fn(r["combo"])
            if val not in value_scores:
                value_scores[val] = []
            value_scores[val].append(r["combined"])

        print(f"\n  {var_name}:")
        for val, scores in sorted(value_scores.items(), key=lambda x: -sum(x[1]) / len(x[1])):
            avg = sum(scores) / len(scores)
            best_v = max(scores)
            print(f"    {val:>12}: avg={avg:.1f}  best={best_v}  n={len(scores)}")

    print(f"\nTempo total: {total_time:.1f} segundos")

    import json
    save_path = os.path.join(PROJECT_DIR, "backtests", "saved_results", "smart_baseline_calibration.json")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "w") as fp:
        json.dump(results, fp, indent=2, default=str)
    print(f"Resultados salvos em {save_path}")


if __name__ == "__main__":
    main()

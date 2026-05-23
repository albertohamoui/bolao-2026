#!/usr/bin/env python3
"""
Otimizador de calibração via grid search sobre o backtest da Copa 2018.

Testa combinações de variáveis e encontra a que maximiza pontos do bolão.
Todos os dados são de 2022 (sem data leakage).

Uso:
    python3 backtests/wc2018/optimize.py
    python3 backtests/wc2018/optimize.py --quick   # grid reduzido (~50 combos)
"""

import argparse
import os
import sys
import time
from contextlib import redirect_stdout
from io import StringIO

BACKTEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(BACKTEST_DIR))
sys.path.insert(0, BACKTEST_DIR)
sys.path.insert(0, PROJECT_DIR)

from run_backtest import make_calibration_2018, run_backtest


# =============================================================================
# GRID DE BUSCA
# =============================================================================

# Grid completo (~300 combinações, ~15-30 min)
FULL_GRID = {
    # Pesos do blend (devem somar 1.0)
    "blend_weights": [
        (0.70, 0.20, 0.10),  # DC dominante
        (0.60, 0.25, 0.15),
        (0.50, 0.30, 0.20),
        (0.45, 0.30, 0.25),  # default atual
        (0.40, 0.35, 0.25),
        (0.35, 0.35, 0.30),
        (0.30, 0.40, 0.30),  # ELO dominante
        (0.20, 0.50, 0.30),
        (1.00, 0.00, 0.00),  # DC puro
        (0.00, 1.00, 0.00),  # ELO puro
        (0.00, 0.00, 1.00),  # TM puro
    ],
    # Time-decay
    "xi": [0.0003, 0.0005, 0.001, 0.002, 0.005],
    # Escala TM
    "tm_scale": ["sqrt", "log"],
    # Quality filter on/off
    "dc_qf_enabled": [True, False],
    # Date cutoff
    "date_cutoff": ["2014-01-01", "2012-01-01", "2016-01-01"],
}

# Grid rápido (~50 combinações, ~3-5 min)
QUICK_GRID = {
    "blend_weights": [
        (0.60, 0.25, 0.15),
        (0.45, 0.30, 0.25),
        (0.30, 0.40, 0.30),
        (1.00, 0.00, 0.00),
        (0.00, 1.00, 0.00),
    ],
    "xi": [0.0005, 0.001, 0.003],
    "tm_scale": ["sqrt"],
    "dc_qf_enabled": [True, False],
    "date_cutoff": ["2014-01-01"],
}


def generate_combinations(grid: dict) -> list:
    """Gera todas as combinações do grid."""
    combos = []
    for bw in grid["blend_weights"]:
        for xi in grid["xi"]:
            for tm in grid["tm_scale"]:
                for qf in grid["dc_qf_enabled"]:
                    for dc in grid["date_cutoff"]:
                        combos.append({
                            "w_dc": bw[0], "w_elo": bw[1], "w_tm": bw[2],
                            "xi": xi, "tm_scale": tm,
                            "dc_qf_enabled": qf, "date_cutoff": dc,
                        })
    return combos


def run_single(params: dict) -> dict:
    """Roda um backtest com os parâmetros dados. Retorna resultado."""
    cal = make_calibration_2018(
        w_dc=params["w_dc"],
        w_elo=params["w_elo"],
        w_tm=params["w_tm"],
        xi=params["xi"],
        tm_scale=params["tm_scale"],
        dc_quality_filter_enabled=params["dc_qf_enabled"],
        date_cutoff=params["date_cutoff"],
    )

    # Suprimir output do modelo
    f = StringIO()
    with redirect_stdout(f):
        result = run_backtest(cal, verbose=False)

    return {**result, "params": params}


def main():
    parser = argparse.ArgumentParser(description="Otimizador de calibração")
    parser.add_argument("--quick", action="store_true", help="Grid reduzido (~50 combos)")
    args = parser.parse_args()

    grid = QUICK_GRID if args.quick else FULL_GRID
    combos = generate_combinations(grid)

    print("=" * 70)
    print("  OTIMIZADOR DE CALIBRAÇÃO — Copa 2018 (dados de época)")
    print("=" * 70)
    print(f"\nCombinações a testar: {len(combos)}")
    print(f"Grid: {'QUICK' if args.quick else 'FULL'}")
    print()

    results = []
    t0 = time.time()

    for i, params in enumerate(combos):
        t_start = time.time()
        try:
            result = run_single(params)
            results.append(result)
            elapsed = time.time() - t_start
            total_elapsed = time.time() - t0
            eta = (total_elapsed / (i + 1)) * (len(combos) - i - 1)

            label = (f"DC={params['w_dc']:.2f} ELO={params['w_elo']:.2f} "
                     f"TM={params['w_tm']:.2f} xi={params['xi']:.4f} "
                     f"scale={params['tm_scale']} qf={params['dc_qf_enabled']} "
                     f"cut={params['date_cutoff']}")
            print(f"  [{i+1:>3}/{len(combos)}] {result['model_total']:>4} pts  "
                  f"({elapsed:.1f}s, ETA {eta/60:.0f}min)  {label}")

        except Exception as e:
            print(f"  [{i+1:>3}/{len(combos)}] ERRO: {e}")

    total_time = time.time() - t0

    # =================================================================
    # RANKING
    # =================================================================
    results.sort(key=lambda r: r["model_total"], reverse=True)

    print("\n" + "=" * 70)
    print("  TOP 10 CONFIGURAÇÕES")
    print("=" * 70)
    print(f"\n{'#':>3} {'Total':>6} {'Grupos':>7} {'KO':>5}  {'Config'}")
    print("-" * 90)

    for i, r in enumerate(results[:10]):
        p = r["params"]
        config_str = (f"DC={p['w_dc']:.2f} ELO={p['w_elo']:.2f} TM={p['w_tm']:.2f} "
                      f"xi={p['xi']:.4f} {p['tm_scale']} "
                      f"qf={'ON' if p['dc_qf_enabled'] else 'OFF'} "
                      f"cut={p['date_cutoff']}")
        print(f"{i+1:>3} {r['model_total']:>6} {r['model_groups']:>7} {r['model_ko']:>5}  {config_str}")

    # =================================================================
    # PIORES 5
    # =================================================================
    print(f"\n{'#':>3} {'Total':>6}  {'Config (PIORES 5)'}")
    print("-" * 90)
    for i, r in enumerate(results[-5:]):
        p = r["params"]
        config_str = (f"DC={p['w_dc']:.2f} ELO={p['w_elo']:.2f} TM={p['w_tm']:.2f} "
                      f"xi={p['xi']:.4f} {p['tm_scale']} "
                      f"qf={'ON' if p['dc_qf_enabled'] else 'OFF'} "
                      f"cut={p['date_cutoff']}")
        print(f"{len(results)-4+i:>3} {r['model_total']:>6}  {config_str}")

    # =================================================================
    # COMPARAÇÃO COM BASELINES
    # =================================================================
    best = results[0]
    print(f"\n--- MELHOR CONFIGURAÇÃO ---")
    p = best["params"]
    print(f"  w_dc={p['w_dc']:.2f}, w_elo={p['w_elo']:.2f}, w_tm={p['w_tm']:.2f}")
    print(f"  xi={p['xi']:.4f}, tm_scale={p['tm_scale']}")
    print(f"  dc_quality_filter={'ON' if p['dc_qf_enabled'] else 'OFF'}")
    print(f"  date_cutoff={p['date_cutoff']}")
    print(f"\n  Modelo: {best['model_total']} pts (grupos={best['model_groups']}, ko={best['model_ko']})")
    print(f"  Baseline-1 (Fav 1x0): {best['b1_total']} pts  (diff: {best['model_total'] - best['b1_total']:+d})")
    print(f"  Baseline-2 (Fav 2x1): {best['b2_total']} pts  (diff: {best['model_total'] - best['b2_total']:+d})")
    print(f"  Baseline-3 (Sempre 1x1): {best['b3_total']} pts  (diff: {best['model_total'] - best['b3_total']:+d})")

    print(f"\nTempo total: {total_time/60:.1f} minutos")
    print(f"Combinações testadas: {len(results)}/{len(combos)}")

    # =================================================================
    # ANÁLISE DE SENSIBILIDADE
    # =================================================================
    print("\n" + "=" * 70)
    print("  ANÁLISE DE SENSIBILIDADE (impacto de cada variável)")
    print("=" * 70)

    for var_name, var_key in [
        ("Blend DC", "w_dc"), ("Blend ELO", "w_elo"), ("Blend TM", "w_tm"),
        ("xi", "xi"), ("TM scale", "tm_scale"),
        ("Quality filter", "dc_qf_enabled"), ("Date cutoff", "date_cutoff"),
    ]:
        value_scores = {}
        for r in results:
            val = r["params"][var_key]
            val_str = f"{val}" if isinstance(val, (str, bool)) else f"{val:.4f}"
            if val_str not in value_scores:
                value_scores[val_str] = []
            value_scores[val_str].append(r["model_total"])

        print(f"\n  {var_name}:")
        for val, scores in sorted(value_scores.items(), key=lambda x: -sum(x[1])/len(x[1])):
            avg = sum(scores) / len(scores)
            best_v = max(scores)
            worst_v = min(scores)
            print(f"    {val:>12}: avg={avg:.1f}  best={best_v}  worst={worst_v}  n={len(scores)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Otimizador de estrategia para o mata-mata — Bolao do Zap.

Backtesta diferentes modelos/thresholds usando os 66 jogos reais da fase
de grupos da Copa 2026 para encontrar a melhor estrategia de palpites
pro mata-mata.

Uso: python3 analysis/knockout_optimizer.py
"""

import sys
import os
from typing import Tuple, Dict, List
from collections import Counter, defaultdict
from itertools import product

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.scoring import zap_points

# ============================================================================
# RESULTADOS REAIS 2026 (grupos A-I completos, J-K-L parciais)
# ============================================================================

REAL_RESULTS = {
    "MEX vs AFS": (2, 0), "COR vs CZE": (2, 1), "CZE vs AFS": (1, 1),
    "MEX vs COR": (1, 0), "CZE vs MEX": (0, 3), "AFS vs COR": (1, 0),
    "CAN vs BOS": (1, 1), "CAT vs SUI": (1, 1), "SUI vs BOS": (4, 1),
    "CAN vs CAT": (6, 0), "SUI vs CAN": (2, 1), "BOS vs CAT": (3, 1),
    "HAI vs ESC": (0, 1), "BRA vs MAR": (1, 1), "BRA vs HAI": (3, 0),
    "ESC vs MAR": (0, 1), "ESC vs BRA": (0, 3), "MAR vs HAI": (4, 2),
    "EUA vs PAR": (4, 1), "AUS vs TUR": (2, 0), "TUR vs PAR": (0, 1),
    "EUA vs AUS": (2, 0), "TUR vs EUA": (3, 2), "PAR vs AUS": (0, 0),
    "CDM vs EQU": (1, 0), "ALE vs CUR": (7, 1), "ALE vs CDM": (2, 1),
    "EQU vs CUR": (0, 0), "CUR vs CDM": (0, 2), "EQU vs ALE": (2, 1),
    "HOL vs JAP": (2, 2), "SUE vs TUN": (5, 1), "HOL vs SUE": (5, 1),
    "TUN vs JAP": (0, 4), "JAP vs SUE": (1, 1), "TUN vs HOL": (1, 3),
    "IRA vs NZL": (2, 2), "BEL vs EGT": (1, 1), "BEL vs IRA": (0, 0),
    "NZL vs EGT": (1, 3), "EGT vs IRA": (1, 1), "NZL vs BEL": (1, 5),
    "SAU vs URU": (1, 1), "ESP vs CPV": (0, 0), "URU vs CPV": (2, 2),
    "ESP vs SAU": (4, 0), "CPV vs SAU": (0, 0), "URU vs ESP": (0, 1),
    "FRA vs SEN": (3, 1), "IRQ vs NOR": (1, 4), "NOR vs SEN": (3, 2),
    "FRA vs IRQ": (3, 0), "NOR vs FRA": (1, 4), "SEN vs IRQ": (5, 0),
    "ARG vs AGL": (3, 0), "AUT vs JRD": (3, 1), "ARG vs AUT": (2, 0),
    "JRD vs AGL": (1, 2), "POR vs RDC": (1, 1), "UZB vs COL": (1, 3),
    "POR vs UZB": (5, 0), "COL vs RDC": (1, 0), "ING vs CRO": (4, 2),
    "GAN vs PAN": (1, 0), "ING vs GAN": (0, 0), "PAN vs CRO": (0, 1),
}

TEAMS_IN_GROUP = {
    "A": ["MEX", "COR", "AFS", "CZE"],
    "B": ["CAN", "SUI", "CAT", "BOS"],
    "C": ["BRA", "MAR", "ESC", "HAI"],
    "D": ["EUA", "AUS", "PAR", "TUR"],
    "E": ["ALE", "CDM", "EQU", "CUR"],
    "F": ["HOL", "JAP", "SUE", "TUN"],
    "G": ["BEL", "IRA", "EGT", "NZL"],
    "H": ["ESP", "URU", "SAU", "CPV"],
    "I": ["FRA", "SEN", "NOR", "IRQ"],
    "J": ["ARG", "AUT", "AGL", "JRD"],
    "K": ["POR", "COL", "UZB", "RDC"],
    "L": ["ING", "CRO", "GAN", "PAN"],
}


def compute_team_stats() -> Dict[str, dict]:
    """Computa estatisticas de cada time na fase de grupos."""
    team_to_group = {}
    for grp, teams in TEAMS_IN_GROUP.items():
        for t in teams:
            team_to_group[t] = grp

    stats = defaultdict(lambda: {"mp": 0, "w": 0, "d": 0, "l": 0,
                                  "gf": 0, "ga": 0, "pts": 0})

    for match_key, (hg, ag) in REAL_RESULTS.items():
        home, away = match_key.split(" vs ")
        for team, gf, ga in [(home, hg, ag), (away, ag, hg)]:
            s = stats[team]
            s["mp"] += 1
            s["gf"] += gf
            s["ga"] += ga
            if gf > ga:
                s["w"] += 1
                s["pts"] += 3
            elif gf == ga:
                s["d"] += 1
                s["pts"] += 1
            else:
                s["l"] += 1

    for team in stats:
        s = stats[team]
        s["gd"] = s["gf"] - s["ga"]
        s["gf_per_game"] = s["gf"] / s["mp"] if s["mp"] else 0
        s["ga_per_game"] = s["ga"] / s["mp"] if s["mp"] else 0
        s["group"] = team_to_group.get(team, "?")

    return dict(stats)


def estimate_strength(stats: dict) -> float:
    """Score de forca baseado em desempenho real na fase de grupos."""
    pts_per_game = stats["pts"] / stats["mp"] if stats["mp"] else 0
    gd_per_game = stats["gd"] / stats["mp"] if stats["mp"] else 0
    gf_per_game = stats["gf_per_game"]
    return pts_per_game * 1.0 + gd_per_game * 0.3 + gf_per_game * 0.2


# ============================================================================
# ESTRATEGIA DE PALPITE
# ============================================================================

def strategy_tier_based(
    strength_diff: float,
    is_home_fav: bool,
    tier_thresholds: List[float],
    tier_scores: List[Tuple[int, int]],
    draw_score: Tuple[int, int],
    draw_threshold: float,
) -> Tuple[int, int]:
    """Estrategia baseada em tiers de diferenca de forca."""
    if abs(strength_diff) < draw_threshold:
        return draw_score

    diff = abs(strength_diff)
    score = tier_scores[-1]  # default: menor tier
    for i, thresh in enumerate(tier_thresholds):
        if diff >= thresh:
            score = tier_scores[i]
            break

    if not is_home_fav:
        score = (score[1], score[0])
    return score


# ============================================================================
# GRID SEARCH
# ============================================================================

GRID = {
    "draw_threshold": [0.3, 0.5, 0.8, 1.0, 1.2],
    "draw_score": [(0, 0), (1, 1)],
    "big_threshold": [2.0, 2.5, 3.0],
    "big_score": [(3, 0), (3, 1), (4, 1)],
    "medium_threshold": [1.0, 1.5, 2.0],
    "medium_score": [(2, 0), (2, 1)],
    "small_score": [(1, 0), (2, 1)],
}


def generate_combos(grid: dict) -> list:
    keys = list(grid.keys())
    vals = [grid[k] for k in keys]
    combos = []
    for combo in product(*vals):
        params = dict(zip(keys, combo))
        if params["big_threshold"] <= params["medium_threshold"]:
            continue
        combos.append(params)
    return combos


def score_strategy(params: dict, team_stats: dict,
                   knockout: bool = False) -> Tuple[int, list]:
    """Pontua uma estrategia contra todos os resultados reais."""
    total = 0
    details = []

    for match_key, real in REAL_RESULTS.items():
        home, away = match_key.split(" vs ")
        h_stats = team_stats.get(home, {"pts": 0, "mp": 1, "gd": 0,
                                         "gf": 0, "gf_per_game": 0})
        a_stats = team_stats.get(away, {"pts": 0, "mp": 1, "gd": 0,
                                         "gf": 0, "gf_per_game": 0})
        h_str = estimate_strength(h_stats)
        a_str = estimate_strength(a_stats)
        diff = h_str - a_str
        is_home_fav = diff >= 0

        bet = strategy_tier_based(
            strength_diff=diff,
            is_home_fav=is_home_fav,
            tier_thresholds=[params["big_threshold"],
                             params["medium_threshold"]],
            tier_scores=[params["big_score"], params["medium_score"],
                         params["small_score"]],
            draw_score=params["draw_score"],
            draw_threshold=params["draw_threshold"],
        )

        pts = zap_points(bet, real, knockout=knockout)
        total += pts
        details.append((match_key, bet, real, pts))

    return total, details


def main():
    print("=" * 90)
    print("  OTIMIZADOR DE ESTRATEGIA — MATA-MATA — BOLAO DO ZAP")
    print("  Backtesting nos 66 jogos reais da fase de grupos Copa 2026")
    print("=" * 90)

    team_stats = compute_team_stats()

    # Ranking de forcas
    print(f"\n  RANKING DE FORCA (baseado na fase de grupos):")
    print(f"  {'#':>3} {'Time':<5} {'Grp':>4} {'MP':>3} {'W':>2} {'D':>2} "
          f"{'L':>2} {'GF':>3} {'GA':>3} {'GD':>3} {'Pts':>4} {'Forca':>6}")
    print(f"  {'-'*55}")

    ranked = sorted(team_stats.items(),
                     key=lambda x: estimate_strength(x[1]), reverse=True)
    for i, (team, s) in enumerate(ranked, 1):
        strength = estimate_strength(s)
        print(f"  {i:>3} {team:<5} {s['group']:>4} {s['mp']:>3} {s['w']:>2} "
              f"{s['d']:>2} {s['l']:>2} {s['gf']:>3} {s['ga']:>3} "
              f"{s['gd']:>+3} {s['pts']:>4} {strength:>6.2f}")

    # Grid search
    combos = generate_combos(GRID)
    print(f"\n  Combinacoes a testar: {len(combos)}")

    results_grp = []
    results_ko = []

    for params in combos:
        pts_grp, _ = score_strategy(params, team_stats, knockout=False)
        pts_ko, _ = score_strategy(params, team_stats, knockout=True)
        results_grp.append({"params": params, "pts": pts_grp})
        results_ko.append({"params": params, "pts": pts_ko})

    results_grp.sort(key=lambda r: r["pts"], reverse=True)
    results_ko.sort(key=lambda r: r["pts"], reverse=True)

    def format_params(p: dict) -> str:
        return (f"draw<{p['draw_threshold']:.1f}->"
                f"{p['draw_score'][0]}x{p['draw_score'][1]}  "
                f"big>{p['big_threshold']:.1f}->"
                f"{p['big_score'][0]}x{p['big_score'][1]}  "
                f"med>{p['medium_threshold']:.1f}->"
                f"{p['medium_score'][0]}x{p['medium_score'][1]}  "
                f"sml->{p['small_score'][0]}x{p['small_score'][1]}")

    print(f"\n{'='*90}")
    print("  TOP 10 — PONTUACAO DE GRUPOS (validacao)")
    print(f"{'='*90}")
    print(f"\n  {'#':>3} {'Pts':>6}  Config")
    print(f"  {'-'*85}")
    for i, r in enumerate(results_grp[:10], 1):
        print(f"  {i:>3} {r['pts']:>6}  {format_params(r['params'])}")

    print(f"\n{'='*90}")
    print("  TOP 10 — PONTUACAO DE MATA-MATA (otimizacao)")
    print(f"{'='*90}")
    print(f"\n  {'#':>3} {'Pts':>6}  Config")
    print(f"  {'-'*85}")
    for i, r in enumerate(results_ko[:10], 1):
        print(f"  {i:>3} {r['pts']:>6}  {format_params(r['params'])}")

    # Referencia: palpite Zap original
    from analysis.copa2026_zap_analysis import ZAP_BETS
    zap_total_grp = sum(
        zap_points(ZAP_BETS[k], REAL_RESULTS[k])
        for k in REAL_RESULTS if k in ZAP_BETS
    )
    zap_total_ko = sum(
        zap_points(ZAP_BETS[k], REAL_RESULTS[k], knockout=True)
        for k in REAL_RESULTS if k in ZAP_BETS
    )

    print(f"\n  REFERENCIA:")
    print(f"    Zap original (grupos):    {zap_total_grp} pts")
    print(f"    Zap original (mata-mata): {zap_total_ko} pts")
    print(f"    Melhor otimizado (grp):   {results_grp[0]['pts']} pts "
          f"({results_grp[0]['pts'] - zap_total_grp:+d})")
    print(f"    Melhor otimizado (ko):    {results_ko[0]['pts']} pts "
          f"({results_ko[0]['pts'] - zap_total_ko:+d})")

    # Detalhamento do melhor modelo
    best = results_grp[0]
    print(f"\n{'='*90}")
    print("  DETALHAMENTO DO MELHOR MODELO (GRUPOS)")
    print(f"{'='*90}")
    _, details = score_strategy(best["params"], team_stats, knockout=False)

    exatos = sum(1 for _, b, r, _ in details if b == r)
    zeros = sum(1 for _, _, _, p in details if p == 0)
    print(f"\n  Exatos: {exatos}, Zeros: {zeros}")
    print(f"\n  {'Jogo':<20} {'Palpite':>8} {'Real':>8} {'Pts':>5}")
    print(f"  {'-'*45}")
    for match_key, bet, real, pts in details:
        bet_str = f"{bet[0]}x{bet[1]}"
        real_str = f"{real[0]}x{real[1]}"
        marker = " ***" if bet == real else (" XXX" if pts == 0 else "")
        print(f"  {match_key:<20} {bet_str:>8} {real_str:>8} {pts:>5}{marker}")

    # Sensibilidade
    print(f"\n{'='*90}")
    print("  ANALISE DE SENSIBILIDADE")
    print(f"{'='*90}")

    for var_name in GRID:
        value_scores = defaultdict(list)
        for r in results_grp:
            val = str(r["params"][var_name])
            value_scores[val].append(r["pts"])

        print(f"\n  {var_name}:")
        for val, scores in sorted(value_scores.items(),
                                   key=lambda x: -sum(x[1]) / len(x[1])):
            avg = sum(scores) / len(scores)
            best_v = max(scores)
            print(f"    {val:>12}: avg={avg:.1f}  best={best_v}  "
                  f"n={len(scores)}")

    # Recomendacao final
    best_p = best["params"]
    print(f"\n{'='*90}")
    print("  CONFIGURACAO RECOMENDADA PARA O MATA-MATA")
    print(f"{'='*90}")
    print(f"""
  Baseado no backtesting com dados reais da Copa 2026:

  - Jogo equilibrado (diff forca < {best_p['draw_threshold']:.1f}):
      Apostar {best_p['draw_score'][0]}x{best_p['draw_score'][1]}

  - Favorito leve (diff < {best_p['medium_threshold']:.1f}):
      Apostar {best_p['small_score'][0]}x{best_p['small_score'][1]} pro favorito

  - Favorito claro (diff < {best_p['big_threshold']:.1f}):
      Apostar {best_p['medium_score'][0]}x{best_p['medium_score'][1]} pro favorito

  - Favorito esmagador (diff >= {best_p['big_threshold']:.1f}):
      Apostar {best_p['big_score'][0]}x{best_p['big_score'][1]} pro favorito

  LEMBRETE: No mata-mata, pontuacao DOBRA!
  Exato: 15 | Dif gols: 9 | Gols venc: 8 | Gols perd: 6 | Vencedor: 5
    """)


if __name__ == "__main__":
    main()

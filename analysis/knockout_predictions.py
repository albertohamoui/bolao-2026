#!/usr/bin/env python3
"""
Palpites do mata-mata — Bolao do Zap — Copa do Mundo 2026.

Usa o modelo otimizado (backtestado nos 72 jogos da fase de grupos)
para gerar palpites de todas as fases: R32 -> R16 -> QF -> SF -> Final.

Uso: python3 analysis/knockout_predictions.py
"""

import sys
import os
from typing import Tuple, Dict
from collections import defaultdict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.scoring import zap_points

# ============================================================================
# RESULTADOS REAIS COMPLETOS — Fase de Grupos (72 jogos)
# Inclui rodada 3 dos grupos J, K, L (27/06)
# ============================================================================

REAL_RESULTS = {
    # Grupo A
    "MEX vs AFS": (2, 0), "COR vs CZE": (2, 1), "CZE vs AFS": (1, 1),
    "MEX vs COR": (1, 0), "CZE vs MEX": (0, 3), "AFS vs COR": (1, 0),
    # Grupo B
    "CAN vs BOS": (1, 1), "CAT vs SUI": (1, 1), "SUI vs BOS": (4, 1),
    "CAN vs CAT": (6, 0), "SUI vs CAN": (2, 1), "BOS vs CAT": (3, 1),
    # Grupo C
    "HAI vs ESC": (0, 1), "BRA vs MAR": (1, 1), "BRA vs HAI": (3, 0),
    "ESC vs MAR": (0, 1), "ESC vs BRA": (0, 3), "MAR vs HAI": (4, 2),
    # Grupo D
    "EUA vs PAR": (4, 1), "AUS vs TUR": (2, 0), "TUR vs PAR": (0, 1),
    "EUA vs AUS": (2, 0), "TUR vs EUA": (3, 2), "PAR vs AUS": (0, 0),
    # Grupo E
    "CDM vs EQU": (1, 0), "ALE vs CUR": (7, 1), "ALE vs CDM": (2, 1),
    "EQU vs CUR": (0, 0), "CUR vs CDM": (0, 2), "EQU vs ALE": (2, 1),
    # Grupo F
    "HOL vs JAP": (2, 2), "SUE vs TUN": (5, 1), "HOL vs SUE": (5, 1),
    "TUN vs JAP": (0, 4), "JAP vs SUE": (1, 1), "TUN vs HOL": (1, 3),
    # Grupo G
    "IRA vs NZL": (2, 2), "BEL vs EGT": (1, 1), "BEL vs IRA": (0, 0),
    "NZL vs EGT": (1, 3), "EGT vs IRA": (1, 1), "NZL vs BEL": (1, 5),
    # Grupo H
    "SAU vs URU": (1, 1), "ESP vs CPV": (0, 0), "URU vs CPV": (2, 2),
    "ESP vs SAU": (4, 0), "CPV vs SAU": (0, 0), "URU vs ESP": (0, 1),
    # Grupo I
    "FRA vs SEN": (3, 1), "IRQ vs NOR": (1, 4), "NOR vs SEN": (3, 2),
    "FRA vs IRQ": (3, 0), "NOR vs FRA": (1, 4), "SEN vs IRQ": (5, 0),
    # Grupo J (completo)
    "ARG vs AGL": (3, 0), "AUT vs JRD": (3, 1), "ARG vs AUT": (2, 0),
    "JRD vs AGL": (1, 2), "ARG vs JRD": (3, 1), "AGL vs AUT": (3, 3),
    # Grupo K (completo)
    "POR vs RDC": (1, 1), "UZB vs COL": (1, 3), "POR vs UZB": (5, 0),
    "COL vs RDC": (1, 0), "COL vs POR": (0, 0), "RDC vs UZB": (3, 1),
    # Grupo L (completo)
    "ING vs CRO": (4, 2), "GAN vs PAN": (1, 0), "ING vs GAN": (0, 0),
    "PAN vs CRO": (0, 1), "ING vs PAN": (2, 0), "CRO vs GAN": (2, 1),
}


# ============================================================================
# CALCULO DE FORCA BASEADO NA FASE DE GRUPOS
# ============================================================================

def compute_team_stats() -> Dict[str, dict]:
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
    return dict(stats)


def estimate_strength(stats: dict) -> float:
    pts_per_game = stats["pts"] / stats["mp"] if stats["mp"] else 0
    gd_per_game = stats["gd"] / stats["mp"] if stats["mp"] else 0
    gf_per_game = stats["gf_per_game"]
    return pts_per_game * 1.0 + gd_per_game * 0.3 + gf_per_game * 0.2


# Elo pre-Copa — do config.json
ELO_PRE = {
    "ESP": 2165, "ARG": 2113, "FRA": 2082, "ING": 2020, "BRA": 1984,
    "POR": 1984, "COL": 1975, "HOL": 1961, "EQU": 1933, "CRO": 1930,
    "ALE": 1923, "NOR": 1912, "JAP": 1904, "TUR": 1902, "URU": 1892,
    "SUI": 1889, "SEN": 1879, "BEL": 1866, "MEX": 1858, "PAR": 1833,
    "AUT": 1827, "MAR": 1821, "CAN": 1784, "AUS": 1783, "ESC": 1767,
    "IRA": 1760, "COR": 1752, "AGL": 1743, "PAN": 1737, "UZB": 1727,
    "CZE": 1726, "EUA": 1721, "SUE": 1719, "JRD": 1690, "EGT": 1689,
    "CDM": 1676, "RDC": 1655, "TUN": 1636, "IRQ": 1607, "BOS": 1594,
    "NZL": 1585, "SAU": 1568, "CPV": 1549, "HAI": 1532, "AFS": 1524,
    "GAN": 1505, "CUR": 1436, "CAT": 1425,
}


def combined_strength(team: str, group_stats: dict) -> float:
    """Combina forca da fase de grupos com Elo pre-Copa."""
    gs = group_stats.get(team)
    group_str = estimate_strength(gs) if gs else 1.0
    elo = ELO_PRE.get(team, 1600)
    elo_norm = (elo - 1600) / 200
    return group_str * 0.6 + elo_norm * 0.4


# ============================================================================
# MODELO OTIMIZADO (do backtesting) — CAMPO NEUTRO
# Bonus de +0.3 para anfitrioes jogando no proprio pais
# ============================================================================

# Venues do R32 — anfitrioes com vantagem real
HOST_ADVANTAGE = {
    # (match_index): team que tem vantagem de casa
    6: "MEX",   # MEX vs EQU em Mexico City
    11: "EUA",  # EUA vs BOS em Santa Clara
}
HOST_BONUS = 0.3


def predict_score(team_a: str, team_b: str,
                  strength: Dict[str, float],
                  host_team: str = "") -> Tuple[int, int]:
    """Gera palpite em campo NEUTRO. Ordem dos nomes nao importa."""
    a_str = strength.get(team_a, 1.0)
    b_str = strength.get(team_b, 1.0)

    # Bonus anfitriao (so pra quem joga no proprio pais)
    if host_team == team_a:
        a_str += HOST_BONUS
    elif host_team == team_b:
        b_str += HOST_BONUS

    diff = a_str - b_str
    abs_diff = abs(diff)
    a_is_fav = diff >= 0

    if abs_diff < 0.5:
        return (1, 1)
    elif abs_diff < 2.0:
        score = (2, 1)
    elif abs_diff < 2.5:
        score = (2, 0)
    else:
        score = (3, 0)

    if a_is_fav:
        return score
    return (score[1], score[0])


# ============================================================================
# CHAVEAMENTO COMPLETO — ordem conforme bracket oficial
# ============================================================================

R32_MATCHES = [
    # Lado A
    ("AFS", "CAN"),       # 0 - Los Angeles (neutro)
    ("HOL", "MAR"),       # 1 - Monterrey (neutro)
    ("ALE", "PAR"),       # 2 - Boston (neutro)
    ("FRA", "SUE"),       # 3 - NY/NJ (neutro)
    ("BRA", "JAP"),       # 4 - Houston (neutro)
    ("CDM", "NOR"),       # 5 - Dallas (neutro)
    ("MEX", "EQU"),       # 6 - MEXICO CITY (MEX casa)
    ("ING", "RDC"),       # 7 - Atlanta (neutro)
    # Lado B
    ("ESP", "AUT"),       # 8 - Los Angeles (neutro)
    ("POR", "CRO"),       # 9 - Toronto (neutro)
    ("BEL", "SEN"),       # 10 - Seattle (neutro)
    ("EUA", "BOS"),       # 12
    ("EGT", "AUS"),       # 13
    ("ARG", "CPV"),       # 14
    ("SUI", "AGL"),       # 15
    ("COL", "GAN"),       # 16
]

R32_DATES = [
    "28/06", "29/06", "29/06", "30/06",
    "29/06", "30/06", "30/06", "01/07",
    "02/07", "02/07", "01/07", "01/07",
    "03/07", "03/07", "02/07", "03/07",
]

R16_PAIRS = [
    (0, 1), (2, 3), (4, 5), (6, 7),
    (8, 9), (10, 11), (12, 13), (14, 15),
]

QF_PAIRS = [(0, 1), (2, 3), (4, 5), (6, 7)]
SF_PAIRS = [(0, 1), (2, 3)]


def simulate_bracket(strength: Dict[str, float]):
    """Simula o mata-mata completo. Tudo campo neutro, sem home/away."""

    predictions = []

    def predict_match(team_a: str, team_b: str, phase: str,
                      host_team: str = ""):
        score = predict_score(team_a, team_b, strength, host_team)
        ga, gb = score
        if ga == gb:
            # Empate: avanca quem tem mais forca (penaltis = 50/50,
            # mas pro palpite precisamos escolher)
            s_a = strength.get(team_a, 1) + (HOST_BONUS if host_team == team_a else 0)
            s_b = strength.get(team_b, 1) + (HOST_BONUS if host_team == team_b else 0)
            winner = team_a if s_a >= s_b else team_b
        elif ga > gb:
            winner = team_a
        else:
            winner = team_b

        predictions.append({
            "phase": phase, "team_a": team_a, "team_b": team_b,
            "score": score, "winner": winner,
        })
        return winner, score

    # ---- R32 ----
    print(f"\n{'='*90}")
    print("  OITAVAS DE FINAL (Round of 32) — CAMPO NEUTRO")
    print("  Bonus anfitriao: MEX (Mexico City), EUA (Santa Clara)")
    print("  Pontuacao: exato 15, dif gols 9, gols venc 8, gols perd 6, "
          "vencedor 5")
    print(f"{'='*90}")
    print(f"\n  {'#':>3} {'Data':<8} {'Jogo':<22} {'Palpite':>8} "
          f"{'Avanca':>8}")
    print(f"  {'-'*55}")

    r32_winners = []
    for i, (team_a, team_b) in enumerate(R32_MATCHES):
        host = HOST_ADVANTAGE.get(i, "")
        winner, score = predict_match(team_a, team_b, "R32", host)
        r32_winners.append(winner)
        match_str = f"{team_a} vs {team_b}"
        score_str = f"{score[0]}x{score[1]}"
        host_flag = " *" if host else ""
        print(f"  {i+1:>3} {R32_DATES[i]:<8} {match_str:<22} "
              f"{score_str:>8} {winner:>8}{host_flag}")

    # ---- R16 (tudo neutro, sem bonus anfitriao) ----
    print(f"\n{'='*90}")
    print("  ROUND OF 16")
    print(f"{'='*90}")
    print(f"\n  {'#':>3} {'Jogo':<22} {'Palpite':>8} {'Avanca':>8}")
    print(f"  {'-'*45}")

    r16_winners = []
    for i, (a, b) in enumerate(R16_PAIRS):
        ta, tb = r32_winners[a], r32_winners[b]
        winner, score = predict_match(ta, tb, "R16")
        r16_winners.append(winner)
        match_str = f"{ta} vs {tb}"
        score_str = f"{score[0]}x{score[1]}"
        print(f"  {i+1:>3} {match_str:<22} {score_str:>8} {winner:>8}")

    # ---- QF ----
    print(f"\n{'='*90}")
    print("  QUARTAS DE FINAL")
    print(f"{'='*90}")
    print(f"\n  {'#':>3} {'Jogo':<22} {'Palpite':>8} {'Avanca':>8}")
    print(f"  {'-'*45}")

    qf_winners = []
    for i, (a, b) in enumerate(QF_PAIRS):
        ta, tb = r16_winners[a], r16_winners[b]
        winner, score = predict_match(ta, tb, "QF")
        qf_winners.append(winner)
        match_str = f"{ta} vs {tb}"
        score_str = f"{score[0]}x{score[1]}"
        print(f"  {i+1:>3} {match_str:<22} {score_str:>8} {winner:>8}")

    # ---- SF ----
    print(f"\n{'='*90}")
    print("  SEMIFINAIS")
    print(f"{'='*90}")
    print(f"\n  {'#':>3} {'Jogo':<22} {'Palpite':>8} {'Avanca':>8}")
    print(f"  {'-'*45}")

    sf_winners = []
    for i, (a, b) in enumerate(SF_PAIRS):
        ta, tb = qf_winners[a], qf_winners[b]
        winner, score = predict_match(ta, tb, "SF")
        sf_winners.append(winner)
        match_str = f"{ta} vs {tb}"
        score_str = f"{score[0]}x{score[1]}"
        print(f"  {i+1:>3} {match_str:<22} {score_str:>8} {winner:>8}")

    # ---- FINAL ----
    print(f"\n{'='*90}")
    print("  FINAL (19/07 - MetLife Stadium, NJ)")
    print(f"{'='*90}")

    ta, tb = sf_winners[0], sf_winners[1]
    winner, score = predict_match(ta, tb, "FINAL")
    print(f"\n  {ta} {score[0]} x {score[1]} {tb}")
    print(f"\n  *** CAMPEAO: {winner} ***")

    # ---- CAMINHO DO CAMPEAO ----
    print(f"\n{'='*90}")
    print(f"  CAMINHO DO CAMPEAO: {winner}")
    print(f"{'='*90}")
    for p in predictions:
        if p["team_a"] == winner or p["team_b"] == winner:
            s = p["score"]
            if p["team_a"] == winner:
                opp = p["team_b"]
                sc = f"{s[0]}x{s[1]}"
            else:
                opp = p["team_a"]
                sc = f"{s[1]}x{s[0]}"
            print(f"    {p['phase']:<8} vs {opp:<8} -> {sc}")

    # ---- TABELA PARA PREENCHER ----
    print(f"\n{'='*90}")
    print("  TABELA PARA PREENCHER NO BOLAO DO ZAP")
    print(f"{'='*90}")

    phases = [
        ("OITAVAS (R32)", "R32"),
        ("ROUND OF 16", "R16"),
        ("QUARTAS DE FINAL", "QF"),
        ("SEMIFINAIS", "SF"),
        ("FINAL", "FINAL"),
    ]
    for label, phase_key in phases:
        print(f"\n  {label}:")
        for p in predictions:
            if p["phase"] == phase_key:
                s = p["score"]
                print(f"    {p['team_a']:<5} {s[0]} x {s[1]} {p['team_b']:<5}")

    print(f"\n  CAMPEAO: {winner}")
    print()


def main():
    print("=" * 90)
    print("  PALPITES MATA-MATA — BOLAO DO ZAP — COPA DO MUNDO 2026")
    print("  Modelo otimizado com backtesting nos 72 jogos da fase de grupos")
    print("=" * 90)

    team_stats = compute_team_stats()

    strength = {}
    for team in set(list(ELO_PRE.keys()) + list(team_stats.keys())):
        strength[team] = combined_strength(team, team_stats)

    # Ranking
    print(f"\n  TOP 20 — RANKING DE FORCA COMBINADO (grupos + Elo):")
    print(f"  {'#':>3} {'Time':<5} {'Forca':>7} {'GrpStr':>7} {'Elo':>5}")
    print(f"  {'-'*30}")

    ranked = sorted(strength.items(), key=lambda x: x[1], reverse=True)
    for i, (team, stren) in enumerate(ranked[:20], 1):
        gs = team_stats.get(team)
        gs_str = estimate_strength(gs) if gs else 0
        elo = ELO_PRE.get(team, 1600)
        print(f"  {i:>3} {team:<5} {stren:>7.2f} {gs_str:>7.2f} {elo:>5}")

    simulate_bracket(strength)


if __name__ == "__main__":
    main()

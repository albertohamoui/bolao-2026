#!/usr/bin/env python3
"""
Analise completa do Bolao do Zap — Copa do Mundo 2026.

1. Resultados reais vs palpites
2. Pontuacao jogo a jogo
3. Padroes de erro
4. Backtesting com modelos alternativos
5. Otimizacao para o mata-mata

Uso: python3 analysis/copa2026_zap_analysis.py
"""

import sys
import os
from typing import Tuple
from collections import Counter, defaultdict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.scoring import zap_points

# ============================================================================
# RESULTADOS REAIS — Copa do Mundo 2026 (ate 27/06, grupos A-I completos)
# Grupos J, K, L: 2 jogos cada (rodada 3 em 27/06)
# ============================================================================

REAL_RESULTS = {
    # ---- GRUPO A (completo) ----
    "MEX vs AFS": (2, 0),
    "COR vs CZE": (2, 1),
    "CZE vs AFS": (1, 1),
    "MEX vs COR": (1, 0),
    "CZE vs MEX": (0, 3),
    "AFS vs COR": (1, 0),

    # ---- GRUPO B (completo) ----
    "CAN vs BOS": (1, 1),
    "CAT vs SUI": (1, 1),
    "SUI vs BOS": (4, 1),
    "CAN vs CAT": (6, 0),
    "SUI vs CAN": (2, 1),
    "BOS vs CAT": (3, 1),

    # ---- GRUPO C (completo) ----
    "HAI vs ESC": (0, 1),
    "BRA vs MAR": (1, 1),
    "BRA vs HAI": (3, 0),
    "ESC vs MAR": (0, 1),
    "ESC vs BRA": (0, 3),
    "MAR vs HAI": (4, 2),

    # ---- GRUPO D (completo) ----
    "EUA vs PAR": (4, 1),
    "AUS vs TUR": (2, 0),
    "TUR vs PAR": (0, 1),
    "EUA vs AUS": (2, 0),
    "TUR vs EUA": (3, 2),
    "PAR vs AUS": (0, 0),

    # ---- GRUPO E (completo) ----
    "CDM vs EQU": (1, 0),
    "ALE vs CUR": (7, 1),
    "ALE vs CDM": (2, 1),
    "EQU vs CUR": (0, 0),
    "CUR vs CDM": (0, 2),
    "EQU vs ALE": (2, 1),

    # ---- GRUPO F (completo) ----
    "HOL vs JAP": (2, 2),
    "SUE vs TUN": (5, 1),
    "HOL vs SUE": (5, 1),
    "TUN vs JAP": (0, 4),
    "JAP vs SUE": (1, 1),
    "TUN vs HOL": (1, 3),

    # ---- GRUPO G (completo) ----
    "IRA vs NZL": (2, 2),
    "BEL vs EGT": (1, 1),
    "BEL vs IRA": (0, 0),
    "NZL vs EGT": (1, 3),
    "EGT vs IRA": (1, 1),
    "NZL vs BEL": (1, 5),

    # ---- GRUPO H (completo) ----
    "SAU vs URU": (1, 1),
    "ESP vs CPV": (0, 0),
    "URU vs CPV": (2, 2),
    "ESP vs SAU": (4, 0),
    "CPV vs SAU": (0, 0),
    "URU vs ESP": (0, 1),

    # ---- GRUPO I (completo) ----
    "FRA vs SEN": (3, 1),
    "IRQ vs NOR": (1, 4),
    "NOR vs SEN": (3, 2),
    "FRA vs IRQ": (3, 0),
    "NOR vs FRA": (1, 4),
    "SEN vs IRQ": (5, 0),

    # ---- GRUPO J (2 rodadas jogadas, rodada 3 em 27/06) ----
    "ARG vs AGL": (3, 0),
    "AUT vs JRD": (3, 1),
    "ARG vs AUT": (2, 0),
    "JRD vs AGL": (1, 2),

    # ---- GRUPO K (2 rodadas jogadas, rodada 3 em 27/06) ----
    "POR vs RDC": (1, 1),
    "UZB vs COL": (1, 3),
    "POR vs UZB": (5, 0),
    "COL vs RDC": (1, 0),

    # ---- GRUPO L (2 rodadas jogadas, rodada 3 em 27/06) ----
    "ING vs CRO": (4, 2),
    "GAN vs PAN": (1, 0),
    "ING vs GAN": (0, 0),
    "PAN vs CRO": (0, 1),
}

# ============================================================================
# PALPITES DO BOLAO DO ZAP (extraidos da planilha, colunas E/F)
# ============================================================================

ZAP_BETS = {
    # Grupo A
    "MEX vs AFS": (2, 0),
    "COR vs CZE": (2, 1),
    "CZE vs AFS": (2, 1),
    "MEX vs COR": (2, 1),
    "CZE vs MEX": (2, 1),
    "AFS vs COR": (1, 2),
    # Grupo B
    "CAN vs BOS": (2, 0),
    "CAT vs SUI": (0, 2),
    "SUI vs BOS": (2, 0),
    "CAN vs CAT": (2, 0),
    "SUI vs CAN": (2, 1),
    "BOS vs CAT": (2, 1),
    # Grupo C
    "HAI vs ESC": (0, 2),
    "BRA vs MAR": (2, 1),
    "BRA vs HAI": (2, 0),
    "ESC vs MAR": (0, 2),
    "ESC vs BRA": (0, 2),
    "MAR vs HAI": (2, 0),
    # Grupo D
    "EUA vs PAR": (2, 1),
    "AUS vs TUR": (2, 1),
    "TUR vs PAR": (2, 1),
    "EUA vs AUS": (1, 2),
    "TUR vs EUA": (2, 1),
    "PAR vs AUS": (1, 1),
    # Grupo E
    "CDM vs EQU": (1, 1),
    "ALE vs CUR": (2, 0),
    "ALE vs CDM": (2, 0),
    "EQU vs CUR": (2, 0),
    "CUR vs CDM": (0, 2),
    "EQU vs ALE": (2, 1),
    # Grupo F
    "HOL vs JAP": (1, 2),
    "SUE vs TUN": (1, 2),
    "HOL vs SUE": (2, 0),
    "TUN vs JAP": (2, 0),
    "JAP vs SUE": (2, 0),
    "TUN vs HOL": (0, 2),
    # Grupo G
    "IRA vs NZL": (2, 0),
    "BEL vs EGT": (2, 0),
    "BEL vs IRA": (2, 0),
    "NZL vs EGT": (0, 2),
    "EGT vs IRA": (1, 2),
    "NZL vs BEL": (0, 2),
    # Grupo H
    "SAU vs URU": (0, 2),
    "ESP vs CPV": (2, 0),
    "URU vs CPV": (2, 0),
    "ESP vs SAU": (2, 0),
    "CPV vs SAU": (1, 1),
    "URU vs ESP": (0, 2),
    # Grupo I
    "FRA vs SEN": (2, 0),
    "IRQ vs NOR": (0, 2),
    "NOR vs SEN": (2, 1),
    "FRA vs IRQ": (2, 0),
    "NOR vs FRA": (0, 2),
    "SEN vs IRQ": (2, 0),
    # Grupo J
    "ARG vs AGL": (2, 0),
    "AUT vs JRD": (2, 0),
    "ARG vs AUT": (2, 0),
    "JRD vs AGL": (0, 2),
    "AGL vs AUT": (1, 2),
    "JRD vs ARG": (0, 2),
    # Grupo K
    "POR vs RDC": (2, 0),
    "UZB vs COL": (0, 2),
    "POR vs UZB": (2, 0),
    "COL vs RDC": (2, 0),
    "COL vs POR": (1, 2),
    "RDC vs UZB": (1, 1),
    # Grupo L
    "ING vs CRO": (2, 1),
    "GAN vs PAN": (2, 1),
    "ING vs GAN": (2, 0),
    "PAN vs CRO": (0, 2),
    "PAN vs ING": (0, 2),
    "CRO vs GAN": (2, 0),
}

# Palpites de classificacao — do modelo (bolao2026_results.json group_bets)
ZAP_GROUP_BETS = {
    "A": ("MEX", "COR"),
    "B": ("SUI", "CAN"),
    "C": ("BRA", "MAR"),
    "D": ("TUR", "AUS"),
    "E": ("ALE", "EQU"),
    "F": ("HOL", "JAP"),
    "G": ("BEL", "IRA"),
    "H": ("ESP", "URU"),
    "I": ("FRA", "NOR"),
    "J": ("ARG", "AUT"),
    "K": ("POR", "COL"),
    "L": ("ING", "CRO"),
}

ZAP_CHAMPION_BET = "ESP"

# ============================================================================
# CLASSIFICACAO REAL DOS GRUPOS (A-I completos)
# ============================================================================

REAL_GROUP_STANDINGS = {
    "A": ("MEX", "AFS", "COR", "CZE"),
    "B": ("SUI", "CAN", "BOS", "CAT"),
    "C": ("BRA", "MAR", "ESC", "HAI"),
    "D": ("EUA", "AUS", "PAR", "TUR"),
    "E": ("ALE", "CDM", "EQU", "CUR"),
    "F": ("HOL", "JAP", "SUE", "TUN"),
    "G": ("BEL", "EGT", "IRA", "NZL"),
    "H": ("ESP", "CPV", "URU", "SAU"),
    "I": ("FRA", "NOR", "SEN", "IRQ"),
}


# ============================================================================
# FUNCOES DE ANALISE
# ============================================================================

def classify_outcome(home: int, away: int) -> str:
    if home > away:
        return "HOME"
    elif away > home:
        return "AWAY"
    return "DRAW"


def analyze_match(match_key: str, bet: Tuple[int, int], real: Tuple[int, int]) -> dict:
    pts = zap_points(bet, real, knockout=False)
    bet_outcome = classify_outcome(*bet)
    real_outcome = classify_outcome(*real)

    if bet == real:
        accuracy = "EXATO"
    elif bet_outcome == real_outcome:
        if bet_outcome == "DRAW":
            accuracy = "EMPATE_ERRADO"
        elif (bet[0] - bet[1]) == (real[0] - real[1]):
            accuracy = "DIF_GOLS"
        elif max(bet) == max(real):
            accuracy = "GOLS_VENC"
        elif min(bet) == min(real):
            accuracy = "GOLS_PERD"
        else:
            accuracy = "SO_VENCEDOR"
    else:
        accuracy = "ERRADO"

    return {
        "match": match_key,
        "bet": bet,
        "real": real,
        "pts": pts,
        "accuracy": accuracy,
        "bet_outcome": bet_outcome,
        "real_outcome": real_outcome,
    }


def get_group(match_key: str) -> str:
    groups_teams = {
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
    teams = match_key.replace(" vs ", ",").split(",")
    for grp, grp_teams in groups_teams.items():
        if teams[0].strip() in grp_teams:
            return grp
    return "?"


def main():
    print("=" * 90)
    print("  ANALISE COMPLETA — BOLAO DO ZAP — COPA DO MUNDO 2026")
    print("  Data: 27/06/2026 (fim da fase de grupos)")
    print("=" * 90)

    # ================================================================
    # 1. ANALISE JOGO A JOGO
    # ================================================================
    results = []
    for match_key, real in REAL_RESULTS.items():
        if match_key in ZAP_BETS:
            analysis = analyze_match(match_key, ZAP_BETS[match_key], real)
            analysis["group"] = get_group(match_key)
            results.append(analysis)

    total_pts = sum(r["pts"] for r in results)
    total_games = len(results)

    print(f"\n  JOGOS ANALISADOS: {total_games} (de 72 totais)")
    print(f"  PONTUACAO TOTAL: {total_pts} pontos")
    print(f"  MEDIA POR JOGO: {total_pts / total_games:.2f} pontos")

    # ================================================================
    # 2. DISTRIBUICAO DE ACERTOS
    # ================================================================
    print(f"\n{'='*90}")
    print("  DISTRIBUICAO DE ACERTOS")
    print(f"{'='*90}")

    accuracy_counts = Counter(r["accuracy"] for r in results)
    pts_by_accuracy = defaultdict(int)
    for r in results:
        pts_by_accuracy[r["accuracy"]] += r["pts"]

    order = ["EXATO", "DIF_GOLS", "GOLS_VENC", "GOLS_PERD", "SO_VENCEDOR",
             "EMPATE_ERRADO", "ERRADO"]
    pts_labels = {"EXATO": 10, "DIF_GOLS": 6, "GOLS_VENC": 5, "GOLS_PERD": 4,
                  "SO_VENCEDOR": 3, "EMPATE_ERRADO": 6, "ERRADO": 0}

    print(f"\n  {'Categoria':<18} {'Qtd':>5} {'%':>6} {'Pts':>6} {'Valor unit.':>12}")
    print(f"  {'-'*50}")
    for cat in order:
        cnt = accuracy_counts.get(cat, 0)
        pct = 100 * cnt / total_games if total_games else 0
        pts = pts_by_accuracy.get(cat, 0)
        print(f"  {cat:<18} {cnt:>5} {pct:>5.1f}% {pts:>6} {pts_labels.get(cat, '?'):>12}")

    # ================================================================
    # 3. DETALHAMENTO POR GRUPO
    # ================================================================
    print(f"\n{'='*90}")
    print("  PONTUACAO POR GRUPO")
    print(f"{'='*90}")

    group_pts = defaultdict(lambda: {"pts": 0, "games": 0, "exatos": 0})
    for r in results:
        g = r["group"]
        group_pts[g]["pts"] += r["pts"]
        group_pts[g]["games"] += 1
        if r["accuracy"] == "EXATO":
            group_pts[g]["exatos"] += 1

    print(f"\n  {'Grupo':<8} {'Jogos':>6} {'Pts':>6} {'Media':>7} {'Exatos':>7}")
    print(f"  {'-'*40}")
    for grp in sorted(group_pts.keys()):
        g = group_pts[grp]
        avg = g["pts"] / g["games"] if g["games"] else 0
        print(f"  {grp:<8} {g['games']:>6} {g['pts']:>6} {avg:>7.2f} {g['exatos']:>7}")

    # ================================================================
    # 4. JOGO A JOGO DETALHADO
    # ================================================================
    print(f"\n{'='*90}")
    print("  JOGO A JOGO — PALPITE vs REAL")
    print(f"{'='*90}")

    print(f"\n  {'#':>3} {'Grp':>4} {'Jogo':<18} {'Palpite':>8} {'Real':>8} "
          f"{'Pts':>5} {'Status':<18}")
    print(f"  {'-'*70}")

    for i, r in enumerate(results, 1):
        bet_str = f"{r['bet'][0]}x{r['bet'][1]}"
        real_str = f"{r['real'][0]}x{r['real'][1]}"
        marker = " ***" if r["accuracy"] == "EXATO" else ""
        print(f"  {i:>3} {r['group']:>4} {r['match']:<18} {bet_str:>8} "
              f"{real_str:>8} {r['pts']:>5} {r['accuracy']:<18}{marker}")

    # ================================================================
    # 5. ERROS CRITICOS (0 pontos)
    # ================================================================
    print(f"\n{'='*90}")
    print("  ERROS CRITICOS (0 PONTOS)")
    print(f"{'='*90}")

    zeros = [r for r in results if r["pts"] == 0]
    print(f"\n  Total de zeros: {len(zeros)} de {total_games} jogos "
          f"({100*len(zeros)/total_games:.1f}%)")
    print(f"\n  {'Jogo':<20} {'Palpite':>8} {'Real':>8} {'Tipo':<30}")
    print(f"  {'-'*70}")
    for r in zeros:
        bet_str = f"{r['bet'][0]}x{r['bet'][1]}"
        real_str = f"{r['real'][0]}x{r['real'][1]}"
        tipo = f"Apostou {r['bet_outcome']}, deu {r['real_outcome']}"
        print(f"  {r['match']:<20} {bet_str:>8} {real_str:>8} {tipo:<30}")

    # ================================================================
    # 6. PADROES DE ERRO
    # ================================================================
    print(f"\n{'='*90}")
    print("  PADROES DE ERRO — INSIGHTS PARA O MATA-MATA")
    print(f"{'='*90}")

    bet_draws = sum(1 for r in results if r["bet_outcome"] == "DRAW")
    real_draws = sum(1 for r in results if r["real_outcome"] == "DRAW")
    print(f"\n  Empates apostados: {bet_draws} ({100*bet_draws/total_games:.1f}%)")
    print(f"  Empates reais:     {real_draws} ({100*real_draws/total_games:.1f}%)")

    bet_scores = Counter(ZAP_BETS[k] for k in REAL_RESULTS if k in ZAP_BETS)
    real_scores = Counter(REAL_RESULTS[k] for k in REAL_RESULTS)

    print(f"\n  Placares mais apostados (Zap):")
    for score, cnt in bet_scores.most_common(8):
        print(f"    {score[0]}x{score[1]}: {cnt} vezes")

    print(f"\n  Placares reais mais comuns:")
    for score, cnt in real_scores.most_common(10):
        print(f"    {score[0]}x{score[1]}: {cnt} vezes")

    bet_total_goals = [sum(ZAP_BETS[k]) for k in REAL_RESULTS if k in ZAP_BETS]
    real_total_goals = [sum(v) for v in REAL_RESULTS.values()]

    avg_bet = sum(bet_total_goals) / len(bet_total_goals)
    avg_real = sum(real_total_goals) / len(real_total_goals)
    print(f"\n  Media de gols por jogo (palpite): {avg_bet:.2f}")
    print(f"  Media de gols por jogo (real):    {avg_real:.2f}")
    vies = "subestima" if avg_real > avg_bet else "superestima"
    print(f"  Diferenca: {avg_real - avg_bet:+.2f} gols (modelo {vies})")

    # ================================================================
    # 7. CLASSIFICACAO DOS GRUPOS
    # ================================================================
    print(f"\n{'='*90}")
    print("  CLASSIFICACAO DOS GRUPOS — PALPITE vs REAL")
    print(f"{'='*90}")

    completed_groups = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    acertos_1st = 0
    acertos_2nd = 0

    print(f"\n  {'Grp':>4} {'Palp 1o':>10} {'Palp 2o':>10} {'Real 1o':>10} "
          f"{'Real 2o':>10} {'Status'}")
    print(f"  {'-'*65}")

    for grp in completed_groups:
        bet_1, bet_2 = ZAP_GROUP_BETS[grp]
        real_1, real_2 = REAL_GROUP_STANDINGS[grp][0], REAL_GROUP_STANDINGS[grp][1]

        status_parts = []
        if bet_1 == real_1:
            acertos_1st += 1
            status_parts.append("1o OK")
        else:
            status_parts.append(f"1o ERRADO (era {real_1})")

        if bet_2 == real_2:
            acertos_2nd += 1
            status_parts.append("2o OK")
        else:
            status_parts.append(f"2o ERRADO (era {real_2})")

        print(f"  {grp:>4} {bet_1:>10} {bet_2:>10} {real_1:>10} "
              f"{real_2:>10} {', '.join(status_parts)}")

    print(f"\n  Acertos 1o lugar: {acertos_1st}/{len(completed_groups)}")
    print(f"  Acertos 2o lugar: {acertos_2nd}/{len(completed_groups)}")

    # ================================================================
    # 8. SURPRESAS DESTA COPA
    # ================================================================
    print(f"\n{'='*90}")
    print("  GRANDES SURPRESAS DESTA COPA 2026")
    print(f"{'='*90}")

    surprises_list = [
        ("H", "Cabo Verde 2o! Uruguai ELIMINADO na fase de grupos",
         "3 empates de Cabo Verde bastaram; Uruguai nao venceu ninguem"),
        ("G", "Egito 2o (nao Ira)",
         "Egito consistente com 2 empates e 1 vitoria; Ira 3 empates"),
        ("E", "Costa do Marfim 2a (nao Equador)",
         "CDM venceu Equador e Curacao; Equador empatou com Curacao"),
        ("D", "EUA liderou (nao Turquia)",
         "Turquia 1 vitoria em 3 jogos; EUA forte como anfitrao"),
        ("A", "Africa do Sul 2a (nao Coreia do Sul)",
         "AFS venceu Coreia; resultado inesperado"),
        ("I", "Noruega GOLEOU Franca 4-1",
         "Resultado chocante na ultima rodada"),
        ("F", "Suecia 5-1 Tunisia, Holanda 5-1 Suecia",
         "Muitas goleadas neste grupo"),
        ("B", "Canada 6-0 Qatar, Suica 4-1 Bosnia",
         "Placares muito altos nao previstos"),
    ]

    for grp, surpresa, motivo in surprises_list:
        print(f"\n  [Grupo {grp}] {surpresa}")
        print(f"    -> {motivo}")

    # ================================================================
    # 9. BACKTESTING — ESTRATEGIAS ALTERNATIVAS
    # ================================================================
    print(f"\n{'='*90}")
    print("  BACKTESTING — ESTRATEGIAS ALTERNATIVAS NOS GRUPOS 2026")
    print(f"{'='*90}")

    # Gerar palpites para cada estrategia
    def make_fixed_bets(score: Tuple[int, int]) -> dict:
        return {k: score for k in REAL_RESULTS}

    def make_fav_bets(score: Tuple[int, int]) -> dict:
        """Mandante como favorito (simplificacao)."""
        return {k: score for k in REAL_RESULTS}

    strategies = {
        "Zap (original)": {k: ZAP_BETS[k] for k in REAL_RESULTS if k in ZAP_BETS},
        "Sempre 1x0 (mandante)": make_fav_bets((1, 0)),
        "Sempre 2x1 (mandante)": make_fav_bets((2, 1)),
        "Sempre 1x1": make_fixed_bets((1, 1)),
        "Sempre 0x0": make_fixed_bets((0, 0)),
        "Sempre 2x0 (mandante)": make_fav_bets((2, 0)),
        "Sempre 3x1 (mandante)": make_fav_bets((3, 1)),
    }

    print(f"\n  {'Estrategia':<30} {'Pts':>8} {'Media':>8} {'vs Zap':>8}")
    print(f"  {'-'*58}")

    zap_total = sum(
        zap_points(ZAP_BETS[k], REAL_RESULTS[k])
        for k in REAL_RESULTS if k in ZAP_BETS
    )

    for name, bets in sorted(
        strategies.items(),
        key=lambda x: -sum(zap_points(x[1][k], REAL_RESULTS[k]) for k in x[1]),
    ):
        total = sum(zap_points(bets[k], REAL_RESULTS[k]) for k in bets)
        avg = total / len(bets)
        diff = total - zap_total
        marker = " <-- NOSSO" if name == "Zap (original)" else ""
        print(f"  {name:<30} {total:>8} {avg:>8.2f} {diff:>+8}{marker}")

    # ================================================================
    # 10. ANALISE POR TIPO DE JOGO
    # ================================================================
    print(f"\n{'='*90}")
    print("  PONTUACAO POR TIPO DE RESULTADO REAL")
    print(f"{'='*90}")

    by_real_outcome = defaultdict(lambda: {"pts": 0, "count": 0, "zeros": 0})
    for r in results:
        o = r["real_outcome"]
        by_real_outcome[o]["pts"] += r["pts"]
        by_real_outcome[o]["count"] += 1
        if r["pts"] == 0:
            by_real_outcome[o]["zeros"] += 1

    print(f"\n  {'Resultado Real':<18} {'Jogos':>6} {'Pts':>6} {'Media':>7} "
          f"{'Zeros':>6} {'Taxa 0':>7}")
    print(f"  {'-'*55}")
    for outcome in ["HOME", "DRAW", "AWAY"]:
        d = by_real_outcome[outcome]
        avg = d["pts"] / d["count"] if d["count"] else 0
        zero_rate = 100 * d["zeros"] / d["count"] if d["count"] else 0
        print(f"  {outcome:<18} {d['count']:>6} {d['pts']:>6} {avg:>7.2f} "
              f"{d['zeros']:>6} {zero_rate:>6.1f}%")

    # ================================================================
    # 11. RECOMENDACOES PARA O MATA-MATA
    # ================================================================
    print(f"\n{'='*90}")
    print("  RECOMENDACOES PARA OTIMIZAR O MATA-MATA")
    print(f"{'='*90}")

    print("""
  PROBLEMAS IDENTIFICADOS:

  1. MODELO CONSERVADOR DEMAIS NOS PLACARES
     - Nossos palpites: quase tudo 2x0, 2x1, 0x2, 1x2
     - Realidade: muitas goleadas (7-1, 6-0, 5-1, 5-0, 4-2, 4-1, 4-0)
     - Media de gols real muito acima do previsto

  2. EMPATES SUBESTIMADOS
     - Nesta Copa houve muitos empates (0-0, 1-1, 2-2)
     - Varios empates em jogos que previamos vitoria clara

  3. FAVORITOS FALHARAM EM VARIOS GRUPOS
     - Turquia, Uruguai, Ira nao corresponderam
     - Cabo Verde, Africa do Sul, Costa do Marfim surpreenderam
     - Equador empatou 0-0 com Curacao!

  4. NO MATA-MATA A PONTUACAO DOBRA:
     - Exato: 15 pts | Dif gols: 9 | Gols vencedor: 8
     - Gols perdedor: 6 | So vencedor: 5
     - Empate exato: 15 | Empate errado: 9
     -> Prioridade MAXIMA: acertar o LADO (min 5 pts)
     -> Buscar exatos onde possivel (15 pts = diferencial enorme)

  AJUSTES PARA O MATA-MATA:

  1. Jogos muito desiguais: usar 3x0, 3x1, 4x1 (nao so 2x0)
     -> Esta Copa tem media ~3 gols/jogo, bem acima do historico

  2. Jogos equilibrados: 1x0 ou 2x1 para o favorito
     -> Mata-mata tende a ser mais fechado

  3. RECALIBRAR forcas com dados REAIS da fase de grupos:
     -> Noruega subiu muito (4-1 na Franca!)
     -> Cabo Verde surpreendeu (classificou em 2o!)
     -> Egito subiu (2o do grupo G)
     -> Turquia caiu (eliminada)
     -> Uruguai caiu (eliminado!)

  4. Considerar forma recente, nao so Elo pre-Copa
    """)


if __name__ == "__main__":
    main()

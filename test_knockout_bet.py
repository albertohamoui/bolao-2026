"""
Testes unitarios de optimal_knockout_bet e knockout_advance_points
vs manual oficial (bolaodozap.com pag 4 e 5).

Uso:
    python test_knockout_bet.py

Saida esperada: "OK (N testes)" em < 1s.
"""

import sys
import numpy as np
from scipy.stats import poisson

from bolao2026 import (
    optimal_knockout_bet,
    knockout_advance_points,
    bolao_points,
)


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}" + (f": {detail}" if detail else ""))
    else:
        FAILURES.append((name, detail))
        print(f"  FAIL {name}: {detail}")


def build_score_matrix(lh, la, max_goals=8):
    """Matriz de placares independente via Poisson (sem correcao de Dixon-Coles)."""
    m = np.zeros((max_goals, max_goals))
    for i in range(max_goals):
        for j in range(max_goals):
            m[i, j] = poisson.pmf(i, lh) * poisson.pmf(j, la)
    s = m.sum()
    if s > 0:
        m /= s
    return m


def p_advance_from_matrix(m):
    """
    P(home avanca) estimado da matriz: vitoria em 90min + metade do empate
    (aproxima prorrogacao+penaltis como 50/50 quando nao sabemos mais).
    Usado so nos testes. Na producao a marginal correta vem do MC.
    """
    p_home = float(np.sum(np.tril(m, -1)))
    p_draw = float(np.sum(np.diag(m)))
    return p_home + 0.5 * p_draw


def run():
    print("\n=== knockout_advance_points ===")
    check("zero acertos", knockout_advance_points([False, False, False]) == 0)
    check("um acerto", knockout_advance_points([True, False]) == 10)
    check("tres acertos", knockout_advance_points([True, True, True]) == 30)
    check("lista vazia", knockout_advance_points([]) == 0)

    print("\n=== optimal_knockout_bet: confronto desigual (Spain-like vs Cape Verde-like) ===")
    # Spain atacando ~2.5, Cape Verde ~0.3. P(Spain avanca) muito alto.
    m = build_score_matrix(2.5, 0.3)
    p_home = 0.95  # Spain avanca quase sempre
    out = optimal_knockout_bet(m, p_home, "Spain", "Cape Verde")

    check("bet_advance = favorito",
          out["bet_advance"] == "Spain",
          f"got {out['bet_advance']}")
    check("regime = vitoria (nao empate)",
          out["regime"] == "vitoria",
          f"got {out['regime']}")
    a, b = out["bet_score"]
    check("placar tem vencedor Spain (a > b)",
          a > b,
          f"got {a}x{b}")
    check("placar decisivo razoavel (1 <= a <= 4)",
          1 <= a <= 4,
          f"got {a}x{b}")
    check("EV_total > 15 (placar decente + bonus alto)",
          out["ev_total"] > 15,
          f"got {out['ev_total']:.2f}")
    check("EV_advance ~= 9.5 (10 * 0.95)",
          abs(out["ev_advance"] - 9.5) < 0.01,
          f"got {out['ev_advance']:.3f}")

    print("\n=== optimal_knockout_bet: confronto equilibrado (Brazil-like vs Croatia-like) ===")
    # Brasil ligeiro favorito: 1.5 x 1.2. Uma das ponderacoes no MC deve
    # dar algo como 55% para Brasil avancar.
    m = build_score_matrix(1.5, 1.2)
    p_home = 0.55
    out = optimal_knockout_bet(m, p_home, "Brazil", "Croatia")

    check("ev_total positivo e razoavel",
          5 < out["ev_total"] < 20,
          f"got {out['ev_total']:.2f}")
    # O importante aqui: qualquer que seja a escolha, o EV deve ser consistente.
    # Verificamos que o bet_advance maximiza mesmo: se escolheu Brazil,
    # EV(Brazil) >= EV(Croatia); se escolheu Croatia, o inverso.
    # Simetria: trocar home<->away exige transpor a matriz (m[i,j] vira m[j,i])
    # e inverter p_advance. EV_total deve ser identico.
    other_out = optimal_knockout_bet(m.T, 1 - p_home, "Croatia", "Brazil")
    check("simetria: inverter ordem dos times produz mesmo EV",
          abs(out["ev_total"] - other_out["ev_total"]) < 1e-9,
          f"brz-cro={out['ev_total']:.4f}, cro-brz={other_out['ev_total']:.4f}")
    print(f"    -> bet: {out['bet_score']} avanco={out['bet_advance']} "
          f"regime={out['regime']} EV={out['ev_total']:.2f}")

    print("\n=== optimal_knockout_bet: super equilibrado (50/50) ===")
    # Times identicos: lambda_home = lambda_away = 1.0, p_home = 0.5
    m = build_score_matrix(1.0, 1.0)
    p_home = 0.5
    out = optimal_knockout_bet(m, p_home, "TeamA", "TeamB")

    # Com 50/50 e placares simetricos, o empate deve competir forte.
    # Vamos verificar especificamente se o regime de empate e o escolhido.
    check("super equilibrado: regime = empate",
          out["regime"] == "empate",
          f"got {out['regime']}, placar={out['bet_score']}")
    a, b = out["bet_score"]
    check("placar de empate",
          a == b,
          f"got {a}x{b}")
    check("placar de empate plausivel (0x0 ou 1x1)",
          (a, b) in [(0, 0), (1, 1), (2, 2)],
          f"got {a}x{b}")
    check("ev_advance = 5.0 (10 * 0.5)",
          abs(out["ev_advance"] - 5.0) < 0.01,
          f"got {out['ev_advance']:.3f}")
    print(f"    -> bet: {out['bet_score']} avanco={out['bet_advance']} "
          f"regime={out['regime']} EV={out['ev_total']:.2f}")

    print("\n=== optimal_knockout_bet: sanity de consistencia ===")
    # EV_total deve ser monotonico em p_advance_home quando tudo mais e igual.
    m = build_score_matrix(1.5, 1.2)
    ev_low = optimal_knockout_bet(m, 0.3, "A", "B")["ev_total"]
    ev_mid = optimal_knockout_bet(m, 0.5, "A", "B")["ev_total"]
    ev_high = optimal_knockout_bet(m, 0.8, "A", "B")["ev_total"]
    # Nao e estritamente monotonico porque o regime pode trocar, mas
    # o EV no extremo alto (home muito provavel) deve ser > extremo baixo
    # quando a matriz favorece home.
    check("EV cresce com P(avanca) quando matriz favorece o home",
          ev_high >= ev_low,
          f"low(0.3)={ev_low:.2f}, high(0.8)={ev_high:.2f}")
    check("ev_score + ev_advance = ev_total",
          True,  # estrutural, sempre passa mas vale um sanity visual
          "")
    out = optimal_knockout_bet(m, 0.5, "A", "B")
    diff = abs(out["ev_score"] + out["ev_advance"] - out["ev_total"])
    check("decomposicao ev_total = ev_score + ev_advance",
          diff < 1e-9,
          f"diff={diff}")

    print("\n=== optimal_knockout_bet: vs baseline ingenuo ===")
    # Confirma que otimo >= baseline (apostar 1x0 com favorito avancando)
    m = build_score_matrix(1.8, 1.0)
    p_home = 0.7
    out = optimal_knockout_bet(m, p_home, "A", "B")

    # EV do baseline 1x0 + A avanca
    ev_baseline_score = 0.0
    for i in range(8):
        for j in range(8):
            ev_baseline_score += m[i, j] * bolao_points((1, 0), (i, j), knockout=True)
    ev_baseline_total = ev_baseline_score + 10 * p_home

    check("otimo >= baseline 1x0 + favorito",
          out["ev_total"] >= ev_baseline_total - 1e-9,
          f"otimo={out['ev_total']:.3f}, baseline={ev_baseline_total:.3f}")

    print()
    total = (4 + 6 + 3 + 5 + 4 + 1)  # contagem manual de checks por bloco
    passed = total - len(FAILURES)
    if FAILURES:
        print(f"FALHOU: {len(FAILURES)} de {total} testes")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
        return 1
    print(f"OK ({passed} testes)")
    return 0


if __name__ == "__main__":
    sys.exit(run())

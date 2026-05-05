"""
Testes unitarios de optimal_group_bet e optimal_champion_bet.

Usa matrizes conjuntas sinteticas (independente do Monte Carlo).

Uso:
    python test_group_champion_bet.py
"""

import sys
import numpy as np
from bolao2026 import optimal_group_bet, optimal_champion_bet


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}" + (f": {detail}" if detail else ""))
    else:
        FAILURES.append((name, detail))
        print(f"  FAIL {name}: {detail}")


def make_joint(k, cells):
    """cells: dict {(i, j): prob}. Resto zero. Nao normaliza."""
    m = np.zeros((k, k))
    for (i, j), p in cells.items():
        m[i, j] = p
    return m


def run():
    teams = ["A", "B", "C", "D"]

    print("\n=== optimal_group_bet: favorito dominante ===")
    # A e 1o em 80% dos cenarios, B fica em 2o na maioria deles.
    # P(1=A, 2=B) = 0.6; P(1=A, 2=C) = 0.1; P(1=A, 2=D) = 0.1
    # P(1=B, 2=A) = 0.1; P(1=C, 2=A) = 0.05; P(1=D, 2=A) = 0.05
    joint = make_joint(4, {
        (0, 1): 0.6, (0, 2): 0.1, (0, 3): 0.1,
        (1, 0): 0.1, (2, 0): 0.05, (3, 0): 0.05,
    })
    out = optimal_group_bet(joint, teams)
    check("bet_1st = A (favorito dominante)",
          out["bet_1st"] == "A", f"got {out['bet_1st']}")
    check("bet_2nd = B (segundo favorito)",
          out["bet_2nd"] == "B", f"got {out['bet_2nd']}")
    # EV esperado: 0.6*(10+10) + 0.1*(10+0) + 0.1*(10+0) + 0.1*(5+5) + 0.05*(5+0) + 0.05*(5+0)
    # = 12 + 1 + 1 + 1 + 0.25 + 0.25 = 15.5
    check("EV = 15.5 no cenario favorito dominante",
          abs(out["ev_points"] - 15.5) < 1e-9,
          f"got {out['ev_points']:.3f}")

    print("\n=== optimal_group_bet: correlacao alternada (A e B trocam) ===")
    # A e B disputam 1o/2o, 50/50. Qualquer par (A,B) ou (B,A) deve dar mesmo EV.
    joint = make_joint(4, {
        (0, 1): 0.5,  # A 1o, B 2o
        (1, 0): 0.5,  # B 1o, A 2o
    })
    out = optimal_group_bet(joint, teams)
    check("aposta eh dupla {A, B} (qualquer ordem)",
          {out["bet_1st"], out["bet_2nd"]} == {"A", "B"},
          f"got ({out['bet_1st']}, {out['bet_2nd']})")
    # Com (A, B): 0.5*(10+10) + 0.5*(5+5) = 10 + 5 = 15. Simetrico em (B, A).
    check("EV = 15 (simetria A<->B)",
          abs(out["ev_points"] - 15.0) < 1e-9,
          f"got {out['ev_points']:.3f}")

    print("\n=== optimal_group_bet: grupo uniforme ===")
    # 12 pares (i != j) com P = 1/12
    joint = np.ones((4, 4)) / 12.0
    np.fill_diagonal(joint, 0.0)
    out = optimal_group_bet(joint, teams)
    # Por simetria, qualquer par (b1, b2) distinto da mesmo EV.
    # EV = sum sobre pares (i!=j) de (1/12) * pts((b1,b2), (i,j))
    # Para b1=A, b2=B:
    #   (A,B) -> 20 (exato); (A,X) X!=B -> 10; (X,A) X!=B -> 5; (X,B) X!=A -> 10; (B,X) X!=A -> 5
    # Vou so verificar que EV e positivo e consistente
    check("EV >= 0 grupo uniforme",
          out["ev_points"] > 0,
          f"got {out['ev_points']:.3f}")
    # Calculo manual: cada bet paga em pelo menos alguns cenarios
    # total_pts considerando (A, B) como bet:
    # (A,B)=20, (A,C)=10, (A,D)=10, (C,A)=5, (D,A)=5, (B,A)=10 (b1=A e real 2o, b2=B e real 1o -> 5+5=10? Nope: bet_1st=A foi 2o (trocado), bet_2nd=B foi 1o (trocado). Ambos trocados -> 5+5=10)
    # (B,C)=5 (bet_2nd=B foi 1o real, trocado), (B,D)=5, (C,B)=10 (bet_2nd=B acertou 2o), (D,B)=10
    # (C,D)=0, (D,C)=0
    # Soma pts = 20+10+10+5+5+10+5+5+10+10 = 90
    # EV = 90 / 12 = 7.5
    check("EV = 7.5 grupo uniforme (formula conferida)",
          abs(out["ev_points"] - 7.5) < 1e-9,
          f"got {out['ev_points']:.3f}")

    print("\n=== optimal_group_bet: cenario cruzado premiado ===")
    # Cenario onde (1=A, 2=B) OU (1=B, 2=A) - queremos testar que apostar
    # A em 1o + B em 2o ganha EV comparado a apostar A e C.
    joint = make_joint(4, {
        (0, 1): 0.5,  # A=1, B=2
        (1, 0): 0.5,  # B=1, A=2
    })
    # bet (A, B): 0.5*20 + 0.5*10 = 15
    # bet (A, C): 0.5*10 + 0.5*5 = 7.5
    out = optimal_group_bet(joint, teams)
    check("bet correto captura correlacao cruzada",
          abs(out["ev_points"] - 15.0) < 1e-9,
          f"got {out['ev_points']:.3f}")
    check("p_both_exact = 0.5 (prob de acertar os dois)",
          abs(out["p_both_exact"] - 0.5) < 1e-9,
          f"got {out['p_both_exact']:.3f}")
    check("p_at_least_one_pt = 1.0 (algum pt sempre)",
          abs(out["p_at_least_one_pt"] - 1.0) < 1e-9,
          f"got {out['p_at_least_one_pt']:.3f}")

    print("\n=== optimal_champion_bet ===")
    probs = {"Spain": 0.2, "Brazil": 0.18, "France": 0.15, "Argentina": 0.1}
    out = optimal_champion_bet(probs)
    check("bet = favorito",
          out["bet"] == "Spain", f"got {out['bet']}")
    check("p_champion = 0.2",
          abs(out["p_champion"] - 0.2) < 1e-9,
          f"got {out['p_champion']}")
    check("ev = 25 * 0.2 = 5.0",
          abs(out["ev_points"] - 5.0) < 1e-9,
          f"got {out['ev_points']}")

    out_empty = optimal_champion_bet({})
    check("entrada vazia -> bet=None",
          out_empty["bet"] is None, f"got {out_empty['bet']}")

    # Empate em probabilidade: max devolve o primeiro (determinado por dict order)
    probs_tie = {"A": 0.3, "B": 0.3}
    out_tie = optimal_champion_bet(probs_tie)
    check("empate devolve algum dos dois",
          out_tie["bet"] in ("A", "B"), f"got {out_tie['bet']}")
    check("empate EV = 25 * 0.3 = 7.5",
          abs(out_tie["ev_points"] - 7.5) < 1e-9,
          f"got {out_tie['ev_points']}")

    print()
    total = (3 + 2 + 2 + 3 + 3 + 1 + 2)  # grupos por bloco
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

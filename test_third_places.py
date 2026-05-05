"""
Testes unitarios de induced_third_places e third_places_ev.

Constroi predictions sinteticas para um grupo pequeno e verifica
que a tabela induzida, o 3o lugar e o EV batem com calculo manual.

Uso:
    python test_third_places.py
"""

import sys
from bolao2026 import induced_third_places, third_places_ev


FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}" + (f": {detail}" if detail else ""))
    else:
        FAILURES.append((name, detail))
        print(f"  FAIL {name}: {detail}")


def make_pred(score_ev: str) -> dict:
    return {"score_ev": score_ev}


def run():
    print("\n=== induced_third_places: grupo simples ===")
    # Grupo A: 4 times, placares EV-optimal tal que:
    # A vence todos, B vence C e D, C vence D. Ordem esperada: A, B, C, D.
    groups = {"A": ["Alpha", "Beta", "Gamma", "Delta"]}
    predictions = {
        "Alpha vs Beta":  make_pred("2x0"),  # A 3pts
        "Alpha vs Gamma": make_pred("1x0"),  # A 3pts
        "Alpha vs Delta": make_pred("3x0"),  # A 3pts
        "Beta vs Gamma":  make_pred("2x1"),  # B 3pts
        "Beta vs Delta":  make_pred("1x0"),  # B 3pts
        "Gamma vs Delta": make_pred("2x1"),  # C 3pts
    }
    # Alpha: 9 pts, gd=+6
    # Beta: 6 pts, gd=+2
    # Gamma: 3 pts, gd=-1
    # Delta: 0 pts, gd=-7
    out = induced_third_places(predictions, groups)

    check("3o do grupo A = Gamma",
          out["thirds_per_group"]["A"] == "Gamma",
          f"got {out['thirds_per_group']['A']}")
    standings = out["induced_tables"]["A"]["standings"]
    check("standings corretos",
          standings == ["Alpha", "Beta", "Gamma", "Delta"],
          f"got {standings}")
    t = out["induced_tables"]["A"]["table"]
    check("Alpha 9 pts gd=+6",
          t["Alpha"]["pts"] == 9 and t["Alpha"]["gd"] == 6,
          f"got pts={t['Alpha']['pts']} gd={t['Alpha']['gd']}")
    check("Gamma 3 pts gd=-1",
          t["Gamma"]["pts"] == 3 and t["Gamma"]["gd"] == -1,
          f"got pts={t['Gamma']['pts']} gd={t['Gamma']['gd']}")

    print("\n=== induced_third_places: seleciona 8 melhores 3os entre 12 ===")
    # 12 grupos, todos com a mesma estrutura: time 1 vence todos, time 2 ganha
    # de 3 e 4, time 3 ganha de 4. Todos os 3os (time 3) ficam com 3 pts.
    # O criterio tiebreak sera gd e gf. Fabricamos para os 4 primeiros grupos
    # terem gd melhor.
    big_groups = {}
    big_preds = {}
    for idx, letter in enumerate("ABCDEFGHIJKL"):
        t1, t2, t3, t4 = f"{letter}1", f"{letter}2", f"{letter}3", f"{letter}4"
        big_groups[letter] = [t1, t2, t3, t4]
        # t3 vence t4 por 1x0 (mesma gd) em todos os grupos; variamos o
        # placar t3 vs t2 para dar gd diferente aos 3os.
        # Padrao: t1 vence todos, t2 vence t3 e t4, t3 vence t4
        # Na partida t2 vs t3, placar varia:
        # Grupos A-D: t2 vence 3x0 (t3 leva -3)
        # Grupos E-L: t2 vence 2x0 (t3 leva -2)
        # Grupos A-D entao tem 3o com gd = (+1 do vencer t4) + (-3 do perder t2) = -2
        # Grupos E-L tem 3o com gd = (+1) + (-2) = -1 -> MELHOR
        # Entao E-L deviam ficar entre os 8 melhores
        goals_vs_t2 = "3x0" if letter in "ABCD" else "2x0"
        big_preds[f"{t1} vs {t2}"] = make_pred("1x0")
        big_preds[f"{t1} vs {t3}"] = make_pred("2x0")
        big_preds[f"{t1} vs {t4}"] = make_pred("1x0")
        big_preds[f"{t2} vs {t3}"] = make_pred(goals_vs_t2)
        big_preds[f"{t2} vs {t4}"] = make_pred("1x0")
        big_preds[f"{t3} vs {t4}"] = make_pred("1x0")

    out = induced_third_places(big_preds, big_groups)
    top8 = set(out["top8_induced"])
    bottom4 = set(out["bottom4_eliminated"])

    check("top8 tem 8 elementos",
          len(out["top8_induced"]) == 8,
          f"got {len(out['top8_induced'])}")
    check("bottom4 tem 4 elementos",
          len(out["bottom4_eliminated"]) == 4,
          f"got {len(out['bottom4_eliminated'])}")
    check("3os com gd melhor (grupos E-L) entram no top8",
          all(f"{g}3" in top8 for g in "EFGHIJKL"),
          f"top8 = {out['top8_induced']}")
    check("3os com gd pior (grupos A-D) sao bottom4",
          bottom4 == {"A3", "B3", "C3", "D3"},
          f"bottom4 = {out['bottom4_eliminated']}")

    print("\n=== third_places_ev ===")
    # Construir team_stats sintetico
    top8_induced = ["A3", "B3", "C3", "D3", "E3", "F3", "G3", "H3"]
    team_stats = {
        "A3": {"group_3rd_qual": 80.0},
        "B3": {"group_3rd_qual": 60.0},
        "C3": {"group_3rd_qual": 40.0},
        "D3": {"group_3rd_qual": 20.0},
        "E3": {"group_3rd_qual": 50.0},
        "F3": {"group_3rd_qual": 50.0},
        "G3": {"group_3rd_qual": 50.0},
        "H3": {"group_3rd_qual": 10.0},
    }
    ev_out = third_places_ev(top8_induced, team_stats)
    # EV = 5 * (0.8+0.6+0.4+0.2+0.5+0.5+0.5+0.1) = 5 * 3.6 = 18.0
    check("EV = 18.0 com probs conhecidas",
          abs(ev_out["ev_points"] - 18.0) < 1e-9,
          f"got {ev_out['ev_points']:.3f}")
    check("per_team tem 8 entradas",
          len(ev_out["per_team"]) == 8,
          f"got {len(ev_out['per_team'])}")
    # Sanity: soma dos EV por team = total
    soma = sum(e["ev"] for e in ev_out["per_team"])
    check("soma por-team = total",
          abs(soma - ev_out["ev_points"]) < 1e-9,
          f"soma={soma}, total={ev_out['ev_points']}")

    # Team ausente -> p=0, nao quebra
    ev_out2 = third_places_ev(["Unknown"], {})
    check("time ausente nao quebra e contribui 0",
          ev_out2["ev_points"] == 0.0,
          f"got {ev_out2['ev_points']}")

    print()
    total = 4 + 4 + 4  # contagem manual
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

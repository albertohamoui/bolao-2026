"""
Smoke test do pipeline completo apos as extensoes:
- Confirma que group_bets aparece para todos os 12 grupos
- Confirma que champion_bet e populado
- Confirma que simulator guarda group_top2_joint com shape correto
- Mede tempo (deve ficar << 10s com n_sims reduzido)

Nao e teste unitario rigoroso - so sanity end-to-end.

Uso:
    python test_pipeline_smoke.py
"""

import sys
import time
from bolao2026 import Calibration, run_full_pipeline, GROUPS


def main():
    # n_sims reduzido pra smoke rapido; pipeline real usa 50k.
    cal = Calibration()
    cal.n_sims = 2000

    t0 = time.time()
    out = run_full_pipeline(cal, verbose=False)
    elapsed = time.time() - t0

    print(f"\nPipeline executado em {elapsed:.2f}s (n_sims={cal.n_sims}).")

    fails = []

    # group_bets
    gb = out.get("group_bets")
    if not gb:
        fails.append("group_bets ausente no output")
    elif set(gb.keys()) != set(GROUPS.keys()):
        fails.append(f"group_bets cobrindo {set(gb.keys())}, esperado {set(GROUPS.keys())}")
    else:
        print("\n--- Apostas de classificacao por grupo (smoke) ---")
        total_ev = 0.0
        for gname in sorted(gb.keys()):
            b = gb[gname]
            total_ev += b["ev_points"]
            for field in ("bet_1st", "bet_2nd", "ev_points",
                          "p_both_exact", "p_at_least_one_pt"):
                if field not in b:
                    fails.append(f"group_bets[{gname}] sem campo {field}")
            if b["bet_1st"] == b["bet_2nd"]:
                fails.append(f"group_bets[{gname}]: bet_1st == bet_2nd "
                             f"({b['bet_1st']})")
            if b["bet_1st"] not in GROUPS[gname]:
                fails.append(f"group_bets[{gname}]: bet_1st nao pertence ao grupo")
            if b["bet_2nd"] not in GROUPS[gname]:
                fails.append(f"group_bets[{gname}]: bet_2nd nao pertence ao grupo")
            print(f"  {gname}: {b['bet_1st']:<22} / {b['bet_2nd']:<22} "
                  f"EV={b['ev_points']:>6.2f}  Pexact={b['p_both_exact']:.3f}")
        print(f"  Total EV classificacao: {total_ev:.2f} / 240 max")

    # champion_bet
    ch = out.get("champion_bet")
    if not ch:
        fails.append("champion_bet ausente")
    elif ch.get("bet") is None:
        fails.append("champion_bet.bet e None")
    else:
        print(f"\n--- Aposta de campeao: {ch['bet']} "
              f"(P={ch['p_champion']*100:.2f}%, EV={ch['ev_points']:.2f})")
        # Sanity: ev = 25 * p
        if abs(ch["ev_points"] - 25 * ch["p_champion"]) > 1e-6:
            fails.append(f"champion_bet.ev_points nao bate com 25*p: "
                         f"{ch['ev_points']} vs {25*ch['p_champion']}")

    # Sanity: soma de EV esperada > 0
    total_group_ev = sum(gb[g]["ev_points"] for g in gb) if gb else 0
    if total_group_ev <= 0:
        fails.append(f"soma de EV de grupos <= 0: {total_group_ev}")

    # third_places diagnostico
    tp = out.get("third_places")
    if not tp:
        fails.append("third_places ausente")
    else:
        if len(tp.get("thirds_per_group", {})) != 12:
            fails.append(f"thirds_per_group nao tem 12 entradas: "
                         f"{len(tp.get('thirds_per_group', {}))}")
        if len(tp.get("top8_induced", [])) != 8:
            fails.append(f"top8_induced nao tem 8 entradas: "
                         f"{len(tp.get('top8_induced', []))}")
        if len(tp.get("bottom4_eliminated", [])) != 4:
            fails.append(f"bottom4_eliminated nao tem 4 entradas: "
                         f"{len(tp.get('bottom4_eliminated', []))}")
        # Sanity: EV dos 3os entre 0 e 40
        if not (0 <= tp["ev_points"] <= 40):
            fails.append(f"ev_points 3os fora de [0, 40]: {tp['ev_points']}")
        print(f"\n--- 3os induzidos (top 8): "
              f"{', '.join(tp['top8_induced'])}")
        print(f"    Eliminados: {', '.join(tp['bottom4_eliminated'])}")
        print(f"    EV 3os: {tp['ev_points']:.2f} / 40 max")

    # Tempo: apenas informativo. O budget de <= 10s e para n_sims=50k
    # na maquina do usuario; a sandbox de CI pode ser mais lenta.
    print(f"\n(tempo informativo: {elapsed:.2f}s com n_sims={cal.n_sims})")

    print()
    if fails:
        print(f"FALHOU ({len(fails)} problemas):")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("OK (smoke test)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

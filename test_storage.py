"""
Testa end-to-end a Parte 2: roda 2 simulacoes com calibracoes diferentes,
salva ambas, lista, compara, testa lock, deleta.

Uso:
    python3 test_storage.py

Tempo esperado: ~15 segundos (2 pipelines de ~6s cada + overhead).
"""

import os
import time
from copy import deepcopy

from bolao2026 import load_config, run_full_pipeline
from services.storage import (
    init_db, save_simulation, load_simulation, list_simulations,
    update_simulation, delete_simulation, lock_simulation,
    count_simulations, get_locked_simulation,
    set_market_odds, get_market_odds,
)
from services.sanity import run_sanity_checks, format_checks_for_terminal, summarize_checks
from services.diff import (
    diff_calibrations, diff_outputs, divergence_from_market,
    format_calibration_diff, format_output_diff,
)


# Usamos um DB separado pra teste, pra nao misturar com producao
TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_simulations.db")


def cleanup():
    """Remove o DB de teste se existir."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def run_pipeline_with_timing(cal, label):
    print(f"\n{'='*60}")
    print(f"  RODANDO PIPELINE: {label}")
    print(f"{'='*60}")
    t0 = time.time()
    output = run_full_pipeline(cal, verbose=False)
    elapsed = time.time() - t0
    print(f"  Concluido em {elapsed:.1f}s")
    return output, elapsed


def main():
    print("\n" + "#" * 60)
    print("# TESTE DE STORAGE - PARTE 2")
    print("#" * 60)

    cleanup()
    init_db(TEST_DB)

    # ------------------------------------------------------------------
    # Simulacao 1: configuracao padrao
    # ------------------------------------------------------------------
    cal1 = load_config("config.json")
    output1, runtime1 = run_pipeline_with_timing(cal1, "Calibracao PADRAO (baseline)")

    print("\nRodando sanity checks...")
    checks1 = run_sanity_checks(output1, runtime_seconds=runtime1)
    print(format_checks_for_terminal(checks1))

    print("\nSalvando simulacao 1...")
    sim1_id = save_simulation(
        name="Baseline (DC 45 / Elo 30 / TM 25)",
        notes="Configuracao padrao pos-refatoracao",
        calibration=cal1.to_dict(),
        output=output1,
        sanity_checks=checks1,
        runtime_seconds=runtime1,
        db_path=TEST_DB,
    )
    print(f"  Salvo com id={sim1_id}")

    # ------------------------------------------------------------------
    # Simulacao 2: mais peso no Dixon-Coles
    # ------------------------------------------------------------------
    cal2_dict = deepcopy(cal1.to_dict())
    cal2_dict["w_dc"] = 0.60
    cal2_dict["w_elo"] = 0.15
    cal2_dict["w_tm"] = 0.25
    # Teste expert adjustment
    cal2_dict["expert_adjustments"] = {
        "Brazil": {"attack_mult": 0.92}
    }

    from bolao2026 import Calibration
    cal2 = Calibration.from_dict(cal2_dict)

    output2, runtime2 = run_pipeline_with_timing(cal2, "Mais DC + Brasil -8%")

    print("\nRodando sanity checks...")
    checks2 = run_sanity_checks(output2, runtime_seconds=runtime2)
    print(format_checks_for_terminal(checks2))

    print("\nSalvando simulacao 2...")
    sim2_id = save_simulation(
        name="DC 60/15/25 + Brasil -8%",
        notes="Teste com mais peso DC e Brasil penalizado",
        calibration=cal2.to_dict(),
        output=output2,
        sanity_checks=checks2,
        runtime_seconds=runtime2,
        db_path=TEST_DB,
    )
    print(f"  Salvo com id={sim2_id}")

    # ------------------------------------------------------------------
    # Listar simulacoes
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  LISTAGEM DE SIMULACOES")
    print("=" * 60)
    sims = list_simulations(db_path=TEST_DB)
    for s in sims:
        lock_tag = " 🔒" if s["is_locked"] else ""
        print(f"\n  #{s['id']} — {s['name']}{lock_tag}")
        print(f"  Criada: {s['created_at']}  Runtime: {s['runtime_seconds']:.1f}s")
        print(f"  Sanity: {s['sanity_summary']}")
        print(f"  Notas: {s['notes']}")
        print(f"  Top 5 campeoes:")
        for team, pct in s["top5"]:
            print(f"    - {team}: {pct:.1f}%")

    # ------------------------------------------------------------------
    # Diff entre as duas
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  DIFF ENTRE SIMULACOES")
    print("=" * 60)

    s1 = load_simulation(sim1_id, db_path=TEST_DB)
    s2 = load_simulation(sim2_id, db_path=TEST_DB)

    cal_diff = diff_calibrations(s1["calibration"], s2["calibration"])
    print("\n" + format_calibration_diff(cal_diff))

    out_diff = diff_outputs(s1["output"], s2["output"], top_n=10)
    print("\n" + format_output_diff(out_diff))

    # ------------------------------------------------------------------
    # Market odds + divergencia
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  MERCADO E DIVERGENCIA")
    print("=" * 60)

    print("\nSalvando odds de mercado (exemplo)...")
    market = {
        "Spain": 16.4, "France": 14.0, "Argentina": 9.4, "England": 12.4,
        "Brazil": 7.0, "Portugal": 5.0, "Germany": 5.0, "Netherlands": 4.0,
    }
    for team, p in market.items():
        set_market_odds(team, p, db_path=TEST_DB)

    odds = get_market_odds(db_path=TEST_DB)
    print(f"  Odds salvas: {len(odds)} times")

    div1 = divergence_from_market(s1["output"], odds)
    div2 = divergence_from_market(s2["output"], odds)
    print(f"\n  Divergencia media (baseline):    {div1['mean_absolute_error']:.2f}pp")
    print(f"  Divergencia media (DC60+Brasil-): {div2['mean_absolute_error']:.2f}pp")

    print(f"\n  Maiores divergencias do baseline:")
    for d in div1["largest_divergences"][:5]:
        sign = "+" if d["diff"] > 0 else ""
        print(f"    {d['team']:<15} modelo={d['model']:.1f}% mercado={d['market']:.1f}% ({sign}{d['diff']:.1f})")

    # ------------------------------------------------------------------
    # Testar lock e update
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  TESTE LOCK / UPDATE / DELETE")
    print("=" * 60)

    print(f"\nTotal antes do lock: {count_simulations(TEST_DB)}")

    lock_simulation(sim1_id, db_path=TEST_DB)
    locked = get_locked_simulation(db_path=TEST_DB)
    print(f"  Simulacao travada: #{locked['id']} — {locked['name']}")

    update_simulation(sim2_id,
                      notes="Nota atualizada via update_simulation",
                      db_path=TEST_DB)
    s2_updated = load_simulation(sim2_id, db_path=TEST_DB)
    print(f"  Notas da sim2 agora: '{s2_updated['notes']}'")

    # Deleta a sim2
    delete_simulation(sim2_id, db_path=TEST_DB)
    print(f"  Sim #{sim2_id} deletada.")
    print(f"  Total depois do delete: {count_simulations(TEST_DB)}")

    # ------------------------------------------------------------------
    # Resultado final
    # ------------------------------------------------------------------
    print("\n" + "#" * 60)
    print("# TESTE CONCLUIDO COM SUCESSO")
    print("#" * 60)
    print(f"\n  DB de teste: {TEST_DB}")
    print(f"  Tamanho: {os.path.getsize(TEST_DB) / 1024:.1f} KB")
    print(f"\n  Para limpar: rm {TEST_DB}")


if __name__ == "__main__":
    main()
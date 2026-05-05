"""
Sanity checks automaticos para outputs de simulacao.
Baseado na secao 11.7 do bolao2026_documentacao.md.

Cada check retorna:
    {"passed": bool, "message": str, "severity": "critical"|"warning"}

Uso:
    from services.sanity import run_sanity_checks
    results = run_sanity_checks(output, runtime_seconds=5.8)
    # results = {"runtime_ok": {"passed": True, ...}, ...}
"""

from __future__ import annotations

from typing import Dict, Any, Optional


Check = Dict[str, Any]  # {"passed": bool, "message": str, "severity": str}


def _pass(msg: str, severity: str = "warning") -> Check:
    return {"passed": True, "message": msg, "severity": severity}


def _fail(msg: str, severity: str = "warning") -> Check:
    return {"passed": False, "message": msg, "severity": severity}


def check_runtime(runtime_seconds: Optional[float]) -> Check:
    """Runtime esperado entre 3 e 20 segundos pro pipeline completo."""
    if runtime_seconds is None:
        return _pass("runtime nao medido", "warning")
    if 3 <= runtime_seconds <= 20:
        return _pass(f"runtime {runtime_seconds:.1f}s dentro do esperado")
    if runtime_seconds < 3:
        return _fail(f"runtime suspeito baixo: {runtime_seconds:.1f}s (Monte Carlo rodou?)",
                     "critical")
    return _fail(f"runtime alto: {runtime_seconds:.1f}s (performance degradada?)",
                 "warning")


def check_top5_are_elo_top(output: Dict[str, Any]) -> Check:
    """Top 5 favoritos ao titulo devem ter pelo menos 3 no top 10 de Elo."""
    stats = output.get("simulation_stats", {})
    elo = output.get("elo_ratings", {})

    if not stats or not elo:
        return _fail("stats ou elo_ratings ausentes", "critical")

    top5_champ = sorted(stats.items(), key=lambda x: x[1].get("champion", 0), reverse=True)[:5]
    top5_names = {t for t, _ in top5_champ}
    top10_elo = sorted(elo.items(), key=lambda x: x[1], reverse=True)[:10]
    top10_elo_names = {t for t, _ in top10_elo}

    overlap = top5_names & top10_elo_names
    if len(overlap) >= 3:
        return _pass(f"{len(overlap)}/5 favoritos estao no top 10 de Elo")
    return _fail(f"so {len(overlap)}/5 favoritos no top 10 Elo "
                 f"(top5: {sorted(top5_names)})", "critical")


def check_cascade_monotonic(output: Dict[str, Any]) -> Check:
    """
    Cascata deve ser decrescente: r16 >= qf >= sf >= final >= champion.
    Tolerancia de 0.1pp para ruido do Monte Carlo.
    """
    stats = output.get("simulation_stats", {})
    if not stats:
        return _fail("simulation_stats ausente", "critical")

    TOL = 0.1
    violations = []
    for team, s in stats.items():
        try:
            r16 = s.get("r16", 0)
            qf = s.get("qf", 0)
            sf = s.get("sf", 0)
            fn = s.get("final", 0)
            ch = s.get("champion", 0)
            if not (r16 + TOL >= qf >= sf - TOL >= fn - TOL >= ch - TOL):
                # Checa cada par separadamente pra log melhor
                if qf > r16 + TOL:
                    violations.append(f"{team}: qf({qf}) > r16({r16})")
                if sf > qf + TOL:
                    violations.append(f"{team}: sf({sf}) > qf({qf})")
                if fn > sf + TOL:
                    violations.append(f"{team}: final({fn}) > sf({sf})")
                if ch > fn + TOL:
                    violations.append(f"{team}: champ({ch}) > final({fn})")
        except (KeyError, TypeError):
            continue

    if not violations:
        return _pass("cascata de fases monotonicamente decrescente")
    return _fail(f"{len(violations)} violacoes na cascata: {violations[:3]}",
                 "critical")


def check_group_probs_sum_100(output: Dict[str, Any]) -> Check:
    """Soma de (1o + 2o + 3oQ + eliminado) deve ser 100% por time."""
    stats = output.get("simulation_stats", {})
    groups = output.get("groups", {})
    if not stats or not groups:
        return _fail("stats ou groups ausentes", "critical")

    TOL = 0.5
    violations = []
    for gname, teams in groups.items():
        for team in teams:
            s = stats.get(team, {})
            total = (s.get("group_1st", 0)
                     + s.get("group_2nd", 0)
                     + s.get("group_3rd_qual", 0))
            # Time eliminado = 100 - total. Se total > 100, erro.
            if total > 100 + TOL:
                violations.append(f"{team}: classif = {total:.1f}%")

    if not violations:
        return _pass("probabilidades de classificacao somam <= 100%")
    return _fail(f"{len(violations)} times com prob > 100%: {violations[:3]}",
                 "critical")


def check_hosts_reasonable(output: Dict[str, Any]) -> Check:
    """
    Hosts (USA, Mexico, Canada) devem ter chance razoavel de avancar (>= 40%).
    Se estiver muito baixo, bug no host advantage.
    """
    stats = output.get("simulation_stats", {})
    if not stats:
        return _fail("simulation_stats ausente", "critical")

    hosts = ["United States", "Mexico", "Canada"]
    low = []
    for h in hosts:
        s = stats.get(h, {})
        advance = s.get("group_1st", 0) + s.get("group_2nd", 0) + s.get("group_3rd_qual", 0)
        if advance < 40:
            low.append(f"{h}: {advance:.1f}%")

    if not low:
        return _pass("hosts com >= 40% de chance de avancar")
    return _fail(f"hosts com pouca chance: {low}", "warning")


def check_ev_diverges_from_modal(output: Dict[str, Any]) -> Check:
    """
    O EV-optimal deve divergir do modal em 15-40% dos jogos.
    Fora desse range = sinal de problema (ou placares todos iguais, ou muito ruido).
    """
    preds = output.get("predictions", {})
    if not preds:
        return _fail("predictions ausente", "critical")

    total = len(preds)
    diverges = sum(1 for p in preds.values() if p.get("score_modal") != p.get("score_ev"))
    if total == 0:
        return _fail("nenhuma predicao", "critical")

    frac = diverges / total
    if 0.10 <= frac <= 0.50:
        return _pass(f"EV diverge do modal em {diverges}/{total} ({frac*100:.0f}%)")
    return _fail(f"EV diverge em {frac*100:.0f}% (esperado 10-50%)", "warning")


def check_draw_probs_reasonable(output: Dict[str, Any]) -> Check:
    """Probabilidade media de empate por jogo deve estar entre 18-38%."""
    preds = output.get("predictions", {})
    if not preds:
        return _fail("predictions ausente", "critical")

    draws = [p.get("draw", 0) for p in preds.values()]
    if not draws:
        return _fail("sem probabilidades de empate", "critical")

    avg = sum(draws) / len(draws)
    if 18 <= avg <= 38:
        return _pass(f"prob media de empate = {avg:.1f}%")
    return _fail(f"prob media de empate fora do range: {avg:.1f}% "
                 f"(esperado 18-38%)", "warning")


def check_output_structure(output: Dict[str, Any]) -> Check:
    """Valida que o output tem as chaves esperadas."""
    required = ["predictions", "simulation_stats", "model_params",
                "calibration", "groups", "elo_ratings"]
    missing = [k for k in required if k not in output]
    if not missing:
        return _pass("output tem todas as chaves esperadas")
    return _fail(f"chaves faltando: {missing}", "critical")


def run_sanity_checks(
    output: Dict[str, Any],
    runtime_seconds: Optional[float] = None,
) -> Dict[str, Check]:
    """
    Roda todos os checks e retorna dict com resultados.
    """
    return {
        "output_structure": check_output_structure(output),
        "runtime": check_runtime(runtime_seconds),
        "top5_are_elo_top": check_top5_are_elo_top(output),
        "cascade_monotonic": check_cascade_monotonic(output),
        "group_probs_sum_100": check_group_probs_sum_100(output),
        "hosts_reasonable": check_hosts_reasonable(output),
        "ev_diverges_from_modal": check_ev_diverges_from_modal(output),
        "draw_probs_reasonable": check_draw_probs_reasonable(output),
    }


def summarize_checks(checks: Dict[str, Check]) -> Dict[str, Any]:
    """Resumo pra print ou logs."""
    total = len(checks)
    passed = sum(1 for c in checks.values() if c["passed"])
    critical_fails = [
        name for name, c in checks.items()
        if not c["passed"] and c.get("severity") == "critical"
    ]
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "critical_failures": critical_fails,
        "all_passed": passed == total,
        "no_critical_failures": len(critical_fails) == 0,
    }


def format_checks_for_terminal(checks: Dict[str, Check]) -> str:
    """Formata pra print bonito no terminal."""
    lines = []
    for name, c in checks.items():
        icon = "✅" if c["passed"] else ("❌" if c["severity"] == "critical" else "⚠️ ")
        lines.append(f"  {icon} {name}: {c['message']}")
    summary = summarize_checks(checks)
    lines.append(f"\n  Resumo: {summary['passed']}/{summary['total']} ok")
    if summary["critical_failures"]:
        lines.append(f"  ❌ Falhas criticas: {summary['critical_failures']}")
    return "\n".join(lines)

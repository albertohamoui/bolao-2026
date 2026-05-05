"""
Comparacao estruturada entre simulacoes.
- diff_calibrations: o que mudou na calibracao
- diff_outputs: o que mudou nos outputs (probabilidades, etc)
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple


# =============================================================================
# Diff de calibracoes
# =============================================================================

def diff_calibrations(cal_a: dict, cal_b: dict) -> Dict[str, Any]:
    """
    Compara duas calibracoes e retorna estrutura com as mudancas.

    Retorna:
        {
            "scalars": [{"field": "w_dc", "from": 0.45, "to": 0.60}, ...],
            "elo_changes": [{"team": "Brazil", "from": 1984, "to": 2010}, ...],
            "tm_changes": [...],
            "expert_changes": [{"team": "Brazil", "change": "added/removed/modified",
                                "from": ..., "to": ...}],
            "n_changes": int,
        }
    """
    SCALAR_FIELDS = ["w_dc", "w_elo", "w_tm", "xi", "wc_host_adv",
                     "n_sims", "date_cutoff", "tm_scale", "ad_split"]

    scalars = []
    for f in SCALAR_FIELDS:
        v_a = cal_a.get(f)
        v_b = cal_b.get(f)
        if v_a != v_b:
            scalars.append({"field": f, "from": v_a, "to": v_b})

    elo_a = cal_a.get("elo_ratings", {})
    elo_b = cal_b.get("elo_ratings", {})
    elo_changes = []
    for team in sorted(set(elo_a.keys()) | set(elo_b.keys())):
        v_a = elo_a.get(team)
        v_b = elo_b.get(team)
        if v_a != v_b:
            elo_changes.append({"team": team, "from": v_a, "to": v_b})

    tm_a = cal_a.get("transfermarkt_values", {})
    tm_b = cal_b.get("transfermarkt_values", {})
    tm_changes = []
    for team in sorted(set(tm_a.keys()) | set(tm_b.keys())):
        v_a = tm_a.get(team)
        v_b = tm_b.get(team)
        if v_a != v_b:
            tm_changes.append({"team": team, "from": v_a, "to": v_b})

    exp_a = cal_a.get("expert_adjustments", {}) or {}
    exp_b = cal_b.get("expert_adjustments", {}) or {}
    exp_changes = []
    for team in sorted(set(exp_a.keys()) | set(exp_b.keys())):
        if team in exp_a and team not in exp_b:
            exp_changes.append({"team": team, "change": "removed", "from": exp_a[team], "to": None})
        elif team not in exp_a and team in exp_b:
            exp_changes.append({"team": team, "change": "added", "from": None, "to": exp_b[team]})
        elif exp_a[team] != exp_b[team]:
            exp_changes.append({"team": team, "change": "modified",
                                "from": exp_a[team], "to": exp_b[team]})

    n = len(scalars) + len(elo_changes) + len(tm_changes) + len(exp_changes)

    return {
        "scalars": scalars,
        "elo_changes": elo_changes,
        "tm_changes": tm_changes,
        "expert_changes": exp_changes,
        "n_changes": n,
    }


# =============================================================================
# Diff de outputs
# =============================================================================

def diff_outputs(out_a: dict, out_b: dict, top_n: int = 10) -> Dict[str, Any]:
    """
    Compara dois outputs e retorna mudancas relevantes.

    Retorna:
        {
            "champion_changes": [{"team": "Brazil", "from": 12.0, "to": 8.4,
                                  "delta": -3.6}, ...],
            "group_1st_changes": [...],  # top N mudancas
            "new_favorites": [...],  # subiu muito
            "dropped_favorites": [...],  # caiu muito
        }
    """
    stats_a = out_a.get("simulation_stats", {})
    stats_b = out_b.get("simulation_stats", {})
    all_teams = sorted(set(stats_a.keys()) | set(stats_b.keys()))

    def collect_changes(key: str) -> List[Dict[str, Any]]:
        changes = []
        for team in all_teams:
            v_a = stats_a.get(team, {}).get(key, 0)
            v_b = stats_b.get(team, {}).get(key, 0)
            delta = v_b - v_a
            if abs(delta) >= 0.1:  # ignora ruido de MC
                changes.append({
                    "team": team, "from": v_a, "to": v_b, "delta": round(delta, 2),
                })
        changes.sort(key=lambda x: abs(x["delta"]), reverse=True)
        return changes[:top_n]

    champion_changes = collect_changes("champion")
    group_1st_changes = collect_changes("group_1st")
    final_changes = collect_changes("final")

    # Favoritos que emergiram/caíram (delta grande em champion)
    all_champion_changes = []
    for team in all_teams:
        v_a = stats_a.get(team, {}).get("champion", 0)
        v_b = stats_b.get(team, {}).get("champion", 0)
        if abs(v_b - v_a) >= 1.0:  # mais de 1pp
            all_champion_changes.append({
                "team": team, "from": v_a, "to": v_b, "delta": round(v_b - v_a, 2),
            })

    new_favs = [c for c in all_champion_changes if c["delta"] >= 1.0]
    new_favs.sort(key=lambda x: x["delta"], reverse=True)

    dropped = [c for c in all_champion_changes if c["delta"] <= -1.0]
    dropped.sort(key=lambda x: x["delta"])

    # Mudancas nos parametros do modelo
    params_a = out_a.get("model_params", {})
    params_b = out_b.get("model_params", {})
    home_adv_delta = params_b.get("home_adv", 0) - params_a.get("home_adv", 0)
    rho_delta = params_b.get("rho", 0) - params_a.get("rho", 0)

    return {
        "champion_changes": champion_changes,
        "group_1st_changes": group_1st_changes,
        "final_changes": final_changes,
        "new_favorites": new_favs,
        "dropped_favorites": dropped,
        "home_adv_delta": round(home_adv_delta, 4),
        "rho_delta": round(rho_delta, 4),
    }


# =============================================================================
# Divergencia com mercado
# =============================================================================

def divergence_from_market(
    output: dict,
    market_odds: Dict[str, float],
) -> Dict[str, Any]:
    """
    Calcula o quanto o output diverge das odds de mercado.

    market_odds: {team: champion_prob_em_percentual}
    Retorna:
        {
            "mean_absolute_error": float,
            "largest_divergences": [{"team", "model", "market", "diff"}, ...],
            "convergent": [...],  # diferenca < 1pp
        }
    """
    stats = output.get("simulation_stats", {})
    if not market_odds or not stats:
        return {"mean_absolute_error": None, "largest_divergences": [], "convergent": []}

    divergences = []
    for team, market_p in market_odds.items():
        model_p = stats.get(team, {}).get("champion", 0)
        diff = model_p - market_p
        divergences.append({
            "team": team,
            "model": round(model_p, 2),
            "market": round(market_p, 2),
            "diff": round(diff, 2),
        })

    mae = sum(abs(d["diff"]) for d in divergences) / len(divergences)
    divergences.sort(key=lambda x: abs(x["diff"]), reverse=True)

    largest = divergences[:10]
    convergent = [d for d in divergences if abs(d["diff"]) < 1.0]

    return {
        "mean_absolute_error": round(mae, 2),
        "largest_divergences": largest,
        "convergent": convergent,
    }


# =============================================================================
# Formatadores pra terminal
# =============================================================================

def format_calibration_diff(diff: Dict[str, Any]) -> str:
    """String bonita pra terminal."""
    lines = [f"Diff de calibracao ({diff['n_changes']} mudancas):"]

    if diff["scalars"]:
        lines.append("\n  Parametros:")
        for c in diff["scalars"]:
            lines.append(f"    {c['field']}: {c['from']} -> {c['to']}")

    if diff["elo_changes"]:
        lines.append(f"\n  Elo ({len(diff['elo_changes'])} mudancas):")
        for c in diff["elo_changes"][:10]:
            lines.append(f"    {c['team']}: {c['from']} -> {c['to']}")
        if len(diff["elo_changes"]) > 10:
            lines.append(f"    ... mais {len(diff['elo_changes']) - 10}")

    if diff["tm_changes"]:
        lines.append(f"\n  Transfermarkt ({len(diff['tm_changes'])} mudancas):")
        for c in diff["tm_changes"][:10]:
            lines.append(f"    {c['team']}: {c['from']} -> {c['to']}")

    if diff["expert_changes"]:
        lines.append(f"\n  Expert adjustments:")
        for c in diff["expert_changes"]:
            lines.append(f"    {c['team']} ({c['change']}): {c['from']} -> {c['to']}")

    if diff["n_changes"] == 0:
        lines.append("  (sem mudancas)")

    return "\n".join(lines)


def format_output_diff(diff: Dict[str, Any]) -> str:
    """String bonita pra terminal."""
    lines = ["Diff de outputs:"]

    if diff["champion_changes"]:
        lines.append("\n  Top mudancas em % campeao:")
        for c in diff["champion_changes"]:
            sign = "+" if c["delta"] > 0 else ""
            lines.append(f"    {c['team']:<25} {c['from']:.1f}% -> {c['to']:.1f}% ({sign}{c['delta']:.1f})")

    if diff["new_favorites"]:
        lines.append(f"\n  Novos favoritos (subiram >1pp):")
        for c in diff["new_favorites"][:5]:
            lines.append(f"    {c['team']:<25} +{c['delta']:.1f}pp")

    if diff["dropped_favorites"]:
        lines.append(f"\n  Favoritos em queda:")
        for c in diff["dropped_favorites"][:5]:
            lines.append(f"    {c['team']:<25} {c['delta']:.1f}pp")

    lines.append(f"\n  home_adv delta: {diff['home_adv_delta']:+.4f}")
    lines.append(f"  rho delta:      {diff['rho_delta']:+.4f}")

    return "\n".join(lines)

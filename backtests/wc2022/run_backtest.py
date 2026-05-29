#!/usr/bin/env python3
"""
Backtest LIMPO do modelo contra a Copa do Mundo 2022 no Catar.

Diferenças vs o backtest antigo (scripts/backtest_2022.py):
  - ELOs de nov/2022 (pré-Copa), NÃO de 2026
  - Transfermarkt de nov/2022, NÃO de 2026
  - Dados 100% isolados em backtests/wc2022/data/
  - Nenhuma dependência do config.json de 2026
  - Aceita override de calibração para uso pelo otimizador

Uso:
    python backtests/wc2022/run_backtest.py
"""

import csv
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Setup paths
BACKTEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(BACKTEST_DIR))
sys.path.insert(0, PROJECT_DIR)

from bolao2026 import (
    Calibration,
    DixonColesModel,
    WORLD_CUP_TEAM_LIST,
    _EXTERNAL_TO_MODEL_NAME,
    bolao_points,
    ev_optimal_score,
    load_matches,
)


# =============================================================================
# DADOS DA COPA 2022 — tudo hardcoded aqui, isolado do modelo 2026
# =============================================================================

GROUPS_2022 = {
    "A": ["Qatar", "Ecuador", "Senegal", "Netherlands"],
    "B": ["England", "Iran", "United States", "Wales"],
    "C": ["Argentina", "Saudi Arabia", "Mexico", "Poland"],
    "D": ["France", "Australia", "Denmark", "Tunisia"],
    "E": ["Spain", "Costa Rica", "Germany", "Japan"],
    "F": ["Belgium", "Canada", "Morocco", "Croatia"],
    "G": ["Brazil", "Serbia", "Switzerland", "Cameroon"],
    "H": ["Portugal", "Ghana", "Uruguay", "South Korea"],
}

WC2022_TEAMS = sorted({t for g in GROUPS_2022.values() for t in g})
WC2022_CUTOFF_DATE = "2022-11-20"
WC2022_END_DATE = "2022-12-18"


# =============================================================================
# LOADERS — dados de 2022, isolados
# =============================================================================

_cache = {}


def load_elo_2022() -> Dict[str, int]:
    """Carrega ELOs de nov/2022 do arquivo local (cached)."""
    if "elo" not in _cache:
        path = os.path.join(BACKTEST_DIR, "data", "elo_2022.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache["elo"] = {k: v for k, v in data.items() if not k.startswith("_")}
    return dict(_cache["elo"])


def load_tm_2022() -> Dict[str, int]:
    """Carrega Transfermarkt de nov/2022 do arquivo local (cached)."""
    if "tm" not in _cache:
        path = os.path.join(BACKTEST_DIR, "data", "tm_2022.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache["tm"] = {k: v for k, v in data.items() if not k.startswith("_")}
    return dict(_cache["tm"])


def load_wc2022_results() -> Tuple[list, list]:
    """Carrega resultados reais da Copa 2022 do results.csv do projeto."""
    csv_path = os.path.join(PROJECT_DIR, "results.csv")
    group_results = []
    knockout_results = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "FIFA World Cup" not in row.get("tournament", ""):
                continue
            if row["date"] < WC2022_CUTOFF_DATE or row["date"] > WC2022_END_DATE:
                continue

            home = _EXTERNAL_TO_MODEL_NAME.get(row["home_team"], row["home_team"])
            away = _EXTERNAL_TO_MODEL_NAME.get(row["away_team"], row["away_team"])
            hg = int(row["home_score"])
            ag = int(row["away_score"])

            match = {"home": home, "away": away, "hg": hg, "ag": ag, "date": row["date"]}

            if len(group_results) < 48:
                group_results.append(match)
            else:
                knockout_results.append(match)

    return group_results, knockout_results


# =============================================================================
# CALIBRAÇÃO DE 2022 — construída a partir dos dados de época
# =============================================================================

def inflated_score_matrix(model, home: str, away: str, k: float):
    """Recalcula score_matrix com lambdas multiplicados por k."""
    from scipy.stats import poisson
    import numpy as _np
    pred = model.predict_match(home, away, host_adv=0.0)
    lh, la = pred["lambdas"]
    lh *= k
    la *= k
    mg = 8
    sm = _np.zeros((mg, mg))
    for i in range(mg):
        for j in range(mg):
            sm[i, j] = poisson.pmf(i, lh) * poisson.pmf(j, la)
    total = sm.sum()
    if total > 0:
        sm /= total
    return sm, (lh, la)


def make_calibration_2022(
    w_dc: float = 0.45,
    w_elo: float = 0.30,
    w_tm: float = 0.25,
    xi: float = 0.001,
    date_cutoff: str = "2018-01-01",
    tm_scale: str = "sqrt",
    ad_split: Optional[List[float]] = None,
    dc_quality_filter_enabled: bool = True,
    dc_quality_filter_thresholds: Optional[List[int]] = None,
    dc_quality_filter_weights: Optional[List[float]] = None,
) -> Calibration:
    """
    Cria Calibration com dados de 2022 (ELOs e TM de época).
    Aceita overrides para o otimizador testar combinações.
    """
    elo_2022 = load_elo_2022()
    tm_2022 = load_tm_2022()

    if ad_split is None:
        ad_split = [0.6, -0.4]
    if dc_quality_filter_thresholds is None:
        dc_quality_filter_thresholds = [300, 200, 100]
    if dc_quality_filter_weights is None:
        dc_quality_filter_weights = [0.2, 0.5, 0.8, 1.0]

    # Garantir que todas as 48 da Copa 2026 tenham ELO/TM
    # (o blend bayesiano itera sobre WORLD_CUP_TEAM_LIST)
    full_elo = dict(elo_2022)
    full_tm = dict(tm_2022)
    for t in WORLD_CUP_TEAM_LIST:
        if t not in full_elo:
            full_elo[t] = 1500
        if t not in full_tm:
            full_tm[t] = 30

    cal = Calibration(
        w_dc=w_dc,
        w_elo=w_elo,
        w_tm=w_tm,
        xi=xi,
        wc_host_adv=0.0,  # Copa 2022 no Catar — nenhum participante é host
        n_sims=50000,
        date_cutoff=date_cutoff,
        tm_scale=tm_scale,
        ad_split=ad_split,
        dc_quality_filter={
            "enabled": dc_quality_filter_enabled,
            "thresholds": dc_quality_filter_thresholds,
            "weights": dc_quality_filter_weights,
        },
        tournament_factor={"enabled": False},
        top_scorer_model={"enabled": False},
        squad_data={"enabled": False},
        elo_ratings=full_elo,
        transfermarkt_values=full_tm,
        expert_adjustments={},
    )
    return cal


# =============================================================================
# TREINO E PREVISÃO
# =============================================================================

def _load_all_matches():
    """Carrega todos os jogos do results.csv (cached)."""
    if "matches" not in _cache:
        csv_path = os.path.join(PROJECT_DIR, "results.csv")
        _cache["matches"] = load_matches(csv_path)
        all_teams_set = set()
        for h, a, _, _, _ in _cache["matches"]:
            all_teams_set.add(h)
            all_teams_set.add(a)
        _cache["all_teams"] = sorted(all_teams_set)
    return _cache["matches"], _cache["all_teams"]


def train_model(cal: Calibration) -> DixonColesModel:
    """Treina DC com jogos anteriores à Copa 2022, usando ELOs de 2022."""
    elo_2022 = load_elo_2022()

    all_matches, all_teams = _load_all_matches()

    # ELOs: times fora da Copa 2022 recebem default
    world_elo = {t: elo_2022.get(t, 1500) for t in all_teams}

    model = DixonColesModel(all_teams, cal, world_elo=world_elo)

    # Filtrar jogos: só antes da Copa
    cutoff_ord = datetime.strptime(WC2022_CUTOFF_DATE, "%Y-%m-%d").toordinal()
    train_cutoff_ord = datetime.strptime(cal.date_cutoff, "%Y-%m-%d").toordinal()
    pre_wc = [m for m in all_matches if train_cutoff_ord <= m[4] < cutoff_ord]

    print(f"Jogos de treino ({cal.date_cutoff} a {WC2022_CUTOFF_DATE}): {len(pre_wc):,}")
    model.fit(pre_wc)
    return model


def generate_group_predictions(model: DixonColesModel, goal_inflation: float = 1.0) -> dict:
    """Gera previsões EV-optimal para fase de grupos."""
    predictions = {}
    for gname, teams in sorted(GROUPS_2022.items()):
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                h, a = teams[i], teams[j]
                if goal_inflation != 1.0:
                    sm, lambdas = inflated_score_matrix(model, h, a, goal_inflation)
                else:
                    pred = model.predict_match(h, a, host_adv=0.0)
                    sm, lambdas = pred["score_matrix"], pred["lambdas"]
                ev_score, ev_pts = ev_optimal_score(sm, knockout=False)
                key = f"{h} vs {a}"
                predictions[key] = {
                    "home": h, "away": a, "group": gname,
                    "bet": ev_score, "ev_pts": ev_pts,
                    "lambdas": lambdas,
                }
    return predictions


def generate_knockout_predictions(model: DixonColesModel, knockout_results: list, goal_inflation: float = 1.0) -> list:
    """Gera previsões EV-optimal para mata-mata."""
    predictions = []
    for m in knockout_results:
        h, a = m["home"], m["away"]
        try:
            if goal_inflation != 1.0:
                sm, _ = inflated_score_matrix(model, h, a, goal_inflation)
            else:
                pred = model.predict_match(h, a, host_adv=0.0)
                sm = pred["score_matrix"]
            ev_score, ev_pts = ev_optimal_score(sm, knockout=True)
            predictions.append({"home": h, "away": a, "bet": ev_score, "ev_pts": ev_pts})
        except KeyError:
            predictions.append({"home": h, "away": a, "bet": (1, 0), "ev_pts": 0})
    return predictions


# =============================================================================
# PONTUAÇÃO
# =============================================================================

def score_bets(bets: list, results: list, knockout: bool = False) -> Tuple[int, list]:
    """Pontua apostas contra resultados reais."""
    total = 0
    details = []
    for bet_info, result in zip(bets, results):
        bet = bet_info if isinstance(bet_info, tuple) else bet_info["bet"]
        actual = (result["hg"], result["ag"])
        pts = bolao_points(bet, actual, knockout=knockout)
        total += pts
        details.append({
            "home": result["home"], "away": result["away"],
            "bet": f"{bet[0]}x{bet[1]}", "actual": f"{actual[0]}x{actual[1]}",
            "pts": pts,
        })
    return total, details


def align_predictions_to_results(predictions: dict, results: list) -> list:
    """Alinha previsões com resultados na mesma ordem."""
    bets = []
    for result in results:
        h, a = result["home"], result["away"]
        key1 = f"{h} vs {a}"
        key2 = f"{a} vs {h}"
        if key1 in predictions:
            bets.append(predictions[key1]["bet"])
        elif key2 in predictions:
            pred_bet = predictions[key2]["bet"]
            bets.append((pred_bet[1], pred_bet[0]))
        else:
            bets.append((1, 1))
    return bets


def baseline_favorite(home: str, away: str, elo: dict, score: tuple) -> tuple:
    """Aposta no favorito ELO com placar dado."""
    if elo.get(home, 1500) >= elo.get(away, 1500):
        return score
    return (score[1], score[0])


# =============================================================================
# MAIN
# =============================================================================

def run_backtest(cal: Optional[Calibration] = None, verbose: bool = True, goal_inflation: float = 1.0) -> dict:
    """
    Roda backtest completo e retorna pontuações.
    Se cal=None, usa defaults com dados de 2022.
    goal_inflation: fator multiplicativo nos lambdas (1.0 = sem mudança).
    """
    if cal is None:
        cal = make_calibration_2022()

    elo_2022 = load_elo_2022()

    # 1. Resultados reais
    group_results, knockout_results = load_wc2022_results()
    if verbose:
        print(f"Jogos fase de grupos: {len(group_results)}")
        print(f"Jogos mata-mata: {len(knockout_results)}")

    # 2. Treinar modelo
    model = train_model(cal)

    # 3. Previsões
    predictions = generate_group_predictions(model, goal_inflation=goal_inflation)
    ko_predictions = generate_knockout_predictions(model, knockout_results, goal_inflation=goal_inflation)

    # 4. Pontuar modelo
    model_bets = align_predictions_to_results(predictions, group_results)
    model_pts_groups, model_details = score_bets(model_bets, group_results, knockout=False)
    model_pts_ko, ko_details = score_bets(ko_predictions, knockout_results, knockout=True)

    # 5. Baselines
    b1_bets = [baseline_favorite(r["home"], r["away"], elo_2022, (1, 0)) for r in group_results]
    b2_bets = [baseline_favorite(r["home"], r["away"], elo_2022, (2, 1)) for r in group_results]
    b3_bets = [(1, 1) for _ in group_results]

    b1_groups, _ = score_bets(b1_bets, group_results, knockout=False)
    b2_groups, _ = score_bets(b2_bets, group_results, knockout=False)
    b3_groups, _ = score_bets(b3_bets, group_results, knockout=False)

    b1_ko_bets = [{"bet": baseline_favorite(r["home"], r["away"], elo_2022, (1, 0))} for r in knockout_results]
    b2_ko_bets = [{"bet": baseline_favorite(r["home"], r["away"], elo_2022, (2, 1))} for r in knockout_results]
    b3_ko_bets = [{"bet": (1, 1)} for _ in knockout_results]

    b1_ko, _ = score_bets(b1_ko_bets, knockout_results, knockout=True)
    b2_ko, _ = score_bets(b2_ko_bets, knockout_results, knockout=True)
    b3_ko, _ = score_bets(b3_ko_bets, knockout_results, knockout=True)

    result = {
        "model_groups": model_pts_groups,
        "model_ko": model_pts_ko,
        "model_total": model_pts_groups + model_pts_ko,
        "b1_total": b1_groups + b1_ko,
        "b2_total": b2_groups + b2_ko,
        "b3_total": b3_groups + b3_ko,
        "details_groups": model_details,
        "details_ko": ko_details,
        "config": {
            "w_dc": cal.w_dc, "w_elo": cal.w_elo, "w_tm": cal.w_tm,
            "xi": cal.xi, "tm_scale": cal.tm_scale,
            "ad_split": cal.ad_split,
            "date_cutoff": cal.date_cutoff,
            "dc_qf_enabled": cal.dc_quality_filter.get("enabled", True),
            "goal_inflation": goal_inflation,
        },
    }

    if verbose:
        print("\n" + "=" * 70)
        print("  BACKTEST LIMPO — Copa do Mundo 2022 (dados de época)")
        print("=" * 70)
        print(f"\n{'Estratégia':<35} {'Grupos':>8} {'Mata-mata':>10} {'TOTAL':>8}")
        print("-" * 65)
        print(f"{'Modelo (EV-optimal)':<35} {model_pts_groups:>8} {model_pts_ko:>10} {model_pts_groups + model_pts_ko:>8}")
        print(f"{'Baseline-1 (Favorito 1x0)':<35} {b1_groups:>8} {b1_ko:>10} {b1_groups + b1_ko:>8}")
        print(f"{'Baseline-2 (Favorito 2x1)':<35} {b2_groups:>8} {b2_ko:>10} {b2_groups + b2_ko:>8}")
        print(f"{'Baseline-3 (Sempre 1x1)':<35} {b3_groups:>8} {b3_ko:>10} {b3_groups + b3_ko:>8}")

        print("\n--- Detalhamento por jogo (fase de grupos) ---\n")
        print(f"{'Jogo':<35} {'Aposta':>7} {'Real':>7} {'Pts':>5}")
        print("-" * 60)
        for d in model_details:
            game = f"{d['home']} vs {d['away']}"
            print(f"{game:<35} {d['bet']:>7} {d['actual']:>7} {d['pts']:>5}")

        diff_b1 = result["model_total"] - result["b1_total"]
        diff_b2 = result["model_total"] - result["b2_total"]
        print(f"\nModelo vs Baseline-1: {diff_b1:+d} pts")
        print(f"Modelo vs Baseline-2: {diff_b2:+d} pts")
        print(f"\nDados: ELOs nov/2022, TM nov/2022 (sem data leakage)")

    return result


if __name__ == "__main__":
    run_backtest()

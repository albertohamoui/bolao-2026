"""
Bolao 2026 — Frontend Streamlit
Sprint 3a: Setup + Tela de Calibracao
"""

import glob
import json
import os
import sys
import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import streamlit as st

# Garante que o diretorio do projeto esta no path
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from bolao2026 import (
    CONFEDERATIONS,
    DEFAULT_ELO_RATINGS,
    DEFAULT_TRANSFERMARKT_VALUES,
    GROUPS,
    WORLD_CUP_TEAM_LIST,
    Calibration,
    load_config,
    run_full_pipeline,
    save_config,
)

# Caminho absoluto do config.json
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")

# Lista de todos os times presentes nos grupos (48)
ALL_TEAMS = sorted({t for g in GROUPS.values() for t in g})

# =============================================================================
# Setup da pagina
# =============================================================================

st.set_page_config(
    page_title="Bolao 2026",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =============================================================================
# Session state — inicializa calibracao a partir do config.json
# =============================================================================

if "calibration" not in st.session_state:
    st.session_state.calibration = load_config(CONFIG_PATH).to_dict()

# Aplicar config pendente do backtest (antes dos widgets serem criados)
if "_pending_apply" in st.session_state:
    _pa = st.session_state.pop("_pending_apply")
    _cal = st.session_state.calibration
    _cal["w_dc"] = _pa["w_dc"]
    _cal["w_elo"] = _pa["w_elo"]
    _cal["w_tm"] = _pa["w_tm"]
    _cal["xi"] = _pa["xi"]
    _cal["tm_scale"] = _pa["tm_scale"]
    _cal["dc_quality_filter"]["enabled"] = _pa["dc_qf_enabled"]
    # Sincronizar widget keys para que os sliders reflitam os novos valores
    st.session_state["sl_w_dc"] = float(_pa["w_dc"])
    st.session_state["sl_w_elo"] = float(_pa["w_elo"])
    st.session_state["sl_w_tm"] = float(_pa["w_tm"])
    st.session_state["sl_xi"] = float(_pa["xi"])
    st.session_state["rd_tm_scale"] = _pa["tm_scale"]
    dcqf = _cal.get("dc_quality_filter", {})
    st.session_state["cb_dcqf_enabled"] = bool(_pa["dc_qf_enabled"])

# Contadores de versao para forcar re-render de data_editors apos reset
for _vkey in ("elo_editor_version", "tm_editor_version", "expert_editor_version"):
    if _vkey not in st.session_state:
        st.session_state[_vkey] = 0


def _cal_dict() -> dict:
    """Atalho pro dict de calibracao no session_state."""
    return st.session_state.calibration


def _sync_widget_keys_from_cal():
    """Atualiza as keys dos widgets para refletir o estado atual de calibration.

    Necessario antes de st.rerun() quando um botao muta session_state.calibration,
    porque widgets com key leem de st.session_state[key] em vez do parametro value.
    """
    cal = _cal_dict()
    st.session_state["sl_w_dc"] = float(cal["w_dc"])
    st.session_state["sl_w_elo"] = float(cal["w_elo"])
    st.session_state["sl_w_tm"] = float(cal["w_tm"])
    st.session_state["sl_xi"] = float(cal["xi"])
    st.session_state["sl_host_adv"] = float(cal["wc_host_adv"])
    st.session_state["ni_nsims"] = int(cal["n_sims"])
    cutoff = cal.get("date_cutoff", "2022-01-01")
    st.session_state["di_cutoff"] = (
        date.fromisoformat(cutoff) if isinstance(cutoff, str) else cutoff
    )
    st.session_state["rd_tm_scale"] = cal.get("tm_scale", "sqrt")
    ad = cal.get("ad_split", [0.6, -0.4])
    st.session_state["sl_ad_atk"] = float(ad[0])
    st.session_state["sl_ad_def"] = float(ad[1])

    # Features opcionais
    dcqf = cal.get("dc_quality_filter", {})
    st.session_state["cb_dcqf_enabled"] = bool(dcqf.get("enabled", True))

    tf = cal.get("tournament_factor", {})
    st.session_state["cb_tf_enabled"] = bool(tf.get("enabled", False))
    st.session_state["sl_tf_weight"] = float(tf.get("weight", 0.15))
    st.session_state["sl_tf_ko_weight"] = float(tf.get("knockout_weight", 2.0))

    sq = cal.get("squad_data", {})
    st.session_state["cb_sq_enabled"] = bool(sq.get("enabled", False))
    st.session_state["sl_sq_weight"] = float(sq.get("weight", 0.5))
    st.session_state["cb_sq_top11"] = bool(sq.get("use_top_11", False))

    ts = cal.get("top_scorer_model", {})
    st.session_state["cb_ts_enabled"] = bool(ts.get("enabled", False))
    pp = ts.get("position_probabilities", {"ATK": 0.75, "MID": 0.15, "DEF": 0.10})
    st.session_state["sl_ts_atk"] = float(pp.get("ATK", 0.75))
    st.session_state["sl_ts_mid"] = float(pp.get("MID", 0.15))
    st.session_state["sl_ts_def"] = float(pp.get("DEF", 0.10))
    st.session_state["sl_ts_k"] = int(ts.get("regularization_k", 5))
    st.session_state["sl_ts_sigma"] = float(ts.get("simulation_noise_sigma", 0.2))


# =============================================================================
# Tela de Calibracao
# =============================================================================

def render_calibration_page():
    st.header("Calibracao do Modelo")

    tab_presets, tab_params, tab_features, tab_elo, tab_tm, tab_expert, tab_review = st.tabs([
        "Presets",
        "Pesos & Hiperparametros",
        "Features Opcionais",
        "Elo Ratings",
        "Transfermarkt",
        "Expert Adjustments",
        "Revisao & Salvar",
    ])

    with tab_presets:
        _render_presets_tab()
    with tab_params:
        _render_params_tab()
    with tab_features:
        _render_features_tab()
    with tab_elo:
        _render_elo_tab()
    with tab_tm:
        _render_tm_tab()
    with tab_expert:
        _render_expert_tab()
    with tab_review:
        _render_review_tab()


# ---------------------------------------------------------------------------
# Aba 1: Pesos & Hiperparametros
# ---------------------------------------------------------------------------

def _render_params_tab():
    cal = _cal_dict()

    st.subheader("Pesos do Blend Bayesiano")

    col1, col2, col3 = st.columns(3)
    with col1:
        w_dc = st.slider("Dixon-Coles (w_dc)", 0.0, 1.0, float(cal["w_dc"]),
                          step=0.05, key="sl_w_dc")
    with col2:
        w_elo = st.slider("Elo (w_elo)", 0.0, 1.0, float(cal["w_elo"]),
                           step=0.05, key="sl_w_elo")
    with col3:
        w_tm = st.slider("Transfermarkt (w_tm)", 0.0, 1.0, float(cal["w_tm"]),
                          step=0.05, key="sl_w_tm")

    cal["w_dc"] = w_dc
    cal["w_elo"] = w_elo
    cal["w_tm"] = w_tm

    soma = w_dc + w_elo + w_tm
    if abs(soma - 1.0) < 1e-6:
        st.success(f"Soma dos pesos: {soma:.3f}")
    else:
        st.error(f"Pesos devem somar 1.0 — soma atual: {soma:.3f}")

    if st.button("Normalizar pesos", key="btn_normalize"):
        if soma > 0:
            cal["w_dc"] = round(w_dc / soma, 4)
            cal["w_elo"] = round(w_elo / soma, 4)
            cal["w_tm"] = round(1.0 - cal["w_dc"] - cal["w_elo"], 4)
            _sync_widget_keys_from_cal()
            st.rerun()

    st.divider()
    st.subheader("Hiperparametros")

    col_a, col_b = st.columns(2)
    with col_a:
        cal["xi"] = st.slider(
            "Time-decay (xi)", 0.0001, 0.01, float(cal["xi"]),
            step=0.0001, format="%.4f", key="sl_xi",
        )
        cal["wc_host_adv"] = st.slider(
            "Vantagem de mando - Copa (wc_host_adv)", 0.0, 0.30,
            float(cal["wc_host_adv"]), step=0.01, format="%.2f",
            key="sl_host_adv",
        )
        cal["n_sims"] = st.number_input(
            "Numero de simulacoes (n_sims)", min_value=1000, max_value=200000,
            value=int(cal["n_sims"]), step=1000, key="ni_nsims",
        )

    with col_b:
        # date_cutoff
        current_cutoff = cal.get("date_cutoff", "2022-01-01")
        if isinstance(current_cutoff, str):
            cutoff_date = date.fromisoformat(current_cutoff)
        else:
            cutoff_date = current_cutoff
        new_cutoff = st.date_input(
            "Data de corte (date_cutoff)", value=cutoff_date, key="di_cutoff",
        )
        cal["date_cutoff"] = new_cutoff.isoformat()

        # tm_scale
        tm_options = ["sqrt", "log", "linear"]
        current_idx = tm_options.index(cal.get("tm_scale", "sqrt"))
        cal["tm_scale"] = st.radio(
            "Escala TM (tm_scale)", tm_options,
            index=current_idx, horizontal=True, key="rd_tm_scale",
        )

    st.divider()
    st.subheader("Split Ataque / Defesa (ad_split)")
    st.caption(
        "Define como a 'forca' de cada time e distribuida entre capacidade de atacar "
        "(attack_ratio, positivo) e defender (defense_ratio, negativo — valor negativo "
        "significa que times fortes sofrem menos gols). Os dois valores sao independentes "
        "e NAO precisam somar 1.0. Valores tipicos: 0.6 e -0.4."
    )

    ad = cal.get("ad_split", [0.6, -0.4])
    col_ad1, col_ad2 = st.columns(2)
    with col_ad1:
        ad_attack = st.slider(
            "Attack ratio", 0.1, 1.0, float(ad[0]),
            step=0.05, key="sl_ad_atk",
        )
    with col_ad2:
        ad_defense = st.slider(
            "Defense ratio", -1.0, -0.1, float(ad[1]),
            step=0.05, key="sl_ad_def",
        )
    cal["ad_split"] = [ad_attack, ad_defense]


# ---------------------------------------------------------------------------
# Aba: Presets
# ---------------------------------------------------------------------------

def _render_presets_tab():
    cal = _cal_dict()

    st.subheader("Presets de Configuracao")
    st.caption(
        "Presets aplicam combinacoes de features de uma vez. Uteis para comparar "
        "cenarios diferentes (ex: modelo antes vs. depois das melhorias da Sprint 3.5). "
        "Apos aplicar um preset, va na aba 'Revisao & Salvar' para salvar em config.json."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Modo Legacy**")
        st.markdown(
            "Todas as features novas desligadas. Modelo equivalente ao "
            "pre-Sprint 3.5 (apenas com Elos atualizados)."
        )
        if st.button("Aplicar Modo Legacy", key="btn_preset_legacy"):
            cal.setdefault("dc_quality_filter", {})["enabled"] = False
            cal.setdefault("tournament_factor", {})["enabled"] = False
            cal.setdefault("squad_data", {})["enabled"] = False
            cal.setdefault("top_scorer_model", {})["enabled"] = False
            _sync_widget_keys_from_cal()
            st.rerun()

    with col2:
        st.markdown("**Modo Producao Atual**")
        st.markdown(
            "Filtro de qualidade DC ativo (melhora calibracao). "
            "Tournament factor, escalacao e artilheiro desligados "
            "(dependem de dados ou backtest pendente)."
        )
        if st.button("Aplicar Modo Producao", key="btn_preset_prod"):
            cal.setdefault("dc_quality_filter", {})["enabled"] = True
            cal.setdefault("tournament_factor", {})["enabled"] = False
            cal.setdefault("squad_data", {})["enabled"] = False
            cal.setdefault("top_scorer_model", {})["enabled"] = False
            _sync_widget_keys_from_cal()
            st.rerun()

    # Status atual
    st.divider()
    st.subheader("Status atual das features")
    dcqf = cal.get("dc_quality_filter", {})
    tf = cal.get("tournament_factor", {})
    sq = cal.get("squad_data", {})
    ts = cal.get("top_scorer_model", {})

    status_data = {
        "Feature": [
            "Filtro de qualidade DC",
            "Tournament Factor",
            "Modelo de Escalacao",
            "Modelo de Artilheiro",
        ],
        "Status": [
            "ATIVO" if dcqf.get("enabled") else "Desligado",
            "ATIVO" if tf.get("enabled") else "Desligado",
            "ATIVO" if sq.get("enabled") else "Desligado",
            "ATIVO" if ts.get("enabled") else "Desligado",
        ],
        "Nota": [
            "Melhora calibracao DC em jogos desiguais",
            "Desativado — impacto empirico marginal (ver doc §3.7.8)",
            "Ativar apos convocacoes FIFA (~01/jun/2026)",
            "Ativar apos preencher player_stats no config.json",
        ],
    }
    st.table(pd.DataFrame(status_data))


# ---------------------------------------------------------------------------
# Aba: Features Opcionais
# ---------------------------------------------------------------------------

def _render_features_tab():
    cal = _cal_dict()

    st.subheader("Features Opcionais")
    st.caption(
        "Features implementadas mas desligadas por default ate dados ou backtest "
        "validarem ativacao. Cada toggle habilita/desabilita a feature inteira. "
        "Controles ficam visiveis mas inativos quando a feature esta desligada."
    )

    # --- Secao 1: Filtro de Qualidade DC ---
    st.markdown("---")
    st.markdown("#### Calibracao DC — Filtro de Qualidade")
    st.caption(
        "Reduz peso de jogos entre adversarios muito desiguais na calibracao "
        "Dixon-Coles. Evita que goleadas contra fracos inflem parametros. "
        "Ver documentacao §3.1.4."
    )

    dcqf = cal.setdefault("dc_quality_filter", {
        "enabled": True, "thresholds": [300, 200, 100],
        "weights": [0.2, 0.5, 0.8, 1.0],
    })

    dcqf_on = st.checkbox(
        "Ativar filtro de qualidade", value=bool(dcqf.get("enabled", True)),
        key="cb_dcqf_enabled",
    )
    dcqf["enabled"] = dcqf_on

    thresholds = dcqf.get("thresholds", [300, 200, 100])
    weights = dcqf.get("weights", [0.2, 0.5, 0.8, 1.0])

    col_t, col_w = st.columns(2)
    with col_t:
        st.markdown("**Thresholds de gap Elo**")
        t1 = st.number_input("Gap > X (severo)", value=int(thresholds[0]),
                             min_value=100, max_value=600, step=50,
                             disabled=not dcqf_on, key="ni_dcqf_t1")
        t2 = st.number_input("Gap > X (moderado)", value=int(thresholds[1]),
                             min_value=50, max_value=500, step=50,
                             disabled=not dcqf_on, key="ni_dcqf_t2")
        t3 = st.number_input("Gap > X (leve)", value=int(thresholds[2]),
                             min_value=25, max_value=300, step=25,
                             disabled=not dcqf_on, key="ni_dcqf_t3")
        dcqf["thresholds"] = [t1, t2, t3]

    with col_w:
        st.markdown("**Pesos por faixa**")
        w1 = st.slider(f"Peso gap > {t1}", 0.0, 1.0, float(weights[0]),
                       step=0.05, disabled=not dcqf_on, key="sl_dcqf_w1")
        w2 = st.slider(f"Peso gap > {t2}", 0.0, 1.0, float(weights[1]),
                       step=0.05, disabled=not dcqf_on, key="sl_dcqf_w2")
        w3 = st.slider(f"Peso gap > {t3}", 0.0, 1.0, float(weights[2]),
                       step=0.05, disabled=not dcqf_on, key="sl_dcqf_w3")
        st.caption("Peso gap <= menor threshold: 1.0 (sem desconto)")
        dcqf["weights"] = [w1, w2, w3, 1.0]

    # --- Secao 2: Tournament Factor ---
    st.markdown("---")
    st.markdown("#### Tournament Factor")
    st.caption(
        "Ajuste residual pos-blend baseado em saldo de gols em torneios curtos "
        "(Copas, Euros, Copa America). Desativado por decisao empirica — impacto "
        "marginal no output. Ver documentacao §3.7.8."
    )

    tf = cal.setdefault("tournament_factor", {
        "enabled": False, "weight": 0.15, "knockout_weight": 2.0,
        "min_games_groups": 3, "min_games_knockout": 2,
        "start_year": 2014, "tournaments": [
            "FIFA World Cup", "UEFA Euro", "Copa América", "Copa America"
        ],
    })

    tf_on = st.checkbox(
        "Ativar tournament factor", value=bool(tf.get("enabled", False)),
        key="cb_tf_enabled",
    )
    tf["enabled"] = tf_on

    col_tf1, col_tf2 = st.columns(2)
    with col_tf1:
        tf["weight"] = st.slider(
            "Peso do TF (weight)", 0.0, 0.50, float(tf.get("weight", 0.15)),
            step=0.01, format="%.2f", disabled=not tf_on, key="sl_tf_weight",
        )
    with col_tf2:
        tf["knockout_weight"] = st.slider(
            "Peso mata-mata vs grupos (knockout_weight)", 1.0, 5.0,
            float(tf.get("knockout_weight", 2.0)),
            step=0.5, disabled=not tf_on, key="sl_tf_ko_weight",
        )

    # --- Secao 3: Modelo de Escalacao ---
    st.markdown("---")
    st.markdown("#### Modelo de Escalacao")
    st.caption(
        "Ajusta alpha/beta pelo ratio qualidade convocada vs plantel ideal. "
        "Ativar apos convocacoes FIFA (~01/jun/2026). Convocacoes sao preenchidas "
        "diretamente no config.json (campo convocated_squads). Ver documentacao §3.8."
    )

    sq = cal.setdefault("squad_data", {
        "enabled": False, "weight": 0.5, "use_top_11": False,
        "ideal_squad_values": {}, "convocated_squads": {},
    })

    sq_on = st.checkbox(
        "Ativar modelo de escalacao", value=bool(sq.get("enabled", False)),
        key="cb_sq_enabled",
    )
    sq["enabled"] = sq_on

    col_sq1, col_sq2 = st.columns(2)
    with col_sq1:
        sq["weight"] = st.slider(
            "Smoothing (weight)", 0.0, 1.0, float(sq.get("weight", 0.5)),
            step=0.05, disabled=not sq_on, key="sl_sq_weight",
        )
    with col_sq2:
        sq["use_top_11"] = st.checkbox(
            "Usar apenas top 11 jogadores", value=bool(sq.get("use_top_11", False)),
            disabled=not sq_on, key="cb_sq_top11",
        )

    n_squads = len(sq.get("convocated_squads", {}))
    if sq_on and n_squads == 0:
        st.warning("Nenhuma convocacao preenchida em config.json. "
                   "Modelo nao tera efeito ate convocated_squads ser populado.")
    elif sq_on:
        st.info(f"{n_squads} convocacao(oes) carregada(s).")

    # --- Secao 4: Modelo de Artilheiro ---
    st.markdown("---")
    st.markdown("#### Modelo de Artilheiro")
    st.caption(
        "Sorteia autor de cada gol no Monte Carlo. Requer player_stats preenchido "
        "no config.json. Com dados de 2-3 selecoes, adiciona ~5s ao tempo de execucao. "
        "Ver documentacao §3.9."
    )

    ts = cal.setdefault("top_scorer_model", {
        "enabled": False,
        "position_probabilities": {"ATK": 0.75, "MID": 0.15, "DEF": 0.10},
        "regularization_k": 5, "simulation_noise_sigma": 0.2,
        "player_stats": {},
    })

    ts_on = st.checkbox(
        "Ativar modelo de artilheiro", value=bool(ts.get("enabled", False)),
        key="cb_ts_enabled",
    )
    ts["enabled"] = ts_on

    st.markdown("**Probabilidade por posicao** (devem somar 1.0)")
    pp = ts.setdefault("position_probabilities",
                       {"ATK": 0.75, "MID": 0.15, "DEF": 0.10})
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        p_atk = st.slider("ATK", 0.0, 1.0, float(pp.get("ATK", 0.75)),
                          step=0.05, disabled=not ts_on, key="sl_ts_atk")
    with col_p2:
        p_mid = st.slider("MID", 0.0, 1.0, float(pp.get("MID", 0.15)),
                          step=0.05, disabled=not ts_on, key="sl_ts_mid")
    with col_p3:
        p_def = st.slider("DEF", 0.0, 1.0, float(pp.get("DEF", 0.10)),
                          step=0.05, disabled=not ts_on, key="sl_ts_def")

    soma_pos = p_atk + p_mid + p_def
    if abs(soma_pos - 1.0) < 0.01:
        pp["ATK"], pp["MID"], pp["DEF"] = p_atk, p_mid, p_def
    else:
        st.warning(f"Probabilidades de posicao devem somar 1.0 (atual: {soma_pos:.2f})")
        # Normaliza automaticamente pra evitar erro
        if soma_pos > 0:
            pp["ATK"] = round(p_atk / soma_pos, 3)
            pp["MID"] = round(p_mid / soma_pos, 3)
            pp["DEF"] = round(1.0 - pp["ATK"] - pp["MID"], 3)

    col_k, col_s = st.columns(2)
    with col_k:
        ts["regularization_k"] = st.slider(
            "Regularizacao bayesiana (k)", 0, 20,
            int(ts.get("regularization_k", 5)),
            disabled=not ts_on, key="sl_ts_k",
        )
    with col_s:
        ts["simulation_noise_sigma"] = st.slider(
            "Ruido por simulacao (sigma)", 0.0, 0.50,
            float(ts.get("simulation_noise_sigma", 0.2)),
            step=0.05, format="%.2f",
            disabled=not ts_on, key="sl_ts_sigma",
        )

    n_players = len(ts.get("player_stats", {}))
    if ts_on and n_players == 0:
        st.warning("Nenhum player_stats preenchido em config.json. "
                   "Modelo nao tera efeito ate player_stats ser populado.")
    elif ts_on:
        st.info(f"{n_players} selecao(oes) com player_stats carregado(s).")


# ---------------------------------------------------------------------------
# Aba: Elo Ratings
# ---------------------------------------------------------------------------

def _render_elo_tab():
    cal = _cal_dict()
    elo = cal.get("elo_ratings", {})

    st.caption(
        "Elo ratings atuais (abril 2026, fonte: eloratings.net). Voce pode editar "
        "pra testar hipoteses ou atualizar quando novos dados sairem. Mudancas aqui "
        "afetam o prior Bayesiano — nao substituem os resultados historicos do Dixon-Coles."
    )

    rows = []
    for team in ALL_TEAMS:
        rows.append({
            "Time": team,
            "Elo": int(elo.get(team, 1500)),
            "Confederacao": CONFEDERATIONS.get(team, "?"),
        })

    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        column_config={
            "Time": st.column_config.TextColumn(disabled=True),
            "Elo": st.column_config.NumberColumn(min_value=1000, max_value=2500, step=1),
            "Confederacao": st.column_config.TextColumn(disabled=True),
        },
        use_container_width=True,
        height=600,
        hide_index=True,
        key=f"de_elo_{st.session_state.elo_editor_version}",
    )

    for _, row in edited.iterrows():
        cal["elo_ratings"][row["Time"]] = int(row["Elo"])

    if st.button("Resetar Elo pros defaults", key="btn_reset_elo"):
        cal["elo_ratings"] = dict(DEFAULT_ELO_RATINGS)
        st.session_state.elo_editor_version += 1
        st.rerun()


# ---------------------------------------------------------------------------
# Aba 3: Transfermarkt Values
# ---------------------------------------------------------------------------

def _render_tm_tab():
    cal = _cal_dict()
    tm = cal.get("transfermarkt_values", {})

    st.caption(
        "Valor de elenco por time (Transfermarkt, marco 2026, em milhoes de EUR). "
        "Atualize quando tiver dados novos. Este canal captura qualidade individual "
        "do plantel, independente de resultados em campo."
    )

    rows = []
    for team in ALL_TEAMS:
        rows.append({
            "Time": team,
            "Valor (M EUR)": int(tm.get(team, 30)),
            "Confederacao": CONFEDERATIONS.get(team, "?"),
        })

    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        column_config={
            "Time": st.column_config.TextColumn(disabled=True),
            "Valor (M EUR)": st.column_config.NumberColumn(min_value=1, max_value=5000, step=1),
            "Confederacao": st.column_config.TextColumn(disabled=True),
        },
        use_container_width=True,
        height=600,
        hide_index=True,
        key=f"de_tm_{st.session_state.tm_editor_version}",
    )

    for _, row in edited.iterrows():
        cal["transfermarkt_values"][row["Time"]] = int(row["Valor (M EUR)"])

    if st.button("Resetar TM pros defaults", key="btn_reset_tm"):
        cal["transfermarkt_values"] = dict(DEFAULT_TRANSFERMARKT_VALUES)
        st.session_state.tm_editor_version += 1
        st.rerun()


# ---------------------------------------------------------------------------
# Aba 4: Expert Adjustments
# ---------------------------------------------------------------------------

def _render_expert_tab():
    cal = _cal_dict()
    expert = cal.get("expert_adjustments", {}) or {}

    st.info(
        "Expert adjustments sao multiplicadores manuais no ataque de selecoes "
        "especificas. Use para capturar fatores que os dados nao veem: lesoes "
        "de craques, trocas de tecnico, subperformance historica em torneios. "
        "Valores < 1.0 reduzem o ataque, > 1.0 aumentam. Default = 1.0 (sem ajuste)."
    )

    rows = []
    for team, adj in expert.items():
        rows.append({
            "Time": team,
            "attack_mult": float(adj.get("attack_mult", 1.0)),
        })

    df = pd.DataFrame(rows, columns=["Time", "attack_mult"])

    edited = st.data_editor(
        df,
        column_config={
            "Time": st.column_config.SelectboxColumn(
                options=ALL_TEAMS, required=True,
            ),
            "attack_mult": st.column_config.NumberColumn(
                min_value=0.5, max_value=1.5, step=0.01, format="%.2f",
            ),
        },
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"de_expert_{st.session_state.expert_editor_version}",
    )

    # Detecta duplicatas
    if not edited.empty:
        dupes = edited["Time"].dropna()
        dupes = dupes[dupes.duplicated(keep=False)]
        if not dupes.empty:
            st.warning(f"Times duplicados detectados: {', '.join(dupes.unique())}. "
                       "A ultima entrada prevalece.")

    # Converte de volta pra dict
    new_expert = {}
    for _, row in edited.iterrows():
        team = row.get("Time")
        mult = row.get("attack_mult")
        if pd.notna(team) and team and pd.notna(mult):
            new_expert[team] = {"attack_mult": float(mult)}
    cal["expert_adjustments"] = new_expert

    if st.button("Limpar todos ajustes", key="btn_clear_expert"):
        cal["expert_adjustments"] = {}
        st.session_state.expert_editor_version += 1
        st.rerun()


# ---------------------------------------------------------------------------
# Aba 5: Revisao & Salvar
# ---------------------------------------------------------------------------

def _render_review_tab():
    cal = _cal_dict()

    # Le estado atual do disco
    disk_cal = load_config(CONFIG_PATH).to_dict()

    # Monta calibracao editada para validacao
    edited_cal = Calibration.from_dict(dict(cal))
    errors = edited_cal.validate()

    # --- Preview lado a lado ---
    st.subheader("Preview das alteracoes")

    col_disk, col_edit = st.columns(2)

    scalar_fields = [
        ("w_dc", "W Dixon-Coles"),
        ("w_elo", "W Elo"),
        ("w_tm", "W Transfermarkt"),
        ("xi", "Time-decay (xi)"),
        ("wc_host_adv", "Host advantage"),
        ("n_sims", "Simulacoes"),
        ("date_cutoff", "Data de corte"),
        ("tm_scale", "Escala TM"),
        ("ad_split", "Split atk/def"),
    ]

    # Extrai flags de features opcionais pra comparacao
    def _feature_status(d, key, enabled_key="enabled"):
        feat = d.get(key, {})
        if not isinstance(feat, dict):
            return "N/A"
        parts = []
        parts.append("ON" if feat.get(enabled_key) else "OFF")
        for k, v in feat.items():
            if k in (enabled_key, "thresholds", "weights", "tournaments",
                     "player_stats", "convocated_squads", "ideal_squad_values",
                     "position_probabilities"):
                continue
            parts.append(f"{k}={v}")
        return ", ".join(parts)

    feature_fields = [
        ("dc_quality_filter", "Filtro qualidade DC"),
        ("tournament_factor", "Tournament factor"),
        ("squad_data", "Modelo escalacao"),
        ("top_scorer_model", "Modelo artilheiro"),
    ]

    with col_disk:
        st.markdown("**config.json em disco**")
        for key, label in scalar_fields:
            val = disk_cal.get(key)
            st.text(f"{label}: {val}")
        st.markdown("**Features opcionais**")
        for key, label in feature_fields:
            st.text(f"{label}: {_feature_status(disk_cal, key)}")

    with col_edit:
        st.markdown("**Estado editado**")
        for key, label in scalar_fields:
            val = cal.get(key)
            disk_val = disk_cal.get(key)
            changed = " *" if val != disk_val else ""
            st.text(f"{label}: {val}{changed}")
        st.markdown("**Features opcionais**")
        for key, label in feature_fields:
            cur = _feature_status(cal, key)
            disk = _feature_status(disk_cal, key)
            changed = " *" if cur != disk else ""
            st.text(f"{label}: {cur}{changed}")

    # Contagem de alteracoes em dicts grandes
    elo_changes = sum(
        1 for t in ALL_TEAMS
        if cal.get("elo_ratings", {}).get(t) != disk_cal.get("elo_ratings", {}).get(t)
    )
    tm_changes = sum(
        1 for t in ALL_TEAMS
        if cal.get("transfermarkt_values", {}).get(t) != disk_cal.get("transfermarkt_values", {}).get(t)
    )
    expert_edit = cal.get("expert_adjustments", {}) or {}
    expert_disk = disk_cal.get("expert_adjustments", {}) or {}
    expert_changed = expert_edit != expert_disk

    summary_parts = []
    if elo_changes:
        summary_parts.append(f"{elo_changes} alteracao(oes) em Elo")
    if tm_changes:
        summary_parts.append(f"{tm_changes} alteracao(oes) em TM")
    if expert_changed:
        summary_parts.append("Expert adjustments modificados")
    if not summary_parts:
        summary_parts.append("Nenhuma alteracao em Elo/TM/Expert")

    st.caption(" | ".join(summary_parts))

    # --- Validacao ---
    st.divider()
    st.subheader("Validacao")

    if errors:
        for err in errors:
            st.error(err)
    else:
        st.success("Calibracao valida")

    # --- Botoes ---
    st.divider()

    col_save, col_discard, col_reset = st.columns(3)

    with col_save:
        save_disabled = len(errors) > 0
        if st.button("Salvar em config.json", type="primary",
                      disabled=save_disabled, key="btn_save"):
            save_config(edited_cal, CONFIG_PATH)
            pushed = _auto_git_push([CONFIG_PATH], "data: update config.json")
            st.success("Salvo e sincronizado!" if pushed else "Salvo localmente!")
            st.balloons()

    with col_discard:
        if st.button("Descartar alteracoes", key="btn_discard"):
            st.session_state.calibration = load_config(CONFIG_PATH).to_dict()
            _sync_widget_keys_from_cal()
            st.session_state.elo_editor_version += 1
            st.session_state.tm_editor_version += 1
            st.session_state.expert_editor_version += 1
            st.rerun()

    with col_reset:
        if st.button("Resetar tudo pros defaults", key="btn_reset_all"):
            st.session_state.calibration = Calibration().to_dict()
            _sync_widget_keys_from_cal()
            st.session_state.elo_editor_version += 1
            st.session_state.tm_editor_version += 1
            st.session_state.expert_editor_version += 1
            st.rerun()


# =============================================================================
# Diretorio de simulacoes salvas
# =============================================================================

RUNS_DIR = os.path.join(PROJECT_DIR, "runs")
os.makedirs(RUNS_DIR, exist_ok=True)


def _auto_git_push(filepaths: list, message: str):
    """Commita e pusha arquivos salvos automaticamente.

    Funciona localmente com credenciais git existentes.
    Em ambientes sem git (ex: Streamlit Cloud sem token), falha silenciosamente.
    """
    import subprocess
    try:
        for fp in filepaths:
            rel = os.path.relpath(fp, PROJECT_DIR)
            subprocess.run(["git", "add", rel], cwd=PROJECT_DIR,
                           capture_output=True, timeout=10)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=PROJECT_DIR, capture_output=True, timeout=10,
        )
        result = subprocess.run(
            ["git", "push"],
            cwd=PROJECT_DIR, capture_output=True, timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


# =============================================================================
# Tela: Rodar Simulacao
# =============================================================================

def render_run_page():
    st.header("Rodar Simulacao")

    cal_d = _cal_dict()
    cal = Calibration.from_dict(dict(cal_d))
    errors = cal.validate()

    if errors:
        st.error("Calibracao invalida — corrija na aba Calibracao antes de rodar:")
        for e in errors:
            st.error(f"  {e}")
        return

    col_run, col_info = st.columns([1, 3])
    with col_run:
        run_clicked = st.button("Rodar Pipeline", type="primary", key="btn_run")
    with col_info:
        st.caption(
            f"DC {cal.w_dc:.0%} + Elo {cal.w_elo:.0%} + TM {cal.w_tm:.0%} | "
            f"{cal.n_sims:,} sims | cutoff {cal.date_cutoff}"
        )

    if run_clicked:
        t_start = time.time()
        status = st.empty()
        progress_bar = st.progress(0, text="Carregando dados e otimizando Dixon-Coles...")

        def mc_progress(current, total):
            pct = current / total
            progress_bar.progress(pct, text=f"Monte Carlo: {current:,}/{total:,} simulacoes...")

        try:
            status.info("Otimizacao Dixon-Coles em andamento (multi-start 8x). Pode levar alguns minutos...")
            output = run_full_pipeline(cal, progress_callback=mc_progress)
            elapsed = time.time() - t_start
            progress_bar.progress(1.0, text=f"Concluido em {elapsed:.0f}s")
            status.success(f"Pipeline concluido em {elapsed:.0f}s")

            st.session_state.last_run = output
            st.session_state.last_run_time = elapsed
            st.session_state.last_run_timestamp = datetime.now().isoformat()

        except Exception as e:
            progress_bar.empty()
            status.empty()
            st.error(f"Erro no pipeline: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

    if "last_run" not in st.session_state:
        st.info("Clique 'Rodar Pipeline' para executar o modelo com a calibracao atual.")
        return

    output = st.session_state.last_run
    elapsed = st.session_state.get("last_run_time", 0)
    timestamp = st.session_state.get("last_run_timestamp", "")

    _display_results(output, elapsed, timestamp, show_save=True)


def _display_results(output, elapsed, timestamp, show_save=False):
    """Renderiza os resultados do pipeline em secoes organizadas."""
    model_params = output["model_params"]
    stats = output["simulation_stats"]

    st.divider()

    # Metricas resumo
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("rho", f"{model_params['rho']:.4f}")
    with col2:
        st.metric("Home Advantage", f"{model_params['home_adv']:.3f}")
    with col3:
        st.metric("Tempo Total", f"{elapsed:.0f}s" if elapsed else "N/A")
    with col4:
        ts_display = timestamp[:19].replace("T", " ") if timestamp else "N/A"
        st.metric("Executado em", ts_display)

    # Abas de resultados
    tab_fav, tab_groups, tab_bets, tab_params = st.tabs([
        "Favoritos ao Titulo",
        "Previsoes por Grupo",
        "Apostas EV-Optimal",
        "Parametros do Modelo",
    ])

    with tab_fav:
        _render_favorites(stats)

    with tab_groups:
        _render_group_predictions(output)

    with tab_bets:
        _render_bets(output)

    with tab_params:
        _render_model_params_table(output)

    # Salvar
    if show_save:
        st.divider()
        col_name, col_save = st.columns([3, 1])
        with col_name:
            run_name = st.text_input(
                "Nome da simulacao (opcional)",
                value="", key="ti_run_name",
            )
        with col_save:
            st.write("")  # spacer
            st.write("")
            if st.button("Salvar Simulacao", key="btn_save_run"):
                _save_run(output, run_name, timestamp)
                st.success("Simulacao salva!")
                st.rerun()


def _render_favorites(stats):
    """Top 20 favoritos ao titulo."""
    rows = []
    for team in WORLD_CUP_TEAM_LIST:
        s = stats.get(team, {})
        rows.append({
            "Selecao": team,
            "Titulo": s.get("champion", 0),
            "Final": s.get("final", 0),
            "Semi": s.get("sf", 0),
            "Quartas": s.get("qf", 0),
            "R16": s.get("r16", 0),
        })
    df = pd.DataFrame(rows).sort_values("Titulo", ascending=False).head(20)
    df.index = range(1, len(df) + 1)
    df.index.name = "Pos"

    # Formatar como percentual
    for col in ["Titulo", "Final", "Semi", "Quartas", "R16"]:
        df[col] = df[col].apply(lambda x: f"{x:.1f}%")

    st.dataframe(df, use_container_width=True, height=740)


def _render_group_predictions(output):
    """Previsoes por grupo: placares e classificacao."""
    predictions = output["predictions"]
    stats = output["simulation_stats"]

    view = st.radio(
        "Visualizacao", ["Placares", "Classificacao"],
        horizontal=True, key="rd_group_view",
    )

    if view == "Placares":
        by_group = {}
        for _, pred in predictions.items():
            by_group.setdefault(pred["group"], []).append(pred)

        for gname in sorted(by_group.keys()):
            with st.expander(f"Grupo {gname}", expanded=False):
                rows = []
                for p in by_group[gname]:
                    rows.append({
                        "Jogo": f"{p['home']} vs {p['away']}",
                        "Placar EV": p["score_ev"],
                        "Modal": p["score_modal"],
                        "Casa": f"{p['home_win']:.0f}%",
                        "Empate": f"{p['draw']:.0f}%",
                        "Fora": f"{p['away_win']:.0f}%",
                        "EV pts": p["ev_points"],
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        for gname in sorted(GROUPS.keys()):
            teams = GROUPS[gname]
            with st.expander(f"Grupo {gname}", expanded=False):
                rows = []
                for t in teams:
                    s = stats.get(t, {})
                    rows.append({
                        "Selecao": t,
                        "1o": f"{s.get('group_1st', 0):.1f}%",
                        "2o": f"{s.get('group_2nd', 0):.1f}%",
                        "3o (Q)": f"{s.get('group_3rd_qual', 0):.1f}%",
                        "Elim": f"{100 - s.get('group_1st', 0) - s.get('group_2nd', 0) - s.get('group_3rd_qual', 0):.1f}%",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_bets(output):
    """Apostas EV-optimal: grupos, campeao, terceiros."""

    # Classificacao dos grupos
    st.subheader("Classificacao dos Grupos")
    group_bets = output.get("group_bets", {})
    rows = []
    total_ev = 0.0
    for gname in sorted(group_bets.keys()):
        gb = group_bets[gname]
        ev = gb["ev_points"]
        total_ev += ev
        rows.append({
            "Grupo": gname,
            "1o": gb["bet_1st"],
            "2o": gb["bet_2nd"],
            "EV pts": f"{ev:.2f}",
            "P(ambos exatos)": f"{gb['p_both_exact']:.1%}",
        })
    df_groups = pd.DataFrame(rows)
    st.dataframe(df_groups, use_container_width=True, hide_index=True)
    st.caption(f"Total EV classificacao: **{total_ev:.2f} pts** (max 240)")

    st.divider()

    # Campeao
    st.subheader("Aposta de Campeao")
    champ = output.get("champion_bet", {})
    if champ and champ.get("bet"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Time", champ["bet"])
        with col2:
            st.metric("P(campeao)", f"{champ['p_champion']:.1%}")
        with col3:
            st.metric("EV", f"{champ['ev_points']:.2f} pts (max 25)")

    st.divider()

    # Terceiros colocados
    st.subheader("Terceiros Colocados (induzidos)")
    thirds = output.get("third_places", {})
    if thirds:
        per_team = thirds.get("per_team", [])
        if per_team:
            rows = []
            for entry in per_team:
                rows.append({
                    "Selecao": entry["team"],
                    "P(3o qual)": f"{entry['p_3rd_qual']:.1%}",
                    "EV pts": f"{entry['ev']:.2f}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"Total EV terceiros: **{thirds.get('ev_points', 0):.2f} pts** (max 40)")

    # Resumo geral EV
    st.divider()
    st.subheader("Resumo EV Total")
    ev_groups = total_ev
    ev_champ = champ.get("ev_points", 0) if champ else 0
    ev_thirds = thirds.get("ev_points", 0) if thirds else 0

    # EV dos placares
    predictions = output.get("predictions", {})
    ev_scores = sum(p.get("ev_points", 0) for p in predictions.values())

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Placares", f"{ev_scores:.1f} pts")
    with col2:
        st.metric("Classificacao", f"{ev_groups:.1f} pts")
    with col3:
        st.metric("Campeao", f"{ev_champ:.1f} pts")
    with col4:
        st.metric("Terceiros", f"{ev_thirds:.1f} pts")
    with col5:
        st.metric("TOTAL", f"{ev_scores + ev_groups + ev_champ + ev_thirds:.1f} pts")


def _render_model_params_table(output):
    """Tabela de parametros alpha/beta por selecao."""
    team_params = output.get("team_params", [])
    rows = []
    for p in team_params:
        rows.append({
            "Selecao": p["team"],
            "Ataque": f"{p['attack']:+.3f}",
            "Defesa": f"{p['defense']:+.3f}",
            "Forca": f"{p['strength']:.3f}",
            "Elo": p["elo"],
            "Confed": p["confederation"],
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=1200, hide_index=True)

    # Tournament factors se disponiveis
    tfs = output.get("tournament_factors")
    if tfs:
        st.divider()
        st.subheader("Tournament Factors")
        tf_rows = []
        for team, tf in sorted(tfs.items(), key=lambda x: x[1], reverse=True):
            if tf == 0.0:
                continue
            tf_rows.append({
                "Selecao": team,
                "TF": f"{tf:+.3f}",
                "Tipo": "over" if tf > 0 else "under",
            })
        if tf_rows:
            st.dataframe(pd.DataFrame(tf_rows), use_container_width=True, hide_index=True)


def _save_run(output, name, timestamp):
    """Salva simulacao em runs/ como JSON."""
    ts = timestamp or datetime.now().isoformat()
    slug = ts[:19].replace(":", "-").replace("T", "_")
    if name:
        slug = f"{slug}_{name.replace(' ', '_')}"
    filepath = os.path.join(RUNS_DIR, f"{slug}.json")

    # Preparar output serializavel (remover numpy arrays)
    clean = {
        "metadata": {
            "name": name or slug,
            "timestamp": ts,
            "calibration_summary": {
                "w_dc": output["calibration"]["w_dc"],
                "w_elo": output["calibration"]["w_elo"],
                "w_tm": output["calibration"]["w_tm"],
                "n_sims": output["calibration"]["n_sims"],
            },
        },
        "predictions": output["predictions"],
        "simulation_stats": output["simulation_stats"],
        "group_bets": {
            g: {k: v for k, v in b.items() if not isinstance(v, np.ndarray)}
            for g, b in output.get("group_bets", {}).items()
        },
        "champion_bet": output.get("champion_bet"),
        "third_places": output.get("third_places"),
        "model_params": output["model_params"],
        "team_params": output.get("team_params"),
        "elo_ratings": output.get("elo_ratings"),
        "groups": output.get("groups"),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False, default=str)

    if _auto_git_push([filepath], f"data: save run {slug}"):
        st.toast("Simulacao salva e sincronizada com GitHub")


# =============================================================================
# Tela: Backtest & Otimizacao
# =============================================================================

BACKTEST_SAVE_DIR = os.path.join(PROJECT_DIR, "backtests", "saved_results")
os.makedirs(BACKTEST_SAVE_DIR, exist_ok=True)


def _load_saved_optimize_results(cup: str) -> list:
    """Carrega resultados salvos do otimizador."""
    path = os.path.join(BACKTEST_SAVE_DIR, f"optimize_{cup}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_optimize_results(cup: str, results: list):
    """Salva resultados do otimizador em JSON e pusha pro GitHub."""
    path = os.path.join(BACKTEST_SAVE_DIR, f"optimize_{cup}.json")
    serializable = []
    for r in results:
        s = {k: v for k, v in r.items() if k not in ("details_groups", "details_ko")}
        serializable.append(s)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)

    _auto_git_push([path], f"data: save optimize results {cup}")


def _get_backtest_module(cup: str):
    """Importa o modulo de backtest correto."""
    import sys as _sys
    _backtest_dir = os.path.join(PROJECT_DIR, "backtests", f"wc{cup}")
    if _backtest_dir not in _sys.path:
        _sys.path.insert(0, _backtest_dir)

    if cup == "2022":
        from backtests.wc2022.run_backtest import make_calibration_2022 as make_cal, run_backtest as run_bt
    else:
        from backtests.wc2018.run_backtest import make_calibration_2018 as make_cal, run_backtest as run_bt
    return make_cal, run_bt


def render_backtest_page():
    st.header("Backtest & Otimizacao")

    st.markdown("""
    Testa o modelo contra Copas passadas usando dados de epoca (sem data leakage).
    Resultados do otimizador sao **salvos automaticamente** em disco.
    """)

    tab_single, tab_optimize = st.tabs(["Backtest Unico", "Otimizador (Grid Search)"])

    with tab_single:
        _render_backtest_single()

    with tab_optimize:
        _render_optimizer()


def _render_backtest_single():
    """Roda backtest com parametros configuraveis."""
    st.subheader("Backtest com configuracao manual")

    bt_cup = st.radio("Copa", ["2022", "2018"], key="bt_cup", horizontal=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        bt_w_dc = st.slider("Peso DC", 0.0, 1.0, 0.45, 0.05, key="bt_w_dc")
    with col2:
        bt_w_elo = st.slider("Peso ELO", 0.0, 1.0, 0.30, 0.05, key="bt_w_elo")
    with col3:
        bt_w_tm = st.slider("Peso TM", 0.0, 1.0, 0.25, 0.05, key="bt_w_tm")

    w_sum = bt_w_dc + bt_w_elo + bt_w_tm
    if abs(w_sum - 1.0) > 0.01:
        st.warning(f"Pesos devem somar 1.0 (atual: {w_sum:.2f})")
        return

    col4, col5, col6 = st.columns(3)
    with col4:
        bt_xi = st.select_slider("xi (time-decay)", [0.0003, 0.0005, 0.001, 0.002, 0.003, 0.005], value=0.001, key="bt_xi")
    with col5:
        bt_tm_scale = st.selectbox("Escala TM", ["sqrt", "log", "linear"], key="bt_tm_scale")
    with col6:
        bt_qf = st.checkbox("Quality Filter", value=True, key="bt_qf")

    cutoff_options = {
        "2022": ["2016-01-01", "2018-01-01", "2020-01-01"],
        "2018": ["2012-01-01", "2014-01-01", "2016-01-01"],
    }
    bt_cutoff = st.selectbox("Date Cutoff", cutoff_options[bt_cup], index=1, key="bt_cutoff")

    if st.button(f"Rodar Backtest {bt_cup}", type="primary", key="btn_backtest"):
        make_cal, run_bt = _get_backtest_module(bt_cup)

        cal = make_cal(
            w_dc=bt_w_dc, w_elo=bt_w_elo, w_tm=bt_w_tm,
            xi=bt_xi, tm_scale=bt_tm_scale,
            dc_quality_filter_enabled=bt_qf,
            date_cutoff=bt_cutoff,
        )

        with st.spinner(f"Treinando modelo com dados pre-Copa {bt_cup}..."):
            import builtins
            _orig_print = builtins.print
            builtins.print = lambda *a, **k: None
            try:
                result = run_bt(cal, verbose=False)
            finally:
                builtins.print = _orig_print

        _display_backtest_result(result)


def _render_optimizer():
    """Grid search sobre variaveis."""
    st.subheader("Otimizador de Calibracao")
    st.markdown("Testa multiplas combinacoes e encontra a melhor. Resultados sao salvos em disco.")

    opt_cup = st.radio("Copa", ["2022", "2018"], key="opt_cup", horizontal=True)

    grid_mode = st.radio("Modo", ["Rapido (~30 combos, ~30s)", "Completo (~660 combos, ~12min)"],
                         key="grid_mode", horizontal=True)

    col_run, col_load = st.columns(2)

    with col_run:
        run_clicked = st.button("Iniciar Otimizacao", type="primary", key="btn_optimize")

    with col_load:
        load_clicked = st.button("Carregar resultados salvos", key="btn_load_optimize")

    if load_clicked:
        saved = _load_saved_optimize_results(opt_cup)
        if saved:
            st.session_state[f"optimize_results_{opt_cup}"] = saved
            st.success(f"Carregados {len(saved)} resultados salvos da Copa {opt_cup}")
        else:
            st.warning(f"Nenhum resultado salvo encontrado para Copa {opt_cup}")

    if run_clicked:
        # Rodar otimizador como subprocess para evitar overhead do Streamlit
        import subprocess
        quick_flag = "--quick" if "Rapido" in grid_mode else ""
        script_path = os.path.join(PROJECT_DIR, "backtests", f"wc{opt_cup}", "optimize.py")

        n_combos = 30 if "Rapido" in grid_mode else 660
        status_text = st.empty()
        progress = st.progress(0)
        timer_text = st.empty()

        # Rodar como Popen para monitorar progresso em tempo real
        proc = subprocess.Popen(
            [sys.executable, "-u", script_path] + ([quick_flag] if quick_flag else []),
            cwd=PROJECT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        output_lines = []
        completed = 0
        best_so_far = 0
        t0 = time.time()

        for line in proc.stdout:
            output_lines.append(line)
            # Parsear progresso das linhas tipo "  [  3/660] 150 pts  (...)"
            stripped = line.strip()
            if stripped.startswith("[") and "/" in stripped and "pts" in stripped:
                try:
                    parts = stripped.split("]")[0].replace("[", "").strip().split("/")
                    completed = int(parts[0])
                    total = int(parts[1])
                    pts_str = stripped.split("]")[1].strip().split("pts")[0].strip()
                    pts = int(pts_str)
                    if pts > best_so_far:
                        best_so_far = pts
                    elapsed = time.time() - t0
                    speed = completed / elapsed if elapsed > 0 else 0
                    eta_sec = (total - completed) / speed if speed > 0 else 0
                    progress.progress(completed / total)
                    timer_text.text(
                        f"{completed}/{total} combinacoes | "
                        f"melhor: {best_so_far} pts | "
                        f"{speed:.1f} combos/s | "
                        f"ETA: {eta_sec:.0f}s"
                    )
                except (ValueError, IndexError):
                    pass

        proc.wait()
        stderr_output = proc.stderr.read()

        if proc.returncode == 0:
            progress.progress(1.0)
            elapsed = time.time() - t0
            saved = _load_saved_optimize_results(opt_cup)
            if saved:
                st.session_state[f"optimize_results_{opt_cup}"] = saved
                timer_text.empty()
                status_text.success(
                    f"Concluido! {len(saved)} combinacoes em {elapsed:.0f}s "
                    f"({len(saved)/elapsed:.1f} combos/s). Melhor: {best_so_far} pts"
                )
            else:
                status_text.warning("Otimizacao concluiu mas nenhum resultado foi salvo.")
            with st.expander("Output completo", expanded=False):
                st.code("".join(output_lines[-100:]))
        else:
            status_text.error("Erro no otimizador")
            st.code(stderr_output[:2000])

    session_key = f"optimize_results_{opt_cup}"
    if session_key in st.session_state:
        results = st.session_state[session_key]
        _display_optimize_results(results)


def _display_backtest_result(result: dict):
    """Mostra resultados de um backtest unico."""
    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Modelo", f"{result['model_total']} pts")
    col2.metric("Baseline Fav 1x0", f"{result['b1_total']} pts",
                delta=f"{result['model_total'] - result['b1_total']:+d}")
    col3.metric("Baseline Fav 2x1", f"{result['b2_total']} pts",
                delta=f"{result['model_total'] - result['b2_total']:+d}")
    col4.metric("Baseline 1x1", f"{result['b3_total']} pts",
                delta=f"{result['model_total'] - result['b3_total']:+d}")

    st.caption(f"Grupos: {result['model_groups']} pts | Mata-mata: {result['model_ko']} pts")

    # Detalhamento
    with st.expander("Detalhamento por jogo (fase de grupos)", expanded=False):
        rows = []
        for d in result["details_groups"]:
            rows.append({
                "Jogo": f"{d['home']} vs {d['away']}",
                "Aposta": d["bet"],
                "Real": d["actual"],
                "Pts": d["pts"],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("Detalhamento por jogo (mata-mata)", expanded=False):
        rows = []
        for d in result["details_ko"]:
            rows.append({
                "Jogo": f"{d['home']} vs {d['away']}",
                "Aposta": d["bet"],
                "Real": d["actual"],
                "Pts": d["pts"],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _display_optimize_results(results: list):
    """Mostra resultados do otimizador."""
    st.divider()
    st.subheader("Ranking de Configuracoes")

    best = results[0]
    worst = results[-1]

    col1, col2, col3 = st.columns(3)
    col1.metric("Melhor", f"{best['model_total']} pts")
    col2.metric("Mediana", f"{results[len(results)//2]['model_total']} pts")
    col3.metric("Pior", f"{worst['model_total']} pts")

    # Top 10
    st.markdown("**Top 10:**")
    top_rows = []
    for i, r in enumerate(results[:10]):
        p = r["params"]
        top_rows.append({
            "#": i + 1,
            "Total": r["model_total"],
            "Grupos": r["model_groups"],
            "KO": r["model_ko"],
            "DC": p["w_dc"],
            "ELO": p["w_elo"],
            "TM": p["w_tm"],
            "xi": p["xi"],
            "Scale": p["tm_scale"],
            "QF": "ON" if p["dc_qf_enabled"] else "OFF",
            "Cutoff": p["date_cutoff"],
        })
    st.dataframe(pd.DataFrame(top_rows), use_container_width=True, hide_index=True)

    # Baselines do melhor
    bp = best["params"]
    st.markdown(f"""
    **Melhor config:** DC={bp['w_dc']:.2f}, ELO={bp['w_elo']:.2f}, TM={bp['w_tm']:.2f},
    xi={bp['xi']:.4f}, scale={bp['tm_scale']}, QF={'ON' if bp['dc_qf_enabled'] else 'OFF'},
    cutoff={bp['date_cutoff']}

    | Estrategia | Pts | vs Modelo |
    |---|---|---|
    | **Modelo** | **{best['model_total']}** | — |
    | Baseline Fav 1x0 | {best['b1_total']} | {best['model_total'] - best['b1_total']:+d} |
    | Baseline Fav 2x1 | {best['b2_total']} | {best['model_total'] - best['b2_total']:+d} |
    | Baseline 1x1 | {best['b3_total']} | {best['model_total'] - best['b3_total']:+d} |
    """)

    # Analise de sensibilidade
    with st.expander("Analise de Sensibilidade", expanded=False):
        for var_name, var_key in [
            ("Blend DC", "w_dc"), ("Blend ELO", "w_elo"), ("Blend TM", "w_tm"),
            ("xi", "xi"), ("TM scale", "tm_scale"),
            ("Quality filter", "dc_qf_enabled"), ("Date cutoff", "date_cutoff"),
        ]:
            value_scores = {}
            for r in results:
                val = r["params"][var_key]
                val_str = f"{val}" if isinstance(val, (str, bool)) else f"{val:.4f}"
                if val_str not in value_scores:
                    value_scores[val_str] = []
                value_scores[val_str].append(r["model_total"])

            sens_rows = []
            for val, scores in sorted(value_scores.items(), key=lambda x: -sum(x[1])/len(x[1])):
                sens_rows.append({
                    "Valor": val,
                    "Media": round(sum(scores) / len(scores), 1),
                    "Melhor": max(scores),
                    "Pior": min(scores),
                    "N": len(scores),
                })
            st.markdown(f"**{var_name}:**")
            st.dataframe(pd.DataFrame(sens_rows), use_container_width=True, hide_index=True)

    # Botao para aplicar melhor config ao modelo 2026
    st.divider()
    if st.button("Aplicar melhor config ao modelo 2026", key="btn_apply_best"):
        st.session_state["_pending_apply"] = {
            "w_dc": bp["w_dc"], "w_elo": bp["w_elo"], "w_tm": bp["w_tm"],
            "xi": bp["xi"], "tm_scale": bp["tm_scale"],
            "dc_qf_enabled": bp["dc_qf_enabled"],
        }
        st.session_state["_apply_best_msg"] = (
            f"Config aplicada! DC={bp['w_dc']:.2f}, ELO={bp['w_elo']:.2f}, "
            f"TM={bp['w_tm']:.2f}, xi={bp['xi']:.4f}"
        )
        st.rerun()

    if "_apply_best_msg" in st.session_state:
        st.success(st.session_state.pop("_apply_best_msg"))


# =============================================================================
# Tela: Historico de Simulacoes
# =============================================================================

def render_history_page():
    st.header("Historico de Simulacoes")

    # Listar runs salvos
    pattern = os.path.join(RUNS_DIR, "*.json")
    files = sorted(glob.glob(pattern), reverse=True)

    if not files:
        st.info("Nenhuma simulacao salva. Rode o pipeline e salve na aba 'Rodar Simulacao'.")
        return

    # Lista de runs
    run_meta = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("metadata", {})
            mp = data.get("model_params", {})
            stats = data.get("simulation_stats", {})

            # Favorito
            fav = max(stats.items(), key=lambda x: x[1].get("champion", 0)) if stats else ("?", {})

            run_meta.append({
                "Arquivo": os.path.basename(fp),
                "Nome": meta.get("name", ""),
                "Data": meta.get("timestamp", "")[:19].replace("T", " "),
                "rho": f"{mp.get('rho', 0):.4f}",
                "home_adv": f"{mp.get('home_adv', 0):.3f}",
                "Favorito": f"{fav[0]} ({fav[1].get('champion', 0):.1f}%)",
                "_path": fp,
            })
        except (json.JSONDecodeError, KeyError):
            continue

    if not run_meta:
        st.warning("Nenhum arquivo valido encontrado em runs/.")
        return

    df_runs = pd.DataFrame(run_meta)

    st.subheader(f"{len(run_meta)} simulacao(oes) salva(s)")
    st.dataframe(
        df_runs[["Nome", "Data", "rho", "home_adv", "Favorito"]],
        use_container_width=True, hide_index=True,
    )

    # Selecionar run para visualizar
    options = [r["Nome"] or r["Arquivo"] for r in run_meta]
    selected = st.selectbox("Selecionar simulacao", options, key="sb_history_select")
    idx = options.index(selected)
    selected_path = run_meta[idx]["_path"]

    col_view, col_delete = st.columns([1, 1])

    with col_view:
        if st.button("Visualizar", key="btn_view_run"):
            with open(selected_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.session_state.history_view = data
            st.session_state.history_view_name = selected

    with col_delete:
        if st.button("Excluir", key="btn_delete_run", type="secondary"):
            os.remove(selected_path)
            st.success(f"Simulacao '{selected}' excluida.")
            if "history_view" in st.session_state:
                del st.session_state.history_view
            st.rerun()

    # Visualizar run selecionado
    if "history_view" in st.session_state:
        data = st.session_state.history_view
        name = st.session_state.get("history_view_name", "")
        st.divider()
        st.subheader(f"Simulacao: {name}")

        meta = data.get("metadata", {})
        cal_sum = meta.get("calibration_summary", {})
        st.caption(
            f"DC {cal_sum.get('w_dc', '?')} + Elo {cal_sum.get('w_elo', '?')} "
            f"+ TM {cal_sum.get('w_tm', '?')} | {cal_sum.get('n_sims', '?'):,} sims"
        )

        _display_results(data, elapsed=0, timestamp=meta.get("timestamp", ""), show_save=False)

    # Comparar duas runs
    if len(run_meta) >= 2:
        st.divider()
        st.subheader("Comparar Simulacoes")

        col_a, col_b = st.columns(2)
        with col_a:
            sel_a = st.selectbox("Simulacao A", options, index=0, key="sb_cmp_a")
        with col_b:
            sel_b = st.selectbox("Simulacao B", options,
                                 index=min(1, len(options) - 1), key="sb_cmp_b")

        if st.button("Comparar", key="btn_compare"):
            path_a = run_meta[options.index(sel_a)]["_path"]
            path_b = run_meta[options.index(sel_b)]["_path"]
            with open(path_a, "r", encoding="utf-8") as f:
                data_a = json.load(f)
            with open(path_b, "r", encoding="utf-8") as f:
                data_b = json.load(f)

            _render_comparison(data_a, data_b, sel_a, sel_b)


def _render_comparison(data_a, data_b, name_a, name_b):
    """Compara top 20 favoritos de duas simulacoes lado a lado."""
    stats_a = data_a.get("simulation_stats", {})
    stats_b = data_b.get("simulation_stats", {})

    rows = []
    all_teams = set(list(stats_a.keys()) + list(stats_b.keys()))
    for team in all_teams:
        ca = stats_a.get(team, {}).get("champion", 0)
        cb = stats_b.get(team, {}).get("champion", 0)
        if ca > 0 or cb > 0:
            rows.append({
                "Selecao": team,
                f"Titulo ({name_a})": f"{ca:.1f}%",
                f"Titulo ({name_b})": f"{cb:.1f}%",
                "Delta": f"{cb - ca:+.1f}pp",
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        # Ordenar pelo primeiro run
        col_a_name = f"Titulo ({name_a})"
        df["_sort"] = df[col_a_name].str.rstrip("%").astype(float)
        df = df.sort_values("_sort", ascending=False).drop(columns="_sort").head(20)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Comparar parametros
    mp_a = data_a.get("model_params", {})
    mp_b = data_b.get("model_params", {})

    st.caption(
        f"rho: {mp_a.get('rho', 0):.4f} vs {mp_b.get('rho', 0):.4f} | "
        f"home_adv: {mp_a.get('home_adv', 0):.3f} vs {mp_b.get('home_adv', 0):.3f}"
    )


# =============================================================================
# Layout principal
# =============================================================================

tab_calib, tab_run, tab_backtest, tab_history = st.tabs([
    "Calibracao",
    "Rodar Simulacao",
    "Backtest & Otimizacao",
    "Historico",
])

with tab_calib:
    render_calibration_page()

with tab_run:
    render_run_page()

with tab_backtest:
    render_backtest_page()

with tab_history:
    render_history_page()

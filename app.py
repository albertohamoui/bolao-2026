"""
Bolao 2026 — Frontend Streamlit
Sprint 3a: Setup + Tela de Calibracao
"""

import os
import sys
from datetime import date, datetime

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
    Calibration,
    load_config,
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
            st.success("Salvo com sucesso!")
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
# Stubs das telas futuras
# =============================================================================

def render_run_page_stub():
    st.header("Rodar Simulacao")
    st.info(
        "Em construcao — Sprint 3b.\n\n"
        "Aqui voce podera:\n"
        "- Executar o pipeline com a calibracao ativa\n"
        "- Ver resultados (top favoritos, grupos, apostas EV-optimal)\n"
        "- Rodar sanity checks\n"
        "- Comparar com a ultima simulacao salva\n"
        "- Salvar com nome e notas"
    )


def render_history_page_stub():
    st.header("Historico de Simulacoes")
    st.info(
        "Em construcao — Sprint 3c.\n\n"
        "Aqui voce podera:\n"
        "- Listar simulacoes salvas\n"
        "- Comparar 2+ simulacoes lado a lado\n"
        "- Editar odds de mercado\n"
        "- Lock/unlock/delete simulacoes\n"
        "- Exportar apostas finais"
    )


# =============================================================================
# Layout principal
# =============================================================================

tab_calib, tab_run, tab_history = st.tabs([
    "Calibracao",
    "Rodar Simulacao",
    "Historico",
])

with tab_calib:
    render_calibration_page()

with tab_run:
    render_run_page_stub()

with tab_history:
    render_history_page_stub()

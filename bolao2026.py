"""
BOLAO 2026 - Modelo Estatistico de Previsao da Copa do Mundo FIFA 2026
======================================================================
Arquitetura: Dixon-Coles + Bayesian Update + Monte Carlo
Sprint 3.5: Refatoracao para calibracao via config.json

Para rodar (modo terminal):
    pip install numpy scipy pandas
    python bolao2026.py

Para usar como biblioteca (ex: do Streamlit):
    from bolao2026 import Calibration, run_full_pipeline, load_config
    cal = load_config("config.json")
    result = run_full_pipeline(cal)
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Tuple, Any
import json
import csv
import os

# =============================================================================
# FATOS DA COPA 2026 (hardcoded - nao vao pro config)
# =============================================================================

# Grupos oficiais da Copa 2026 (sorteio 5/dez/2025)
GROUPS: Dict[str, List[str]] = {
    "A": ["Mexico", "South Korea", "South Africa", "Czechia"],
    "B": ["Canada", "Switzerland", "Qatar", "Bosnia and Herzegovina"],
    "C": ["Brazil", "Morocco", "Scotland", "Haiti"],
    "D": ["United States", "Australia", "Paraguay", "Turkey"],
    "E": ["Germany", "Ecuador", "Ivory Coast", "Curacao"],
    "F": ["Netherlands", "Japan", "Tunisia", "Sweden"],
    "G": ["Belgium", "Iran", "Egypt", "New Zealand"],
    "H": ["Spain", "Uruguay", "Saudi Arabia", "Cape Verde"],
    "I": ["France", "Senegal", "Norway", "Iraq"],
    "J": ["Argentina", "Austria", "Algeria", "Jordan"],
    "K": ["Portugal", "Colombia", "Uzbekistan", "DR Congo"],
    "L": ["England", "Croatia", "Panama", "Ghana"],
}

# Confederacao de cada selecao
CONFEDERATIONS: Dict[str, str] = {
    "Mexico": "CONCACAF", "South Korea": "AFC", "South Africa": "CAF", "Czechia": "UEFA",
    "Canada": "CONCACAF", "Switzerland": "UEFA", "Qatar": "AFC", "Bosnia and Herzegovina": "UEFA",
    "Brazil": "CONMEBOL", "Morocco": "CAF", "Scotland": "UEFA", "Haiti": "CONCACAF",
    "United States": "CONCACAF", "Australia": "AFC", "Paraguay": "CONMEBOL", "Turkey": "UEFA",
    "Germany": "UEFA", "Ecuador": "CONMEBOL", "Ivory Coast": "CAF", "Curacao": "CONCACAF",
    "Netherlands": "UEFA", "Japan": "AFC", "Tunisia": "CAF", "Sweden": "UEFA",
    "Belgium": "UEFA", "Iran": "AFC", "Egypt": "CAF", "New Zealand": "OFC",
    "Spain": "UEFA", "Uruguay": "CONMEBOL", "Saudi Arabia": "AFC", "Cape Verde": "CAF",
    "France": "UEFA", "Senegal": "CAF", "Norway": "UEFA", "Iraq": "AFC",
    "Argentina": "CONMEBOL", "Austria": "UEFA", "Algeria": "CAF", "Jordan": "AFC",
    "Portugal": "UEFA", "Colombia": "CONMEBOL", "Uzbekistan": "AFC", "DR Congo": "CAF",
    "England": "UEFA", "Croatia": "UEFA", "Panama": "CONCACAF", "Ghana": "CAF",
}

# Selecoes anfitrias
HOST_TEAMS: set = {"United States", "Mexico", "Canada"}

# Os 9 jogos da fase de grupos onde um host joga no proprio pais.
# Armazenado como lista de tuplas pra poder serializar em JSON se precisar.
# A funcao host_team_for_match converte pra frozenset no lookup.
HOST_HOME_MATCHES_LIST: List[Tuple[str, str]] = [
    ("Mexico", "South Africa"),       # Mexico City
    ("Mexico", "South Korea"),        # Guadalajara
    ("Mexico", "Czechia"),            # Mexico City
    ("Canada", "Qatar"),              # Vancouver
    ("Canada", "Switzerland"),        # Vancouver
    ("Canada", "Bosnia and Herzegovina"),  # Toronto
    ("United States", "Paraguay"),    # Los Angeles
    ("United States", "Australia"),   # Seattle
    ("United States", "Turkey"),      # Los Angeles
]
HOST_HOME_MATCHES: set = {frozenset(p) for p in HOST_HOME_MATCHES_LIST}


def host_team_for_match(team1: str, team2: str) -> Optional[str]:
    """
    Retorna o time da casa se o jogo for um host jogando em seu proprio pais.
    Caso contrario, retorna None (jogo neutro).
    """
    if frozenset({team1, team2}) in HOST_HOME_MATCHES:
        for t in (team1, team2):
            if t in HOST_TEAMS:
                return t
    return None



# =============================================================================
# ELO LOADER — carrega do CSV (fonte unica de verdade)
# =============================================================================

# Lista das 48 selecoes da Copa (derivada de GROUPS)
WORLD_CUP_TEAM_LIST: List[str] = sorted({t for g in GROUPS.values() for t in g})

# Mapeamento de nomes: fontes externas (eloratings.net, results.csv) -> modelo/GROUPS
# Qualquer nome externo que difira do nome em GROUPS deve ter entrada aqui.
_EXTERNAL_TO_MODEL_NAME = {
    "Curaçao": "Curacao",
    "Czech Republic": "Czechia",
}
# Aliases para retrocompatibilidade
_ELO_TO_MODEL_NAME = _EXTERNAL_TO_MODEL_NAME
# Inverso
_MODEL_TO_ELO_NAME = {v: k for k, v in _EXTERNAL_TO_MODEL_NAME.items()}

_ELO_CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "data", "elo_ratings_latest.csv")


def load_world_elo(csv_path: str = _ELO_CSV_PATH) -> Dict[str, int]:
    """Carrega Elo de TODAS as selecoes do CSV gerado por scripts/update_elos.py.

    Aplica mapeamento de nomes pra alinhar com GROUPS/modelo.
    Retorna dict {nome_modelo: elo} com ~244 selecoes.
    Se CSV nao existe, retorna fallback das 48 da Copa.
    """
    if not os.path.exists(csv_path):
        print(f"WARNING: {csv_path} nao encontrado. Usando fallback das 48 da Copa.")
        return dict(_FALLBACK_CUP_ELO)

    result: Dict[str, int] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                name = row["team"]
                elo = int(row["elo"])
                # Aplica mapping de nomes
                model_name = _ELO_TO_MODEL_NAME.get(name, name)
                result[model_name] = elo
            except (ValueError, KeyError):
                continue

    if len(result) < 48:
        print(f"WARNING: CSV tem apenas {len(result)} selecoes. Usando fallback.")
        return dict(_FALLBACK_CUP_ELO)

    # Valida que todas as 48 da Copa estao presentes
    missing = [t for t in WORLD_CUP_TEAM_LIST if t not in result]
    if missing:
        raise ValueError(
            f"ERRO: {len(missing)} selecoes da Copa sem Elo no CSV: {missing}. "
            f"Rode 'python3 scripts/update_elos.py' para atualizar."
        )

    return result


def load_world_cup_elo(world_elo: Dict[str, int]) -> Dict[str, int]:
    """Filtra o Elo global pra apenas as 48 da Copa."""
    return {t: world_elo[t] for t in WORLD_CUP_TEAM_LIST if t in world_elo}


# =============================================================================
# DEFAULTS DE CALIBRACAO (lidos se nao existir config.json)
# =============================================================================

# Fallback das 48 da Copa — usado APENAS se data/elo_ratings_latest.csv nao existir.
# Para atualizar, rode scripts/update_elos.py (que gera o CSV automaticamente).
_FALLBACK_CUP_ELO: Dict[str, int] = {
    "Spain": 2165, "Argentina": 2113, "France": 2082, "England": 2020,
    "Brazil": 1984, "Portugal": 1984, "Colombia": 1975, "Netherlands": 1961,
    "Ecuador": 1933, "Croatia": 1930, "Germany": 1923, "Norway": 1912,
    "Japan": 1904, "Turkey": 1902, "Uruguay": 1892, "Switzerland": 1889,
    "Senegal": 1879, "Belgium": 1866, "Mexico": 1858, "Paraguay": 1833,
    "Austria": 1827, "Morocco": 1821, "Canada": 1784, "Australia": 1783,
    "Scotland": 1767, "Iran": 1760, "South Korea": 1752, "Algeria": 1743,
    "Panama": 1737, "Uzbekistan": 1727, "Czechia": 1726, "United States": 1721,
    "Sweden": 1719, "Jordan": 1690, "Egypt": 1689, "Ivory Coast": 1676,
    "DR Congo": 1655, "Tunisia": 1636, "Iraq": 1607,
    "Bosnia and Herzegovina": 1594, "New Zealand": 1585, "Saudi Arabia": 1568,
    "Cape Verde": 1549, "Haiti": 1532, "South Africa": 1524, "Ghana": 1505,
    "Curacao": 1436, "Qatar": 1425,
}

# Mantido como DEFAULT_ELO_RATINGS por retrocompatibilidade (app.py importa)
DEFAULT_ELO_RATINGS = _FALLBACK_CUP_ELO

# Valor de mercado do elenco (Transfermarkt, marco 2026, em milhoes de Euros)
DEFAULT_TRANSFERMARKT_VALUES: Dict[str, int] = {
    "England": 1300, "France": 1280, "Spain": 920, "Portugal": 865,
    "Brazil": 854, "Germany": 817, "Netherlands": 712, "Argentina": 600,
    "Belgium": 549, "Croatia": 350, "Colombia": 350, "Uruguay": 300,
    "Morocco": 250, "Switzerland": 220, "Japan": 200, "United States": 180,
    "Mexico": 150, "South Korea": 150, "Senegal": 145, "Austria": 140,
    "Norway": 135, "Ecuador": 120, "Turkey": 115, "Sweden": 110,
    "Canada": 95, "Czechia": 95, "Iran": 95, "Algeria": 90,
    "Scotland": 90, "Australia": 85, "Egypt": 80, "Ivory Coast": 75,
    "Tunisia": 70, "Ghana": 70, "Paraguay": 60, "Bosnia and Herzegovina": 60,
    "DR Congo": 55, "Panama": 50, "South Africa": 45, "Saudi Arabia": 35,
    "Iraq": 30, "Uzbekistan": 30, "Qatar": 25, "Jordan": 22,
    "New Zealand": 22, "Cape Verde": 18, "Haiti": 15, "Curacao": 12,
}


# =============================================================================
# CLASSE CALIBRATION
# =============================================================================

@dataclass
class Calibration:
    """
    Todos os parametros editaveis do modelo. Pode ser serializada pra JSON
    (config.json) e editada pelo frontend ou manualmente.

    Pesos do blend bayesiano:
        w_dc, w_elo, w_tm: devem somar 1.0 (validado).

    Time-decay:
        xi: quanto maior, mais peso em jogos recentes na calibracao Dixon-Coles.

    Host advantage:
        wc_host_adv: vantagem de mando em escala log para os 9 jogos de host
                     jogando em proprio pais (exp(0.12) = ~+12.7% no lambda).

    Monte Carlo:
        n_sims: numero de simulacoes. Default 50k.

    Filtro temporal:
        date_cutoff: string ISO (YYYY-MM-DD). Jogos anteriores sao ignorados.

    Escala do TM:
        tm_scale: "sqrt" (default), "log" ou "linear".

    Split ataque/defesa no blend:
        ad_split: [attack_ratio, defense_ratio]. Default [0.6, -0.4] - defesa
                  negativa porque defesa boa = sofre menos gols.

    Dados por time:
        elo_ratings: dict {time: elo}
        transfermarkt_values: dict {time: valor_em_milhoes_euros}
        expert_adjustments: dict {time: {"attack_mult": float, "defense_mult": float}}
    """
    # Pesos do blend
    w_dc: float = 0.45
    w_elo: float = 0.30
    w_tm: float = 0.25

    # Dixon-Coles
    xi: float = 0.001

    # Host advantage
    wc_host_adv: float = 0.12

    # Monte Carlo
    n_sims: int = 50000

    # Filtro de dados
    date_cutoff: str = "2022-01-01"

    # Escala TM
    tm_scale: str = "sqrt"  # "sqrt" | "log" | "linear"

    # Proporcao ataque/defesa nos priors
    ad_split: List[float] = field(default_factory=lambda: [0.6, -0.4])

    # Filtro de qualidade no DC fitting (pesa menos jogos entre adversarios desiguais)
    dc_quality_filter: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "thresholds": [300, 200, 100],
        "weights": [0.2, 0.5, 0.8, 1.0],
    })

    # Tournament factor: ajuste residual pos-blend baseado em performance
    # em torneios curtos (Copas, Euros, Copa America) vs eliminatorias/amistosos.
    tournament_factor: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "weight": 0.15,
        "min_games": 5,
        "start_year": 2014,
        "tournaments": [
            "FIFA World Cup",
            "UEFA Euro",
            "Copa América",
            "Copa America",
        ],
    })

    # Modelo de artilheiro: sorteia autor de cada gol no Monte Carlo.
    # Ativar apos preencher player_stats. Com enabled=false, sem efeito.
    top_scorer_model: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": False,
        "position_probabilities": {"ATK": 0.75, "MID": 0.15, "DEF": 0.10},
        "regularization_k": 5,
        "simulation_noise_sigma": 0.2,
        "player_stats": {},
    })

    # Modelo de escalacao: ajuste por qualidade do plantel convocado vs ideal.
    # Ativar apos convocacoes FIFA (~01/jun/2026). Com enabled=false, sem efeito.
    squad_data: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": False,
        "weight": 0.5,
        "use_top_11": False,
        "ideal_squad_values": {},
        "convocated_squads": {},
    })

    # Dados por time
    elo_ratings: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_ELO_RATINGS))
    transfermarkt_values: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_TRANSFERMARKT_VALUES))
    expert_adjustments: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def validate(self) -> List[str]:
        """Retorna lista de erros. Vazia = ok."""
        errors = []
        s = self.w_dc + self.w_elo + self.w_tm
        if abs(s - 1.0) > 1e-6:
            errors.append(f"Pesos do blend nao somam 1.0 (soma={s:.4f})")
        if self.xi < 0:
            errors.append(f"xi deve ser >= 0 (atual={self.xi})")
        if self.n_sims < 100:
            errors.append(f"n_sims muito baixo (atual={self.n_sims}, min=100)")
        if self.tm_scale not in ("sqrt", "log", "linear"):
            errors.append(f"tm_scale deve ser sqrt/log/linear (atual={self.tm_scale})")
        if len(self.ad_split) != 2:
            errors.append(f"ad_split deve ter 2 elementos (atual={self.ad_split})")
        return errors

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Calibration":
        """Cria Calibration a partir de dict, com fallback nos defaults pra campos faltantes."""
        defaults = cls()
        for k in list(d.keys()):
            if not hasattr(defaults, k):
                # Ignora campos desconhecidos em vez de dar erro
                d.pop(k)
        return cls(**{**asdict(defaults), **d})


def load_config(path: str = "config.json") -> Calibration:
    """Carrega config.json. Se nao existir, cria com defaults e salva."""
    if not os.path.exists(path):
        cal = Calibration()
        save_config(cal, path)
        print(f"config.json nao encontrado. Criado em {path} com defaults.")
        return cal
    with open(path, 'r', encoding='utf-8') as f:
        d = json.load(f)
    cal = Calibration.from_dict(d)
    errors = cal.validate()
    if errors:
        print("AVISO: config.json tem erros de validacao:")
        for e in errors:
            print(f"  - {e}")
    return cal


def save_config(cal: Calibration, path: str = "config.json") -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cal.to_dict(), f, indent=2, ensure_ascii=False)


# =============================================================================
# MODELO DE ESCALACAO
# =============================================================================


def _compute_squad_multiplier(
    team: str,
    ideal_values: Dict[str, int],
    squads: Dict[str, list],
    weight: float,
    use_top_11: bool,
) -> float:
    """
    Calcula multiplicador de escalacao para um time.

    Retorna 1.0 (sem efeito) se dados insuficientes.
    Caso contrario:
        raw_mult = sum(value convocados) / ideal
        mult = 1 + weight * (raw_mult - 1)

    Com use_top_11=True, soma apenas os 11 jogadores de maior valor e
    normaliza o ideal por 11/26 (aproximacao — nao temos breakdown
    posicional do ideal).
    """
    convocated = squads.get(team)
    if not convocated:
        return 1.0

    ideal = ideal_values.get(team)
    if not ideal or ideal == 0:
        return 1.0

    if use_top_11:
        sorted_players = sorted(
            convocated, key=lambda p: p.get("value_eur_m", 0), reverse=True
        )
        actual = sum(p.get("value_eur_m", 0) for p in sorted_players[:11])
        ideal_normalized = ideal * (11 / 26)
        if ideal_normalized == 0:
            return 1.0
        raw_mult = actual / ideal_normalized
    else:
        actual = sum(p.get("value_eur_m", 0) for p in convocated)
        raw_mult = actual / ideal

    return 1 + weight * (raw_mult - 1)


# =============================================================================
# MODELO DE ARTILHEIRO
# =============================================================================


def precompute_scorer_data(
    cal: "Calibration",
) -> Optional[Dict[str, Any]]:
    """
    Pre-computa pesos de gol por (time, posicao) para o modelo de artilheiro.

    Chamado UMA VEZ antes do loop Monte Carlo. Retorna None se desabilitado
    ou sem dados.

    Para cada time com player_stats:
      - Agrupa jogadores por posicao (ATK, MID, DEF)
      - Calcula base_weight = goals_season + 0.7 * xg_season (com fallbacks)
      - Aplica regularizacao bayesiana: (bw + k * mean) / (1 + k)
      - Normaliza por posicao -> probabilidades base

    Retorna:
        {
            "teams": {
                team_name: {
                    "positions": ["ATK", "MID", "DEF"],  # posicoes com jogadores
                    "pos_probs": np.array,  # prob de cada posicao (normalizada)
                    "by_position": {
                        "ATK": {"names": [...], "base_probs": np.array},
                        ...
                    },
                    "all_player_names": [...],  # flat list de todos os jogadores
                },
                ...
            },
            "sigma": float,  # noise sigma pra o ruido por simulacao
        }
    """
    ts_cfg = cal.top_scorer_model
    if not isinstance(ts_cfg, dict) or not ts_cfg.get("enabled", False):
        return None

    player_stats = ts_cfg.get("player_stats", {})
    if not player_stats:
        return None

    pos_probs_cfg = ts_cfg.get("position_probabilities",
                                {"ATK": 0.75, "MID": 0.15, "DEF": 0.10})
    k = ts_cfg.get("regularization_k", 5)
    sigma = ts_cfg.get("simulation_noise_sigma", 0.2)
    pos_order = ["ATK", "MID", "DEF"]

    result_teams: Dict[str, Any] = {}

    for team, players in player_stats.items():
        if not players:
            continue

        by_pos: Dict[str, List[Tuple[str, float]]] = {p: [] for p in pos_order}

        for pl in players:
            pos = pl.get("position")
            if pos not in by_pos:
                continue  # skip jogadores com posicao invalida/None
            name = pl.get("name", "Unknown")
            gs = pl.get("goals_season")
            xg = pl.get("xg_season")
            val = pl.get("value_eur_m", 0)

            # Base weight com fallbacks
            if gs is not None and xg is not None:
                bw = gs + 0.7 * xg
            elif gs is not None:
                bw = gs
            elif xg is not None:
                bw = 0.7 * xg
            else:
                bw = max(val / 10.0, 0.1)  # fallback: valor / 10

            by_pos[pos].append((name, max(bw, 0.01)))

        # Filtra posicoes vazias e computa probs
        pos_data: Dict[str, Dict[str, Any]] = {}
        actual_pos_probs = []
        actual_positions = []

        for pos in pos_order:
            if not by_pos[pos]:
                continue
            names = [n for n, _ in by_pos[pos]]
            weights = np.array([w for _, w in by_pos[pos]])

            # Regularizacao bayesiana
            mean_w = np.mean(weights)
            regularized = (weights + k * mean_w) / (1 + k)

            # Normaliza
            total = regularized.sum()
            probs = regularized / total if total > 0 else np.ones(len(regularized)) / len(regularized)

            pos_data[pos] = {"names": names, "base_probs": probs}
            actual_positions.append(pos)
            actual_pos_probs.append(pos_probs_cfg.get(pos, 0.0))

        if not actual_positions:
            continue

        # Normaliza probabilidades de posicao pelas posicoes realmente presentes
        pp = np.array(actual_pos_probs)
        pp = pp / pp.sum()

        all_names = []
        for pos in actual_positions:
            all_names.extend(pos_data[pos]["names"])

        result_teams[team] = {
            "positions": actual_positions,
            "pos_probs": pp,
            "by_position": pos_data,
            "all_player_names": all_names,
        }

    if not result_teams:
        return None

    return {"teams": result_teams, "sigma": sigma}


def sample_sim_noise(
    scorer_data: Dict[str, Any],
    rng: np.random.RandomState,
) -> Dict[str, np.ndarray]:
    """
    Sorteia ruido gaussiano por jogador, UMA VEZ por simulacao.

    Cada simulacao tem um "dia" especifico pra cada jogador: nesta
    simulacao Haaland esta em dia bom (multiplier 1.15), Mbappe em dia
    ruim (0.85), etc. Persiste coerencia dentro da mesma Copa simulada.

    Retorna: {team: {pos: noisy_probs}} pre-normalizado.
    """
    sigma = scorer_data["sigma"]
    noisy: Dict[str, Dict[str, np.ndarray]] = {}

    for team, tdata in scorer_data["teams"].items():
        noisy[team] = {}
        for pos in tdata["positions"]:
            bp = tdata["by_position"][pos]["base_probs"]
            n = len(bp)
            noise = rng.normal(0, sigma, size=n)
            noisy_w = bp * np.maximum(0.1, 1 + noise)
            total = noisy_w.sum()
            noisy[team][pos] = noisy_w / total if total > 0 else bp

    return noisy


def sample_goals_for_team(
    team: str,
    n_goals: int,
    scorer_data: Dict[str, Any],
    noisy_probs: Dict[str, Dict[str, np.ndarray]],
    rng: np.random.RandomState,
) -> Dict[str, int]:
    """
    Para um time com n_goals gols numa simulacao, sorteia quem marcou cada um.

    Retorna {player_name: n_gols} ou {} se time nao tem player_stats.
    """
    if n_goals <= 0:
        return {}
    tdata = scorer_data["teams"].get(team)
    if tdata is None:
        return {}

    positions = tdata["positions"]
    pos_probs = tdata["pos_probs"]
    team_noisy = noisy_probs.get(team, {})

    # Sorteia posicoes para todos os gols de uma vez
    pos_indices = rng.choice(len(positions), size=n_goals, p=pos_probs)

    goal_counts: Dict[str, int] = {}
    for pos_idx in pos_indices:
        pos = positions[pos_idx]
        pd = tdata["by_position"][pos]
        probs = team_noisy.get(pos, pd["base_probs"])
        player_idx = rng.choice(len(pd["names"]), p=probs)
        name = pd["names"][player_idx]
        goal_counts[name] = goal_counts.get(name, 0) + 1

    return goal_counts


# =============================================================================
# REGRAS DO BOLAO E EV-OPTIMAL SCORE
# =============================================================================

# Tabelas canonicas de pontuacao (manual bolaodozap.com, pagina 4).
# Tiers mutuamente exclusivos: pega o mais alto que aplica.
_POINTS_GROUP = {
    "exact":        10,  # Placar exato (com vitoria)
    "diff":          6,  # Diferenca de gols certa
    "winner_goals":  5,  # Gols do vencedor certos
    "loser_goals":   4,  # Gols do perdedor certos
    "winner_only":   3,  # So o vencedor certo
    "draw_exact":   10,  # Empate com placar exato
    "draw_wrong":    6,  # Empate com placar errado
}
# Mata-mata: valores canonicos do manual (pagina 4).
# Nota: manual antigo descrevia como "x1.5 com arredondamento"; manual
# novo lista os valores finais diretamente, sem mencionar a formula.
_POINTS_KNOCKOUT = {
    "exact":        15,
    "diff":          9,
    "winner_goals":  8,  # manual pagina 4
    "loser_goals":   6,
    "winner_only":   5,  # manual pagina 4
    "draw_exact":   15,
    "draw_wrong":    9,
}


def bolao_points(bet: Tuple[int, int], actual: Tuple[int, int], knockout: bool = False) -> int:
    """
    Pontos do bolao 2026 para uma aposta vs resultado real.

    Tabela (Grupos / Mata-Mata) - manual bolaodozap.com pagina 4:
        Placar exato:        10 / 15
        Diferenca de gols:    6 /  9
        Gols do vencedor:     5 /  8
        Gols do perdedor:     4 /  6
        So o vencedor:        3 /  5
        Empate exato:        10 / 15
        Empate placar errado: 6 /  9
        Errou vencedor:       0 /  0

    Tiers mutuamente exclusivos: pega o mais alto que aplica.

    No mata-mata o placar e avaliado apos 90/120min. Empate vale como empate
    mesmo quando o jogo e decidido nos penaltis (manual pag 4, rodape).
    """
    bh, ba = bet
    rh, ra = actual
    table = _POINTS_KNOCKOUT if knockout else _POINTS_GROUP

    bet_draw = (bh == ba)
    result_draw = (rh == ra)

    if bet_draw:
        if not result_draw:
            return 0
        return table["draw_exact"] if bh == rh else table["draw_wrong"]

    if result_draw:
        return 0
    if (bh > ba) != (rh > ra):
        return 0

    if (bh, ba) == (rh, ra):
        return table["exact"]
    if (bh - ba) == (rh - ra):
        return table["diff"]

    if bh > ba:
        bet_winner_g, bet_loser_g = bh, ba
        result_winner_g, result_loser_g = rh, ra
    else:
        bet_winner_g, bet_loser_g = ba, bh
        result_winner_g, result_loser_g = ra, rh

    if bet_winner_g == result_winner_g:
        return table["winner_goals"]
    if bet_loser_g == result_loser_g:
        return table["loser_goals"]
    return table["winner_only"]


def smart_baseline_score(
    score_matrix: np.ndarray,
    lambdas: Tuple[float, float],
    draw_threshold: float = 0.35,
    draw_score: Tuple[int, int] = (1, 1),
    big_win_lambda_diff: float = 0.5,
    big_win_score: Tuple[int, int] = (2, 0),
    normal_win_score: Tuple[int, int] = (2, 1),
) -> Tuple[int, int]:
    """
    Smart Baseline: usa probabilidades DC para escolher placar.

    1. Se P(empate) > draw_threshold -> draw_score
    2. Se |lambda_h - lambda_a| > big_win_lambda_diff -> big_win_score pro favorito
    3. Senao -> normal_win_score pro favorito
    """
    n = score_matrix.shape[0]
    p_draw = sum(float(score_matrix[i, i]) for i in range(n))
    lh, la = lambdas

    if p_draw > draw_threshold:
        return draw_score

    diff = abs(lh - la)
    home_is_fav = lh >= la

    if diff > big_win_lambda_diff:
        score = big_win_score
    else:
        score = normal_win_score

    if home_is_fav:
        return score
    else:
        return (score[1], score[0])


def ev_optimal_score(score_matrix: np.ndarray, knockout: bool = False, max_goals: int = 8):
    """
    Encontra o placar (a, b) que maximiza o valor esperado de pontos
    do bolao, dado a distribuicao de probabilidades de placares.
    """
    best_ev = -1.0
    best_score = (0, 0)
    n = min(max_goals, score_matrix.shape[0])

    for a in range(n):
        for b in range(n):
            ev = 0.0
            for i in range(n):
                for j in range(n):
                    p = score_matrix[i, j]
                    if p <= 0:
                        continue
                    ev += p * bolao_points((a, b), (i, j), knockout=knockout)
            if ev > best_ev:
                best_ev = ev
                best_score = (a, b)

    return best_score, best_ev


def knockout_advance_points(bet_hits: List[bool]) -> int:
    """
    Pontos do bonus "acertou o time que avancou" no mata-mata.
    10 pts por confronto em que o lado apostado avancou (manual pag 4).
    """
    return 10 * sum(1 for hit in bet_hits if hit)


def optimal_knockout_bet(
    score_matrix: np.ndarray,
    p_advance_home: float,
    home: str,
    away: str,
    max_goals: int = 8,
) -> Dict[str, Any]:
    """
    Palpite otimo para um confronto de mata-mata, maximizando EV combinado de
    placar (max 15 pts) + bonus "time que avancou" (10 pts).

    Formulacao fatorada (manual bolaodozap.com pag 4 e 5):
        - Se o palpite de placar tem vencedor, o bracket avanca o vencedor
          automaticamente - bet_advance fica amarrado ao placar.
        - Se o palpite e empate, o palpiteiro escolhe livremente quem passa
          nos penaltis - bet_advance e independente do placar.

    Logo, para cada lado candidato ao avanco so fazem sentido placares onde
    aquele lado vence ou placares de empate:

        Para bet_advance em {home, away}:
            ev_vitoria = max sobre placares (a,b) em que bet_advance vence
                         de E[placar_pts((a,b), real)]
            ev_empate  = max sobre placares (n,n)
                         de E[placar_pts((n,n), real)]
            EV(bet_advance) = max(ev_vitoria, ev_empate)
                              + 10 * P(bet_advance avanca)

    O EV total e max sobre os dois candidatos.

    METHODOLOGICAL NOTE: score_matrix e a distribuicao de placares em 90min.
    No mata-mata o placar real considera 90 ou 120min (manual pag 4). Usar a
    matriz de 90min e aproximacao - o placar pos-prorrogacao tende a ter mais
    gols, mas a massa em 1x0/2x1 e robusta o bastante para que a aposta
    EV-optimal tipicamente nao mude. Ja p_advance_home e a marginal correta
    (inclui vitoria em 90/120min e penaltis), agregada do Monte Carlo.

    TODO(pre-R32): na vespera do R32, quando os pares estao definidos, vale
    refinar score_matrix usando Poisson de prorrogacao especifica do par.
    Para R16+ mantem 90min porque os pares sao incertos.

    Parametros:
        score_matrix: shape (>=max_goals, >=max_goals), P(home=i, away=j) 90min.
        p_advance_home: P(home avanca), marginal agregada (0..1).
        home, away: nomes dos times (usados apenas no output).
        max_goals: truncamento da iteracao.

    Retorna:
        {
            "bet_score": (a, b),
            "bet_advance": str,       # nome do time
            "regime": "vitoria" ou "empate",
            "ev_score": float,        # EV da componente de placar
            "ev_advance": float,      # EV do bonus de avanco (10 * p)
            "ev_total": float,
        }
    """
    n = min(max_goals, score_matrix.shape[0])
    p_adv = {home: p_advance_home, away: 1.0 - p_advance_home}

    # EV de placar para cada candidato (a,b)
    ev_cache: Dict[Tuple[int, int], float] = {}
    for a in range(n):
        for b in range(n):
            ev = 0.0
            for i in range(n):
                for j in range(n):
                    p = score_matrix[i, j]
                    if p <= 0:
                        continue
                    ev += p * bolao_points((a, b), (i, j), knockout=True)
            ev_cache[(a, b)] = ev

    # Regime empate: mesmo para os dois candidatos ao avanco
    draw_candidates = [(k, k) for k in range(n)]
    best_draw_score = max(draw_candidates, key=lambda s: ev_cache[s])
    best_draw_ev = ev_cache[best_draw_score]

    best = None  # (ev_total, bet_score, bet_advance, regime, ev_score, ev_advance)
    for team in (home, away):
        if team == home:
            victory_candidates = [(a, b) for a in range(n) for b in range(n) if a > b]
        else:
            victory_candidates = [(a, b) for a in range(n) for b in range(n) if a < b]

        best_vict_score = max(victory_candidates, key=lambda s: ev_cache[s])
        best_vict_ev = ev_cache[best_vict_score]

        if best_vict_ev >= best_draw_ev:
            chosen_score = best_vict_score
            ev_score = best_vict_ev
            regime = "vitoria"
        else:
            chosen_score = best_draw_score
            ev_score = best_draw_ev
            regime = "empate"

        ev_advance = 10.0 * p_adv[team]
        ev_total = ev_score + ev_advance

        cand = (ev_total, chosen_score, team, regime, ev_score, ev_advance)
        if best is None or cand[0] > best[0]:
            best = cand

    return {
        "bet_score": (int(best[1][0]), int(best[1][1])),
        "bet_advance": best[2],
        "regime": best[3],
        "ev_score": float(best[4]),
        "ev_advance": float(best[5]),
        "ev_total": float(best[0]),
    }


def optimal_group_bet(
    joint_top2: np.ndarray,
    teams: List[str],
) -> Dict[str, Any]:
    """
    Escolhe (bet_1st, bet_2nd) que maximiza EV do bonus de classificacao do
    grupo. Manual pag 4 (max 20 pts por grupo):

        10 pts se bet_1st = 1o real
        10 pts se bet_2nd = 2o real
         5 pts se bet_1st foi classificado em posicao trocada (foi 2o real)
         5 pts se bet_2nd foi classificado em posicao trocada (foi 1o real)

    A distribuicao conjunta joint_top2 captura a correlacao entre os palpites:
    cenario "apostei A 1o, B 2o; real A 2o, B 1o" paga 5+5=10, nao zero.
    Marginais P(1o=X) e P(2o=Y) nao capturariam isso.

    Parametros:
        joint_top2: shape (k, k), joint_top2[i, j] = P(1o=teams[i], 2o=teams[j]).
                    Diagonal = 0 (um time nao pode ser 1o e 2o ao mesmo tempo).
        teams: lista de times na mesma ordem da indexacao da matriz.

    Retorna:
        {
            "bet_1st": str,
            "bet_2nd": str,
            "ev_points": float,       # EV em pontos (max 20)
            "p_both_exact": float,    # P(acertar os dois na pos certa)
            "p_at_least_one_pt": float,  # P(pegar >=1 pt do bonus)
        }
    """
    k = len(teams)
    best_ev, best_b1, best_b2 = -1.0, 0, 1
    for b1 in range(k):
        for b2 in range(k):
            if b1 == b2:
                continue
            ev = 0.0
            for i in range(k):
                for j in range(k):
                    if i == j:
                        continue
                    p = joint_top2[i, j]
                    if p <= 0:
                        continue
                    pts = 0
                    if b1 == i:
                        pts += 10
                    elif b1 == j:
                        pts += 5
                    if b2 == j:
                        pts += 10
                    elif b2 == i:
                        pts += 5
                    ev += p * pts
            if ev > best_ev:
                best_ev, best_b1, best_b2 = ev, b1, b2

    p_both_exact = float(joint_top2[best_b1, best_b2])
    p_at_least_one = 0.0
    for i in range(k):
        for j in range(k):
            if i == j:
                continue
            if best_b1 in (i, j) or best_b2 in (i, j):
                p_at_least_one += float(joint_top2[i, j])

    return {
        "bet_1st": teams[best_b1],
        "bet_2nd": teams[best_b2],
        "ev_points": float(best_ev),
        "p_both_exact": p_both_exact,
        "p_at_least_one_pt": p_at_least_one,
    }


def optimal_champion_bet(champion_probs: Dict[str, float]) -> Dict[str, Any]:
    """
    Aposta otima de campeao: argmax P(champion). Manual pag 5: 25 pts.

    Parametros:
        champion_probs: {time: P(champion)} em fracao [0, 1].
                        (O Monte Carlo retorna em %; converter antes.)

    Retorna:
        {"bet": str, "p_champion": float, "ev_points": float}
    """
    if not champion_probs:
        return {"bet": None, "p_champion": 0.0, "ev_points": 0.0}
    team = max(champion_probs, key=champion_probs.get)
    p = float(champion_probs[team])
    return {"bet": team, "p_champion": p, "ev_points": 25.0 * p}


def induced_third_places(
    predictions: Dict[str, Any],
    groups: Dict[str, List[str]],
) -> Dict[str, Any]:
    """
    Calcula os terceiros colocados induzidos pelos placares EV-optimal de
    cada grupo e identifica os 8 melhores pelo criterio FIFA (pts, saldo,
    gols marcados).

    Manual pag 3 (aba "3os Colocados"): os palpites de 3o sao derivados
    automaticamente dos placares apostados. Esta funcao replica essa logica.

    Nota: usa criterio simplificado pts -> gd -> gf (sem confronto direto ou
    fair play). E o mesmo criterio usado pelo Monte Carlo interno
    (WorldCupSimulator._simulate_group), entao as tabelas sao consistentes.

    Parametros:
        predictions: output["predictions"] de run_full_pipeline, contendo
                     score_ev por jogo.
        groups: dict {gname: [teams]}.

    Retorna:
        {
            "thirds_per_group": {gname: team, ...},  # 12 entradas, 1 por grupo
            "top8_induced": [team, ...],             # 8 melhores 3os (ordenados)
            "bottom4_eliminated": [team, ...],       # 4 3os eliminados
            "induced_tables": {gname: {"standings": [...], "table": {...}}},
        }
    """
    thirds = {}
    induced_tables: Dict[str, Dict[str, Any]] = {}
    for gname, teams in groups.items():
        table = {t: {"pts": 0, "gf": 0, "ga": 0, "gd": 0} for t in teams}
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                h, a = teams[i], teams[j]
                key = f"{h} vs {a}"
                if key not in predictions:
                    continue
                ev_str = predictions[key]["score_ev"]
                hg, ag = (int(x) for x in ev_str.split("x"))
                table[h]["gf"] += hg
                table[h]["ga"] += ag
                table[h]["gd"] += (hg - ag)
                table[a]["gf"] += ag
                table[a]["ga"] += hg
                table[a]["gd"] += (ag - hg)
                if hg > ag:
                    table[h]["pts"] += 3
                elif hg < ag:
                    table[a]["pts"] += 3
                else:
                    table[h]["pts"] += 1
                    table[a]["pts"] += 1

        standings = sorted(
            teams,
            key=lambda t: (table[t]["pts"], table[t]["gd"], table[t]["gf"]),
            reverse=True,
        )
        induced_tables[gname] = {
            "standings": standings,
            "table": {t: dict(table[t]) for t in teams},
        }
        if len(standings) >= 3:
            thirds[gname] = standings[2]

    third_entries = []
    for gname, team in thirds.items():
        stats = induced_tables[gname]["table"][team]
        third_entries.append((gname, team, stats["pts"], stats["gd"], stats["gf"]))
    third_entries.sort(key=lambda e: (e[2], e[3], e[4]), reverse=True)

    top8 = [e[1] for e in third_entries[:8]]
    bottom4 = [e[1] for e in third_entries[8:]]

    return {
        "thirds_per_group": thirds,
        "top8_induced": top8,
        "bottom4_eliminated": bottom4,
        "induced_tables": induced_tables,
    }


def third_places_ev(
    top8_induced: List[str],
    team_stats: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """
    EV do bonus de 3os colocados (manual pag 4: 5 pts por cada 3o acertado
    entre os 8 que avancaram).

    Parametros:
        top8_induced: lista de 8 times que o sistema selecionaria como nossos
                      palpites de 3o (output de induced_third_places).
        team_stats: saida do MC; team_stats[t]["group_3rd_qual"] em % -
                    probabilidade de t ser um dos 8 3os reais qualificados.

    Retorna:
        {"ev_points": float, "per_team": [{"team", "p", "ev"}, ...]}
    """
    per_team = []
    total_ev = 0.0
    for t in top8_induced:
        p = float(team_stats.get(t, {}).get("group_3rd_qual", 0.0)) / 100.0
        ev = 5.0 * p
        total_ev += ev
        per_team.append({"team": t, "p_3rd_qual": p, "ev": ev})
    return {"ev_points": total_ev, "per_team": per_team}


# =============================================================================
# MODELO DIXON-COLES
# =============================================================================

class DixonColesModel:
    """
    Modelo Dixon-Coles para previsao de resultados de futebol.
    Agora depende de um Calibration em vez de globals.
    """

    def __init__(self, teams: List[str], cal: Calibration,
                 world_elo: Optional[Dict[str, int]] = None):
        self.teams = sorted(teams)
        self.team_idx = {t: i for i, t in enumerate(self.teams)}
        self.n_teams = len(self.teams)
        self.cal = cal
        self.world_elo = world_elo or dict(cal.elo_ratings)
        self.params = None
        self.attack: Dict[str, float] = {}
        self.defense: Dict[str, float] = {}
        self.home_adv: float = 0.0
        self.rho: float = 0.0

    def _tau(self, x, y, lambda_x, mu_y, rho):
        if x == 0 and y == 0:
            return 1 - lambda_x * mu_y * rho
        elif x == 0 and y == 1:
            return 1 + lambda_x * rho
        elif x == 1 and y == 0:
            return 1 + mu_y * rho
        elif x == 1 and y == 1:
            return 1 - rho
        else:
            return 1.0

    def _unpack_params(self, params):
        n = self.n_teams
        attack = params[:n]
        defense = params[n:2*n]
        home_adv = params[2*n]
        rho = params[2*n + 1]
        return attack, defense, home_adv, rho

    def _log_likelihood(self, params, matches, weights):
        """Versao original (mantida para compatibilidade com audit scripts)."""
        attack, defense, home_adv, rho = self._unpack_params(params)
        log_lik = 0.0
        attack_penalty = 100 * (np.sum(attack) ** 2)
        for i, (home, away, hg, ag, _) in enumerate(matches):
            hi = self.team_idx.get(home)
            ai = self.team_idx.get(away)
            if hi is None or ai is None:
                continue
            lambda_h = np.clip(np.exp(attack[hi] + defense[ai] + home_adv), 0.001, 15.0)
            mu_a = np.clip(np.exp(attack[ai] + defense[hi]), 0.001, 15.0)
            tau = self._tau(hg, ag, lambda_h, mu_a, rho)
            if tau <= 0:
                tau = 0.0001
            w = weights[i]
            log_lik += w * (np.log(tau) + hg * np.log(lambda_h) - lambda_h
                            + ag * np.log(mu_a) - mu_a)
        return -log_lik + attack_penalty

    def _nll_and_grad(self, params, hi_arr, ai_arr, hg_arr, ag_arr, w_arr):
        """
        Neg-log-likelihood + gradiente analitico, totalmente vectorizado.

        Recebe arrays pre-computados (indices inteiros, nao nomes de time).
        Retorna (nll, grad) para uso com minimize(..., jac=True).
        """
        attack, defense, home_adv, rho = self._unpack_params(params)
        n = self.n_teams

        # --- Forward: lambdas e mus ---
        lh_raw = np.exp(attack[hi_arr] + defense[ai_arr] + home_adv)
        ma_raw = np.exp(attack[ai_arr] + defense[hi_arr])
        lh = np.clip(lh_raw, 0.001, 15.0)
        ma = np.clip(ma_raw, 0.001, 15.0)

        # Mascara de clipping (gradiente = 0 onde clip ativou)
        lh_active = (lh_raw > 0.001) & (lh_raw < 15.0)
        ma_active = (ma_raw > 0.001) & (ma_raw < 15.0)

        # --- Tau vectorizado ---
        tau = np.ones_like(lh)
        m00 = (hg_arr == 0) & (ag_arr == 0)
        m01 = (hg_arr == 0) & (ag_arr == 1)
        m10 = (hg_arr == 1) & (ag_arr == 0)
        m11 = (hg_arr == 1) & (ag_arr == 1)

        tau[m00] = 1.0 - lh[m00] * ma[m00] * rho
        tau[m01] = 1.0 + lh[m01] * rho
        tau[m10] = 1.0 + ma[m10] * rho
        tau[m11] = 1.0 - rho
        tau = np.maximum(tau, 0.0001)

        # --- NLL ---
        log_lik = np.sum(w_arr * (
            np.log(tau) + hg_arr * np.log(lh) - lh + ag_arr * np.log(ma) - ma
        ))
        sum_atk = np.sum(attack)
        penalty = 100.0 * sum_atk ** 2
        nll = -log_lik + penalty

        # --- Gradiente analitico ---
        dtau_dlh = np.zeros_like(lh)
        dtau_dlh[m00] = -ma[m00] * rho
        dtau_dlh[m01] = rho

        dtau_dma = np.zeros_like(ma)
        dtau_dma[m00] = -lh[m00] * rho
        dtau_dma[m10] = rho

        dlogtau_dlh = dtau_dlh / tau
        dlogtau_dma = dtau_dma / tau

        # Contribuicao de cada jogo via lambda_h e mu_a (com chain rule)
        contrib_lh = w_arr * (dlogtau_dlh * lh + hg_arr - lh) * lh_active
        contrib_ma = w_arr * (dlogtau_dma * ma + ag_arr - ma) * ma_active

        grad = np.zeros(2 * n + 2)

        # attack[k]: recebe contrib_lh onde hi==k, contrib_ma onde ai==k
        np.add.at(grad[:n], hi_arr, contrib_lh)
        np.add.at(grad[:n], ai_arr, contrib_ma)

        # defense[k]: recebe contrib_lh onde ai==k, contrib_ma onde hi==k
        np.add.at(grad[n:2*n], ai_arr, contrib_lh)
        np.add.at(grad[n:2*n], hi_arr, contrib_ma)

        # home_adv: recebe contrib_lh de todos os jogos
        grad[2*n] = np.sum(contrib_lh)

        # rho
        dtau_drho = np.zeros_like(lh)
        dtau_drho[m00] = -lh[m00] * ma[m00]
        dtau_drho[m01] = lh[m01]
        dtau_drho[m10] = ma[m10]
        dtau_drho[m11] = -1.0
        grad[2*n + 1] = np.sum(w_arr * dtau_drho / tau)

        # Negar (minimizamos -log_lik) e somar penalty gradient
        grad = -grad
        grad[:n] += 200.0 * sum_atk

        return nll, grad

    def fit(self, matches):
        """
        Ajusta o modelo aos dados historicos. Usa self.cal.xi como time-decay.

        matches: lista de (home_team, away_team, home_goals, away_goals, date_ordinal)
        """
        cup_set = set(WORLD_CUP_TEAM_LIST)
        valid = [(h, a, hg, ag, d) for h, a, hg, ag, d in matches
                 if h in self.team_idx and a in self.team_idx
                 and (h in cup_set or a in cup_set)]

        if not valid:
            print("AVISO: Nenhum jogo valido encontrado para as selecoes do modelo.")
            self._init_from_elo()
            return

        max_date = max(d for _, _, _, _, d in valid)
        weights = [np.exp(-self.cal.xi * (max_date - d)) for _, _, _, _, d in valid]

        # Filtro de qualidade: pesa menos jogos entre adversarios muito desiguais.
        # Usa world_elo (global) porque os jogos incluem selecoes fora da Copa.
        qf = self.cal.dc_quality_filter
        if qf.get("enabled", False):
            thresholds = qf.get("thresholds", [300, 200, 100])
            qf_weights = qf.get("weights", [0.2, 0.5, 0.8, 1.0])
            elo = self.world_elo
            for i, (h, a, _, _, _) in enumerate(valid):
                gap = abs(elo.get(h, 1500) - elo.get(a, 1500))
                qw = qf_weights[-1]  # default: no discount
                for t, w in zip(thresholds, qf_weights):
                    if gap > t:
                        qw = w
                        break
                weights[i] *= qw

        n = self.n_teams
        N_STARTS = 8

        # Pre-computar arrays de indices para o otimizador vectorizado
        hi_arr = np.array([self.team_idx[h] for h, _, _, _, _ in valid], dtype=np.int32)
        ai_arr = np.array([self.team_idx[a] for _, a, _, _, _ in valid], dtype=np.int32)
        hg_arr = np.array([hg for _, _, hg, _, _ in valid], dtype=np.int32)
        ag_arr = np.array([ag for _, _, _, ag, _ in valid], dtype=np.int32)
        w_arr = np.array(weights, dtype=np.float64)

        # Ponto base: zeros para alpha/beta, home_adv=0.25, rho=-0.05
        x0_base = np.zeros(2 * n + 2)
        x0_base[2*n] = 0.25
        x0_base[2*n + 1] = -0.05

        # Gerar N pontos iniciais (seed fixa para reprodutibilidade)
        rng = np.random.RandomState(42)
        starts = [x0_base.copy()]
        for _ in range(N_STARTS - 1):
            noise = np.zeros(2 * n + 2)
            noise[:2*n] = rng.normal(0, 0.05, size=2*n)    # alpha/beta
            noise[2*n] = rng.normal(0, 0.02)                # home_adv
            noise[2*n + 1] = rng.normal(0, 0.02)            # rho
            starts.append(x0_base + noise)

        import time
        t0 = time.time()
        print(f"Otimizando Dixon-Coles com {len(valid)} jogos ({N_STARTS} starts)...")

        best_result = None
        all_nll = []
        for i, x0 in enumerate(starts):
            result = minimize(
                self._nll_and_grad,
                x0,
                args=(hi_arr, ai_arr, hg_arr, ag_arr, w_arr),
                method='L-BFGS-B',
                jac=True,
                options={'maxiter': 500}
            )
            all_nll.append(result.fun)
            if best_result is None or result.fun < best_result.fun:
                best_result = result

        elapsed = time.time() - t0

        self.params = best_result.x
        attack, defense, home_adv, rho = self._unpack_params(best_result.x)

        for i, team in enumerate(self.teams):
            self.attack[team] = attack[i]
            self.defense[team] = defense[i]

        self.home_adv = home_adv
        self.rho = rho
        decay_1yr = np.exp(-self.cal.xi * 365) * 100
        print(f"Multi-start: best NLL={min(all_nll):.2f}, worst={max(all_nll):.2f}, "
              f"range={max(all_nll)-min(all_nll):.2f} ({elapsed:.1f}s)")
        print(f"Otimizacao concluida. Home advantage: {home_adv:.3f}, rho: {rho:.4f}")
        print(f"Time-decay efetivo: jogo de 1 ano atras pesa {decay_1yr:.1f}% de um jogo de hoje")

        self._apply_bayesian_blend()

        tf_cfg = self.cal.tournament_factor
        if isinstance(tf_cfg, dict) and tf_cfg.get("enabled", False):
            self._apply_tournament_factor(valid)

        sq_cfg = self.cal.squad_data
        if isinstance(sq_cfg, dict) and sq_cfg.get("enabled", False):
            self._apply_squad_multiplier()

    def _apply_squad_multiplier(self):
        """
        Ajusta alpha e beta pelo ratio qualidade_convocada / qualidade_ideal.

        Se a escalacao convocada vale menos que o plantel ideal (em valor
        de mercado Transfermarkt), o time fica mais fraco. O smoothing
        via weight evita que o efeito seja 1:1 (o coletivo compensa
        parcialmente ausencias individuais).

        Formula:
            raw_mult = sum(value convocados) / ideal_squad_value
            mult = 1 + weight * (raw_mult - 1)

        Aplicacao em alpha E beta:
            attack[t]  *= mult   # mult<1 = alpha menor = ataque pior
            defense[t] *= mult   # mult<1 = beta mais proximo de zero
                                 #   (beta negativo * mult<1 = menos negativo
                                 #    = defesa pior). Correto.

        Com enabled=false ou convocated_squads vazio, nenhum efeito.
        """
        sq = self.cal.squad_data
        weight = sq.get("weight", 0.5)
        use_top_11 = sq.get("use_top_11", False)
        ideal_values = sq.get("ideal_squad_values", {})
        squads = sq.get("convocated_squads", {})

        adjusted = 0
        for team in self.teams:
            mult = _compute_squad_multiplier(
                team, ideal_values, squads, weight, use_top_11
            )
            if mult != 1.0:
                self.attack[team] *= mult
                self.defense[team] *= mult
                adjusted += 1

        if adjusted:
            print(f"Squad multiplier: {adjusted} selecoes ajustadas "
                  f"(weight={weight}, use_top_11={use_top_11})")

    def _apply_bayesian_blend(self):
        """
        Blend bayesiano de 3 canais: Dixon-Coles + Elo + Transfermarkt.

        Aplica APENAS as 48 selecoes da Copa (WORLD_CUP_TEAM_LIST).
        Selecoes extras (Italy etc.) ficam com alpha/beta do DC cru — nao
        importa porque nao vao ao Monte Carlo.

        elo_mean e tm_mean sao calculados sobre as 48 da Copa (escala
        relativa dentro do torneio, nao global).
        """
        W_DC = self.cal.w_dc
        W_ELO = self.cal.w_elo
        W_TM = self.cal.w_tm
        assert abs(W_DC + W_ELO + W_TM - 1.0) < 1e-6, "Pesos do blend devem somar 1.0"

        cup_teams = WORLD_CUP_TEAM_LIST
        elo = self.cal.elo_ratings  # cup_elo (48 selecoes)
        tm = self.cal.transfermarkt_values
        ad_attack, ad_defense = self.cal.ad_split[0], self.cal.ad_split[1]

        # --- Prior do Elo (media sobre as 48 da Copa) ---
        elo_mean = np.mean([elo[t] for t in cup_teams])
        elo_attack = {}
        elo_defense = {}
        for team in cup_teams:
            e = elo[team]
            strength = (e - elo_mean) / 400.0
            elo_attack[team] = strength * ad_attack
            elo_defense[team] = strength * ad_defense

        # --- Prior do Transfermarkt (media sobre as 48 da Copa) ---
        if self.cal.tm_scale == "sqrt":
            scaled_tm = {t: np.sqrt(max(tm.get(t, 30), 1.0)) for t in cup_teams}
        elif self.cal.tm_scale == "log":
            scaled_tm = {t: np.log(max(tm.get(t, 30), 1.0)) for t in cup_teams}
        else:  # linear
            scaled_tm = {t: float(max(tm.get(t, 30), 1.0)) for t in cup_teams}

        tm_mean = np.mean(list(scaled_tm.values()))
        tm_std = np.std(list(scaled_tm.values())) or 1.0
        tm_attack = {}
        tm_defense = {}
        for team in cup_teams:
            z = (scaled_tm[team] - tm_mean) / tm_std
            strength = z * 0.5
            tm_attack[team] = strength * ad_attack
            tm_defense[team] = strength * ad_defense

        print(f"Blend bayesiano: DC {W_DC:.0%} + Elo {W_ELO:.0%} + TM {W_TM:.0%}")
        for team in cup_teams:
            self.attack[team] = (
                W_DC * self.attack[team]
                + W_ELO * elo_attack[team]
                + W_TM * tm_attack[team]
            )
            self.defense[team] = (
                W_DC * self.defense[team]
                + W_ELO * elo_defense[team]
                + W_TM * tm_defense[team]
            )

    def _apply_tournament_factor(self, matches):
        """
        Ajuste residual pos-blend V2: saldo de gols em torneios curtos,
        com peso maior em fases de mata-mata.

        Formula:
            saldo_rel = saldo_real - saldo_esperado (por fase: grupos/ko)
            TF_bruto = (saldo_rel_grupos + ko_weight * saldo_rel_ko)
                     / (n_grupos + ko_weight * n_ko)
            TF = TF_bruto - media(TF_bruto elegíveis)

        O saldo (gols pro - gols contra) captura performance completa
        (ataque E defesa), e o peso maior em mata-mata (ko_weight=2.0)
        penaliza times que jogam mal sob pressao decisiva.

        Aplicacao one-shot. Nao iterar. Ajuste intencionalmente residual —
        TF usa alpha/beta pos-blend mas nao alimenta de volta. Iterar ate
        convergencia poderia amplificar o ajuste e levar a instabilidade.

        Aplica em alpha E beta com sinais opostos:
            attack[t]  *= (1 + TF * weight)   # TF>0 = ataque melhor
            defense[t] *= (1 - TF * weight)   # TF>0 = defesa melhor
                                               # (beta mais negativo)

        Deteccao de fase (grupos vs mata-mata): heuristica por data.
        Para cada (torneio, ano), os jogos sao ordenados cronologicamente.
        Os ultimos N jogos sao classificados como mata-mata:
            FIFA World Cup: ultimos 16 (R16+QF+SF+3rd+Final)
            UEFA Euro: ultimos 15 (R16+QF+SF+Final)
            Copa America: ultimos 7 (QF+SF+3rd+Final)
        Aproximacao conhecida — o CSV nao tem coluna de fase.

        Configuravel via config.json -> tournament_factor.
        Com enabled=false, nao e chamado.
        """
        tf_cfg = self.cal.tournament_factor
        weight = tf_cfg.get("weight", 0.15)
        ko_weight = tf_cfg.get("knockout_weight", 2.0)
        min_groups = tf_cfg.get("min_games_groups", 3)
        min_ko = tf_cfg.get("min_games_knockout", 2)
        start_year = tf_cfg.get("start_year", 2014)
        tournaments = set(tf_cfg.get("tournaments", []))

        # Carrega jogos separados por fase
        group_matches, ko_matches = self._load_tournament_matches_v2(
            tournaments, start_year
        )

        # Calcula saldo relativo por fase para cada selecao
        team_data: Dict[str, Dict[str, float]] = {}
        for team in self.teams:
            gd = self._calc_goal_diff_residual(team, group_matches)
            kd = self._calc_goal_diff_residual(team, ko_matches)
            team_data[team] = {
                "groups_gd": gd[0], "groups_exp": gd[1], "groups_n": gd[2],
                "ko_gd": kd[0], "ko_exp": kd[1], "ko_n": kd[2],
            }

        # Calcula TF combinado
        team_tf: Dict[str, float] = {}
        team_tf_detail: Dict[str, Dict[str, float]] = {}
        for team in self.teams:
            d = team_data[team]
            has_groups = d["groups_n"] >= min_groups
            has_ko = d["ko_n"] >= min_ko

            if not has_groups and not has_ko:
                team_tf[team] = 0.0
                team_tf_detail[team] = {"groups": 0.0, "ko": 0.0}
                continue

            # Saldo relativo por fase
            gr_rel = (d["groups_gd"] - d["groups_exp"]) if has_groups else 0.0
            ko_rel = (d["ko_gd"] - d["ko_exp"]) if has_ko else 0.0
            n_gr = d["groups_n"] if has_groups else 0
            n_ko = d["ko_n"] if has_ko else 0

            # TF por fase (para output)
            tf_groups = gr_rel / n_gr if n_gr > 0 else 0.0
            tf_ko = ko_rel / n_ko if n_ko > 0 else 0.0

            # TF combinado ponderado
            denom = n_gr + ko_weight * n_ko
            if denom > 0:
                tf_combined = (gr_rel + ko_weight * ko_rel) / denom
            else:
                tf_combined = 0.0

            team_tf[team] = tf_combined
            team_tf_detail[team] = {"groups": tf_groups, "ko": tf_ko}

        # Centraliza
        eligible = [v for v in team_tf.values() if v != 0.0]
        if eligible:
            mean_tf = np.mean(eligible)
            for team in team_tf:
                if team_tf[team] != 0.0:
                    team_tf[team] -= mean_tf

        # Aplica em attack E defense (sinais opostos)
        adjusted = 0
        for team in self.teams:
            tf = team_tf[team]
            if tf != 0.0:
                self.attack[team] *= (1 + tf * weight)
                self.defense[team] *= (1 - tf * weight)
                adjusted += 1

        # Guarda para output
        self._tournament_factors = team_tf
        self._tournament_factors_detail = team_tf_detail

        print(f"Tournament factor V2: {adjusted} selecoes ajustadas "
              f"(weight={weight}, ko_weight={ko_weight}, "
              f"desde {start_year})")

    def _calc_goal_diff_residual(
        self, team: str, matches: list
    ) -> Tuple[float, float, int]:
        """Calcula (saldo_real, saldo_esperado, n_jogos) de um time em matches."""
        gd_real = 0.0
        gd_expected = 0.0
        n = 0
        for h, a, hg, ag in matches:
            if team == h:
                gd_real += (hg - ag)
                if a in self.attack:
                    lam_h = np.exp(self.attack[team] + self.defense[a])
                    lam_a = np.exp(self.attack[a] + self.defense[team])
                    gd_expected += (lam_h - lam_a)
                n += 1
            elif team == a:
                gd_real += (ag - hg)
                if h in self.attack:
                    lam_h = np.exp(self.attack[h] + self.defense[team])
                    lam_a = np.exp(self.attack[team] + self.defense[h])
                    gd_expected += (lam_a - lam_h)
                n += 1
        return gd_real, gd_expected, n

    def _load_tournament_matches_v2(
        self, tournaments: set, start_year: int
    ) -> Tuple[list, list]:
        """
        Carrega jogos de torneios do results.csv, separados em grupos e
        mata-mata via heuristica por data.

        Para cada (torneio, ano), ordena por data e classifica os ultimos
        N jogos como mata-mata:
            FIFA World Cup: ultimos 16
            UEFA Euro: ultimos 15
            Copa America com <=28 jogos: ultimos 7
            Copa America com >28 jogos: ultimos 15
        """
        import csv as csv_mod
        from datetime import datetime
        from collections import defaultdict

        # Numero de jogos de mata-mata por torneio
        KO_COUNTS = {
            "FIFA World Cup": 16,
            "UEFA Euro": 15,
        }
        # Copa America: depende do formato (12 ou 16 times)
        COPA_AM_SMALL = 7   # formato 12 times (<=28 jogos)
        COPA_AM_LARGE = 15  # formato 16 times (>28 jogos)

        csv_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "results.csv"
        )
        if not os.path.exists(csv_path):
            return [], []

        start_ordinal = datetime(start_year, 1, 1).toordinal()

        # Agrupa por (torneio, ano)
        by_edition: Dict[Tuple[str, int], list] = defaultdict(list)
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                t = row.get("tournament", "")
                if t not in tournaments:
                    continue
                try:
                    d = datetime.strptime(row["date"], "%Y-%m-%d")
                    if d.toordinal() < start_ordinal:
                        continue
                    h = _EXTERNAL_TO_MODEL_NAME.get(row["home_team"], row["home_team"])
                    a = _EXTERNAL_TO_MODEL_NAME.get(row["away_team"], row["away_team"])
                    hg = int(row["home_score"])
                    ag = int(row["away_score"])
                    by_edition[(t, d.year)].append((d, h, a, hg, ag))
                except (ValueError, KeyError):
                    continue

        group_matches = []
        ko_matches = []

        for (tourn, year), games in by_edition.items():
            games.sort(key=lambda x: x[0])  # ordena por data

            # Determina quantos jogos sao mata-mata
            if tourn in KO_COUNTS:
                n_ko = KO_COUNTS[tourn]
            elif "Copa" in tourn or "copa" in tourn:
                n_ko = COPA_AM_LARGE if len(games) > 28 else COPA_AM_SMALL
            else:
                n_ko = 0

            n_ko = min(n_ko, len(games))  # safety
            cutoff_idx = len(games) - n_ko

            for i, (_, h, a, hg, ag) in enumerate(games):
                if i < cutoff_idx:
                    group_matches.append((h, a, hg, ag))
                else:
                    ko_matches.append((h, a, hg, ag))

        return group_matches, ko_matches

    def _init_from_elo(self):
        """Fallback quando nao ha dados historicos. Usa apenas Elo pras 48 da Copa."""
        print("Inicializando parametros a partir de Elo ratings...")
        cup_teams = WORLD_CUP_TEAM_LIST
        elo = self.cal.elo_ratings
        ad_attack, ad_defense = self.cal.ad_split[0], self.cal.ad_split[1]
        elo_mean = np.mean([elo[t] for t in cup_teams])
        for team in cup_teams:
            strength = (elo[team] - elo_mean) / 400.0
            self.attack[team] = strength * ad_attack
            self.defense[team] = strength * ad_defense
        self.home_adv = 0.2
        self.rho = -0.04

    def predict_match(self, home: str, away: str, host_adv: float = 0.0) -> dict:
        """
        Prediz distribuicao de probabilidades para um jogo.
        host_adv: vantagem de mando em escala log (0.0 = neutro).
        """
        if not self.attack:
            self._init_from_elo()

        lambda_h = np.exp(self.attack[home] + self.defense[away] + host_adv)
        mu_a = np.exp(self.attack[away] + self.defense[home])

        lambda_h = np.clip(lambda_h, 0.05, 10.0)
        mu_a = np.clip(mu_a, 0.05, 10.0)

        max_goals = 8
        score_matrix = np.zeros((max_goals, max_goals))

        for i in range(max_goals):
            for j in range(max_goals):
                p = (poisson.pmf(i, lambda_h) *
                     poisson.pmf(j, mu_a) *
                     self._tau(i, j, lambda_h, mu_a, self.rho))
                score_matrix[i][j] = max(p, 0)

        total = score_matrix.sum()
        if total > 0:
            score_matrix /= total

        p_home = np.sum(np.tril(score_matrix, -1))
        p_draw = np.sum(np.diag(score_matrix))
        p_away = np.sum(np.triu(score_matrix, 1))

        best = np.unravel_index(np.argmax(score_matrix), score_matrix.shape)

        return {
            "lambdas": (float(lambda_h), float(mu_a)),
            "score_matrix": score_matrix,
            "result_probs": (float(p_home), float(p_draw), float(p_away)),
            "most_likely_score": (int(best[0]), int(best[1])),
            "expected_goals": (float(lambda_h), float(mu_a)),
        }


# =============================================================================
# THIRD-PLACE BRACKET ASSIGNMENT (FIFA 2026 official bracket)
# =============================================================================

# Each R32 match involving a 3rd-place team and the groups it can come from.
_THIRD_PLACE_SLOTS: Dict[str, set] = {
    "3_M74": {"A", "B", "C", "D", "F"},
    "3_M77": {"C", "D", "F", "G", "H"},
    "3_M79": {"C", "E", "F", "H", "I"},
    "3_M80": {"E", "H", "I", "J", "K"},
    "3_M81": {"B", "E", "F", "I", "J"},
    "3_M82": {"A", "E", "H", "I", "J"},
    "3_M85": {"E", "F", "G", "I", "J"},
    "3_M87": {"D", "E", "I", "J", "L"},
}


def _assign_thirds_to_slots(
    best_thirds: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Assign 8 qualified third-place teams to the 8 bracket slots using
    a most-constrained-first greedy approach.

    Args:
        best_thirds: list of 8 dicts with keys "team" and "group".

    Returns:
        dict mapping slot key (e.g. "3_M74") to team name.
    """
    qualified_groups = {t3["group"] for t3 in best_thirds}
    group_to_team = {t3["group"]: t3["team"] for t3 in best_thirds}

    # Build available options per slot (intersection with qualified groups)
    available: Dict[str, set] = {}
    for slot, allowed in _THIRD_PLACE_SLOTS.items():
        available[slot] = allowed & qualified_groups

    assigned: Dict[str, str] = {}
    used_groups: set = set()

    # Greedy: always pick the slot with fewest remaining options first
    for _ in range(8):
        # Filter out already-assigned slots
        remaining = {
            s: opts - used_groups
            for s, opts in available.items()
            if s not in assigned
        }
        if not remaining:
            break
        # Pick most constrained slot
        slot = min(remaining, key=lambda s: len(remaining[s]))
        options = remaining[slot]
        if not options:
            # Fallback: pick any unused group (should not happen with valid data)
            options = qualified_groups - used_groups
        # Pick the first group alphabetically for determinism
        chosen_group = min(options)
        assigned[slot] = group_to_team[chosen_group]
        used_groups.add(chosen_group)

    return assigned


# =============================================================================
# SIMULACAO MONTE CARLO
# =============================================================================

class WorldCupSimulator:
    """Simula a Copa do Mundo 2026 completa via Monte Carlo."""

    def __init__(self, model: DixonColesModel, groups: Dict[str, List[str]],
                 cal: Calibration):
        self.model = model
        self.groups = groups
        self.cal = cal
        self.n_sims = cal.n_sims
        self.all_teams: List[str] = []
        for g in groups.values():
            self.all_teams.extend(g)

    def _simulate_group(self, teams: List[str]):
        """Simula fase de grupos. Retorna standings ordenados."""
        table = {t: {"pts": 0, "gf": 0, "ga": 0, "gd": 0} for t in teams}

        for i in range(len(teams)):
            for j in range(i+1, len(teams)):
                h, a = teams[i], teams[j]
                hg, ag, _ = self._simulate_match_fast(h, a)

                table[h]["gf"] += hg
                table[h]["ga"] += ag
                table[h]["gd"] += (hg - ag)
                table[a]["gf"] += ag
                table[a]["ga"] += hg
                table[a]["gd"] += (ag - hg)

                if hg > ag:
                    table[h]["pts"] += 3
                elif hg < ag:
                    table[a]["pts"] += 3
                else:
                    table[h]["pts"] += 1
                    table[a]["pts"] += 1

        standings = sorted(
            table.keys(),
            key=lambda t: (
                table[t]["pts"],
                table[t]["gd"],
                table[t]["gf"],
                self.cal.elo_ratings[t]
            ),
            reverse=True
        )
        return standings, table

    def simulate_tournament(self):
        """Simula o torneio inteiro uma vez."""
        group_results = {}
        third_place = []
        team_goals: Dict[str, int] = {}  # total gols marcados por time

        for gname, teams in self.groups.items():
            standings, table = self._simulate_group(teams)
            group_results[gname] = {
                "standings": standings,
                "table": table,
            }
            # Acumula gols da fase de grupos
            for t in teams:
                team_goals[t] = team_goals.get(t, 0) + table[t]["gf"]
            if len(standings) >= 3:
                t3 = standings[2]
                third_place.append({
                    "team": t3,
                    "group": gname,
                    "pts": table[t3]["pts"],
                    "gd": table[t3]["gd"],
                    "gf": table[t3]["gf"],
                })

        # Build position lookup: "1A" -> team, "2A" -> team, etc.
        pos = {}
        for gname in sorted(self.groups.keys()):
            s = group_results[gname]["standings"]
            pos["1" + gname] = s[0]
            pos["2" + gname] = s[1]

        third_place.sort(key=lambda x: (x["pts"], x["gd"], x["gf"]), reverse=True)
        best_thirds = third_place[:8]
        best_third_teams = [t3["team"] for t3 in best_thirds]

        # Assign 8 third-place teams to bracket slots using constraint satisfaction
        third_slots = _assign_thirds_to_slots(best_thirds)
        for slot_key, team in third_slots.items():
            pos[slot_key] = team

        # Official FIFA 2026 R32 bracket (16 matches)
        r32_matchups = [
            (pos["2A"], pos["2B"]),           # M73
            (pos["1E"], pos.get("3_M74")),    # M74
            (pos["1F"], pos["2C"]),            # M75
            (pos["1C"], pos["2F"]),            # M76
            (pos["1I"], pos.get("3_M77")),    # M77
            (pos["2E"], pos["2I"]),            # M78
            (pos["1A"], pos.get("3_M79")),    # M79
            (pos["1L"], pos.get("3_M80")),    # M80
            (pos["1D"], pos.get("3_M81")),    # M81
            (pos["1G"], pos.get("3_M82")),    # M82
            (pos["2K"], pos["2L"]),            # M83
            (pos["1H"], pos["2J"]),            # M84
            (pos["1B"], pos.get("3_M85")),    # M85
            (pos["1J"], pos["2H"]),            # M86
            (pos["1K"], pos.get("3_M87")),    # M87
            (pos["2D"], pos["2G"]),            # M88
        ]

        r32_teams = [t for pair in r32_matchups for t in pair]
        rounds_results = {}
        reached = {
            "R32": list(r32_teams),
            "R16": [], "QF": [], "SF": [], "Final": [],
        }

        def _sim_ko(h, a):
            hg, ag, pen = self._simulate_match_fast(h, a, knockout=True)
            team_goals[h] = team_goals.get(h, 0) + hg
            team_goals[a] = team_goals.get(a, 0) + ag
            if pen:
                return pen
            return h if hg > ag else a

        # R32 (16 matches -> 16 winners)
        r32_winners = [_sim_ko(h, a) for h, a in r32_matchups]
        rounds_results["R32"] = [
            (m[0], m[1], w) for m, w in zip(r32_matchups, r32_winners)
        ]
        reached["R16"] = list(r32_winners)

        # R16: pair R32 winners per official bracket
        # M89: W(M74) vs W(M77), M90: W(M73) vs W(M75)
        # M91: W(M76) vs W(M78), M92: W(M79) vs W(M80)
        # M93: W(M83) vs W(M84), M94: W(M81) vs W(M82)
        # M95: W(M86) vs W(M88), M96: W(M85) vs W(M87)
        w = r32_winners  # indices 0-15 correspond to M73-M88
        r16_matchups = [
            (w[1], w[4]),    # M89: W(M74) vs W(M77)
            (w[0], w[2]),    # M90: W(M73) vs W(M75)
            (w[3], w[5]),    # M91: W(M76) vs W(M78)
            (w[6], w[7]),    # M92: W(M79) vs W(M80)
            (w[10], w[11]),  # M93: W(M83) vs W(M84)
            (w[8], w[9]),    # M94: W(M81) vs W(M82)
            (w[13], w[15]),  # M95: W(M86) vs W(M88)
            (w[12], w[14]),  # M96: W(M85) vs W(M87)
        ]
        r16_winners = [_sim_ko(h, a) for h, a in r16_matchups]
        rounds_results["R16"] = [
            (m[0], m[1], w) for m, w in zip(r16_matchups, r16_winners)
        ]
        reached["QF"] = list(r16_winners)

        # QF
        qf_matchups = [
            (r16_winners[0], r16_winners[1]),  # M97: W(M89) vs W(M90)
            (r16_winners[4], r16_winners[5]),  # M98: W(M93) vs W(M94)
            (r16_winners[2], r16_winners[3]),  # M99: W(M91) vs W(M92)
            (r16_winners[6], r16_winners[7]),  # M100: W(M95) vs W(M96)
        ]
        qf_winners = [_sim_ko(h, a) for h, a in qf_matchups]
        rounds_results["QF"] = [
            (m[0], m[1], w) for m, w in zip(qf_matchups, qf_winners)
        ]
        reached["SF"] = list(qf_winners)

        # SF
        sf_matchups = [
            (qf_winners[0], qf_winners[1]),  # M101: W(M97) vs W(M98)
            (qf_winners[2], qf_winners[3]),  # M102: W(M99) vs W(M100)
        ]
        sf_winners = [_sim_ko(h, a) for h, a in sf_matchups]
        rounds_results["SF"] = [
            (m[0], m[1], w) for m, w in zip(sf_matchups, sf_winners)
        ]
        reached["Final"] = list(sf_winners)

        # Final
        final_matchup = (sf_winners[0], sf_winners[1])
        champion = _sim_ko(final_matchup[0], final_matchup[1])
        rounds_results["Final"] = [
            (final_matchup[0], final_matchup[1], champion)
        ]
        return {
            "groups": group_results,
            "champion": champion,
            "team_goals": team_goals,
            "rounds": rounds_results,
            "reached": reached,
            "best_thirds": best_third_teams,
        }

    def _precache_lambdas(self):
        """Pre-calcula todos os lambdas possiveis para evitar recalculo."""
        self._lambda_cache = {}
        teams = self.all_teams
        ha_boost = np.exp(self.cal.wc_host_adv)

        for t1 in teams:
            for t2 in teams:
                if t1 != t2:
                    pred = self.model.predict_match(t1, t2, host_adv=0.0)
                    lh, la = pred["lambdas"]

                    home_team = host_team_for_match(t1, t2)
                    if home_team == t1:
                        lh *= ha_boost
                    elif home_team == t2:
                        la *= ha_boost

                    if t1 in self.cal.expert_adjustments:
                        lh *= self.cal.expert_adjustments[t1].get("attack_mult", 1.0)
                    if t2 in self.cal.expert_adjustments:
                        la *= self.cal.expert_adjustments[t2].get("attack_mult", 1.0)
                    self._lambda_cache[(t1, t2)] = (lh, la)

    def _simulate_match_fast(self, home: str, away: str, knockout: bool = False):
        """Versao otimizada usando cache de lambdas."""
        lh, la = self._lambda_cache[(home, away)]
        hg = np.random.poisson(lh)
        ag = np.random.poisson(la)

        pen_winner = None
        if knockout and hg == ag:
            hg += np.random.poisson(lh / 3)
            ag += np.random.poisson(la / 3)
            if hg == ag:
                elo_h = self.cal.elo_ratings[home]
                elo_a = self.cal.elo_ratings[away]
                p = np.clip(0.5 + (elo_h - elo_a) / 4000, 0.35, 0.65)
                pen_winner = home if np.random.random() < p else away
        return hg, ag, pen_winner

    def run_simulations(self, progress_callback=None):
        """
        Roda N simulacoes e agrega resultados.
        progress_callback: opcional, funcao chamada com (sim_atual, n_sims) a cada ~5%.
                           Usado pelo Streamlit pra barra de progresso.
        """
        print(f"\nRodando {self.n_sims:,} simulacoes Monte Carlo...")
        print(f"Pre-calculando lambdas...")
        self._precache_lambdas()

        # Pre-computa dados do scorer model (se habilitado)
        scorer_data = precompute_scorer_data(self.cal)
        if scorer_data:
            print(f"Scorer model: {len(scorer_data['teams'])} times com player_stats")

        print(f"Simulando...\n")

        team_stats = {t: {
            "group_1st": 0, "group_2nd": 0, "group_3rd_qual": 0,
            "r32": 0, "r16": 0, "qf": 0, "sf": 0, "final": 0, "champion": 0,
        } for t in self.all_teams}

        # Distribuicao conjunta top-2 por grupo: joint[g][i, j] = contagem de
        # simulacoes onde groups[g][i] foi 1o e groups[g][j] foi 2o.
        # Usado por optimal_group_bet para capturar correlacao entre palpites.
        group_top2_joint = {
            gname: np.zeros((len(teams), len(teams)), dtype=np.int64)
            for gname, teams in self.groups.items()
        }

        # Scorer tracking: contagem de vezes que cada jogador foi artilheiro
        scorer_artilheiro_counts: Dict[str, int] = {}
        scorer_goal_totals: Dict[str, int] = {}
        rng = np.random.RandomState()  # para reprodutibilidade do scorer

        import time
        start = time.time()
        update_every = max(1, self.n_sims // 20)

        for sim in range(self.n_sims):
            if (sim + 1) % update_every == 0:
                pct = (sim + 1) / self.n_sims * 100
                elapsed = time.time() - start
                rate = (sim + 1) / elapsed
                remaining = (self.n_sims - sim - 1) / rate
                filled = int(30 * (sim + 1) / self.n_sims)
                bar = "█" * filled + "░" * (30 - filled)
                print(f"\r  [{bar}] {pct:5.1f}%  ({sim+1:,}/{self.n_sims:,})  ~{remaining:.0f}s restantes", end="", flush=True)
                if progress_callback is not None:
                    progress_callback(sim + 1, self.n_sims)

            result = self.simulate_tournament()

            for gname, gres in result["groups"].items():
                s = gres["standings"]
                if len(s) >= 1:
                    team_stats[s[0]]["group_1st"] += 1
                if len(s) >= 2:
                    team_stats[s[1]]["group_2nd"] += 1
                    teams_list = self.groups[gname]
                    idx_1 = teams_list.index(s[0])
                    idx_2 = teams_list.index(s[1])
                    group_top2_joint[gname][idx_1, idx_2] += 1

            for t3 in result.get("best_thirds", []):
                team_stats[t3]["group_3rd_qual"] += 1

            if result["champion"]:
                team_stats[result["champion"]]["champion"] += 1

            key_map = {"R32": "r32", "R16": "r16", "QF": "qf",
                       "SF": "sf", "Final": "final"}
            for round_name, teams_in_round in result.get("reached", {}).items():
                if round_name in key_map:
                    for t in teams_in_round:
                        team_stats[t][key_map[round_name]] += 1

            # Scorer model: atribuir gols a jogadores e encontrar artilheiro
            if scorer_data:
                noisy_probs = sample_sim_noise(scorer_data, rng)
                sim_goals: Dict[str, int] = {}  # player -> goals nesta sim

                for team, n_goals in result.get("team_goals", {}).items():
                    if n_goals <= 0:
                        continue
                    player_goals = sample_goals_for_team(
                        team, n_goals, scorer_data, noisy_probs, rng
                    )
                    for player, g in player_goals.items():
                        sim_goals[player] = sim_goals.get(player, 0) + g
                        scorer_goal_totals[player] = (
                            scorer_goal_totals.get(player, 0) + g
                        )

                if sim_goals:
                    top_scorer = max(sim_goals, key=sim_goals.get)
                    scorer_artilheiro_counts[top_scorer] = (
                        scorer_artilheiro_counts.get(top_scorer, 0) + 1
                    )

        elapsed = time.time() - start
        print(f"\r  [{'█' * 30}] 100.0%  Concluido em {elapsed:.1f}s" + " " * 20)

        for team in self.all_teams:
            for key in team_stats[team]:
                team_stats[team][key] = round(
                    team_stats[team][key] / self.n_sims * 100, 2
                )

        # Normaliza matriz conjunta e guarda como atributo para consumo
        # posterior por optimal_group_bet (evita quebrar a assinatura publica).
        self.group_top2_joint = {
            gname: counts.astype(np.float64) / self.n_sims
            for gname, counts in group_top2_joint.items()
        }

        # Guarda resultados do scorer model
        if scorer_data and scorer_artilheiro_counts:
            # Normaliza pra probabilidades
            self.scorer_results = {
                "artilheiro_probs": {
                    p: round(c / self.n_sims * 100, 2)
                    for p, c in sorted(scorer_artilheiro_counts.items(),
                                       key=lambda x: x[1], reverse=True)
                },
                "avg_goals": {
                    p: round(scorer_goal_totals[p] / self.n_sims, 2)
                    for p in scorer_artilheiro_counts
                },
            }
        else:
            self.scorer_results = None

        return team_stats


# =============================================================================
# PIPELINE DE DADOS
# =============================================================================

def download_historical_data(target_path: Optional[str] = None):
    """Baixa dados historicos. Roda uma vez."""
    try:
        import urllib.request
        url = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
        if target_path is None:
            target_path = os.path.join(os.path.dirname(__file__), "results.csv")
        if not os.path.exists(target_path):
            print(f"Baixando dados historicos de {url}...")
            urllib.request.urlretrieve(url, target_path)
            print(f"Salvo em {target_path}")
        return target_path
    except Exception as e:
        print(f"Erro ao baixar dados: {e}")
        return None


def load_matches(filepath: str):
    """Carrega jogos do CSV, aplicando mapeamento de nomes."""
    from datetime import datetime
    matches = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                date = datetime.strptime(row['date'], '%Y-%m-%d')
                date_ordinal = date.toordinal()
                home = _EXTERNAL_TO_MODEL_NAME.get(row['home_team'], row['home_team'])
                away = _EXTERNAL_TO_MODEL_NAME.get(row['away_team'], row['away_team'])
                hg = int(row['home_score'])
                ag = int(row['away_score'])
                matches.append((home, away, hg, ag, date_ordinal))
            except (ValueError, KeyError):
                continue
    return matches


# =============================================================================
# PIPELINE COMPLETO (ponto de entrada unico)
# =============================================================================

def run_full_pipeline(cal: Calibration,
                      csv_path: Optional[str] = None,
                      verbose: bool = True,
                      progress_callback=None) -> Dict[str, Any]:
    """
    Roda o pipeline completo: calibracao + previsoes + Monte Carlo.

    Parametros:
        cal: Calibration
        csv_path: caminho pra results.csv. Default = ./results.csv
        verbose: se True, imprime progresso no terminal
        progress_callback: funcao(sim_atual, n_sims) pra progresso do MC

    Retorna dict com:
        predictions: dict {jogo: {home, away, group, score_modal, score_ev, ...}}
        simulation_stats: dict {time: {group_1st, group_2nd, r32, ..., champion}}
        model_params: dict {attack, defense, home_adv, rho}
        team_params: lista ordenada de (team, attack, defense, strength, elo, confed)
        calibration: dict (cal serializada)
        groups: dict (para referencia)
    """
    errors = cal.validate()
    if errors:
        raise ValueError(f"Calibration invalida: {errors}")

    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.csv")

    # Carrega Elos: universo amplo (todas as ~244 selecoes) para DC fitting,
    # e subconjunto das 48 da Copa para blend/MC/output.
    world_elo = load_world_elo()
    cup_elo = load_world_cup_elo(world_elo)

    # Injeta Elos no cal para que o resto do pipeline os use
    cal.elo_ratings = cup_elo

    # Modelo DC recebe universo AMPLO (maximiza jogos no fitting)
    all_teams = list(world_elo.keys())
    model = DixonColesModel(all_teams, cal, world_elo=world_elo)

    # Carrega dados e calibra
    if os.path.exists(csv_path):
        if verbose:
            print(f"\nCarregando dados de {csv_path}...")
        matches = load_matches(csv_path)
        if verbose:
            print(f"Total de jogos carregados: {len(matches):,}")

        from datetime import datetime
        cutoff_dt = datetime.strptime(cal.date_cutoff, "%Y-%m-%d")
        cutoff = cutoff_dt.toordinal()
        recent = [m for m in matches if m[4] >= cutoff]
        if verbose:
            print(f"Jogos desde {cal.date_cutoff}: {len(recent):,}")

        model.fit(recent)
    else:
        if verbose:
            print(f"\nDados historicos nao encontrados em {csv_path}.")
            print("Usando Elo ratings como base.")
        model._init_from_elo()

    # Tabela de parametros (apenas 48 da Copa, nao as ~244 do universo DC)
    team_params = []
    for team in WORLD_CUP_TEAM_LIST:
        atk = model.attack.get(team, 0)
        dfn = model.defense.get(team, 0)
        strength = atk - dfn
        elo = cup_elo[team]
        confed = CONFEDERATIONS.get(team, "?")
        team_params.append({
            "team": team, "attack": atk, "defense": dfn,
            "strength": strength, "elo": elo, "confederation": confed,
        })
    team_params.sort(key=lambda x: x["strength"], reverse=True)

    # Previsoes por jogo
    all_predictions = {}
    for gname in sorted(GROUPS.keys()):
        teams = GROUPS[gname]
        for i in range(len(teams)):
            for j in range(i+1, len(teams)):
                h, a = teams[i], teams[j]
                home_team = host_team_for_match(h, a)
                if home_team == h:
                    pred = model.predict_match(h, a, host_adv=cal.wc_host_adv)
                elif home_team == a:
                    p_inv = model.predict_match(a, h, host_adv=cal.wc_host_adv)
                    pred = {
                        "lambdas": (p_inv["lambdas"][1], p_inv["lambdas"][0]),
                        "score_matrix": p_inv["score_matrix"].T,
                        "result_probs": (p_inv["result_probs"][2],
                                         p_inv["result_probs"][1],
                                         p_inv["result_probs"][0]),
                        "most_likely_score": (p_inv["most_likely_score"][1],
                                              p_inv["most_likely_score"][0]),
                        "expected_goals": (p_inv["lambdas"][1],
                                           p_inv["lambdas"][0]),
                    }
                else:
                    pred = model.predict_match(h, a, host_adv=0.0)

                ph, pd, pa = pred["result_probs"]
                ms = pred["most_likely_score"]
                ev_score, ev_pts = ev_optimal_score(pred["score_matrix"], knockout=False)
                lh, la = pred["lambdas"]
                sb = smart_baseline_score(pred["score_matrix"], pred["lambdas"])

                match_key = f"{h} vs {a}"
                all_predictions[match_key] = {
                    "home": h, "away": a,
                    "group": gname,
                    "score_modal": f"{ms[0]}x{ms[1]}",
                    "score_ev": f"{ev_score[0]}x{ev_score[1]}",
                    "score_smart": f"{sb[0]}x{sb[1]}",
                    "ev_points": round(ev_pts, 2),
                    "home_win": round(ph * 100, 1),
                    "draw": round(pd * 100, 1),
                    "away_win": round(pa * 100, 1),
                    "home_xg": round(lh, 2),
                    "away_xg": round(la, 2),
                }

    # Monte Carlo
    simulator = WorldCupSimulator(model, GROUPS, cal)
    stats = simulator.run_simulations(progress_callback=progress_callback)

    # Apostas EV-optimal sobre saidas do MC
    group_bets = {}
    for gname, teams in GROUPS.items():
        joint = simulator.group_top2_joint[gname]
        group_bets[gname] = optimal_group_bet(joint, teams)

    champion_probs = {t: s["champion"] / 100.0 for t, s in stats.items()}
    champion_bet = optimal_champion_bet(champion_probs)

    # 3os colocados induzidos pelos placares EV-optimal (diagnostico)
    induced = induced_third_places(all_predictions, GROUPS)
    thirds_ev = third_places_ev(induced["top8_induced"], stats)
    third_places = {
        "thirds_per_group": induced["thirds_per_group"],
        "top8_induced": induced["top8_induced"],
        "bottom4_eliminated": induced["bottom4_eliminated"],
        "ev_points": thirds_ev["ev_points"],
        "per_team": thirds_ev["per_team"],
    }

    output = {
        "predictions": all_predictions,
        "simulation_stats": stats,
        "group_bets": group_bets,
        "champion_bet": champion_bet,
        "third_places": third_places,
        "model_params": {
            "attack": {t: model.attack[t] for t in WORLD_CUP_TEAM_LIST},
            "defense": {t: model.defense[t] for t in WORLD_CUP_TEAM_LIST},
            "home_adv": float(model.home_adv),
            "rho": float(model.rho),
        },
        "team_params": team_params,
        "calibration": cal.to_dict(),
        "groups": GROUPS,
        "elo_ratings": cup_elo,
        "tournament_factors": getattr(model, "_tournament_factors", None),
        "tournament_factors_detail": getattr(model, "_tournament_factors_detail", None),
        "scorer_results": getattr(simulator, "scorer_results", None),
        "_model": model,
    }

    return output


# =============================================================================
# CLI / IMPRESSAO (mantem comportamento terminal)
# =============================================================================

def print_results(output: Dict[str, Any]) -> None:
    """Imprime o output do pipeline no terminal (formato original)."""
    cal = Calibration.from_dict(output["calibration"])

    print("\n" + "=" * 70)
    print("  PARAMETROS DO MODELO (Ataque / Defesa por selecao)")
    print("=" * 70)
    print(f"\n  {'Selecao':<25} {'Ataque':>8} {'Defesa':>8} {'Forca':>8}  {'Elo':>6}  {'Confed':<10}")
    print("  " + "-" * 75)

    for p in output["team_params"]:
        flag = ""
        if p["attack"] > 0.4 and p["defense"] > -0.1:
            flag = "  << ATAQUE INFLADO?"
        elif p["attack"] < 0 and p["elo"] > 1900:
            flag = "  << ATAQUE BAIXO?"
        print(f"  {p['team']:<25} {p['attack']:>+8.3f} {p['defense']:>+8.3f} "
              f"{p['strength']:>8.3f}  {p['elo']:>6}  {p['confederation']:<10}{flag}")

    print("\n" + "=" * 70)
    print("  PREVISOES - FASE DE GRUPOS")
    print("=" * 70)

    predictions = output["predictions"]
    # Agrupa por grupo pra manter a ordem de apresentacao original
    by_group: Dict[str, List[Tuple[str, dict]]] = {}
    for key, pred in predictions.items():
        by_group.setdefault(pred["group"], []).append((key, pred))

    for gname in sorted(by_group.keys()):
        print(f"\n--- GRUPO {gname} ---")
        for key, pred in by_group[gname]:
            modal_str = pred["score_modal"]
            ev_str = pred["score_ev"]
            tag = "" if modal_str == ev_str else f" [modal: {modal_str}]"
            h, a = pred["home"], pred["away"]
            result_str = f"  {h} {ev_str} {a}"
            prob_str = f"  [{pred['home_win']:.0f}%/{pred['draw']:.0f}%/{pred['away_win']:.0f}%]"
            ev_print = f"  EV={pred['ev_points']:.1f}"
            print(f"{result_str:45s} {prob_str} {ev_print}{tag}")

    # Top 20 titulo
    print("\n" + "=" * 70)
    print("  SIMULACAO MONTE CARLO")
    print("=" * 70)
    print("\n--- TOP 20 FAVORITOS AO TITULO ---")
    print(f"{'Pos':>3}  {'Selecao':<25} {'Titulo':>7}  {'Final':>7}  {'Semi':>7}  {'Quartas':>7}")
    print("-" * 70)

    stats = output["simulation_stats"]
    ranked = sorted(stats.items(), key=lambda x: x[1]["champion"], reverse=True)
    for pos, (team, s) in enumerate(ranked[:20], 1):
        print(f"{pos:3d}. {team:<25} {s['champion']:>6.1f}% {s['final']:>6.1f}% "
              f"{s['sf']:>6.1f}% {s['qf']:>6.1f}%")

    # Classificacao por grupo
    print("\n--- PROBABILIDADE DE CLASSIFICACAO POR GRUPO ---")
    for gname in sorted(GROUPS.keys()):
        teams = GROUPS[gname]
        print(f"\nGrupo {gname}:")
        print(f"  {'Selecao':<25} {'1o':>6} {'2o':>6} {'3o(Q)':>6} {'Elim':>6}")
        for team in sorted(teams, key=lambda t: stats[t]["group_1st"], reverse=True):
            s = stats[team]
            elim = 100 - s["group_1st"] - s["group_2nd"] - s.get("group_3rd_qual", 0)
            print(f"  {team:<25} {s['group_1st']:>5.1f}% {s['group_2nd']:>5.1f}% "
                  f"{s.get('group_3rd_qual', 0):>5.1f}% {elim:>5.1f}%")

    # Apostas recomendadas
    print("\n" + "=" * 70)
    print("  APOSTAS RECOMENDADAS - FASE DE GRUPOS (EV-optimal)")
    print("=" * 70)
    print(f"\n{'Jogo':<40} {'Placar':>8} {'EV pts':>8}  {'Modal':>7}")
    print("-" * 70)
    for key, pred in sorted(predictions.items(), key=lambda x: x[1]["group"]):
        modal = pred["score_modal"]
        ev = pred["score_ev"]
        modal_tag = modal if modal != ev else "="
        print(f"  {key:<38} {ev:>8} {pred['ev_points']:>8.1f}  {modal_tag:>7}")

    # Apostas de classificacao dos grupos (1o / 2o)
    group_bets = output.get("group_bets", {})
    if group_bets:
        print("\n" + "=" * 70)
        print("  APOSTAS DE CLASSIFICACAO DOS GRUPOS (EV-optimal, 1o/2o)")
        print("=" * 70)
        print(f"\n{'Grupo':<6} {'1o':<22} {'2o':<22} {'EV pts':>8}")
        print("-" * 70)
        total_ev_groups = 0.0
        for gname in sorted(group_bets.keys()):
            gb = group_bets[gname]
            total_ev_groups += gb["ev_points"]
            print(f"  {gname:<4} {gb['bet_1st']:<22} {gb['bet_2nd']:<22} "
                  f"{gb['ev_points']:>8.2f}")
        print("-" * 70)
        print(f"  Total EV classificacao: {total_ev_groups:.2f} pts "
              f"(max teorico 240)")

    # Aposta de campeao
    champ_bet = output.get("champion_bet")
    if champ_bet and champ_bet.get("bet"):
        print("\n" + "=" * 70)
        print("  APOSTA DE CAMPEAO (EV-optimal)")
        print("=" * 70)
        print(f"\n  Time: {champ_bet['bet']}")
        print(f"  P(campeao): {champ_bet['p_champion']*100:.2f}%")
        print(f"  EV: {champ_bet['ev_points']:.2f} pts (max 25)")

    # 3os colocados induzidos (diagnostico)
    tp = output.get("third_places")
    if tp:
        print("\n" + "=" * 70)
        print("  TERCEIROS COLOCADOS INDUZIDOS (diagnostico, nao otimiza)")
        print("=" * 70)
        print("\n  Dos 12 3os induzidos pelos placares EV-optimal, o sistema")
        print("  selecionaria os 8 melhores como nossos palpites. A pontuacao")
        print("  vem de P(cada um ser 3o real qualificado) x 5 pts (manual pag 4).")
        print(f"\n  {'Time':<22} {'P(3o qual)':>10}  {'EV pts':>8}")
        print("  " + "-" * 45)
        for entry in tp["per_team"]:
            print(f"  {entry['team']:<22} {entry['p_3rd_qual']*100:>9.2f}%  "
                  f"{entry['ev']:>8.2f}")
        print("  " + "-" * 45)
        print(f"  Total EV 3os: {tp['ev_points']:.2f} pts (max 40)")
        if tp.get("bottom4_eliminated"):
            print(f"\n  Nao selecionados (3os de grupos fracos): "
                  f"{', '.join(tp['bottom4_eliminated'])}")

    # Tournament factors (so imprime se habilitado)
    cal_tf = cal.tournament_factor if isinstance(cal.tournament_factor, dict) else {}
    tfs = output.get("tournament_factors")
    tfs_detail = output.get("tournament_factors_detail")
    if tfs and cal_tf.get("enabled", False):
        print("\n" + "=" * 70)
        print("  TOURNAMENT FACTOR V2 (saldo de gols, peso em mata-mata)")
        print("=" * 70)
        if tfs_detail:
            print(f"\n  {'Selecao':<22} {'Grupos':>8} {'Mata-Mata':>10} "
                  f"{'TF Final':>9}  {'Efeito'}")
            print("  " + "-" * 65)
            sorted_tfs = sorted(tfs.items(), key=lambda x: x[1], reverse=True)
            for team, tf in sorted_tfs:
                if tf == 0.0:
                    continue
                det = tfs_detail.get(team, {})
                gr = det.get("groups", 0.0)
                ko = det.get("ko", 0.0)
                label = "over" if tf > 0 else "under"
                print(f"  {team:<22} {gr:>+8.3f} {ko:>+10.3f} "
                      f"{tf:>+9.3f}  {label}")
        else:
            print(f"\n  {'Selecao':<25} {'TF':>8}  {'Efeito'}")
            print("  " + "-" * 55)
            sorted_tfs = sorted(tfs.items(), key=lambda x: x[1], reverse=True)
            for team, tf in sorted_tfs:
                if tf == 0.0:
                    continue
                label = "over" if tf > 0 else "under"
                print(f"  {team:<25} {tf:>+8.3f}  {label}")
        n_zero = sum(1 for _, v in tfs.items() if v == 0.0)
        if n_zero:
            print(f"\n  ({n_zero} selecoes com TF=0: amostra insuficiente)")

    # Top scorer model
    scorer = output.get("scorer_results")
    if scorer:
        print("\n" + "=" * 70)
        print("  TOP 20 CANDIDATOS A ARTILHEIRO")
        print("=" * 70)
        print(f"\n  {'RK':>3}  {'Jogador':<25} {'P(Artilheiro)':>13}  {'Gols médios':>11}")
        print("  " + "-" * 58)
        artilheiro = scorer["artilheiro_probs"]
        avg_goals = scorer["avg_goals"]
        for i, (player, prob) in enumerate(artilheiro.items(), 1):
            if i > 20:
                break
            avg_g = avg_goals.get(player, 0)
            print(f"  {i:3d}. {player:<25} {prob:>12.1f}%  {avg_g:>11.1f}")


def save_results_json(output: Dict[str, Any], path: str) -> None:
    """Salva output em JSON (formato compativel com versao anterior)."""
    # Remove score_matrix (numpy array) pra serializar
    clean = {
        "predictions": output["predictions"],
        "simulation_stats": output["simulation_stats"],
        "group_bets": output.get("group_bets", {}),
        "champion_bet": output.get("champion_bet"),
        "third_places": output.get("third_places"),
        "model_params": output["model_params"],
        "elo_ratings": output["elo_ratings"],
        "groups": output["groups"],
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(clean, f, indent=2, ensure_ascii=False, default=str)


def main():
    print("=" * 70)
    print("  BOLAO 2026 - Modelo de Previsao Copa do Mundo FIFA 2026")
    print("  Arquitetura: Dixon-Coles + Monte Carlo")
    print("=" * 70)

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    cal = load_config(config_path)

    output = run_full_pipeline(cal)
    print_results(output)

    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bolao2026_results.json")
    save_results_json(output, json_path)
    print(f"\nResultados exportados para {json_path}")


if __name__ == "__main__":
    import sys
    if "--download" in sys.argv:
        download_historical_data()
    main()
    

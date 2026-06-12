"""
Funcoes de pontuacao dos 3 boloes (modulo leve, sem dependencias pesadas).

Validado identico as funcoes de referencia do repo (bolao2026.bolao_points,
bolao_cli.pontuacao.bolao_cli_points e gen_polla_palpites.polla_points) em
todas as 2401 combinacoes de placar 0..6 x 0..6 — ver test_scoring.py.

Regras:
  Zap  (grupos / mata-mata):
      exato 10/15 | dif 6/9 | gols vencedor 5/8 | gols perdedor 4/6 |
      so vencedor 3/5 | empate exato 10/15 | empate placar errado 6/9 | resto 0
  Cli  (todas as fases, mesmos valores):
      exato 5 (+1 se 5 gols totais, +2 se >=6) | empate certo placar errado 3 |
      vitoria certa placar errado 2 | resto 0
  Polla (todas as fases, mesmos valores):
      exato 3 | so vencedor/empate certo 1 | resto 0
"""
from __future__ import annotations

from typing import Tuple

Score = Tuple[int, int]

_ZAP_GROUP = {"exact": 10, "diff": 6, "winner_goals": 5, "loser_goals": 4,
              "winner_only": 3, "draw_exact": 10, "draw_wrong": 6}
_ZAP_KO = {"exact": 15, "diff": 9, "winner_goals": 8, "loser_goals": 6,
           "winner_only": 5, "draw_exact": 15, "draw_wrong": 9}


def zap_points(bet: Score, actual: Score, knockout: bool = False) -> int:
    """Pontos do Bolao do Zap (tiers mutuamente exclusivos, pega o maior)."""
    bh, ba = bet
    rh, ra = actual
    t = _ZAP_KO if knockout else _ZAP_GROUP
    bet_draw, res_draw = bh == ba, rh == ra
    if bet_draw:
        if not res_draw:
            return 0
        return t["draw_exact"] if bh == rh else t["draw_wrong"]
    if res_draw or (bh > ba) != (rh > ra):
        return 0
    if (bh, ba) == (rh, ra):
        return t["exact"]
    if (bh - ba) == (rh - ra):
        return t["diff"]
    if max(bh, ba) == max(rh, ra):
        return t["winner_goals"]
    if min(bh, ba) == min(rh, ra):
        return t["loser_goals"]
    return t["winner_only"]


def cli_points(bet: Score, actual: Score, knockout: bool = False) -> int:
    """Pontos do Bolao do Cli (mesmos valores em todas as fases)."""
    bh, ba = bet
    rh, ra = actual
    if bh == rh and ba == ra:
        total = rh + ra
        return 5 + (2 if total >= 6 else 1 if total == 5 else 0)
    if bh == ba and rh == ra:
        return 3
    if bh != ba and rh != ra and (bh > ba) == (rh > ra):
        return 2
    return 0


def polla_points(bet: Score, actual: Score, knockout: bool = False) -> int:
    """Pontos da Polla 26 (exato 3, vencedor/empate certo 1)."""
    bh, ba = bet
    rh, ra = actual
    if (bh, ba) == (rh, ra):
        return 3
    if ((bh > ba) - (bh < ba)) == ((rh > ra) - (rh < ra)):
        return 1
    return 0


BOLOES = {"Zap": zap_points, "Cli": cli_points, "Polla": polla_points}

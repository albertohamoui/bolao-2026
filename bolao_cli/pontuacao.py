"""
Bolao do Cli — funcao de pontuacao (apenas placares, 90 min).

Regulamento:
  Resultado Certo (exato):     5 pts
  Empate Incerto (errou placar): 3 pts
  Vitoria Incerta (errou placar): 2 pts
  Bonus: jogo com 5 gols totais +1, 6+ gols +2 (so se resultado certo)
  Errou tudo: 0 pts

  Limite: max 40 resultados iguais nos 104 jogos.
"""

from typing import Tuple


def bolao_cli_points(bet: Tuple[int, int], actual: Tuple[int, int]) -> int:
    """Pontos do Bolao do Cli para um jogo."""
    bh, ba = bet
    rh, ra = actual

    # Resultado certo (placar exato)
    if bh == rh and ba == ra:
        pts = 5
        total_goals = rh + ra
        if total_goals >= 6:
            pts += 2
        elif total_goals == 5:
            pts += 1
        return pts

    bet_draw = (bh == ba)
    result_draw = (rh == ra)

    # Empate incerto
    if bet_draw and result_draw:
        return 3

    # Vitoria incerta (acertou vencedor, errou placar)
    if not bet_draw and not result_draw:
        if (bh > ba) == (rh > ra):
            return 2

    return 0

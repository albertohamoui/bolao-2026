"""
Garante que scripts/scoring.py (usado pelo job de email) e identico as funcoes
de pontuacao de referencia do repo, em todas as combinacoes de placar.

Se algum regulamento mudar, este teste quebra e forca sincronizar as duas
implementacoes.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "bolao_cli"))

from bolao2026 import bolao_points  # noqa: E402
from pontuacao import bolao_cli_points  # noqa: E402
from scoring import cli_points, polla_points, zap_points  # noqa: E402

SCORES = [(h, a) for h in range(7) for a in range(7)]


@pytest.mark.parametrize("bet", SCORES)
def test_zap_matches_reference_group(bet):
    for actual in SCORES:
        assert zap_points(bet, actual, knockout=False) == bolao_points(
            bet, actual, knockout=False)


@pytest.mark.parametrize("bet", SCORES)
def test_zap_matches_reference_knockout(bet):
    for actual in SCORES:
        assert zap_points(bet, actual, knockout=True) == bolao_points(
            bet, actual, knockout=True)


@pytest.mark.parametrize("bet", SCORES)
def test_cli_matches_reference(bet):
    for actual in SCORES:
        assert cli_points(bet, actual) == bolao_cli_points(bet, actual)


@pytest.mark.parametrize("bet", SCORES)
def test_cli_knockout_same_as_group(bet):
    # Bolao do Cli usa os mesmos valores em todas as fases.
    for actual in SCORES:
        assert cli_points(bet, actual, knockout=True) == cli_points(bet, actual)


@pytest.mark.parametrize("bet", SCORES)
def test_polla_rules(bet):
    for actual in SCORES:
        expected = 3 if bet == actual else (
            1 if (bet[0] > bet[1]) - (bet[0] < bet[1]) ==
                 (actual[0] > actual[1]) - (actual[0] < actual[1]) else 0)
        assert polla_points(bet, actual) == expected

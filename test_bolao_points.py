"""
Testes unitarios de bolao_points vs manual oficial (bolaodozap.com pagina 4).

Cobre 14 tiers: 7 fase de grupos + 7 mata-mata, mais casos de zero e
sanity check de precedencia (tier mais alto que aplica).

Uso:
    python test_bolao_points.py

Saida esperada: "OK (N testes)" em < 1s.
"""

import sys
from bolao2026 import bolao_points


FAILURES = []


def check(name, got, want):
    if got == want:
        print(f"  OK  {name}: {got}")
    else:
        FAILURES.append((name, got, want))
        print(f"  FAIL {name}: esperado {want}, obtido {got}")


def run():
    print("\n=== Fase de Grupos (7 tiers) ===")
    # G1: placar exato com vitoria. Real 2x1, aposta 2x1.
    check("G1 placar exato",
          bolao_points((2, 1), (2, 1), knockout=False), 10)
    # G2: diferenca certa. Real 2x1 (+1), aposta 3x2 (+1).
    check("G2 diferenca de gols",
          bolao_points((3, 2), (2, 1), knockout=False), 6)
    # G3: gols do vencedor. Exemplo do manual: real 2x1, aposta 2x0.
    check("G3 gols do vencedor",
          bolao_points((2, 0), (2, 1), knockout=False), 5)
    # G4: gols do perdedor. Exemplo do manual: real 2x1, aposta 3x1.
    check("G4 gols do perdedor",
          bolao_points((3, 1), (2, 1), knockout=False), 4)
    # G5: so o vencedor. Real 2x1, aposta 3x0 (so acertou que home venceu).
    check("G5 so o vencedor",
          bolao_points((3, 0), (2, 1), knockout=False), 3)
    # G6: empate exato. Real 1x1, aposta 1x1.
    check("G6 empate exato",
          bolao_points((1, 1), (1, 1), knockout=False), 10)
    # G7: empate placar errado. Exemplo do manual: real 0x0, aposta 1x1.
    check("G7 empate placar errado",
          bolao_points((1, 1), (0, 0), knockout=False), 6)

    print("\n=== Mata-Mata (7 tiers) ===")
    # K1: placar exato. Real 2x1, aposta 2x1. 10 x 1.5 = 15.
    check("K1 placar exato",
          bolao_points((2, 1), (2, 1), knockout=True), 15)
    # K2: diferenca certa. 6 x 1.5 = 9.
    check("K2 diferenca de gols",
          bolao_points((3, 2), (2, 1), knockout=True), 9)
    # K3: gols do vencedor. 5 x 1.5 = 7.5, manual arredonda para 8.
    check("K3 gols do vencedor (arredondado)",
          bolao_points((2, 0), (2, 1), knockout=True), 8)
    # K4: gols do perdedor. 4 x 1.5 = 6.
    check("K4 gols do perdedor",
          bolao_points((3, 1), (2, 1), knockout=True), 6)
    # K5: so o vencedor. 3 x 1.5 = 4.5, manual arredonda para 5.
    check("K5 so o vencedor (arredondado)",
          bolao_points((3, 0), (2, 1), knockout=True), 5)
    # K6: empate exato no mata-mata (decide nos penaltis) = 15.
    check("K6 empate exato",
          bolao_points((1, 1), (1, 1), knockout=True), 15)
    # K7: empate placar errado = 9.
    check("K7 empate placar errado",
          bolao_points((1, 1), (0, 0), knockout=True), 9)

    print("\n=== Casos de zero (G8 / K8) ===")
    check("apostei empate mas houve vencedor (grupos)",
          bolao_points((1, 1), (2, 0), knockout=False), 0)
    check("apostei empate mas houve vencedor (mata-mata)",
          bolao_points((1, 1), (2, 0), knockout=True), 0)
    check("errei o vencedor (grupos)",
          bolao_points((0, 1), (1, 0), knockout=False), 0)
    check("errei o vencedor (mata-mata)",
          bolao_points((0, 1), (1, 0), knockout=True), 0)
    check("apostei vitoria mas houve empate (grupos)",
          bolao_points((2, 1), (0, 0), knockout=False), 0)
    check("apostei vitoria mas houve empate (mata-mata)",
          bolao_points((2, 1), (0, 0), knockout=True), 0)

    print("\n=== Sanity (vitoria do time visitante) ===")
    # Espelho de G1 com vitoria visitante: real 1x2, aposta 1x2.
    check("G1 espelho vitoria visitante",
          bolao_points((1, 2), (1, 2), knockout=False), 10)
    # Real 1x2, aposta 0x1 -> diferenca certa (ambos -1).
    check("G2 espelho vitoria visitante",
          bolao_points((0, 1), (1, 2), knockout=False), 6)
    # Real 1x2, aposta 1x3 -> gols do vencedor errados, perdedor certos = 4.
    # (bet_winner_g=3 vs result_winner_g=2 -> fail G3; bet_loser_g=1==result_loser_g=1 -> G4)
    check("G4 espelho vitoria visitante",
          bolao_points((1, 3), (1, 2), knockout=False), 4)

    print("\n=== Sanity: tier mais alto ganha ===")
    # Aposta 2x1 vs real 2x1: casa 'exato', 'diff', 'winner_goals',
    # 'loser_goals' e 'winner_only'. Deve retornar 'exato' (mais alto).
    check("precedencia exato > diff",
          bolao_points((2, 1), (2, 1), knockout=False), 10)

    print()
    total = 20 + 3 + 1  # mantido em sincronia com os checks acima
    if FAILURES:
        print(f"FALHOU: {len(FAILURES)} de {total} testes")
        for name, got, want in FAILURES:
            print(f"  - {name}: esperado {want}, obtido {got}")
        return 1
    print(f"OK ({total} testes)")
    return 0


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3
"""
Compara Elo ratings entre config.json atual e valores novos.
Mostra diff formatado e pede confirmacao antes de sobrescrever.

Uso:
    python scripts/diff_elos.py novos_elos.json

Onde novos_elos.json e um JSON simples {"Team": valor, ...}.
Se nenhum arquivo for passado, pede input interativo.

Exemplo:
    echo '{"Norway": 1912, "Ghana": 1505}' > novos.json
    python scripts/diff_elos.py novos.json
"""

import json
import sys
import os


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict, config_path: str) -> None:
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def diff_elos(current: dict, new_vals: dict, threshold: int = 40):
    """Compara dois dicts de Elo e imprime diff formatado."""
    all_teams = sorted(set(list(current.keys()) + list(new_vals.keys())))

    changes = []
    for team in all_teams:
        old = current.get(team)
        new = new_vals.get(team)

        if old is None and new is not None:
            changes.append((team, None, new, new, "NOVO"))
        elif old is not None and new is None:
            changes.append((team, old, None, 0, "REMOVIDO"))
        elif old != new:
            delta = new - old
            flag = "MUDANCA GRANDE" if abs(delta) > threshold else ""
            changes.append((team, old, new, delta, flag))

    if not changes:
        print("Nenhuma mudanca encontrada.")
        return []

    # Ordena por magnitude do delta (maiores primeiro)
    changes.sort(key=lambda x: abs(x[3]), reverse=True)

    print(f"\n{'='*65}")
    print(f"  DIFF DE ELO RATINGS ({len(changes)} mudancas)")
    print(f"{'='*65}")
    print(f"  {'Selecao':<30} {'Antigo':>6} {'Novo':>6} {'Delta':>7}  {'Flag'}")
    print(f"  {'-'*60}")

    big_changes = 0
    for team, old, new, delta, flag in changes:
        old_str = str(old) if old is not None else "---"
        new_str = str(new) if new is not None else "---"
        delta_str = f"{delta:+d}" if isinstance(delta, int) else "---"
        flag_str = f"[{flag}]" if flag else ""
        if flag == "MUDANCA GRANDE":
            big_changes += 1
        print(f"  {team:<30} {old_str:>6} {new_str:>6} {delta_str:>7}  {flag_str}")

    print(f"\n  Total: {len(changes)} mudancas, {big_changes} grandes (>{threshold} pts)")
    return changes


def main():
    # Encontra config.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    config_path = os.path.join(project_dir, "config.json")

    if not os.path.exists(config_path):
        print(f"ERRO: config.json nao encontrado em {config_path}")
        sys.exit(1)

    # Carrega config atual
    config = load_config(config_path)
    current_elos = config.get("elo_ratings", {})

    # Carrega novos valores
    if len(sys.argv) > 1:
        new_path = sys.argv[1]
        if not os.path.exists(new_path):
            print(f"ERRO: arquivo {new_path} nao encontrado")
            sys.exit(1)
        with open(new_path, "r", encoding="utf-8") as f:
            new_elos = json.load(f)
    else:
        print("Uso: python scripts/diff_elos.py <novos_elos.json>")
        print("Onde novos_elos.json e um JSON simples {\"Team\": valor, ...}")
        sys.exit(1)

    # Mostra diff
    changes = diff_elos(current_elos, new_elos)

    if not changes:
        sys.exit(0)

    # Pede confirmacao
    print()
    resp = input("Aplicar mudancas ao config.json? [y/N] ").strip().lower()
    if resp != "y":
        print("Cancelado.")
        sys.exit(0)

    # Aplica
    for team, old, new, delta, flag in changes:
        if new is None:
            config["elo_ratings"].pop(team, None)
        else:
            config["elo_ratings"][team] = new

    save_config(config, config_path)
    print(f"\nconfig.json atualizado em {config_path}")
    print("LEMBRETE: replique as mesmas mudancas em DEFAULT_ELO_RATINGS no bolao2026.py")


if __name__ == "__main__":
    main()

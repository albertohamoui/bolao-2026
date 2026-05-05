#!/usr/bin/env python3
"""
FALLBACK — usar apenas se scripts/update_elos.py (TSV) quebrar.

Extrai Elo ratings do eloratings.net via Playwright (browser headless).
Mais lento (~30s) e requer dependencia pesada (playwright + chromium),
mas funciona mesmo se os endpoints TSV forem removidos.

Requisitos:
    pip install playwright pandas openpyxl
    playwright install chromium

Uso:
    python3 scripts/update_elos_playwright.py
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
HISTORY_DIR = os.path.join(DATA_DIR, "elo_history")
LATEST_CSV = os.path.join(DATA_DIR, "elo_ratings_latest.csv")

URL = "https://eloratings.net/"

SANITY_TOP_10 = {"Spain", "Argentina", "France"}
MIN_TEAMS = 200


def extrair_elo():
    hoje = date.today().isoformat()
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector(".slick-row", timeout=30000)
        linhas = page.locator(".slick-row").all()
        dados = []
        for linha in linhas:
            celulas = linha.locator(".slick-cell").all_inner_texts()
            celulas = [c.strip() for c in celulas if c.strip() != ""]
            if len(celulas) >= 5:
                dados.append(celulas)
        browser.close()

    # Validacao de sanidade
    if len(dados) < MIN_TEAMS:
        print(f"ERRO: Tabela incompleta — apenas {len(dados)} linhas. "
              f"Minimo: {MIN_TEAMS}. CSV NAO sobrescrito.")
        sys.exit(1)

    max_colunas = max(len(linha) for linha in dados)
    colunas = [
        "Rank", "team", "elo", "Mudanca", "Jogos",
        "Vitorias", "Empates", "Derrotas", "Gols Pro", "Gols Contra"
    ]
    if max_colunas > len(colunas):
        colunas += [f"Coluna_{i}" for i in range(len(colunas) + 1, max_colunas + 1)]
    df = pd.DataFrame(dados, columns=colunas[:max_colunas])

    # Sanidade: top 10 deve conter Spain, Argentina, France
    top10_names = set(df.head(10)["team"].tolist())
    missing = SANITY_TOP_10 - top10_names
    if missing:
        print(f"ERRO: {missing} nao estao no top 10. "
              f"Top 10: {df.head(10)['team'].tolist()}. CSV NAO sobrescrito.")
        sys.exit(1)

    # Salva CSV simplificado (team, elo) — formato compativel com update_elos.py
    df_simple = df[["team", "elo"]].copy()
    df_simple["elo"] = pd.to_numeric(df_simple["elo"], errors="coerce")
    df_simple = df_simple.dropna(subset=["elo"])
    df_simple["elo"] = df_simple["elo"].astype(int)

    df_simple.to_csv(LATEST_CSV, index=False, encoding="utf-8")
    snapshot = os.path.join(HISTORY_DIR, f"elo_ratings_{hoje}.csv")
    df_simple.to_csv(snapshot, index=False, encoding="utf-8")

    print(f"Tabela extraida com sucesso.")
    print(f"  Linhas: {len(df_simple)}")
    print(f"  Latest: {LATEST_CSV}")
    print(f"  Snapshot: {snapshot}")


if __name__ == "__main__":
    extrair_elo()

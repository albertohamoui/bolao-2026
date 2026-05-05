"""
Storage layer para simulacoes do Bolao 2026.
Usa SQLite com JSON armazenado em colunas TEXT.

Schema:
    simulations:
        id              INTEGER PRIMARY KEY AUTOINCREMENT
        created_at      TEXT (ISO timestamp)
        name            TEXT
        notes           TEXT
        is_locked       INTEGER (0/1)
        runtime_seconds REAL
        calibration     TEXT (JSON)
        output          TEXT (JSON)
        sanity_checks   TEXT (JSON)
        claude_analysis TEXT (markdown/texto)

    market_odds:
        team           TEXT PRIMARY KEY
        champion_prob  REAL
        updated_at     TEXT
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any


DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "simulations.db"
)


def _get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Conexao com row_factory pra retornar dicts."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Cria as tabelas se nao existirem. Idempotente."""
    with _get_connection(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS simulations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at      TEXT NOT NULL,
                name            TEXT NOT NULL,
                notes           TEXT DEFAULT '',
                is_locked       INTEGER DEFAULT 0,
                runtime_seconds REAL,
                calibration     TEXT NOT NULL,
                output          TEXT NOT NULL,
                sanity_checks   TEXT,
                claude_analysis TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sims_created
                ON simulations(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_sims_locked
                ON simulations(is_locked DESC, created_at DESC);

            CREATE TABLE IF NOT EXISTS market_odds (
                team           TEXT PRIMARY KEY,
                champion_prob  REAL NOT NULL,
                updated_at     TEXT NOT NULL
            );
        """)


def save_simulation(
    name: str,
    calibration: dict,
    output: dict,
    sanity_checks: Optional[dict] = None,
    claude_analysis: Optional[str] = None,
    notes: str = "",
    runtime_seconds: Optional[float] = None,
    db_path: Optional[str] = None,
) -> int:
    """
    Salva uma simulacao completa no banco.
    Retorna o ID da simulacao criada.
    """
    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO simulations
                (created_at, name, notes, runtime_seconds,
                 calibration, output, sanity_checks, claude_analysis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                name,
                notes,
                runtime_seconds,
                json.dumps(calibration, default=str),
                json.dumps(output, default=str),
                json.dumps(sanity_checks, default=str) if sanity_checks else None,
                claude_analysis,
            ),
        )
        return cursor.lastrowid


def load_simulation(sim_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Carrega uma simulacao completa. Retorna None se nao existir."""
    init_db(db_path)
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM simulations WHERE id = ?", (sim_id,)
        ).fetchone()

    if row is None:
        return None

    return _row_to_dict(row)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Converte Row em dict com JSONs parseados."""
    d = dict(row)
    for field in ("calibration", "output", "sanity_checks"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass
    d["is_locked"] = bool(d.get("is_locked", 0))
    return d


def list_simulations(
    limit: int = 50,
    include_locked_first: bool = True,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Lista simulacoes com resumo (sem carregar output/calibration inteiros).
    Retorna: [{id, created_at, name, notes, is_locked, runtime_seconds,
               top5: [(team, pct), ...], sanity_summary: "7/8 ok"}]
    """
    init_db(db_path)
    order = "is_locked DESC, created_at DESC" if include_locked_first else "created_at DESC"

    with _get_connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT id, created_at, name, notes, is_locked, runtime_seconds,
                   output, sanity_checks
            FROM simulations
            ORDER BY {order}
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    results = []
    for row in rows:
        d = dict(row)
        d["is_locked"] = bool(d["is_locked"])

        # Extrai top 5 campeoes
        top5 = []
        if d.get("output"):
            try:
                output = json.loads(d["output"])
                stats = output.get("simulation_stats", {})
                ranked = sorted(
                    stats.items(),
                    key=lambda x: x[1].get("champion", 0),
                    reverse=True,
                )[:5]
                top5 = [(t, s.get("champion", 0)) for t, s in ranked]
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        # Resumo dos sanity checks
        sanity_summary = "n/a"
        if d.get("sanity_checks"):
            try:
                sc = json.loads(d["sanity_checks"])
                total = len(sc)
                passed = sum(1 for v in sc.values() if v.get("passed"))
                sanity_summary = f"{passed}/{total}"
            except (json.JSONDecodeError, TypeError):
                pass

        results.append({
            "id": d["id"],
            "created_at": d["created_at"],
            "name": d["name"],
            "notes": d["notes"] or "",
            "is_locked": d["is_locked"],
            "runtime_seconds": d["runtime_seconds"],
            "top5": top5,
            "sanity_summary": sanity_summary,
        })

    return results


def update_simulation(
    sim_id: int,
    db_path: Optional[str] = None,
    **fields
) -> bool:
    """
    Atualiza campos arbitrarios. Valida que o campo existe.
    Retorna True se atualizou, False se simulacao nao existe.

    Uso:
        update_simulation(5, notes="versao final", is_locked=True)
        update_simulation(5, claude_analysis="...")
    """
    ALLOWED = {"name", "notes", "is_locked", "claude_analysis", "runtime_seconds"}
    invalid = set(fields.keys()) - ALLOWED
    if invalid:
        raise ValueError(f"Campos invalidos: {invalid}. Permitidos: {ALLOWED}")

    if not fields:
        return True  # nada a fazer

    # Normaliza bool pra int
    if "is_locked" in fields:
        fields["is_locked"] = int(bool(fields["is_locked"]))

    init_db(db_path)
    with _get_connection(db_path) as conn:
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [sim_id]
        cursor = conn.execute(
            f"UPDATE simulations SET {set_clause} WHERE id = ?",
            values,
        )
        return cursor.rowcount > 0


def delete_simulation(sim_id: int, db_path: Optional[str] = None) -> bool:
    """Deleta uma simulacao. Retorna True se deletou, False se nao existe."""
    init_db(db_path)
    with _get_connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM simulations WHERE id = ?", (sim_id,))
        return cursor.rowcount > 0


def lock_simulation(sim_id: int, db_path: Optional[str] = None) -> bool:
    """Marca como 'a oficial'. Nao desbloqueia outras automaticamente."""
    return update_simulation(sim_id, is_locked=True, db_path=db_path)


def unlock_simulation(sim_id: int, db_path: Optional[str] = None) -> bool:
    return update_simulation(sim_id, is_locked=False, db_path=db_path)


# =============================================================================
# Market odds (tabela auxiliar)
# =============================================================================

def set_market_odds(team: str, champion_prob: float, db_path: Optional[str] = None) -> None:
    """Upsert de odds de mercado pra um time."""
    init_db(db_path)
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO market_odds (team, champion_prob, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(team) DO UPDATE SET
                champion_prob = excluded.champion_prob,
                updated_at = excluded.updated_at
            """,
            (team, champion_prob, datetime.now().isoformat(timespec="seconds")),
        )


def get_market_odds(db_path: Optional[str] = None) -> Dict[str, float]:
    """Retorna dict {team: champion_prob} com as odds atuais."""
    init_db(db_path)
    with _get_connection(db_path) as conn:
        rows = conn.execute("SELECT team, champion_prob FROM market_odds").fetchall()
    return {r["team"]: r["champion_prob"] for r in rows}


def clear_market_odds(db_path: Optional[str] = None) -> None:
    init_db(db_path)
    with _get_connection(db_path) as conn:
        conn.execute("DELETE FROM market_odds")


# =============================================================================
# Estatisticas / utilitarios
# =============================================================================

def count_simulations(db_path: Optional[str] = None) -> int:
    init_db(db_path)
    with _get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM simulations").fetchone()
    return row["c"]


def get_locked_simulation(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retorna a simulacao oficial (locked) mais recente, ou None.
    Se tiver varias locked, pega a mais recente.
    """
    init_db(db_path)
    with _get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM simulations
            WHERE is_locked = 1
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    return _row_to_dict(row) if row else None
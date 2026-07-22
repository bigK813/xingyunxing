"""
幸运猩 — 数据库抽象层
根据 GameConfig 动态建表，提供统一的读写接口。
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional
from config import GameConfig

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
DB_PATH = DATA_DIR / "lottery.db"


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_table(config: GameConfig) -> None:
    """根据配置创建对应的彩票数据表（如不存在）。"""
    conn = _get_conn()
    cols = [f"pos{i+1} INTEGER" for i in range(config.num_positions)]
    sql = f"""
        CREATE TABLE IF NOT EXISTS {config.table_name} (
            issue   TEXT PRIMARY KEY,
            date    TEXT NOT NULL,
            {', '.join(cols)},
            raw_json TEXT
        )
    """
    conn.execute(sql)
    conn.commit()


def save_batch(config: GameConfig, data: list[dict]) -> int:
    """批量插入或更新数据。返回写入条数。"""
    if not data:
        return 0
    conn = _get_conn()
    pos_cols = [f"pos{i+1}" for i in range(config.num_positions)]
    placeholders = ", ".join(["?"] * (2 + config.num_positions + 1))
    cols_str = ", ".join(["issue", "date"] + pos_cols + ["raw_json"])

    sql = f"INSERT OR REPLACE INTO {config.table_name} ({cols_str}) VALUES ({placeholders})"
    rows = []
    for d in data:
        nums = d["numbers"]
        row = [d["issue"], d["date"]] + nums + [json.dumps(d, ensure_ascii=False)]
        rows.append(row)

    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def load_all(config: GameConfig) -> list[dict]:
    """加载该彩票的全部历史数据，按期号降序。"""
    conn = _get_conn()
    pos_cols = [f"pos{i+1}" for i in range(config.num_positions)]
    cols = ", ".join(["issue", "date"] + pos_cols)
    rows = conn.execute(
        f"SELECT {cols} FROM {config.table_name} ORDER BY issue ASC"
    ).fetchall()

    results = []
    for r in rows:
        nums = [r[f"pos{i+1}"] for i in range(config.num_positions)]
        results.append({
            "issue": r["issue"],
            "date": r["date"],
            "numbers": nums,
        })
    return results


def get_latest_issue(config: GameConfig) -> Optional[str]:
    """获取最新一期期号。"""
    conn = _get_conn()
    row = conn.execute(
        f"SELECT issue FROM {config.table_name} ORDER BY issue DESC LIMIT 1"
    ).fetchone()
    return row["issue"] if row else None


def count(config: GameConfig) -> int:
    """返回数据库中该彩票的总期数。"""
    conn = _get_conn()
    row = conn.execute(f"SELECT COUNT(*) as cnt FROM {config.table_name}").fetchone()
    return row["cnt"] if row else 0

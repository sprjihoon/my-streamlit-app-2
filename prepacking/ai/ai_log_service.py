from __future__ import annotations

import datetime as dt

from prepacking.common.date_helper import today_kst
from prepacking.database import get_pp_connection


def log_ai_call(
    model_name: str,
    prompt_version: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    success: bool = True,
    error_message: str = "",
) -> int:
    total = int(input_tokens or 0) + int(output_tokens or 0)
    with get_pp_connection() as con:
        cur = con.execute(
            """
            INSERT INTO pp_ai_logs(
                model_name, prompt_version, input_tokens, output_tokens, total_tokens,
                cost_usd, latency_ms, success, error_message
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                model_name or "",
                prompt_version or "",
                int(input_tokens or 0),
                int(output_tokens or 0),
                total,
                float(cost_usd or 0),
                int(latency_ms or 0),
                1 if success else 0,
                error_message or "",
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def get_ai_usage_summary(days: int = 30) -> dict:
    start = dt.datetime.combine(today_kst() - dt.timedelta(days=max(0, int(days))), dt.time.min)
    start_s = start.strftime("%Y-%m-%d %H:%M:%S")
    with get_pp_connection() as con:
        row = con.execute(
            """
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COALESCE(SUM(cost_usd), 0) AS total_cost,
                COALESCE(AVG(latency_ms), 0) AS avg_latency,
                COALESCE(AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END), 0) AS success_rate
            FROM pp_ai_logs
            WHERE datetime(created_at) >= datetime(?)
            """,
            (start_s,),
        ).fetchone()
    total_calls = int(row[0] or 0)
    total_tokens = int(row[1] or 0)
    total_cost = float(row[2] or 0)
    avg_latency = float(row[3] or 0)
    success_rate = float(row[4] or 0)
    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "avg_latency": avg_latency,
        "success_rate": success_rate,
    }

"""
prepacking/database.py - 프리패킹 전용 DB (prepacking.db)
──────────────────────────────────────────────────────────
기존 billing.db와 완전 분리. 독립 스키마.
"""
from __future__ import annotations

import sqlite3
import textwrap
from contextlib import contextmanager

from .config import PP_DB_PATH

DDL = textwrap.dedent("""\

    /* 1. 전용 배송통계 업로드 파일 */
    CREATE TABLE IF NOT EXISTS pp_upload_files(
        upload_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name       TEXT NOT NULL,
        file_hash       TEXT DEFAULT '',
        file_version    INTEGER DEFAULT 1,
        uploaded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        uploaded_by     TEXT DEFAULT '',
        data_start_date TEXT,
        data_end_date   TEXT,
        row_count       INTEGER DEFAULT 0,
        skipped_count   INTEGER DEFAULT 0,
        total_count     INTEGER DEFAULT 0,
        upload_status   TEXT DEFAULT 'processing',
        error_message   TEXT DEFAULT '',
        applied_yn      INTEGER DEFAULT 0,
        note            TEXT DEFAULT ''
    );

    /* 2. 파싱된 배송 데이터 */
    CREATE TABLE IF NOT EXISTS pp_shipping_stats(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        upload_id       INTEGER NOT NULL,
        shipping_date   TEXT,
        supplier_name   TEXT,
        order_no        TEXT,
        invoice_no      TEXT,
        combo_no        TEXT,
        product_name    TEXT,
        option_name     TEXT,
        sku_code        TEXT,
        barcode         TEXT,
        qty             INTEGER DEFAULT 1,
        inner_qty       INTEGER DEFAULT 1,
        admin_product_qty TEXT,
        raw_data        TEXT DEFAULT '',
        FOREIGN KEY (upload_id) REFERENCES pp_upload_files(upload_id)
    );
    CREATE INDEX IF NOT EXISTS idx_pp_ss_date ON pp_shipping_stats(shipping_date);
    CREATE INDEX IF NOT EXISTS idx_pp_ss_supplier ON pp_shipping_stats(supplier_name);
    CREATE INDEX IF NOT EXISTS idx_pp_ss_dedup ON pp_shipping_stats(
        shipping_date, supplier_name, order_no, invoice_no, product_name, option_name, sku_code, qty
    );

    /* 3. 선포장 추천 마스터 */
    CREATE TABLE IF NOT EXISTS pp_recommendations(
        recommendation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_date TEXT NOT NULL,
        target_date         TEXT NOT NULL,
        supplier_name       TEXT NOT NULL,
        target_type         TEXT DEFAULT 'single_sku',
        target_code         TEXT DEFAULT '',
        target_name         TEXT NOT NULL,
        option_name         TEXT DEFAULT '',
        combination_key     TEXT DEFAULT '',
        predicted_qty       INTEGER DEFAULT 0,
        recommended_pack_unit INTEGER DEFAULT 1,
        confidence_score    REAL DEFAULT 0,
        risk_score          REAL DEFAULT 0,
        recommendation_reason TEXT DEFAULT '',
        weekday_basis       INTEGER,
        recent_7d_avg       REAL DEFAULT 0,
        recent_30d_avg      REAL DEFAULT 0,
        recent_same_weekday_avg REAL DEFAULT 0,
        source_upload_id    INTEGER,
        status              TEXT DEFAULT 'recommended',
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (source_upload_id) REFERENCES pp_upload_files(upload_id)
    );
    CREATE INDEX IF NOT EXISTS idx_pp_rec_target ON pp_recommendations(target_date);
    CREATE INDEX IF NOT EXISTS idx_pp_rec_supplier ON pp_recommendations(supplier_name);

    /* 4. 승인/수정 이력 */
    CREATE TABLE IF NOT EXISTS pp_approvals(
        approval_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id   INTEGER NOT NULL,
        action_type         TEXT NOT NULL,
        original_qty        INTEGER DEFAULT 0,
        adjusted_qty        INTEGER DEFAULT 0,
        action_reason       TEXT DEFAULT '',
        approved_by         TEXT DEFAULT '',
        approved_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        memo                TEXT DEFAULT '',
        FOREIGN KEY (recommendation_id) REFERENCES pp_recommendations(recommendation_id)
    );

    /* 5. 실제 선포장 실행 기록 */
    CREATE TABLE IF NOT EXISTS pp_executions(
        execution_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id   INTEGER,
        supplier_name       TEXT NOT NULL,
        target_type         TEXT DEFAULT 'single_sku',
        target_code         TEXT DEFAULT '',
        target_name         TEXT NOT NULL,
        executed_qty        INTEGER DEFAULT 0,
        executed_pack_unit  INTEGER DEFAULT 1,
        executed_by         TEXT DEFAULT '',
        executed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        execution_status    TEXT DEFAULT 'completed',
        memo                TEXT DEFAULT '',
        FOREIGN KEY (recommendation_id) REFERENCES pp_recommendations(recommendation_id)
    );

    /* 6. 선포장 재고 상태 */
    CREATE TABLE IF NOT EXISTS pp_stock(
        prepack_stock_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_name       TEXT NOT NULL,
        target_type         TEXT DEFAULT 'single_sku',
        target_code         TEXT DEFAULT '',
        target_name         TEXT NOT NULL,
        option_name         TEXT DEFAULT '',
        combination_key     TEXT DEFAULT '',
        current_qty         INTEGER DEFAULT 0,
        reserved_qty        INTEGER DEFAULT 0,
        available_qty       INTEGER DEFAULT 0,
        pack_status         TEXT DEFAULT 'packed',
        location_code       TEXT DEFAULT '',
        packed_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expiry_at           TEXT,
        last_moved_at       TIMESTAMP,
        source_execution_id INTEGER,
        memo                TEXT DEFAULT '',
        FOREIGN KEY (source_execution_id) REFERENCES pp_executions(execution_id)
    );

    /* 7. 로케이션 마스터 */
    CREATE TABLE IF NOT EXISTS pp_locations(
        location_code   TEXT PRIMARY KEY,
        location_name   TEXT DEFAULT '',
        location_zone   TEXT DEFAULT '',
        location_type   TEXT DEFAULT 'shelf',
        max_capacity    INTEGER DEFAULT 100,
        current_capacity INTEGER DEFAULT 0,
        is_active       INTEGER DEFAULT 1,
        note            TEXT DEFAULT ''
    );

    /* 8. 로케이션 이동 이력 */
    CREATE TABLE IF NOT EXISTS pp_location_history(
        location_history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        prepack_stock_id    INTEGER,
        target_type         TEXT DEFAULT '',
        target_code         TEXT DEFAULT '',
        target_name         TEXT DEFAULT '',
        action_type         TEXT NOT NULL,
        from_location       TEXT DEFAULT '',
        to_location         TEXT DEFAULT '',
        qty                 INTEGER DEFAULT 0,
        related_order_no    TEXT DEFAULT '',
        related_recommendation_id INTEGER,
        related_execution_id INTEGER,
        action_reason       TEXT DEFAULT '',
        action_by           TEXT DEFAULT '',
        action_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        memo                TEXT DEFAULT '',
        FOREIGN KEY (prepack_stock_id) REFERENCES pp_stock(prepack_stock_id)
    );

    /* 9. 해체/원복 이력 */
    CREATE TABLE IF NOT EXISTS pp_unwrap_history(
        unwrap_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        prepack_stock_id    INTEGER,
        supplier_name       TEXT DEFAULT '',
        target_type         TEXT DEFAULT '',
        target_code         TEXT DEFAULT '',
        target_name         TEXT DEFAULT '',
        unwrap_qty          INTEGER DEFAULT 0,
        unwrap_reason       TEXT DEFAULT '',
        return_to_stock_yn  INTEGER DEFAULT 0,
        return_location     TEXT DEFAULT '',
        unwrap_by           TEXT DEFAULT '',
        unwrap_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        memo                TEXT DEFAULT '',
        FOREIGN KEY (prepack_stock_id) REFERENCES pp_stock(prepack_stock_id)
    );

    /* 10. 예측 검증 결과 */
    CREATE TABLE IF NOT EXISTS pp_validations(
        validation_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id   INTEGER,
        supplier_name       TEXT DEFAULT '',
        target_type         TEXT DEFAULT '',
        target_code         TEXT DEFAULT '',
        target_name         TEXT DEFAULT '',
        target_date         TEXT,
        predicted_qty       INTEGER DEFAULT 0,
        actual_qty          INTEGER DEFAULT 0,
        executed_qty        INTEGER DEFAULT 0,
        used_qty            INTEGER DEFAULT 0,
        unused_qty          INTEGER DEFAULT 0,
        unwrap_qty          INTEGER DEFAULT 0,
        over_predict_qty    INTEGER DEFAULT 0,
        under_predict_qty   INTEGER DEFAULT 0,
        accuracy_rate       REAL DEFAULT 0,
        usage_rate          REAL DEFAULT 0,
        unwrap_rate         REAL DEFAULT 0,
        validation_result   TEXT DEFAULT '',
        failure_reason      TEXT DEFAULT '',
        validated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recommendation_id) REFERENCES pp_recommendations(recommendation_id)
    );

    /* 11. 제외/예외 대상 */
    CREATE TABLE IF NOT EXISTS pp_exceptions(
        exception_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_name   TEXT DEFAULT '',
        target_type     TEXT DEFAULT '',
        target_code     TEXT DEFAULT '',
        target_name     TEXT DEFAULT '',
        exception_type  TEXT DEFAULT 'excluded',
        exception_reason TEXT DEFAULT '',
        start_date      TEXT,
        end_date        TEXT,
        is_active       INTEGER DEFAULT 1,
        created_by      TEXT DEFAULT '',
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        memo            TEXT DEFAULT ''
    );

    /* 12. 조합 구성표 */
    CREATE TABLE IF NOT EXISTS pp_combinations(
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        combination_key     TEXT NOT NULL,
        combination_name    TEXT DEFAULT '',
        version_no          INTEGER DEFAULT 1,
        supplier_name       TEXT DEFAULT '',
        component_sku_code  TEXT DEFAULT '',
        component_sku_name  TEXT DEFAULT '',
        component_option    TEXT DEFAULT '',
        component_qty       INTEGER DEFAULT 1,
        package_type        TEXT DEFAULT '',
        insert_material     TEXT DEFAULT '',
        label_type          TEXT DEFAULT '',
        is_active           INTEGER DEFAULT 1,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    /* 13. AI 검증 입력/결과 */
    CREATE TABLE IF NOT EXISTS pp_ai_reviews(
        ai_review_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id   INTEGER,
        supplier_name       TEXT DEFAULT '',
        target_type         TEXT DEFAULT '',
        target_code         TEXT DEFAULT '',
        target_name         TEXT DEFAULT '',
        rule_based_predicted_qty INTEGER DEFAULT 0,
        recent_7d_avg       REAL DEFAULT 0,
        recent_30d_avg      REAL DEFAULT 0,
        recent_same_weekday_avg REAL DEFAULT 0,
        variability_score   REAL DEFAULT 0,
        repeat_score        REAL DEFAULT 0,
        combination_repeat_score REAL DEFAULT 0,
        pack_stability_score REAL DEFAULT 0,
        exclusion_flag      INTEGER DEFAULT 0,
        historical_accuracy_rate REAL DEFAULT 0,
        historical_unwrap_rate REAL DEFAULT 0,
        ai_model_name       TEXT DEFAULT '',
        ai_prompt_version   TEXT DEFAULT '',
        ai_input_snapshot   TEXT DEFAULT '',
        ai_review_result    TEXT DEFAULT '',
        ai_recommended_action TEXT DEFAULT '',
        ai_reason_summary   TEXT DEFAULT '',
        ai_risk_summary     TEXT DEFAULT '',
        ai_confidence_comment TEXT DEFAULT '',
        reviewed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recommendation_id) REFERENCES pp_recommendations(recommendation_id)
    );

    /* 14. AI 사후 검증 */
    CREATE TABLE IF NOT EXISTS pp_ai_post_validations(
        ai_post_validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        validation_id       INTEGER,
        recommendation_id   INTEGER,
        predicted_qty       INTEGER DEFAULT 0,
        actual_qty          INTEGER DEFAULT 0,
        error_qty           INTEGER DEFAULT 0,
        over_under_type     TEXT DEFAULT '',
        ai_failure_reason   TEXT DEFAULT '',
        ai_improvement_suggestion TEXT DEFAULT '',
        ai_reanalysis_model TEXT DEFAULT '',
        ai_reanalysis_prompt_version TEXT DEFAULT '',
        reanalyzed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (validation_id) REFERENCES pp_validations(validation_id)
    );

    /* 15. AI 호출 로그 */
    CREATE TABLE IF NOT EXISTS pp_ai_logs(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name      TEXT DEFAULT '',
        prompt_version  TEXT DEFAULT '',
        input_tokens    INTEGER DEFAULT 0,
        output_tokens   INTEGER DEFAULT 0,
        total_tokens    INTEGER DEFAULT 0,
        cost_usd        REAL DEFAULT 0,
        latency_ms      INTEGER DEFAULT 0,
        success         INTEGER DEFAULT 1,
        error_message   TEXT DEFAULT '',
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")


@contextmanager
def get_pp_connection():
    """프리패킹 전용 DB 연결."""
    PP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(PP_DB_PATH)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=5000;")
    try:
        yield con
    finally:
        con.close()


def ensure_pp_tables() -> None:
    """프리패킹 전용 테이블 생성."""
    with get_pp_connection() as con:
        con.executescript(DDL)
        cols = {r[1] for r in con.execute("PRAGMA table_info(pp_upload_files)").fetchall()}
        migrations = {
            "file_hash": "ALTER TABLE pp_upload_files ADD COLUMN file_hash TEXT DEFAULT ''",
            "upload_status": "ALTER TABLE pp_upload_files ADD COLUMN upload_status TEXT DEFAULT 'completed'",
            "error_message": "ALTER TABLE pp_upload_files ADD COLUMN error_message TEXT DEFAULT ''",
            "skipped_count": "ALTER TABLE pp_upload_files ADD COLUMN skipped_count INTEGER DEFAULT 0",
            "total_count": "ALTER TABLE pp_upload_files ADD COLUMN total_count INTEGER DEFAULT 0",
        }
        for col, sql in migrations.items():
            if col not in cols:
                con.execute(sql)
        con.commit()


def pp_df_from_sql(sql: str, params=None):
    """프리패킹 DB에서 DataFrame 조회."""
    import pandas as pd
    with get_pp_connection() as con:
        df = pd.read_sql(sql, con, params=params)
    df.columns = [str(c).strip() for c in df.columns]
    return df

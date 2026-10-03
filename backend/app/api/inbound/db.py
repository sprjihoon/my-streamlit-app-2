"""Inbound table initialization."""
from __future__ import annotations

from logic.db import get_connection

# ─────────────────────────────────────
# DB 초기화
# ─────────────────────────────────────

def ensure_inbound_tables():
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_batches (
                id TEXT PRIMARY KEY,
                vendor TEXT NOT NULL,
                inbound_date TEXT NOT NULL,
                status TEXT DEFAULT 'ocr_pending',
                memo TEXT,
                receipt_id TEXT,
                janggi_filename TEXT,
                janggi_date TEXT,
                janggi_no TEXT,
                wholesale TEXT,
                total_janggi_qty INTEGER DEFAULT 0,
                total_actual_qty INTEGER DEFAULT 0,
                total_missing_qty INTEGER DEFAULT 0,
                created_by TEXT,
                closed_by TEXT,
                closed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_items (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                line_no INTEGER DEFAULT 0,
                item_name TEXT,
                option_text TEXT,
                unit_price REAL,
                janggi_qty INTEGER DEFAULT 0,
                actual_qty INTEGER DEFAULT 0,
                missing_qty INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                matched_barcode TEXT,
                matched_vendor TEXT,
                matched_product TEXT,
                matched_option TEXT,
                match_confidence REAL DEFAULT 0.0,
                needs_matching INTEGER DEFAULT 0,
                supplier_location TEXT,
                supplier_contact TEXT,
                memo TEXT,
                defect_case_id TEXT,
                inbound_item_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES inbound_batches(id)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_item_photos (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES inbound_items(id)
            )
        """)
    # inbound_share_links 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_share_links (
                token TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                password TEXT,
                expires_at TEXT,
                allow_excel INTEGER DEFAULT 0,
                created_by TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES inbound_batches(id)
            )
        """)
        # barcode_print_jobs 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS barcode_print_jobs (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                item_id TEXT,
                barcode TEXT,
                product TEXT,
                option_text TEXT,
                vendor TEXT,
                wholesale TEXT,
                qty INTEGER DEFAULT 1,
                pdf_filename TEXT,
                printed_by TEXT,
                printed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES inbound_batches(id)
            )
        """)
        # 벤더 별칭 테이블
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_vendor_aliases (
                canonical TEXT PRIMARY KEY,
                aliases TEXT DEFAULT '',
                memo TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 기존 테이블에 inbound 연결 컬럼 추가
        for table, col in [
            ("defect_log",      "inbound_item_id TEXT"),
            ("defect_log",      "defect_case_id TEXT"),
            ("repair_work_log", "inbound_item_id TEXT"),
            ("repair_work_log", "defect_case_id TEXT"),
        ]:
            try:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except Exception:
                pass  # 이미 존재하면 무시
        # inbound_batches 에 vendor_canonical 컬럼 추가
        try:
            con.execute("ALTER TABLE inbound_batches ADD COLUMN vendor_canonical TEXT")
        except Exception:
            pass
        # inbound_items 에 신규 컬럼 추가 (기존 DB 마이그레이션)
        for col_def in [
            "supplier_location TEXT",
            "supplier_contact TEXT",
            "updated_at DATETIME",
            "confirmed_by TEXT",    # 로그인 없이 접근하는 작업자 이름
            "item_wholesale TEXT",  # 도매처 항목별 오버라이드
            "normal_qty INTEGER DEFAULT 0",  # 정상처리 수량 (직원 직접 입력)
            "actual_qty_confirmed INTEGER DEFAULT 0",  # 0=미확인, 1=직원이 수량 확인 완료
            "photo_decision TEXT",  # null=미결정, 'photo'=업로드사진, 'existing'=바코드연결, 'new'=신상품, 'none'=사진없음
        ]:
            try:
                con.execute(f"ALTER TABLE inbound_items ADD COLUMN {col_def}")
            except Exception:
                pass
        # 기존 inbound_done/done 배치 품목 → actual_qty_confirmed=1 backfill
        try:
            con.execute("""
                UPDATE inbound_items SET actual_qty_confirmed=1
                WHERE actual_qty_confirmed=0
                  AND batch_id IN (
                      SELECT id FROM inbound_batches WHERE status IN ('inbound_done','done','grading','repairing')
                  )
            """)
        except Exception:
            pass
        # 기존 matched_barcode 있는 품목 → photo_decision='existing' backfill
        try:
            con.execute("""
                UPDATE inbound_items SET photo_decision='existing'
                WHERE photo_decision IS NULL AND matched_barcode IS NOT NULL
            """)
        except Exception:
            pass
        # inbound_share_links 에 폐기 컬럼 추가
        try:
            con.execute("ALTER TABLE inbound_share_links ADD COLUMN revoked_at DATETIME")
        except Exception:
            pass
        # repair_barcode 에 도매처주소·도매처연락처 컬럼 추가 (없으면)
        for _col in ("도매처주소 TEXT", "도매처연락처 TEXT"):
            try:
                con.execute(f"ALTER TABLE repair_barcode ADD COLUMN {_col}")
            except Exception:
                pass

        # ── 제품사진 inbox (봇 채팅으로 수집된 제품사진) ──
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_product_photo_inbox (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                filename TEXT,
                stored_filename TEXT,
                item_id TEXT,           -- 매칭 완료 후 연결
                is_deleted INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES inbound_batches(id)
            )
        """)

        # ── 상품사진 사전 (직원이 확정 연결한 항목만 등록) ──
        con.execute("""
            CREATE TABLE IF NOT EXISTS product_photo_dict (
                id TEXT PRIMARY KEY,
                photo_filename TEXT NOT NULL,
                item_id TEXT,
                barcode TEXT,
                vendor TEXT,
                wholesale TEXT,
                wholesale_product TEXT,
                sales_product TEXT,
                option_text TEXT,
                confirmed_by TEXT,
                confirmed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_representative INTEGER DEFAULT 0,
                quality_score REAL DEFAULT 0.0,
                replaced_at DATETIME,
                replace_reason TEXT
            )
        """)

        # ── 상품 이미지 특징값 (추천 서비스용, 향후 구현) ──
        con.execute("""
            CREATE TABLE IF NOT EXISTS product_image_features (
                barcode TEXT NOT NULL,
                photo_filename TEXT NOT NULL,
                feature_vector TEXT,        -- JSON 직렬화 벡터
                provider TEXT DEFAULT 'none',
                computed_at DATETIME,
                PRIMARY KEY (barcode, photo_filename)
            )
        """)

        # ── 입고 수량 상태 이력 ──
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_item_qty_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                changed_by TEXT,
                changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                field_name TEXT NOT NULL,
                before_value INTEGER,
                after_value INTEGER,
                reason TEXT
            )
        """)

        # inbound_items 에 세부 수량 상태 컬럼 추가 (additive migration)
        for col_def in [
            "defect_pending_qty INTEGER DEFAULT 0",
            "repairing_qty INTEGER DEFAULT 0",
            "repair_done_qty INTEGER DEFAULT 0",
            "unrecoverable_qty INTEGER DEFAULT 0",
        ]:
            try:
                con.execute(f"ALTER TABLE inbound_items ADD COLUMN {col_def}")
            except Exception:
                pass

        # ── 부분수량 상태전환 이력 테이블 (move_item_qty 전용) ──
        con.execute("""
            CREATE TABLE IF NOT EXISTS inbound_item_qty_transitions (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                qty INTEGER NOT NULL,
                actor TEXT,
                ref_id TEXT,
                reason TEXT,
                moved_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ref_id 인덱스 (idempotency 조회 속도)
        try:
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_qty_trans_ref ON inbound_item_qty_transitions(ref_id, item_id)"
            )
        except Exception:
            pass

        # ── 수량 컬럼 backfill: status 기반 → qty 컬럼 (idempotent) ──────────
        # 모든 부분수량이 0 인 기존 행을 status 에 맞게 초기화한다.
        # 이미 부분수량이 설정된 행은 건드리지 않는다.
        _backfill_qty_sql = [
            # confirmed → normal_qty
            ("normal_qty=actual_qty",
             "status='confirmed' AND actual_qty>0 "
             "AND (normal_qty+defect_pending_qty+repairing_qty+repair_done_qty+unrecoverable_qty)=0"),
            # defect → defect_pending_qty
            ("defect_pending_qty=actual_qty",
             "status='defect' AND actual_qty>0 "
             "AND (normal_qty+defect_pending_qty+repairing_qty+repair_done_qty+unrecoverable_qty)=0"),
            # repair → repairing_qty
            ("repairing_qty=actual_qty",
             "status='repair' AND actual_qty>0 "
             "AND (normal_qty+defect_pending_qty+repairing_qty+repair_done_qty+unrecoverable_qty)=0"),
            # done → repair_done_qty
            ("repair_done_qty=actual_qty",
             "status='done' AND actual_qty>0 "
             "AND (normal_qty+defect_pending_qty+repairing_qty+repair_done_qty+unrecoverable_qty)=0"),
            # unrecoverable → unrecoverable_qty
            ("unrecoverable_qty=actual_qty",
             "status='unrecoverable' AND actual_qty>0 "
             "AND (normal_qty+defect_pending_qty+repairing_qty+repair_done_qty+unrecoverable_qty)=0"),
        ]
        for set_clause, where_clause in _backfill_qty_sql:
            try:
                con.execute(f"UPDATE inbound_items SET {set_clause} WHERE {where_clause}")
            except Exception:
                pass

        con.commit()

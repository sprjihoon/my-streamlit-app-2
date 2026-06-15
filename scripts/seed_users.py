"""
scripts/seed_users.py - 초기 직원 계정 생성 스크립트
──────────────────────────────────────────────────
실행: python scripts/seed_users.py
      (프로젝트 루트에서 실행)

초기 비밀번호: 123456
첫 로그인 시 비밀번호 변경 강제
"""

import sys
import os
import hashlib
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from logic.db import get_connection


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ──────────────────────────────────────────────────
# 직원 데이터 (확정)
# ──────────────────────────────────────────────────

INITIAL_PASSWORD = "123456"

USERS = [
    {
        "username":        "ti.72908",
        "nickname":        "장지훈",
        "department":      None,
        "position":        "대표",
        "position_order":  99,
        "naver_works_id":  "ti.72908",
        "join_date":       "2023-02-01",
        "is_admin":        1,
        "leave_exempt":    1,   # 대표 - 연차 관리 제외
        "approver_key":    None,
    },
    {
        "username":        "kyungha7182",
        "nickname":        "박경하",
        "department":      "인사",
        "position":        "인사과장",
        "position_order":  3,
        "naver_works_id":  "kyungha7182",
        "join_date":       "2023-11-01",
        "is_admin":        1,
        "leave_exempt":    0,
        "approver_key":    "ti.72908",   # 대표에게 결재
    },
    {
        "username":        "skerg",
        "nickname":        "장명찬",
        "department":      "뷰티팀",
        "position":        "팀장",
        "position_order":  2,
        "naver_works_id":  "skerg",
        "join_date":       "2023-11-01",
        "is_admin":        0,
        "leave_exempt":    0,
        "approver_key":    "kyungha7182",  # 인사과장 → 대표
    },
    {
        "username":        "tkh4262",
        "nickname":        "태찬기",
        "department":      "뷰티팀",
        "position":        "일반직",
        "position_order":  1,
        "naver_works_id":  "tkh4262",
        "join_date":       "2024-12-26",
        "is_admin":        0,
        "leave_exempt":    0,
        "approver_key":    "skerg",       # 뷰티팀장 → 인사과장 → 대표
    },
    {
        "username":        "gamja0821",
        "nickname":        "신경주",
        "department":      "뷰티팀",
        "position":        "일반직",
        "position_order":  1,
        "naver_works_id":  "gamja0821",
        "join_date":       "2026-01-01",
        "is_admin":        0,
        "leave_exempt":    0,
        "approver_key":    "skerg",
    },
    {
        "username":        "jsr486",
        "nickname":        "장성령",
        "department":      "패션팀",
        "position":        "팀장",
        "position_order":  2,
        "naver_works_id":  "jsr486",
        "join_date":       "2026-05-01",
        "is_admin":        0,
        "leave_exempt":    0,
        "approver_key":    "kyungha7182",
    },
    {
        "username":        "miyas86",
        "nickname":        "신윤미",
        "department":      "패션팀",
        "position":        "일반직",
        "position_order":  1,
        "naver_works_id":  "miyas86",
        "join_date":       "2025-04-15",
        "is_admin":        0,
        "leave_exempt":    0,
        "approver_key":    "jsr486",      # 패션팀장 → 인사과장 → 대표
    },
    {
        "username":        "hj23711",
        "nickname":        "윤혜준",
        "department":      "패션팀",
        "position":        "일반직",
        "position_order":  1,
        "naver_works_id":  "hj23711",
        "join_date":       "2026-06-01",
        "is_admin":        0,
        "leave_exempt":    0,
        "approver_key":    "jsr486",
    },
]


def ensure_columns(con):
    """users 테이블에 필요한 컬럼 추가"""
    new_cols = [
        ("department",           "TEXT"),
        ("position",             "TEXT"),
        ("position_order",       "INTEGER DEFAULT 1"),
        ("naver_works_id",       "TEXT"),
        ("approver_id",          "INTEGER"),
        ("join_date",            "TEXT"),
        ("must_change_password", "INTEGER DEFAULT 0"),
        ("leave_exempt",         "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in new_cols:
        try:
            con.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            print(f"  [컬럼 추가] {col_name}")
        except Exception:
            pass  # 이미 존재하면 무시


def seed():
    print("=" * 50)
    print("스프링풀필먼트 초기 계정 생성 스크립트")
    print("=" * 50)

    # users 테이블이 없으면 기존 auth.py의 ensure_users_table 호출
    try:
        from backend.app.api.auth import ensure_users_table
        ensure_users_table()
    except Exception as e:
        print(f"[경고] users 테이블 초기화 실패: {e}")

    with get_connection() as con:
        ensure_columns(con)

        # username → user_id 매핑 (approver_id 설정용)
        username_to_id = {}

        for user in USERS:
            # 기존 계정 확인
            existing = con.execute(
                "SELECT user_id FROM users WHERE username = ?", (user["username"],)
            ).fetchone()

            if existing:
                user_id = existing[0]
                # 기존 계정 업데이트 (비밀번호/must_change는 건드리지 않음)
                con.execute(
                    """UPDATE users SET
                       nickname = ?,
                       department = ?,
                       position = ?,
                       position_order = ?,
                       naver_works_id = ?,
                       join_date = ?,
                       is_admin = ?,
                       leave_exempt = ?
                       WHERE user_id = ?""",
                    (
                        user["nickname"],
                        user["department"],
                        user["position"],
                        user["position_order"],
                        user["naver_works_id"],
                        user["join_date"],
                        user["is_admin"],
                        user["leave_exempt"],
                        user_id,
                    )
                )
                print(f"  [업데이트] {user['nickname']} ({user['username']})")
            else:
                # 신규 계정 생성
                cur = con.execute(
                    """INSERT INTO users
                       (username, password_hash, nickname, is_admin,
                        department, position, position_order,
                        naver_works_id, join_date, must_change_password, leave_exempt)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (
                        user["username"],
                        hash_password(INITIAL_PASSWORD),
                        user["nickname"],
                        user["is_admin"],
                        user["department"],
                        user["position"],
                        user["position_order"],
                        user["naver_works_id"],
                        user["join_date"],
                        user["leave_exempt"],
                    )
                )
                user_id = cur.lastrowid
                print(f"  [생성] {user['nickname']} ({user['username']}) - 초기비밀번호: {INITIAL_PASSWORD}")

            username_to_id[user["username"]] = user_id

        con.commit()

        # approver_id 설정
        print("\n결재 라인 설정 중...")
        for user in USERS:
            if user["approver_key"] and user["approver_key"] in username_to_id:
                approver_id = username_to_id[user["approver_key"]]
                user_id = username_to_id[user["username"]]
                con.execute(
                    "UPDATE users SET approver_id = ? WHERE user_id = ?",
                    (approver_id, user_id)
                )
                approver_name = next((u["nickname"] for u in USERS if u["username"] == user["approver_key"]), "?")
                print(f"  {user['nickname']} → {approver_name}")

        con.commit()

    print("\n결재 라인 구조:")
    print("  패션팀 일반직 → 장성령(팀장) → 박경하(인사과장) [→ 장지훈(대표) 제외]")
    print("  뷰티팀 일반직 → 장명찬(팀장) → 박경하(인사과장) [→ 장지훈(대표) 제외]")
    print("  팀장들        → 박경하(인사과장) [→ 장지훈(대표) 제외]")
    print("  박경하        → 장지훈(대표) [leave_exempt=1 이므로 결재 체인 종료]")
    print()
    print("=" * 50)
    print(f"완료! 총 {len(USERS)}명의 계정이 준비되었습니다.")
    print(f"초기 비밀번호: {INITIAL_PASSWORD} (첫 로그인 시 변경 강제)")
    print("=" * 50)


if __name__ == "__main__":
    seed()

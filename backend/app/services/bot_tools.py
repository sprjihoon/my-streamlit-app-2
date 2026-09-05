"""
봇 Function Calling 도구 정의
───────────────────────────────────────
OpenAI Function Calling을 위한 도구(tools) 스키마와 실행 함수를 정의합니다.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from logic.db import get_connection
from backend.app.api.logs import add_log

QUERY_DEFAULT_LIMIT = 20
QUERY_MAX_LIMIT = 50
QUERY_ALL_TABLE_LIMIT = 15
TRUSTED_EXCEL_UPLOAD = "excel_upload"
_SECRET_KEY_RE = re.compile(
    r"password|passwd|api[_-]?key|secret|token|credential|private[_-]?key|authorization|session|env",
    re.I,
)


# ═══════════════════════════════════════════════════════════════════
# 도구(Tools) 스키마 정의 - OpenAI Function Calling 형식
# ═══════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_work_log",
            "description": "작업일지를 저장합니다. 업체명, 작업종류, 단가는 필수. 단가=1개당 금액만 넣을 것. 예: 88개 개당 100원 → unit_price=100, qty=88 (합계 8800). unit_price에 8800 넣지 말 것.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {
                        "type": "string",
                        "description": "업체명 (예: 틸리언, 나블리)"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업 종류 (예: 1톤하차, 양품화, 입고)"
                    },
                    "unit_price": {
                        "type": "integer",
                        "description": "단가 = 1개당 금액(원). '개당 100원'이면 100, '3만원'이면 30000. 합계가 아닌 개당 금액!"
                    },
                    "qty": {
                        "type": "integer",
                        "description": "수량(건수/개수). '88개'면 88. 기본값 1",
                        "default": 1
                    },
                    "date": {
                        "type": "string",
                        "description": "작업일 (YYYY-MM-DD 형식, 기본값: 오늘)"
                    },
                    "remark": {
                        "type": "string",
                        "description": "비고/메모"
                    }
                },
                "required": ["vendor", "work_type", "unit_price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_multiple_work_logs",
            "description": "여러 작업일지를 한 번에 저장합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entries": {
                        "type": "array",
                        "description": "저장할 작업일지 목록",
                        "items": {
                            "type": "object",
                            "properties": {
                                "vendor": {"type": "string"},
                                "work_type": {"type": "string"},
                                "unit_price": {"type": "integer"},
                                "qty": {"type": "integer", "default": 1},
                                "date": {"type": "string"},
                                "remark": {"type": "string"}
                            },
                            "required": ["vendor", "work_type", "unit_price"]
                        }
                    }
                },
                "required": ["entries"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_work_log",
            "description": "작업일지를 삭제합니다. ID로 삭제하거나, 조건으로 최근 1건을 삭제합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_id": {
                        "type": "integer",
                        "description": "삭제할 작업일지 ID (알고 있는 경우)"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "업체명 조건"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업종류 조건"
                    },
                    "date": {
                        "type": "string",
                        "description": "날짜 조건 (YYYY-MM-DD)"
                    },
                    "price": {
                        "type": "integer",
                        "description": "금액 조건 (합계)"
                    },
                    "delete_recent": {
                        "type": "boolean",
                        "description": "사용자의 가장 최근 작업일지 삭제 (true면 다른 조건 무시)",
                        "default": False
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_work_logs",
            "description": "조건에 맞는 작업일지를 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {
                        "type": "string",
                        "description": "업체명 (부분 일치)"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업종류 (부분 일치)"
                    },
                    "date": {
                        "type": "string",
                        "description": "특정 날짜 (YYYY-MM-DD)"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "시작 날짜 (YYYY-MM-DD)"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "종료 날짜 (YYYY-MM-DD)"
                    },
                    "price": {
                        "type": "integer",
                        "description": "금액 (±10% 범위로 검색)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "최대 결과 수 (기본: 20)",
                        "default": 20
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_work_log_stats",
            "description": "작업일지 통계를 조회합니다 (총 건수, 총액, 업체별, 작업별 통계). 반드시 start_date와 end_date를 지정하세요! 1월이면 2026-01-01 ~ 2026-01-31",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "시작 날짜 (YYYY-MM-DD). 필수! 예: 1월이면 2026-01-01"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "종료 날짜 (YYYY-MM-DD). 필수! 예: 1월이면 2026-01-31"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "특정 업체만 조회"
                    }
                },
                "required": ["start_date", "end_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "두 기간의 작업일지 통계를 비교합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period1_start": {
                        "type": "string",
                        "description": "기간1 시작일 (YYYY-MM-DD)"
                    },
                    "period1_end": {
                        "type": "string",
                        "description": "기간1 종료일 (YYYY-MM-DD)"
                    },
                    "period1_name": {
                        "type": "string",
                        "description": "기간1 이름 (예: '지난주')"
                    },
                    "period2_start": {
                        "type": "string",
                        "description": "기간2 시작일 (YYYY-MM-DD)"
                    },
                    "period2_end": {
                        "type": "string",
                        "description": "기간2 종료일 (YYYY-MM-DD)"
                    },
                    "period2_name": {
                        "type": "string",
                        "description": "기간2 이름 (예: '이번주')"
                    }
                },
                "required": ["period1_start", "period1_end", "period2_start", "period2_end"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_work_log",
            "description": "작업일지를 수정합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_id": {
                        "type": "integer",
                        "description": "수정할 작업일지 ID"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "업체명 조건 (ID 모를 때)"
                    },
                    "date": {
                        "type": "string",
                        "description": "날짜 조건 (ID 모를 때)"
                    },
                    "old_price": {
                        "type": "integer",
                        "description": "기존 금액 조건 (ID 모를 때)"
                    },
                    "new_vendor": {
                        "type": "string",
                        "description": "새 업체명"
                    },
                    "new_work_type": {
                        "type": "string",
                        "description": "새 작업종류"
                    },
                    "new_unit_price": {
                        "type": "integer",
                        "description": "새 단가"
                    },
                    "new_qty": {
                        "type": "integer",
                        "description": "새 수량"
                    },
                    "new_remark": {
                        "type": "string",
                        "description": "새 비고/메모 (기존 비고에 추가하거나 교체)"
                    },
                    "append_remark": {
                        "type": "boolean",
                        "description": "true면 기존 비고에 추가, false면 교체 (기본: true)",
                        "default": True
                    },
                    "update_recent": {
                        "type": "boolean",
                        "description": "사용자의 가장 최근 작업일지 수정 (true면 조건 무시)",
                        "default": False
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_update_work_logs",
            "description": "조건에 맞는 여러 작업일지를 일괄 수정합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {
                        "type": "string",
                        "description": "업체명 조건"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업종류 조건"
                    },
                    "date": {
                        "type": "string",
                        "description": "날짜 조건"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "시작 날짜"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "종료 날짜"
                    },
                    "new_unit_price": {
                        "type": "integer",
                        "description": "새 단가"
                    }
                },
                "required": ["new_unit_price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "copy_work_logs",
            "description": "작업일지를 다른 날짜로 복사합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_date": {
                        "type": "string",
                        "description": "복사할 원본 날짜"
                    },
                    "source_start_date": {
                        "type": "string",
                        "description": "복사할 기간 시작일"
                    },
                    "source_end_date": {
                        "type": "string",
                        "description": "복사할 기간 종료일"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "특정 업체만 복사"
                    },
                    "target_date": {
                        "type": "string",
                        "description": "복사 대상 날짜 (기본: 오늘)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_memo",
            "description": "작업일지에 메모/비고를 추가합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_id": {
                        "type": "integer",
                        "description": "작업일지 ID"
                    },
                    "memo": {
                        "type": "string",
                        "description": "추가할 메모 내용"
                    },
                    "add_to_recent": {
                        "type": "boolean",
                        "description": "가장 최근 작업일지에 추가",
                        "default": False
                    }
                },
                "required": ["memo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_undo_history",
            "description": "되돌리기 가능한 변경 이력을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "조회할 이력 수 (기본: 5)",
                        "default": 5
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "undo_action",
            "description": "특정 변경을 되돌립니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_id": {
                        "type": "integer",
                        "description": "되돌릴 이력 ID"
                    },
                    "history_index": {
                        "type": "integer",
                        "description": "되돌릴 이력 인덱스 (1부터 시작, 사용자가 '1번' 선택 시)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_dashboard_url",
            "description": "대시보드/웹페이지 URL을 반환합니다.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_invoice_stats",
            "description": "인보이스(청구서) 통계를 조회합니다. period_from(청구 시작일) 기준으로 조회합니다. '청구금액', '인보이스', '매출', '청구서' 관련 질문에 사용하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "조회 시작 날짜 (YYYY-MM-DD). 예: 1월이면 2026-01-01"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "조회 종료 날짜 (YYYY-MM-DD). 예: 1월이면 2026-01-31"
                    },
                    "vendor": {
                        "type": "string",
                        "description": "특정 업체만 조회"
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "상위 N개 업체만 조회 (기본: 10)"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "웹에서 정보를 검색합니다 (외부 정보 조회용).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색어"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_help",
            "description": "사용법/도움말을 반환합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "도움말 주제 (입력, 조회, 수정, 분석, 고급, 전체)",
                        "enum": ["입력", "조회", "수정", "분석", "고급", "전체"]
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_price_from_history",
            "description": "업체명+작업종류로 기존 작업일지에서 이전에 사용한 가격을 조회합니다. 사용자가 가격 없이 업체명, 작업명, 수량만 말했을 때 이 도구로 가격을 찾아서 확인을 요청하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {
                        "type": "string",
                        "description": "업체명"
                    },
                    "work_type": {
                        "type": "string",
                        "description": "작업 종류"
                    }
                },
                "required": ["vendor", "work_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_repair_log",
            "description": "수선작업일지를 저장합니다. 구멍/스팀/바느질/세탁 등 수선 건만 사용. 물류 하차·입고는 save_work_log.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string", "description": "업체명"},
                    "product": {"type": "string", "description": "제품명"},
                    "option": {"type": "string", "description": "옵션/색상"},
                    "barcode": {"type": "string", "description": "바코드"},
                    "defect": {"type": "string", "description": "불량명"},
                    "work_type": {"type": "string", "description": "수선 작업명"},
                    "unit_price": {"type": "integer", "description": "비용(원)"},
                    "qty": {"type": "integer", "description": "수량", "default": 1},
                    "remark": {"type": "string"},
                    "price_stated": {"type": "boolean", "description": "사용자가 가격을 직접 말했으면 true"}
                },
                "required": ["vendor", "work_type", "unit_price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_repair_price",
            "description": "수선 업체+작업의 최근 비용 또는 기본비용을 조회합니다. 가격 없이 수선 작업만 왔을 때 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "work_type": {"type": "string"}
                },
                "required": ["work_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_repair_barcode",
            "description": "수선 바코드 마스터에서 업체명·제품명·옵션을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "barcode": {"type": "string"}
                },
                "required": ["barcode"]
            }
        }
    },
    # ── 연차 관련 도구 ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "check_leave",
            "description": "연차 현황을 조회합니다. '연차 몇일 남았어?', '내 연차 알려줘', '휴가 현황' 등의 요청에 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "조회 연도 (기본값: 올해)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_leave",
            "description": "연차를 신청합니다. '연차 신청해줘', '7/1~7/3 연차', '다음주 반차' 등의 요청에 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "leave_type": {
                        "type": "string",
                        "description": "휴가 종류: '연차', '반차(오전)', '반차(오후)' 중 하나",
                        "enum": ["연차", "반차(오전)", "반차(오후)"]
                    },
                    "start_date": {
                        "type": "string",
                        "description": "시작일 (YYYY-MM-DD)"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "종료일 (YYYY-MM-DD). 반차는 start_date와 동일하게."
                    },
                    "reason": {
                        "type": "string",
                        "description": "신청 사유 (선택)"
                    }
                },
                "required": ["leave_type", "start_date", "end_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_leave",
            "description": "연차 신청을 취소합니다. '연차 취소해줘', '#5 취소' 등의 요청에 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "integer",
                        "description": "취소할 연차 신청 ID (#번호)"
                    }
                },
                "required": ["request_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "approve_leave",
            "description": "연차 신청을 승인합니다. 결재자가 '승인 #5', '연차 승인해줘' 등의 요청을 할 때 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "integer",
                        "description": "승인할 연차 신청 ID (#번호)"
                    },
                    "comment": {
                        "type": "string",
                        "description": "승인 코멘트 (선택)"
                    }
                },
                "required": ["request_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reject_leave",
            "description": "연차 신청을 반려합니다. 결재자가 '반려 #5 사유', '연차 반려' 등의 요청을 할 때 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "integer",
                        "description": "반려할 연차 신청 ID (#번호)"
                    },
                    "comment": {
                        "type": "string",
                        "description": "반려 사유"
                    }
                },
                "required": ["request_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_approvals",
            "description": "내가 결재해야 할 연차 목록을 조회합니다. '결재 대기', '승인 대기 연차', '결재할 거 있어?' 등의 요청에 사용합니다.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_vendors",
            "description": "등록 업체와 별칭을 조회합니다. 읽기 전용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "업체명 또는 별칭 검색어"},
                    "limit": {"type": "integer", "description": "최대 행 수 (기본 20, 최대 50)"},
                    "offset": {"type": "integer", "description": "건너뛸 행 수"},
                },
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_rate_tables",
            "description": "출고비·추가작업비·택배비·부자재 단가를 조회합니다. 읽기 전용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "out_basic, out_extra, shipping_zone, material_rates 중 하나. 전체를 원하면 테이블을 나눠 조회"
                    },
                    "limit": {"type": "integer", "description": "최대 행 수 (기본 20, 최대 50)"},
                    "offset": {"type": "integer", "description": "건너뛸 행 수"},
                },
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_storage",
            "description": "보관료 단가와 업체별 보관 설정을 조회합니다. 읽기 전용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string", "description": "업체명(선택)"},
                    "limit": {"type": "integer", "description": "최대 행 수 (기본 20, 최대 50)"},
                    "offset": {"type": "integer", "description": "건너뛸 행 수"},
                },
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_vendor_charges",
            "description": "거래처별 추가 청구 설정을 조회합니다. 읽기 전용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string", "description": "업체명 또는 vendor_id"},
                    "limit": {"type": "integer", "description": "최대 행 수 (기본 20, 최대 50)"},
                    "offset": {"type": "integer", "description": "건너뛸 행 수"},
                },
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_repair_catalog",
            "description": "수선 작업·불량·기본비용을 조회합니다. 읽기 전용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "최대 행 수 (기본 20, 최대 50)"},
                    "offset": {"type": "integer", "description": "건너뛸 행 수"},
                },
                "additionalProperties": False,
            }
        }
    },
]


WRITE_TOOL_NAMES = {
    "save_work_log",
    "save_multiple_work_logs",
    "delete_work_log",
    "update_work_log",
    "bulk_update_work_logs",
    "copy_work_logs",
    "add_memo",
    "undo_action",
    "save_repair_log",
    "apply_leave",
    "cancel_leave",
    "approve_leave",
    "reject_leave",
}

JOURNAL_TOOL_NAMES = {
    "save_work_log",
    "save_multiple_work_logs",
    "lookup_price_from_history",
    "update_work_log",
    "delete_work_log",
    "add_memo",
    "ask_missing_info",
    "complete_pending_entry",
    "ask_price_confirmation",
    "cancel_pending_entry",
}

QUERY_TOOL_NAMES = {
    "search_work_logs",
    "get_work_log_stats",
    "compare_periods",
    "get_invoice_stats",
    "lookup_vendors",
    "lookup_rate_tables",
    "lookup_storage",
    "lookup_vendor_charges",
    "lookup_repair_catalog",
}

INACTIVE_TOOL_NAMES = {
    "bulk_update_work_logs",
    "copy_work_logs",
    "get_undo_history",
    "undo_action",
    "get_dashboard_url",
    "web_search",
    "get_help",
    "save_repair_log",
    "lookup_repair_price",
    "lookup_repair_barcode",
    "check_leave",
    "apply_leave",
    "cancel_leave",
    "approve_leave",
    "reject_leave",
    "get_pending_approvals",
}

_TOOL_BY_NAME = {
    spec["function"]["name"]: spec for spec in TOOLS if spec.get("function")
}


def _apply_schema_guard(spec: dict, *, strict: bool) -> dict:
    """가능한 범위에서 additionalProperties=false, strict를 붙인다. 실행 함수는 그대로 둔다."""
    out = json.loads(json.dumps(spec))
    fn = out["function"]
    params = fn.setdefault("parameters", {"type": "object", "properties": {}})
    params["type"] = "object"
    params["additionalProperties"] = False
    props = params.get("properties") or {}
    if strict and props:
        params["required"] = list(props.keys())
        fn["strict"] = True
    elif not props:
        params["additionalProperties"] = False
        if strict:
            fn["strict"] = True
            params["required"] = []
    return out


def get_tools_for_mode(mode: str) -> list:
    """모드에 노출할 도구 스키마만 반환. 비활성 그룹은 삭제하지 않고 여기 넣지 않는다."""
    if mode == "journal":
        names = JOURNAL_TOOL_NAMES
        strict = False
    elif mode == "query":
        names = QUERY_TOOL_NAMES
        strict = True
    else:
        return []
    tools = []
    for name, spec in _TOOL_BY_NAME.items():
        if name in names:
            tools.append(_apply_schema_guard(spec, strict=strict and name.startswith("lookup_")))
    return tools


def allowed_arg_keys(tool_name: str) -> set:
    spec = _TOOL_BY_NAME.get(tool_name) or {}
    props = ((spec.get("function") or {}).get("parameters") or {}).get("properties") or {}
    return set(props.keys())


def _coerce_arg(value: Any, typ: Optional[str]) -> Any:
    if value is None:
        return None
    if typ == "integer":
        if isinstance(value, bool):
            raise ValueError("boolean is not integer")
        return int(value)
    if typ == "number":
        if isinstance(value, bool):
            raise ValueError("boolean is not number")
        return float(value)
    if typ == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "yes"):
            return True
        if text in ("false", "0", "no"):
            return False
        raise ValueError("invalid boolean")
    if typ == "string":
        return str(value)
    if typ == "array":
        if not isinstance(value, list):
            raise ValueError("expected array")
        return value
    if typ == "object":
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    return value


def validate_tool_args(tool_name: str, arguments: Optional[Dict[str, Any]]) -> tuple:
    """타입·필수값·허용 필드만 통과시킨다. 선택값은 비워도 된다."""
    spec = _TOOL_BY_NAME.get(tool_name) or {}
    params = (spec.get("function") or {}).get("parameters") or {}
    props = params.get("properties") or {}
    required = params.get("required") or []
    raw = dict(arguments or {})
    cleaned: Dict[str, Any] = {}
    for key, val in raw.items():
        if key not in props:
            continue
        prop = props[key] or {}
        typ = prop.get("type")
        try:
            if typ == "array" and key == "entries":
                items_spec = prop.get("items") or {}
                item_props = items_spec.get("properties") or {}
                item_req = items_spec.get("required") or []
                if not isinstance(val, list):
                    return None, "entries는 배열이어야 합니다."
                entries = []
                for item in val:
                    if not isinstance(item, dict):
                        return None, "entries 항목이 올바르지 않습니다."
                    one: Dict[str, Any] = {}
                    for ik, iv in item.items():
                        if ik not in item_props:
                            continue
                        one[ik] = _coerce_arg(iv, item_props[ik].get("type"))
                    for rk in item_req:
                        if one.get(rk) in (None, ""):
                            return None, f"entries.{rk}은(는) 필수입니다."
                    entries.append(one)
                cleaned[key] = entries
                continue
            cleaned[key] = _coerce_arg(val, typ)
        except (TypeError, ValueError):
            return None, f"{key} 값이 올바르지 않습니다."
    for rk in required:
        if cleaned.get(rk) in (None, "", []):
            return None, f"{rk}은(는) 필수입니다."
    return cleaned, None


# ═══════════════════════════════════════════════════════════════════
# 도구 실행 함수들
# ═══════════════════════════════════════════════════════════════════

def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: str,
    user_name: str = None,
    mode: str = None,
    trusted_source: str = None,
) -> Dict[str, Any]:
    """
    도구를 실행하고 결과를 반환합니다.
    GPT/외부 호출은 mode가 없거나 잘못되면 쓰기를 거부한다.
    엑셀 업로드만 trusted_source='excel_upload'로 저장을 허용한다.
    """
    if trusted_source == TRUSTED_EXCEL_UPLOAD:
        if tool_name != "save_work_log":
            return {"success": False, "error": "엑셀 업로드는 작업일지 저장만 허용합니다."}
    else:
        if tool_name in WRITE_TOOL_NAMES and mode != "journal":
            if mode == "query":
                return {"success": False, "error": "조회모드에서는 저장·수정·삭제를 할 수 없습니다."}
            if mode == "idle":
                return {"success": False, "error": "기본상태에서는 업무 도구를 실행할 수 없습니다. 모드를 선택해주세요."}
            if mode == "repair":
                return {"success": False, "error": "수선모드에서는 GPT 업무 도구를 실행하지 않습니다."}
            return {"success": False, "error": "모드가 없거나 올바르지 않아 쓰기를 거부합니다."}
        if mode == "idle":
            return {"success": False, "error": "기본상태에서는 업무 도구를 실행할 수 없습니다. 모드를 선택해주세요."}
        if mode == "query" and (tool_name in WRITE_TOOL_NAMES or tool_name not in QUERY_TOOL_NAMES):
            return {"success": False, "error": "조회모드에서는 저장·수정·삭제를 할 수 없습니다."}
        if mode == "journal" and tool_name not in JOURNAL_TOOL_NAMES:
            return {"success": False, "error": "일지모드에서 사용할 수 없는 도구입니다."}
        if mode == "repair":
            return {"success": False, "error": "수선모드에서는 GPT 업무 도구를 실행하지 않습니다."}

    cleaned, err = validate_tool_args(tool_name, arguments)
    if err:
        return {"success": False, "error": err}
    args = cleaned

    tool_functions = {
        "save_work_log": _save_work_log,
        "save_multiple_work_logs": _save_multiple_work_logs,
        "delete_work_log": _delete_work_log,
        "search_work_logs": _search_work_logs,
        "get_work_log_stats": _get_work_log_stats,
        "compare_periods": _compare_periods,
        "update_work_log": _update_work_log,
        "bulk_update_work_logs": _bulk_update_work_logs,
        "copy_work_logs": _copy_work_logs,
        "add_memo": _add_memo,
        "get_undo_history": _get_undo_history,
        "undo_action": _undo_action,
        "get_dashboard_url": _get_dashboard_url,
        "get_invoice_stats": _get_invoice_stats,
        "web_search": _web_search,
        "get_help": _get_help,
        "lookup_price_from_history": _lookup_price_from_history,
        "save_repair_log": _save_repair_log,
        "lookup_repair_price": _lookup_repair_price,
        "lookup_repair_barcode": _lookup_repair_barcode_tool,
        "check_leave": _check_leave,
        "apply_leave": _apply_leave,
        "cancel_leave": _cancel_leave,
        "approve_leave": _approve_leave,
        "reject_leave": _reject_leave,
        "get_pending_approvals": _get_pending_approvals,
        "lookup_vendors": _lookup_vendors,
        "lookup_rate_tables": _lookup_rate_tables,
        "lookup_storage": _lookup_storage,
        "lookup_vendor_charges": _lookup_vendor_charges_tool,
        "lookup_repair_catalog": _lookup_repair_catalog,
    }
    
    if tool_name not in tool_functions:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}
    
    try:
        return tool_functions[tool_name](args, user_id, user_name)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────
# 개별 도구 실행 함수
# ─────────────────────────────────────

def _save_work_log(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 저장"""
    vendor = args.get("vendor", "")
    work_type = args.get("work_type", "")
    unit_price = args.get("unit_price", 0)
    qty = args.get("qty", 1)
    date = args.get("date") or datetime.now().strftime("%Y-%m-%d")
    remark = args.get("remark", "")
    
    if not vendor or not work_type or not unit_price:
        return {"success": False, "error": "업체명, 작업종류, 단가는 필수입니다."}
    
    # 업체명 검증 - 등록된 업체인지 확인
    with get_connection() as con:
        # 공백 제거한 버전도 준비
        vendor_normalized = vendor.replace(" ", "").replace("　", "")
        
        # 1. 정확히 일치하는 업체 검색 (vendors 테이블 + aliases 테이블)
        # aliases 테이블: alias, file_type, vendor (vendor는 문자열)
        vendor_check = con.execute(
            """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
               UNION
               SELECT vendor FROM aliases WHERE LOWER(alias) = LOWER(?)""",
            (vendor, vendor)
        ).fetchone()
        
        # 2. 정확히 일치 없으면 → 공백 제거 후 검색
        if not vendor_check:
            vendor_check = con.execute(
                """SELECT vendor FROM vendors 
                   WHERE REPLACE(LOWER(vendor), ' ', '') = LOWER(?)
                   UNION
                   SELECT vendor FROM aliases 
                   WHERE REPLACE(LOWER(alias), ' ', '') = LOWER(?)""",
                (vendor_normalized, vendor_normalized)
            ).fetchone()
        
        # 3. 여전히 없으면 → 부분 일치 검색 (결과가 1개면 자동 선택)
        if not vendor_check:
            partial_matches = con.execute(
                """SELECT DISTINCT vendor FROM vendors 
                   WHERE vendor LIKE ? OR vendor LIKE ?
                   UNION
                   SELECT DISTINCT vendor FROM aliases 
                   WHERE alias LIKE ? OR alias LIKE ?""",
                (f"%{vendor}%", f"%{vendor_normalized}%", f"%{vendor}%", f"%{vendor_normalized}%")
            ).fetchall()
            
            if len(partial_matches) == 1:
                # 부분 일치가 1개면 자동 선택
                vendor_check = partial_matches[0]
        
        if not vendor_check:
            # 유사한 업체명 제안
            similar = con.execute(
                """SELECT vendor FROM vendors 
                   WHERE vendor LIKE ? OR vendor LIKE ? 
                   LIMIT 5""",
                (f"%{vendor}%", f"%{vendor[:2]}%")
            ).fetchall()
            
            similar_names = [r[0] for r in similar] if similar else []
            suggestion = f" 비슷한 업체: {', '.join(similar_names)}" if similar_names else ""
            
            return {
                "success": False, 
                "error": f"'{vendor}'은(는) 등록되지 않은 업체입니다.{suggestion}",
                "unknown_vendor": vendor,
                "similar_vendors": similar_names
            }
        
        # 정식 업체명으로 변환 (별칭으로 입력한 경우)
        vendor = vendor_check[0]
    
    total = unit_price * qty
    저장시간 = datetime.now().isoformat()
    
    with get_connection() as con:
        cursor = con.execute(
            """INSERT INTO work_log 
               (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, vendor, work_type, unit_price, qty, total, remark, user_name, 저장시간, "bot", user_id)
        )
        con.commit()
        record_id = cursor.lastrowid
    
    # 이력 기록
    _log_work_history(record_id, "create", {
        "날짜": date, "업체명": vendor, "분류": work_type,
        "단가": unit_price, "수량": qty, "합계": total, "작성자": user_name
    }, user_name, "봇 입력", user_id)
    
    # 활동 로그
    add_log(
        action_type="작업일지_생성",
        target_type="work_log",
        target_id=str(record_id),
        target_name=f"{vendor} {work_type}",
        user_nickname=user_name or "봇",
        details=f"날짜: {date}, 합계: {total:,}원 (봇 입력)"
    )
    
    return {
        "success": True,
        "record_id": record_id,
        "data": {
            "vendor": vendor,
            "work_type": work_type,
            "qty": qty,
            "unit_price": unit_price,
            "total": total,
            "date": date,
            "remark": remark
        },
        "message": f"저장완료! {vendor} {work_type} {total:,}원"
    }


def _save_multiple_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """여러 작업일지 저장"""
    entries = args.get("entries", [])
    if not entries:
        return {"success": False, "error": "저장할 항목이 없습니다."}
    
    results = []
    total_saved = 0
    total_amount = 0
    
    for entry in entries:
        result = _save_work_log(entry, user_id, user_name)
        results.append(result)
        if result.get("success"):
            total_saved += 1
            total_amount += result["data"]["total"]
    
    return {
        "success": True,
        "saved_count": total_saved,
        "total_amount": total_amount,
        "results": results,
        "message": f"{total_saved}건 저장완료! 총 {total_amount:,}원"
    }


def _delete_work_log(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 삭제 - 상세 정보 포함"""
    log_id = args.get("log_id")
    delete_recent = args.get("delete_recent", False)
    
    with get_connection() as con:
        # 삭제할 레코드 찾기 (비고 포함)
        if delete_recent:
            row = con.execute(
                """SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 비고1
                   FROM work_log WHERE works_user_id = ?
                   ORDER BY id DESC LIMIT 1""",
                (user_id,)
            ).fetchone()
        elif log_id:
            row = con.execute(
                "SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 비고1 FROM work_log WHERE id = ?",
                (log_id,)
            ).fetchone()
        else:
            # 조건으로 찾기
            conditions = []
            params = []
            if args.get("vendor"):
                conditions.append("업체명 LIKE ?")
                params.append(f"%{args['vendor']}%")
            if args.get("work_type"):
                conditions.append("분류 LIKE ?")
                params.append(f"%{args['work_type']}%")
            if args.get("date"):
                conditions.append("날짜 = ?")
                params.append(args["date"])
            if args.get("price"):
                conditions.append("합계 BETWEEN ? AND ?")
                params.extend([int(args["price"] * 0.9), int(args["price"] * 1.1)])
            
            if not conditions:
                return {"success": False, "error": "삭제 조건을 지정해주세요."}
            
            # 사용자 제한
            conditions.append("works_user_id = ?")
            params.append(user_id)
            
            row = con.execute(
                f"""SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 비고1
                   FROM work_log WHERE {' AND '.join(conditions)}
                   ORDER BY id DESC LIMIT 1""",
                params
            ).fetchone()
        
        if not row:
            return {"success": False, "error": "삭제할 작업일지를 찾지 못했습니다."}
        
        log_id = row[0]
        log_data = {
            "id": row[0], "날짜": row[1], "업체명": row[2], "분류": row[3],
            "단가": row[4], "수량": row[5], "합계": row[6], "작성자": row[7],
            "비고": row[8] if len(row) > 8 else None
        }
        
        # 이력 기록
        _log_work_history(log_id, "delete", log_data, user_name, "삭제", user_id)
        
        # 삭제
        con.execute("DELETE FROM work_log WHERE id = ?", (log_id,))
        con.commit()
    
    # 활동 로그
    add_log(
        action_type="작업일지_삭제",
        target_type="work_log",
        target_id=str(log_id),
        target_name=f"{log_data['업체명']} {log_data['분류']}",
        user_nickname=user_name or "봇",
        details=f"날짜: {log_data['날짜']}, 합계: {log_data['합계']:,}원"
    )
    
    # 상세 삭제 메시지 구성
    날짜 = log_data['날짜']
    업체명 = log_data['업체명']
    분류 = log_data['분류']
    단가 = log_data['단가'] or 0
    수량 = log_data['수량'] or 1
    합계 = log_data['합계'] or 0
    비고 = log_data.get('비고')
    
    # 상세 메시지
    detail_msg = f"🗑️ 삭제 완료!\n"
    detail_msg += f"━━━━━━━━━━━━━━━━━━━━\n"
    detail_msg += f"📅 날짜: {날짜}\n"
    detail_msg += f"🏢 업체: {업체명}\n"
    detail_msg += f"📋 작업: {분류}\n"
    detail_msg += f"💵 단가: {단가:,}원\n"
    detail_msg += f"📦 수량: {수량}건\n"
    detail_msg += f"💰 합계: {합계:,}원\n"
    if 비고:
        detail_msg += f"📝 비고: {비고}\n"
    detail_msg += f"━━━━━━━━━━━━━━━━━━━━"
    
    return {
        "success": True,
        "deleted": log_data,
        "message": detail_msg
    }


def _search_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 검색 (업체 별칭 지원)"""
    conditions = []
    params = []
    
    vendor_query = args.get("vendor")
    vendor_resolved = None
    if args.get("vendor"):
        vendor_search = args['vendor']
        # 별칭 테이블에서 실제 업체명 찾기
        with get_connection() as con:
            # aliases에서 검색
            alias_rows = con.execute(
                "SELECT DISTINCT vendor FROM aliases WHERE alias LIKE ? OR vendor LIKE ?",
                (f"%{vendor_search}%", f"%{vendor_search}%")
            ).fetchall()
            # vendors에서도 검색
            vendor_rows = con.execute(
                "SELECT vendor FROM vendors WHERE vendor LIKE ? OR name LIKE ?",
                (f"%{vendor_search}%", f"%{vendor_search}%")
            ).fetchall()
        # 조회 시 사용한 검색어 → 실제 정식 업체명 (봇 응답용)
        if alias_rows:
            vendor_resolved = alias_rows[0][0]
        elif vendor_rows:
            vendor_resolved = vendor_rows[0][0]
        # 찾은 모든 업체명으로 검색
        all_vendors = set([r[0] for r in alias_rows if r[0]] + [r[0] for r in vendor_rows if r[0]])
        all_vendors.add(vendor_search)  # 원본 검색어도 포함
        
        if len(all_vendors) == 1:
            conditions.append("업체명 LIKE ?")
            params.append(f"%{list(all_vendors)[0]}%")
        else:
            vendor_conditions = " OR ".join(["업체명 LIKE ?" for _ in all_vendors])
            conditions.append(f"({vendor_conditions})")
            params.extend([f"%{v}%" for v in all_vendors])
    if args.get("work_type"):
        conditions.append("분류 LIKE ?")
        params.append(f"%{args['work_type']}%")
    if args.get("date"):
        conditions.append("날짜 = ?")
        params.append(args["date"])
    elif args.get("start_date") and args.get("end_date"):
        conditions.append("날짜 >= ? AND 날짜 <= ?")
        params.extend([args["start_date"], args["end_date"]])
    elif args.get("start_date"):
        conditions.append("날짜 >= ?")
        params.append(args["start_date"])
    elif args.get("end_date"):
        conditions.append("날짜 <= ?")
        params.append(args["end_date"])
    if args.get("price"):
        conditions.append("합계 BETWEEN ? AND ?")
        params.extend([int(args["price"] * 0.9), int(args["price"] * 1.1)])
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    limit = _clamp_limit(args.get("limit"))
    
    with get_connection() as con:
        rows = con.execute(
            f"""SELECT id, 날짜, 업체명, 분류, 수량, 단가, 합계, 저장시간, 작성자
               FROM work_log WHERE {where_clause}
               ORDER BY 날짜 DESC, id DESC LIMIT ?""",
            params + [limit]
        ).fetchall()
        
        logs = [
            {"id": r[0], "날짜": r[1], "업체명": r[2], "분류": r[3], "수량": r[4],
             "단가": r[5], "합계": r[6], "저장시간": str(r[7]) if r[7] else None, "작성자": r[8]}
            for r in rows
        ]
        
        total_amount = sum(l["합계"] or 0 for l in logs)
    
    result = {
        "success": True,
        "count": len(logs),
        "total_amount": total_amount,
        "logs": logs,
        "message": f"검색결과: {len(logs)}건, 총 {total_amount:,}원"
    }
    if vendor_query:
        result["vendor_query"] = vendor_query
    if vendor_resolved:
        result["vendor_resolved"] = vendor_resolved
    return result


def _get_work_log_stats(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 통계 (업체 별칭 지원)"""
    conditions = []
    params = []
    
    if args.get("start_date"):
        conditions.append("날짜 >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        conditions.append("날짜 <= ?")
        params.append(args["end_date"])
    vendor_query = args.get("vendor")
    vendor_resolved = None
    if args.get("vendor"):
        vendor_search = args['vendor']
        # 별칭 테이블에서 실제 업체명 찾기
        with get_connection() as con:
            alias_rows = con.execute(
                "SELECT DISTINCT vendor FROM aliases WHERE alias LIKE ? OR vendor LIKE ?",
                (f"%{vendor_search}%", f"%{vendor_search}%")
            ).fetchall()
            vendor_rows = con.execute(
                "SELECT vendor FROM vendors WHERE vendor LIKE ? OR name LIKE ?",
                (f"%{vendor_search}%", f"%{vendor_search}%")
            ).fetchall()
        if alias_rows:
            vendor_resolved = alias_rows[0][0]
        elif vendor_rows:
            vendor_resolved = vendor_rows[0][0]
        all_vendors = set([r[0] for r in alias_rows if r[0]] + [r[0] for r in vendor_rows if r[0]])
        all_vendors.add(vendor_search)
        
        if len(all_vendors) == 1:
            conditions.append("업체명 LIKE ?")
            params.append(f"%{list(all_vendors)[0]}%")
        else:
            vendor_conditions = " OR ".join(["업체명 LIKE ?" for _ in all_vendors])
            conditions.append(f"({vendor_conditions})")
            params.extend([f"%{v}%" for v in all_vendors])
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with get_connection() as con:
        # 총합
        total_row = con.execute(
            f"SELECT COUNT(*), COALESCE(SUM(합계), 0) FROM work_log WHERE {where_clause}",
            params
        ).fetchone()
        
        # 업체별
        by_vendor = con.execute(
            f"""SELECT 업체명, COUNT(*), SUM(합계)
               FROM work_log WHERE {where_clause} AND 업체명 IS NOT NULL
               GROUP BY 업체명 ORDER BY SUM(합계) DESC LIMIT 10""",
            params
        ).fetchall()
        
        # 작업종류별
        by_work_type = con.execute(
            f"""SELECT 분류, COUNT(*), SUM(합계)
               FROM work_log WHERE {where_clause} AND 분류 IS NOT NULL
               GROUP BY 분류 ORDER BY COUNT(*) DESC LIMIT 10""",
            params
        ).fetchall()
    
    result = {
        "success": True,
        "total_count": total_row[0] or 0,
        "total_amount": total_row[1] or 0,
        "by_vendor": [{"vendor": v[0], "count": v[1], "amount": v[2]} for v in by_vendor],
        "by_work_type": [{"work_type": w[0], "count": w[1], "amount": w[2]} for w in by_work_type],
        "message": f"통계: {total_row[0]}건, 총 {total_row[1]:,}원"
    }
    if vendor_query:
        result["vendor_query"] = vendor_query
    if vendor_resolved:
        result["vendor_resolved"] = vendor_resolved
    return result


def _compare_periods(args: Dict, user_id: str, user_name: str) -> Dict:
    """기간 비교"""
    stats1 = _get_work_log_stats({
        "start_date": args.get("period1_start"),
        "end_date": args.get("period1_end")
    }, user_id, user_name)
    
    stats2 = _get_work_log_stats({
        "start_date": args.get("period2_start"),
        "end_date": args.get("period2_end")
    }, user_id, user_name)
    
    count_diff = stats2["total_count"] - stats1["total_count"]
    amount_diff = stats2["total_amount"] - stats1["total_amount"]
    count_rate = (count_diff / stats1["total_count"] * 100) if stats1["total_count"] > 0 else 0
    amount_rate = (amount_diff / stats1["total_amount"] * 100) if stats1["total_amount"] > 0 else 0
    
    return {
        "success": True,
        "period1": {
            "name": args.get("period1_name", "기간1"),
            "start": args.get("period1_start"),
            "end": args.get("period1_end"),
            "count": stats1["total_count"],
            "amount": stats1["total_amount"]
        },
        "period2": {
            "name": args.get("period2_name", "기간2"),
            "start": args.get("period2_start"),
            "end": args.get("period2_end"),
            "count": stats2["total_count"],
            "amount": stats2["total_amount"]
        },
        "diff": {
            "count": count_diff,
            "count_rate": count_rate,
            "amount": amount_diff,
            "amount_rate": amount_rate
        },
        "message": f"비교: 건수 {count_diff:+}건({count_rate:+.1f}%), 금액 {amount_diff:+,}원({amount_rate:+.1f}%)"
    }


def _update_work_log(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 수정"""
    log_id = args.get("log_id")
    update_recent = args.get("update_recent", False)
    
    with get_connection() as con:
        # 수정할 레코드 찾기
        if update_recent:
            row = con.execute(
                """SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계
                   FROM work_log WHERE works_user_id = ?
                   ORDER BY id DESC LIMIT 1""",
                (user_id,)
            ).fetchone()
        elif log_id:
            row = con.execute(
                "SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계 FROM work_log WHERE id = ?",
                (log_id,)
            ).fetchone()
        else:
            # 조건으로 찾기
            conditions = ["works_user_id = ?"]
            params = [user_id]
            if args.get("vendor"):
                conditions.append("업체명 LIKE ?")
                params.append(f"%{args['vendor']}%")
            if args.get("date"):
                conditions.append("날짜 = ?")
                params.append(args["date"])
            if args.get("old_price"):
                conditions.append("합계 BETWEEN ? AND ?")
                params.extend([int(args["old_price"] * 0.9), int(args["old_price"] * 1.1)])
            
            row = con.execute(
                f"""SELECT id, 날짜, 업체명, 분류, 단가, 수량, 합계
                   FROM work_log WHERE {' AND '.join(conditions)}
                   ORDER BY id DESC LIMIT 1""",
                params
            ).fetchone()
        
        if not row:
            return {"success": False, "error": "수정할 작업일지를 찾지 못했습니다."}
        
        log_id = row[0]
        old_data = {
            "날짜": row[1], "업체명": row[2], "분류": row[3],
            "단가": row[4], "수량": row[5], "합계": row[6]
        }
        
        # 기존 비고 조회
        remark_row = con.execute("SELECT 비고1 FROM work_log WHERE id = ?", (log_id,)).fetchone()
        old_remark = remark_row[0] if remark_row and remark_row[0] else ""
        
        # 업데이트 필드 구성
        updates = []
        update_params = []
        
        if args.get("new_vendor"):
            updates.append("업체명 = ?")
            update_params.append(args["new_vendor"])
        if args.get("new_work_type"):
            updates.append("분류 = ?")
            update_params.append(args["new_work_type"])
        if args.get("new_unit_price"):
            updates.append("단가 = ?")
            update_params.append(args["new_unit_price"])
        if args.get("new_qty"):
            updates.append("수량 = ?")
            update_params.append(args["new_qty"])
        
        # 비고 수정 처리
        if args.get("new_remark"):
            new_remark = args["new_remark"]
            append_remark = args.get("append_remark", True)  # 기본값: 기존에 추가
            
            if append_remark and old_remark:
                # 기존 비고에 추가
                final_remark = f"{old_remark}, {new_remark}"
            else:
                # 교체
                final_remark = new_remark
            
            updates.append("비고1 = ?")
            update_params.append(final_remark)
        
        if not updates:
            return {"success": False, "error": "수정할 내용이 없습니다."}
        
        # 합계 재계산
        new_단가 = args.get("new_unit_price") or old_data["단가"]
        new_수량 = args.get("new_qty") or old_data["수량"]
        updates.append("합계 = ?")
        update_params.append(new_단가 * new_수량)
        
        update_params.append(log_id)
        con.execute(f"UPDATE work_log SET {', '.join(updates)} WHERE id = ?", update_params)
        con.commit()
        
        # 수정된 데이터 조회
        new_row = con.execute(
            "SELECT 날짜, 업체명, 분류, 단가, 수량, 합계 FROM work_log WHERE id = ?",
            (log_id,)
        ).fetchone()
        
        new_data = {
            "날짜": new_row[0], "업체명": new_row[1], "분류": new_row[2],
            "단가": new_row[3], "수량": new_row[4], "합계": new_row[5]
        }
    
    # 이력 기록
    _log_work_history(log_id, "update", new_data, user_name, "수정", user_id)
    
    # 응답 메시지 구성
    message = f"수정완료! {new_data['업체명']} {new_data['분류']} {new_data['합계']:,}원"
    if args.get("new_remark"):
        message += f" (비고: {args['new_remark']})"
    
    return {
        "success": True,
        "log_id": log_id,
        "old_data": old_data,
        "new_data": new_data,
        "remark_updated": args.get("new_remark"),
        "message": message
    }


def _bulk_update_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """일괄 수정"""
    new_unit_price = args.get("new_unit_price")
    if not new_unit_price:
        return {"success": False, "error": "새 단가를 지정해주세요."}
    
    conditions = ["works_user_id = ?"]
    params = [user_id]
    
    if args.get("vendor"):
        conditions.append("업체명 LIKE ?")
        params.append(f"%{args['vendor']}%")
    if args.get("work_type"):
        conditions.append("분류 LIKE ?")
        params.append(f"%{args['work_type']}%")
    if args.get("date"):
        conditions.append("날짜 = ?")
        params.append(args["date"])
    if args.get("start_date"):
        conditions.append("날짜 >= ?")
        params.append(args["start_date"])
    if args.get("end_date"):
        conditions.append("날짜 <= ?")
        params.append(args["end_date"])
    
    with get_connection() as con:
        cursor = con.execute(
            f"""UPDATE work_log 
               SET 단가 = ?, 합계 = 수량 * ?
               WHERE {' AND '.join(conditions)}""",
            [new_unit_price, new_unit_price] + params
        )
        con.commit()
        updated_count = cursor.rowcount
    
    return {
        "success": True,
        "updated_count": updated_count,
        "new_unit_price": new_unit_price,
        "message": f"{updated_count}건 일괄 수정완료! 단가: {new_unit_price:,}원"
    }


def _copy_work_logs(args: Dict, user_id: str, user_name: str) -> Dict:
    """작업일지 복사"""
    target_date = args.get("target_date") or datetime.now().strftime("%Y-%m-%d")
    
    conditions = []
    params = []
    
    if args.get("source_date"):
        conditions.append("날짜 = ?")
        params.append(args["source_date"])
    if args.get("source_start_date") and args.get("source_end_date"):
        conditions.append("날짜 >= ? AND 날짜 <= ?")
        params.extend([args["source_start_date"], args["source_end_date"]])
    if args.get("vendor"):
        conditions.append("업체명 LIKE ?")
        params.append(f"%{args['vendor']}%")
    
    if not conditions:
        return {"success": False, "error": "복사할 원본 조건을 지정해주세요."}
    
    new_ids = []
    저장시간 = datetime.now().isoformat()
    
    with get_connection() as con:
        rows = con.execute(
            f"""SELECT 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 출처, works_user_id
               FROM work_log WHERE {' AND '.join(conditions)}""",
            params
        ).fetchall()
        
        for row in rows:
            cursor = con.execute(
                """INSERT INTO work_log (날짜, 업체명, 분류, 단가, 수량, 합계, 비고1, 작성자, 저장시간, 출처, works_user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (target_date, row[0], row[1], row[2], row[3], row[4],
                 f"{row[5] or ''} [복사됨]", row[6], 저장시간, "bot_copy", row[8])
            )
            new_ids.append(cursor.lastrowid)
        
        con.commit()
    
    return {
        "success": True,
        "copied_count": len(new_ids),
        "target_date": target_date,
        "new_ids": new_ids,
        "message": f"{len(new_ids)}건 복사완료! 대상 날짜: {target_date}"
    }


def _add_memo(args: Dict, user_id: str, user_name: str) -> Dict:
    """메모 추가"""
    memo = args.get("memo", "")
    if not memo:
        return {"success": False, "error": "메모 내용을 입력해주세요."}
    
    log_id = args.get("log_id")
    add_to_recent = args.get("add_to_recent", False)
    
    with get_connection() as con:
        if add_to_recent or not log_id:
            row = con.execute(
                "SELECT id FROM work_log WHERE works_user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,)
            ).fetchone()
            if row:
                log_id = row[0]
        
        if not log_id:
            return {"success": False, "error": "메모를 추가할 작업일지를 찾지 못했습니다."}
        
        existing = con.execute("SELECT 비고1 FROM work_log WHERE id = ?", (log_id,)).fetchone()
        if existing:
            old_memo = existing[0] or ""
            new_memo = f"{old_memo} [{memo}]" if old_memo else memo
            con.execute("UPDATE work_log SET 비고1 = ? WHERE id = ?", (new_memo, log_id))
            con.commit()
    
    return {
        "success": True,
        "log_id": log_id,
        "memo": memo,
        "message": f"메모 추가완료! [{memo}]"
    }


def _get_undo_history(args: Dict, user_id: str, user_name: str) -> Dict:
    """변경 이력 조회"""
    limit = args.get("limit", 5)
    
    with get_connection() as con:
        rows = con.execute(
            """SELECT id, action, 업체명, 분류, 합계, 변경자, 변경시간, log_id
               FROM work_log_history
               WHERE works_user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit)
        ).fetchall()
    
    history = []
    for i, r in enumerate(rows, 1):
        history.append({
            "index": i,
            "id": r[0],
            "action": r[1],
            "vendor": r[2],
            "work_type": r[3],
            "amount": r[4],
            "user": r[5],
            "time": r[6],
            "log_id": r[7]
        })
    
    return {
        "success": True,
        "history": history,
        "message": f"최근 변경 이력 {len(history)}건"
    }


def _undo_action(args: Dict, user_id: str, user_name: str) -> Dict:
    """되돌리기 실행"""
    history_id = args.get("history_id")
    history_index = args.get("history_index")
    
    # 이력 조회
    history_result = _get_undo_history({"limit": 10}, user_id, user_name)
    history = history_result.get("history", [])
    
    if not history:
        return {"success": False, "error": "되돌릴 이력이 없습니다."}
    
    # 대상 찾기
    target = None
    if history_index:
        for h in history:
            if h["index"] == history_index:
                target = h
                break
    elif history_id:
        for h in history:
            if h["id"] == history_id:
                target = h
                break
    
    if not target:
        return {"success": False, "error": "되돌릴 이력을 찾지 못했습니다."}
    
    action = target["action"]
    log_id = target["log_id"]
    
    if action == "create":
        # 생성된 것 삭제
        with get_connection() as con:
            con.execute("DELETE FROM work_log WHERE id = ?", (log_id,))
            con.commit()
        return {"success": True, "message": "되돌리기 완료! (추가된 데이터 삭제됨)"}
    
    elif action == "delete":
        # 삭제된 것 복구
        data = {
            "vendor": target["vendor"],
            "work_type": target["work_type"],
            "unit_price": target["amount"],  # 합계를 단가로 사용 (수량 1 가정)
            "qty": 1,
            "remark": "[복구됨]"
        }
        result = _save_work_log(data, user_id, user_name)
        return {"success": True, "message": "되돌리기 완료! (삭제된 데이터 복구됨)", "new_id": result.get("record_id")}
    
    return {"success": False, "error": "이 항목은 되돌릴 수 없습니다."}


def _get_dashboard_url(args: Dict, user_id: str, user_name: str) -> Dict:
    """대시보드 URL"""
    import os
    base_url = os.getenv("FRONTEND_URL", "https://my-streamlit-app-2.vercel.app")
    
    return {
        "success": True,
        "urls": {
            "main": base_url,
            "work_log": f"{base_url}/work-log"
        },
        "message": f"대시보드: {base_url}"
    }


def _get_invoice_stats(args: Dict, user_id: str, user_name: str) -> Dict:
    """인보이스 통계 조회 (청구 기간 기준)"""
    conditions = []
    params = []
    
    # 날짜 조건 - period_from이 지정 기간 내인 인보이스 조회
    # 예: 1월 조회 → period_from이 2026-01-01 ~ 2026-01-31 사이인 인보이스
    if args.get("start_date") and args.get("end_date"):
        conditions.append("i.period_from BETWEEN ? AND ?")
        params.extend([args["start_date"], args["end_date"]])
    elif args.get("start_date"):
        conditions.append("i.period_from >= ?")
        params.append(args["start_date"])
    elif args.get("end_date"):
        conditions.append("i.period_from <= ?")
        params.append(args["end_date"])
    
    # 업체 조건
    if args.get("vendor"):
        conditions.append("v.vendor LIKE ?")
        params.append(f"%{args['vendor']}%")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    top_n = _clamp_limit(args.get("top_n"), default=10, maximum=QUERY_MAX_LIMIT)
    
    try:
        with get_connection() as con:
            # 전체 통계
            total_stats = con.execute(f"""
                SELECT COUNT(*), COALESCE(SUM(i.total_amount), 0)
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE {where_clause}
            """, params).fetchone()
            
            # 업체별 통계 (상위 N개)
            vendor_stats = con.execute(f"""
                SELECT v.vendor, COUNT(*) as cnt, SUM(i.total_amount) as total
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE {where_clause} AND v.vendor IS NOT NULL
                GROUP BY v.vendor
                ORDER BY total DESC
                LIMIT ?
            """, params + [top_n]).fetchall()
            
            # 최근 인보이스 5건
            recent = con.execute(f"""
                SELECT v.vendor, i.total_amount, i.period_from, i.period_to, i.created_at
                FROM invoices i
                LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                WHERE {where_clause}
                ORDER BY i.created_at DESC
                LIMIT 5
            """, params).fetchall()
        
        # 결과 구성
        result = {
            "success": True,
            "query_params": {
                "start_date": args.get("start_date"),
                "end_date": args.get("end_date"),
                "vendor": args.get("vendor"),
                "where_clause": where_clause
            },
            "total_count": total_stats[0] or 0,
            "total_amount": total_stats[1] or 0,
            "by_vendor": [
                {"vendor": r[0], "count": r[1], "amount": r[2] or 0}
                for r in vendor_stats
            ],
            "recent": [
                {
                    "vendor": r[0],
                    "amount": r[1] or 0,
                    "period": f"{r[2]} ~ {r[3]}" if r[2] and r[3] else "",
                    "created": r[4]
                }
                for r in recent
            ]
        }
        
        # 상위 업체 정보
        if vendor_stats:
            top_vendor = vendor_stats[0]
            result["top_vendor"] = {
                "name": top_vendor[0],
                "count": top_vendor[1],
                "amount": top_vendor[2] or 0
            }
            result["message"] = f"청구금액 1위: {top_vendor[0]} ({top_vendor[2]:,.0f}원, {top_vendor[1]}건)"
        else:
            result["message"] = "조건에 맞는 인보이스가 없습니다."
        
        return result
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def _web_search(args: Dict, user_id: str, user_name: str) -> Dict:
    """웹 검색"""
    query = args.get("query", "")
    if not query:
        return {"success": False, "error": "검색어를 입력해주세요."}
    
    try:
        from duckduckgo_search import DDGS
        
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
        
        if not results:
            return {"success": False, "error": "검색 결과가 없습니다."}
        
        return {
            "success": True,
            "query": query,
            "results": results,
            "message": f"'{query}' 검색결과 {len(results)}건"
        }
    except ImportError:
        return {"success": False, "error": "웹 검색 라이브러리가 설치되지 않았습니다."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _lookup_price_from_history(args: Dict, user_id: str, user_name: str) -> Dict:
    """기존 작업일지에서 업체명+작업종류 조합의 가격 조회
    
    조회 우선순위:
    1. 해당 업체 + 해당 작업종류 (정확히 일치)
    2. 해당 작업종류만 (모든 업체에서 검색)
    """
    vendor = args.get("vendor", "")
    work_type = args.get("work_type", "")
    
    if not work_type:
        return {"success": False, "error": "작업종류가 필요합니다."}
    
    with get_connection() as con:
        resolved_vendor = vendor
        
        if vendor:
            # 공백 제거한 버전도 준비
            vendor_normalized = vendor.replace(" ", "").replace("　", "")
            
            # 1. 별칭 테이블에서 실제 업체명 찾기
            vendor_check = con.execute(
                """SELECT vendor FROM vendors WHERE LOWER(vendor) = LOWER(?)
                   UNION
                   SELECT vendor FROM aliases WHERE LOWER(alias) = LOWER(?)""",
                (vendor, vendor)
            ).fetchone()
            
            if not vendor_check:
                vendor_check = con.execute(
                    """SELECT vendor FROM vendors 
                       WHERE REPLACE(LOWER(vendor), ' ', '') = LOWER(?)
                       UNION
                       SELECT vendor FROM aliases 
                       WHERE REPLACE(LOWER(alias), ' ', '') = LOWER(?)""",
                    (vendor_normalized, vendor_normalized)
                ).fetchone()
            
            if vendor_check:
                resolved_vendor = vendor_check[0]
            
            # 2. 해당 업체+작업종류 조합의 최근 가격 조회
            price_rows = con.execute(
                """SELECT 단가, 합계, 수량, 날짜, COUNT(*) as usage_count, 업체명
                   FROM work_log 
                   WHERE 업체명 = ? AND 분류 LIKE ?
                   GROUP BY 단가
                   ORDER BY MAX(날짜) DESC, usage_count DESC
                   LIMIT 5""",
                (resolved_vendor, f"%{work_type}%")
            ).fetchall()
            
            if price_rows:
                # 정확히 일치하는 경우
                prices = [
                    {
                        "unit_price": r[0],
                        "total": r[1],
                        "qty": r[2],
                        "last_date": r[3],
                        "usage_count": r[4],
                        "vendor": r[5]
                    }
                    for r in price_rows if r[0]
                ]
                
                if prices:
                    most_recent = prices[0]
                    return {
                        "success": True,
                        "found": True,
                        "exact_match": True,
                        "vendor": resolved_vendor,
                        "work_type": work_type,
                        "prices": prices,
                        "most_recent_price": most_recent["unit_price"],
                        "most_recent_date": most_recent["last_date"],
                        "usage_count": most_recent["usage_count"],
                        "message": f"'{resolved_vendor} {work_type}'의 최근 단가: {most_recent['unit_price']:,}원 ({most_recent['usage_count']}회 사용)"
                    }
        
        # 3. 작업종류만으로 검색 (모든 업체에서)
        # 가장 많이 사용된 단가를 찾음
        price_rows = con.execute(
            """SELECT 단가, 합계, 수량, MAX(날짜) as last_date, COUNT(*) as usage_count, 업체명
               FROM work_log 
               WHERE 분류 LIKE ? AND 단가 IS NOT NULL AND 단가 > 0
               GROUP BY 단가
               ORDER BY usage_count DESC, last_date DESC
               LIMIT 5""",
            (f"%{work_type}%",)
        ).fetchall()
        
        if not price_rows:
            return {
                "success": False,
                "found": False,
                "vendor": resolved_vendor,
                "work_type": work_type,
                "message": f"'{work_type}' 작업에 대한 이전 가격 기록이 없습니다."
            }
        
        # 작업종류만 일치하는 경우 - 가장 많이 사용된 단가 제안
        prices = [
            {
                "unit_price": r[0],
                "total": r[1],
                "qty": r[2],
                "last_date": r[3],
                "usage_count": r[4],
                "sample_vendor": r[5]
            }
            for r in price_rows if r[0]
        ]
        
        if not prices:
            return {
                "success": False,
                "found": False,
                "vendor": resolved_vendor,
                "work_type": work_type,
                "message": f"'{work_type}' 작업에 대한 이전 가격 기록이 없습니다."
            }
        
        most_used = prices[0]
        sample_vendor = most_used.get("sample_vendor", "")
        
        return {
            "success": True,
            "found": True,
            "exact_match": False,
            "vendor": resolved_vendor,
            "work_type": work_type,
            "prices": prices,
            "most_recent_price": most_used["unit_price"],
            "most_recent_date": most_used["last_date"],
            "usage_count": most_used["usage_count"],
            "sample_vendor": sample_vendor,
            "message": f"'{work_type}' 작업의 최근 단가: {most_used['unit_price']:,}원 ({most_used['usage_count']}회 사용, 예: {sample_vendor})"
        }


def _save_repair_log(args: Dict, user_id: str, user_name: str) -> Dict:
    from backend.app.services.repair_bot import save_repair_from_tool
    return save_repair_from_tool(args, user_id, user_name)


def _lookup_repair_price(args: Dict, user_id: str, user_name: str) -> Dict:
    from backend.app.services import repair_catalog
    return repair_catalog.lookup_repair_price(args.get("vendor"), args.get("work_type"))


def _lookup_repair_barcode_tool(args: Dict, user_id: str, user_name: str) -> Dict:
    from backend.app.api.repair_log import _lookup_barcode, ensure_repair_tables
    ensure_repair_tables()
    code = (args.get("barcode") or "").strip()
    with get_connection() as con:
        found = _lookup_barcode(con, code)
    if not found:
        return {"success": False, "found": False, "message": "등록 안 된 바코드예요."}
    return {"success": True, "found": True, **found}


def _get_help(args: Dict, user_id: str, user_name: str) -> Dict:
    """도움말"""
    topic = args.get("topic", "전체")
    
    help_texts = {
        "입력": """📝 작업일지 입력
━━━━━━━━━━━━━━━━━━━━
✨ 자연스럽게 말하면 됩니다!

• "틸리언 1톤하차 3만원"
• "나블리 양품화 20개 800원"
• "어제 틸리언 하차 3만원"

💬 정보가 부족하면 물어봐요:
  "틸리언 하차" → "단가가 얼마예요?"
  "3만원" → 자동으로 완성!

💡 입력 후 '취소'로 바로 삭제 가능

🧵 수선작업일지
• 사진 3장(바코드 / 수선 전 / 수선 후)을 한 번에 보내기
• "구멍 바느질 1500원"처럼 작업·금액 말하기
• 물류 하차·입고는 기존처럼 입력""",

        "조회": """🔍 조회/검색
━━━━━━━━━━━━━━━━━━━━
자연어로 물어보세요!

📅 기간 조회
• "오늘 작업 보여줘"
• "이번주 뭐했어?"
• "지난달 작업"

🏢 업체별 조회
• "틸리언 작업 보여줘"
• "이번주 나블리"

💰 금액 검색
• "3만원짜리 뭐있어?"
• "5만원 이상"

🔀 조합도 가능!
• "이번주 틸리언 뭐했어?"
• "어제 3만원짜리"

📥 결과에서 엑셀 다운로드 가능""",

        "수정": """✏️ 수정/삭제
━━━━━━━━━━━━━━━━━━━━
🗑️ 삭제
• "취소" / "삭제해줘"
• "방금꺼 지워줘"
• "틸리언 3만원 삭제해줘"

✏️ 수정
• "수정해줘"
• "5만원으로 바꿔줘"
• "업체명 틸리언으로 수정"

📦 일괄 수정
• "오늘 전부 5만원으로"
• "틸리언 단가 3만원으로"

🔄 되돌리기
• "되돌려줘" - 최근 변경 이력
• 번호 선택해서 복구""",

        "분석": """📊 통계/분석
━━━━━━━━━━━━━━━━━━━━
💰 합계
• "이번달 총 얼마?"
• "오늘 합계"

🏢 업체별
• "업체별 합계"
• "틸리언 이번달 얼마?"

📈 비교
• "지난주랑 이번주 비교"
• "저번달이랑 비교해줘"

🏆 순위
• "가장 많이 일한 업체"
• "이번달 Top 5"

🌐 대시보드
• "대시보드" → 웹 링크 제공""",

        "고급": """🔧 고급 기능
━━━━━━━━━━━━━━━━━━━━
📋 메모 추가
• "방금꺼에 메모 추가해줘"
• "급건이라고 메모"

📑 복사
• "어제꺼 오늘로 복사"
• "월요일 작업 복사해줘"

📊 엑셀 일괄 등록
• 엑셀 파일 보내면 자동 등록
• 필수 컬럼: 날짜, 업체명, 분류, 단가

🔍 웹 검색
• "OO업체 정보 찾아줘"

💬 일반 대화
• 아무 질문이나 OK!
• AI가 이해하고 답변해요""",

        "전체": """📚 작업일지봇 사용법
━━━━━━━━━━━━━━━━━━━━

💬 자연어로 편하게 말하세요!
정보가 부족하면 물어보고,
대화하듯 완성해갑니다.

━━━━━━━━━━━━━━━━━━━━
📝 입력 예시
  "틸리언 하차 3만원"
  "나블리 양품화 20개 800원"

🔍 조회 예시
  "오늘 작업 보여줘"
  "이번주 틸리언"

✏️ 수정 예시
  "취소" / "수정해줘"
  "5만원으로 바꿔"

📊 통계 예시
  "이번달 총 얼마?"
  "지난주랑 비교"

━━━━━━━━━━━━━━━━━━━━
📖 상세 도움말
  "도움말 입력"
  "도움말 조회"
  "도움말 수정"
  "도움말 분석"
  "도움말 고급"
━━━━━━━━━━━━━━━━━━━━"""
    }
    
    return {
        "success": True,
        "topic": topic,
        "help_text": help_texts.get(topic, help_texts["전체"]),
        "message": f"도움말: {topic}"
    }


# ─────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────

def _log_work_history(
    log_id: int,
    action: str,
    log_data: Dict,
    변경자: str = None,
    변경사유: str = None,
    works_user_id: str = None
):
    """작업일지 변경 이력 기록"""
    try:
        with get_connection() as con:
            con.execute(
                """INSERT INTO work_log_history 
                   (log_id, action, 날짜, 업체명, 분류, 단가, 수량, 합계, 작성자, 변경자, 변경시간, 변경사유, works_user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    log_id, action,
                    log_data.get("날짜") or log_data.get("date"),
                    log_data.get("업체명") or log_data.get("vendor"),
                    log_data.get("분류") or log_data.get("work_type"),
                    log_data.get("단가") or log_data.get("unit_price"),
                    log_data.get("수량") or log_data.get("qty"),
                    log_data.get("합계") or (log_data.get("수량", 1) * log_data.get("단가", 0)),
                    log_data.get("작성자"),
                    변경자,
                    datetime.now().isoformat(),
                    변경사유,
                    works_user_id
                )
            )
            con.commit()
    except Exception as e:
        print(f"Warning: Could not log work history: {e}")


# ─────────────────────────────────────
# 연차 관련 도구 실행 함수
# ─────────────────────────────────────

def _check_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 현황 조회"""
    try:
        from backend.app.api.leave import bot_get_leave_summary
        year = args.get("year")
        result = bot_get_leave_summary(user_id)
        if "error" in result:
            return result
        if result.get("exempt"):
            return {"success": True, "message": f"{result['nickname']}님은 연차 관리 대상이 아닙니다."}

        summary = result
        lines = [
            f"📊 {summary['nickname']}님 연차 현황 ({summary['year']}년)",
            f"━━━━━━━━━━━━━━━━",
            f"📋 총 부여: {summary['total_hours']}시간 ({summary['total_days']}일)",
            f"✅ 사용:    {summary['used_hours']}시간 ({summary['used_days']}일)",
        ]
        if summary['pending_hours'] > 0:
            lines.append(f"⏳ 결재중:  {summary['pending_hours']}시간 ({summary['pending_days']}일)")
        color = "🔴" if summary['remaining_days'] < 0 else ("🟡" if summary['remaining_days'] < 3 else "🟢")
        lines.append(f"{color} 잔여:    {summary['remaining_hours']}시간 ({summary['remaining_days']}일)")
        lines.append(f"(입사일: {summary['join_date']})")
        return {"success": True, "message": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _apply_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 신청"""
    try:
        from backend.app.api.leave import bot_apply_leave
        leave_type = args.get("leave_type", "연차")
        start_date = args.get("start_date", "")
        end_date = args.get("end_date", start_date)
        reason = args.get("reason")

        if not start_date:
            return {"success": False, "error": "시작일을 알려주세요. (예: 7월 1일)"}

        result = bot_apply_leave(user_id, leave_type, start_date, end_date, reason)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def _cancel_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 취소"""
    try:
        from backend.app.api.leave import bot_cancel_leave
        request_id = args.get("request_id")
        if not request_id:
            return {"success": False, "error": "취소할 신청 번호(#ID)를 알려주세요."}
        return bot_cancel_leave(user_id, request_id)
    except Exception as e:
        return {"success": False, "error": str(e)}


def _approve_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 승인"""
    try:
        from backend.app.api.leave import bot_approve_leave
        request_id = args.get("request_id")
        if not request_id:
            return {"success": False, "error": "승인할 신청 번호(#ID)를 알려주세요."}
        comment = args.get("comment")
        return bot_approve_leave(user_id, request_id, comment)
    except Exception as e:
        return {"success": False, "error": str(e)}


def _reject_leave(args: Dict, user_id: str, user_name: str) -> Dict:
    """연차 반려"""
    try:
        from backend.app.api.leave import bot_reject_leave
        request_id = args.get("request_id")
        if not request_id:
            return {"success": False, "error": "반려할 신청 번호(#ID)를 알려주세요."}
        comment = args.get("comment")
        return bot_reject_leave(user_id, request_id, comment)
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_pending_approvals(args: Dict, user_id: str, user_name: str) -> Dict:
    """결재 대기 목록"""
    try:
        from backend.app.api.leave import bot_get_pending_approvals
        result = bot_get_pending_approvals(user_id)
        if "error" in result:
            return result

        if result["count"] == 0:
            return {"success": True, "message": "✅ 결재 대기 중인 연차가 없습니다."}

        lines = [f"📋 결재 대기 {result['count']}건", "━━━━━━━━━━━━━━━━"]
        for item in result["items"]:
            lines.append(
                f"#{item['request_id']} {item['requester']}({item['department']}) "
                f"{item['start_date']}~{item['end_date']} {item['leave_type']} {item['days']}일\n"
                f"   사유: {item['reason']}"
            )
        lines.append("━━━━━━━━━━━━━━━━")
        lines.append("승인: '승인 #번호' | 반려: '반려 #번호 사유'")
        return {"success": True, "message": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _clamp_limit(value, default: int = QUERY_DEFAULT_LIMIT, maximum: int = QUERY_MAX_LIMIT) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, maximum))


def _clamp_offset(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    return max(0, n)


def _sql_ident(name: str) -> str:
    return "[" + str(name).replace("]", "") + "]"


def _strip_secrets(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in row.items() if not _SECRET_KEY_RE.search(str(k))}


def _fetch_allowed(
    con,
    table: str,
    columns: List[str],
    *,
    where: str = "",
    params: tuple = (),
    order_by: Optional[str] = None,
    limit: int = QUERY_DEFAULT_LIMIT,
    offset: int = 0,
) -> Dict[str, Any]:
    allowed_tables = {
        "vendors", "aliases", "out_basic", "out_extra", "shipping_zone",
        "material_rates", "storage_rates", "vendor_storage", "vendor_charges",
        "repair_work_type", "repair_defect",
    }
    if table not in allowed_tables:
        return {"rows": [], "truncated": False, "limit": limit, "offset": offset}
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return {"rows": [], "truncated": False, "limit": limit, "offset": offset, "missing": True}
    real_cols = {c[1] for c in con.execute(f"PRAGMA table_info({_sql_ident(table)})")}
    cols = [c for c in columns if c in real_cols and not _SECRET_KEY_RE.search(c)]
    if not cols:
        return {"rows": [], "truncated": False, "limit": limit, "offset": offset}
    order_sql = ""
    if order_by and order_by in cols:
        order_sql = f" ORDER BY {_sql_ident(order_by)}"
    sql = f"SELECT {', '.join(_sql_ident(c) for c in cols)} FROM {_sql_ident(table)}"
    if where:
        sql += f" WHERE {where}"
    sql += f"{order_sql} LIMIT ? OFFSET ?"
    rows = con.execute(sql, (*params, limit, offset)).fetchall()
    out_rows = [_strip_secrets(dict(zip(cols, r))) for r in rows]
    return {
        "rows": out_rows,
        "truncated": len(out_rows) >= limit,
        "limit": limit,
        "offset": offset,
    }


def _lookup_vendors(args: Dict, user_id: str, user_name: str) -> Dict:
    q = (args.get("query") or "").strip()
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    where = "vendor IS NOT NULL"
    params: tuple = ()
    if q:
        where += " AND (vendor LIKE ? OR IFNULL(name, '') LIKE ?)"
        params = (f"%{q}%", f"%{q}%")
    with get_connection() as con:
        vendors = _fetch_allowed(
            con, "vendors", ["vendor", "name"],
            where=where, params=params, order_by="vendor",
            limit=limit, offset=offset,
        )
        alias_where = "alias IS NOT NULL AND vendor IS NOT NULL"
        alias_params: tuple = ()
        if q:
            alias_where += " AND (alias LIKE ? OR vendor LIKE ?)"
            alias_params = (f"%{q}%", f"%{q}%")
        aliases = _fetch_allowed(
            con, "aliases", ["alias", "vendor"],
            where=alias_where, params=alias_params, order_by="alias",
            limit=limit, offset=offset,
        )
    return {
        "success": True,
        "vendors": [r.get("vendor") for r in vendors["rows"] if r.get("vendor")],
        "aliases": aliases["rows"],
        "truncated": vendors["truncated"] or aliases["truncated"],
        "limit": limit,
        "offset": offset,
    }


_RATE_TABLE_COLS = {
    "out_basic": ["SKU 구간", "출고비"],
    "out_extra": ["항목", "단가"],
    "shipping_zone": ["요금제", "구간", "len_min_cm", "len_max_cm", "요금"],
    "material_rates": ["항목", "단가", "size_code"],
}
_RATE_TABLE_ORDER = {
    "out_basic": "SKU 구간",
    "out_extra": "항목",
    "shipping_zone": "요금제",
    "material_rates": "항목",
}


def _lookup_rate_tables(args: Dict, user_id: str, user_name: str) -> Dict:
    table = (args.get("table") or "").strip()
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    if table == "all" or not table:
        return {
            "success": False,
            "error": "테이블을 하나만 지정하세요: out_basic, out_extra, shipping_zone, material_rates",
            "allowed_tables": list(_RATE_TABLE_COLS.keys()),
        }
    if table not in _RATE_TABLE_COLS:
        return {"success": False, "error": "허용되지 않은 요금 테이블입니다.", "allowed_tables": list(_RATE_TABLE_COLS)}
    with get_connection() as con:
        fetched = _fetch_allowed(
            con, table, _RATE_TABLE_COLS[table],
            order_by=_RATE_TABLE_ORDER[table],
            limit=limit, offset=offset,
        )
    return {
        "success": True,
        "table": table,
        "rows": fetched["rows"],
        "truncated": fetched["truncated"],
        "limit": limit,
        "offset": offset,
    }


def _lookup_storage(args: Dict, user_id: str, user_name: str) -> Dict:
    vendor = (args.get("vendor") or "").strip()
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    result: Dict[str, Any] = {"success": True, "storage_rates": [], "vendor_storage": []}
    with get_connection() as con:
        rates = _fetch_allowed(
            con, "storage_rates",
            ["item_name", "unit_price", "unit", "description", "is_active"],
            order_by="item_name", limit=limit, offset=offset,
        )
        result["storage_rates"] = rates["rows"]
        vs_where = "1=1"
        vs_params: tuple = ()
        if vendor:
            vs_where = "vendor_id LIKE ? OR item_name LIKE ?"
            vs_params = (f"%{vendor}%", f"%{vendor}%")
        storage = _fetch_allowed(
            con, "vendor_storage",
            ["vendor_id", "item_name", "qty", "unit_price", "amount", "period", "remark", "is_active"],
            where=vs_where, params=vs_params, order_by="vendor_id",
            limit=limit, offset=offset,
        )
        result["vendor_storage"] = storage["rows"]
        result["truncated"] = rates["truncated"] or storage["truncated"]
        result["limit"] = limit
        result["offset"] = offset
    return result


def _lookup_vendor_charges_tool(args: Dict, user_id: str, user_name: str) -> Dict:
    vendor = (args.get("vendor") or "").strip()
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    where = "1=1"
    params: tuple = ()
    if vendor:
        where = "vendor_id LIKE ? OR item_name LIKE ?"
        params = (f"%{vendor}%", f"%{vendor}%")
    with get_connection() as con:
        fetched = _fetch_allowed(
            con, "vendor_charges",
            ["vendor_id", "item_name", "qty", "unit_price", "amount", "remark", "charge_type", "is_active"],
            where=where, params=params, order_by="vendor_id",
            limit=limit, offset=offset,
        )
    if fetched.get("missing"):
        return {"success": True, "charges": [], "message": "추가 청구 테이블이 없습니다."}
    return {
        "success": True,
        "charges": fetched["rows"],
        "truncated": fetched["truncated"],
        "limit": limit,
        "offset": offset,
    }


def _lookup_repair_catalog(args: Dict, user_id: str, user_name: str) -> Dict:
    """조회모드 전용. 카탈로그 테이블을 읽기만 하고 생성·시드하지 않는다."""
    limit = _clamp_limit(args.get("limit"))
    offset = _clamp_offset(args.get("offset"))
    with get_connection() as con:
        works = _fetch_allowed(
            con, "repair_work_type", ["작업명", "기본비용", "별칭"],
            order_by="작업명", limit=limit, offset=offset,
        )
        defects = _fetch_allowed(
            con, "repair_defect", ["불량명", "별칭"],
            order_by="불량명", limit=limit, offset=offset,
        )
    result = {
        "success": True,
        "work_types": works["rows"],
        "defects": defects["rows"],
        "truncated": bool(works.get("truncated") or defects.get("truncated")),
        "limit": limit,
        "offset": offset,
    }
    if works.get("missing") or defects.get("missing"):
        result["message"] = "수선 카탈로그 테이블이 없어 조회하지 않았습니다."
    return result


def get_db_context_for_ai() -> str:
    """AI에게 제공할 DB 컨텍스트 요약 (작업일지 + 인보이스)"""
    try:
        today = datetime.now()
        month_start = today.replace(day=1).strftime("%Y-%m-%d")
        month_end = today.strftime("%Y-%m-%d")
        
        with get_connection() as con:
            # 등록 업체
            vendors = [r[0] for r in con.execute(
                "SELECT vendor FROM vendors WHERE active != 'NO' OR active IS NULL ORDER BY vendor LIMIT 15"
            ).fetchall() if r[0]]
            
            # 자주 쓰는 작업종류
            work_types = [r[0] for r in con.execute(
                """SELECT 분류 FROM work_log WHERE 분류 IS NOT NULL
                   GROUP BY 분류 ORDER BY COUNT(*) DESC LIMIT 10"""
            ).fetchall() if r[0]]
            
            # 이번달 작업일지 통계
            stats = con.execute(
                f"SELECT COUNT(*), COALESCE(SUM(합계), 0) FROM work_log WHERE 날짜 BETWEEN ? AND ?",
                (month_start, month_end)
            ).fetchone()
            
            # 인보이스 총계
            inv_total = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoices"
            ).fetchone()
            
            # 이번달 인보이스
            inv_month = con.execute(
                "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoices WHERE created_at >= ?",
                (month_start,)
            ).fetchone()
            
            # 업체별 인보이스 누적 (상위 5개)
            inv_by_vendor = con.execute(
                """SELECT v.vendor, COUNT(*) as cnt, SUM(i.total_amount) as total
                   FROM invoices i
                   LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                   WHERE v.vendor IS NOT NULL
                   GROUP BY v.vendor ORDER BY total DESC LIMIT 5"""
            ).fetchall()
            
            # 최근 인보이스 3건
            recent_inv = con.execute(
                """SELECT v.vendor, i.total_amount, i.period_from, i.period_to
                   FROM invoices i
                   LEFT JOIN vendors v ON i.vendor_id = v.vendor_id
                   ORDER BY i.created_at DESC LIMIT 3"""
            ).fetchall()
        
        repair_ctx = ""
        try:
            from backend.app.services import repair_catalog
            repair_ctx = repair_catalog.catalog_context_for_ai()
        except Exception:
            pass

        # 컨텍스트 구성
        context_lines = [
            "## 현재 DB 정보 (참고용, 특정 기간 조회는 반드시 도구 호출!)",
            f"- 등록 업체: {', '.join(vendors[:10])}{'...' if len(vendors) > 10 else ''}",
            f"- 자주 쓰는 작업: {', '.join(work_types)}",
            f"- 이번달({month_start}~{month_end}) 작업일지: {stats[0]}건, {stats[1]:,}원",
            f"- 오늘: {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})",
            "",
            "## 인보이스 정보 (전체 누적, 특정 기간은 get_invoice_stats 호출!)",
            f"- 전체 누적 인보이스: {inv_total[0]}건, 총 {inv_total[1]:,.0f}원",
            "",
            "⚠️ 특정 월/기간 데이터 요청 시: 반드시 get_work_log_stats 또는 get_invoice_stats 호출!",
            "⚠️ 이 컨텍스트 데이터를 특정 기간 답변에 사용하지 마세요!",
        ]
        if repair_ctx:
            context_lines.extend(["", "## 수선 마스터 (수선 건만. 하차/입고는 작업일지)", repair_ctx])
        
        return "\n".join(context_lines)
    except Exception as e:
        return f"## DB 정보 로드 오류: {e}"

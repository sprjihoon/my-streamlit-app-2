"""Tool schemas and mode exposure. Order matches the original registry."""
import json

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
                    },
                    "worker": {
                        "type": "string",
                        "description": "작업자"
                    },
                    "remark": {
                        "type": "string",
                        "description": "비고"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_repair_logs",
            "description": "조건에 맞는 수선일지를 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "product": {"type": "string"},
                    "work_type": {"type": "string"},
                    "defect": {"type": "string"},
                    "worker": {"type": "string"},
                    "barcode": {"type": "string"},
                    "remark": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer", "default": 20}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_repair_log_stats",
            "description": "수선일지 건수·수량·금액을 집계합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "product": {"type": "string"},
                    "work_type": {"type": "string"},
                    "defect": {"type": "string"},
                    "worker": {"type": "string"},
                    "barcode": {"type": "string"},
                    "remark": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "group_by": {"type": "string"},
                    "metric": {"type": "string"},
                    "sort": {"type": "string"},
                    "limit": {"type": "integer"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_work_price",
            "description": "작업일지 단가 이력을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "work_type": {"type": "string"}
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
                    },
                    "work_type": {"type": "string"},
                    "worker": {"type": "string"},
                    "remark": {"type": "string"},
                    "group_by": {"type": "string"},
                    "metric": {"type": "string"},
                    "sort": {"type": "string"},
                    "limit": {"type": "integer"}
                }
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
            "description": "수선 제품+작업의 최근 비용, 없으면 업체+작업, 없으면 기본비용을 조회합니다. 가격 없이 수선 작업만 왔을 때 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "work_type": {"type": "string"},
                    "product": {"type": "string", "description": "제품명"}
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
    "search_repair_logs",
    "get_repair_log_stats",
    "lookup_work_price",
    "lookup_repair_price",
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


from .validation import _apply_schema_guard

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

# NAVER WORKS 업무봇 기준선

기준 커밋: `84160d38f94fb6dc70b30052e72f93f36639382f`

작성 기준일: 2026-09-05

이 문서는 탐색을 빠르게 하기 위한 기준선이다. 구현 전에 현재 브랜치의 코드와 diff를 확인하고, 코드가 달라졌으면 현재 코드를 우선한다.

## 현재 라우팅

1. `backend/app/api/naver_works_webhook.py`가 메시지를 받는다.
2. 현재 사용자 문장을 저장하기 전에 방 단위 과거 이력을 가져온다.
3. `parse_mode_command()`가 모드 명령을 GPT보다 먼저 처리한다.
4. `idle`은 안내만, `repair`는 기존 `repair_bot.py`, `journal`과 `query`는 `AIParser`로 보낸다.
5. 사진은 `repair` 모드일 때만 다운로드해 수선 inbox로 전달한다.
6. 엑셀은 모드와 별개인 기존 업로드 경로이며 서버 내부 `trusted_source="excel_upload"`로 `save_work_log`만 허용한다.

## 모드와 도구

| 모드 | 역할 | 쓰기 |
| --- | --- | --- |
| `idle` | 모드 선택 안내 | 금지 |
| `journal` | 작업일지 입력·보완·수정 | 허용된 일지 도구만 |
| `repair` | 기존 수선 텍스트·사진 흐름 | GPT 업무 도구 사용 안 함 |
| `query` | 작업·인보이스·업체·요금·보관·수선 카탈로그 조회 | 금지 |

모드 저장, pending, 사진 inbox의 범위는 `(user_id, channel_id)`다. 개인방은 `channel_id`가 없을 때 `user_id`를 사용한다.

## 주요 파일

| 파일 | 책임 | 변경 원칙 |
| --- | --- | --- |
| `backend/app/api/naver_works_webhook.py` | 입력 종류와 모드 라우팅, 공통 응답 | 오케스트레이션만 변경 |
| `backend/app/services/bot_mode.py` | 모드 명령·저장·접두어 | 결정적 명령 유지 |
| `backend/app/services/ai_parser.py` | 일지·조회 프롬프트와 멀티턴 | 기본값 `idle`, current message 1회 |
| `backend/app/services/bot_tools.py` | 도구 schema, 인자 검증, 모드별 실행 가드 | 기존 실행 본체 재사용 |
| `backend/app/services/conversation_state.py` | 방 단위 pending·history, 만료 | `(user_id, channel_id)` 유지 |
| `backend/app/services/repair_bot.py` | 수선 대화, 사진 inbox·flush | 저장·사진 판독 본체 보존 |
| `backend/app/api/repair_log.py` | 수선 API와 60일 사진 정리 | legacy/v2 정리 구분 유지 |

## 보호할 기존 기능

사용자가 해당 작업에서 명시적으로 변경해 달라고 하지 않으면 아래를 재작성하지 않는다.

- `bot_tools.py`의 `_save_work_log`, `_save_multiple_work_logs`, `_lookup_price_from_history` 실행 본체
- 업체 검증, `vendors`, `aliases`, `_map_vendor_alias`, `_resolve_vendor`
- `logic/invoice_calc.py`, `backend/app/api/calculate.py`, `backend/app/api/billing_invoice.py`
- `shipping_zone`, `storage_rates`, 업체별 청구와 기존 계산 공식
- `process_excel_upload`, `logic/upload.py`
- `repair_bot.py`의 기존 저장 흐름, `insert_repair_log_record`, `barcode_decode.classify_photos`
- 프론트엔드와 기존 업무 테이블 데이터

## 유지해야 할 안전장치

- `execute_tool()`은 mode 누락·오타·`idle`·`query`·`repair`에서 허용되지 않은 쓰기를 거부한다.
- `trusted_source`는 호출 코드가 직접 넘기며, GPT schema에 포함하지 않는다.
- 조회 도구는 명시한 컬럼, limit, offset만 사용하고 비밀 컬럼을 반환하지 않는다.
- 사진 inbox와 비동기 timer key는 사용자와 방을 함께 사용한다.
- 모드 전환은 해당 방 pending과 미완료 inbox만 정리한다. 저장 완료 업무 데이터·사진은 삭제하지 않는다.
- GPT에 넘기는 현재 사용자 문장은 정확히 한 번이고, 응답 접두어도 첫 줄에 한 번이다.

## 다음 기능의 대표 문제

수선 저장 직후 사용자가 `직전내용수정`, `방금 거 수정`, `금액만 2천원으로 바꿔`라고 말했을 때 새 수선 접수로 라우팅하거나 사진 3장을 다시 요구하면 안 된다.

권장 흐름:

1. 저장 성공 결과의 `repair_record_id`를 방 단위 `last_saved` 컨텍스트에 남긴다.
2. 공통 intent가 `action=update`, `target.type=last_saved`로 분류한다.
3. 서버가 해당 ID의 존재, 도메인, 사용자·방 범위, 수정 가능한 field를 검증한다.
4. 변경 전·후를 보여 주고 확인받는다.
5. 기존 수선 update 함수 또는 얇은 adapter를 실행한다.
6. 성공 응답에 같은 record ID를 유지해 연속 정정이 가능하게 한다.

대상이 없거나 여러 후보가 있으면 사진 접수로 되돌아가지 말고 대상을 명확히 묻는다.

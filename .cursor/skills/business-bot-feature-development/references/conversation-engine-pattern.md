# 공통 대화 엔진 패턴

## 원칙

자연어의 경우의 수를 문장 목록으로 해결하지 않는다. 변하기 쉬운 표현과 변하지 않는 업무 규칙을 분리한다.

| 층 | 책임 | 예시 |
| --- | --- | --- |
| 코드 명령 게이트 | 완전히 결정적인 고위험 명령 | 모드 시작·종료·현재 모드 |
| Intent parser | 자유로운 문장을 공통 계약으로 변환 | `직전 거 가격 바꿔` → update |
| State reducer | 현재 상태와 이벤트로 다음 상태 결정 | awaiting_fields → awaiting_confirmation |
| Target resolver | 수정·삭제할 정확한 기록 결정 | last_saved → record ID |
| Server validator | mode·권한·타입·필수값·범위 검증 | query 쓰기 거부 |
| Domain adapter | 기존 저장·조회 함수를 호출 | repair update adapter |
| Reply renderer | 일관된 확인·성공·실패 문구 | `[수선모드] ...` |

표현 사전은 업체명 별칭, 작업명, 단위, 도메인 용어처럼 실제로 관리할 가치가 있는 것만 둔다. `고쳐줘`, `바꿔`, `수정`, `아까 거` 같은 일반 문장을 모두 코드에 나열하지 않는다.

## Canonical intent

```json
{
  "version": "1.0",
  "domain": "repair",
  "action": "update",
  "target": {
    "type": "last_saved",
    "record_id": null,
    "filters": {}
  },
  "fields": {
    "work_type": "구멍",
    "qty": 1,
    "unit_price": 1500
  },
  "confidence": 0.97,
  "missing_fields": [],
  "needs_confirmation": true,
  "reason": "직전 저장 기록의 작업과 수량 수정"
}
```

### 권장 enum

- `domain`: `journal`, `repair`, `query`, `invoice`, 기능별 확장값
- `action`: `create`, `update`, `delete`, `cancel`, `confirm`, `clarify`, `show_last`, `help`
- `target.type`: `draft`, `last_saved`, `by_id`, `by_filter`, `none`

`fields`는 domain별 schema를 분리한다. 모델이 임의 컬럼명, SQL, 함수명, `trusted_source`, 권한 값을 만들 수 없게 한다.

## 처리 순서

1. 공백·단위·숫자를 가볍게 정규화하되 원문도 보존한다.
2. 코드 명령을 먼저 확인한다.
3. 현재 mode, pending, last_saved ID, 최근 결과 요약을 최소 컨텍스트로 구성한다.
4. 모델에서 구조화 intent 하나를 받는다. 복합 요청은 서버가 허용한 경우에만 여러 action으로 분리한다.
5. schema와 allowlist를 서버에서 다시 검증한다.
6. target을 실제 ID로 resolve한다.
7. 필수값이 없으면 `awaiting_fields`, 대상이 모호하면 `clarify`, 쓰기면 보통 `awaiting_confirmation`으로 전이한다.
8. 확인 후 domain adapter를 한 번 실행한다.
9. 성공 ID, 실행 요약, undo 가능 여부를 상태와 audit log에 남긴다.
10. reply renderer가 사용자 문구를 만든다.

## 상태 모델

```text
idle
  → drafting
  → awaiting_fields
  → awaiting_confirmation
  → executing
  → completed

어느 단계에서든 cancel → cancelled
만료 시간 경과 → expired
```

전이는 pure reducer 또는 한 서비스에 모은다. 여러 handler가 pending row를 제각각 수정하면 동일 문장이 다른 결과를 내기 쉽다.

## 대상 기록 규칙

- 저장 성공 시 반드시 생성·수정된 record ID를 반환한다.
- `last_saved`는 도메인별로 구분한다. 마지막 작업일지와 마지막 수선일지는 같은 포인터가 아니다.
- `방금`, `직전`, `아까`는 현재 `(user_id, channel_id, domain)`의 포인터에서 찾는다.
- ID를 찾은 후에도 테이블, 삭제 여부, 접근 범위, 수정 가능 상태를 검증한다.
- 시간이나 업체 필터로 여러 건이 나오면 후보 2~5개만 보여 주고 선택받는다.
- `draft`와 `last_saved`를 절대 혼용하지 않는다.

## 자연어 평가 예시

| 사용자 문장 | 기대 결과 |
| --- | --- |
| `직전내용수정` | update + last_saved, 바꿀 field 질문 |
| `방금 거 금액 2천원으로` | update + last_saved + unit_price=2000, 확인 |
| `구멍 아니고 지퍼야` | pending 또는 last_saved의 work_type 정정 |
| `그거 1건 말고 3건` | qty만 3으로 유지, 다른 field 보존 |
| `아까 틸리언 하차 삭제` | 후보 resolve 후 삭제 확인 |
| `아니 취소` | 실행 전 pending만 취소, 저장 완료 데이터 불변 |
| `네` | awaiting_confirmation일 때만 confirm |
| `사진 다시 보낼게` | 수선 pending 상태에 맞는 photo action, 다른 모드에서는 다운로드 금지 |

발화 예시는 테스트 데이터로 늘릴 수 있지만, 모든 예시가 같은 canonical contract와 서버 검증을 통과해야 한다.

## 확인 응답

쓰기 전에 다음을 한 화면에 보여 준다.

- 대상: ID와 사람이 알아볼 수 있는 요약
- 변경 전
- 변경 후
- 실행될 action
- `확인` / `취소` 방법

확인 토큰은 현재 방의 pending action과 연결하고 짧게 만료시킨다. 다른 방의 `네`가 실행하지 못하게 한다.

## 실패 경로

- 낮은 confidence: action 후보를 추측 실행하지 말고 한 가지 질문을 한다.
- refusal·timeout·invalid JSON·schema mismatch: 사용자에게 재입력 방법을 안내하고 write는 0건이어야 한다.
- adapter 오류: 트랜잭션 rollback 후 재시도 가능 상태를 명확히 한다.
- 중복 웹훅: event ID 또는 idempotency key로 한 번만 실행한다.
- 부분 사진 업로드: 저장 완료로 처리하지 않고 현재 수신 장수와 필요한 장수를 안내한다.

## 프롬프트 골격

```text
역할: 사용자의 자연어를 허용된 업무 intent JSON으로만 구조화한다.

현재 컨텍스트:
- mode: {mode}
- state: {state}
- domain: {domain}
- last_saved_summary: {summary_without_secrets}

규칙:
1. 제공된 enum과 field 외에는 만들지 않는다.
2. DB 쓰기, SQL, 권한 판단, 대상 ID 확정은 하지 않는다.
3. 정보가 없으면 missing_fields에 넣는다.
4. 대상이 모호하면 action=clarify로 반환한다.
5. 이유는 짧게 쓰고 사용자에게 없는 사실은 추측하지 않는다.
```

지원 모델에서는 strict Structured Outputs를 사용한다. 동시에 여러 tool call이 구조 보장을 깨뜨릴 수 있는 구성이라면 구조화 분류 단계의 parallel tool calls를 끈다. 어떤 모델을 쓰더라도 서버 검증은 생략하지 않는다.

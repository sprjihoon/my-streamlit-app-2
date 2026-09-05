# 업무봇 기능 명세 양식

새 기능마다 이 문서를 전부 길게 채울 필요는 없다. 구현 판단에 영향을 주는 항목만 채우고, 모르는 사실은 추측하지 않는다.

## 1. 기본 정보

| 항목 | 작성 내용 |
| --- | --- |
| 기능명 |  |
| 상태 | 초안 / 검토 / 승인 / 구현 / 검증 / 완료 |
| 요청자·담당자 |  |
| 대상 릴리스 |  |
| 관련 이슈·대화·화면 |  |
| 필수 기능 여부 | 필수 / 선택 |

### 문제

- 지금 사용자가 하려는 일:
- 현재 실패하거나 불편한 장면:
- 이 기능을 만들지 않으면 생기는 문제:

### 목표와 성공 기준

- 사용자 가치 한 문장:
- 성공 지표:
- 통과해야 할 실제 대화:
- 성능·비용·응답시간 기준:

### 범위 밖

- 이번 작업에서 하지 않는 것:
- 다음 단계로 미루는 것:

## 2. 보존 계약

| 구분 | 파일·함수·테이블 | 허용 작업 |
| --- | --- | --- |
| 절대 보존 |  | 호출만 / 읽기만 |
| adapter로 재사용 |  | 얇은 래퍼 추가 |
| 수정 가능 |  | orchestration만 |
| 신규 추가 |  | 파일·테이블·테스트 |

기존 데이터 마이그레이션 여부:

운영 배포·키·인증정보 변경 여부:

## 3. 대화 계약

| 항목 | 결정 |
| --- | --- |
| domain | journal / repair / query / invoice / 기타 |
| action | create / update / delete / cancel / confirm / show_last / help |
| target | draft / last_saved / by_id / by_filter / none |
| 허용 fields |  |
| 필수 fields |  |
| 확인이 필요한 조건 |  |
| 자동 실행 가능한 조건 |  |
| 권한·mode 조건 |  |
| 성공 응답 |  |
| 실패·보완 응답 |  |

### 대표 발화

문장 목록을 코드로 옮기기 위한 표가 아니다. 같은 의미가 공통 action으로 잘 접히는지 평가하는 데이터다.

| 의미 범주 | 사용자 예시 | 기대 action | 기대 target | 기대 fields |
| --- | --- | --- | --- | --- |
| 정규 표현 |  |  |  |  |
| 짧은 표현 |  |  |  |  |
| 오타·띄어쓰기 |  |  |  |  |
| 문맥 의존 |  |  |  |  |
| 정정 |  |  |  |  |
| 취소 |  |  |  |  |
| 모호한 대상 |  | clarify |  |  |
| 범위 밖 |  | reject / help | none |  |

## 4. 상태 전이

| 현재 상태 | 이벤트 | 다음 상태 | 서버 동작 | 사용자 응답 |
| --- | --- | --- | --- | --- |
| idle |  |  |  |  |
| drafting |  |  |  |  |
| awaiting_fields |  |  |  |  |
| awaiting_confirmation |  |  |  |  |
| executing |  |  |  |  |
| completed |  |  |  |  |
| cancelled / expired |  |  |  |  |

상태 키: `(user_id, channel_id)`

만료 시간과 만료 후 동작:

재시작·중복 웹훅 처리:

## 5. 구조화 출력

```json
{
  "version": "1.0",
  "domain": "repair",
  "action": "update",
  "target": {"type": "last_saved", "record_id": null},
  "fields": {"work_type": "구멍", "qty": 1},
  "confidence": 0.96,
  "missing_fields": [],
  "needs_confirmation": true,
  "reason": "직전에 저장한 수선일지 수정 요청"
}
```

- `domain`, `action`, `target.type`은 enum인가?
- `fields`는 도메인 allowlist인가?
- `additionalProperties: false`인가?
- refusal, finish reason, timeout, schema 오류가 분리되는가?
- 서버가 타입, 범위, mode, 권한, 대상 ID를 다시 검증하는가?

## 6. 실행 adapter

| 항목 | 내용 |
| --- | --- |
| adapter 이름 |  |
| 호출할 기존 함수 |  |
| 입력 변환 |  |
| 서버 검증 |  |
| 트랜잭션 경계 |  |
| idempotency 기준 |  |
| audit 정보 |  |
| 반환할 record ID |  |

## 7. 실패와 복구

| 실패 | 데이터 변경 여부 | 복구·안내 |
| --- | --- | --- |
| 필수값 누락 | 없음 |  |
| 대상 모호 | 없음 |  |
| mode·권한 위반 | 없음 |  |
| 모델 거부·timeout | 없음 |  |
| DB 오류 | rollback |  |
| 중복 이벤트 | 한 번만 반영 |  |
| 사진 일부 실패 |  |  |

## 8. 테스트와 완료 조건

- 신규 정상 시나리오:
- 누락값 보완:
- 수정·취소·재시도:
- 동일 사용자 다른 방 격리:
- 읽기 모드 쓰기 차단:
- 사진 모드 게이트:
- 기존 인보이스·업체 매칭·요금·업로드 회귀:
- 실제 DB·업로드 폴더 불변:
- `compileall`, 전체 `pytest`, `git diff --check`:

완료 정의:

승인 후 별도로 할 일: push / PR / main 병합 / 배포 / 마이그레이션

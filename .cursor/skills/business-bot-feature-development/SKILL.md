---
name: business-bot-feature-development
description: NAVER WORKS·GPT·내부 전산 업무봇에 자연어 기반 저장, 조회, 수정, 삭제, 사진, 확인 대화 기능을 안전하게 추가하거나 변경할 때 사용한다. 기존 인보이스·업체 매칭·요금·업로드·수선 저장 기능을 보존하면서 action, state, target, guard, test 중심으로 설계하고 구현한다.
metadata:
  version: "1.0.0"
  owner: "Spring Fulfillment"
---

# 업무봇 기능 개발

사용자가 다양한 문장을 말하더라도 문장별 `if/elif`를 계속 추가하지 않는다. 자연어는 소수의 공통 `action`과 허용된 `fields`로 구조화하고, 실제 검증·확인·저장·수정·삭제는 서버 코드가 책임지게 한다.

## 시작할 때

1. 현재 코드와 [NAVER WORKS 봇 기준선](references/naver-works-bot-context.md)을 비교한다. 문서와 코드가 다르면 현재 코드를 사실로 삼고 차이를 작업 계획에 적는다.
2. 요청을 [기능 명세 양식](references/feature-spec-template.md)에 맞춰 짧게 정리한다. 구현 결과가 달라지는 질문만 사용자에게 묻는다.
3. 자연어 분류, 대상 기록 결정, 필수값, 확인 조건, 실행 adapter, 실패 복구, 테스트를 먼저 확정한다.
4. 변경 전 관련 테스트를 실행하고 결과를 기록한다. 테스트는 임시 DB와 임시 업로드 폴더만 사용한다.

자연어·상태 설계가 필요한 경우 [대화 엔진 패턴](references/conversation-engine-pattern.md)을 읽는다. 구현과 완료 판정에는 [검증 체크리스트](references/verification-checklist.md)를 읽는다. 근거를 다시 확인해야 할 때만 [공식 참고 자료](references/official-references.md)를 읽는다.

## 핵심 계약

- 모드 시작·종료·현재 모드처럼 결과가 명확하고 위험도가 높은 명령은 GPT보다 먼저 코드가 처리한다.
- GPT는 사용자의 의도를 구조화할 뿐 DB에 직접 쓰지 않는다.
- 모델 출력은 가능한 경우 strict Structured Outputs와 JSON Schema를 사용한다. 허용하지 않은 action·field·target은 서버가 거부한다.
- 쓰기 전 서버가 `mode`, `user_id`, `channel_id`, 권한, 필수값, 타입, 범위, 정확한 대상 ID를 다시 검증한다.
- `직전 내용 수정`, `방금 것 삭제` 같은 명령은 현재 대화 초안이 아니라 마지막으로 저장된 정확한 기록 ID에 묶는다. 대상이 모호하면 후보를 보여 주고 확인받는다.
- 확인 단계에서는 실행될 변경 전·후를 미리 보여 준다. 확인 전에는 DB와 저장 완료 사진을 바꾸지 않는다.
- `query`는 읽기 전용이다. `idle`, 잘못된 mode, mode 누락은 쓰기를 거부한다.
- `trusted_source`는 서버 내부 인자다. 사용자 문장이나 GPT tool arguments에서 읽지 않는다.
- 사용자와 방의 상태는 항상 `(user_id, channel_id)`로 격리한다.
- 사진은 허용된 모드에서만 다운로드한다. 비동기 처리도 원래 `channel_id`로 응답한다.
- 같은 사용자 메시지를 GPT 이력에 중복 삽입하지 않고, 응답 접두어도 한 번만 붙인다.
- 모델 거부, timeout, 잘못된 JSON, schema 오류, 낮은 확신은 정상 실패 경로로 처리하며 쓰기 작업을 실행하지 않는다.
- 환경변수, API 키, 비밀번호, private key, 원본 인증정보는 프롬프트·로그·조회 결과·커밋에 넣지 않는다.

## 구현 순서

1. **Intent contract**: `domain`, `action`, `target`, `fields`, `confidence`, `missing_fields`, `needs_confirmation`을 정의한다.
2. **Deterministic gate**: 모드 명령, 취소, 명시적 확인처럼 코드가 확정할 수 있는 입력을 GPT 앞에서 처리한다.
3. **State reducer**: 상태 전이를 한 곳에서 결정한다. 임의 분기에서 pending 상태를 직접 바꾸지 않는다.
4. **Target resolver**: 저장 완료 결과의 ID를 대화 컨텍스트에 남기고, 수정·삭제 시 ID와 소유 범위를 재검증한다.
5. **Domain adapter**: 기존 검증·계산·저장 함수를 얇게 감싼다. 핵심 실행 함수를 복제하거나 다시 작성하지 않는다.
6. **Preview and confirmation**: 변경 내용을 사람이 읽을 수 있게 보여 주고 승인 후에만 adapter를 실행한다.
7. **Reply renderer**: 모드 접두어, 성공, 보완 요청, 취소, 실패 응답을 일관된 형식으로 만든다.
8. **Tests**: 대표 문장보다 불변조건을 검증한다. 동의어, 누락값, 다중 방, 중복 이벤트, 실패·재시도, 기존 기능 회귀를 포함한다.

## 기존 기능 보존 원칙

- 인보이스 계산, 업체 매칭·별칭, 요금 공식, 엑셀 업로드 본체, 작업일지 저장 본체, 수선 저장·사진 판독 본체는 사용자가 명시적으로 요청하지 않는 한 재작성하지 않는다.
- 기존 함수의 앞뒤에 orchestration, validation, adapter를 추가하는 방식을 우선한다.
- 변경 대상이 보호 영역을 건드릴 수밖에 없다면 코드를 수정하기 전에 이유, 최소 범위, 회귀 테스트를 사용자에게 제시한다.
- 한 번에 전체 봇을 재작성하지 않는다. 공통 엔진과 한 개 도메인 adapter부터 연결해 실제 대화로 검증한다.

## 완료 보고

다음 순서로 짧고 검증 가능하게 보고한다.

1. 결과와 사용자에게 달라지는 점
2. 변경 파일과 핵심 설계
3. 보호한 기존 기능
4. 실행한 테스트와 실제 결과
5. DB·업로드·민감정보 불변 여부
6. 알려진 한계와 다음 후보
7. 커밋 SHA와 현재 브랜치

push, PR, `main` 병합, 운영 배포, DB 마이그레이션 실행은 사용자가 각각 명시적으로 요청한 범위에서만 한다.

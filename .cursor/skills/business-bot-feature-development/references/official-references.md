# 공식 참고 자료

확인일: 2026-09-05

이 자료의 원문을 복제하지 않고, 업무봇 템플릿에 적용한 구조적 원칙만 정리했다. 실제 구현에서는 현재 저장소 코드와 운영 규칙이 최우선이다.

## Cursor

- [Agent Skills](https://cursor.com/docs/skills): 프로젝트 스킬은 `.cursor/skills/` 또는 `.agents/skills/`에 두며 Git으로 버전 관리할 수 있다. Cursor가 자동 발견하고 `/` 메뉴에서 직접 실행할 수 있다.
- [Rules](https://cursor.com/docs/rules): `.cursor/rules/*.mdc`는 코드베이스 규칙과 파일 범위별 지침에 적합하다. 이 템플릿은 절차와 참고 자료가 필요하므로 Agent Skill로 구성했다.
- [Prompting agents](https://cursor.com/docs/agent/prompting): 파일·폴더·Git diff를 `@`로 첨부할 수 있고, Skill을 Custom Mode로 유지할 수 있다.

## 기능 명세와 입력 품질

- [Atlassian Product requirements template](https://www.atlassian.com/software/confluence/templates/product-requirements): 목표·성공 지표, 가정, supporting artifacts, open questions, out-of-scope를 한 명세 안에서 관리하는 구조를 참고했다.
- [GitHub Issue form syntax](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms): 입력 유형, 필수값, validation을 명시해 요청 품질을 일정하게 만드는 원칙을 참고했다.

## 모델 출력 계약

- [OpenAI Structured Outputs](https://openai.com/index/introducing-structured-outputs-in-the-api/): JSON Schema 기반 구조화 출력, strict 제약, refusal과 완료 상태를 별도 실패 경로로 다루는 원칙을 참고했다.

## 문서 시각 체계

- [Microsoft Fluent 2 Design tokens](https://fluent2.microsoft.design/design-tokens): 색상·타이포그래피·간격을 의미 기반 token으로 일관되게 쓰는 원칙을 참고했다.
- [Microsoft Fluent 2 Layout](https://fluent2.microsoft.design/layout): 충분한 여백과 정보 위계, 4단위 계열 간격 원칙을 참고했다.
- [Microsoft Fluent 2 Typography](https://fluent2.microsoft.design/typography): 본문과 큰 제목의 대비 및 읽기 쉬운 계층을 참고했다.

## 이 템플릿에 반영한 결론

1. 문장 예측 목록보다 action·field·state·target 계약을 먼저 만든다.
2. 모델 출력과 서버 실행 사이에 schema, 권한, 범위, 확인 guard를 둔다.
3. 기능의 목표·성공 기준·범위 밖·보존 영역을 구현 전에 명시한다.
4. 테스트는 문구 자체보다 DB 불변, 방 격리, 정확한 대상 ID, 중복 실행 방지 같은 불변조건을 검증한다.
5. 상세 자료는 references로 분리하고, Cursor는 작업에 필요한 문서만 점진적으로 읽게 한다.

# 구현·회귀 검증 체크리스트

## 변경 전

- 현재 브랜치, HEAD, 원격과의 차이를 확인한다.
- 사용자 로컬 변경과 추적 중인 DB·업로드·생성 파일을 확인하고 건드리지 않는다.
- 변경 파일 후보와 보호 파일을 나눈다.
- 관련 기존 테스트를 먼저 실행해 기준선을 기록한다.
- 테스트가 운영 `billing.db`나 실제 업로드 폴더를 가리키지 않는지 확인한다.

## 대화 계약 테스트

- 정규 문장, 축약, 띄어쓰기, 오타가 같은 action으로 분류된다.
- 업체명·작업명 별칭이 기존 resolver를 통과한다.
- 누락값을 보완해도 처음 입력한 수량·금액·대상은 보존된다.
- `네`, `아니`, `취소`는 해당 방의 현재 상태에서만 의미를 갖는다.
- `직전`, `방금`, `아까`가 도메인별 저장 완료 ID에 연결된다.
- 여러 후보면 실행 없이 선택을 요청한다.
- 한 메시지의 복합 요청을 지원하지 않는 경우 부분 실행하지 않는다.

## 쓰기 안전 테스트

- `idle`, `query`, `repair`, mode 누락, mode 오타에서 GPT 업무 쓰기가 0건이다.
- Excel의 신뢰 경로는 `save_work_log`만 허용한다.
- 사용자 문장이나 tool arguments의 `trusted_source`는 무시·거부한다.
- 확인 전 DB 행과 저장 완료 사진이 불변이다.
- 잘못된 field, 타입, 범위, ID, 다른 사용자·방 대상은 거부한다.
- 중복 webhook과 재시도에서 한 번만 반영된다.
- adapter 예외 시 transaction이 rollback된다.

## 방·상태·사진 테스트

- 같은 사용자의 A방·B방 pending, history, last_saved, inbox가 서로 섞이지 않는다.
- A방 모드 종료가 B방 state와 timer를 지우지 않는다.
- 만료는 해당 방에만 적용된다.
- 수선 이외 모드 사진은 다운로드조차 하지 않는다.
- 비동기 사진 응답은 원래 방으로 가며 접두어가 한 번만 붙는다.
- 현재 사용자 메시지는 GPT messages와 conversation history에 각각 한 번만 존재한다.

## 기존 기능 회귀

- 인보이스 배송구간·수량·금액 계산
- 업체 매칭과 별칭
- 요금·보관료·추가 청구
- Excel 업로드 정상·일부 실패·전체 실패
- 작업일지 단건·다건 저장
- 수선 사진 분류·저장
- 조회 limit, 컬럼 allowlist, 비밀 컬럼 제외

## 권장 명령

저장소의 실제 환경과 테스트 문서를 먼저 확인한다.

```bash
python -m compileall backend/app
python -m pytest -q tests/test_bot_modes.py tests/test_bot_hardening.py
python -m pytest -q
git diff --check
git status --short
```

테스트가 없는 환경에서 성공으로 간주하지 않는다. 실행 불가 이유와 대체 검증을 분리해 보고한다.

## 산출물 불변 확인

테스트 전후로 필요하면 다음을 비교한다.

- 운영 또는 로컬 실제 `billing.db` 해시와 수정시각
- 실제 `data/uploads` 파일 수와 경로
- `.env`, private key, API key의 Git 포함 여부
- `frontend/.next`, `node_modules`, `__pycache__`, `*.pyc` 포함 여부

테스트 fixture는 임시 DB와 임시 업로드 디렉터리를 사용하고, 테스트 실패 시에도 정리되게 한다.

## 완료 보고 양식

```text
결과:
- 사용자가 할 수 있게 된 일

변경:
- 파일 / 책임 / 핵심 이유

보존:
- 손대지 않은 기존 기능·함수·데이터

검증:
- 명령 → 실제 결과

위험·제한:
- 남은 경우의 수와 다음 개선 후보

Git:
- branch / commit SHA / push 여부

배포:
- PR / main 병합 / 운영 배포 여부
```

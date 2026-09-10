"""
treat_status_from_tracking_text 단위 테스트.

실제 service.epost.go.kr HTML 구조:
  - 날짜/시간이 별도 TD: <td>2026.09.10</td><td>07:55</td><td>위치</td><td>상태</td>
  - 이력은 오름차순(오래된 것 먼저) → 마지막 행이 최신
  - 진행 단계 레이블로 '배달완료' 등이 span/div에 항상 존재
"""
import sys
sys.path.insert(0, '.')
from backend.app.services.epost.fields import treat_status_from_tracking_text


def make_table(*rows):
    """rows: [(날짜, 시각, 위치, 상태), ...] 오래된 순"""
    trs = ""
    for date, time, loc, stat in rows:
        trs += f"""
        <tr>
          <td>{date}</td><td>{time}</td>
          <td>{loc}</td><td>{stat}</td>
        </tr>"""
    return f"""
    <div class="step_track">
      <span>집하</span><span>이동중</span><span>배달중</span>
      <span class="last">배달완료</span>
    </div>
    <table class="table_d">
      <thead><tr><th>배송시간</th><th></th><th>현재위치</th><th>배송상태</th></tr></thead>
      <tbody>{trs}</tbody>
    </table>
    """


CASES = [
    (
        "CASE 1 - 수거준비 (배달완료 단계레이블 포함, 역순 최신 반환)",
        make_table(
            ("2026.09.10", "06:22", "서울강남우체국", "운송장출력"),
            ("2026.09.10", "07:55", "서울강남우체국", "수거준비"),
        ),
        "05",
    ),
    (
        "CASE 2 - 배차신청 (별도 09 코드)",
        make_table(
            ("2026.09.10", "06:22", "서울강남우체국", "운송장출력"),
            ("2026.09.10", "07:55", "서울강남우체국", "수거준비"),
            ("2026.09.10", "11:25", "서울강남우체국", "배차신청"),
        ),
        "09",
    ),
    (
        "CASE 2b - 접수확인 (별도 08 코드)",
        make_table(
            ("2026.09.10", "06:00", "서울강남우체국", "운송장출력"),
            ("2026.09.10", "07:00", "서울강남우체국", "접수확인"),
        ),
        "08",
    ),
    (
        "CASE 3 - 실제 배달완료 (마지막 행이 배달완료)",
        make_table(
            ("2026.09.09", "09:11", "서울강남우체국", "배달중"),
            ("2026.09.09", "14:30", "서울강남우체국", "배달완료"),
        ),
        "03",
    ),
    (
        "CASE 4 - 이동중",
        make_table(
            ("2026.09.09", "22:00", "서울강남우체국", "수거완료"),
            ("2026.09.10", "03:00", "서울우편집중국", "이동중"),
        ),
        "02",
    ),
    (
        "CASE 5 - 배달준비 (배달완료 레이블은 span에만)",
        make_table(
            ("2026.09.10", "07:00", "강남우체국", "이동중"),
            ("2026.09.10", "08:00", "강남우체국", "배달준비"),
        ),
        "06",
    ),
    (
        "CASE 6 - 운송장출력 (이력 1개)",
        make_table(
            ("2026.09.10", "06:00", "서울강남우체국", "운송장출력"),
        ),
        "04",
    ),
    (
        "CASE 7 - 텍스트 fallback (HTML 없음, 배달중)",
        "배달중 현재위치: 서울",
        "07",
    ),
    (
        "CASE 8 - 배달완료 텍스트 fallback (TD 없는 순수 텍스트)",
        "배달완료",  # HTML 아닌 텍스트 → 3단계 fallback에서 정상 인식
        "03",
    ),
]

passed = 0
for name, html, expected in CASES:
    result = treat_status_from_tracking_text(html)
    ok = result == expected
    mark = "PASS" if ok else f"FAIL (got {result!r}, expected {expected!r})"
    print(f"  {'OK' if ok else 'NG'}  {name}: {mark}")
    if ok:
        passed += 1

print()
print(f"결과: {passed}/{len(CASES)} 통과")
if passed == len(CASES):
    print("모든 케이스 PASS")
    sys.exit(0)
else:
    print("일부 FAIL")
    sys.exit(1)

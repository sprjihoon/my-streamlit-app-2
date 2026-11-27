"""달력에서 날짜 클릭·드래그로 알바를 넣을 때 쓰는 규칙. 화면 로직과 같다."""

DEFAULT_START = "09:00"


def parse_clock_minutes(value: str) -> int | None:
    text = (value or "").strip()
    if ":" not in text:
        return None
    hour_s, minute_s = text.split(":", 1)
    if not hour_s.isdigit() or not minute_s[:2].isdigit():
        return None
    hour = int(hour_s)
    minute = int(minute_s[:2])
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def normalize_clock(value: str) -> str:
    minutes = parse_clock_minutes(value)
    if minutes is None:
        raise ValueError("시작시간은 HH:MM 형식입니다.")
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def shift_times(start: str, hours: float) -> dict:
    start_clock = normalize_clock(start)
    extra = max(0, int(round(float(hours) * 60)))
    total = parse_clock_minutes(start_clock) + extra
    next_day = total >= 24 * 60
    end_hour, end_minute = divmod(total % (24 * 60), 60)
    end_clock = f"{end_hour:02d}:{end_minute:02d}"
    return {
        "start_time": start_clock,
        "end_time": end_clock,
        "next_day": next_day,
        "label": f"{start_clock}~{'익일 ' if next_day else ''}{end_clock}",
    }


def workers_available_on_date(workers: list[dict], entries: list[dict]) -> list[dict]:
    taken = {item["worker_id"] for item in entries}
    return [worker for worker in workers if worker.get("active") and worker["id"] not in taken]


def drop_worker_onto_date(workers: list[dict], entries: list[dict], worker_id: int) -> dict:
    worker = next((item for item in workers if item["id"] == worker_id), None)
    if not worker or not worker.get("active"):
        return {"kind": "ignore"}
    if any(item["worker_id"] == worker_id for item in entries):
        return {"kind": "duplicate", "name": worker["name"]}
    return {"kind": "hours", "worker_id": worker["id"], "name": worker["name"]}


def date_from_point_target(attribute_value: str | None) -> str | None:
    return attribute_value or None

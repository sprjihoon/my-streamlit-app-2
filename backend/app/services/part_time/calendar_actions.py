"""달력에서 날짜 클릭·드래그로 알바를 넣을 때 쓰는 규칙. 화면 로직과 같다."""


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

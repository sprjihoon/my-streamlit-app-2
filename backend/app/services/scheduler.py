"""
스케줄러 모듈
───────────────────────────────────────
평일 오전 10시 자동 인사 메시지 등 정기 작업을 처리합니다.
"""

import os
import asyncio
import random
from datetime import datetime, time
from typing import Optional

from backend.app.services.naver_works import get_naver_works_client

# 인사 메시지 템플릿 (매일 랜덤으로 선택)
MORNING_GREETINGS = [
    "좋은 아침이에요! ☀️ 오늘도 화이팅입니다!",
    "안녕하세요! 🌤️ 오늘 하루도 힘내세요!",
    "좋은 아침! 😊 오늘도 멋진 하루 되세요!",
    "굿모닝! ☕ 오늘도 활기찬 하루 시작해볼까요?",
    "안녕하세요! 🌞 새로운 하루가 시작됐어요!",
    "좋은 아침이에요! 💪 오늘도 파이팅!",
    "하이! 🙌 오늘 하루도 응원합니다!",
    "안녕하세요! 🌈 좋은 일만 가득한 하루 되세요!",
    "좋은 아침! ✨ 오늘도 최고의 하루를 만들어봐요!",
    "굿모닝! 🎉 오늘도 즐거운 하루 되세요!",
]

# 요일별 추가 메시지
WEEKDAY_MESSAGES = {
    0: "월요일이네요! 한 주의 시작, 힘내요! 💪",  # 월
    1: "화요일! 어제보다 더 좋은 하루 될 거예요! 🔥",  # 화
    2: "수요일, 주중 반 왔어요! 조금만 더 힘내요! 🌟",  # 수
    3: "목요일! 주말이 코앞이에요! 💫",  # 목
    4: "불금 전날! 오늘만 버티면 주말! 🎊",  # 금
}


def is_korean_holiday(date: datetime) -> bool:
    """
    한국 공휴일 체크 (간단한 버전)
    실제로는 공휴일 API나 라이브러리 사용 권장
    """
    # 2026년 주요 공휴일 (양력)
    holidays_2026 = [
        (1, 1),    # 신정
        (1, 28),   # 설날 연휴
        (1, 29),   # 설날
        (1, 30),   # 설날 연휴
        (3, 1),    # 삼일절
        (5, 5),    # 어린이날
        (5, 24),   # 부처님오신날 (예상)
        (6, 6),    # 현충일
        (8, 15),   # 광복절
        (10, 5),   # 추석 연휴 (예상)
        (10, 6),   # 추석
        (10, 7),   # 추석 연휴
        (10, 3),   # 개천절
        (10, 9),   # 한글날
        (12, 25),  # 크리스마스
    ]
    
    return (date.month, date.day) in holidays_2026


def is_workday(date: datetime) -> bool:
    """평일인지 확인 (주말, 공휴일 제외)"""
    # 주말 체크 (토:5, 일:6)
    if date.weekday() >= 5:
        return False
    
    # 공휴일 체크
    if is_korean_holiday(date):
        return False
    
    return True


def get_morning_greeting() -> str:
    """오늘의 인사말 생성"""
    now = datetime.now()
    
    # 기본 인사말 랜덤 선택
    greeting = random.choice(MORNING_GREETINGS)
    
    # 요일별 추가 메시지
    weekday = now.weekday()
    if weekday in WEEKDAY_MESSAGES:
        greeting += f"\n\n{WEEKDAY_MESSAGES[weekday]}"
    
    # 날짜 정보 추가
    date_str = now.strftime("%m월 %d일 %A").replace(
        "Monday", "월요일"
    ).replace(
        "Tuesday", "화요일"
    ).replace(
        "Wednesday", "수요일"
    ).replace(
        "Thursday", "목요일"
    ).replace(
        "Friday", "금요일"
    )
    
    return f"🌅 {date_str}\n\n{greeting}"


async def send_morning_greeting():
    """아침 인사 메시지 전송"""
    # 평일 체크
    now = datetime.now()
    if not is_workday(now):
        print(f"[Scheduler] Skipping greeting - not a workday ({now.strftime('%Y-%m-%d %A')})")
        return
    
    # 인사 보낼 채널 ID (환경변수에서 가져옴)
    channel_id = os.getenv("MORNING_GREETING_CHANNEL_ID")
    if not channel_id:
        print("[Scheduler] MORNING_GREETING_CHANNEL_ID not set, skipping greeting")
        return
    
    try:
        nw_client = get_naver_works_client()
        greeting = get_morning_greeting()
        
        # 채널이 여러 개일 경우 쉼표로 구분
        channel_ids = [cid.strip() for cid in channel_id.split(",") if cid.strip()]
        
        for cid in channel_ids:
            try:
                # 채널 타입 결정 (사용자 ID 형식이면 user, 아니면 group)
                channel_type = "user" if "-" in cid and len(cid) > 30 else "group"
                await nw_client.send_text_message(cid, greeting, channel_type)
                print(f"[Scheduler] Morning greeting sent to {cid}")
            except Exception as e:
                print(f"[Scheduler] Failed to send greeting to {cid}: {e}")
                
    except Exception as e:
        print(f"[Scheduler] Morning greeting error: {e}")


async def scheduler_loop():
    """스케줄러 메인 루프"""
    print("[Scheduler] Started")
    
    while True:
        now = datetime.now()
        
        # 오전 10시 체크 (10:00 ~ 10:01 사이)
        if now.hour == 10 and now.minute == 0:
            await send_morning_greeting()
            # 1분 대기 (중복 실행 방지)
            await asyncio.sleep(60)
        else:
            # 30초마다 체크
            await asyncio.sleep(30)


def start_scheduler():
    """스케줄러 시작 (백그라운드 태스크)"""
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler_loop())
    print("[Scheduler] Background task created")

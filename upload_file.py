"""
파일 업로드 스크립트
"""
import sys
import os
from pathlib import Path
from logic.upload import ingest

def upload_file(file_path: str, table: str):
    """파일을 지정된 테이블에 업로드"""
    # 한글 경로 처리
    if isinstance(file_path, str):
        # Windows 경로에서 슬래시를 백슬래시로 변환
        file_path = file_path.replace('/', '\\')
        file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"파일을 찾을 수 없습니다: {file_path}")
        print(f"절대 경로: {file_path.absolute()}")
        return
    
    print(f"파일 업로드 중: {file_path.name}")
    print(f"대상 테이블: {table}")
    print(f"파일 크기: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
    
    try:
        with open(file_path, 'rb') as f:
            success, message = ingest(f, table, file_path.name)
        
        if success:
            print(f"[OK] {message}")
        else:
            print(f"[ERROR] {message}")
    except Exception as e:
        print(f"[ERROR] 업로드 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python upload_file.py <파일경로> <테이블명>")
        print("\n테이블명 옵션:")
        print("  - kpost_in: 우체국 접수")
        print("  - kpost_ret: 우체국 반품")
        print("  - shipping_stats: 배송통계")
        print("  - inbound_slip: 입고전표")
        print("  - work_log: 작업일지")
        sys.exit(1)
    
    file_path = sys.argv[1]
    table = sys.argv[2]
    
    upload_file(file_path, table)


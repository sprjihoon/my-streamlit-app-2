"""
백업 테이블에서 매핑 데이터 복구
"""
from logic.db import get_connection
import pandas as pd

def restore_mapping_from_backup():
    """백업 테이블에서 vendors와 aliases 복구"""
    print("="*60)
    print("매핑 데이터 복구 (백업 테이블에서)")
    print("="*60)
    
    with get_connection() as con:
        # vendors_backup 확인
        try:
            vendors_backup = pd.read_sql("SELECT * FROM vendors_backup", con)
            print(f"\n[vendors_backup] 백업 데이터: {len(vendors_backup)}건")
            
            if not vendors_backup.empty:
                # 현재 vendors 데이터 확인
                current_vendors = pd.read_sql("SELECT * FROM vendors", con)
                print(f"[vendors] 현재 데이터: {len(current_vendors)}건")
                
                if len(current_vendors) == 0:
                    # 현재 데이터가 없으면 백업에서 복구
                    vendors_backup.to_sql('vendors', con, if_exists='append', index=False)
                    con.commit()
                    print(f"[OK] vendors 복구 완료: {len(vendors_backup)}건")
                    print(vendors_backup)
                else:
                    # 현재 데이터가 있으면 비교
                    print("\n현재 vendors 데이터:")
                    print(current_vendors)
                    print("\n백업 vendors 데이터:")
                    print(vendors_backup)
                    
                    # 백업에 있지만 현재에 없는 것만 추가
                    merged = current_vendors.merge(
                        vendors_backup, 
                        on=['vendor'], 
                        how='right', 
                        indicator=True
                    )
                    new_vendors = merged[merged['_merge'] == 'right_only'].drop(columns=['_merge'])
                    
                    if not new_vendors.empty:
                        # vendor_id 제거하고 추가
                        if 'vendor_id' in new_vendors.columns:
                            new_vendors = new_vendors.drop(columns=['vendor_id'])
                        new_vendors.to_sql('vendors', con, if_exists='append', index=False)
                        con.commit()
                        print(f"\n[OK] vendors 추가 복구: {len(new_vendors)}건")
                        print(new_vendors)
                    else:
                        print("\n[INFO] vendors는 이미 모두 복구되어 있습니다.")
            else:
                print("[WARN] vendors_backup에 데이터가 없습니다.")
        except Exception as e:
            print(f"[ERROR] vendors 복구 실패: {e}")
            import traceback
            traceback.print_exc()
        
        # aliases_backup 확인
        try:
            aliases_backup = pd.read_sql("SELECT * FROM aliases_backup", con)
            print(f"\n[aliases_backup] 백업 데이터: {len(aliases_backup)}건")
            
            if not aliases_backup.empty:
                # 현재 aliases 데이터 확인
                current_aliases = pd.read_sql("SELECT * FROM aliases", con)
                print(f"[aliases] 현재 데이터: {len(current_aliases)}건")
                
                if len(current_aliases) == 0:
                    # 현재 데이터가 없으면 백업에서 복구
                    aliases_backup.to_sql('aliases', con, if_exists='append', index=False)
                    con.commit()
                    print(f"[OK] aliases 복구 완료: {len(aliases_backup)}건")
                    print(aliases_backup.head(10))
                else:
                    # 현재 데이터가 있으면 비교
                    print("\n현재 aliases 데이터:")
                    print(current_aliases.head(10))
                    print(f"\n백업 aliases 데이터:")
                    print(aliases_backup.head(10))
                    
                    # 백업에 있지만 현재에 없는 것만 추가
                    # aliases는 vendor, alias, file_type의 조합이 유니크
                    key_cols = ['vendor', 'alias', 'file_type']
                    if all(col in aliases_backup.columns for col in key_cols):
                        merged = current_aliases.merge(
                            aliases_backup,
                            on=key_cols,
                            how='right',
                            indicator=True
                        )
                        new_aliases = merged[merged['_merge'] == 'right_only'].drop(columns=['_merge'])
                        
                        if not new_aliases.empty:
                            # alias_id 제거하고 추가
                            if 'alias_id' in new_aliases.columns:
                                new_aliases = new_aliases.drop(columns=['alias_id'])
                            new_aliases.to_sql('aliases', con, if_exists='append', index=False)
                            con.commit()
                            print(f"\n[OK] aliases 추가 복구: {len(new_aliases)}건")
                            print(new_aliases.head(10))
                        else:
                            print("\n[INFO] aliases는 이미 모두 복구되어 있습니다.")
            else:
                print("[WARN] aliases_backup에 데이터가 없습니다.")
        except Exception as e:
            print(f"[ERROR] aliases 복구 실패: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("매핑 데이터 복구 완료!")
    print("="*60)

if __name__ == "__main__":
    restore_mapping_from_backup()


import sys
import os
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.collectors.ohlcv_collector import OHLCVCollector
from src.utils.notifier import TelegramNotifier

def run_test():
    print("Testing OHLCV Collector for Samsung Electronics (005930)...")
    
    # 알림봇 초기화
    notifier = TelegramNotifier()
    
    # OHLCV 수집기 초기화
    collector = OHLCVCollector()
    
    # 날짜 설정 (최근 30일)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    
    print(f"Date range: {start_date} to {end_date}")
    
    # 데이터 수집
    df = collector.fetch_daily_data("005930", start_date, end_date)
    
    if df.empty:
        error_msg = "Failed to fetch OHLCV data. Check KIS API credentials."
        print(error_msg)
        notifier.notify_error("OHLCV 수집 테스트", error_msg)
        return False
    
    # 데이터 저장
    output_dir = "data/raw"
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/005930_{start_date}_{end_date}.csv"
    
    if collector.save_to_csv(df, filename):
        # 데이터 샘플 출력
        print(f"\nData saved successfully: {filename}")
        print(f"Total records: {len(df)}")
        print("\nSample data (first 5 rows):")
        print(df.head().to_string())
        
        # 알림 전송
        details = f"종목: 삼성전자(005930)\n기간: {start_date} ~ {end_date}\n레코드 수: {len(df)}개\n저장 위치: {filename}"
        notifier.notify_success("OHLCV 수집 테스트", details)
        
        return True
    else:
        error_msg = f"Failed to save data to {filename}"
        print(error_msg)
        notifier.notify_error("OHLCV 수집 테스트", error_msg)
        return False

if __name__ == "__main__":
    success = run_test()
    if success:
        print("\n✅ OHLCV collection test completed successfully!")
    else:
        print("\n❌ OHLCV collection test failed!")
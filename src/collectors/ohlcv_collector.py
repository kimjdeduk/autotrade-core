import pandas as pd
import json
import requests
from datetime import datetime, timedelta
from src.utils.kis_client import KISClient

class OHLCVCollector:
    def __init__(self):
        self.kis = KISClient()
    
    def fetch_daily_data(self, symbol_code, start_date, end_date, is_virtual=True):
        """
        KIS API 국내주식기간별시세(일별) 데이터 수집
        Args:
            symbol_code: 종목코드 (예: "005930")
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
        Returns:
            pandas.DataFrame: OHLCV 데이터
        """
        print(f"Fetching daily OHLCV data for {symbol_code} from {start_date} to {end_date}")
        
        # KIS API 액세스 토큰 획득
        if not self.kis.get_access_token():
            print("Failed to get KIS API access token")
            return pd.DataFrame()
        
        # KIS API 국내주식기간별시세(일별) 호출
        url = f"{self.kis.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.kis.access_token}",
            "appkey": self.kis.app_key,
            "appsecret": self.kis.app_secret,
            "tr_id": "FHKST03010100"  # 국내주식기간별시세(일별)
        }
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 주식
            "FID_INPUT_ISCD": symbol_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",  # 일별
            "FID_ORG_ADJ_PRC": "0"  # 수정주가 원주가
        }
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("rt_cd") == "0":
                    return self._parse_ohlcv_data(data, symbol_code)
                else:
                    print(f"API Error: {data.get('msg1')}")
            else:
                print(f"HTTP Error: {response.status_code}")
                
        except Exception as e:
            print(f"Error fetching OHLCV data: {e}")
        
        return pd.DataFrame()
    
    def _parse_ohlcv_data(self, api_response, symbol_code):
        """
        KIS API 응답을 pandas DataFrame으로 파싱
        """
        output_data = api_response.get("output2", [])
        
        if not output_data:
            print("No data returned from API")
            return pd.DataFrame()
        
        records = []
        for item in output_data:
            record = {
                'symbol': symbol_code,
                'date': item['stck_bsop_date'],  # 기준일자
                'open': int(item['stck_oprc']),  # 시가
                'high': int(item['stck_hgpr']),  # 고가
                'low': int(item['stck_lwpr']),  # 저가
                'close': int(item['stck_clpr']),  # 종가
                'volume': int(item['acml_vol']),  # 누적거래량
                'amount': int(item['acml_tr_pbmn']),  # 누적거래대금
                'change': int(item['prdy_vrss']),  # 전일대비
                'change_rate': float(item.get('prdy_ctrt', 0))  # 전일대비율 (없으면 0)
            }
            records.append(record)
        
        df = pd.DataFrame(records)
        
        # 날짜 형식 변환 및 정렬
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df = df.sort_values('date')
        df = df.reset_index(drop=True)
        
        return df
    
    def save_to_csv(self, df, filename):
        """
        DataFrame을 CSV 파일로 저장
        """
        if df.empty:
            print("No data to save")
            return False
        
        try:
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"Data saved to {filename}")
            return True
        except Exception as e:
            print(f"Error saving CSV: {e}")
            return False
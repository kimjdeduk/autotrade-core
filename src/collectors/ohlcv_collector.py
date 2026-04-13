import pandas as pd
from src.utils.kis_client import KISClient

class OHLCVCollector:
    def __init__(self):
        self.kis = KISClient()
    
    def fetch_daily_data(self, symbol_code, start_date, end_date):
        print(f"Fetching data for {symbol_code} from {start_date} to {end_date}")
        return pd.DataFrame()
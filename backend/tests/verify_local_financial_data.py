"""
backend/tests/verify_local_financial_data.py
--------------------------------------------------------------------------
Verification script for local database market data and live fallbacks.
--------------------------------------------------------------------------
"""

import os
import sys

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from database.db import db
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from services.market_data_service import MarketDataService
from services.company_search_service import CompanySearchService
from services.financial_service import get_stock_quote, get_stock_history

def main():
    app = create_app({"DEBUG": True})
    with app.app_context():
        # Check Total DB Counts
        c_count = Company.query.count()
        s_count = Security.query.count()
        dp_count = DailyPrice.query.count()
        print(f"DATABASE SUMMARY:")
        print(f"  Companies: {c_count}")
        print(f"  Securities: {s_count}")
        print(f"  Daily Prices: {dp_count}")
        print("-" * 50)

        # 1. Search for Indian stocks (Local Bhavcopy seeded)
        for query in ["RELIANCE", "TCS", "INFY", "TATAMOTORS"]:
            results = CompanySearchService.search(query)
            print(f"Search Query: '{query}' -> Found {len(results)} match(es)")
            if results:
                first = results[0]
                sec_id = first["security_id"]
                symbol = first["symbol"]
                company_name = first["company_name"]
                latest = MarketDataService.get_latest_market_data(sec_id)
                md = latest.get("market_data")
                hist = MarketDataService.get_price_history(sec_id, range_key="1m")
                prices = hist.get("prices", [])
                print(f"  => {symbol} ({company_name}) | Security ID: {sec_id}")
                if md:
                    print(f"     Price: {md.get('close')} {md.get('currency')} | Change: {md.get('change')} ({md.get('change_percent')}%) | Vol: {md.get('volume')} | Date: {md.get('date')}")
                else:
                    print("     Price: [No Market Data]")
                print(f"     History (1M): {len(prices)} candles | Start: {prices[0]['date'] if prices else 'N/A'} -> End: {prices[-1]['date'] if prices else 'N/A'}")
            print()

        # 2. Search for Global / US Equities (Dynamic discovery + live quote fallback)
        for query in ["Apple", "Tesla", "Nvidia"]:
            results = CompanySearchService.search(query)
            print(f"Search Query (Global): '{query}' -> Found {len(results)} match(es)")
            if results:
                first = results[0]
                sec_id = first["security_id"]
                symbol = first["symbol"]
                company_name = first["company_name"]
                latest = MarketDataService.get_latest_market_data(sec_id)
                md = latest.get("market_data")
                hist = MarketDataService.get_price_history(sec_id, range_key="1m")
                prices = hist.get("prices", [])
                print(f"  => {symbol} ({company_name}) | Security ID: {sec_id}")
                if md:
                    print(f"     Price: {md.get('close')} {md.get('currency')} | Change: {md.get('change')} ({md.get('change_percent')}%) | Vol: {md.get('volume')} | Date: {md.get('date')}")
                else:
                    print("     Price: [No Market Data]")
                print(f"     History (1M): {len(prices)} candles")
            print()

if __name__ == "__main__":
    main()

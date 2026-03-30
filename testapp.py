import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re

st.set_page_config(page_title="台股股息成長分析", layout="wide")

st.title("🇹🇼 台股股息成長 (DGI) 自動分析")

@st.cache_data(ttl=3600)
def get_tw_stock_dividends(stock_id):
    # 使用台灣 Yahoo 奇摩股市的網頁
    url = f"https://tw.stock.yahoo.com/quote/{stock_id}/dividend"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尋找包含配息資料的列表項
        # 結構通常是：年度, 公告日, 除息日, 現金股利...
        rows = soup.select('li.List\(n\)')
        
        data = []
        for row in rows:
            divs = row.select('div')
            if len(divs) >= 6:
                year_text = divs[0].get_text(strip=True)
                # 過濾出「年度」格式 (如 2023)
                if re.match(r'^\d{4}$', year_text):
                    try:
                        dividend = float(divs[5].get_text(strip=True))
                        data.append({"年度": year_text, "現金股利": dividend})
                    except ValueError:
                        continue
        
        if not data:
            return None
            
        df = pd.DataFrame(data)
        # 如果一年內有多筆配息（如季配、半年配），將其按年度加總
        df = df.groupby("年度")["現金股利"].sum().sort_index(ascending=False).reset_index()
        return df
    except Exception as e:
        st.error(f"連線發生錯誤: {e}")
        return None

# --- UI 介面 ---
stock_id = st.text_input("請輸入台股代號 (如: 2330, 00878, 0056)", value="2330")

if st.button("開始分析"):
    with st.spinner(f'正在分析 {stock_id} 的配息歷史...'):
        df = get_tw_stock_dividends(stock_id)
        
        if df is not None and not df.empty:
            # 1. 計算連續配息年數
            consecutive_years = 0
            for val in df['現金股利']:
                if val > 0:
                    consecutive_years += 1
                else:
                    break
            
            # 2. 顯示亮點數據
            st.subheader(f"📊 代號 {stock_id} 分析結果")
            col1, col2 = st.columns(2)
            col1.metric("連續配息年數", f"{consecutive_years} 年")
            col2.metric("最新年度總股利", f"${df.iloc[0]['現金股利']:.2f}")

            # 3. 圖表顯示
            st.bar_chart(df.set_index('年度'))
            
            with st.expander("查看年度配息數據表"):
                st.table(df)
        else:
            st.error("❌ 無法取得數據。請檢查代號是否正確，或該股票尚未有配息紀錄。")

st.divider()
st.caption("提示：此版本直接解析 Yahoo 奇摩股市網頁，不依賴容易受限的 API。")

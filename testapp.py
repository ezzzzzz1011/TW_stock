import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time

st.set_page_config(page_title="台股股息成長分析", layout="wide")

st.title("🇹🇼 台股股息成長 (DGI) 自動分析")

@st.cache_data(ttl=3600)
def get_tw_dividend_data(stock_id):
    # 使用 Yahoo 奇摩股市的網頁，對台灣使用者更友善且不易封鎖
    url = f"https://tw.stock.yahoo.com/quote/{stock_id}/dividend"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 這裡抓取表格中的年度與配息數據
    # 注意：Yahoo 的網頁結構可能會變動，以下是針對目前的結構抓取
    try:
        table = soup.find('ul', {'class': 'M(0) P(0) List(n)'})
        items = table.find_all('li', recursive=False)
        
        data = []
        for item in items[1:]: # 跳過標題
            cols = item.find_all('div')
            year = cols[0].text.strip()
            div_sum = cols[5].text.strip() # 現金股利總計
            data.append({"年度": year, "現金股利": float(div_sum)})
            
        return pd.DataFrame(data)
    except:
        return None

# --- UI 介面 ---
stock_id = st.text_input("請輸入台股代號 (如: 2330, 878, 0056)", value="2330")

if st.button("開始分析"):
    with st.spinner('正在從 Yahoo 奇摩股市獲取數據...'):
        df = get_tw_dividend_data(stock_id)
        
        if df is not None and not df.empty:
            # 整理數據
            df = df.sort_values("年度", ascending=False)
            
            # 計算連續配息
            consecutive_years = 0
            for val in df['現金股利']:
                if val > 0:
                    consecutive_years += 1
                else:
                    break
            
            # --- 顯示亮點指標 ---
            col1, col2 = st.columns(2)
            col1.metric("連續配息年數", f"{consecutive_years} 年")
            col2.metric("最新年度股利", f"${df.iloc[0]['現金股利']:.2f}")

            # --- 圖表 ---
            st.subheader("歷史配息走勢")
            chart_df = df.set_index("年度")
            st.bar_chart(chart_df)
            
            with st.expander("查看原始配息明細"):
                st.table(df)
        else:
            st.error("❌ 無法獲取資料。可能是代號輸入錯誤，或是網頁結構已更新。")

st.info("💡 這個版本直接抓取台灣 Yahoo 股市網頁，繞過了容易報錯的 API 限制。")

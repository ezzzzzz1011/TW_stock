import streamlit as st
import yfinance as yf
import pandas as pd
import time
import random

st.set_page_config(page_title="台股股息成長分析", layout="wide")

st.title("🇹🇼 台股股息成長 (DGI) 自動分析")

# --- 使用快取機制來避免重複請求引發封鎖 ---
@st.cache_data(ttl=3600)  # 資料會快取一小時，這期間抓同代號不會重複請求 Yahoo
def get_stock_data(stock_id):
    ticker_str = f"{stock_id}.TW"
    ticker = yf.Ticker(ticker_str)
    
    # 增加一個隨機微小延遲，模擬真人行為
    time.sleep(random.uniform(0.5, 1.5))
    
    # 獲取配息與基本資料
    divs = ticker.actions
    info = ticker.info
    return divs, info

# --- 輸入區 ---
stock_id = st.text_input("請輸入台股代號 (如: 2330, 878, 56)", value="2330")
analyze_btn = st.button("開始分析")

if analyze_btn:
    try:
        with st.spinner(f'正在分析 {stock_id}，請稍候...'):
            dividends, info = get_stock_data(stock_id)
            
            if dividends is None or dividends.empty:
                st.warning("⚠️ 找不到該代號的配息紀錄。")
            else:
                # 處理配息數據
                div_df = dividends[['Dividends']].resample('YE').sum()
                div_df.index = div_df.index.year
                div_df = div_df.sort_index(ascending=False)
                
                # 計算連續配息年數
                amounts = div_df['Dividends'].tolist()
                consecutive_years = 0
                for amt in amounts:
                    if amt > 0:
                        consecutive_years += 1
                    else:
                        break
                
                # --- 介面顯示 ---
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("連續配息年數", f"{consecutive_years} 年")
                with col2:
                    current_div = amounts[0] if len(amounts) > 0 else 0
                    st.metric("最新年度股息", f"${current_div:.2f}")
                with col3:
                    yld = info.get("dividendYield", 0)
                    st.metric("預估殖利率", f"{yld * 100:.2f} %" if yld else "N/A")

                st.subheader("年度配息紀錄圖表")
                st.bar_chart(div_df)
                
                with st.expander("查看原始數據"):
                    st.table(div_df)

    except Exception as e:
        if "RateLimitError" in str(e):
            st.error("🚨 哎呀！Yahoo Finance 暫時限制了訪問。請等待 10 分鐘後再試，或嘗試輸入不同代號。")
        else:
            st.error(f"發生錯誤: {e}")

st.divider()
st.caption("提示：如果遇到封鎖，請嘗試點擊右上角三點選單中的 'Clear cache' 後重整網頁。")

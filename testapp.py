import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="台股股息成長分析", layout="wide")

st.title("🇹🇼 台股股息成長 (DGI) 自動分析")

@st.cache_data(ttl=3600)
def get_dividend_data_final(stock_id):
    # 策略 A: 直接抓取 Yahoo 財經的 API (這跟 yfinance 不同，更輕量)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock_id}.TW?symbol={stock_id}.TW&period1=0&period2=9999999999&interval=1d&events=div"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        # 解析 JSON 裡面的配息資料
        if "chart" in data and "result" in data["chart"] and "events" in data["chart"]["result"][0]:
            div_events = data["chart"]["result"][0]["events"]["dividends"]
            df_list = []
            for timestamp, details in div_events.items():
                date = pd.to_datetime(int(timestamp), unit='s')
                df_list.append({"日期": date, "現金股利": details["amount"]})
            
            df = pd.DataFrame(df_list)
            df['年度'] = df['日期'].dt.year
            # 年度加總 (處理季配息)
            final_df = df.groupby("年度")["現金股利"].sum().sort_index(ascending=False).reset_index()
            return final_df
    except Exception as e:
        pass
    
    return None

# --- UI 介面 ---
stock_id = st.text_input("請輸入台股代號 (如: 2330, 2317, 00878)", value="2317")

if st.button("開始分析"):
    with st.spinner(f'正在分析 {stock_id}...'):
        df = get_dividend_data_final(stock_id)
        
        if df is not None and not df.empty:
            # 計算連續配息年數
            consecutive_years = 0
            for val in df['現金股利']:
                if val > 0:
                    consecutive_years += 1
                else:
                    break
            
            # --- 顯示結果 ---
            st.subheader(f"📊 {stock_id} 分析結果")
            col1, col2 = st.columns(2)
            col1.metric("連續配息年數", f"{consecutive_years} 年")
            col2.metric("最新年度總股利", f"${df.iloc[0]['現金股利']:.2f}")

            # 柱狀圖
            st.bar_chart(df.set_index('年度'))
            
            with st.expander("查看原始年度配息表"):
                st.table(df)
        else:
            st.error("❌ 目前無法從雲端獲取數據。這通常是伺服器 IP 被限制，建議稍後再試，或更換代號。")
            st.info("💡 試試看 2330 或 0050，若都失敗，代表 Streamlit 伺服器目前的 IP 正在被 Yahoo 限制中。")

st.divider()
st.caption("備註：本工具抓取公開市場配息紀錄進行年度加總運算。")

import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="台股數據校正系統", page_icon="📈")

st.title("📈 台股精準資訊與估價")

@st.cache_data(ttl=3600)
def fetch_stock_info(stock_code):
    for suffix in [".TW", ".TWO"]:
        ticker_str = f"{stock_code}{suffix}"
        ticker = yf.Ticker(ticker_str)
        try:
            hist = ticker.history(period="1d")
            if not hist.empty:
                data = ticker.info
                data['current_price'] = hist['Close'].iloc[-1]
                data['actual_ticker'] = ticker_str
                return data
        except:
            continue
    return None

stock_code = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")

if stock_code:
    info = fetch_stock_info(stock_code)
    
    if info:
        try:
            current_price = info.get('current_price', 0)
            
            # --- 精確修正邏輯：解決截圖中的錯誤 ---
            
            # 1. 殖利率校正 (解決出現 132% 或 46% 的錯誤)
            # Yahoo 有時將 $5 元配息誤傳為 5.0 (500%)，正常應為 0.05 (5%)
            dy_raw = info.get('dividendYield', 0) or 0
            if dy_raw >= 1: # 如果數值大於 1，代表 Yahoo 傳回的是「金額」而非「比率」
                dy_fixed = (dy_raw / current_price) * 100
            else:
                dy_fixed = dy_raw * 100
            
            # 2. 本益比 (PE) 校正
            # 優先從 info 抓取，若數值極端異常則顯示 N/A，由使用者自訂輸入
            pe_raw = info.get('trailingPE')
            display_pe = f"{pe_raw:.2f}" if pe_raw and 0 < pe_raw < 150 else "數據異常(N/A)"

            # 3. 股本與市值校正 (億)
            shares = info.get('sharesOutstanding', 0) or 0
            share_capital = (shares * 10) / 1e8 # 台灣 10 元面額計算法
            mkt_cap = (info.get('marketCap', 0) or 0) / 1e8

            # --- 顯示表格 ---
            basic_data = {
                "項目": ["目前股價", "本益比 (PE)", "殖利率", "ROE", "市值 (億)", "股本 (億)"],
                "數值": [
                    f"{current_price:.2f}",
                    display_pe,
                    f"{dy_fixed:.2f}%",
                    f"{(info.get('returnOnEquity', 0) or 0)*100:.2f}%",
                    f"{mkt_cap:,.2f}",
                    f"{share_capital:,.2f}"
                ]
            }
            st.subheader("📊 股票基本資料 (已校正)")
            st.table(pd.DataFrame(basic_data))

            st.divider()

            # --- 估價功能 (讓使用者以「自訂」為準，避免原始數據錯誤影響決策) ---
            st.subheader("⚙️ 自訂估價計算")
            # 自動帶入 Yahoo 的 EPS 作為參考，但允許手動修改
            auto_eps = info.get('trailingEps', 0.0)
            
            col1, col2 = st.columns(2)
            with col1:
                eps = st.number_input("輸入該股 EPS", value=float(auto_eps) if auto_eps else 10.0, step=0.1)
            with col2:
                # 這裡就是你想要的「合理價參考」本益比輸入
                pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)

            fair_price = eps * pe_target
            st.metric(label="合理價參考", value=f"{fair_price:.2f}")

        except Exception as e:
            st.error("解析異常，請重新輸入代號。")
    else:
        st.error("找不到該股票資訊。")

import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="台股精準估價", page_icon="📈")

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
            stock_name = info.get('shortName', stock_code)
            st.success(f"✅ 已取得 **{stock_name} ({info['actual_ticker']})** 最新股價：{current_price:.2f}")

            # --- 精確資料處理邏輯 ---
            # 1. 殖利率與 ROE (修正數值異常)
            dy = info.get('dividendYield', 0) or 0
            display_dy = f"{dy * 100:.2f}%" if 0 < dy < 1 else f"{dy:.2f}%"

            roe = info.get('returnOnEquity', 0) or 0
            display_roe = f"{roe * 100:.2f}%" if 0 < abs(roe) < 1 else f"{roe:.2f}%"

            # 2. 市值 (億)：直接使用 Yahoo 的 marketCap 除以 1 億
            mkt_cap_raw = info.get('marketCap', 0) or 0
            mkt_cap_billion = mkt_cap_raw / 1e8

            # 3. 股本 (億)：台灣算法 = (發行股數 * 10元面額) / 1億
            shares = info.get('sharesOutstanding', 0) or 0
            share_capital_billion = (shares * 10) / 1e8

            # --- 基本資料表格 ---
            st.subheader("📊 股票基本資料")
            basic_data = {
                "項目": ["目前股價", "產業分類", "本益比 (PE)", "股價淨值比 (PB)", "殖利率", "ROE", "市值 (億)", "股本 (億)"],
                "數值": [
                    f"{current_price:.2f}",
                    f"{info.get('industry', '-')}",
                    f"{info.get('trailingPE', 0):.2f}" if info.get('trailingPE') else "N/A",
                    f"{info.get('priceToBook', 0):.2f}" if info.get('priceToBook') else "N/A",
                    display_dy,
                    display_roe,
                    f"{mkt_cap_billion:,.2f}", # 加入千分位符號
                    f"{share_capital_billion:,.2f}"
                ]
            }
            st.table(pd.DataFrame(basic_data))

            st.divider()

            # --- 估價功能 ---
            st.subheader("⚙️ 自訂估價計算")
            auto_eps = info.get('trailingEps', 0.0)
            
            col1, col2 = st.columns(2)
            with col1:
                eps = st.number_input("輸入該股 EPS", value=float(auto_eps) if auto_eps else 10.0, step=0.1)
            with col2:
                pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)

            fair_price = eps * pe_target
            st.metric(label="合理價參考", value=f"{fair_price:.2f}")

            # 比較結果
            if current_price <= fair_price:
                st.success(f"🟢 目前股價 {current_price:.2f} 低於參考價 {fair_price:.2f}。")
            else:
                st.warning(f"🟡 目前股價 {current_price:.2f} 高於參考價 {fair_price:.2f}。")

        except Exception as e:
            st.error(f"解析資料時發生錯誤。")
    else:
        st.error(f"❌ 抓取失敗。請檢查代號 '{stock_code}'。")

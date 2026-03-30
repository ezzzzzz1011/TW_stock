import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="台股獲利數據分析", page_icon="📈")

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
            eps_ttm = info.get('trailingEps', 0) or 0
            
            st.success(f"✅ 已取得數據：{info.get('shortName', stock_code)} ({info['actual_ticker']})")

            # 計算即時本益比
            pe_calc = current_price / eps_ttm if eps_ttm > 0 else 0

            # 數據修正邏輯
            dy_raw = info.get('dividendYield', 0) or 0
            dy_fixed = (dy_raw / current_price * 100) if dy_raw >= 1 else (dy_raw * 100)
            shares = info.get('sharesOutstanding', 0) or 0
            share_capital = (shares * 10) / 1e8 
            mkt_cap = (info.get('marketCap', 0) or 0) / 1e8

            # 表格顯示
            st.subheader("📊 股票基本資料")
            basic_data = {
                "項目": ["目前股價", "最近四季累積 EPS", "即時本益比 (PE)", "殖利率", "ROE", "市值 (億)", "股本 (億)"],
                "數值": [
                    f"{current_price:.2f}",
                    f"{eps_ttm:.2f}",
                    f"{pe_calc:.2f}",
                    f"{dy_fixed:.2f}%",
                    f"{(info.get('returnOnEquity', 0) or 0)*100:.2f}%",
                    f"{mkt_cap:,.2f}",
                    f"{share_capital:,.2f}"
                ]
            }
            st.table(pd.DataFrame(basic_data))

            st.divider()

            # --- 估價功能 ---
            st.subheader("⚙️ 自訂本益比估價")
            col1, col2 = st.columns(2)
            
            with col1:
                # 預設帶入抓到的 EPS
                eps_input = st.number_input("參考 EPS (累積)", value=float(eps_ttm), step=0.1)
            
            with col2:
                # 【關鍵修改點】將預設值固定在 15.0，這樣就不會一開始跑出目前的股價
                # 你依然可以在網頁畫面上手動修改這個數字
                pe_target = st.number_input("自訂目標本益比", value=15.0, step=0.1)

            # 計算合理價
            fair_price = eps_input * pe_target
            
            # 顯示結果
            diff = fair_price - current_price
            st.metric(
                label="合理價參考", 
                value=f"{fair_price:.2f}", 
                delta=f"{diff:.2f} (與現價差距)"
            )
            
            st.info(f"💡 計算公式：參考 EPS ({eps_input:.2f}) × 目標本益比 ({pe_target:.2f}) = {fair_price:.2f}")

        except Exception as e:
            st.error(f"解析異常：{e}")
    else:
        st.error("❌ 找不到該股票，請檢查代號是否正確。")

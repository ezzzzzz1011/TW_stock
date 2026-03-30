import streamlit as st
import yfinance as yf
import pandas as pd
import requests

# 設定網頁標題
st.set_page_config(page_title="台股精準估價", page_icon="📈")

st.title("📈 台股精準資訊與估價")

# --- 輸入代號 ---
stock_code = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")

if stock_code:
    # 嘗試不同的後綴 (上市 .TW, 上櫃 .TWO)
    target_stock = f"{stock_code}.TW"
    
    @st.cache_data(ttl=3600) # 快取一小時，減少請求次數
    def get_stock_data(ticker_str):
        try:
            ticker = yf.Ticker(ticker_str)
            # 使用 history 獲取最新價格，這比 fast_info 穩定
            hist = ticker.history(period="1d")
            if hist.empty:
                return None, None
            return ticker, hist['Close'].iloc[-1]
        except:
            return None, None

    # 先試上市
    stock_obj, current_price = get_stock_data(target_stock)
    
    # 若失敗，試上櫃
    if stock_obj is None:
        target_stock = f"{stock_code}.TWO"
        stock_obj, current_price = get_stock_data(target_stock)

    if stock_obj and current_price:
        try:
            info = stock_obj.info
            stock_name = info.get('shortName', stock_code)
            st.success(f"✅ 已取得 **{stock_name} ({stock_code})** 最新股價：{current_price:.2f}")

            # --- 資料處理 ---
            dy = info.get('dividendYield', 0) or 0
            display_dy = f"{dy * 100:.2f}%" if dy < 1 else f"{dy:.2f}%"

            roe = info.get('returnOnEquity', 0) or 0
            display_roe = f"{roe * 100:.2f}%" if abs(roe) < 1 else f"{roe:.2f}%"

            mkt_cap = (info.get('marketCap', 0) or 0) / 1e8
            shares = (info.get('sharesOutstanding', 0) or 0)
            share_capital = (shares * 10) / 1e8

            # --- 基本資料表格 ---
            st.subheader("📊 股票基本資料")
            basic_df = pd.DataFrame({
                "項目": ["目前股價", "產業分類", "本益比 (PE)", "股價淨值比 (PB)", "殖利率", "ROE", "市值 (億)", "股本 (億)"],
                "數值": [
                    f"{current_price:.2f}",
                    f"{info.get('industry', '-')}",
                    f"{info.get('trailingPE', 0):.2f}" if info.get('trailingPE') else "N/A",
                    f"{info.get('priceToBook', 0):.2f}" if info.get('priceToBook') else "N/A",
                    display_dy,
                    display_roe,
                    f"{mkt_cap:.2f}",
                    f"{share_capital:.2f}"
                ]
            })
            st.table(basic_df)

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

            if current_price <= fair_price:
                st.success(f"🟢 目前股價 {current_price:.2f} 低於參考價。")
            else:
                st.warning(f"🟡 目前股價 {current_price:.2f} 高於參考價。")

        except Exception as e:
            st.error(f"解析資料時發生錯誤：{e}")
    else:
        st.error(f"❌ 抓取失敗。請檢查代號 '{stock_code}' 是否正確，或稍後再試。")

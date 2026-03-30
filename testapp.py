import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="台股精準估價", page_icon="📈")

st.title("📈 台股精準資訊與估價")

stock_code = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")

if stock_code:
    # 支援上市 (.TW) 與 上櫃 (.TWO) 自動切換
    ticker_name = f"{stock_code}.TW"
    stock_data = yf.Ticker(ticker_name)
    
    # 若抓不到資料，嘗試上櫃後綴
    if not stock_data.info or 'regularMarketPrice' not in stock_data.fast_info:
        ticker_name = f"{stock_code}.TWO"
        stock_data = yf.Ticker(ticker_name)

    try:
        info = stock_data.info
        # 使用 fast_info 取得最新股價最準確
        current_price = stock_data.fast_info['last_price']
        stock_name = info.get('shortName', stock_code)
        
        st.success(f"✅ 已取得 **{stock_name} ({stock_code})** 最新數據")

        # --- 資料修正邏輯 ---
        # 1. 殖利率修正: Yahoo 有時給 0.0132 (1.32%), 有時給 1.32 (132%)
        dy = info.get('dividendYield', 0)
        if dy is None: dy = 0
        display_dy = f"{dy * 100:.2f}%" if dy < 1 else f"{dy:.2f}%"

        # 2. ROE 修正
        roe = info.get('returnOnEquity', 0)
        if roe is None: roe = 0
        display_roe = f"{roe * 100:.2f}%" if abs(roe) < 1 else f"{roe:.2f}%"

        # 3. 市值與股本換算 (億)
        mkt_cap = info.get('marketCap', 0) / 1e8 if info.get('marketCap') else 0
        # 股本概算 = 市值 / 股價 (或是從 sharesOutstanding 抓)
        shares = info.get('sharesOutstanding', 0)
        share_capital = (shares * 10) / 1e8  # 台灣面額通常是 10 元

        # --- 顯示基本資料表格 ---
        basic_info = {
            "項目": ["目前股價", "產業分類", "個股本益比", "股價淨值比", "殖利率", "ROE", "市值 (億)", "股本 (億)"],
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
        }
        
        st.table(pd.DataFrame(basic_info))

        st.divider()

        # --- 估價功能 (自動帶入 EPS) ---
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
        st.error(f"資料擷取失敗，請確認代號是否正確。")

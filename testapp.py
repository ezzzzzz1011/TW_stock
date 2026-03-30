import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="台股自動估價與資訊", page_icon="📈")

st.title("📈 台股個股資訊與估價")

# --- 輸入代號 ---
stock_code = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")

if stock_code:
    full_code = f"{stock_code}.TW"
    try:
        stock_data = yf.Ticker(full_code)
        info = stock_data.info
        current_price = stock_data.fast_info['last_price']
        stock_name = info.get('shortName', stock_code)
        
        st.success(f"✅ 已取得 **{stock_name}** 最新數據")

        # --- 1. 個股基本資料表格 (模擬你提供的截圖) ---
        st.subheader("📊 股票基本資料")
        
        # 整理成表格數據
        basic_info = {
            "項目": [
                "英文名稱", "產業分類", "個股本益比", "股價淨值比", 
                "殖利率 (%)", "ROE (近四季)", "股本 (億)", "市值 (億)", "公司地址"
            ],
            "數值": [
                info.get('longName', '-'),
                f"{info.get('industry', '-')} ({info.get('sector', '-')})",
                f"{info.get('trailingPE', 0):.2f}" if info.get('trailingPE') else "N/A",
                f"{info.get('priceToBook', 0):.2f}" if info.get('priceToBook') else "N/A",
                f"{(info.get('dividendYield', 0) * 100):.2f}%" if info.get('dividendYield') else "N/A",
                f"{(info.get('returnOnEquity', 0) * 100):.2f}%" if info.get('returnOnEquity') else "N/A",
                f"{(info.get('sharesOutstanding', 0) * current_price / 10**8 / info.get('trailingPE', 1)):.2f}" if info.get('trailingPE') else "-", # 概算股本
                f"{(info.get('marketCap', 0) / 10**8):.2f}",
                info.get('address1', '-')
            ]
        }
        
        df = pd.DataFrame(basic_info)
        st.table(df) # 使用 table 顯示固定格式

        st.divider()

        # --- 2. 估價功能 ---
        st.subheader("⚙️ 自訂估價計算")
        col1, col2 = st.columns(2)
        with col1:
            # 嘗試自動抓取 EPS，抓不到則預設 30.0
            default_eps = info.get('trailingEps', 30.0)
            eps = st.number_input("輸入該股 EPS", value=float(default_eps), step=0.1)
        with col2:
            pe_target = st.number_input("自訂參考本益比 (PE)", value=20.0, step=0.1)

        fair_price = eps * pe_target
        
        st.metric(label="合理價參考", value=f"{fair_price:.2f}")

        if current_price <= fair_price:
            st.success(f"🟢 目前股價 {current_price:.2f} 低於參考價。")
        else:
            st.warning(f"🟡 目前股價 {current_price:.2f} 高於參考價。")

    except Exception as e:
        st.error(f"代號錯誤或無權限抓取數據。如果是上櫃請輸入 '{stock_code}.TWO'")

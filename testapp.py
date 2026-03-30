import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="台股精準估價系統", page_icon="📈")

st.title("📈 台股精準資訊與估價")

# --- 核心數據抓取函數 ---
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

# --- UI 介面 ---
stock_code = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")

if stock_code:
    info = fetch_stock_info(stock_code)
    
    if info:
        try:
            # 1. 提取核心數據
            current_price = info.get('current_price', 0)
            eps_ttm = info.get('trailingEps', 0) or 0 # 最近四季累積 EPS
            stock_name = info.get('shortName', stock_code)
            
            st.success(f"✅ 已取得 **{stock_name} ({info['actual_ticker']})** 數據")

            # 2. 數據精確修正邏輯
            # 殖利率修正
            dy_raw = info.get('dividendYield', 0) or 0
            dy_fixed = (dy_raw / current_price * 100) if dy_raw >= 1 else (dy_raw * 100)

            # 即時本益比換算
            pe_calc = current_price / eps_ttm if eps_ttm > 0 else 0

            # 股本與市值 (億)
            shares = info.get('sharesOutstanding', 0) or 0
            share_capital = (shares * 10) / 1e8 
            mkt_cap = (info.get('marketCap', 0) or 0) / 1e8

            # --- 顯示基本資料表格 ---
            st.subheader("📊 股票基本資料")
            basic_df = pd.DataFrame({
                "項目": ["目前股價", "最近四季累積 EPS", "即時本益比 (PE)", "殖利率", "ROE (近四季)", "市值 (億)", "股本 (億)"],
                "數值": [
                    f"{current_price:.2f}",
                    f"{eps_ttm:.2f}",
                    f"{pe_calc:.2f}",
                    f"{dy_fixed:.2f}%",
                    f"{(info.get('returnOnEquity', 0) or 0)*100:.2f}%",
                    f"{mkt_cap:,.2f}",
                    f"{share_capital:,.2f}"
                ]
            })
            st.table(basic_df)

            st.divider()

            # --- 換算目標股價結果 (直接連動上方的 eps_ttm) ---
            st.subheader("⚙️ 換算目標股價結果")
            
            # 使用 columns 顯示本益比設定框
            col1, col2, col3 = st.columns(3)
            with col1:
                low_pe = st.number_input("便宜價本益比", value=12.0, step=0.5)
            with col2:
                mid_pe = st.number_input("合理價本益比", value=15.0, step=0.5)
            with col3:
                high_pe = st.number_input("昂貴價本益比", value=20.0, step=0.5)

            # 計算價格：直接乘以基本資料抓到的 eps_ttm
            prices = {
                "便宜價": eps_ttm * low_pe,
                "合理價": eps_ttm * mid_pe,
                "昂貴價": eps_ttm * high_pe
            }

            # 顯示換算結果
            res_col1, res_col2, res_col3 = st.columns(3)
            res_col1.metric("便宜價參考", f"{prices['便宜價']:.2f}")
            res_col2.metric("合理價參考", f"{prices['合理價']:.2f}")
            res_col3.metric("昂貴價參考", f"{prices['昂貴價']:.2f}")

            # 狀態提醒
            if current_price <= prices['便宜價']:
                st.success(f"🟢 當前股價 {current_price:.2f} 處於「便宜價」以下。")
            elif current_price <= prices['合理價']:
                st.info(f"🔵 當前股價 {current_price:.2f} 處於「合理價」區間。")
            else:
                st.warning(f"🟡 當前股價 {current_price:.2f} 已超過「合理價」。")

        except Exception as e:
            st.error(f"資料處理發生錯誤。")
    else:
        st.error(f"❌ 抓取失敗。請檢查代號 '{stock_code}' 是否正確。")

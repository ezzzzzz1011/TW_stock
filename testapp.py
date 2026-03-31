import streamlit as st
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="台股自動估價系統", page_icon="🔍", layout="wide")

# --- 1. 初始化頁面狀態 ---
if 'page' not in st.session_state:
    st.session_state.page = "home"  # 預設為首頁

# --- 2. 導覽功能函數 ---
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# --- 3. 首頁畫面 (按鈕選擇) ---
if st.session_state.page == "home":
    st.title("🚀 台股投資工具箱")
    st.write("請選擇您要使用的查詢系統：")
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 個股分析")
        if st.button("個股查詢系統", use_container_width=True, type="primary"):
            go_to("stock_query")
            
    with col2:
        st.subheader("📊 ETF 分析")
        if st.button("ETF 查詢系統", use_container_width=True, type="primary"):
            go_to("etf_query")

# --- 4. 個股查詢程式碼區塊 ---
elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"):
        go_to("home")
        
    st.title("🔍 台股自動估價系統 (個股)")
    
    stock_code = st.text_input("請輸入台股代號 (例如: 2317)", value="")
    current_price = 0.0

    if stock_code:
        full_code = f"{stock_code}.TW" if "." not in stock_code else stock_code
        try:
            ticker = yf.Ticker(full_code)
            hist = ticker.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                open_price = hist['Open'].iloc[-1]
                high_price = hist['High'].iloc[-1]
                low_price = hist['Low'].iloc[-1]
                volume = hist['Volume'].iloc[-1]
                prev_close = ticker.info.get('previousClose', open_price)
                
                stock_name = ticker.info.get('shortName', stock_code)
                if "Taiwan Semiconductor" in stock_name or stock_code == "2330":
                    stock_name = "台積電"
                
                price_change = current_price - prev_close
                price_change_pct = (price_change / prev_close) * 100
                
                # 行情面板
                st.markdown(f"## {stock_name}")
                st.caption(f"資料日期：{datetime.now().strftime('%Y-%m-%d')}")
                cp1, cp2 = st.columns([2, 1])
                with cp1:
                    color = "#FF0000" if price_change > 0 else "#00FF00" if price_change < 0 else "#FFFFFF"
                    st.markdown(f"<h1 style='color: {color}; margin-bottom: 0;'>{current_price:.2f}</h1>", unsafe_allow_html=True)
                    st.markdown(f"<h3 style='color: {color}; margin-top: 0;'>{price_change:+.2f} ({price_change_pct:+.2f}%)</h3>", unsafe_allow_html=True)
                with cp2:
                    st.write("**今日行情細節**")
                    st.write(f"最高: {high_price:.2f} / 最低: {low_price:.2f}")
                    st.write(f"開盤: {open_price:.2f} / 總量: {int(volume/1000):?} 張")
                st.divider()
        except Exception as e:
            st.error(f"查詢出錯：{e}")

    # 估價參數
    col_eps, col_pe = st.columns(2)
    with col_eps:
        eps = st.number_input("輸入該股 EPS (4季累積)", min_value=0.01, step=0.1, value=10.0)
    with col_pe:
        pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)

    fair_price = eps * pe_target
    if current_price > 0:
        st.subheader("📊 換算結果")
        st.metric(label="合理價參考", value=f"{fair_price:.2f}")
        if current_price <= fair_price:
            st.success(f"✅ 目前股價 {current_price:.2f} 低於目標參考價 {fair_price:.2f}")
        else:
            st.warning(f"⚠️ 目前股價 {current_price:.2f} 已超過目標參考價 {fair_price:.2f}")
        st.divider()

    st.markdown("### 📖 說明")
    st.markdown("1. 輸入個股代碼。\n2. 輸入4季累積EPS。\n3. 輸入個股本益比。\n4. 計算公式為 `EPS × 自訂目標本益比 = 合理價參考`。")

# --- 5. ETF 查詢程式碼區塊 (預留位置) ---
elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"):
        go_to("home")
        
    st.title("📊 ETF 查詢分析系統")
    
    st.info("請將您的 ETF 查詢程式碼貼在此處")
    
    # -----------------------------------------------
    # 這裡請貼上你之後要給我的 ETF 程式碼內容
    # -----------------------------------------------
    
    st.write("目前尚未加入 ETF 具體邏輯，請提供代碼後我幫你整合進來。")

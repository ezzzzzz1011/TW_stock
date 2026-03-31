import streamlit as st
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="台股自動估價系統", page_icon="🔍")

st.title("🔍 台股自動估價系統")

# --- 側邊欄或上方輸入代號 ---
stock_code = st.text_input("請輸入台股代號 (例如: 2317)", value="2317")

if stock_code:
    full_code = f"{stock_code}.TW"
    
    try:
        # 抓取股票資料
        ticker = yf.Ticker(full_code)
        info = ticker.info
        fast = ticker.fast_info
        
        # 取得行情數據
        current_price = fast['last_price']
        prev_close = fast['previous_close']
        price_change = current_price - prev_close
        price_change_pct = (price_change / prev_close) * 100
        stock_name = info.get('shortName', stock_code)
        
        # --- 改成圖二的視覺風格 ---
        st.markdown(f"## {stock_name}")
        st.caption(f"資料日期：{datetime.now().strftime('%Y-%m-%d')}")
        
        col_price, col_details = st.columns([2, 1])
        
        with col_price:
            # 根據漲跌決定顏色
            color = "#00FF00" if price_change < 0 else "#FF0000" # 這裡依截圖呈現綠色
            st.markdown(f"<h1 style='color: {color}; margin-bottom: 0;'>{current_price:.2f}</h1>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='color: {color}; margin-top: 0;'>{price_change:+.2f} ({price_change_pct:+.2f}%)</h3>", unsafe_allow_html=True)
            
        with col_details:
            st.write("今日行情細節")
            st.write(f"最高: {fast['day_high']:.2f} / 最低: {fast['day_low']:.2f}")
            st.write(f"開盤: {fast['open']:.2f} / 總量: {int(fast['last_volume']/1000):,} 張")

    except Exception as e:
        st.error("找不到該代號，請檢查輸入是否正確。")
        current_price = 0.0

st.divider()

# --- 估價參數輸入 ---
col1, col2 = st.columns(2)

with col1:
    eps = st.number_input("輸入該股 EPS", min_value=0.01, step=0.1, value=10.0)

with col2:
    pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)

# --- 計算邏輯 ---
fair_price = eps * pe_target

# --- 結果顯示 ---
st.subheader("📊 換算結果")
st.metric(label="合理價參考", value=f"{fair_price:.2f}")

st.divider()

# 判斷邏輯
if current_price > 0:
    if current_price <= fair_price:
        st.success(f"✅ 目前股價 {current_price:.2f} 低於目標參考價 {fair_price:.2f}")
    else:
        st.warning(f"⚠️ 目前股價 {current_price:.2f} 已超過目標參考價 {fair_price:.2f}")

# --- 說明區塊 ---
st.markdown("### 📖 說明")
st.markdown("""
1. 輸入個股代碼。
2. 輸入4季累積EPS。
3. 輸入個股本益比。
4. 計算公式為 `EPS × 自訂目標本益比 = 合理價參考`。
""")

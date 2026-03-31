import streamlit as st
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="台股自動估價系統", page_icon="🔍")

st.title("🔍 台股自動估價系統")

# --- 輸入代號 ---
stock_code = st.text_input("請輸入台股代號 (例如: 2317)", value="2330")

if stock_code:
    # 判斷是否已經有後綴，沒有則補上 .TW
    full_code = f"{stock_code}.TW" if "." not in stock_code else stock_code
    
    try:
        ticker = yf.Ticker(full_code)
        
        # 為了確保價格準確，抓取最近一天的歷史資料
        hist = ticker.history(period="1d")
        if not hist.empty:
            current_price = hist['Close'].iloc[-1]
            open_price = hist['Open'].iloc[-1]
            high_price = hist['High'].iloc[-1]
            low_price = hist['Low'].iloc[-1]
            volume = hist['Volume'].iloc[-1]
            prev_close = ticker.info.get('previousClose', open_price)
        else:
            # 備援方案
            current_price = ticker.fast_info['last_price']
            open_price = ticker.fast_info['open']
            high_price = ticker.fast_info['day_high']
            low_price = ticker.fast_info['day_low']
            volume = ticker.fast_info['last_volume']
            prev_close = ticker.fast_info['previous_close']

        # 計算漲跌
        price_change = current_price - prev_close
        price_change_pct = (price_change / prev_close) * 100
        
        # 中文化名稱處理
        stock_name = ticker.info.get('shortName', stock_code)
        if "Taiwan Semiconductor" in stock_name or stock_code == "2330":
            stock_name = "台積電"
        
        # --- 顯示行情面板 (圖二風格) ---
        st.markdown(f"## {stock_name}")
        st.caption(f"資料日期：{datetime.now().strftime('%Y-%m-%d')}")
        
        col_price, col_details = st.columns([2, 1])
        
        with col_price:
            # 台灣習慣：漲紅跌綠
            color = "#FF0000" if price_change > 0 else "#00FF00" if price_change < 0 else "#FFFFFF"
            st.markdown(f"<h1 style='color: {color}; margin-bottom: 0;'>{current_price:.2f}</h1>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='color: {color}; margin-top: 0;'>{price_change:+.2f} ({price_change_pct:+.2f}%)</h3>", unsafe_allow_html=True)
            
        with col_details:
            st.write("**今日行情細節**")
            st.write(f"最高: {high_price:.2f} / 最低: {low_price:.2f}")
            st.write(f"開盤: {open_price:.2f} / 總量: {int(volume/1000):,} 張")

    except Exception as e:
        st.error(f"錯誤: {e}")
        current_price = 0.0

st.divider()

# --- 估價參數輸入 ---
col1, col2 = st.columns(2)
with col1:
    eps = st.number_input("輸入該股 EPS (4季累積)", min_value=0.01, step=0.1, value=30.0)
with col2:
    pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)

fair_price = eps * pe_target

# --- 結果顯示 ---
st.subheader("📊 換算結果")
st.metric(label="合理價參考", value=f"{fair_price:.2f}")

st.divider()

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

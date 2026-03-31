import streamlit as st
import yfinance as yf

st.set_page_config(page_title="台股自動估價系統", page_icon="🔍")

st.title("🔍 台股自動估價系統")

# --- 側邊欄或上方輸入代號 ---
stock_code = st.text_input("請輸入台股代號 (例如: 2317)", value="2317")

# 台股代號處理邏輯
if stock_code:
    full_code = f"{stock_code}.TW"
    
    try:
        # 抓取股票資料
        stock_data = yf.Ticker(full_code)
        # 取得最新收盤價
        current_price = stock_data.fast_info['last_price']
        stock_name = stock_data.info.get('longName', stock_code)
        
        st.success(f"已取得 **{stock_name}** 最新股價：**{current_price:.2f}**")
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

# --- 更新後的說明區塊 ---
st.markdown("### 📖 說明")
st.markdown("""
1. 輸入個股代碼。
2. 輸入4季累積EPS。
3. 輸入個股本益比。
4. 計算公式為 `EPS × 自訂目標本益比 = 合理參考價`。
""")

import streamlit as st

# 設定網頁標題與圖示
st.set_page_config(page_title="台股價值估算器", page_icon="📈")

st.title("📈 台股價值估算器")
st.write("透過 EPS 與歷史本益比，快速判斷股價是否合理。")

# --- 側邊欄輸入參數 ---
st.sidebar.header("輸入股票參數")
stock_name = st.sidebar.text_input("股票名稱", value="台積電")
current_price = st.sidebar.number_input("目前股價", min_value=0.0, value=700.0)
eps = st.sidebar.number_input("最近四季累積 EPS", min_value=0.0, value=30.0)

st.sidebar.subheader("本益比 (PE) 區間設定")
pe_low = st.sidebar.slider("便宜價本益比", 5, 30, 12)
pe_mid = st.sidebar.slider("合理價本益比", 5, 40, 15)
pe_high = st.sidebar.slider("昂貴價本益比", 5, 50, 20)

# --- 計算邏輯 ---
cheap_price = eps * pe_low
fair_price = eps * pe_mid
expensive_price = eps * pe_high

# --- 顯示結果 ---
st.subheader(f"📊 {stock_name} 估價分析")

col1, col2, col3 = st.columns(3)
col1.metric("便宜價", f"{cheap_price:.1f}")
col2.metric("合理價", f"{fair_price:.1f}")
col3.metric("昂貴價", f"{expensive_price:.1f}")

st.divider()

# 判斷邏輯與顯示
if current_price <= cheap_price:
    st.success(f"🟢 目前股價 {current_price}：處於【便宜區間】，具備安全邊際！")
elif current_price <= fair_price:
    st.info(f"🟡 目前股價 {current_price}：處於【合理區間】，可考慮分批佈局。")
elif current_price <= expensive_price:
    st.warning(f"🟠 目前股價 {current_price}：處於【昂貴區間】，建議觀望。")
else:
    st.error(f"🔴 目前股價 {current_price}：【極度高估】，風險較大！")

# 補充小筆記
with st.expander("💡 投資小筆記"):
    st.write("""
    - **EPS**：建議參考最近四季財報加總，或法人預估的全年 EPS。
    - **本益比**：不同產業有不同標準，半導體（高成長）與金融股（穩定）的 PE 區間大不相同。
    """)

import streamlit as st

# 設定網頁標題
st.set_page_config(page_title="台股估價工具", page_icon="💰")

st.title("💰 台股價值快速估算")
st.write("直接輸入各項數值，系統將自動計算合理區間。")

# 使用兩欄佈局，左邊輸入基礎資料，右邊輸入本益比設定
col_info, col_pe = st.columns(2)

with col_info:
    st.subheader("📌 股票基本資訊")
    stock_name = st.text_input("股票名稱/代號", value="2330 台積電")
    current_price = st.number_input("目前股價", min_value=0.0, step=0.5, value=700.0)
    eps = st.number_input("最近四季 EPS (或預估值)", min_value=0.0, step=0.1, value=30.0)

with col_pe:
    st.subheader("⚙️ 本益比設定")
    # 這裡直接讓你填寫數值
    pe_low = st.number_input("便宜價本益比 (PE)", min_value=0.0, step=0.5, value=12.0)
    pe_mid = st.number_input("合理價本益比 (PE)", min_value=0.0, step=0.5, value=15.0)
    pe_high = st.number_input("昂貴價本益比 (PE)", min_value=0.0, step=0.5, value=20.0)

# --- 計算結果 ---
cheap_price = eps * pe_low
fair_price = eps * pe_mid
expensive_price = eps * pe_high

st.divider()

# 顯示結果卡片
st.subheader(f"📊 {stock_name} 估價報告")

res_col1, res_col2, res_col3 = st.columns(3)
res_col1.metric("便宜價", f"{cheap_price:.2f}")
res_col2.metric("合理價", f"{fair_price:.2f}")
res_col3.metric("昂貴價", f"{expensive_price:.2f}")

st.write("") # 留點空隙

# 核心判斷邏輯
if current_price <= cheap_price:
    st.success(f"✅ **買入訊號**：目前股價 {current_price} 低於便宜價，具備安全邊際。")
elif current_price <= fair_price:
    st.info(f"💡 **觀望/佈局**：目前股價 {current_price} 位於合理區間。")
elif current_price <= expensive_price:
    st.warning(f"⚠️ **謹慎/減碼**：目前股價 {current_price} 偏向昂貴區間。")
else:
    st.error(f"🚨 **風險預警**：目前股價 {current_price} 已顯著高估！")

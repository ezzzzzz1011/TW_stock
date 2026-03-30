import streamlit as st

st.set_page_config(page_title="台股快速估價", page_icon="📈")

st.title("📈 台股快速估價")
st.write("輸入 EPS 與自訂本益比，快速計算合理目標價。")

# 第一排：股票基礎數據
col1, col2 = st.columns(2)
with col1:
    stock_id = st.text_input("股票名稱/代號", value="2317 鴻海")
    eps = st.number_input("輸入該股 EPS", min_value=0.01, step=0.1, value=66.26)
with col2:
    current_price = st.number_input("目前市場股價", min_value=0.0, step=0.5, value=1780.0)

st.divider()

# 第二排：僅保留一個本益比輸入
st.subheader("⚙️ 設定參考本益比 (PE)")
# 使用 columns 讓輸入框不要太寬
pe_col1, pe_col2 = st.columns([1, 1]) 
with pe_col1:
    pe_target = st.number_input("自訂參考本益比", value=27.48, step=0.1)

# --- 計算邏輯 ---
fair_price = eps * pe_target
current_pe = current_price / eps if eps > 0 else 0

# --- 結果顯示 ---
st.info(f"💡 目前市場實際本益比：**{current_pe:.2f} 倍**")

st.subheader("📊 換算結果")
# 大字顯示合理參考價
st.metric(label="合理價參考", value=f"{fair_price:.2f}")

st.divider()

# 簡單的判斷邏輯
if current_price <= fair_price:
    st.success(f"✅ 目前股價 {current_price} 低於目標參考價 {fair_price:.2f}。")
else:
    st.warning(f"⚠️ 目前股價 {current_price} 已超過目標參考價 {fair_price:.2f}。")

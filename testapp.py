import streamlit as st

st.set_page_config(page_title="個股本益比自訂估價", page_icon="📝")

st.title("📝 個股自訂本益比估價")
st.write("直接輸入你觀察到的個股本益比，快速換算合理股價。")

# 第一排：基礎數據
col1, col2 = st.columns(2)
with col1:
    stock_name = st.text_input("股票名稱/代號", value="2330 台積電")
    eps = st.number_input("輸入該股 EPS", min_value=0.01, step=0.1, value=30.0)
with col2:
    current_price = st.number_input("目前市場股價", min_value=0.0, step=0.5, value=700.0)

st.divider()

# 第二排：手動填入你觀察到的本益比
st.subheader("⚙️ 設定你想參考的本益比 (PE)")
c1, c2, c3 = st.columns(3)

with c1:
    pe_low = st.number_input("低點本益比", value=12.0, step=0.1)
with c2:
    pe_mid = st.number_input("中位本益比", value=15.0, step=0.1)
with c3:
    pe_high = st.number_input("高點本益比", value=20.0, step=0.1)

# --- 計算邏輯 ---
cheap_price = eps * pe_low
fair_price = eps * pe_mid
expensive_price = eps * pe_high

current_pe = current_price / eps if eps > 0 else 0

# --- 結果顯示 ---
st.info(f"💡 目前該股市場實際本益比約為：**{current_pe:.2f} 倍**")

st.subheader("📊 換算目標股價結果")
res1, res2, res3 = st.columns(3)
res1.metric("便宜價參考", f"{cheap_price:.2f}", help="EPS * 低點PE")
res2.metric("合理價參考", f"{fair_price:.2f}", help="EPS * 中位PE")
res3.metric("昂貴價參考", f"{expensive_price:.2f}", help="EPS * 高點PE")

st.divider()

# 最終判斷
if current_price <= cheap_price:
    st.success(f"🌟 超過預期！目前的 {current_pe:.2f} 倍低於你設定的低點 ({pe_low})。")
elif current_price <= fair_price:
    st.info(f"✅ 價格合理。目前的 {current_pe:.2f} 倍介於低點與中位數之間。")
elif current_price <= expensive_price:
    st.warning(f"⚠️ 略微偏高。目前的 {current_pe:.2f} 倍已超過合理中位數。")
else:
    st.error(f"🚨 風險較高！目前的 {current_pe:.2f} 倍已超過你設定的高點 ({pe_high})。")

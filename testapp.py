import streamlit as st
import yfinance as yf

st.set_page_config(page_title="台股自動估價系統", page_icon="🔍")

st.title("🔍 台股自動估價系統")

# --- 側邊欄或上方輸入代號 ---
stock_code = st.text_input("請輸入台股代號 (例如: 2317)", value="2317")

# 台股代號需要加上 .TW (上市) 或 .TWO (上櫃)
# 這裡寫一個簡單的邏輯自動幫你補上 .TW
if stock_code:
    full_code = f"{stock_code}.TW"
    
    try:
        # 抓取股票資料
        stock_data = yf.Ticker(full_code)
        # 取得最新收盤價 (或是最後一筆交易價)
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
    # 你可以選擇手動輸入 EPS，或是參考下方自動抓取的建議
    eps = st.number_input("輸入該股 EPS", min_value=0.01, step=0.1, value=10.0)

with col2:
    pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)

# --- 計算邏輯 ---
fair_price = eps * pe_target
current_pe = current_price / eps if eps > 0 else 0

# --- 結果顯示 ---
st.info(f"💡 目前市場實際本益比：**{current_pe:.2f} 倍**")

st.subheader("📊 換算結果")
st.metric(label="合理價參考", value=f"{fair_price:.2f}")

st.divider()

# 判斷邏輯
if current_price > 0:
    if current_price <= fair_price:
        st.success(f"✅ 目前股價 {current_price:.2f} 低於目標參考價 {fair_price:.2f}")
    else:
        st.warning(f"⚠️ 目前股價 {current_price:.2f} 已超過目標參考價 {fair_price:.2f}")

# 額外小功能：顯示該公司基本資料
with st.expander("查看公司簡介"):
    if stock_code:
        st.write(stock_data.info.get('longBusinessSummary', "暫無資料"))

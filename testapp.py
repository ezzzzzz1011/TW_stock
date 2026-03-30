import streamlit as st
import yfinance as yf

st.set_page_config(page_title="台股自動估價系統", page_icon="🔍")

st.title("🔍 台股自動估價系統")

# --- 側邊欄或上方輸入代號 ---
stock_code = st.text_input("請輸入台股代號 (例如: 2330)", value="2330")

if stock_code:
    # 台股代號處理邏輯
    full_code = f"{stock_code}.TW"
    
    try:
        stock_data = yf.Ticker(full_code)
        # 取得最新股價
        current_price = stock_data.fast_info['last_price']
        # 取得名稱 (若 Yahoo 有提供中文名稱)
        stock_name = stock_data.info.get('shortName', stock_code)
        
        st.success(f"✅ 已取得 **{stock_name}** 最新股價：**{current_price:.2f}**")
        
        # --- 估價參數輸入 ---
        col1, col2 = st.columns(2)
        with col1:
            eps = st.number_input("輸入該股 EPS", min_value=0.01, step=0.1, value=30.0)
        with col2:
            pe_target = st.number_input("自訂參考本益比 (PE)", value=20.0, step=0.1)

        # --- 計算邏輯 ---
        fair_price = eps * pe_target
        current_pe = current_price / eps if eps > 0 else 0

        # --- 結果顯示 ---
        st.info(f"💡 目前市場實際本益比：**{current_pe:.2f} 倍**")

        st.subheader("📊 換算結果")
        st.metric(label="合理價參考", value=f"{fair_price:.2f}")

        st.divider()

        # 判斷邏輯
        if current_price <= fair_price:
            st.success(f"🟢 目前股價 {current_price:.2f} 低於目標參考價 {fair_price:.2f}。")
        else:
            st.warning(f"🟡 目前股價 {current_price:.2f} 已超過目標參考價 {fair_price:.2f}。")

        # --- 修改標籤名稱為：股票基本資料 ---
        with st.expander("📊 股票基本資料"):
            # 這裡顯示產業與基本分類
            industry = stock_data.info.get('industry', '未知')
            sector = stock_data.info.get('sector', '未知')
            summary = stock_data.info.get('longBusinessSummary', '暫無詳細內容')
            
            st.write(f"**所屬產業：** {industry} ({sector})")
            st.write("**業務重點 (英文摘要)：**")
            st.write(summary)
            st.caption("註：以上數據由 Yahoo Finance 提供。")

    except Exception as e:
        st.error(f"找不到該代號 '{stock_code}'，如果是上櫃請輸入 '代號.TWO'。")

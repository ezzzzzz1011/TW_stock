import streamlit as st
import yfinance as yf
import pandas as pd
import datetime

st.set_page_config(page_title="台股股息成長分析", layout="wide")

st.title("🇹🇼 台股股息成長 (DGI) 自動分析")
st.write("輸入台股代號（例如：2330），系統將自動計算配息連續成長年數。")

# --- 輸入區 ---
stock_id = st.text_input("請輸入台股代號", value="2330")
analyze_btn = st.button("開始分析")

if analyze_btn:
    # 台股代號需要加上 .TW
    ticker_str = f"{stock_id}.TW"
    ticker = yf.Ticker(ticker_str)
    
    with st.spinner('正在讀取歷史配息數據...'):
        # 1. 取得股息歷史
        dividends = ticker.actions
        
        if dividends.empty or 'Dividends' not in dividends:
            st.error(f"找不到 {ticker_str} 的配息紀錄，請確認代號是否正確。")
        else:
            # 2. 整理年度配息金額
            div_df = dividends[['Dividends']].resample('YE').sum()
            div_df.index = div_df.index.year
            div_df = div_df.sort_index(ascending=False)
            
            # 3. 計算連續配息與成長年數
            years = div_df.index.tolist()
            amounts = div_df['Dividends'].tolist()
            
            consecutive_years = 0
            growth_years = 0
            
            # 計算邏輯 (由新往舊比)
            for i in range(len(amounts) - 1):
                # 如果今年配息 > 0，連續配息加一
                if amounts[i] > 0:
                    consecutive_years += 1
                    # 如果今年配息 > 去年配息，成長加一
                    if amounts[i] > amounts[i+1]:
                        growth_years += 1
                    else:
                        # 成長中斷就停止計算成長年數
                        pass 
                else:
                    break
            
            # --- 顯示結果 ---
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("連續配息年數", f"{consecutive_years} 年")
            with col2:
                st.metric("最新股息金額", f"${amounts[0]:.2f}")
            with col3:
                info = ticker.info
                yield_val = info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0
                st.metric("預估殖利率", f"{yield_val:.2f} %")

            st.subheader("年度配息紀錄")
            st.bar_chart(div_df)
            st.table(div_df.head(10)) # 顯示最近10年

            # 額外資訊：體質檢查
            st.subheader("🔍 公司體質快檢")
            st.write({
                "公司簡稱": info.get("longName", "N/A"),
                "產業": info.get("industry", "N/A"),
                "本益比 (PE)": info.get("trailingPE", "N/A"),
                "每股盈餘 (EPS)": info.get("trailingEps", "N/A"),
                "現金流量": f"{info.get('freeCashflow', 0):,}"
            })

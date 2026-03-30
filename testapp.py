import streamlit as st
import yfinance as yf
import pandas as pd
import time

st.set_page_config(page_title="股息成長投資分析器", layout="wide")

st.title("📈 股息成長投資 (DGI) 自動化分析")
st.write("請上傳從 Portfolio Insight 下載的 Dividend Radar Excel 檔案。")

# --- 第一步：上傳檔案 ---
uploaded_file = st.file_uploader("選擇 Excel 檔案", type=["xlsx"])

if uploaded_file:
    # 讀取 Excel (通常是第二個分頁，Header 在第三行)
    try:
        df_radar = pd.read_excel(uploaded_file, sheet_name=1, header=2)
        st.success("檔案讀取成功！")
        
        # 讓使用者選擇要分析的數量（避免一次跑太多被 Yahoo 封鎖）
        num_to_analyze = st.slider("選擇要分析的前幾檔股票：", 5, 50, 10)
        
        if st.button(f"開始分析前 {num_to_analyze} 檔"):
            results = []
            progress_bar = st.progress(0)
            
            # 選取前 N 筆
            subset_df = df_radar.head(num_to_analyze)
            
            for index, row in subset_df.iterrows():
                symbol = row['Symbol']
                st.write(f"正在抓取 {symbol} ({row['Company']})...")
                
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    
                    data = {
                        "代號": symbol,
                        "公司名稱": row['Company'],
                        "連續增發年數": row['No Years'],
                        "股息殖利率(%)": info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0,
                        "EPS (前一年)": info.get("trailingEps", "N/A"),
                        "自由現金流 (FCF)": info.get("freeCashflow", "N/A"),
                        "本益比 (PE)": info.get("trailingPE", "N/A")
                    }
                    results.append(data)
                except Exception as e:
                    st.warning(f"無法獲取 {symbol} 的數據: {e}")
                
                # 更新進度條
                progress_bar.progress((index + 1) / num_to_analyze)
                time.sleep(0.5) # 稍微停頓
            
            # --- 第三步：顯示結果 ---
            st.subheader("分析結果")
            final_df = pd.DataFrame(results)
            st.dataframe(final_df)
            
            # 提供下載
            csv = final_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="下載分析報表 (CSV)",
                data=csv,
                file_name='dividend_analysis.csv',
                mime='text/csv',
            )
            
    except Exception as e:
        st.error(f"檔案格式不正確，請確保上傳的是 Dividend Radar 原始檔。錯誤原因: {e}")

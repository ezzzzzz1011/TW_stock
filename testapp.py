import streamlit as st
import yfinance as yf
import pandas as pd
import requests

st.set_page_config(page_title="台股股息成長分析", layout="wide")

st.title("🇹🇼 台股股息成長 (DGI) 自動分析")

# --- 核心數據抓取函數 ---
@st.cache_data(ttl=3600)
def get_stock_data_v3(stock_id):
    ticker_str = f"{stock_id}.TW"
    
    # 建立一個自定義的 Session 來偽裝瀏覽器頭部 (關鍵點！)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    })
    
    ticker = yf.Ticker(ticker_str, session=session)
    
    # 取得配息歷史
    divs = ticker.actions
    # 取得基本資料 (info 有時候會報錯，我們用 try 框住)
    try:
        info = ticker.info
    except:
        info = {"longName": f"台股 {stock_id}"}
        
    return divs, info

# --- UI 介面 ---
stock_id = st.text_input("請輸入台股代號 (如: 2330, 00878, 0056)", value="2330")

if st.button("開始分析"):
    with st.spinner('正在獲取數據...'):
        try:
            dividends, info = get_stock_data_v3(stock_id)
            
            if dividends is not None and not dividends.empty and 'Dividends' in dividends:
                # 1. 整理數據：按年度加總配息金額
                df = dividends[['Dividends']].resample('YE').sum()
                df.index = df.index.year
                df = df.sort_index(ascending=False).reset_index()
                df.columns = ['年度', '現金股利']
                
                # 2. 移除 0 的年份 (還沒配息的年度)
                df = df[df['現金股利'] > 0]

                # 3. 計算連續配息年數
                consecutive_years = 0
                for val in df['現金股利']:
                    if val > 0:
                        consecutive_years += 1
                    else:
                        break
                
                # --- 數據顯示 ---
                st.subheader(f"📊 {info.get('longName', stock_id)} 分析結果")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("連續配息年數", f"{consecutive_years} 年")
                col2.metric("最新年度股利", f"${df.iloc[0]['現金股利']:.2f}")
                
                yld = info.get('dividendYield')
                col3.metric("預估殖利率", f"{yld*100:.2f}%" if yld else "N/A")

                # --- 圖表 ---
                st.bar_chart(df.set_index('年度'))
                
                with st.expander("查看詳細配息表"):
                    st.table(df)
            else:
                st.error("❌ 找不到配息紀錄，請確認代號是否正確。")
                
        except Exception as e:
            st.error(f"分析失敗，錯誤原因: {e}")

st.info("💡 提示：台股代號請直接輸入數字（如 2330），程式會自動加上 .TW。")

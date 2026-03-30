import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime

# --- 網頁設定 ---
st.set_page_config(page_title="ETF專用 Ez開發", layout="wide")

# --- 自定義 CSS ---
st.markdown("""
    <style>
    .main { background-color: #121218; color: #ffffff; }
    .stButton>button { width: 100%; border-radius: 12px; font-weight: bold; height: 3.5em; background-color: #ffffff; color: black; border: none; }
    .white-text { color: #ffffff !important; font-weight: bold; }
    /* 表格樣式優化 */
    .comp-table { width: 100%; color: white; border-collapse: collapse; margin-top: 20px; }
    .comp-table th { background-color: #1e1e28; padding: 12px; text-align: left; border-bottom: 2px solid #444; }
    .comp-table td { padding: 12px; border-bottom: 1px solid #333; }
    .yield-high { color: #ff4b4b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 核心：精準抓取成分股與比例 (圖二數據源邏輯) ---
@st.cache_data(ttl=3600)
def get_etf_full_components(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    results = []
    try:
        # 使用玩股網成分股頁面
        url = f"https://www.wantgoo.com/stock/etf/{symbol}/constituent"
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 鎖定表格行
        table_rows = soup.select('table tbody tr')
        for row in table_rows:
            cols = row.find_all('td')
            if len(cols) >= 3:
                # 抓取代號與名稱
                name_code = cols[0].text.strip().split()
                if len(name_code) >= 2:
                    code = name_code[0]
                    name = name_code[1]
                    weight = cols[2].text.strip() # 權重比例
                    
                    # 過濾：只要個股 (4碼數字)，排除 ETF
                    if code.isdigit() and len(code) == 4:
                        results.append({"code": code, "name": name, "weight": weight})
        return results
    except:
        return []

# --- 數據抓取函式 (套用你的配息邏輯) ---
def get_safe_data(symbol):
    try:
        full_ticker = f"{symbol}.TW"
        t = yf.Ticker(full_ticker)
        hist = t.history(period="5d")
        divs = t.dividends
        
        # 初始化預設值
        res = {"success": False, "price": 0.0, "yield": 0.0, "freq": "季", "multiplier": 4}
        
        if not hist.empty:
            curr_p = hist.iloc[-1]['Close']
            res["price"] = curr_p
            if not divs.empty:
                # 自動偵測頻率邏輯
                last_year = divs[divs.index > (divs.index[-1] - pd.DateOffset(years=1))]
                count = len(last_year)
                mult = 12 if count >= 10 else 4 if count >= 3 else 2 if count >= 2 else 1
                label = "月" if count >= 10 else "季" if count >= 3 else "半年" if count >= 2 else "年"
                
                avg_div = (sum(divs.tail(4)) / 4) * mult
                res["yield"] = (avg_div / curr_p) * 100
                res["freq"] = label
                res["success"] = True
        return res
    except:
        return {"success": False}

# --- 初始化 ---
if 'page' not in st.session_state: st.session_state.page = "main"

st.title("📊 ETF 成分股深度分析")
input_c1, input_c2, input_c3 = st.columns([4, 1, 1])
with input_c1:
    symbol_input = st.text_input("輸入 ETF 代號", placeholder="例如: 00919").strip()
with input_c2:
    st.write(""); st.write("")
    if st.button("開始試算"): st.session_state.page = "main"
with input_c3:
    st.write(""); st.write("")
    if st.button("🔍 查看成分股"): st.session_state.page = "holdings"

# --- 頁面切換 ---
if st.session_state.page == "holdings" and symbol_input:
    if st.button("⬅️ 返回主頁"):
        st.session_state.page = "main"
        st.rerun()

    with st.spinner('正在讀取清單並計算殖利率...'):
        comp_data = get_etf_full_components(symbol_input)
        
        if not comp_data:
            st.error("無法抓取成分股，請確認代號是否正確。")
        else:
            st.subheader(f"🎯 ETF 代號 {symbol_input} - 真實成分股清單")
            
            # 建立表格 HTML
            html = """
            <table class="comp-table">
                <thead>
                    <tr>
                        <th>代號</th><th>名稱</th><th>權重</th><th>目前股價</th><th>配息頻率</th><th>預估殖利率</th>
                    </tr>
                </thead>
                <tbody>
            """
            
            for item in comp_data:
                # 調用你的配息計算邏輯
                detail = get_safe_data(item['code'])
                if detail["success"]:
                    y_style = 'class="yield-high"' if detail['yield'] > 7 else ""
                    html += f"""
                    <tr>
                        <td>{item['code']}</td>
                        <td>{item['name']}</td>
                        <td>{item['weight']}</td>
                        <td>{detail['price']:.2f}</td>
                        <td>{detail['freq']}配</td>
                        <td {y_style}>{detail['yield']:.2f}%</td>
                    </tr>
                    """
            
            html += "</tbody></table>"
            st.markdown(html, unsafe_allow_html=True)

else:
    st.info("請輸入 ETF 代號並點擊「查看成分股」來開始。")

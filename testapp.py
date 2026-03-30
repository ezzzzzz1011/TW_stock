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
    .metric-val { font-family: 'Consolas'; font-size: 3.5rem; font-weight: bold; line-height: 1.1; }
    .stTextInput>div>div>input, .stNumberInput>div>div>input { background-color: #1e1e28 !important; color: white !important; border-radius: 8px !important; }
    .white-text { color: #ffffff !important; font-weight: bold; }
    .date-text { color: #ffffff; opacity: 0.9; font-size: 1.1rem; margin-bottom: 10px; font-weight: bold; }
    .calc-box { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #444; margin-top: 10px; }
    .tax-text { color: #ffffff; font-size: 1rem; font-weight: normal; opacity: 0.8; }
    .plan-box { background-color: #1e1e28; padding: 18px; border-radius: 10px; border: 1.5px solid #ffffff; }
    .highlight-val { font-size: 2.5rem; font-family: 'Consolas'; font-weight: bold; color: #ffffff; }
    .styled-table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 1.1rem; }
    .styled-table th { background-color: #1e1e28; color: #ffffff; text-align: left; padding: 12px; border-bottom: 2px solid #ffffff; }
    .styled-table td { padding: 12px; border-bottom: 1px solid #444; color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

# --- 核心：精準抓取成分股 (排除相關ETF) ---
@st.cache_data(ttl=3600)
def get_etf_components(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    components = []
    try:
        # 抓取玩股網 00919 頁面 (此頁面只有個股)
        url = f"https://www.wantgoo.com/stock/etf/{symbol}/constituent"
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 尋找表格中帶有代號的 a 標籤
        links = soup.select('td.text-center a')
        for link in links:
            code = link.text.strip()
            # 過濾條件：必須是數字、長度通常為 4 位 (個股)，且排除 00 開頭的 ETF 相關代號
            if code.isdigit() and len(code) == 4 and code != symbol:
                if code not in components:
                    components.append(code)
        
        # 備援：若玩股網失敗，強攻 Yahoo 奇摩個股區塊
        if not components:
            url_yf = f"https://tw.stock.yahoo.com/quote/{symbol}.TW/holding"
            soup_yf = BeautifulSoup(requests.get(url_yf, headers=headers).text, 'html.parser')
            # 找到包含股票名稱的區塊，Yahoo 個股會出現在 <a> 裡面且連結包含 quote
            for a in soup_yf.find_all('a', href=True):
                if '/quote/' in a['href']:
                    raw = a['href'].split('/')[-1].split('.')[0]
                    # 強制過濾掉 ETF：台灣 ETF 代號通常是 00XXX 或 00XXXX
                    if raw.isdigit() and len(raw) == 4:
                        components.append(raw)
        
        return list(dict.fromkeys(components))[:30] # 移除重複並回傳前 30 名
    except:
        return []

# --- 核心數據抓取 ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    default_date = datetime.now().strftime('%Y-%m-%d')
    res = {"name": symbol, "success": False, "price_hist": None, "raw_divs": [0.0]*4, "msg": "", "last_date": default_date, "multiplier": 4, "freq_label": "季"}
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                res["price_hist"] = hist
                res["last_date"] = hist.index[-1].strftime('%Y-%m-%d')
                divs = t.dividends
                if not divs.empty:
                    d_list = divs.tail(4).tolist()[::-1]
                    while len(d_list) < 4: d_list.append(0.0)
                    res["raw_divs"] = d_list
                    count_in_year = len(divs[divs.index > (divs.index[-1] - pd.DateOffset(years=1))])
                    if count_in_year >= 10: res["multiplier"], res["freq_label"] = 12, "月"
                    elif count_in_year >= 3: res["multiplier"], res["freq_label"] = 4, "季"
                    elif count_in_year >= 2: res["multiplier"], res["freq_label"] = 2, "半年"
                    else: res["multiplier"], res["freq_label"] = 1, "年"
                
                soup = BeautifulSoup(requests.get(f"https://tw.stock.yahoo.com/quote/{full_ticker}", headers=headers).text, 'html.parser')
                name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                if name_tag: res["name"] = name_tag.text.strip()
                res["success"] = True
                return res
        except: continue
    return res

# --- 初始化 ---
if 'page' not in st.session_state: st.session_state.page = "main"
if 'data' not in st.session_state: st.session_state.data = None

st.title("📈 ETF專用 Ez開發")
main_col, side_col = st.columns([8, 2])

with main_col:
    st.markdown("### 🔍 查詢設定")
    input_c1, input_c2, input_c3 = st.columns([4, 1, 1]) 
    with input_c1: 
        symbol_input = st.text_input("股票代號", placeholder="例如:00919").strip().upper()
    with input_c2:
        st.write(""); st.write("")
        if st.button("開始計算", type="primary"):
            st.session_state.page = "main"
            if symbol_input:
                with st.spinner('計算中...'): st.session_state.data = get_safe_data(symbol_input)
    with input_c3:
        st.write(""); st.write("")
        if st.button("🔍 成分股"):
            if symbol_input:
                st.session_state.page = "holdings"
                with st.spinner('正在分析真實持股...'):
                    st.session_state.data = get_safe_data(symbol_input)
                    st.session_state.comp_list = get_etf_components(symbol_input)

    if st.session_state.data and st.session_state.data.get("success"):
        data = st.session_state.data
        
        if st.session_state.page == "main":
            # --- 原始主頁面內容 ---
            mult, fl = data["multiplier"], data["freq_label"]
            latest_p = float(data["price_hist"].iloc[-1]['Close'])
            st.markdown(f"## {data['name']} <small>({fl}配)</small>", unsafe_allow_html=True)
            
            e_cols = st.columns(4)
            d1 = e_cols[0].number_input("最新", value=float(data["raw_divs"][0]), format="%.3f")
            d2 = e_cols[1].number_input("前一", value=float(data["raw_divs"][1]), format="%.3f")
            d3 = e_cols[2].number_input("前二", value=float(data["raw_divs"][2]), format="%.3f")
            d4 = e_cols[3].number_input("前三", value=float(data["raw_divs"][3]), format="%.3f")
            
            avg_div = (sum([d1, d2, d3, d4]) / 4) * mult
            st.metric("預估年配息", f"{avg_div:.2f} 元", f"實質殖利率 {(avg_div/latest_p*100):.2f}%")

        elif st.session_state.page == "holdings":
            if st.button("⬅️ 返回主試算頁"):
                st.session_state.page = "main"
                st.rerun()
            
            st.header(f"🎯 {data['name']} - 真實成分股分析")
            clist = st.session_state.get('comp_list', [])
            
            if not clist:
                st.error("目前暫時無法獲取成分股代號，請檢查網路或稍後再試。")
            else:
                for code in clist:
                    c_data = get_safe_data(code)
                    if c_data["success"]:
                        cp = c_data["price_hist"].iloc[-1]['Close']
                        c_avg = (sum(c_data["raw_divs"]) / 4) * c_data["multiplier"]
                        cyield = (c_avg / cp) * 100
                        with st.expander(f"【{code}】{c_data['name']} ▶ 殖利率 {cyield:.2f}%"):
                            col_a, col_b = st.columns(2)
                            col_a.metric("股價", f"{cp:.2f}")
                            col_b.metric("偵測配息", f"{c_data['freq_label']}配")

with side_col:
    st.success("運行中")

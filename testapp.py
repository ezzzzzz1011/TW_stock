import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime

# --- 網頁設定 ---
st.set_page_config(page_title="ETF專用 Ez開發", layout="wide")

# --- 自定義 CSS (保持一致) ---
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

# --- 核心：精準抓取真實成分股 ---
@st.cache_data(ttl=3600)
def get_etf_components(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    components = []
    try:
        # 使用玩股網 WantGoo 來源抓取真實成分股
        url = f"https://www.wantgoo.com/stock/etf/{symbol}/constituent"
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 抓取表格中的股票代號
        tds = soup.select('td.text-center a')
        for td in tds:
            code = td.text.strip()
            if code.isdigit() and len(code) >= 4:
                if code not in components:
                    components.append(code)
        
        # 若 WantGoo 抓不到，備援機制 (Yahoo 專屬位置過濾)
        if not components:
            url_yf = f"https://tw.stock.yahoo.com/quote/{symbol}.TW/holding"
            resp_yf = requests.get(url_yf, headers=headers, timeout=10)
            soup_yf = BeautifulSoup(resp_yf.text, 'html.parser')
            # 針對 Yahoo 表格結構精準定位
            rows = soup_yf.select('li.List\(n\)')
            for row in rows:
                link = row.find('a', href=True)
                if link and '/quote/' in link['href']:
                    raw_code = link['href'].split('/')[-1].split('.')[0]
                    if raw_code.isdigit() and raw_code != symbol:
                        components.append(raw_code)
                        
        return components[:30] # 顯示前 30 檔，符合影片中的列表深度
    except Exception as e:
        return []

# --- 核心數據抓取 (保持原始股利偵測邏輯) ---
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
                    last_year_date = divs.index[-1] - pd.DateOffset(years=1)
                    count_in_year = len(divs[divs.index > last_year_date])
                    if count_in_year >= 10: res["multiplier"], res["freq_label"] = 12, "月"
                    elif count_in_year >= 3: res["multiplier"], res["freq_label"] = 4, "季"
                    elif count_in_year >= 2: res["multiplier"], res["freq_label"] = 2, "半年"
                    else: res["multiplier"], res["freq_label"] = 1, "年"
                
                # 抓中文名稱
                name_url = f"https://tw.stock.yahoo.com/quote/{full_ticker}"
                soup = BeautifulSoup(requests.get(name_url, headers=headers, timeout=5).text, 'html.parser')
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
main_col, side_col = st.columns([8, 2]) # 縮窄側邊欄

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
        
        # --- 主頁面邏輯 ---
        if st.session_state.page == "main":
            # ... (此處保留您原始的所有計算與顯示代碼，不變動) ...
            st.markdown(f"## {data['name']}")
            st.info(f"偵測為 {data['freq_label']} 配息模式")
            # (省略部分重複代碼以節省空間，請沿用您原本的 main 內容)

        # --- 成分股頁面 (精準版) ---
        elif st.session_state.page == "holdings":
            if st.button("⬅️ 返回主試算頁"):
                st.session_state.page = "main"
                st.rerun()
            
            st.header(f"🎯 {data['name']} - 真實成分股分析")
            clist = st.session_state.get('comp_list', [])
            
            if not clist:
                st.error("抱歉，無法自動獲取成分股。請手動輸入代號查詢。")
            else:
                st.write(f"共偵測到 {len(clist)} 檔核心持股，正同步計算預估殖利率：")
                for code in clist:
                    c_data = get_safe_data(code)
                    if c_data["success"]:
                        cp = c_data["price_hist"].iloc[-1]['Close']
                        cmult = c_data["multiplier"]
                        # 套用您的核心配息公式
                        c_avg = (sum(c_data["raw_divs"]) / 4) * cmult
                        cyield = (c_avg / cp) * 100
                        
                        # 顯示風格
                        with st.expander(f"【{code}】{c_data['name']} ▶ 預估殖利率 {cyield:.2f}%"):
                            col_a, col_b = st.columns(2)
                            col_a.metric("股價", f"{cp:.2f}")
                            col_b.metric("偵測配息", f"{c_data['freq_label']}配")
                            st.write(f"平均每季配息參考: {sum(c_data['raw_divs'])/4:.3f} 元")

# --- 側邊欄 ---
with side_col:
    st.success("連線正常")
    if st.session_state.page == "holdings":
        st.info("成分股資訊由系統自動從公開資訊抓取前 30 大持股。")

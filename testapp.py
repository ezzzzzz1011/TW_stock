import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import pytz
import plotly.express as px

# --- 1. 網頁全域設定 ---
st.set_page_config(page_title="台股個股/ETF查詢 Ez開發", page_icon="🔍", layout="wide")

# 設定台灣時區
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 初始化頁面狀態 ---
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'data' not in st.session_state: 
    st.session_state.data = None
# 初始化投資組合清單
if 'portfolio_list' not in st.session_state:
    st.session_state.portfolio_list = []

# --- 3. 自定義 CSS ---
st.markdown("""
    <style>
    .main { background-color: #121218; color: #ffffff; }
    .stButton>button { width: 100%; border-radius: 12px; font-weight: bold; background-color: #ffffff; color: black; border: none; height: 3.5em; }
    .metric-val { font-family: 'Consolas'; font-size: 3.5rem; font-weight: bold; line-height: 1.1; }
    .stTextInput>div>div>input, .stNumberInput>div>div>input { background-color: #1e1e28 !important; color: white !important; border-radius: 8px !important; }
    .calc-box { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #444; margin-top: 10px; }
    .highlight-val { font-size: 2.5rem; font-family: 'Consolas'; font-weight: bold; color: #ffffff; }
    .styled-table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 1.1rem; }
    .styled-table th { background-color: #1e1e28; color: #ffffff; text-align: left; padding: 12px; border-bottom: 2px solid #ffffff; }
    .styled-table td { padding: 12px; border-bottom: 1px solid #444; color: #ffffff; }
    .pk-card { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #555; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 核心數據抓取函數 ---
def get_stock_info(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                name = symbol
                try:
                    name_url = f"https://tw.stock.yahoo.com/quote/{full_ticker}"
                    soup = BeautifulSoup(requests.get(name_url, headers=headers, timeout=5).text, 'html.parser')
                    name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                    if name_tag: name = name_tag.text.strip()
                except:
                    name = t.info.get('shortName', symbol)
                if symbol == "2330": name = "台積電"
                
                # 獲取配息資訊以便用於 Portfolio 計算
                divs = t.dividends
                annual_div = 0.0
                if not divs.empty:
                    last_year = divs[divs.index > (divs.index[-1] - pd.DateOffset(years=1))]
                    annual_div = last_year.sum()

                return {
                    "name": name, "price": hist['Close'].iloc[-1], "change": hist['Close'].iloc[-1] - hist['Close'].iloc[-2],
                    "pct": ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100,
                    "high": hist['High'].iloc[-1], "low": hist['Low'].iloc[-1], 
                    "open": hist['Open'].iloc[-1], "vol": hist['Volume'].iloc[-1],
                    "annual_div": annual_div, "hist": hist, "full_ticker": full_ticker
                }
        except: continue
    return None

@st.cache_data(ttl=600)
def get_safe_data_etf(symbol):
    info = get_stock_info(symbol)
    if not info: return {"success": False, "msg": f"找不到代號 {symbol}"}
    t = yf.Ticker(info["full_ticker"])
    divs = t.dividends
    raw_divs = [0.0]*4
    multiplier, freq_label = 4, "季"
    if not divs.empty:
        d_list = divs.tail(4).tolist()[::-1]
        while len(d_list) < 4: d_list.append(0.0)
        raw_divs = d_list
        last_year_date = divs.index[-1] - pd.DateOffset(years=1)
        count_in_year = len(divs[divs.index > last_year_date])
        if count_in_year >= 10: multiplier, freq_label = 12, "月"
        elif count_in_year >= 3: multiplier, freq_label = 4, "季"
        elif count_in_year >= 2: multiplier, freq_label = 2, "半年"
        else: multiplier, freq_label = 1, "年"
    return {
        "success": True, "name": info["name"], "price": info["price"], "change": info["change"], 
        "pct": info["pct"], "high": info["high"], "low": info["low"], "open": info["open"], 
        "vol": info["vol"], "raw_divs": raw_divs, "multiplier": multiplier, "freq_label": freq_label,
        "last_date": info["hist"].index[-1].strftime('%Y-%m-%d'), "full_ticker": info["full_ticker"]
    }

def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# --- 導覽邏輯 ---
if st.session_state.page == "home":
    st.title("🚀 台股個股/ETF查詢 Ez開發")
    st.divider()
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.subheader("📈 個股分析")
        if st.button("個股查詢與估價", use_container_width=True, type="primary"): go_to("stock_query")
    with col_b:
        st.subheader("📊 ETF 分析")
        if st.button("ETF 試算與規劃", use_container_width=True, type="primary"): go_to("etf_query")
    with col_c:
        st.subheader("⚔️ ETF對比")
        if st.button("ETF對比工具", use_container_width=True, type="primary"): go_to("pk_tool")
    with col_d:
        st.subheader("💼 我的組合") # 新增按鈕
        if st.button("個人投資組合", use_container_width=True, type="primary"): go_to("portfolio")

elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("🔍 台股自動估價系統 (個股)")
    stock_code = st.text_input("請輸入台股代碼 (例如: 2330)")
    if stock_code:
        info = get_stock_info(stock_code)
        if info:
            st.markdown(f"## {info['name']} - {info['price']:.2f}")
            eps = st.number_input("輸入該股 EPS", value=10.0)
            pe = st.number_input("自訂參考本益比", value=15.0)
            st.subheader(f"合理價參考：{eps * pe:.2f}")

elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF 試算工具")
    symbol = st.text_input("ETF 代號", value="00919").upper()
    if st.button("開始計算"):
        st.session_state.data = get_safe_data_etf(symbol)
    
    if st.session_state.data and st.session_state.data.get("success"):
        d = st.session_state.data
        st.markdown(f"## {d['name']} - {d['price']:.2f}")
        # 二代健保計算邏輯（僅保留二代健保，刪除預扣所得稅）
        lots = st.number_input("持有張數", value=10)
        ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
        total_raw = lots * 1000 * d['raw_divs'][0]
        nhi = (total_raw * ratio_54c/100) * 0.0211 if (total_raw * ratio_54c/100) >= 20000 else 0
        st.markdown(f"<div class='calc-box'>每期總息：{total_raw:,.0f} 元<br>二代健保：-{nhi:,.0f} 元<br><b>實領：{total_raw-nhi:,.0f} 元</b></div>", unsafe_allow_html=True)

elif st.session_state.page == "pk_tool":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("⚔️ ETF 對比")
    c1, c2 = st.columns(2)
    t1 = c1.text_input("代碼 A", value="00919")
    t2 = c2.text_input("代碼 B", value="00878")
    if st.button("開始對比"):
        st.write(f"正在對比 {t1} 與 {t2}...")

elif st.session_state.page == "portfolio": # 新增頁面實作
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("💼 個人化投資組合管理")
    with st.expander("➕ 新增持股", expanded=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        add_code = c1.text_input("代碼").upper()
        add_lots = c2.number_input("張數", min_value=0.1, value=1.0)
        if c3.button("加入"):
            info = get_stock_info(add_code)
            if info:
                st.session_state.portfolio_list.append({"code": add_code, "name": info['name'], "price": info['price'], "lots": add_lots, "annual_div": info['annual_div']})
                st.rerun()
    
    if st.session_state.portfolio_list:
        df = pd.DataFrame(st.session_state.portfolio_list)
        df['市值'] = df['price'] * df['lots'] * 1000
        # 繪製資產佔比圖
        fig = px.pie(df, values='市值', names='name', hole=0.4, title="資產比例")
        st.plotly_chart(fig)
        st.dataframe(df)
        if st.button("清空重置"): st.session_state.portfolio_list = []; st.rerun()

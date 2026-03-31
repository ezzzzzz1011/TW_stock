import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime

# --- 1. 網頁全域設定 ---
st.set_page_config(page_title="台股投資工具箱", page_icon="🔍", layout="wide")

# --- 2. 初始化頁面狀態 ---
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'data' not in st.session_state: 
    st.session_state.data = None

# --- 3. 自定義 CSS ---
st.markdown("""
    <style>
    .main { background-color: #121218; color: #ffffff; }
    .stButton>button { width: 100%; border-radius: 12px; font-weight: bold; background-color: #ffffff; color: black; border: none; }
    .metric-val { font-family: 'Consolas'; font-size: 3.5rem; font-weight: bold; line-height: 1.1; }
    .white-text { color: #ffffff !important; font-weight: bold; }
    .calc-box { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #444; margin-top: 10px; }
    .plan-box { background-color: #1e1e28; padding: 18px; border-radius: 10px; border: 1.5px solid #ffffff; }
    .highlight-val { font-size: 2.5rem; font-family: 'Consolas'; font-weight: bold; color: #ffffff; }
    .styled-table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 1.1rem; }
    .styled-table th { background-color: #1e1e28; color: #ffffff; text-align: left; padding: 12px; border-bottom: 2px solid #ffffff; }
    .styled-table td { padding: 12px; border-bottom: 1px solid #444; color: #ffffff; }
    .pk-card { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #555; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 核心數據抓取函數 (通用型) ---
def get_stock_info(symbol):
    for suffix in [".TW", ".TWO"]:
        try:
            t = yf.Ticker(f"{symbol}{suffix}")
            hist = t.history(period="5d")
            if not hist.empty:
                info = t.info
                # 處理中文名稱
                name = info.get('shortName', symbol)
                if symbol == "2330": name = "台積電"
                
                curr_p = hist['Close'].iloc[-1]
                prev_p = hist['Close'].iloc[-2]
                change = curr_p - prev_p
                pct = (change / prev_p) * 100
                
                # 估算年化股利
                divs = t.dividends
                annual_div = 0.0
                if not divs.empty:
                    last_year = divs[divs.index > (divs.index[-1] - pd.DateOffset(years=1))]
                    annual_div = last_year.sum()
                
                return {
                    "name": name, "price": curr_p, "change": change, 
                    "pct": pct, "div": annual_div, "yield": (annual_div/curr_p)*100 if curr_p>0 else 0,
                    "high": hist['High'].iloc[-1], "low": hist['Low'].iloc[-1], "vol": hist['Volume'].iloc[-1]
                }
        except: continue
    return None

@st.cache_data(ttl=600)
def get_safe_data_etf(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    res = {"name": symbol, "success": False, "price_hist": None, "raw_divs": [0.0]*4, "multiplier": 4, "freq_label": "季"}
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                res["price_hist"] = hist
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
                try:
                    soup = BeautifulSoup(requests.get(f"https://tw.stock.yahoo.com/quote/{full_ticker}", headers=headers, timeout=5).text, 'html.parser')
                    name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                    if name_tag: res["name"] = name_tag.text.strip()
                except: pass
                res["success"] = True
                return res
        except: continue
    return res

# --- 5. 導覽邏輯 ---
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# ==========================================
# 首頁：選擇功能
# ==========================================
if st.session_state.page == "home":
    st.title("🚀 台股投資工具箱")
    st.write("請選擇您要使用的工具：")
    st.divider()
    
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.subheader("📈 個股分析")
        if st.button("個股查詢系統", use_container_width=True, type="primary"):
            go_to("stock_query")
    with col_b:
        st.subheader("📊 ETF 分析")
        if st.button("ETF 查詢系統", use_container_width=True, type="primary"):
            go_to("etf_query")
    with col_c:
        st.subheader("⚔️ PK 對比")
        if st.button("雙股 PK 工具", use_container_width=True, type="primary"):
            go_to("pk_tool")

# ==========================================
# 頁面 A：個股查詢系統
# ==========================================
elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("🔍 台股自動估價系統 (個股)")
    stock_code = st.text_input("請輸入台股代碼", value="")
    current_price = 0.0
    if stock_code:
        info = get_stock_info(stock_code)
        if info:
            current_price = info['price']
            st.markdown(f"## {info['name']}")
            st.caption(f"資料日期：{datetime.now().strftime('%Y-%m-%d')}")
            cp1, cp2 = st.columns([2, 1])
            with cp1:
                color = "#FF0000" if info['change'] > 0 else "#00FF00" if info['change'] < 0 else "#FFFFFF"
                st.markdown(f"<h1 style='color: {color}; margin-bottom: 0;'>{current_price:.2f}</h1>", unsafe_allow_html=True)
                st.markdown(f"<h3 style='color: {color}; margin-top: 0;'>{info['change']:+.2f} ({info['pct']:+.2f}%)</h3>", unsafe_allow_html=True)
            with cp2:
                st.write("**今日行情細節**")
                st.write(f"最高: {info['high']:.2f} / 最低: {info['low']:.2f}")
                st.write(f"開盤: {info['vol']/1000:,.0f} 張")
            st.divider()

    col_eps, col_pe = st.columns(2)
    with col_eps: eps = st.number_input("輸入該股 EPS", min_value=0.01, step=0.1, value=10.0)
    with col_pe: pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)
    if current_price > 0:
        fair_price = eps * pe_target
        st.metric(label="合理價參考", value=f"{fair_price:.2f}")
        if current_price <= fair_price: st.success(f"✅ 目前低於目標參考價")
        else: st.warning(f"⚠️ 目前已超過目標參考價")
    st.markdown("### 📖 說明\n1. 輸入個股代碼。 2. 輸入EPS。 3. 本益比。 4. 公式 `EPS × PE`。")

# ==========================================
# 頁面 B：ETF 查詢系統
# ==========================================
elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF 專用分析系統")
    symbol_input = st.text_input("ETF 代號", placeholder="例如: 00919").strip().upper()
    if st.button("開始計算", type="primary"):
        if symbol_input: st.session_state.data = get_safe_data_etf(symbol_input)
    
    if st.session_state.data and st.session_state.data.get("success"):
        d = st.session_state.data
        latest = d["price_hist"].iloc[-1]
        curr_p = float(latest['Close'])
        st.markdown(f"## {d['name']} <small>(偵測為{d['freq_label']}配)</small>", unsafe_allow_html=True)
        st.metric("當前股價", f"{curr_p:.2f}")
        st.divider()
        st.subheader("💰 持有張數試算")
        lots = st.number_input("持有張數", min_value=0, value=10)
        total_val = lots * 1000 * curr_p
        st.info(f"預估總投入：{total_val:,.0f} 元")

# ==========================================
# 頁面 C：PK 對比工具
# ==========================================
elif st.session_state.page == "pk_tool":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("⚔️ 雙股 PK 對比工具")
    st.write("輸入兩個代號，快速對比各項指標")
    
    col_in1, col_in2 = st.columns(2)
    with col_in1: code1 = st.text_input("輸入代碼 A", value="2330").strip().upper()
    with col_in2: code2 = st.text_input("輸入代碼 B", value="2454").strip().upper()
    
    if st.button("開始 PK"):
        with st.spinner("對比數據抓取中..."):
            res1 = get_stock_info(code1)
            res2 = get_stock_info(code2)
            
            if res1 and res2:
                st.divider()
                # 頂部視覺卡片
                c1, c2 = st.columns(2)
                for i, res in enumerate([res1, res2]):
                    with [c1, c2][i]:
                        st.markdown(f"""<div class="pk-card">
                            <h3>{res['name']}</h3>
                            <h2 style="color:{'#FF0000' if res['change']>0 else '#00FF00'}">{res['price']:.2f}</h2>
                            <p>{res['change']:+.2f} ({res['pct']:+.2f}%)</p>
                        </div>""", unsafe_allow_html=True)
                
                # 詳細表格对比
                data = {
                    "指標項目": ["公司/名稱", "目前股價", "今日漲跌", "當前漲跌幅", "預估年配息", "年化殖利率"],
                    f"{code1}": [res1['name'], f"{res1['price']:.2f}", f"{res1['change']:+.2f}", f"{res1['pct']:+.2f}%", f"{res1['div']:.2f}", f"{res1['yield']:.2f}%"],
                    f"{code2}": [res2['name'], f"{res2['price']:.2f}", f"{res2['change']:+.2f}", f"{res2['pct']:+.2f}%", f"{res2['div']:.2f}", f"{res2['yield']:.2f}%"]
                }
                df = pd.DataFrame(data)
                st.table(df)
                
                st.info("💡 提示：殖利率是以過去一年配息總額進行預估，僅供參考。")
            else:
                st.error("其中一個代碼查詢失敗，請檢查代碼是否正確。")

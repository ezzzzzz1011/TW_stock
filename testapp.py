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

# --- 4. 核心數據抓取與 ETF 殖利率換算邏輯 ---
def get_comprehensive_info(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                # 抓取中文名稱
                name = symbol
                try:
                    name_url = f"https://tw.stock.yahoo.com/quote/{full_ticker}"
                    soup = BeautifulSoup(requests.get(name_url, headers=headers, timeout=5).text, 'html.parser')
                    name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                    if name_tag: name = name_tag.text.strip()
                except:
                    name = t.info.get('shortName', symbol)
                if symbol == "2330": name = "台積電"

                curr_p = hist['Close'].iloc[-1]
                change = curr_p - hist['Close'].iloc[-2]
                pct = (change / hist['Close'].iloc[-2]) * 100

                # --- 套用 ETF 分析頁面的殖利率計算邏輯 ---
                divs = t.dividends
                est_annual_div = 0.0
                freq_label = "年"
                
                if not divs.empty:
                    latest_div = divs.iloc[-1] # 最新一筆配息
                    # 偵測頻率
                    last_year_date = divs.index[-1] - pd.DateOffset(years=1)
                    count_in_year = len(divs[divs.index > last_year_date])
                    
                    if count_in_year >= 10: mult, freq_label = 12, "月"
                    elif count_in_year >= 3: mult, freq_label = 4, "季"
                    elif count_in_year >= 2: mult, freq_label = 2, "半年"
                    else: mult, freq_label = 1, "年"
                    
                    est_annual_div = latest_div * mult # 核心邏輯：最新一筆 * 頻率倍數

                return {
                    "name": name, "price": curr_p, "change": change, "pct": pct,
                    "est_annual_div": est_annual_div, 
                    "yield": (est_annual_div / curr_p) * 100 if curr_p > 0 else 0,
                    "freq": freq_label, "high": hist['High'].iloc[-1], 
                    "low": hist['Low'].iloc[-1], "vol": hist['Volume'].iloc[-1],
                    "open": hist['Open'].iloc[-1]
                }
        except: continue
    return None

# --- 5. 導覽邏輯 ---
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# ==========================================
# 首頁
# ==========================================
if st.session_state.page == "home":
    st.title("🚀 台股投資工具箱")
    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📈 個股查詢與估價", use_container_width=True, type="primary"): go_to("stock_query")
    with c2:
        if st.button("📊 ETF 試算與規劃", use_container_width=True, type="primary"): go_to("etf_query")
    with c3:
        if st.button("⚔️ 雙股 PK 工具", use_container_width=True, type="primary"): go_to("pk_tool")

# ==========================================
# 頁面 A：個股查詢 (已整合中文化與基本功能)
# ==========================================
elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("🔍 台股自動估價系統")
    code = st.text_input("請輸入台股代碼", value="2330").strip().upper()
    if code:
        res = get_comprehensive_info(code)
        if res:
            st.markdown(f"## {res['name']}")
            col1, col2 = st.columns([2, 1])
            with col1:
                color = "#FF0000" if res['change'] > 0 else "#00FF00"
                st.markdown(f"<h1 style='color:{color}'>{res['price']:.2f}</h1>", unsafe_allow_html=True)
                st.markdown(f"<h3 style='color:{color}'>{res['change']:+.2f} ({res['pct']:+.2f}%)</h3>", unsafe_allow_html=True)
            with col2:
                st.write(f"最高: {res['high']:.2f} / 最低: {res['low']:.2f}")
                st.write(f"總量: {int(res['vol']/1000):,} 張")
            st.divider()
            
            e1, e2 = st.columns(2)
            with e1: eps = st.number_input("輸入該股 EPS", value=10.0)
            with e2: pe = st.number_input("自訂參考本益比 (PE)", value=15.0)
            st.metric("合理價參考", f"{eps * pe:.2f}")

# ==========================================
# 頁面 B：ETF 分析 (使用核心換算邏輯)
# ==========================================
elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF 專用 Ez開發")
    code = st.text_input("ETF 代號", placeholder="例如: 00919").strip().upper()
    if st.button("開始計算", type="primary") and code:
        st.session_state.data = get_comprehensive_info(code)
    
    if st.session_state.data:
        d = st.session_state.data
        st.markdown(f"## {d['name']} <small>(偵測為{d['freq']}配)</small>", unsafe_allow_html=True)
        st.metric("預估年配息", f"{d['est_annual_div']:.2f}")
        st.metric("實質殖利率", f"{d['yield']:.2f}%")
        st.divider()
        st.subheader("說明")
        st.caption("1. 輸入代號後點擊開始計算。")
        st.caption("2. 系統自動偵測配息頻率 (月/季/半年/年)。")

# ==========================================
# 頁面 C：PK 對比工具 (已同步 ETF 殖利率換算邏輯)
# ==========================================
elif st.session_state.page == "pk_tool":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("⚔️ 雙股 PK 對比工具")
    
    c_in1, c_in2 = st.columns(2)
    with c_in1: code1 = st.text_input("輸入代碼 A", value="00918").strip().upper()
    with c_in2: code2 = st.text_input("輸入代碼 B", value="00919").strip().upper()
    
    if st.button("開始 PK"):
        r1, r2 = get_comprehensive_info(code1), get_comprehensive_info(code2)
        if r1 and r2:
            st.divider()
            # 視覺卡片
            v1, v2 = st.columns(2)
            for i, r in enumerate([r1, r2]):
                with [v1, v2][i]:
                    st.markdown(f"""<div class="pk-card">
                        <h3>{r['name']}</h3>
                        <h2 style="color:{'#FF0000' if r['change']>0 else '#00FF00'}">{r['price']:.2f}</h2>
                        <p>{r['change']:+.2f} ({r['pct']:+.2f}%)</p>
                    </div>""", unsafe_allow_html=True)
            
            # 對比表格
            df = pd.DataFrame({
                "指標項目": ["公司/名稱", "目前股價", "今日漲跌", "當前漲跌幅", "偵測配息頻率", "預估年配息", "年化殖利率"],
                f"{code1}": [r1['name'], f"{r1['price']:.2f}", f"{r1['change']:+.2f}", f"{r1['pct']:.2f}%", r1['freq'], f"{r1['est_annual_div']:.2f}", f"{r1['yield']:.2f}%"],
                f"{code2}": [r2['name'], f"{r2['price']:.2f}", f"{r2['change']:+.2f}", f"{r2['pct']:.2f}%", r2['freq'], f"{r2['est_annual_div']:.2f}", f"{r2['yield']:.2f}%"]
            })
            st.table(df)
            st.info(f"💡 註：預估年配息是以「最新一筆配息」乘以「偵測頻率({r1['freq']}/{r2['freq']})」計算。")

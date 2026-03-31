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
    .calc-box { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #444; margin-top: 10px; }
    .highlight-val { font-size: 2.5rem; font-family: 'Consolas'; font-weight: bold; color: #ffffff; }
    .pk-card { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #555; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 核心數據抓取函數 (含中文化與頻率偵測) ---
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
                prev_p = hist['Close'].iloc[-2]
                change = curr_p - prev_p
                pct = (change / prev_p) * 100

                # 偵測配息頻率邏輯
                divs = t.dividends
                raw_divs = [0.0]*4
                est_annual_div = 0.0
                multiplier = 4
                freq_label = "季"
                
                if not divs.empty:
                    # 獲取最近四次配息
                    d_list = divs.tail(4).tolist()[::-1]
                    while len(d_list) < 4: d_list.append(0.0)
                    raw_divs = d_list
                    
                    # 偵測頻率
                    last_year_date = divs.index[-1] - pd.DateOffset(years=1)
                    count_in_year = len(divs[divs.index > last_year_date])
                    if count_in_year >= 10: multiplier, freq_label = 12, "月"
                    elif count_in_year >= 3: multiplier, freq_label = 4, "季"
                    elif count_in_year >= 2: multiplier, freq_label = 2, "半年"
                    else: multiplier, freq_label = 1, "年"
                    
                    # 以最新一筆配息計算年化
                    est_annual_div = raw_divs[0] * multiplier

                return {
                    "success": True, "name": name, "price": curr_p, "change": change, "pct": pct,
                    "high": hist['High'].iloc[-1], "low": hist['Low'].iloc[-1], 
                    "open": hist['Open'].iloc[-1], "vol": hist['Volume'].iloc[-1],
                    "raw_divs": raw_divs, "multiplier": multiplier, "freq": freq_label,
                    "est_annual_div": est_annual_div, "yield": (est_annual_div/curr_p)*100 if curr_p>0 else 0
                }
        except: continue
    return {"success": False}

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
# 頁面 A：個股查詢
# ==========================================
elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("🔍 台股自動估價系統")
    code = st.text_input("請輸入台股代碼", value="2330").strip().upper()
    if code:
        res = get_comprehensive_info(code)
        if res["success"]:
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
# 頁面 B：ETF 分析 (修正 KeyError)
# ==========================================
elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF 專用分析系統")
    code = st.text_input("ETF 代號", placeholder="例如: 00919").strip().upper()
    if st.button("開始計算", type="primary") and code:
        st.session_state.data = get_comprehensive_info(code)
    
    if st.session_state.data and st.session_state.data.get("success"):
        d = st.session_state.data
        # 修正這裡的鍵名：d['freq'] 必須存在
        st.markdown(f"## {d['name']} <small>(偵測為{d['freq']}配)</small>", unsafe_allow_html=True)
        
        m_color = "#ff4b4b" if d['change'] >= 0 else "#00ff00"
        st.markdown(f"<div class='metric-val' style='color:{m_color}'>{d['price']:.2f}</div>", unsafe_allow_html=True)
        
        st.divider()
        st.subheader("📑 歷史配息參考 (手動微調)")
        e_cols = st.columns(4)
        v1 = e_cols[0].number_input("最新", value=float(d["raw_divs"][0]), format="%.3f")
        v2 = e_cols[1].number_input("前一", value=float(d["raw_divs"][1]), format="%.3f")
        v3 = e_cols[2].number_input("前二", value=float(d["raw_divs"][2]), format="%.3f")
        v4 = e_cols[3].number_input("前三", value=float(d["raw_divs"][3]), format="%.3f")
        
        # 根據手動輸入重新計算
        new_annual = v1 * d["multiplier"]
        new_yield = (new_annual / d['price']) * 100
        
        sc1, sc2 = st.columns(2)
        with sc1:
            st.caption(f"預估年配息 ({d['freq']}配換算)")
            st.markdown(f"<div class='highlight-val'>{new_annual:.2f}</div>", unsafe_allow_html=True)
        with sc2:
            st.caption("實質殖利率")
            st.markdown(f"<div class='highlight-val'>{new_yield:.2f}%</div>", unsafe_allow_html=True)

# ==========================================
# 頁面 C：PK 對比工具
# ==========================================
elif st.session_state.page == "pk_tool":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("⚔️ 雙股 PK 對比工具")
    c_in1, c_in2 = st.columns(2)
    with c_in1: cd1 = st.text_input("輸入代碼 A", value="00918").strip().upper()
    with c_in2: cd2 = st.text_input("輸入代碼 B", value="00919").strip().upper()
    
    if st.button("開始 PK"):
        r1, r2 = get_comprehensive_info(cd1), get_comprehensive_info(cd2)
        if r1["success"] and r2["success"]:
            st.divider()
            # 顯示表格
            df = pd.DataFrame({
                "指標項目": ["名稱", "目前股價", "今日漲跌", "偵測頻率", "預估年配息", "年化殖利率"],
                f"{cd1}": [r1['name'], f"{r1['price']:.2f}", f"{r1['change']:+.2f}", r1['freq'], f"{r1['est_annual_div']:.2f}", f"{r1['yield']:.2f}%"],
                f"{cd2}": [r2['name'], f"{r2['price']:.2f}", f"{r2['change']:+.2f}", r2['freq'], f"{r2['est_annual_div']:.2f}", f"{r2['yield']:.2f}%"]
            })
            st.table(df)

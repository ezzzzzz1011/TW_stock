import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import pytz
import plotly.express as px
import os

# --- 1. 網頁全域設定 ---
st.set_page_config(page_title="台股個股/ETF查詢 Ez開發", page_icon="🔍", layout="wide")

# 設定台灣時區
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 帳號系統資料庫 (CSV) ---
USER_DB = "users.csv"

if not os.path.exists(USER_DB):
    pd.DataFrame(columns=["username", "password"]).to_csv(USER_DB, index=False)

def load_users():
    return pd.read_csv(USER_DB, dtype={"username": str, "password": str})

def add_user(username, password):
    df = load_users()
    if username in df["username"].values:
        return False
    new_user = pd.DataFrame([[username, password]], columns=["username", "password"])
    pd.concat([df, new_user]).to_csv(USER_DB, index=False)
    return True

# --- 3. 資料持久化邏輯 (按用戶存檔) ---
def get_user_portfolio_file():
    # 根據登入帳號產生專屬檔名
    user = st.session_state.get("current_user", "default")
    return f"portfolio_{user}.csv"

def load_portfolio():
    file = get_user_portfolio_file()
    if os.path.exists(file):
        try:
            return pd.read_csv(file, dtype={"代碼": str})
        except:
            return pd.DataFrame(columns=["代碼", "張數"])
    return pd.DataFrame(columns=["代碼", "張數"])

def save_portfolio(df):
    file = get_user_portfolio_file()
    df.to_csv(file, index=False)

# --- 4. 初始化狀態 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'data' not in st.session_state: 
    st.session_state.data = None

# --- 5. 自定義 CSS ---
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

# --- 6. 核心數據抓取函數 ---
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
                curr_p = hist['Close'].iloc[-1]
                prev_p = hist['Close'].iloc[-2]
                change = curr_p - prev_p
                pct = (change / prev_p) * 100
                return {
                    "name": name, "price": curr_p, "change": change, 
                    "pct": pct, "high": hist['High'].iloc[-1], "low": hist['Low'].iloc[-1], 
                    "open": hist['Open'].iloc[-1], "vol": hist['Volume'].iloc[-1],
                    "hist": hist, "full_ticker": full_ticker, "dividends": t.dividends
                }
        except: continue
    return None

@st.cache_data(ttl=600)
def get_safe_data_etf(symbol):
    info = get_stock_info(symbol)
    if not info: return {"success": False, "msg": f"找不到代號 {symbol}"}
    divs = info["dividends"]
    raw_divs = [0.0]*4
    multiplier = 4
    freq_label = "季"
    last_date = info["hist"].index[-1].strftime('%Y-%m-%d')
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
        "success": True, "name": info["name"], "price": info["price"],
        "change": info["change"], "pct": info["pct"], "high": info["high"],
        "low": info["low"], "open": info["open"], "vol": info["vol"],
        "raw_divs": raw_divs, "multiplier": multiplier, "freq_label": freq_label,
        "last_date": last_date, "price_hist": info["hist"], "full_ticker": info["full_ticker"]
    }

def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# --- 7. 登入與註冊頁面 ---
def auth_page():
    st.title("🔐 歡迎使用 Ez台股開發工具")
    tab1, tab2 = st.tabs(["帳號登入", "新用戶註冊"])
    
    with tab1:
        with st.form("login_form"):
            user = st.text_input("帳號")
            pw = st.text_input("密碼", type="password")
            if st.form_submit_button("登入系統", type="primary"):
                users_df = load_users()
                match = users_df[(users_df["username"] == user) & (users_df["password"] == pw)]
                if not match.empty:
                    st.session_state.logged_in = True
                    st.session_state.current_user = user
                    # 登入後立即載入該用戶的投資組合
                    st.session_state.portfolio = load_portfolio()
                    st.rerun()
                else:
                    st.error("帳號或密碼錯誤")

    with tab2:
        with st.form("reg_form"):
            new_user = st.text_input("設定帳號")
            new_pw = st.text_input("設定密碼", type="password")
            confirm_pw = st.text_input("再次輸入密碼", type="password")
            if st.form_submit_button("提交註冊"):
                if new_pw != confirm_pw:
                    st.error("密碼輸入不一致")
                elif len(new_user) < 2:
                    st.warning("帳號名稱太短")
                else:
                    if add_user(new_user, new_pw):
                        st.success("註冊成功！請切換至「帳號登入」標籤進入系統。")
                    else:
                        st.error("此帳號已被註冊")

# ==========================================
# 主程式邏輯控制
# ==========================================
if not st.session_state.logged_in:
    auth_page()
else:
    # 側邊欄：顯示用戶資訊與登出
    with st.sidebar:
        st.markdown(f"### 👤 使用者: {st.session_state.current_user}")
        if st.button("登出系統"):
            st.session_state.logged_in = False
            st.session_state.page = "home"
            st.rerun()
        st.divider()
        st.caption("Ez開發工具 v1.0")

    # --- 頁面 A：首頁 ---
    if st.session_state.page == "home":
        st.title("🚀 台股個股/ETF查詢 Ez開發")
        st.write(f"您好 {st.session_state.current_user}，請選擇功能進入：")
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
            st.subheader("💼 我的資產")
            if st.button("個人投資組合", use_container_width=True, type="primary"): go_to("portfolio")

    # --- 頁面 B：個股查詢 ---
    elif st.session_state.page == "stock_query":
        if st.button("⬅️ 返回工具箱"): go_to("home")
        st.title("🔍 台股自動估價系統 (個股)")
        main_col, side_col = st.columns([8, 4])
        with main_col:
            stock_code = st.text_input("請輸入台股代碼 (例如: 2330)", value="")
            current_price = 0.0
            if stock_code:
                info = get_stock_info(stock_code)
                if info:
                    current_price = info['price']
                    st.markdown(f"## {info['name']}")
                    color = "#ff4b4b" if info['change'] > 0 else "#00ff00" if info['change'] < 0 else "#FFFFFF"
                    st.markdown(f"<div class='metric-val' style='color:{color}'>{current_price:.2f}</div>", unsafe_allow_html=True)
                    st.markdown(f"<span style='color:{color}; font-weight:bold; font-size:1.5rem;'>{info['change']:+.2f} ({info['pct']:+.2f}%)</span>", unsafe_allow_html=True)
                    st.divider()
            col_eps, col_pe = st.columns(2)
            with col_eps: eps = st.number_input("輸入該股 EPS (4季累積)", min_value=0.01, step=0.1, value=10.0)
            with col_pe: pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)
            if current_price > 0:
                fair_price = eps * pe_target
                st.markdown(f"<div class='calc-box'>合理價參考：<span class='highlight-val'>{fair_price:.2f}</span></div>", unsafe_allow_html=True)
                if current_price <= fair_price: st.success(f"✅ 目前股價 {current_price:.2f} 低於目標參考價")
                else: st.warning(f"⚠️ 目前股價 {current_price:.2f} 已超過目標參考價")
        with side_col:
            st.write("### 📖 說明")
            st.info("計算公式：EPS × 自訂本益比 = 參考價")

    # --- 頁面 C：ETF 分析 ---
    elif st.session_state.page == "etf_query":
        if st.button("⬅️ 返回工具箱"): go_to("home")
        st.title("📈 ETF 專用 ")
        main_col, side_col = st.columns([8, 4])
        with main_col:
            symbol_input = st.text_input("ETF 代號", placeholder="例如: 00919").strip().upper()
            if st.button("開始計算", type="primary"):
                if symbol_input:
                    with st.spinner('抓取數據中...'):
                        st.session_state.data = get_safe_data_etf(symbol_input)
            if st.session_state.data and st.session_state.data.get("success"):
                d = st.session_state.data
                m_color = "#ff4b4b" if d['change'] >= 0 else "#00ff00"
                st.markdown(f"## {d['name']} <small>(偵測為{d['freq_label']}配息)</small>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-val' style='color:{m_color}'>{d['price']:.2f}</div>", unsafe_allow_html=True)
                st.divider()
                # (其餘 ETF 計算邏輯與您原本代碼相同...)
                e_cols = st.columns(4)
                d1 = e_cols[0].number_input("最新", value=float(d["raw_divs"][0]), format="%.3f")
                d2 = e_cols[1].number_input("前一", value=float(d["raw_divs"][1]), format="%.3f")
                d3 = e_cols[2].number_input("前二", value=float(d["raw_divs"][2]), format="%.3f")
                d4 = e_cols[3].number_input("前三", value=float(d["raw_divs"][3]), format="%.3f")
                avg_annual = (sum([d1, d2, d3, d4]) / 4) * d["multiplier"]
                real_yield = (avg_annual / d['price']) * 100
                st.write(f"預估年化殖利率: {real_yield:.2f}%")

    # --- 頁面 D：PK 對比工具 ---
    elif st.session_state.page == "pk_tool":
        if st.button("⬅️ 返回工具箱"): go_to("home")
        st.title("⚔️ ETF 對比工具")
        col_in1, col_in2 = st.columns(2)
        with col_in1: code1 = st.text_input("輸入代碼 A", value="00919").strip().upper()
        with col_in2: code2 = st.text_input("輸入代碼 B", value="00878").strip().upper()
        if st.button("開始對比"):
            r1, r2 = get_safe_data_etf(code1), get_safe_data_etf(code2)
            if r1["success"] and r2["success"]:
                st.table(pd.DataFrame({
                    "指標": ["目前價格", "當前漲幅"],
                    code1: [f"{r1['price']:.2f}", f"{r1['pct']:.2f}%"],
                    code2: [f"{r2['price']:.2f}", f"{r2['pct']:.2f}%"]
                }))

    # --- 頁面 E：個人投資組合 (專屬存檔) ---
    elif st.session_state.page == "portfolio":
        if st.button("⬅️ 返回工具箱"): go_to("home")
        st.title(f"💼 {st.session_state.current_user} 的投資組合")
        
        # 確保有資料可以編輯
        if 'portfolio' not in st.session_state:
            st.session_state.portfolio = load_portfolio()
            
        edited_df = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True)
        
        if st.button("更新、儲存並計算", type="primary"):
            save_portfolio(edited_df)
            st.session_state.portfolio = edited_df
            
            results = []
            total_market_val = 0
            valid_df = edited_df.dropna(subset=["代碼", "張數"])
            if not valid_df.empty:
                for _, row in valid_df.iterrows():
                    code = str(row["代碼"]).strip().upper()
                    shares = float(row["張數"]) * 1000
                    data = get_safe_data_etf(code)
                    if data["success"]:
                        m_val = data["price"] * shares
                        results.append({"名稱": data["name"], "持有價值": m_val})
                        total_market_val += m_val
                
                if results:
                    st.metric("總資產規模", f"${total_market_val:,.0f}")
                    st.plotly_chart(px.pie(pd.DataFrame(results), values='持有價值', names='名稱'))

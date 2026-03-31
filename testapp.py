import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import pytz
import plotly.express as px

# --- 0. 帳號與獨立儲存系統邏輯 ---
@st.cache_resource
def get_user_db():
    # 儲存 帳號:密碼
    return {"admin": "8888"}

@st.cache_resource
def get_all_portfolios():
    # 儲存 帳號:DataFrame
    return {}

user_db = get_user_db()
all_portfolios = get_all_portfolios()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

def login_ui():
    st.markdown("""
        <style>
        .auth-container {
            max-width: 400px;
            margin: 100px auto;
            padding: 30px;
            background-color: #1e1e28;
            border-radius: 15px;
            border: 1px solid #444;
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.title("🔐 系統登入")
    
    tab1, tab2 = st.tabs(["帳號登入", "新用戶註冊"])
    
    with tab1:
        u_id = st.text_input("帳號", key="l_user")
        u_pw = st.text_input("密碼", type="password", key="l_pw")
        if st.button("登入系統", use_container_width=True, type="primary"):
            if u_id in user_db and user_db[u_id] == u_pw:
                st.session_state.logged_in = True
                st.session_state.current_user = u_id
                # 登入時載入該帳號資料
                if u_id not in all_portfolios:
                    all_portfolios[u_id] = pd.DataFrame(columns=["代碼", "張數"])
                st.session_state.portfolio = all_portfolios[u_id]
                st.rerun()
            else:
                st.error("帳號或密碼錯誤")
                
    with tab2:
        new_u = st.text_input("設定帳號", key="r_user")
        new_p = st.text_input("設定密碼", type="password", key="r_pw")
        confirm_p = st.text_input("確認密碼", type="password", key="r_confirm")
        if st.button("完成註冊", use_container_width=True):
            if new_u in user_db:
                st.warning("此帳號已存在")
            elif new_p != confirm_p:
                st.error("密碼不一致")
            elif not new_u or not new_p:
                st.error("請填寫帳號密碼")
            else:
                user_db[new_u] = new_p
                all_portfolios[new_u] = pd.DataFrame(columns=["代碼", "張數"])
                st.success("註冊成功！請切換至登入分頁")
                
    st.markdown('</div>', unsafe_allow_html=True)

if not st.session_state.logged_in:
    login_ui()
    st.stop()

# --- 1. 網頁全域設定 ---
st.set_page_config(page_title="台股個股/ETF查詢 Ez開發", page_icon="🔍", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 初始化頁面狀態 ---
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'data' not in st.session_state: 
    st.session_state.data = None
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = all_portfolios.get(st.session_state.current_user, pd.DataFrame(columns=["代碼", "張數"]))

# --- 3. 自定義 CSS ---
st.markdown("""
    <style>
    .main { background-color: #121218; color: #ffffff; }
    .stButton>button { width: 100%; border-radius: 12px; font-weight: bold; background-color: #ffffff; color: black; border: none; height: 3.5em; }
    .metric-val { font-family: 'Consolas'; font-size: 3.5rem; font-weight: bold; line-height: 1.1; }
    .calc-box { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #444; margin-top: 10px; }
    .highlight-val { font-size: 2.5rem; font-family: 'Consolas'; font-weight: bold; color: #ffffff; }
    .pk-card { background-color: #1e1e28; padding: 20px; border-radius: 15px; border: 1px solid #555; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. 核心數據抓取函數 ---
def get_stock_info(symbol):
    headers = {'User-Agent': 'Mozilla/5.0'}
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
                except: pass
                
                curr_p = hist['Close'].iloc[-1]
                prev_p = hist['Close'].iloc[-2]
                return {
                    "name": name, "price": curr_p, "change": curr_p - prev_p, 
                    "pct": ((curr_p - prev_p) / prev_p) * 100, "high": hist['High'].iloc[-1], 
                    "low": hist['Low'].iloc[-1], "open": hist['Open'].iloc[-1], 
                    "vol": hist['Volume'].iloc[-1], "dividends": t.dividends
                }
        except: continue
    return None

@st.cache_data(ttl=600)
def get_safe_data_etf(symbol):
    info = get_stock_info(symbol)
    if not info: return {"success": False}
    
    divs = info["dividends"]
    raw_divs, multiplier, freq_label = [0.0]*4, 4, "季"
    
    if not divs.empty:
        d_list = divs.tail(4).tolist()[::-1]
        raw_divs = (d_list + [0.0]*4)[:4]
        count = len(divs[divs.index > (divs.index[-1] - pd.DateOffset(years=1))])
        if count >= 10: multiplier, freq_label = 12, "月"
        elif count >= 3: multiplier, freq_label = 4, "季"
        elif count >= 2: multiplier, freq_label = 2, "半年"
        else: multiplier, freq_label = 1, "年"
        
    return {
        "success": True, "name": info["name"], "price": info["price"],
        "change": info["change"], "pct": info["pct"], "high": info["high"],
        "low": info["low"], "open": info["open"], "vol": info["vol"],
        "raw_divs": raw_divs, "multiplier": multiplier, "freq_label": freq_label
    }

def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# --- 5. 導覽邏輯 ---
if st.session_state.page == "home":
    st.title("🚀 台股個股/ETF查詢 Ez開發")
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        if st.button("📈 個股分析"): go_to("stock_query")
    with col_b:
        if st.button("📊 ETF 試算"): go_to("etf_query")
    with col_c:
        if st.button("⚔️ ETF 對比"): go_to("pk_tool")
    with col_d:
        if st.button("💼 我的資產"): go_to("portfolio")

# --- 頁面 A：個股 ---
elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回"): go_to("home")
    st.title("🔍 個股自動估價系統")
    stock_code = st.text_input("輸入台股代碼", value="")
    if stock_code:
        info = get_stock_info(stock_code)
        if info:
            st.subheader(f"{info['name']}")
            st.metric("目前股價", f"{info['price']:.2f}", f"{info['pct']:.2f}%")
            eps = st.number_input("輸入該股 EPS", value=10.0)
            pe_target = st.number_input("自訂本益比", value=15.0)
            st.success(f"合理價參考：{eps * pe_target:.2f}")

# --- 頁面 B：ETF ---
elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回"): go_to("home")
    st.title("📈 ETF 專用分析")
    symbol = st.text_input("ETF 代號").strip().upper()
    if st.button("開始計算") and symbol:
        st.session_state.data = get_safe_data_etf(symbol)
    if st.session_state.data and st.session_state.data.get("success"):
        d = st.session_state.data
        st.header(f"{d['name']} ({d['freq_label']}配)")
        st.metric("現價", f"{d['price']:.2f}", f"{d['pct']:.2f}%")
        avg_annual = (sum(d["raw_divs"]) / 4) * d["multiplier"]
        st.markdown(f"<div class='calc-box'>預估年配息：{avg_annual:.2f}<br>實質殖利率：{(avg_annual/d['price'])*100:.2f}%</div>", unsafe_allow_html=True)

# --- 頁面 C：PK 工具 ---
elif st.session_state.page == "pk_tool":
    if st.button("⬅️ 返回"): go_to("home")
    st.title("⚔️ ETF 對比工具")
    col1, col2 = st.columns(2)
    c1 = col1.text_input("代碼 A", "00919")
    c2 = col2.text_input("代碼 B", "00878")
    if st.button("執行對比"):
        r1, r2 = get_safe_data_etf(c1), get_safe_data_etf(c2)
        if r1["success"] and r2["success"]:
            st.table(pd.DataFrame({
                "項目": ["價格", "漲跌幅", "頻率"],
                c1: [f"{r1['price']:.2f}", f"{r1['pct']:.2f}%", r1['freq_label']],
                c2: [f"{r2['price']:.2f}", f"{r2['pct']:.2f}%", r2['freq_label']]
            }))

# --- 頁面 D：投資組合 (預列 20 行) ---
elif st.session_state.page == "portfolio":
    if st.button("⬅️ 返回"): go_to("home")
    st.title(f"💼 {st.session_state.current_user} 的投資組合")
    
    # 初始化：若為空則直接給 20 行空白列
    if st.session_state.portfolio is None or st.session_state.portfolio.empty:
        st.session_state.portfolio = pd.DataFrame([{"代碼": "", "張數": 0.0} for _ in range(20)])

    st.markdown("### 📝 編輯並儲存清單 (預設顯示 20 行)")
    edited_df = st.data_editor(
        st.session_state.portfolio, 
        num_rows="dynamic", 
        use_container_width=True,
        key="portfolio_editor",
        column_config={
            "代碼": st.column_config.TextColumn("代碼", placeholder="例如: 00919"),
            "張數": st.column_config.NumberColumn("張數", min_value=0.0, step=1.0)
        }
    )

    if st.button("💾 儲存並計算", type="primary"):
        # 僅提取有填寫代碼的列
        final_df = edited_df.copy()
        final_df["代碼"] = final_df["代碼"].astype(str).str.strip().upper()
        final_df = final_df[final_df["代碼"] != ""]
        final_df = final_df.dropna(subset=["代碼"])
        
        st.session_state.portfolio = final_df
        all_portfolios[st.session_state.current_user] = final_df
        
        results = []
        total_v = 0
        if not final_df.empty:
            with st.spinner("計算中..."):
                for _, row in final_df.iterrows():
                    d = get_safe_data_etf(row["代碼"])
                    if d["success"]:
                        v = d["price"] * float(row["張數"]) * 1000
                        results.append({"名稱": d["name"], "價值": v})
                        total_v += v
            
            if results:
                st.metric("總資產價值", f"${total_v:,.0f}")
                st.plotly_chart(px.pie(pd.DataFrame(results), values='價值', names='名稱'))
                st.success("儲存成功")
            else:
                st.error("查無有效代碼")

import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import pytz
import plotly.express as px
import io
import gspread
from google.oauth2.service_account import Credentials

# --- 0. 雲端資料庫連線與帳號邏輯 ---

@st.cache_resource
def init_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"].to_dict()
    
    if "private_key" in creds_dict:
        pk = creds_dict["private_key"]
        pk = pk.replace("\\n", "\n").replace('"', '')
        creds_dict["private_key"] = pk
    
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client

# 初始化資料庫物件
try:
    conn = init_connection()
    sh = conn.open("streamlit_db")
    
    try:
        user_sheet = sh.worksheet("users")
    except:
        user_sheet = sh.add_worksheet(title="users", rows="100", cols="2")
        user_sheet.append_row(["username", "password"])
        user_sheet.append_row(["admin", "8888"])
    
    try:
        portfolio_sheet = sh.worksheet("portfolios")
    except:
        portfolio_sheet = sh.add_worksheet(title="portfolios", rows="1000", cols="2")
        portfolio_sheet.append_row(["username", "data_json"])
        
except Exception as e:
    st.error(f"❌ 雲端資料庫連線失敗：{e}")
    st.stop()

def get_cloud_users():
    """即時從雲端讀取用戶清單"""
    records = user_sheet.get_all_records()
    return {str(row['username']).strip(): str(row['password']).strip() for row in records}

def load_portfolio_from_cloud(username):
    """載入特定使用者的投資組合"""
    try:
        cell = portfolio_sheet.find(username)
        if cell:
            json_data = portfolio_sheet.cell(cell.row, 2).value
            return pd.read_json(io.StringIO(json_data))
    except Exception:
        pass
    return pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20)])

def save_portfolio_to_cloud(username, df):
    """儲存投資組合至雲端"""
    clean_df = df.dropna(subset=['代碼']).copy() if '代碼' in df.columns else df
    json_data = clean_df.to_json(orient='records', date_format='iso')
    try:
        cell = portfolio_sheet.find(username)
        if cell:
            portfolio_sheet.update_cell(cell.row, 2, json_data)
        else:
            portfolio_sheet.append_row([username, json_data])
        return True
    except Exception as e:
        st.error(f"⚠️ 雲端儲存失敗: {e}")
        return False

# --- 初始化應用程式狀態 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user' not in st.session_state:
    st.session_state.current_user = None
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = None
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'data' not in st.session_state: 
    st.session_state.data = None

# --- 登入介面邏輯 ---
def login_ui():
    st.markdown("""
        <style>
        .auth-container {
            max-width: 450px;
            margin: 50px auto;
            padding: 40px;
            background-color: #1e1e28;
            border-radius: 20px;
            border: 1px solid #3e3e42;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.title("🛡️ 投資助手系統")

    user_db = get_cloud_users()
    tab1, tab2 = st.tabs(["🔑 帳號登入", "📝 新用戶註冊"])

    with tab1:
        u_id = st.text_input("帳號名稱", key="l_user", placeholder="請輸入帳號")
        u_pw = st.text_input("存取密碼", type="password", key="l_pw", placeholder="請輸入密碼")
        
        if st.button("確認登入", use_container_width=True, type="primary"):
            if user_db.get(u_id) == u_pw:
                st.session_state.logged_in = True
                st.session_state.current_user = u_id
                st.session_state.portfolio = load_portfolio_from_cloud(u_id)
                st.success("登入成功！")
                st.rerun()
            else:
                st.error("❌ 帳號或密碼不正確")

    with tab2:
        st.info("註冊資料將儲存於雲端，重啟系統不會遺失。")
        new_u = st.text_input("設定帳號", key="r_user")
        new_p = st.text_input("設定密碼", type="password", key="r_pw")
        confirm_p = st.text_input("確認密碼", type="password", key="r_confirm")
        
        if st.button("提交註冊", use_container_width=True):
            if new_u in user_db:
                st.warning("⚠️ 帳號已存在")
            elif new_p != confirm_p:
                st.error("❌ 密碼不一致")
            elif len(new_u) < 2 or len(new_p) < 4:
                st.error("❌ 長度不足")
            else:
                user_sheet.append_row([new_u, new_p])
                default_df = pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20)])
                save_portfolio_to_cloud(new_u, default_df)
                st.success("✅ 註冊成功！請切換至登入分頁。")
                
    st.markdown('</div>', unsafe_allow_html=True)

# 執行登入檢查
if not st.session_state.logged_in:
    login_ui()
    st.stop()

# --- 1. 網頁全域設定 ---
st.set_page_config(page_title="台股個股/ETF查詢 Ez開發", page_icon="🔍", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

# --- 3. 自定義 CSS ---
st.markdown("""
    <style>
    .main { background-color: #121218; color: #ffffff; }
    .stButton>button { width: 100%; border-radius: 12px; font-weight: bold; background-color: #ffffff; color: black; border: none; height: 3.5em; }
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

# ==========================================
# 頁面邏輯
# ==========================================
if st.session_state.page == "home":
    with st.sidebar:
        st.write(f"👤 當前使用者: **{st.session_state.current_user}**")
        if st.button("🚪 登出系統"):
            st.session_state.logged_in = False
            st.session_state.current_user = None
            st.rerun()
    st.title("🚀 台股個股/ETF查詢 Ez開發")
    st.write("請選擇功能進入：")
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

elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("🔍 台股自動估價系統 (個股)")
    main_col, side_col = st.columns([8, 4])
    with main_col:
        stock_code = st.text_input("請輸入台股代碼", value="")
        if stock_code:
            info = get_stock_info(stock_code)
            if info:
                current_price = info['price']
                st.markdown(f"## {info['name']}")
                st.markdown(f"<div class='date-text'>資料日期：{datetime.now(tw_tz).strftime('%Y-%m-%d')}</div>", unsafe_allow_html=True)
                cp1, cp2 = st.columns([2, 1])
                with cp1:
                    color = "#ff4b4b" if info['change'] > 0 else "#00ff00" if info['change'] < 0 else "#FFFFFF"
                    st.markdown(f"<div class='metric-val' style='color:{color}'>{current_price:.2f}</div>", unsafe_allow_html=True)
                    st.markdown(f"<span style='color:{color}; font-weight:bold; font-size:1.5rem;'>{info['change']:+.2f} ({info['pct']:+.2f}%)</span>", unsafe_allow_html=True)
                with cp2:
                    st.caption("今日行情細節")
                    st.write(f"最高: {info['high']:.2f} / 最低: {info['low']:.2f}")
                st.divider()
                col_eps, col_pe = st.columns(2)
                with col_eps: eps = st.number_input("輸入該股 EPS (4季累積)", min_value=0.01, value=10.0)
                with col_pe: pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0)
                fair_price = eps * pe_target
                st.markdown(f"<div class='calc-box'>合理價參考：<span class='highlight-val'>{fair_price:.2f}</span></div>", unsafe_allow_html=True)
    with side_col:
        st.info("計算公式：EPS × 自訂本益比 = 參考價")

elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF 專用 ")
    main_col, side_col = st.columns([8, 4])
    with main_col:
        symbol_input = st.text_input("ETF 代號", placeholder="例如: 00919").strip().upper()
        if st.button("開始計算", type="primary") and symbol_input:
            st.session_state.data = get_safe_data_etf(symbol_input)
        
        if st.session_state.data and st.session_state.data.get("success"):
            d = st.session_state.data
            st.markdown(f"## {d['name']} ({d['freq_label']}配)")
            st.write(f"現價: {d['price']:.2f}")
            
            st.divider()
            st.subheader("💰 持有張數與稅費試算")
            ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
            hold_lots = st.number_input("持有張數", min_value=0, value=10)
            
            total_shares = hold_lots * 1000
            total_raw = total_shares * float(d["raw_divs"][0])
            div_54c_part = total_raw * (ratio_54c/100)
            nhi_amt = div_54c_part * 0.0211 if div_54c_part >= 20000 else 0
            net_per_period = total_raw - nhi_amt
            
            st.markdown(f"""<div class="calc-box">
                每{d['freq_label']}總配息：{total_raw:,.0f} 元<br>
                <span style="color: #ffb7b7;">└ 二代健保扣費：-{nhi_amt:,.0f} 元</span><br>
                <b>每{d['freq_label']}實領金額：{net_per_period:,.0f} 元</b>
            </div>""", unsafe_allow_html=True)

            st.divider()
            st.subheader("🔮 存股未來複利試算")
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1: custom_monthly = st.number_input("每月投入 (元)", value=10000)
            with f_col2: custom_yield = st.number_input("年化殖利率 (%)", value=7.0)
            with f_col3: custom_years = st.slider("投入年數", 1, 40, 10)
            
            r = (custom_yield / 100) / 12
            n = custom_years * 12
            fv = custom_monthly * (((1 + r)**n - 1) / r) * (1 + r) if r > 0 else custom_monthly * n
            st.markdown(f"<div class='calc-box'>預期資產終值：<span class='highlight-val'>${fv:,.0f}</span></div>", unsafe_allow_html=True)

    with side_col:
        st.success("系統正常運行中")

elif st.session_state.page == "pk_tool":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("⚔️ ETF 對比工具")
    c1, c2 = st.columns(2)
    with c1: code1 = st.text_input("代碼 A", value="00919").upper()
    with c2: code2 = st.text_input("代碼 B", value="00878").upper()
    if st.button("開始對比"):
        r1, r2 = get_safe_data_etf(code1), get_safe_data_etf(code2)
        if r1["success"] and r2["success"]:
            df_pk = pd.DataFrame({
                "指標": ["價格", "漲跌幅", "配息頻率"],
                code1: [f"{r1['price']:.2f}", f"{r1['pct']:.2f}%", r1['freq_label']],
                code2: [f"{r2['price']:.2f}", f"{r2['pct']:.2f}%", r2['freq_label']]
            })
            st.table(df_pk)

elif st.session_state.page == "portfolio":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title(f"💼 {st.session_state.current_user} 的投資組合")
    
    with st.expander("📥 匯入投資清單 (CSV)"):
        uploaded_file = st.file_uploader("選擇 CSV 檔案", type="csv")
        if uploaded_file:
            import_df = pd.read_csv(uploaded_file)
            if "代碼" in import_df.columns and "張數" in import_df.columns:
                new_data = import_df[["代碼", "張數"]].copy()
                if len(new_data) < 20:
                    padding = pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20 - len(new_data))])
                    new_data = pd.concat([new_data, padding], ignore_index=True)
                st.session_state.portfolio = new_data
                st.success("CSV 已載入！")

    if st.session_state.portfolio is None:
        st.session_state.portfolio = pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20)])
    
    edited_df = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True)

    if st.button("💾 儲存所有變更至雲端", type="primary"):
        st.session_state.portfolio = edited_df
        if save_portfolio_to_cloud(st.session_state.current_user, edited_df):
            st.success("雲端同步成功！")

    valid_df = edited_df.dropna(subset=["代碼", "張數"])
    valid_df = valid_df[valid_df["代碼"].astype(str).str.strip() != ""]
    if not valid_df.empty and st.button("📊 計算當前市值分析"):
        results = []
        total_val = 0
        for _, row in valid_df.iterrows():
            d = get_safe_data_etf(str(row["代碼"]).strip().upper())
            if d["success"]:
                shares = float(row["張數"]) * 1000
                val = d["price"] * shares
                results.append({"名稱": d["name"], "持有價值": val})
                total_val += val
        if results:
            res_df = pd.DataFrame(results)
            st.metric("總資產價值", f"${total_val:,.0f}")
            st.plotly_chart(px.pie(res_df, values='持有價值', names='名稱', title="資產分佈"))

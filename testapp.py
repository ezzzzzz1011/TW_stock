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
    
    # 關鍵修正：將 "\\n" (字面上兩個字元) 轉為真正的 "\n" (換行符號)
    # 並處理 JSON 匯入時可能多出的雙引號
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
    # 開啟試算表
    sh = conn.open("streamlit_db")
    
    # 檢查或建立「帳號表」
    try:
        user_sheet = sh.worksheet("users")
    except:
        user_sheet = sh.add_worksheet(title="users", rows="100", cols="2")
        user_sheet.append_row(["username", "password"])
        user_sheet.append_row(["admin", "8888"])
    
    # 檢查或建立「投資組合儲存表」
    try:
        portfolio_sheet = sh.worksheet("portfolios")
    except:
        portfolio_sheet = sh.add_worksheet(title="portfolios", rows="1000", cols="2")
        portfolio_sheet.append_row(["username", "data_json"])
        
except Exception as e:
    st.error(f"❌ 雲端資料庫連線失敗：{e}")
    st.info("💡 提示：請檢查 Google Sheet 是否已分享編輯權限給服務帳號 Email。")
    st.stop()

def get_cloud_users():
    """即時從雲端讀取用戶清單"""
    records = user_sheet.get_all_records()
    # 這裡必須縮排 4 個空格
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

def login_ui():
    """渲染登入/註冊介面"""
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
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.title("🛡️ 投資助手系統")
    
    tab1, tab2 = st.tabs(["🔑 帳號登入", "📝 新用戶註冊"])
    # 取得最新帳密資料
user_db = get_cloud_users()

with tab1:
    u_id = st.text_input("帳號名稱", key="l_user", placeholder="請輸入帳號")
    u_pw = st.text_input("存取密碼", type="password", key="l_pw", placeholder="請輸入密碼")
    
    if st.button("確認登入", use_container_width=True, type="primary"):
        # 這裡判斷 user_db 裡的密碼 (字串) 與 輸入的密碼是否一致
        if user_db.get(u_id) == u_pw:
            st.session_state.logged_in = True
            st.session_state.current_user = u_id
            st.session_state.portfolio = load_portfolio_from_cloud(u_id)
            st.success(f"登入成功！")
            st.rerun()
        else:  # <-- 請檢查這一行開頭是否與上方的 if 對齊
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

# 設定台灣時區
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 初始化頁面狀態 ---
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'data' not in st.session_state: 
    st.session_state.data = None
# 確保 session_state 裡有當前使用者的資料
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = all_portfolios.get(
        st.session_state.current_user, 
        pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20)])
    )

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

# --- 5. 導覽邏輯 ---
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# ==========================================
# 首頁
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
        if st.button("個股查詢與估價", use_container_width=True, type="primary"):
            go_to("stock_query")
    with col_b:
        st.subheader("📊 ETF 分析")
        if st.button("ETF 試算與規劃", use_container_width=True, type="primary"):
            go_to("etf_query")
    with col_c:
        st.subheader("⚔️ ETF對比")
        if st.button("ETF對比工具", use_container_width=True, type="primary"):
            go_to("pk_tool")
    with col_d:
        st.subheader("💼 我的資產")
        if st.button("個人投資組合", use_container_width=True, type="primary"):
            go_to("portfolio")

# ==========================================
# 頁面 A：個股查詢系統
# ==========================================
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
                st.markdown(f"<div class='date-text'>資料日期：{datetime.now(tw_tz).strftime('%Y-%m-%d')}</div>", unsafe_allow_html=True)
                
                cp1, cp2 = st.columns([2, 1])
                with cp1:
                    color = "#ff4b4b" if info['change'] > 0 else "#00ff00" if info['change'] < 0 else "#FFFFFF"
                    st.markdown(f"<div class='metric-val' style='color:{color}'>{current_price:.2f}</div>", unsafe_allow_html=True)
                    st.markdown(f"<span style='color:{color}; font-weight:bold; font-size:1.5rem;'>{info['change']:+.2f} ({info['pct']:+.2f}%)</span>", unsafe_allow_html=True)
                with cp2:
                    st.caption("今日行情細節")
                    st.write(f"最高: {info['high']:.2f} / 最低: {info['low']:.2f}")
                    st.write(f"開盤: {info['open']:.2f} / 總量: {int(info['vol']/1000):,} 張")
                st.divider()

        col_eps, col_pe = st.columns(2)
        with col_eps: eps = st.number_input("輸入該股 EPS (4季累積)", min_value=0.01, step=0.1, value=10.0)
        with col_pe: pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)
        
        if current_price > 0:
            fair_price = eps * pe_target
            st.subheader("📊 換算結果")
            st.markdown(f"<div class='calc-box'>合理價參考：<span class='highlight-val'>{fair_price:.2f}</span></div>", unsafe_allow_html=True)
            if current_price <= fair_price: st.success(f"✅ 目前股價 {current_price:.2f} 低於目標參考價")
            else: st.warning(f"⚠️ 目前股價 {current_price:.2f} 已超過目標參考價")

    with side_col:
        st.write("### 📖 說明")
        st.caption("1. 輸入股票代碼。")
        st.caption("2. 輸入股票4季累積EPS。")
        st.caption("3. 輸入個股本益比。")
        st.divider()
        st.info("計算公式：EPS × 自訂本益比 = 參考價")

# ==========================================
# 頁面 B：ETF 分析系統
# ==========================================
elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF 專用 ")
    
    main_col, side_col = st.columns([8, 4])
    with main_col:
        st.markdown("### 🔍 查詢設定")
        input_c1, input_c2 = st.columns([3, 1])
        with input_c1:
            symbol_input = st.text_input("ETF 代號", placeholder="例如: 00919").strip().upper()
        with input_c2:
            st.write("")
            st.write("")
            if st.button("開始計算", type="primary"):
                if symbol_input:
                    with st.spinner('偵測頻率與抓取數據中...'):
                        st.session_state.data = get_safe_data_etf(symbol_input)

        if st.session_state.data and st.session_state.data.get("success"):
            d = st.session_state.data
            m_color = "#ff4b4b" if d['change'] >= 0 else "#00ff00"
            st.markdown(f"## {d['name']} <small style='font-size:1rem; color:#aaa;'>(偵測為{d['freq_label']}配息)</small>", unsafe_allow_html=True)
            st.markdown(f"<div class='date-text'>資料日期：{d.get('last_date')}</div>", unsafe_allow_html=True)
            
            info_c1, info_c2 = st.columns([2, 1])
            with info_c1:
                st.markdown(f"<div class='metric-val' style='color:{m_color}'>{d['price']:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"<span style='color:{m_color}; font-weight:bold; font-size:1.5rem;'>{d['change']:+.2f} ({d['pct']:+.2f}%)</span>", unsafe_allow_html=True)
            with info_c2:
                st.caption("今日行情細節")
                st.write(f"最高: {d['high']:.2f} / 最低: {d['low']:.2f}")
                st.write(f"開盤: {d['open']:.2f} / 總量: {d['vol']/1000:,.0f} 張")

            st.divider()
            st.subheader("📑 歷史配息參考")
            e_cols = st.columns(4)
            d1 = e_cols[0].number_input("最新", value=float(d["raw_divs"][0]), format="%.3f")
            d2 = e_cols[1].number_input("前一", value=float(d["raw_divs"][1]), format="%.3f")
            d3 = e_cols[2].number_input("前二", value=float(d["raw_divs"][2]), format="%.3f")
            d4 = e_cols[3].number_input("前三", value=float(d["raw_divs"][3]), format="%.3f")
            
            avg_annual = (sum([d1, d2, d3, d4]) / 4) * d["multiplier"]
            real_yield = (avg_annual / d['price']) * 100
            
            stat_c1, stat_c2 = st.columns(2)
            with stat_c1:
                st.caption(f"預估年配息 (系統以{d['freq_label']}配計算)")
                st.markdown(f"<div class='highlight-val'>{avg_annual:.2f}</div>", unsafe_allow_html=True)
            with stat_c2:
                st.caption("實質殖利率")
                st.markdown(f"<div class='highlight-val'>{real_yield:.2f}%</div>", unsafe_allow_html=True)

            st.divider()
            st.subheader("📊 估值位階參考")
            p_cheap, p_fair, p_high = avg_annual/0.10, avg_annual/0.07, avg_annual/0.05
            rec = "💎 便宜買入" if d['price'] <= p_cheap else "✅ 合理持有" if d['price'] <= p_fair else "❌ 昂貴不建議"
            st.markdown(f"<div class='calc-box'>系統建議：<b>{rec}</b></div>", unsafe_allow_html=True)

            table_html = f"""
            <table class="styled-table">
                <thead><tr><th>估值位階</th><th>建議價格參考</th></tr></thead>
                <tbody>
                    <tr><td>💎 便宜價 (10%)</td><td>{p_cheap:.2f} 以下</td></tr>
                    <tr><td>🔔 合理價 (7%)</td><td>{p_cheap:.2f} ~ {p_fair:.2f}</td></tr>
                    <tr><td>❌ 昂貴價 (5%)</td><td>高於 {p_high:.2f}</td></tr>
                </tbody>
            </table>
            """
            st.markdown(table_html, unsafe_allow_html=True)

            st.divider()
            st.subheader("💰 持有張數試算")
            ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
            calc_c1, calc_c2 = st.columns([1, 2])
            with calc_c1: hold_lots = st.number_input("持有張數", min_value=0, value=10, step=1)
            with calc_c2:
                total_shares = hold_lots * 1000
                total_raw = total_shares * d1
                
                # --- 稅費計算 (僅保留二代健保) ---
                div_54c_part = total_raw * (ratio_54c/100)
                nhi_amt = div_54c_part * 0.0211 if div_54c_part >= 20000 else 0
                net_per_period = total_raw - nhi_amt
                
                st.markdown(f"""<div class="calc-box">
                    預估總投入：{(total_shares * d['price'] * 1.001425):,.0f} 元<br>
                    每{d['freq_label']}總配息：{total_raw:,.0f} 元<br>
                    <span style="color: #ffb7b7;">└ 二代健保扣費：-{nhi_amt:,.0f} 元</span><br>
                    <b>每{d['freq_label']}實領金額：{net_per_period:,.0f} 元</b><br>
                    <hr style="border: 0.5px solid #444;">
                    一年累計實領：{(net_per_period * d['multiplier']):,.0f} 元
                </div>""", unsafe_allow_html=True)

            # --- 存股未來複利試算 ---
            st.divider()
            st.subheader("🔮 存股未來財富試算")
            with st.container():
                f_col0, f_col1, f_col2, f_col3 = st.columns(4)
                with f_col0: custom_initial = st.number_input("初始投入總金額 (元)", min_value=0, value=100000, step=10000)
                with f_col1: custom_monthly = st.number_input("每月預計投入 (元)", min_value=0, value=10000, step=1000)
                with f_col2: custom_yield = st.number_input("自訂年化殖利率 (%)", value=float(f"{real_yield:.2f}"), step=0.1)
                with f_col3: custom_years = st.slider("目標投入年數", 1, 40, 10)
                
                r = (custom_yield / 100) / 12
                n = custom_years * 12
                if r > 0:
                    fv = custom_initial * ((1 + r)**n) + custom_monthly * (((1 + r)**n - 1) / r) * (1 + r)
                else:
                    fv = custom_initial + (custom_monthly * n)
                
                total_invested = custom_initial + (custom_monthly * n)
                st.markdown(f"""
                <div class="calc-box" style="border: 2px solid #ffffff; padding: 25px;">
                    <div style="font-size: 3.2rem; font-weight: bold; color: #ffffff;">$ {fv:,.0f} <small style="font-size: 1.2rem;">元</small></div>
                    <hr style="border: 0.5px solid #444;">
                    <p style="font-size: 1rem; color: #fff; line-height: 1.8;">
                        累積投入本金：<b>{total_invested:,.0f}</b> 元 | 
                        資產成長倍數：<b>{fv/total_invested if total_invested > 0 else 0:.2f}</b> 倍<br>
                        <span style="color: #00ff00; font-weight: bold;">每月預計領取被動收入：{(fv * (custom_yield / 100)) / 12:,.0f} 元</span>
                    </p>
                </div>
                """, unsafe_allow_html=True)

    with side_col:
        st.write("### 📖 說明")
        st.caption("1. 輸入代號後點擊開始計算。")
        st.caption("2. 系統自動偵測配息頻率。")
        st.divider()
        st.success("系統正常運行中")

# ==========================================
# 頁面 C：PK 對比工具
# ==========================================
elif st.session_state.page == "pk_tool":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("⚔️ ETF 對比工具")
    
    col_in1, col_in2 = st.columns(2)
    with col_in1: code1 = st.text_input("輸入代碼 A", value="00919").strip().upper()
    with col_in2: code2 = st.text_input("輸入代碼 B", value="00878").strip().upper()
    
    if st.button("開始對比"):
        with st.spinner("抓取對比數據中..."):
            r1 = get_safe_data_etf(code1)
            r2 = get_safe_data_etf(code2)
            
            if r1["success"] and r2["success"]:
                st.divider()
                c1, c2 = st.columns(2)
                analysis = []
                for r in [r1, r2]:
                    avg_annual = (sum(r["raw_divs"]) / 4) * r["multiplier"]
                    real_yield = (avg_annual / r['price']) * 100 if r['price'] > 0 else 0
                    analysis.append({"annual_div": avg_annual, "yield": real_yield})

                for i, r in enumerate([r1, r2]):
                    with [c1, c2][i]:
                        color = "#ff4b4b" if r['change'] > 0 else "#00ff00"
                        st.markdown(f"""<div class="pk-card">
                            <h3>{r['name']}</h3>
                            <h2 style="color:{color}">{r['price']:.2f}</h2>
                            <p>{r['change']:+.2f} ({r['pct']:+.2f}%)</p>
                        </div>""", unsafe_allow_html=True)
                
                df = pd.DataFrame({
                    "指標項目": ["目前價格", "當前漲幅", "配息頻率", "預估年配息", "實質殖利率"],
                    f"{code1}": [f"{r1['price']:.2f}", f"{r1['pct']:.2f}%", r1['freq_label'], f"{analysis[0]['annual_div']:.2f}", f"{analysis[0]['yield']:.2f}%"],
                    f"{code2}": [f"{r2['price']:.2f}", f"{r2['pct']:.2f}%", r2['freq_label'], f"{analysis[1]['annual_div']:.2f}", f"{analysis[1]['yield']:.2f}%"]
                })
                st.table(df)

# ==========================================
# 頁面 D：個人投資組合 (含 CSV 匯入)
# ==========================================
elif st.session_state.page == "portfolio":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title(f"💼 {st.session_state.current_user} 的投資組合")
    
    # --- CSV 匯入區 ---
    with st.expander("📥 匯入投資清單 (CSV)"):
        uploaded_file = st.file_uploader("選擇 CSV 檔案", type="csv")
        if uploaded_file is not None:
            try:
                import_df = pd.read_csv(uploaded_file)
                if "代碼" in import_df.columns and "張數" in import_df.columns:
                    # 抓取檔案中的資料
                    new_data = import_df[["代碼", "張數"]].copy()
                    # 補滿到 20 行
                    if len(new_data) < 20:
                        padding = pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20 - len(new_data))])
                        new_data = pd.concat([new_data, padding], ignore_index=True)
                    
                    st.session_state.portfolio = new_data
                    st.success("CSV 資料已載入編輯器，請檢查後點擊下方儲存按鈕。")
                else:
                    st.error("CSV 格式錯誤！必須包含『代碼』與『張數』兩個欄位。")
            except Exception as e:
                st.error(f"讀取失敗：{e}")

    st.markdown("### 📝 編輯並儲存清單")
    
    # 確保目前的資料至少有 20 行
    if len(st.session_state.portfolio) < 20:
        padding_df = pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20 - len(st.session_state.portfolio))])
        st.session_state.portfolio = pd.concat([st.session_state.portfolio, padding_df], ignore_index=True)

    # 顯示編輯器
edited_df = st.data_editor(
    st.session_state.portfolio, 
    num_rows="dynamic", 
    use_container_width=True,
    key="portfolio_editor"
)

# --- 關鍵修改點：新增雲端儲存按鈕 ---
if st.button("💾 儲存所有變更至雲端"):
    # 先更新目前的 session 狀態
    st.session_state.portfolio = edited_df 
    # 將資料寫回 Google Sheets
    save_portfolio_to_cloud(st.session_state.current_user, edited_df) 
    st.success("雲端同步成功！下次登入資料會自動帶入。")
# 2. 加入存檔按鈕與邏輯
col1, col2 = st.columns([1, 5])
with col1:
    if st.button("💾 儲存至雲端", type="primary", use_container_width=True):
        # 更新 session_state
        st.session_state.portfolio = edited_df
        # 呼叫我們先前定義好的存檔函數
        try:
            save_portfolio_to_cloud(st.session_state.current_user, edited_df)
            st.success("儲存成功！資料已同步至 Google Sheets。")
        except Exception as e:
            st.error(f"儲存失敗：{e}")

with col2:
    st.info("💡 編輯完代碼或張數後，請務必點擊左側儲存按鈕，帳號重啟後資料才不會消失。")

    if st.button("💾 更新並永久儲存至帳號", type="primary"):
        st.session_state.portfolio = edited_df
        all_portfolios[st.session_state.current_user] = edited_df
        
        results = []
        total_market_val = 0
        total_annual_div = 0
        
        valid_df = edited_df.dropna(subset=["代碼", "張數"])
        valid_df = valid_df[valid_df["代碼"].astype(str).str.strip() != ""]
        
        if not valid_df.empty:
            with st.spinner("同步市場最新價格中..."):
                for index, row in valid_df.iterrows():
                    try:
                        code = str(row["代碼"]).strip().upper()
                        shares = float(row["張數"]) * 1000
                        if code:
                            data = get_safe_data_etf(code)
                            if data["success"]:
                                m_val = data["price"] * shares
                                ann_div = (sum(data["raw_divs"]) / 4) * data["multiplier"] * shares
                                results.append({
                                    "名稱": data["name"], "代碼": code, "現價": data["price"],
                                    "持有價值": m_val, "預估年領股息": ann_div
                                })
                                total_market_val += m_val
                                total_annual_div += ann_div
                    except: continue

            if results:
                res_df = pd.DataFrame(results)
                st.divider()
                m1, m2, m3 = st.columns(3)
                m1.metric("總資產規模", f"${total_market_val:,.0f}")
                m2.metric("預估年領股息", f"${total_annual_div:,.0f}")
                avg_yield = (total_annual_div / total_market_val * 100) if total_market_val > 0 else 0
                m3.metric("組合平均殖利率", f"{avg_yield:.2f}%")
                
                col_chart, col_table = st.columns([1, 1])
                with col_chart:
                    fig = px.pie(res_df, values='持有價值', names='名稱', 
                                 title="資產配置分佈圖", color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
                    st.plotly_chart(fig, use_container_width=True)
                with col_table:
                    st.write("#### 詳細數據")
                    st.dataframe(res_df, use_container_width=True)
            else:
                st.error("未能抓取到數據，請檢查代碼。")
        else:
            st.warning("清單為空。")

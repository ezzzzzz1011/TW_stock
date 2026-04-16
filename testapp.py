import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz
import plotly.express as px
import io
import gspread
import time
import requests
import re
from google.oauth2.service_account import Credentials
from fugle_marketdata import RestClient

# --- 1. 網頁全域設定 (必須放在最上方) ---
st.set_page_config(page_title="台股個股/ETF查詢 Ez開發", page_icon="🔍", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

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

try:
    conn = init_connection()
    sh = conn.open("streamlit_db")
    user_sheet = sh.worksheet("users") if "users" in [w.title for w in sh.worksheets()] else sh.add_worksheet("users", 100, 2)
    portfolio_sheet = sh.worksheet("portfolios") if "portfolios" in [w.title for w in sh.worksheets()] else sh.add_worksheet("portfolios", 1000, 2)
    watchlist_sheet = sh.worksheet("watchlist") if "watchlist" in [w.title for w in sh.worksheets()] else sh.add_worksheet("watchlist", 100, 2)
except Exception as e:
    st.error(f"❌ 雲端資料庫連線失敗：{e}")
    st.stop()

def get_cloud_users():
    records = user_sheet.get_all_records()
    return {str(row['username']).strip(): str(row['password']).strip() for row in records}

def load_portfolio_from_cloud(username):
    try:
        cell = portfolio_sheet.find(username)
        if cell:
            return pd.read_json(io.StringIO(portfolio_sheet.cell(cell.row, 2).value))
    except: pass
    return pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20)])

def save_portfolio_to_cloud(username, df):
    json_data = df.dropna(subset=['代碼']).to_json(orient='records', date_format='iso')
    try:
        cell = portfolio_sheet.find(username)
        if cell: portfolio_sheet.update_cell(cell.row, 2, json_data)
        else: portfolio_sheet.append_row([username, json_data])
        return True
    except: return False

def load_watchlist_from_cloud():
    try:
        cell = watchlist_sheet.find(st.session_state.current_user)
        if cell:
            raw = str(watchlist_sheet.cell(cell.row, 2).value).replace("'", "").strip()
            return [c.strip() for c in raw.split(',') if c.strip()]
    except: pass
    return []

def save_watchlist_to_cloud(codes_list):
    try:
        cell = watchlist_sheet.find(st.session_state.current_user)
        codes_str = "'" + ",".join([str(c).strip() for c in codes_list])
        if cell: watchlist_sheet.update(range_name=f"B{cell.row}", values=[[codes_str]])
        else: watchlist_sheet.append_row([st.session_state.current_user, codes_str])
    except: pass

# --- 初始化應用程式狀態 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'portfolio' not in st.session_state: st.session_state.portfolio = None
if 'page' not in st.session_state: st.session_state.page = "welcome"
if 'data' not in st.session_state: st.session_state.data = None

# --- 登入介面邏輯 ---
def login_ui():
    st.markdown('<div style="text-align:center;"><h2>🚀 台股個股/ETF查詢系統</h2><p>Ez開發 - 投資助手</p></div>', unsafe_allow_html=True)
    user_db = get_cloud_users()
    tab1, tab2 = st.tabs(["🔑 帳號登入", "📝 新用戶註冊"])
    with tab1:
        u_id = st.text_input("帳號名稱", key="l_user")
        u_pw = st.text_input("存取密碼", type="password", key="l_pw")
        if st.button("確認登入", use_container_width=True, type="primary"):
            if user_db.get(u_id) == u_pw:
                st.session_state.logged_in, st.session_state.current_user = True, u_id
                st.session_state.portfolio = load_portfolio_from_cloud(u_id)
                st.rerun()
            else: st.error("❌ 帳號或密碼不正確")
    with tab2:
        new_u = st.text_input("設定帳號")
        new_p = st.text_input("設定密碼", type="password")
        if st.button("提交註冊", use_container_width=True):
            if new_u in user_db: st.warning("帳號已存在")
            else:
                user_sheet.append_row([new_u, new_p])
                st.success("✅ 註冊成功！請登入。")

if not st.session_state.logged_in: login_ui(); st.stop()

# --- 自定義 CSS (含刪除按鈕修正) ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; font-weight: bold; border: 1px solid rgba(128, 128, 128, 0.3); height: 3.5em; }
    .metric-val { font-family: 'Consolas'; font-size: 3.5rem; font-weight: bold; line-height: 1.1; }
    .feature-card { background-color: var(--secondary-background-color); padding: 30px; border-radius: 20px; text-align: center; margin-bottom: 20px; }
    .calc-box { background-color: var(--secondary-background-color); padding: 20px; border-radius: 15px; border: 1px solid rgba(128, 128, 128, 0.3); }
    
    /* 關注清單第四欄刪除按鈕縮小並靠上 */
    div[data-testid="stColumn"]:nth-child(4) button[kind="secondary"],
    div[data-testid="column"]:nth-child(4) button[kind="secondary"] {
        height: auto !important; min-height: 32px !important; width: max-content !important;
        padding: 0px 16px !important; margin-top: -12px !important; margin-left: auto !important; margin-right: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 數據引擎 ---
FUGLE_TOKEN = "YzJjNmM3ODAtZjE1Ny00NzhiLWFjOTUtMDUwZjc2ZWJhYTI1IGRjYTE0ODk3LTRjYTUtNDg5Yi05MjAwLWZmYzNmNzFmNmYwNg=="
client = RestClient(api_key=FUGLE_TOKEN)

def get_stock_info(symbol):
    clean_s = str(symbol).strip().upper().replace('.TW', '').replace('.TWO', '')
    try:
        data = client.stock.intraday.quote(symbol=clean_s)
        if data:
            price = float(data.get('lastPrice') or data.get('closePrice') or data.get('previousClose') or 0.0)
            vol = float(data.get('total', {}).get('tradeVolume', 0))
            if 0 < vol < 500000: vol *= 1000
            return {"name": data.get('name', clean_s), "price": price, "change": float(data.get('change', 0.0)),
                    "pct": float(data.get('changePercent', 0.0)), "high": float(data.get('highPrice') or price),
                    "low": float(data.get('lowPrice') or price), "open": float(data.get('openPrice') or price),
                    "vol": int(vol), "full_ticker": clean_s}
    except: pass
    return None

def fetch_dividend_history_super(symbol):
    clean_s = str(symbol).strip().upper().replace('.TW', '').replace('.TWO', '')
    div_list = []
    fm_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2Vyc2lkIjp6ZW5vaWLCJlbWFpbCI6ImVhc29uOTMxMDExQGdtYWlsLmNvbSJ9.ApZobjnh5PCRDtXb8rj6a3Y10h1GUGS0EYKHXkTEvKw"
    try:
        res = requests.get("https://api.finminddata.com/v4/data", params={"dataset": "TaiwanStockDividend", "data_id": clean_s, "token": fm_token}, timeout=5)
        data = res.json()
        if data.get("msg") == "success" and data.get("data"):
            for item in data["data"]:
                if float(item.get('cash_dividend', 0)) > 0:
                    div_list.append({'date': item['ex_dividend_date'], 'amount': float(item['cash_dividend'])})
            if div_list: return sorted(div_list, key=lambda x: x['date'], reverse=True)
    except: pass
    h_urls = [f"https://histock.tw/stock/etfdividend.aspx?no={clean_s}", f"https://histock.tw/stock/financial.aspx?no={clean_s}&t=2"]
    for url in h_urls:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://histock.tw/"}, timeout=5)
            if r.status_code == 200:
                matches = re.findall(r'(\d{4}/\d{1,2}/\d{1,2}).*?(\d+\.\d+)', r.text, re.DOTALL)
                for m_date, m_val in matches: div_list.append({'date': m_date.replace('/', '-'), 'amount': float(m_val)})
                if div_list: break
        except: pass
    return sorted(div_list, key=lambda x: x['date'], reverse=True) if div_list else []

@st.cache_data(ttl=3600)
def get_safe_data_etf(symbol):
    info = get_stock_info(symbol)
    if not info: return {"success": False, "msg": "找不到報價"}
    divs = fetch_dividend_history_super(symbol)
    raw_divs = [float(d['amount']) for d in divs[:4]] + [0.0]*(4-len(divs))
    multiplier, label = 1, "年"
    if len(divs) >= 2:
        days = (datetime.strptime(divs[0]['date'], "%Y-%m-%d") - datetime.strptime(divs[1]['date'], "%Y-%m-%d")).days
        if days <= 45: multiplier, label = 12, "月"
        elif days <= 110: multiplier, label = 4, "季"
        elif days <= 200: multiplier, label = 2, "半年"
    return {"success": True, **info, "raw_divs": raw_divs, "multiplier": multiplier, "freq_label": label}

def go_to(page):
    st.session_state.page = page
    st.rerun()

with st.sidebar:
    st.write(f"👤 使用者: **{st.session_state.current_user}**")
    if st.button("⭐ 關注清單", use_container_width=True): go_to("watchlist")
    if st.button("🚀 工具首頁", use_container_width=True): go_to("home")
    st.divider()
    if st.button("🚪 登出系統", use_container_width=True): st.session_state.logged_in = False; st.rerun()

if st.session_state.page == "welcome":
    st.markdown("<br><br><br><h3 style='text-align: center; color: #555;'>👈 請從左側選單選擇功能</h3>", unsafe_allow_html=True)

elif st.session_state.page == "home":
    st.title("請選擇功能進入：")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("📈 個股分析", type="primary"): go_to("stock_query")
    if c2.button("📊 ETF 分析", type="primary"): go_to("etf_query")
    if c3.button("⚔️ ETF 對比", type="primary"): go_to("pk_tool")
    if c4.button("💼 我的資產", type="primary"): go_to("portfolio")

elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回"): go_to("home")
    st.title("📈 ETF 專用分析")
    code = st.text_input("ETF 代號", placeholder="例如: 00919").upper()
    if st.button("開始計算", type="primary") and code:
        with st.spinner("抓取中..."): st.session_state.data = get_safe_data_etf(code)
    
    if st.session_state.data:
        d = st.session_state.data
        if d["success"]:
            st.header(f"{d['name']} ({d['full_ticker']})")
            st.subheader(f"現價: {d['price']} ({d['change']:+.2f} / {d['pct']:+.2f}%)")
            st.divider(); st.subheader("📑 歷史配息參考")
            f_map = {"月配": 12, "季配": 4, "半年配": 2, "年配": 1}
            sys_f = f"{d['freq_label']}配" if f"{d['freq_label']}配" in f_map else "年配"
            user_f = st.selectbox("🔄 修正配息頻率：", list(f_map.keys()), index=list(f_map.keys()).index(sys_f))
            d['multiplier'], d['freq_label'] = f_map[user_f], user_f.replace("配", "")
            cols = st.columns(4)
            v = [cols[i].number_input(f"配息 {i+1}", value=d['raw_divs'][i], format="%.3f") for i in range(4)]
            ann = round((sum(v)/4) * d['multiplier'], 4)
            st.metric(f"預估年配息 ({d['freq_label']}配)", ann)
            st.metric("實質殖利率", f"{round(ann/d['price']*100, 2)}%")
        else: st.error(d["msg"])

elif st.session_state.page == "portfolio":
    if st.button("⬅️ 返回"): go_to("home")
    st.title("💼 我的資產管理")
    edited = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True)
    if st.button("💾 儲存資產"): save_portfolio_to_cloud(st.session_state.current_user, edited); st.success("已同步")
    if st.button("🚀 計算市值", type="primary"):
        res = []
        valid = edited.dropna(subset=["代碼", "張數"]).copy()
        valid = valid[valid["代碼"].astype(str).str.strip() != ""]
        for _, r in valid.iterrows():
            data = get_safe_data_etf(r["代碼"])
            if data["success"]:
                res.append({"名稱": data["name"], "市值": data["price"]*r["張數"]*1000})
        if res: st.dataframe(pd.DataFrame(res), use_container_width=True)

elif st.session_state.page == "watchlist":
    st.title("⭐ 我的關注清單")
    if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist_from_cloud()
    with st.form("add_form", clear_on_submit=True):
        new_c = st.text_input("新增代碼").upper()
        if st.form_submit_button("加入") and new_c:
            if new_c not in st.session_state.watchlist:
                st.session_state.watchlist.append(new_c); save_watchlist_to_cloud(st.session_state.watchlist); st.rerun()
    
    @st.fragment(run_every=120)
    def show_watchlist():
        st.caption(f"⏱️ 行情自動刷新中... {datetime.now(tw_tz).strftime('%H:%M:%S')}")
        for c in st.session_state.watchlist:
            info = get_stock_info(c)
            if info:
                col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                color = "#ff4b4b" if info['change'] > 0 else "#00ff00"
                col1.write(f"**{info['name']}** ({c})")
                col2.markdown(f"<span style='color:{color}; font-size:1.3rem; font-weight:bold;'>{info['price']:.2f}</span>", unsafe_allow_html=True)
                col3.write(f"{info['pct']:+.2f}%")
                if col4.button("刪除", key=f"del_{c}"):
                    st.session_state.watchlist.remove(c); save_watchlist_to_cloud(st.session_state.watchlist); st.rerun()
                st.divider()
    show_watchlist()

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
    records = user_sheet.get_all_records()
    return {str(row['username']).strip(): str(row['password']).strip() for row in records}

def load_portfolio_from_cloud(username):
    try:
        cell = portfolio_sheet.find(username)
        if cell:
            json_data = portfolio_sheet.cell(cell.row, 2).value
            return pd.read_json(io.StringIO(json_data))
    except Exception:
        pass
    return pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20)])

def save_portfolio_to_cloud(username, df):
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
    st.session_state.page = "welcome"  
if 'data' not in st.session_state: 
    st.session_state.data = None

# --- 登入介面邏輯 ---
def login_ui():
    st.markdown("""
        <div style="max-width: 400px; margin: 40px auto 20px auto; padding: 25px; background-color: #f8f9fa; border-radius: 15px; border: 1px solid #dee2e6; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center;">
            <h2 style="margin: 0; color: #1f1f1f; font-size: 24px;">🚀 台股個股/ETF查詢</h2>
            <p style="color: #666; margin-top: 8px; margin-bottom: 0; font-size: 14px;">Ez開發 - 投資助手系統</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
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
                    st.session_state.page = "welcome"  
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
                    st.error("❌ 長度不足 (帳號需2字元, 密碼需4字元)")
                else:
                    user_sheet.append_row([new_u, new_p])
                    default_df = pd.DataFrame([{"代碼": "", "張數": None} for _ in range(20)])
                    save_portfolio_to_cloud(new_u, default_df)
                    st.success("✅ 註冊成功！請切換至登入分頁。")
                
    st.markdown('</div>', unsafe_allow_html=True)

def load_watchlist_from_cloud():
    try:
        ws = sh.worksheet("watchlist")
        all_records = ws.get_all_records()
        for row in all_records:
            if row.get('username') == st.session_state.current_user:
                raw_codes = str(row.get('codes', "")).replace("'", "").strip()
                if raw_codes:
                    valid_codes = [c.strip() for c in raw_codes.split(',') if 0 < len(c.strip()) < 10]
                    return valid_codes
        return []
    except Exception as e:
        st.error(f"讀取失敗: {e}")
    return []

def save_watchlist_to_cloud(codes_list):
    try:
        ws = sh.worksheet("watchlist")
        cell = ws.find(st.session_state.current_user)
        codes_str = "'" + ",".join([str(c).strip() for c in codes_list])
        
        if cell:
            ws.update(range_name=f"B{cell.row}", values=[[codes_str]])
        else:
            ws.append_row([st.session_state.current_user, codes_str])
    except Exception as e:
        st.error(f"雲端儲存失敗: {e}")

if not st.session_state.logged_in:
    login_ui()
    st.stop()

# --- 自定義 CSS ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; font-weight: bold; border: 1px solid rgba(128, 128, 128, 0.3); height: 3.5em; }
    .metric-val { font-family: 'Consolas'; font-size: 3.5rem; font-weight: bold; line-height: 1.1; color: var(--text-color) !important; }
    .highlight-val { font-size: 2.5rem; font-family: 'Consolas'; font-weight: bold; color: var(--text-color) !important; }
    .stTextInput>div>div>input, .stNumberInput>div>div>input { border-radius: 8px !important; }
    .feature-card { background-color: var(--secondary-background-color); padding: 30px; border-radius: 20px; border: 1px solid rgba(128, 128, 128, 0.2); box-shadow: 0 4px 15px rgba(0,0,0,0.05); text-align: center; transition: all 0.3s ease; margin-bottom: 20px; }
    .feature-card:hover { transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0,0,0,0.15); border-color: var(--primary-color); }
    .feature-title { font-size: 1.5rem; font-weight: bold; color: var(--text-color); margin-bottom: 10px; }
    .feature-desc { color: var(--text-color); opacity: 0.7; font-size: 1rem; }
    .calc-box, .plan-box, .pk-card { background-color: var(--secondary-background-color); padding: 20px; border-radius: 15px; border: 1px solid rgba(128, 128, 128, 0.3); margin-top: 10px; color: var(--text-color); }
    .styled-table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 1.1rem; }
    .styled-table th { background-color: var(--secondary-background-color); color: var(--text-color); text-align: left; padding: 12px; border-bottom: 2px solid var(--text-color); }
    .styled-table td { padding: 12px; border-bottom: 1px solid rgba(128, 128, 128, 0.3); color: var(--text-color) !important; }
    
    /* 專門將關注清單第四欄的刪除按鈕縮小並往上對齊 (排除首頁的主要按鈕) */
    div[data-testid="stColumn"]:nth-child(4) button[kind="secondary"],
    div[data-testid="column"]:nth-child(4) button[kind="secondary"] {
        height: auto !important;
        min-height: 32px !important;
        width: max-content !important;
        padding: 0px 16px !important;
        margin-top: -12px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Fugle API 初始化 ---
FUGLE_TOKEN = "YzJjNmM3ODAtZjE1Ny00NzhiLWFjOTUtMDUwZjc2ZWJhYTI1IGRjYTE0ODk3LTRjYTUtNDg5Yi05MjAwLWZmYzNmNzFmNmYwNg=="
client = RestClient(api_key=FUGLE_TOKEN)

# ==========================================
# 🚀 終極數據引擎 1：報價與總量 (優先使用 Fugle 穩定報價)
# ==========================================
def get_stock_info(symbol):
    clean_symbol = str(symbol).strip().upper().replace('.TW', '').replace('.TWO', '')
    
    # 首先嘗試 Fugle (最穩定，不被封 IP)
    try:
        data = client.stock.intraday.quote(symbol=clean_symbol)
        if data:
            price = float(data.get('lastPrice') or data.get('closePrice') or data.get('previousClose') or 0.0)
            vol = float(data.get('total', {}).get('tradeVolume', 0))
            if 0 < vol < 500000: vol = vol * 1000 
                
            return {
                "name": data.get('name', clean_symbol),
                "price": price,
                "change": float(data.get('change', 0.0)),
                "pct": float(data.get('changePercent', 0.0)),
                "high": float(data.get('highPrice') or price),
                "low": float(data.get('lowPrice') or price),
                "open": float(data.get('openPrice') or price),
                "vol": int(vol),
                "full_ticker": clean_symbol,
                "hist": None, "dividends": None
            }
    except: pass

    # 備援：Yahoo Finance (帶瀏覽器偽裝)
    try:
        url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.quotes;symbols={clean_symbol}.TW,{clean_symbol}.TWO"
        fake_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0 Safari/537.36", "Accept-Language": "zh-TW,zh;q=0.9"}
        res = requests.get(url, headers=fake_headers, timeout=5)
        if res.status_code == 200:
            q = res.json()[0]
            price = float(q.get('price', q.get('previousClose', 0.0)))
            if price > 0:
                return {
                    "name": q.get('symbolName', clean_symbol), "price": price, "change": float(q.get('change', 0.0)),
                    "pct": float(q.get('changePercent', 0.0)), "high": float(q.get('regularMarketDayHigh', price)),
                    "low": float(q.get('regularMarketDayLow', price)), "open": float(q.get('regularMarketDayOpen', price)),
                    "vol": int(q.get('volume', 0)) * 1000, "full_ticker": clean_symbol, "hist": None, "dividends": None
                }
    except: pass
    return None

# ==========================================
# 🚀 終極數據引擎 2：配息與日期 (FinMind + HiStock 雙重備援)
# ==========================================
def fetch_dividend_history_super(symbol):
    clean_symbol = str(symbol).strip().upper().replace('.TW', '').replace('.TWO', '')
    div_list = []
    
    # 你的 FinMind API 金鑰
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2Vyc2lkIjp6ZW5vaWLCJlbWFpbCI6ImVhc29uOTMxMDExQGdtYWlsLmNvbSJ9.ApZobjnh5PCRDtXb8rj6a3Y10h1GUGS0EYKHXkTEvKw"
    
    # 第一重：FinMind API (對一般個股最準)
    try:
        url = "https://api.finminddata.com/v4/data"
        params = {"dataset": "TaiwanStockDividend", "data_id": clean_symbol, "token": token}
        res = requests.get(url, params=params, timeout=5)
        data = res.json()
        if data.get("msg") == "success" and data.get("data"):
            for item in data["data"]:
                amount = float(item.get('cash_dividend', 0))
                if amount > 0:
                    div_list.append({'date': item['ex_dividend_date'], 'amount': amount})
            if div_list: return sorted(div_list, key=lambda x: x['date'], reverse=True)
    except: pass

    # 第二重：HiStock 備援 (含債券 ETF 路徑)
    h_headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://histock.tw/"}
    h_urls = [f"https://histock.tw/stock/etfdividend.aspx?no={clean_symbol}", f"https://histock.tw/stock/financial.aspx?no={clean_symbol}&t=2"]
    for url in h_urls:
        try:
            res = requests.get(url, headers=h_headers, timeout=5)
            if res.status_code == 200:
                matches = re.findall(r'(\d{4}/\d{1,2}/\d{1,2}).*?(\d+\.\d+)', res.text, re.DOTALL)
                for m_date, m_val in matches:
                    div_list.append({'date': m_date.replace('/', '-'), 'amount': float(m_val)})
                if div_list: break
        except: pass
        
    return sorted(div_list, key=lambda x: x['date'], reverse=True) if div_list else []

# --- ETF 資料處理主函數 (精準天數頻率算法) ---
@st.cache_data(ttl=3600) 
def get_safe_data_etf(symbol):
    info = get_stock_info(symbol)
    if not info or info["price"] <= 0:
        return {"success": False, "msg": f"找不到代號 {symbol} 或目前無報價"}
    
    raw_divs = [0.0] * 4
    multiplier = 1
    freq_label = "年"
    
    try:
        data_list = fetch_dividend_history_super(symbol)
        if data_list:
            for i in range(min(4, len(data_list))):
                raw_divs[i] = data_list[i]['amount']
            if len(data_list) >= 2:
                check_len = min(5, len(data_list))
                dates = [datetime.strptime(d['date'], "%Y-%m-%d") for d in data_list[:check_len]]
                days_diffs = [(dates[i] - dates[i+1]).days for i in range(len(dates)-1)]
                avg_days = sum(days_diffs) / len(days_diffs)
                if avg_days <= 45: multiplier, freq_label = 12, "月"
                elif avg_days <= 110: multiplier, freq_label = 4, "季"
                elif avg_days <= 200: multiplier, freq_label = 2, "半年"
                else: multiplier, freq_label = 1, "年"
    except: pass

    return {
        "success": True, "name": info["name"], "price": info["price"], "change": info["change"], "pct": info["pct"], 
        "high": info["high"], "low": info["low"], "open": info["open"], "vol": info["vol"],
        "raw_divs": raw_divs, "multiplier": multiplier, "freq_label": freq_label,
        "last_date": datetime.now(tw_tz).strftime('%Y-%m-%d'), "full_ticker": info["full_ticker"]
    }

def get_dividend_calendar(symbol):
    data_list = fetch_dividend_history_super(symbol)
    if data_list:
        latest = data_list[0]
        try:
            ex_dt = datetime.strptime(latest['date'], "%Y-%m-%d")
            pay_date = (ex_dt + pd.DateOffset(days=28)).strftime('%Y-%m-%d')
            return {"symbol": symbol, "ex_date": latest['date'], "pay_date": pay_date, "amount": latest['amount'], "success": True}
        except: pass
    return {"success": False}

def generate_user_calendar():
    if st.session_state.portfolio is None: return None
    valid_assets = st.session_state.portfolio.dropna(subset=["代碼", "張數"])
    valid_assets = valid_assets[valid_assets["代碼"].astype(str).str.strip() != ""]
    if valid_assets.empty: return None

    calendar_list = []
    today_date = datetime.now(tw_tz).date()
    progress_bar = st.progress(0)
    for i, (index, row) in enumerate(valid_assets.iterrows()):
        div_info = get_dividend_calendar(str(row["代碼"]).strip())
        if div_info["success"]:
            pay_date_obj = datetime.strptime(div_info["pay_date"], '%Y-%m-%d').date()
            if pay_date_obj >= today_date:
                calendar_list.append({
                    "股票名稱": str(row["代碼"]), "預計除息日": div_info["ex_date"], "預計發放日 (預估)": div_info["pay_date"],
                    "每股配息": f"${div_info['amount']:.2f}", "預估入帳金額": int(div_info['amount'] * float(row["張數"]) * 1000)
                })
        progress_bar.progress((i + 1) / len(valid_assets))
    progress_bar.empty()
    return pd.DataFrame(calendar_list) if calendar_list else None

def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# --- 側邊欄 ---
with st.sidebar:
    st.write(f"👤 當前使用者: **{st.session_state.current_user}**")
    if st.button("⭐ 我的關注清單", use_container_width=True): go_to("watchlist")
    if st.button("🚀 台股查詢", use_container_width=True): go_to("home")
    st.divider()
    if st.button("🚪 登出系統", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# --- 頁面邏輯 ---
if st.session_state.page == "welcome":
    st.markdown("<br><br><br><h3 style='text-align: center; color: #555;'>👈 請從左側選單選擇功能</h3>", unsafe_allow_html=True)

elif st.session_state.page == "home":
    st.markdown("<h3 style='color: #333;'>請選擇功能進入：</h3>", unsafe_allow_html=True)
    st.divider()
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.markdown('<div class="feature-card"><div class="feature-title">📈 個股分析</div><div class="feature-desc">個股查詢與估價</div></div>', unsafe_allow_html=True)
        if st.button("進入個股分析", use_container_width=True, type="primary"): go_to("stock_query")
    with col_b:
        st.markdown('<div class="feature-card"><div class="feature-title">📊 ETF 分析</div><div class="feature-desc">ETF 試算與規劃</div></div>', unsafe_allow_html=True)
        if st.button("進入 ETF 分析", use_container_width=True, type="primary"): go_to("etf_query")
    with col_c:
        st.markdown('<div class="feature-card"><div class="feature-title">⚔️ ETF 對比</div><div class="feature-desc">ETF 對比工具</div></div>', unsafe_allow_html=True)
        if st.button("進入對比工具", use_container_width=True, type="primary"): go_to("pk_tool")
    with col_d:
        st.markdown('<div class="feature-card"><div class="feature-title">💼 我的資產</div><div class="feature-desc">個人投資組合</div></div>', unsafe_allow_html=True)
        if st.button("進入我的資產", use_container_width=True, type="primary"): go_to("portfolio")

elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("🔍 台股自動估價系統 (個股)")
    stock_code = st.text_input("請輸入台股代碼 (例如: 2330)", value="")
    if stock_code:
        info = get_stock_info(stock_code)
        if info:
            st.markdown(f"## {info['name']}")
            cp1, cp2 = st.columns([2, 1])
            with cp1:
                color = "#ff4b4b" if info['change'] > 0 else "#00ff00" if info['change'] < 0 else "#FFFFFF"
                st.markdown(f"<div class='metric-val' style='color:{color}'>{info['price']:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"<span style='color:{color}; font-weight:bold; font-size:1.5rem;'>{info['change']:+.2f} ({info['pct']:+.2f}%)</span>", unsafe_allow_html=True)
            with cp2:
                st.caption("今日行情")
                st.write(f"最高: {info['high']:.2f} / 最低: {info['low']:.2f}")
                st.write(f"總量: {int(info['vol']/1000):,} 張")
            st.divider()
            eps = st.number_input("輸入該股 EPS (4季累積)", min_value=0.01, step=0.1, value=10.0)
            pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)
            fair_price = eps * pe_target
            st.subheader("📊 估價結果")
            st.markdown(f"<div class='calc-box'>合理價參考：<span class='highlight-val'>{fair_price:.2f}</span></div>", unsafe_allow_html=True)

elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF 專用分析 ")
    symbol_input = st.text_input("ETF 代號", placeholder="例如: 00919").strip().upper()
    if st.button("開始計算", type="primary") and symbol_input:
        with st.spinner('抓取數據中...'): st.session_state.data = get_safe_data_etf(symbol_input)

    if st.session_state.data and st.session_state.data.get("success"):
        d = st.session_state.data
        st.markdown(f"## {d['name']} <small style='font-size:1rem; color:#aaa;'>(偵測為{d['freq_label']}配息)</small>", unsafe_allow_html=True)
        m_color = "#ff4b4b" if d['change'] >= 0 else "#00ff00"
        st.markdown(f"<div class='metric-val' style='color:{m_color}'>{d['price']:.2f}</div>", unsafe_allow_html=True)
        
        st.divider(); st.subheader("📑 歷史配息參考")
        # 頻率修正選單
        freq_map = {"月配": 12, "季配": 4, "半年配": 2, "年配": 1}
        sys_f = f"{d['freq_label']}配" if f"{d['freq_label']}配" in freq_map else "年配"
        user_f = st.selectbox("🔄 自訂/修正配息頻率：", list(freq_map.keys()), index=list(freq_map.keys()).index(sys_f))
        d['multiplier'], d['freq_label'] = freq_map[user_f], user_f.replace("配", "")

        e_cols = st.columns(4)
        v = [e_cols[i].number_input(f"配息 {i+1}", value=float(d["raw_divs"][i]), format="%.3f") for i in range(4)]
        avg_annual = round((sum(v) / 4) * d["multiplier"], 4)
        real_yield = (avg_annual / d['price']) * 100 if d['price'] > 0 else 0
        
        st.markdown(f"<div class='calc-box'>預估年配息: <span class='highlight-val'>{avg_annual:.2f}</span> / 殖利率: <span class='highlight-val'>{real_yield:.2f}%</span></div>", unsafe_allow_html=True)

        st.divider(); st.subheader("💰 持有張數試算")
        ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
        hold_lots = st.number_input("持有張數", min_value=0, value=10, step=1)
        total_raw = hold_lots * 1000 * v[0]
        div_54c = total_raw * (ratio_54c/100)
        nhi = div_54c * 0.0211 if div_54c >= 20000 else 0
        st.info(f"每期總配息: {total_raw:,.0f} | 扣除二代健保: {nhi:,.0f} | 實領: {total_raw-nhi:,.0f}")

elif st.session_state.page == "portfolio":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title(f"💼 {st.session_state.current_user} 的投資組合")
    edited_df = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True)
    if st.button("💾 儲存變更至資料庫", type="primary"):
        if save_portfolio_to_cloud(st.session_state.current_user, edited_df): st.success("✅ 已同步")
    
    if st.button("🚀 計算市值與領息月曆", type="primary"):
        valid = edited_df.dropna(subset=["代碼", "張數"])
        valid = valid[valid["代碼"].astype(str).str.strip() != ""]
        if not valid.empty:
            results = []
            for _, row in valid.iterrows():
                data = get_safe_data_etf(str(row["代碼"]).strip())
                if data["success"]:
                    results.append({"名稱": data["name"], "現價": data["price"], "市值": data["price"]*float(row["張數"])*1000})
            if results: st.dataframe(pd.DataFrame(results), use_container_width=True)
            cal = generate_user_calendar()
            if cal is not None: st.subheader("📅 領息月曆"); st.dataframe(cal, use_container_width=True)

elif st.session_state.page == "watchlist":
    st.title("⭐ 我的關注清單")
    if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist_from_cloud()
    new_c = st.text_input("新增代碼").upper()
    if st.button("確認加入") and new_c:
        if new_c not in st.session_state.watchlist:
            st.session_state.watchlist.append(new_c); save_watchlist_to_cloud(st.session_state.watchlist); st.rerun()

    @st.fragment(run_every=120)
    def show_watchlist():
        st.caption(f"⏱️ 自動刷新中... {datetime.now(tw_tz).strftime('%H:%M:%S')}")
        for code in st.session_state.watchlist:
            item = get_stock_info(code)
            if item:
                c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                color = "#ff4b4b" if item['change'] > 0 else "#00ff00"
                c1.write(f"**{item['name']}** ({code})")
                c2.markdown(f"<span style='color:{color}; font-size:1.3rem; font-weight:bold;'>{item['price']:.2f}</span>", unsafe_allow_html=True)
                c3.write(f"{item['pct']:+.2f}%")
                if c4.button("刪除", key=f"del_{code}"):
                    st.session_state.watchlist.remove(code); save_watchlist_to_cloud(st.session_state.watchlist); st.rerun()
                st.divider()
    show_watchlist()

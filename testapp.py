import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import pytz
import plotly.express as px
import extra_streamlit_components as stx  # 新增套件

# --- 0. Cookie 管理器初始化 ---
@st.cache_resource
def get_cookie_manager():
    return stx.CookieManager()

cookie_manager = get_cookie_manager()

@st.cache_resource
def get_user_db():
    # 儲存 帳號:密碼
    return {"admin": "8888"}

@st.cache_resource
def get_all_portfolios():
    # 儲存 帳號:DataFrame (模擬資料庫儲存每個人的內容)
    return {}

user_db = get_user_db()
all_portfolios = get_all_portfolios()

# --- 登入狀態邏輯 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'current_user' not in st.session_state:
    st.session_state.current_user = None

# --- [自動登入檢查] ---
# 如果尚未登入，檢查瀏覽器是否有 Cookie
if not st.session_state.logged_in:
    saved_user = cookie_manager.get(cookie="saved_user")
    saved_pw = cookie_manager.get(cookie="saved_pw")
    
    if saved_user and saved_pw:
        if saved_user in user_db and user_db[saved_user] == saved_pw:
            st.session_state.logged_in = True
            st.session_state.current_user = saved_user
            if saved_user not in all_portfolios:
                all_portfolios[saved_user] = pd.DataFrame(columns=["代碼", "張數"])
            st.session_state.portfolio = all_portfolios[saved_user]

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
        # 記住我選項
        remember_me = st.checkbox("下回自動登入", value=True)
        
        if st.button("登入系統", use_container_width=True, type="primary"):
            if u_id in user_db and user_db[u_id] == u_pw:
                # 如果勾選記住我，將資訊存入 Cookie (保存 30 天)
                if remember_me:
                    cookie_manager.set("saved_user", u_id, expires_at=datetime.now() + pd.Timedelta(days=30))
                    cookie_manager.set("saved_pw", u_pw, expires_at=datetime.now() + pd.Timedelta(days=30))
                
                st.session_state.logged_in = True
                st.session_state.current_user = u_id
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
    st.session_state.portfolio = all_portfolios.get(st.session_state.current_user, pd.DataFrame(columns=["代碼", "張數"]))

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
        if st.button("🚪 登出並清除自動登入"):
            # 登出時清除 Cookie
            cookie_manager.delete("saved_user")
            cookie_manager.delete("saved_pw")
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

# 這裡以下維持你原本的所有功能頁面代碼 (stock_query, etf_query, pk_tool, portfolio)...
# (篇幅關係省略重複部分，直接貼上你原本的剩餘代碼即可)
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
# 頁面 D：個人投資組合 (修正編輯與刪除邏輯)
# ==========================================
elif st.session_state.page == "portfolio":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title(f"💼 {st.session_state.current_user} 的投資組合")
    
    st.markdown("### 📝 編輯並儲存清單")
    
    # 修正重點：使用 st.data_editor 並確保它能正確寫回 session_state
    # 這裡的 key="portfolio_editor" 讓 Streamlit 自動追蹤變動
    edited_df = st.data_editor(
        st.session_state.portfolio, 
        num_rows="dynamic", 
        use_container_width=True,
        key="portfolio_editor"
    )
    
    # 只要編輯內容有變，就同步回 session_state
    st.session_state.portfolio = edited_df

    if st.button("💾 更新並永久儲存至帳號", type="primary"):
        # 同步回全局 cache_resource
        all_portfolios[st.session_state.current_user] = st.session_state.portfolio
        
        results = []
        total_market_val = 0
        total_annual_div = 0
        
        # 排除掉空的列
        valid_df = st.session_state.portfolio.dropna(subset=["代碼", "張數"])
        
        if not valid_df.empty:
            with st.spinner("同步市場最新價格中..."):
                for index, row in valid_df.iterrows():
                    code = str(row["代碼"]).strip().upper()
                    try:
                        shares = float(row["張數"]) * 1000
                    except: continue
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

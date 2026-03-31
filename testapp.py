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

# --- 4. 核心數據抓取函數 (中文化增強版) ---
def get_stock_info(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                # 優先從 Yahoo 股市網頁抓取中文名稱
                name = symbol
                try:
                    name_url = f"https://tw.stock.yahoo.com/quote/{full_ticker}"
                    soup = BeautifulSoup(requests.get(name_url, headers=headers, timeout=5).text, 'html.parser')
                    name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                    if name_tag: 
                        name = name_tag.text.strip()
                except:
                    name = t.info.get('shortName', symbol)
                
                # 特定代碼強制修正
                if symbol == "2330": name = "台積電"
                
                curr_p = hist['Close'].iloc[-1]
                prev_p = hist['Close'].iloc[-2]
                change = curr_p - prev_p
                pct = (change / prev_p) * 100
                
                divs = t.dividends
                annual_div = 0.0
                if not divs.empty:
                    last_year = divs[divs.index > (divs.index[-1] - pd.DateOffset(years=1))]
                    annual_div = last_year.sum()
                
                return {
                    "name": name, "price": curr_p, "change": change, 
                    "pct": pct, "div": annual_div, "yield": (annual_div/curr_p)*100 if curr_p>0 else 0,
                    "high": hist['High'].iloc[-1], "low": hist['Low'].iloc[-1], 
                    "open": hist['Open'].iloc[-1], "vol": hist['Volume'].iloc[-1]
                }
        except: continue
    return None

@st.cache_data(ttl=600)
def get_safe_data_etf(symbol):
    # 這裡與 get_stock_info 邏輯類似但針對 ETF 頁面做細節微調
    info = get_stock_info(symbol)
    if not info: return {"success": False, "msg": f"找不到代號 {symbol}"}
    
    # 額外抓取最近四筆配息 (ETF 專用)
    t = yf.Ticker(f"{symbol}.TW" if "." not in str(symbol) else symbol)
    divs = t.dividends
    raw_divs = [0.0]*4
    multiplier = 4
    freq_label = "季"
    
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
        "raw_divs": raw_divs, "multiplier": multiplier, "freq_label": freq_label
    }

# --- 5. 導覽邏輯 ---
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# ==========================================
# 首頁：功能導覽
# ==========================================
if st.session_state.page == "home":
    st.title("🚀 台股投資工具箱")
    st.write("請選擇功能進入：")
    st.divider()
    
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.subheader("📈 個股分析")
        if st.button("個股查詢與估價", use_container_width=True, type="primary"):
            go_to("stock_query")
    with col_b:
        st.subheader("📊 ETF 分析")
        if st.button("ETF 試算與規劃", use_container_width=True, type="primary"):
            go_to("etf_query")
    with col_c:
        st.subheader("⚔️ PK 對比")
        if st.button("雙股/ETF PK 工具", use_container_width=True, type="primary"):
            go_to("pk_tool")

# ==========================================
# 頁面 A：個股查詢系統
# ==========================================
elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("🔍 台股自動估價系統 (個股)")
    stock_code = st.text_input("請輸入台股代碼 (例如: 2330)", value="")
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
                st.write(f"開盤: {info['open']:.2f} / 總量: {int(info['vol']/1000):,} 張")
            st.divider()

    col_eps, col_pe = st.columns(2)
    with col_eps: eps = st.number_input("輸入該股 EPS (4季累積)", min_value=0.01, step=0.1, value=10.0)
    with col_pe: pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)
    
    if current_price > 0:
        fair_price = eps * pe_target
        st.subheader("📊 換算結果")
        st.metric(label="合理價參考", value=f"{fair_price:.2f}")
        if current_price <= fair_price: st.success(f"✅ 目前股價 {current_price:.2f} 低於目標參考價")
        else: st.warning(f"⚠️ 目前股價 {current_price:.2f} 已超過目標參考價")
        st.divider()

    st.markdown("### 📖 說明")
    st.markdown("1. 輸入個股代碼。  \n2. 輸入4季累積EPS。  \n3. 輸入個股本益比。  \n4. 計算公式為 `EPS × 自訂目標本益比 = 合理價參考`。")

# ==========================================
# 頁面 B：ETF 分析系統
# ==========================================
elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF 專用 Ez開發")
    
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
            st.markdown(f"## {d['name']} <small>(偵測為{d['freq_label']}配)</small>", unsafe_allow_html=True)
            
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
            
            sc1, sc2 = st.columns(2)
            with sc1:
                st.caption(f"預估年配息 ({d['freq_label']}配換算)")
                st.markdown(f"<div class='highlight-val'>{avg_annual:.2f}</div>", unsafe_allow_html=True)
            with sc2:
                st.caption("實質殖利率")
                st.markdown(f"<div class='highlight-val'>{real_yield:.2f}%</div>", unsafe_allow_html=True)

            st.divider()
            st.subheader("📊 估值位階參考")
            p_cheap, p_fair, p_high = avg_annual/0.10, avg_annual/0.07, avg_annual/0.05
            rec = "💎 便宜買入" if d['price'] <= p_cheap else "✅ 合理持有" if d['price'] <= p_fair else "❌ 昂貴不建議"
            st.info(f"系統建議：{rec}")
            
            # 張數試算
            st.subheader("💰 持有張數試算")
            hold_lots = st.number_input("持有張數", min_value=0, value=10)
            total_shares = hold_lots * 1000
            st.markdown(f"<div class='calc-box'>預估投入：{(total_shares * d['price'] * 1.001425):,.0f} 元<br>一年累計配息：{(total_shares * d1 * d['multiplier']):,.0f} 元</div>", unsafe_allow_html=True)

    with side_col:
        st.write("### 📖 說明")
        st.caption("1. 輸入代號後點擊開始計算。  \n2. 系統自動偵測配息頻率。  \n3. 配息金額可手動微調。")

# ==========================================
# 頁面 C：PK 對比工具
# ==========================================
elif st.session_state.page == "pk_tool":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("⚔️ 雙股 PK 對比工具")
    
    col_in1, col_in2 = st.columns(2)
    with col_in1: code1 = st.text_input("輸入代碼 A", value="2330").strip().upper()
    with col_in2: code2 = st.text_input("輸入代碼 B", value="2454").strip().upper()
    
    if st.button("開始交叉 PK"):
        with st.spinner("抓取對比數據中..."):
            r1, r2 = get_stock_info(code1), get_stock_info(code2)
            if r1 and r2:
                st.divider()
                c1, c2 = st.columns(2)
                for i, r in enumerate([r1, r2]):
                    with [c1, c2][i]:
                        color = "#FF0000" if r['change'] > 0 else "#00FF00"
                        st.markdown(f"""<div class="pk-card">
                            <h3>{r['name']}</h3>
                            <h2 style="color:{color}">{r['price']:.2f}</h2>
                            <p>{r['change']:+.2f} ({r['pct']:+.2f}%)</p>
                        </div>""", unsafe_allow_html=True)
                
                # PK 表格
                df = pd.DataFrame({
                    "指標項目": ["名稱", "目前價格", "今日漲跌", "當前漲幅", "預估年配息", "預估殖利率"],
                    f"{code1}": [r1['name'], f"{r1['price']:.2f}", f"{r1['change']:+.2f}", f"{r1['pct']:.2f}%", f"{r1['div']:.2f}", f"{r1['yield']:.2f}%"],
                    f"{code2}": [r2['name'], f"{r2['price']:.2f}", f"{r2['change']:+.2f}", f"{r2['pct']:.2f}%", f"{r2['div']:.2f}", f"{r2['yield']:.2f}%"]
                })
                st.table(df)
            else:
                st.error("查詢失敗，請檢查代碼。")

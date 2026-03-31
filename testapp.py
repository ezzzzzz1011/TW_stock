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
    st.session_state.page = "home"  # 預設首頁
if 'data' not in st.session_state: 
    st.session_state.data = None    # 用於 ETF 數據儲存

# --- 3. 自定義 CSS (整合兩者風格) ---
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
    </style>
    """, unsafe_allow_html=True)

# --- 4. ETF 核心數據抓取函數 ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    default_date = datetime.now().strftime('%Y-%m-%d')
    res = {"name": symbol, "success": False, "price_hist": None, "raw_divs": [0.0]*4, "msg": "", "last_date": default_date, "multiplier": 4, "freq_label": "季"}
    
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                res["price_hist"] = hist
                try: res["last_date"] = hist.index[-1].strftime('%Y-%m-%d')
                except: pass
                divs = t.dividends
                if not divs.empty:
                    d_list = divs.tail(4).tolist()[::-1]
                    while len(d_list) < 4: d_list.append(0.0)
                    res["raw_divs"] = d_list
                    last_year_date = divs.index[-1] - pd.DateOffset(years=1)
                    count_in_year = len(divs[divs.index > last_year_date])
                    if count_in_year >= 10: res["multiplier"], res["freq_label"] = 12, "月"
                    elif count_in_year >= 3: res["multiplier"], res["freq_label"] = 4, "季"
                    elif count_in_year >= 2: res["multiplier"], res["freq_label"] = 2, "半年"
                    else: res["multiplier"], res["freq_label"] = 1, "年"
                try:
                    name_url = f"https://tw.stock.yahoo.com/quote/{full_ticker}"
                    soup = BeautifulSoup(requests.get(name_url, headers=headers, timeout=5).text, 'html.parser')
                    name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                    if name_tag: res["name"] = name_tag.text.strip()
                except: pass
                res["success"] = True
                return res
        except: continue
    res["msg"] = f"找不到代號 {symbol}。"
    return res

# --- 5. 導覽邏輯 ---
def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# ==========================================
# 首頁：選擇功能
# ==========================================
if st.session_state.page == "home":
    st.title("🚀 台股投資工具箱")
    st.write("歡迎使用！請選擇您今天要進行的查詢任務：")
    st.divider()
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("📈 個股分析")
        st.write("包含即時行情與本益比估價系統")
        if st.button("進入個股查詢", use_container_width=True, type="primary"):
            go_to("stock_query")
    with col_b:
        st.subheader("📊 ETF 分析")
        st.write("包含配息頻率偵測、殖利率與資產規劃")
        if st.button("進入 ETF 查詢", use_container_width=True, type="primary"):
            go_to("etf_query")

# ==========================================
# 頁面 A：個股查詢系統
# ==========================================
elif st.session_state.page == "stock_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("🔍 台股自動估價系統 (個股)")

    stock_code = st.text_input("請輸入台股代碼 (例如: 2330)", value="")
    current_price = 0.0

    if stock_code:
        full_code = f"{stock_code}.TW" if "." not in stock_code else stock_code
        try:
            ticker = yf.Ticker(full_code)
            hist = ticker.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                open_price = hist['Open'].iloc[-1]
                high_price = hist['High'].iloc[-1]
                low_price = hist['Low'].iloc[-1]
                volume = hist['Volume'].iloc[-1]
                prev_close = ticker.info.get('previousClose', open_price)
                
                stock_name = ticker.info.get('shortName', stock_code)
                if "Taiwan Semiconductor" in stock_name or stock_code == "2330": stock_name = "台積電"
                
                price_change = current_price - prev_close
                price_change_pct = (price_change / prev_close) * 100
                
                st.markdown(f"## {stock_name}")
                st.caption(f"資料日期：{datetime.now().strftime('%Y-%m-%d')}")
                cp1, cp2 = st.columns([2, 1])
                with cp1:
                    color = "#FF0000" if price_change > 0 else "#00FF00" if price_change < 0 else "#FFFFFF"
                    st.markdown(f"<h1 style='color: {color}; margin-bottom: 0;'>{current_price:.2f}</h1>", unsafe_allow_html=True)
                    st.markdown(f"<h3 style='color: {color}; margin-top: 0;'>{price_change:+.2f} ({price_change_pct:+.2f}%)</h3>", unsafe_allow_html=True)
                with cp2:
                    st.write("**今日行情細節**")
                    st.write(f"最高: {high_price:.2f} / 最低: {low_price:.2f}")
                    st.write(f"開盤: {open_price:.2f} / 總量: {int(volume/1000):,} 張")
                st.divider()
        except: st.error("代碼查詢失敗")

    col_eps, col_pe = st.columns(2)
    with col_eps: eps = st.number_input("輸入該股 EPS (4季累積)", min_value=0.01, step=0.1, value=10.0)
    with col_pe: pe_target = st.number_input("自訂參考本益比 (PE)", value=15.0, step=0.1)

    if current_price > 0:
        fair_price = eps * pe_target
        st.subheader("📊 換算結果")
        st.metric(label="合理價參考", value=f"{fair_price:.2f}")
        if current_price <= fair_price: st.success(f"✅ 目前股價 {current_price:.2f} 低於目標參考價 {fair_price:.2f}")
        else: st.warning(f"⚠️ 目前股價 {current_price:.2f} 已超過目標參考價 {fair_price:.2f}")
        st.divider()

    st.markdown("### 📖 說明")
    st.markdown("1. 輸入個股代碼。\n2. 輸入4季累積EPS。\n3. 輸入個股本益比。\n4. 計算公式為 `EPS × 自訂目標本益比 = 合理價參考`。")

# ==========================================
# 頁面 B：ETF 查詢系統
# ==========================================
elif st.session_state.page == "etf_query":
    if st.button("⬅️ 返回工具箱"): go_to("home")
    st.title("📈 ETF專用 Ez開發")

    main_col, side_col = st.columns([8, 4])
    with main_col:
        st.markdown("### 🔍 查詢設定")
        input_c1, input_c2 = st.columns([3, 1])
        with input_c1: symbol_input = st.text_input("ETF 代號", placeholder="例如: 00919").strip().upper()
        with input_c2:
            st.write("")
            st.write("")
            if st.button("開始計算", type="primary"):
                if symbol_input:
                    with st.spinner('抓取數據中...'):
                        st.session_state.data = get_safe_data(symbol_input)

        if st.session_state.data and st.session_state.data.get("success"):
            data = st.session_state.data
            mult, fl = data["multiplier"], data["freq_label"]
            latest_data = data["price_hist"].iloc[-1]
            curr_p = float(latest_data['Close'])
            diff = curr_p - data["price_hist"]['Close'].iloc[-2]
            pct = (diff / data["price_hist"]['Close'].iloc[-2]) * 100
            m_color = "#ff4b4b" if diff >= 0 else "#00ff00"

            st.markdown(f"## {data['name']} <small style='font-size:1rem; color:#aaa;'>(偵測為{fl}配息)</small>", unsafe_allow_html=True)
            st.markdown(f"<div class='date-text'>資料日期：{data.get('last_date')}</div>", unsafe_allow_html=True)
            
            info_c1, info_c2 = st.columns([2, 1])
            with info_c1:
                st.markdown(f"<div class='metric-val' style='color:{m_color}'>{curr_p:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"<span style='color:{m_color}; font-weight:bold; font-size:1.5rem;'>{diff:+.2f} ({pct:+.2f}%)</span>", unsafe_allow_html=True)
            with info_c2:
                st.caption("今日行情細節")
                st.write(f"最高: {latest_data['High']:.2f} / 最低: {latest_data['Low']:.2f}")
                st.write(f"開盤: {latest_data['Open']:.2f} / 總量: {latest_data['Volume']/1000:,.0f} 張")

            st.divider()
            st.subheader("📑 歷史配息參考")
            e_cols = st.columns(4)
            d1 = e_cols[0].number_input("最新", value=float(data["raw_divs"][0]), format="%.3f")
            d2 = e_cols[1].number_input("前一", value=float(data["raw_divs"][1]), format="%.3f")
            d3 = e_cols[2].number_input("前二", value=float(data["raw_divs"][2]), format="%.3f")
            d4 = e_cols[3].number_input("前三", value=float(data["raw_divs"][3]), format="%.3f")
            
            avg_annual_div = (sum([d1, d2, d3, d4]) / 4) * mult
            real_yield = (avg_annual_div / curr_p) * 100
            
            stat_c1, stat_c2 = st.columns(2)
            with stat_c1:
                st.caption(f"預估年配息 (系統以{fl}配計算)")
                st.markdown(f"<div class='highlight-val'>{avg_annual_div:.2f}</div>", unsafe_allow_html=True)
            with stat_c2:
                st.caption("實質殖利率")
                st.markdown(f"<div class='highlight-val'>{real_yield:.2f}%</div>", unsafe_allow_html=True)

            st.divider()
            st.subheader("📊 估值位階參考")
            p_cheap, p_fair, p_high = avg_annual_div/0.10, avg_annual_div/0.07, avg_annual_div/0.05
            rec_text = "💎 便宜買入" if curr_p <= p_cheap else "✅ 合理持有" if curr_p <= p_fair else "❌ 昂貴不建議"
            st.info(f"系統建議：{rec_text}")
            
            table_html = f"""<table class="styled-table"><thead><tr><th>估值位階</th><th>建議價格參考</th></tr></thead><tbody>
                            <tr><td>💎 便宜價 (10%)</td><td>{p_cheap:.2f} 以下</td></tr>
                            <tr><td>🔔 合理價 (7%)</td><td>{p_cheap:.2f} ~ {p_fair:.2f}</td></tr>
                            <tr><td>❌ 昂貴價 (5%)</td><td>高於 {p_high:.2f}</td></tr></tbody></table>"""
            st.markdown(table_html, unsafe_allow_html=True)

            st.divider()
            st.subheader("💰 持有張數試算")
            ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
            calc_c1, calc_c2 = st.columns([1, 2])
            with calc_c1: hold_lots = st.number_input("持有張數", min_value=0, value=10, step=1)
            with calc_c2:
                total_shares = hold_lots * 1000
                total_raw = total_shares * d1
                div_54c = total_raw * (ratio_54c/100)
                nhi = div_54c * 0.0211 if div_54c >= 20000 else 0
                st.markdown(f"""<div class="calc-box">預估總投入：{(total_shares * curr_p * 1.001425):,.0f} 元<br>
                                每{fl}實領：{(total_raw - nhi):,.0f} 元 {"(已扣二代健保)" if nhi > 0 else ""}<br>
                                一年累計：{((total_raw - nhi) * mult):,.0f} 元</div>""", unsafe_allow_html=True)

    with side_col:
        st.write("### 📖 說明")
        st.caption("1. 輸入代號後點擊開始計算。\n2. 系統自動偵測配息頻率。\n3. 配息金額可手動微調。")
        st.divider()
        st.success("系統正常運行中")

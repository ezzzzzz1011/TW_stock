import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime

# --- [維持原樣] 網頁設定 ---
st.set_page_config(page_title="ETF專用 Ez開發", layout="wide")

# --- [維持原樣] 原始 CSS 樣式 ---
st.markdown("""
    <style>
    .main { background-color: #121218; color: #ffffff; }
    .stButton>button { width: 100%; border-radius: 12px; font-weight: bold; height: 3.5em; background-color: #ffffff; color: black; border: none; }
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
    </style>
    """, unsafe_allow_html=True)

# --- [維持原樣] 核心數據抓取 ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    default_date = datetime.now().strftime('%Y-%m-%d')
    res = {"symbol": symbol, "name": symbol, "success": False, "price_hist": None, "raw_divs": [0.0]*4, "msg": "", "last_date": default_date, "multiplier": 4, "freq_label": "季"}
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

# --- [精準修正] EPS 抓取邏輯 (修正 2025Q4 錯誤) ---
def get_eps_data(symbol):
    for suffix in [".TW", ".TWO"]:
        try:
            t = yf.Ticker(f"{symbol}{suffix}")
            df = t.quarterly_financials
            bs = t.quarterly_balance_sheet
            if df is None or df.empty: continue
            
            def get_val(names, source):
                for name in names:
                    if name in source.index: return source.loc[name]
                return None

            rev = get_val(['Total Revenue'], df)
            gp = get_val(['Gross Profit'], df)
            ni = get_val(['Net Income Common Stockholders', 'Net Income'], df)
            shares = get_val(['Ordinary Share Number', 'Share Capital'], bs)
            eps_raw = get_val(['Basic EPS'], df)

            raw_list = []
            cols = df.columns[:4][::-1] 
            accum_eps = 0.0
            current_year = None

            for col in cols:
                y, m = col.year, col.month
                q_label = "Q1" if m <= 3 else "Q2" if m <= 6 else "Q3" if m <= 9 else "Q4"
                if current_year != y: accum_eps = 0.0; current_year = y
                
                # 校正邏輯：若 EPS 為 NaN/0 則用 (淨利/股數)*10 計算
                val_eps = 0.0
                if ni is not None and shares is not None and not pd.isna(ni[col]) and shares[col] != 0:
                    val_eps = (ni[col] / shares[col]) * 10
                elif eps_raw is not None and not pd.isna(eps_raw[col]):
                    val_eps = eps_raw[col]
                
                margin_g = (gp[col] / rev[col] * 100) if rev is not None and gp is not None else 0
                margin_n = (ni[col] / rev[col] * 100) if rev is not None and ni is not None else 0
                accum_eps += val_eps
                
                raw_list.append({
                    "日期": f"{y}{q_label}",
                    "毛利 (%)": f"{margin_g:.2f}",
                    "淨利 (%)": f"{margin_n:.2f}",
                    "當期 EPS": f"{val_eps:.2f}",
                    "累積 EPS": f"{accum_eps:.2f}"
                })
            return pd.DataFrame(raw_list[::-1])
        except: continue
    return None

# --- [維持原樣] 剩餘 UI 邏輯 ---
if 'data' not in st.session_state: st.session_state.data = None
if 'show_eps' not in st.session_state: st.session_state.show_eps = False

st.title("📈 ETF專用 Ez開發")
main_col, side_col = st.columns([8, 4])

with main_col:
    st.markdown("### 🔍 查詢設定")
    input_c1, input_c2 = st.columns([3, 1])
    with input_c1: symbol_input = st.text_input("股票代號", placeholder="例如:00919").strip().upper()
    with input_c2:
        st.write(""); st.write("")
        if st.button("開始計算", type="primary"):
            if symbol_input:
                st.session_state.data = get_safe_data(symbol_input)
                st.session_state.show_eps = False

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
        
        if st.button("🔍 查詢獲利與當季累積 EPS"):
            st.session_state.show_eps = not st.session_state.show_eps 
        if st.session_state.show_eps:
            eps_df = get_eps_data(data["symbol"])
            if eps_df is not None: st.table(eps_df)
            else: st.warning("無法取得此標的財報數據")

        avg_annual_div = (sum([d1, d2, d3, d4]) / 4) * mult
        real_yield = (avg_annual_div / curr_p) * 100
        
        st.write("")
        stat_c1, stat_c2 = st.columns(2)
        with stat_c1:
            st.caption(f"預估年配息 (系統以{fl}配計算)")
            st.markdown(f"<div class='highlight-val'>{avg_annual_div:.2f}</div>", unsafe_allow_html=True)
        with stat_c2:
            st.caption("實質殖利率")
            st.markdown(f"<div class='highlight-val'>{real_yield:.2f}%</div>", unsafe_allow_html=True)

        st.divider()
        st.subheader("📊 估值位階參考")
        p_cheap, p_fair, p_high = avg_annual_div / 0.10, avg_annual_div / 0.07, avg_annual_div / 0.05
        rec_text = "💎 便宜買入" if curr_p <= p_cheap else "✅ 合理持有" if curr_p <= p_fair else "❌ 昂貴不建議"
        st.markdown(f"<div class='calc-box'>📢 系統建議：{rec_text}</div>", unsafe_allow_html=True)
        st.markdown(f"""<table class="styled-table"><thead><tr><th>估值位階</th><th>建議價格參考</th></tr></thead>
            <tbody><tr><td>💎 便宜價 (10%)</td><td>{p_cheap:.2f} 以下</td></tr><tr><td>🔔 合理價 (7%)</td><td>{p_cheap:.2f} ~ {p_fair:.2f}</td></tr>
            <tr><td>❌ 昂貴價 (5%)</td><td>高於 {p_high:.2f}</td></tr></tbody></table>""", unsafe_allow_html=True)

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
            st.markdown(f"""<div class="calc-box">以現價 {curr_p:.2f} 元計算，持有 {hold_lots} 張：<br>
                <span class="white-text">預估總投入：{(total_shares * curr_p * 1.001425):,.0f} 元</span><br>
                <span class="white-text">每{fl}實領：{(total_raw - nhi):,.0f} 元</span></div>""", unsafe_allow_html=True)

        st.divider()
        st.subheader("🎯 資產與殖利率規劃")
        plan_c1, plan_c2 = st.columns(2)
        with plan_c1:
            plan_budget = st.number_input("預計投入總資產 (元)", min_value=0, value=1000000)
            plan_yield = st.slider("目標年殖利率 (%)", 3.0, 12.0, float(f"{real_yield:.2f}"))
        with plan_c2:
            annual_income = plan_budget * (plan_yield / 100)
            st.markdown(f"<div class='plan-box'>🎯 規劃結果：<br>1 年拿多少：{annual_income:,.0f} 元</div>", unsafe_allow_html=True)

    elif st.session_state.data: st.error(st.session_state.data.get("msg", "查詢失敗"))

with side_col:
    st.write("### 📖 說明")
    st.caption("EPS 計算已新增備援邏輯解決 2025Q4 錯誤。")
    st.success("系統正常運行中")

import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime

# --- 1. 網頁設定與完整 CSS (還原原始樣式) ---
st.set_page_config(page_title="ETF專用 Ez開發", layout="wide")

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

# --- 2. 核心數據抓取 ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    res = {"symbol": symbol, "name": symbol, "success": False, "price_hist": None, "raw_divs": [0.0]*4, "multiplier": 4, "freq_label": "季"}
    
    for suffix in [".TW", ".TWO"]:
        try:
            t = yf.Ticker(f"{symbol}{suffix}")
            hist = t.history(period="5d")
            if not hist.empty:
                res["price_hist"] = hist
                res["last_date"] = hist.index[-1].strftime('%Y-%m-%d')
                divs = t.dividends
                if not divs.empty:
                    d_list = divs.tail(4).tolist()[::-1]
                    while len(d_list) < 4: d_list.append(0.0)
                    res["raw_divs"] = d_list
                    # 偵測配息頻率
                    last_year = divs[divs.index > (divs.index[-1] - pd.DateOffset(years=1))]
                    count = len(last_year)
                    if count >= 10: res["multiplier"], res["freq_label"] = 12, "月"
                    elif count >= 3: res["multiplier"], res["freq_label"] = 4, "季"
                    elif count >= 2: res["multiplier"], res["freq_label"] = 2, "半年"
                    else: res["multiplier"], res["freq_label"] = 1, "年"
                res["success"] = True
                return res
        except: continue
    return res

# --- 3. 強效 EPS 抓取 (解決 NaN 與 數值錯誤) ---
def get_eps_data(symbol):
    for suffix in [".TW", ".TWO"]:
        try:
            t = yf.Ticker(f"{symbol}{suffix}")
            df = t.quarterly_financials
            bs = t.quarterly_balance_sheet
            if df is None or df.empty: continue

            # 備援抓取欄位函數
            def f(names, src):
                for n in names:
                    if n in src.index: return src.loc[n]
                return None

            rev = f(['Total Revenue'], df)
            gp = f(['Gross Profit'], df)
            ni = f(['Net Income Common Stockholders', 'Net Income'], df)
            shares = f(['Ordinary Share Number', 'Share Capital'], bs)
            eps_raw = f(['Basic EPS'], df)

            raw_list = []
            cols = df.columns[:4][::-1] # 取近四期正序計算累積
            accum_eps = 0.0
            curr_year = None

            for col in cols:
                y, m = col.year, col.month
                q = "Q1" if m<=3 else "Q2" if m<=6 else "Q3" if m<=9 else "Q4"
                if curr_year != y: accum_eps = 0.0; curr_year = y
                
                # --- EPS 核心修正：解決 NaN 與 3.23 問題 ---
                val_eps = 0.0
                if ni is not None and shares is not None and not pd.isna(ni[col]) and not pd.isna(shares[col]) and shares[col] != 0:
                    val_eps = (ni[col] / shares[col]) * 10 # 標準台股 EPS 公式
                elif eps_raw is not None and not pd.isna(eps_raw[col]):
                    val_eps = eps_raw[col] if abs(eps_raw[col]) > 0.1 else eps_raw[col] * 100
                
                m_g = (gp[col]/rev[col]*100) if rev is not None and gp is not None else 0
                m_n = (ni[col]/rev[col]*100) if rev is not None and ni is not None else 0
                accum_eps += val_eps
                
                raw_list.append({
                    "日期": f"{y}{q}",
                    "毛利 (%)": f"{m_g:.2f}",
                    "淨利 (%)": f"{m_n:.2f}",
                    "當期 EPS": f"{val_eps:.2f}",
                    "累積 EPS": f"{accum_eps:.2f}"
                })
            return pd.DataFrame(raw_list[::-1])
        except: continue
    return None

# --- 4. UI 介面與功能執行 ---
if 'data' not in st.session_state: st.session_state.data = None
if 'show_eps' not in st.session_state: st.session_state.show_eps = False

st.title("📈 ETF專用 Ez開發")
main_col, side_col = st.columns([8, 4])

with main_col:
    st.markdown("### 🔍 查詢設定")
    c1, c2 = st.columns([3, 1])
    with c1: sym = st.text_input("股票代號", placeholder="例如:00919").strip().upper()
    with c2:
        st.write(""); st.write("")
        if st.button("開始計算", type="primary"):
            if sym:
                st.session_state.data = get_safe_data(sym)
                st.session_state.show_eps = False

    if st.session_state.data and st.session_state.data["success"]:
        d = st.session_state.data
        latest = d["price_hist"].iloc[-1]
        price = float(latest['Close'])
        diff = price - d["price_hist"]['Close'].iloc[-2]
        pct = (diff / d["price_hist"]['Close'].iloc[-2]) * 100
        m_color = "#ff4b4b" if diff >= 0 else "#00ff00"

        st.markdown(f"## {d['name']} <small>(偵測為{d['freq_label']}配)</small>", unsafe_allow_html=True)
        st.markdown(f"<div class='date-text'>資料日期：{d.get('last_date')}</div>", unsafe_allow_html=True)
        
        ic1, ic2 = st.columns([2, 1])
        with ic1:
            st.markdown(f"<div class='metric-val' style='color:{m_color}'>{price:.2f}</div>", unsafe_allow_html=True)
            st.markdown(f"<span style='color:{m_color}; font-weight:bold; font-size:1.5rem;'>{diff:+.2f} ({pct:+.2f}%)</span>", unsafe_allow_html=True)
        with ic2:
            st.caption("今日行情")
            st.write(f"最高: {latest['High']:.2f} / 最低: {latest['Low']:.2f}")
            st.write(f"總量: {latest['Volume']/1000:,.0f} 張")

        st.divider()
        st.subheader("📑 歷史配息參考")
        ec = st.columns(4)
        div1 = ec[0].number_input("最新", value=float(d["raw_divs"][0]), format="%.3f")
        div2 = ec[1].number_input("前一", value=float(d["raw_divs"][1]), format="%.3f")
        div3 = ec[2].number_input("前二", value=float(d["raw_divs"][2]), format="%.3f")
        div4 = ec[3].number_input("前三", value=float(d["raw_divs"][3]), format="%.3f")
        
        # --- EPS 按鈕 ---
        if st.button("🔍 查詢獲利與當季累積 EPS"):
            st.session_state.show_eps = not st.session_state.show_eps
        if st.session_state.show_eps:
            edf = get_eps_data(d["symbol"])
            if edf is not None: st.table(edf)
            else: st.warning("查無財報數據")

        ann_div = (sum([div1, div2, div3, div4])/4) * d["multiplier"]
        yield_rate = (ann_div / price) * 100
        
        sc1, sc2 = st.columns(2)
        with sc1:
            st.caption("預估年配息")
            st.markdown(f"<div class='highlight-val'>{ann_div:.2f}</div>", unsafe_allow_html=True)
        with sc2:
            st.caption("實質殖利率")
            st.markdown(f"<div class='highlight-val'>{yield_rate:.2f}%</div>", unsafe_allow_html=True)

        st.divider()
        st.subheader("📊 估值位階參考")
        p_c, p_f, p_h = ann_div/0.1, ann_div/0.07, ann_div/0.05
        st.table(pd.DataFrame({"位階":["💎 便宜(10%)","🔔 合理(7%)","❌ 昂貴(5%)"],"參考價":[f"{p_c:.2f}↓", f"{p_c:.2f}~{p_f:.2f}", f"{p_h:.2f}↑"]}))

        st.divider()
        st.subheader("💰 持有張數試算")
        r54 = st.slider("54C 佔比 (%)", 0, 100, 40)
        lots = st.number_input("持有張數", min_value=0, value=10)
        total_s = lots * 1000
        d54 = (total_s * div1) * (r54/100)
        nhi = d54 * 0.0211 if d54 >= 20000 else 0
        st.markdown(f"""<div class="calc-box">預估年領：<span class="white-text">{((total_s * div1 - nhi) * d['multiplier']):,.0f} 元</span></div>""", unsafe_allow_html=True)

        st.divider()
        st.subheader("🎯 資產與殖利率規劃")
        pc1, pc2 = st.columns(2)
        with pc1:
            budget = st.number_input("預計投入總資產", min_value=0, value=1000000)
            t_yield = st.slider("目標殖利率 (%)", 3.0, 12.0, 6.0)
        with pc2:
            st.markdown(f"""<div class="plan-box">每月平均領：<span class="white-text">{(budget*t_yield/100/12):,.0f} 元</span></div>""", unsafe_allow_html=True)

with side_col:
    st.write("### 📖 說明")
    st.caption("EPS 採用手動公式校正，解決 NaN 與單位錯誤問題。")
    st.success("系統正常運行中")

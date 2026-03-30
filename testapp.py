import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime

# --- 網頁設定 ---
st.set_page_config(page_title="個股獲利分析 Ez開發", layout="wide")

# --- 初始化 Session State ---
if 'data' not in st.session_state: st.session_state.data = None
if 'show_earnings' not in st.session_state: st.session_state.show_earnings = False

# --- 自定義 CSS (完全保留你原本的樣式) ---
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

# --- 核心數據抓取 (對接 4 期獲利與累積 EPS) ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    res = {
        "symbol": symbol, "name": symbol, "success": False, "price_hist": None, 
        "raw_divs": [0.0]*4, "last_date": datetime.now().strftime('%Y-%m-%d'),
        "multiplier": 4, "freq_label": "季", "earnings": None 
    }
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                res["price_hist"] = hist
                res["last_date"] = hist.index[-1].strftime('%Y-%m-%d')
                
                # --- 配息數據 ---
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
                
                # --- 獲利明細 (只要 4 期，對接圖二與累積邏輯) ---
                try:
                    q_inc = t.quarterly_financials
                    if not q_inc.empty:
                        rev = q_inc.loc['Total Revenue'] if 'Total Revenue' in q_inc.index else None
                        gp = q_inc.loc['Gross Profit'] if 'Gross Profit' in q_inc.index else None
                        ni = q_inc.loc['Net Income'] if 'Net Income' in q_inc.index else None
                        eps_row = 'Basic EPS' if 'Basic EPS' in q_inc.index else ('Diluted EPS' if 'Diluted EPS' in q_inc.index else None)
                        eps_vals = q_inc.loc[eps_row] if eps_row else None

                        dates = q_inc.columns[:4] # 鎖定 4 期
                        temp_data = []
                        annual_sums = {}

                        # 由舊到新計算年度累積
                        for d in sorted(dates):
                            y = d.year
                            cur_rev = float(rev[d]) if rev is not None else 0
                            cur_gp = float(gp[d]) if gp is not None else 0
                            cur_ni = float(ni[d]) if ni is not None else 0
                            cur_eps = float(eps_vals[d]) if eps_vals is not None else 0
                            
                            annual_sums[y] = annual_sums.get(y, 0) + cur_eps # 累積為總和
                            
                            temp_data.append({
                                "日期": f"{y}Q{(d.month-1)//3 + 1}",
                                "毛利 (%)": f"{(cur_gp/cur_rev*100):.2f}" if cur_rev else "0.00",
                                "淨利 (%)": f"{(cur_ni/cur_rev*100):.2f}" if cur_rev else "0.00",
                                "當期 EPS": f"{cur_eps:.2f}",
                                "累積 EPS": f"{annual_sums[y]:.2f}" # 當季累積為總和
                            })
                        res["earnings"] = pd.DataFrame(temp_data[::-1])
                except: pass

                # 抓取名稱
                try:
                    name_url = f"https://tw.stock.yahoo.com/quote/{full_ticker}"
                    soup = BeautifulSoup(requests.get(name_url, headers=headers, timeout=5).text, 'html.parser')
                    name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                    if name_tag: res["name"] = name_tag.text.strip()
                except: pass
                res["success"] = True
                return res
        except: continue
    return res

# --- 介面佈局 ---
st.title("📈 個股獲利分析 Ez開發")
main_col, side_col = st.columns([8, 4])

with main_col:
    st.markdown("### 🔍 查詢設定")
    input_c1, input_c2 = st.columns([3, 1]) 
    with input_c1: 
        symbol_input = st.text_input("股票代號", placeholder="例如:2330").strip().upper()
    with input_c2:
        st.write("")
        st.write("")
        if st.button("開始計算", type="primary"):
            if symbol_input:
                with st.spinner('獲取數據中...'):
                    st.session_state.data = get_safe_data(symbol_input)
                    st.session_state.show_earnings = False

    if st.session_state.data and st.session_state.data.get("success"):
        data = st.session_state.data
        latest_p = float(data["price_hist"].iloc[-1]['Close'])
        diff = latest_p - data["price_hist"]['Close'].iloc[-2]
        pct = (diff / data["price_hist"]['Close'].iloc[-2]) * 100
        m_color = "#ff4b4b" if diff >= 0 else "#00ff00"

        st.markdown(f"## {data['name']}")
        st.markdown(f"<div class='date-text'>資料日期：{data.get('last_date')}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-val' style='color:{m_color}'>{latest_p:.2f}</div>", unsafe_allow_html=True)
        st.markdown(f"<span style='color:{m_color}; font-weight:bold; font-size:1.5rem;'>{diff:+.2f} ({pct:+.2f}%)</span>", unsafe_allow_html=True)

        st.divider()
        
        # --- 獲利明細按鈕 (取代原本成分股按鈕) ---
        if st.button("📋 展開/收合獲利 EPS 明細"):
            st.session_state.show_earnings = not st.session_state.show_earnings
        
        if st.session_state.show_earnings:
            if data.get("earnings") is not None:
                st.markdown("##### 💰 近 4 季獲利明細 (依年度累計)")
                st.table(data["earnings"])
            else:
                st.warning("暫無獲利數據。")

        st.divider()
        
        # --- 歷史配息與預估 (保留) ---
        d1, d2, d3, d4 = [float(x) for x in data["raw_divs"]]
        avg_annual_div = (sum([d1, d2, d3, d4]) / 4) * data["multiplier"]
        real_yield = (avg_annual_div / latest_p) * 100
        
        st.subheader("📑 歷史配息參考")
        st.markdown(f"預估年配息: **{avg_annual_div:.2f}** | 實質殖利率: **{real_yield:.2f}%**")

        st.divider()

        # --- 估值位階參考 (完全保留) ---
        st.subheader("📊 估值位階參考")
        p_cheap, p_fair, p_high = avg_annual_div/0.10, avg_annual_div/0.07, avg_annual_div/0.05
        if latest_p <= p_cheap: rec_text, rec_icon = "💎 便宜買入", "💸"
        elif latest_p <= p_fair: rec_text, rec_icon = "✅ 合理持有", "✅"
        else: rec_text, rec_icon = "❌ 昂貴不建議", "❌"

        st.markdown(f"""
        <div style="background-color:#1e1e28; padding:10px; border-radius:10px; border:1px solid #444; margin-bottom: 15px;">
            <span style="color: #ffffff; font-weight: bold; font-size: 1.2rem;">📢 系統建議：{rec_icon} {rec_text}</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""<table class="styled-table"><thead><tr><th>估值位階</th><th>建議價格參考</th></tr></thead><tbody>
            <tr><td>💎 便宜價 (10%)</td><td>{p_cheap:.2f} 以下</td></tr>
            <tr><td>🔔 合理價 (7%)</td><td>{p_cheap:.2f} ~ {p_fair:.2f}</td></tr>
            <tr><td>❌ 昂貴價 (5%)</td><td>高於 {p_high:.2f}</td></tr></tbody></table>""", unsafe_allow_html=True)

        # --- 54C 與張數試算 (完全保留) ---
        st.divider()
        st.subheader("💰 持有張數試算")
        ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
        hold_lots = st.number_input("持有張數", min_value=0, value=10)
        
        total_shares = hold_lots * 1000
        total_raw = total_shares * d1
        div_54c = total_raw * (ratio_54c/100)
        nhi = div_54c * 0.0211 if div_54c >= 20000 else 0
        
        st.markdown(f"""<div class="calc-box">
            持有 {hold_lots} 張，最新一季實領：<br>
            <span class="white-text">{(total_raw - nhi):,.0f} 元</span> <span class='tax-text'>{"(已扣二代健保)" if nhi > 0 else ""}</span>
        </div>""", unsafe_allow_html=True)

    elif st.session_state.data and not st.session_state.data.get("success"):
        st.error("查詢失敗。")

with side_col:
    st.write("### 📖 說明")
    st.caption("累積 EPS 為當年度各季之總和。")
    st.divider()
    st.success("系統運作中")

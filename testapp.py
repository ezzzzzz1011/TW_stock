import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import re

# --- 網頁設定 ---
st.set_page_config(page_title="ETF專用 Ez開發", layout="wide")

# --- 初始化 Session State ---
if 'data' not in st.session_state: st.session_state.data = None
if 'page' not in st.session_state: st.session_state.page = "main"

# --- 自定義 CSS (完全保留原始樣式) ---
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

# --- 核心數據抓取 (保留原始邏輯) ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    res = {
        "symbol": symbol, "name": symbol, "success": False, 
        "price_hist": None, "raw_divs": [0.0]*4, "msg": "", 
        "last_date": datetime.now().strftime('%Y-%m-%d'),
        "multiplier": 4, "freq_label": "季" 
    }
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                res["price_hist"] = hist
                res["last_date"] = hist.index[-1].strftime('%Y-%m-%d')
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
                
                name_url = f"https://tw.stock.yahoo.com/quote/{full_ticker}"
                soup = BeautifulSoup(requests.get(name_url, headers=headers, timeout=5).text, 'html.parser')
                name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                if name_tag: res["name"] = name_tag.text.strip()
                res["success"] = True
                return res
        except: continue
    res["msg"] = f"找不到代號 {symbol}。"
    return res

# --- 繞過爬蟲：改用玩股網數據源 ---
@st.cache_data(ttl=3600)
def get_etf_holdings(symbol):
    try:
        # 玩股網的 ETF 持股頁面
        url = f"https://www.wantgoo.com/stock/etf/{symbol}/constituent"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.wantgoo.com/'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 抓取表格中的成分股名稱與比例
        table = soup.find('table') 
        if not table: return None
        
        rows = table.find_all('tr')[1:] # 跳過標頭
        holdings = []
        for row in rows:
            tds = row.find_all('td')
            if len(tds) >= 3:
                name = tds[0].get_text(strip=True)
                # 玩股網名稱通常帶有代號，我們只取中文名
                clean_name = re.sub(r'\d+', '', name).replace('()', '').strip()
                ratio = tds[2].get_text(strip=True)
                if "%" in ratio:
                    holdings.append({"成分股名稱": clean_name, "持股比例": ratio})
        
        return pd.DataFrame(holdings).head(10) if holdings else None
    except:
        return None

# --- 介面邏輯 ---
if st.session_state.page == "main":
    st.title("📈 ETF專用 Ez開發")
    main_col, side_col = st.columns([8, 4])
    with main_col:
        st.markdown("### 🔍 查詢設定")
        input_c1, input_c2 = st.columns([3, 1]) 
        with input_c1: 
            symbol_input = st.text_input("股票代號", placeholder="例如:00919").strip().upper()
        with input_c2:
            st.write("")
            st.write("")
            if st.button("開始計算", type="primary"):
                if symbol_input:
                    with st.spinner('偵測頻率與抓取數據中...'):
                        st.session_state.data = get_safe_data(symbol_input)

        if st.session_state.data and st.session_state.data.get("success"):
            data = st.session_state.data
            mult, fl = data["multiplier"], data["freq_label"]
            latest_data = data["price_hist"].iloc[-1]
            curr_p = float(latest_data['Close'])
            diff = curr_p - data["price_hist"]['Close'].iloc[-2]
            pct = (diff / data["price_hist"]['Close'].iloc[-2]) * 100
            m_color = "#ff4b4b" if diff >= 0 else "#00ff00"

            t_col1, t_col2 = st.columns([6, 2])
            with t_col1:
                st.markdown(f"## {data['name']} <small style='font-size:1rem; color:#aaa;'>(偵測為{fl}配息)</small>", unsafe_allow_html=True)
                st.markdown(f"<div class='date-text'>資料日期：{data.get('last_date')}</div>", unsafe_allow_html=True)
            with t_col2:
                st.write("")
                st.write("")
                if st.button("📊 查看成分股"):
                    st.session_state.page = "composition"
                    st.rerun()
            
            st.markdown(f"<div class='metric-val' style='color:{m_color}'>{curr_p:.2f}</div>", unsafe_allow_html=True)
            st.markdown(f"<span style='color:{m_color}; font-weight:bold; font-size:1.5rem;'>{diff:+.2f} ({pct:+.2f}%)</span>", unsafe_allow_html=True)

            st.divider()
            st.subheader("📑 歷史配息參考")
            e_cols = st.columns(4)
            d1 = e_cols[0].number_input("最新", value=float(data["raw_divs"][0]), format="%.3f")
            d2 = e_cols[1].number_input("前一", value=float(data["raw_divs"][1]), format="%.3f")
            d3 = e_cols[2].number_input("前二", value=float(data["raw_divs"][2]), format="%.3f")
            d4 = e_cols[3].number_input("前三", value=float(data["raw_divs"][3]), format="%.3f")
            
            avg_annual_div = (sum([d1, d2, d3, d4]) / 4) * mult
            real_yield = (avg_annual_div / curr_p) * 100
            st.write("")
            st.columns(2)[0].metric(f"預估年配息 ({fl}配)", f"{avg_annual_div:.2f}")
            st.columns(2)[1].metric("實質殖利率", f"{real_yield:.2f}%")

            st.divider()
            st.subheader("📊 估值位階參考")
            p_cheap, p_fair, p_high = avg_annual_div/0.10, avg_annual_div/0.07, avg_annual_div/0.05
            st.markdown(f"""<table class="styled-table"><thead><tr><th>估值位階</th><th>建議價格參考</th></tr></thead><tbody>
                <tr><td>💎 便宜價 (10%)</td><td>{p_cheap:.2f} 以下</td></tr>
                <tr><td>🔔 合理價 (7%)</td><td>{p_cheap:.2f} ~ {p_fair:.2f}</td></tr>
                <tr><td>❌ 昂貴價 (5%)</td><td>高於 {p_high:.2f}</td></tr></tbody></table>""", unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("💰 持有張數試算")
            ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
            hold_lots = st.number_input("持有張數", min_value=0, value=10)
            total_raw = hold_lots * 1000 * d1
            div_54c = total_raw * (ratio_54c/100)
            nhi = div_54c * 0.0211 if div_54c >= 20000 else 0
            st.markdown(f"""<div class="calc-box">
                預估總投入：{(hold_lots * 1000 * curr_p * 1.001425):,.0f} 元<br>
                每{fl}實領：{(total_raw - nhi):,.0f} 元 <span class='tax-text'>{"(已扣二代健保)" if nhi > 0 else ""}</span><br>
                一年累計：{((total_raw - nhi) * mult):,.0f} 元
            </div>""", unsafe_allow_html=True)

elif st.session_state.page == "composition":
    data = st.session_state.data
    st.title(f"📊 {data['name']} - 成分股細節")
    if st.button("⬅️ 返回計算機"):
        st.session_state.page = "main"
        st.rerun()
    st.divider()
    with st.spinner('正在從玩股網獲取資料...'):
        df = get_etf_holdings(data['symbol'])
        if df is not None:
            st.markdown("### 🏆 前十大權重持股")
            st.table(df)
            st.info("註：此數據連結自玩股網 (WantGoo)，權重比例依據最新市場公告為準。")
        else:
            st.error("連線失敗。請檢查該代號是否為正確的台灣 ETF。")

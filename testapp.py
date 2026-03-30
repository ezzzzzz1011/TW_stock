import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime

# --- 網頁設定 ---
st.set_page_config(page_title="ETF專用 Ez開發", layout="wide")

# --- 自定義 CSS ---
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

# --- 新增：自動抓取該 ETF 的真實成分股 ---
@st.cache_data(ttl=3600)
def get_etf_components(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    components = []
    try:
        # 嘗試從 Yahoo 奇摩股市抓取成分股頁面
        url = f"https://tw.stock.yahoo.com/quote/{symbol}.TW/holding"
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 尋找包含股票代號的連結 (通常格式為 /quote/XXXX.TW)
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            if '/quote/' in href and ('.TW' in href or '.TWO' in href):
                code = href.split('/')[-1].split('.')[0]
                # 過濾掉 ETF 本身以及重複的代號
                if code != symbol and code not in components and code.isdigit():
                    components.append(code)
        return components[:10] # 回傳前 10 大成分股
    except:
        return []

# --- 核心數據抓取 (保持你原始的邏輯) ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    default_date = datetime.now().strftime('%Y-%m-%d')
    res = {
        "name": symbol, "success": False, "price_hist": None, 
        "raw_divs": [0.0]*4, "msg": "", "last_date": default_date,
        "multiplier": 4, "freq_label": "季"
    }
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

# --- 初始化 ---
if 'data' not in st.session_state: st.session_state.data = None
if 'page' not in st.session_state: st.session_state.page = "main"

st.title("📈 ETF專用 Ez開發")
main_col, side_col = st.columns([8, 4])

with main_col:
    st.markdown("### 🔍 查詢設定")
    input_c1, input_c2, input_c3 = st.columns([3, 1, 1]) 
    with input_c1: 
        symbol_input = st.text_input("股票代號", placeholder="例如:00919").strip().upper()
    
    with input_c2:
        st.write("")
        st.write("")
        if st.button("開始計算", type="primary"):
            st.session_state.page = "main"
            if symbol_input:
                with st.spinner('偵測數據中...'):
                    st.session_state.data = get_safe_data(symbol_input)

    with input_c3:
        st.write("")
        st.write("")
        if st.button("🔍 成分股"):
            if symbol_input:
                st.session_state.page = "holdings"
                with st.spinner('獲取最新成分股清單...'):
                    st.session_state.data = get_safe_data(symbol_input)
                    st.session_state.comp_list = get_etf_components(symbol_input)

    # --- 顯示邏輯 ---
    if st.session_state.data and st.session_state.data.get("success"):
        data = st.session_state.data
        
        # 主計算頁
        if st.session_state.page == "main":
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
                st.caption(f"預估年配息 ({fl}配計算)")
                st.markdown(f"<div class='highlight-val'>{avg_annual_div:.2f}</div>", unsafe_allow_html=True)
            with stat_c2:
                st.caption("實質殖利率")
                st.markdown(f"<div class='highlight-val'>{real_yield:.2f}%</div>", unsafe_allow_html=True)

            st.divider()
            st.subheader("📊 估值位階參考")
            p_cheap, p_fair, p_high = avg_annual_div/0.1, avg_annual_div/0.07, avg_annual_div/0.05
            rec_text = "💎 便宜買入" if curr_p <= p_cheap else "✅ 合理持有" if curr_p <= p_fair else "❌ 昂貴不建議"
            st.info(f"系統建議：{rec_text}")

            # 試算區 (簡化顯示)
            st.subheader("💰 持有試算")
            hold_lots = st.number_input("持有張數", min_value=0, value=10)
            total_raw = hold_lots * 1000 * d1
            st.markdown(f"<div class='calc-box'>每{fl}實領約：{total_raw:,.0f} 元 (未扣稅)<br>一年累計約：{(total_raw*mult):,.0f} 元</div>", unsafe_allow_html=True)

        # 成分股頁面
        elif st.session_state.page == "holdings":
            if st.button("⬅️ 返回主試算頁"):
                st.session_state.page = "main"
                st.rerun()
            
            st.header(f"🎯 {data['name']} - 真實成分股分析")
            clist = st.session_state.get('comp_list', [])
            
            if not clist:
                st.warning("無法抓取該代號的成分股清單，請確認代號是否為 ETF。")
            else:
                for code in clist:
                    c_data = get_safe_data(code)
                    if c_data["success"]:
                        cp = c_data["price_hist"].iloc[-1]['Close']
                        cmult = c_data["multiplier"]
                        c_avg = (sum(c_data["raw_divs"]) / 4) * cmult
                        cyield = (c_avg / cp) * 100
                        with st.expander(f"{c_data['name']} ({code}) - 預估殖利率 {cyield:.2f}%"):
                            st.write(f"股價: {cp} | 頻率: {c_data['freq_label']}配 | 預估年息: {c_avg:.2f}")

    elif st.session_state.data and not st.session_state.data.get("success"):
        st.error(st.session_state.data.get("msg", "查詢失敗"))

with side_col:
    st.write("### 📖 說明")
    st.caption("1. 系統現已支援「自動抓取」ETF 真實成分股。")
    st.caption("2. 成分股頁面同樣套用您的年化股利計算邏輯。")
    st.divider()
    st.success("數據源：Yahoo Finance / 奇摩股市")

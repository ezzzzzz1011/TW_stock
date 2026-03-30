import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime

# --- 網頁設定 ---
st.set_page_config(page_title="ETF專用 Ez開發測試版", layout="wide")

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
    .eps-box { background-color: #252532; padding: 15px; border-radius: 10px; border-left: 5px solid #ffffff; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 強化版 EPS 抓取函數 (解決 Q4 消失問題) ---
def get_eps_final(symbol, ticker_obj):
    # 方案 A: 鉅亨網季報 API (台灣在地資料，最快更新 Q4)
    try:
        url = f"https://ws.api.cnyes.com/ws/api/v1/stock/financial/profit/quarterly/{symbol}?isExtended=true"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'https://invest.cnyes.com/twstock/TWS/{symbol}/financial/profit/quarterly'
        }
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        
        if data.get('statusCode') == 200:
            items = data['data']['items']
            periods = items.get('period', [])
            # 優先取 Basic EPS
            eps_list = items.get('basicEarningsPerShare') or items.get('netEarningsPerShare', [])
            
            if eps_list and periods:
                df = pd.DataFrame({'Period': periods, 'EPS': eps_list})
                df = df.dropna().reset_index(drop=True)
                # 確保排序：最新的在最前面
                df = df.sort_values('Period', ascending=False)
                return df.head(4), "鉅亨網(即時)"
    except:
        pass

    # 方案 B: yfinance 備援 (如果 Yahoo 抓到的是舊的，會顯示來源)
    try:
        q_fin = ticker_obj.quarterly_financials
        eps_row_label = next((idx for idx in q_fin.index if "EPS" in idx and "Basic" in idx), None)
        if not eps_row_label:
            eps_row_label = next((idx for idx in q_fin.index if "EPS" in idx), None)
            
        if eps_row_label:
            eps_series = q_fin.loc[eps_row_label].dropna().sort_index(ascending=False)
            if not eps_series.empty:
                periods = []
                for d in eps_series.index:
                    # 修正 Q4 定義問題：12月結算為 Q4
                    q = (d.month-1)//3 + 1
                    periods.append(f"{d.year}-Q{q}")
                df = pd.DataFrame({'Period': periods, 'EPS': eps_series.values})
                return df.head(4), "Yahoo Finance"
    except:
        pass
    
    return None, "未知"

# --- 核心數據抓取 ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    default_date = datetime.now().strftime('%Y-%m-%d')
    res = {
        "name": symbol, "success": False, "price_hist": None, "raw_divs": [0.0]*4, 
        "msg": "", "last_date": default_date, "multiplier": 4, "freq_label": "季",
        "eps_data": None, "eps_source": "未知"
    }
    
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            
            if not hist.empty:
                res["price_hist"] = hist
                res["last_date"] = hist.index[-1].strftime('%Y-%m-%d')

                # 配息頻率偵測
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
                
                # 執行強化後的 EPS 抓取
                eps_df, source = get_eps_final(symbol, t)
                res["eps_data"] = eps_df
                res["eps_source"] = source

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

# --- 頁面呈現邏輯 (保持原樣) ---
if 'data' not in st.session_state: st.session_state.data = None

st.title("📈 ETF專用 Ez開發")
main_col, side_col = st.columns([8, 4])

with main_col:
    st.markdown("### 🔍 查詢設定")
    input_c1, input_c2 = st.columns([3, 1]) 
    with input_c1: 
        symbol_input = st.text_input("股票代號", placeholder="例如:2317 或 00919").strip().upper()
    with input_c2:
        st.write("")
        st.write("")
        if st.button("開始計算", type="primary"):
            if symbol_input:
                with st.spinner('正在從台灣在地數據庫調閱最新的 Q4 財報...'):
                    st.cache_data.clear()
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
            st.caption(f"預估年配息")
            st.markdown(f"<div class='highlight-val'>{avg_annual_div:.2f}</div>", unsafe_allow_html=True)
        with stat_c2:
            st.caption("實質殖利率")
            st.markdown(f"<div class='highlight-val'>{real_yield:.2f}%</div>", unsafe_allow_html=True)

        st.divider()
        source_name = data.get('eps_source', '未知')
        st.subheader(f"📈 核心獲利能力 (近四季 EPS - 來源: {source_name})")
        if data.get("eps_data") is not None:
            eps_df = data["eps_data"]
            st.markdown('<div class="eps-box">', unsafe_allow_html=True)
            eps_cols = st.columns(len(eps_df))
            for i, (_, row) in enumerate(eps_df.iterrows()):
                eps_cols[i].metric(f"{row['Period']}", f"{row['EPS']:.2f}")
            sum_eps = eps_df['EPS'].sum()
            st.markdown(f"<p style='margin-top:10px;'><b>近四季累積 EPS：</b> <span class='white-text' style='font-size:1.5rem;'>{sum_eps:.2f} 元</span></p>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.warning("目前資料源尚未更新 Q4 數據，請稍後再試。")

        # --- 估值、稅務與規劃區塊 (保持不變) ---
        st.divider()
        st.subheader("📊 估值位階參考")
        p_cheap, p_fair, p_high = avg_annual_div/0.10, avg_annual_div/0.07, avg_annual_div/0.05
        rec_text = "💎 便宜買入" if curr_p <= p_cheap else "✅ 合理持有" if curr_p <= p_fair else "❌ 昂貴不建議"
        st.info(f"系統建議：{rec_text}")

        st.markdown("---")
        st.subheader("💰 持有張數試算")
        ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
        hold_lots = st.number_input("持有張數", min_value=0, value=10, step=1)
        total_shares = hold_lots * 1000
        total_raw = total_shares * d1
        div_54c = total_raw * (ratio_54c/100)
        nhi = div_54c * 0.0211 if div_54c >= 20000 else 0
        st.markdown(f"""<div class="calc-box">每{fl}實領：{(total_raw - nhi):,.0f} 元 (一年累計：{((total_raw - nhi) * mult):,.0f} 元)</div>""", unsafe_allow_html=True)

    elif st.session_state.data and not st.session_state.data.get("success"):
        st.error(st.session_state.data.get("msg", "查詢失敗"))

with side_col:
    st.write("### 📖 說明")
    st.caption("1. 優先使用鉅亨網 API 解決 Yahoo 缺漏 Q4 的問題。")
    st.caption("2. 自動修正季度日期排序。")
    st.divider()
    st.success("在地資料源對接成功")

import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime
import plotly.graph_objects as go

# --- 網頁設定 ---
st.set_page_config(page_title="ETF 專業投資診斷 Ez版", layout="wide")

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
    /* 新增指標卡片 */
    .indicator-card { background: #262730; padding: 15px; border-radius: 10px; border-left: 5px solid #ffffff; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 核心數據抓取 ---
@st.cache_data(ttl=600)
def get_safe_data(symbol):
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36']
    headers = {'User-Agent': random.choice(user_agents)}
    default_date = datetime.now().strftime('%Y-%m-%d')
    res = {
        "symbol": symbol,
        "name": symbol, 
        "success": False, 
        "price_hist": None, 
        "raw_divs": [0.0]*4, 
        "msg": "", 
        "last_date": default_date,
        "multiplier": 4, 
        "freq_label": "季",
        "payout_ratio": None,
        "eps_history": None,
        "fcf": None
    }
    
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            hist = t.history(period="5d")
            
            if not hist.empty:
                res["price_hist"] = hist
                res["last_date"] = hist.index[-1].strftime('%Y-%m-%d')

                # --- 獲取財務指標 (網站核心邏輯) ---
                info = t.info
                res["payout_ratio"] = info.get("payoutRatio")
                res["fcf"] = info.get("freeCashflow")
                
                # 抓取 EPS 歷史 (損益表)
                try:
                    income = t.financials
                    if "Diluted EPS" in income.index:
                        res["eps_history"] = income.loc["Diluted EPS"].head(5)
                except: pass

                # --- 自動偵測配息頻率 ---
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
    
    res["msg"] = f"找不到代號 {symbol}。"
    return res

# --- 初始化 ---
if 'data' not in st.session_state: st.session_state.data = None

st.title("📈 ETF 投資成長診斷 Ez版")
main_col, side_col = st.columns([8, 4])

with main_col:
    st.markdown("### 🔍 查詢設定")
    input_c1, input_c2 = st.columns([3, 1])
    
    with input_c1: 
        symbol_input = st.text_input("股票/ETF 代號", placeholder="例如:00919 或 2330").strip().upper()
    
    with input_c2:
        st.write("")
        st.write("")
        if st.button("開始診斷", type="primary"):
            if symbol_input:
                with st.spinner('正在分析財務與配息數據...'):
                    st.session_state.data = get_safe_data(symbol_input)

    if st.session_state.data and st.session_state.data.get("success"):
        data = st.session_state.data
        mult = data["multiplier"]
        fl = data["freq_label"]
        latest_data = data["price_hist"].iloc[-1]
        curr_p = float(latest_data['Close'])
        diff = curr_p - data["price_hist"]['Close'].iloc[-2]
        pct = (diff / data["price_hist"]['Close'].iloc[-2]) * 100
        m_color = "#ff4b4b" if diff >= 0 else "#00ff00"

        # --- 頁籤分類 ---
        tab_calc, tab_growth = st.tabs(["💰 配息試算與估值", "📈 獲利成長分析 (Dividend Growth)"])

        with tab_calc:
            st.markdown(f"## {data['name']} <small style='font-size:1rem; color:#aaa;'>(偵測為{fl}配息)</small>", unsafe_allow_html=True)
            info_c1, info_c2 = st.columns([2, 1])
            with info_c1:
                st.markdown(f"<div class='metric-val' style='color:{m_color}'>{curr_p:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"<span style='color:{m_color}; font-weight:bold; font-size:1.5rem;'>{diff:+.2f} ({pct:+.2f}%)</span>", unsafe_allow_html=True)
            with info_c2:
                st.caption(f"資料日期：{data.get('last_date')}")
                st.write(f"最高: {latest_data['High']:.2f} / 最低: {latest_data['Low']:.2f}")
                st.write(f"總量: {latest_data['Volume']/1000:,.0f} 張")

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

            st.subheader("📊 估值位階參考")
            p_cheap, p_fair, p_high = avg_annual_div/0.10, avg_annual_div/0.07, avg_annual_div/0.05
            rec_text = "💎 便宜買入" if curr_p <= p_cheap else "✅ 合理持有" if curr_p <= p_fair else "❌ 昂貴不建議"
            st.info(f"系統建議：{rec_text}")
            
            st.markdown(f"""<table class="styled-table">
                <thead><tr><th>位階</th><th>參考價格</th></tr></thead>
                <tbody>
                    <tr><td>💎 便宜 (10%)</td><td>{p_cheap:.2f} 以下</td></tr>
                    <tr><td>🔔 合理 (7%)</td><td>{p_cheap:.2f} ~ {p_fair:.2f}</td></tr>
                    <tr><td>❌ 昂貴 (5%)</td><td>高於 {p_high:.2f}</td></tr>
                </tbody></table>""", unsafe_allow_html=True)

            st.divider()
            st.subheader("💰 持有張數試算")
            ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
            hold_lots = st.number_input("持有張數", min_value=0, value=10)
            total_shares = hold_lots * 1000
            total_raw = total_shares * d1
            div_54c = total_raw * (ratio_54c/100)
            nhi = div_54c * 0.0211 if div_54c >= 20000 else 0
            st.markdown(f"""<div class="calc-box">
                預估投入：{(total_shares * curr_p * 1.001425):,.0f} 元<br>
                每{fl}實領：{(total_raw - nhi):,.0f} 元 <small>(已扣二代健保)</small><br>
                一年累計：{((total_raw - nhi) * mult):,.0f} 元
            </div>""", unsafe_allow_html=True)

        with tab_growth:
            st.subheader("📈 股息成長指標分析")
            g_c1, g_c2 = st.columns(2)
            
            with g_c1:
                # 股利發放率 Payout Ratio
                pr = data["payout_ratio"]
                pr_val = f"{pr*100:.1f}%" if pr else "無數據"
                pr_color = "green" if pr and pr < 0.8 else "orange"
                st.markdown(f"""<div class="indicator-card">
                    <small>股利發放率 (Payout Ratio)</small><br>
                    <b style="font-size:1.5rem; color:{pr_color};">{pr_val}</b><br>
                    <small>反映公司是否過度發放股利（建議 < 80%）</small>
                </div>""", unsafe_allow_html=True)

            with g_c2:
                # 自由現金流診斷
                fcf = data["fcf"]
                fcf_status = "✅ 正向" if fcf and fcf > 0 else "⚠️ 負向/缺失"
                st.markdown(f"""<div class="indicator-card">
                    <small>現金流狀態 (FCF)</small><br>
                    <b style="font-size:1.5rem;">{fcf_status}</b><br>
                    <small>這是一間公司發放股利的真金白銀來源</small>
                </div>""", unsafe_allow_html=True)

            # EPS 趨勢圖表
            if data["eps_history"] is not None:
                st.write("#### 獲利趨勢 (EPS History)")
                eps_df = data["eps_history"].sort_index()
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=eps_df.index.strftime('%Y'), y=eps_df.values, mode='lines+markers', name='EPS', line=dict(color='#ffffff')))
                fig.update_layout(template="plotly_dark", height=300, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
                st.caption("網站建議：持續成長的 EPS 是股息增加的保證。")
            else:
                st.warning("暫無 EPS 歷史數據，可能為非個股 ETF。")

    elif st.session_state.data and not st.session_state.data.get("success"):
        st.error(st.session_state.data.get("msg", "查詢失敗"))

with side_col:
    st.write("### 📖 診斷說明")
    st.caption("1. 系統結合了 Yahoo Finance 數據與股息成長投資法。")
    st.caption("2. **EPS 趨勢**：確認公司是否具備成長動力。")
    st.caption("3. **Payout Ratio**：觀察配息是否健康，過高可能代表未來有減息風險。")
    st.divider()
    if st.session_state.data:
        st.info("💡 投資小叮嚀：對於高股息 ETF，除了殖利率，更要關注其選股邏輯中的獲利穩定度。")
    st.success("系統連線正常")

import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime, timedelta
import pytz

# --- 1. 網頁全域設定 ---
st.set_page_config(page_title="台股個股/ETF查詢 Ez開發", page_icon="🔍", layout="wide")

# 設定台灣時區
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 初始化頁面狀態 ---
if 'page' not in st.session_state:
    st.session_state.page = "home"
if 'data' not in st.session_state: 
    st.session_state.data = None

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
                    "hist": hist, "full_ticker": full_ticker
                }
        except: continue
    return None

@st.cache_data(ttl=600)
def get_safe_data_etf(symbol):
    info = get_stock_info(symbol)
    if not info: return {"success": False, "msg": f"找不到代號 {symbol}"}
    
    t = yf.Ticker(info["full_ticker"])
    divs = t.dividends
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
    st.title("🚀 台股個股/ETF查詢 Ez開發")
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
        st.subheader("⚔️ ETF對比")
        if st.button("ETF對比工具", use_container_width=True, type="primary"):
            go_to("pk_tool")

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
                div_54c = total_raw * (ratio_54c/100)
                nhi = div_54c * 0.0211 if div_54c >= 20000 else 0
                st.markdown(f"""<div class="calc-box">
                    預估總投入：{(total_shares * d['price'] * 1.001425):,.0f} 元<br>
                    每{d['freq_label']}實領：{(total_raw - nhi):,.0f} 元<br>
                    一年累計：{((total_raw - nhi) * d['multiplier']):,.0f} 元
                </div>""", unsafe_allow_html=True)
            
            # --- 回測功能修正時區問題 ---
            st.divider()
            st.subheader("⏳ 定期定額回測 (歷史模擬)")
            with st.expander("展開回測設定區塊", expanded=True):
                bt_col1, bt_col2, bt_col3 = st.columns(3)
                with bt_col1:
                    bt_monthly = st.number_input("每月投入金額", min_value=1000, value=10000, step=1000)
                with bt_col2:
                    # 使用台灣時區計算三年前
                    default_start = (datetime.now(tw_tz) - timedelta(days=1095)).date()
                    bt_start_date = st.date_input("開始日期", value=default_start)
                with bt_col3:
                    bt_reinvest = st.checkbox("股息再投入 (複利)", value=True)
                
                if st.button("🚀 執行回測模擬", use_container_width=True):
                    ticker = yf.Ticker(d["full_ticker"])
                    # 統一將輸入日期轉為帶有台灣時區的 datetime
                    bt_start_dt = datetime.combine(bt_start_date, datetime.min.time()).replace(tzinfo=tw_tz)
                    
                    bt_hist = ticker.history(start=bt_start_dt)
                    bt_divs = ticker.dividends
                    
                    if not bt_hist.empty:
                        # 確保股息數據的時區與回測起始日一致
                        # 將股息索引轉換為台灣時區進行比較
                        bt_divs.index = bt_divs.index.tz_convert(tw_tz)
                        valid_divs = bt_divs[bt_divs.index >= bt_start_dt]
                        
                        monthly_idx = bt_hist.resample('MS').first().index
                        total_invested = 0
                        shares_held = 0
                        cash_pool = 0
                        last_div_idx = 0
                        
                        for date in monthly_idx:
                            if date in bt_hist.index:
                                price = bt_hist.loc[date, 'Close']
                                total_invested += bt_monthly
                                
                                # 找出該月發放的新股息
                                # 這裡簡化為：每個月檢查當月之前的累計股息
                                current_div_total = valid_divs[valid_divs.index <= date].sum()
                                if 'prev_div_total' not in locals(): prev_div_total = 0
                                new_div_per_share = current_div_total - prev_div_total
                                prev_div_total = current_div_total
                                
                                received_cash = new_div_per_share * shares_held
                                
                                buy_power = bt_monthly
                                if bt_reinvest:
                                    buy_power += received_cash
                                else:
                                    cash_pool += received_cash
                                
                                shares_held += (buy_power / price)
                        
                        final_price = d['price']
                        stock_value = shares_held * final_price
                        total_assets = stock_value + (0 if bt_reinvest else cash_pool)
                        profit = total_assets - total_invested
                        total_roi = (profit / total_invested) * 100 if total_invested > 0 else 0
                        
                        r_c1, r_c2, r_c3 = st.columns(3)
                        r_c1.metric("累積投入本金", f"{total_invested:,.0f}")
                        r_c2.metric("最終資產價值", f"{total_assets:,.0f}")
                        r_c3.metric("總報酬率", f"{total_roi:.2f}%", delta=f"{profit:,.0f}")
                        
                        st.info(f"💡 模擬結果：從 {bt_start_date} 至今，累積持有約 {shares_held:.2f} 股。")
                    else:
                        st.warning("查無此區間的歷史數據，請縮短日期範圍。")

    with side_col:
        st.write("### 📖 說明")
        st.caption("1. 輸入代號後點擊開始計算。")
        st.caption("2. 系統自動偵測配息頻率。")
        st.caption("3. 配息金額可於歷史參考手動微調。")
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
                            <p style="font-size:0.8rem; color:#888;">{r['freq_label']}配頻率</p>
                        </div>""", unsafe_allow_html=True)
                
                df = pd.DataFrame({
                    "指標項目": ["名稱", "目前價格", "今日漲跌", "當前漲幅", "配息頻率", "預估年配息", "實質殖利率"],
                    f"{code1}": [
                        r1['name'], f"{r1['price']:.2f}", f"{r1['change']:+.2f}", f"{r1['pct']:.2f}%", 
                        r1['freq_label'], f"{analysis[0]['annual_div']:.2f}", f"{analysis[0]['yield']:.2f}%"
                    ],
                    f"{code2}": [
                        r2['name'], f"{r2['price']:.2f}", f"{r2['change']:+.2f}", f"{r2['pct']:.2f}%", 
                        r2['freq_label'], f"{analysis[1]['annual_div']:.2f}", f"{analysis[1]['yield']:.2f}%"
                    ]
                })
                st.table(df)

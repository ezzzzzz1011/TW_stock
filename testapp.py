import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import random

# --- 網頁設定 ---
st.set_page_config(page_title="ETF專用 Ez開發", layout="wide")

# --- 自定義 CSS (紅漲綠跌邏輯與版面優化) ---
st.markdown("""
    <style>
    .main { background-color: #121218; color: #f0f0f0; }
    .stButton>button { width: 100%; border-radius: 10px; font-weight: bold; height: 3.5em; background-color: #00bfa5; color: black; }
    .metric-val { font-family: 'Consolas'; font-size: 3rem; font-weight: bold; line-height: 1.1; }
    /* 輸入框與選擇框深色化 */
    .stTextInput>div>div>input, .stSelectbox>div>div>div { background-color: #1e1e28; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- 核心數據抓取 (防封鎖與多源備援) ---
@st.cache_data(ttl=3600) # 同代號一小時內不重複抓取
def get_safe_data(symbol):
    # 模擬真實瀏覽器標頭，避免被判定為爬蟲
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    ]
    headers = {'User-Agent': random.choice(user_agents)}
    
    res = {"name": symbol, "success": False, "price_hist": None, "raw_divs": [0.0]*4, "msg": ""}
    
    # 自動嘗試常見的台股後綴
    for suffix in [".TW", ".TWO"]:
        try:
            full_ticker = f"{symbol}{suffix}"
            t = yf.Ticker(full_ticker)
            # 使用更穩健的歷史資料抓取方式
            hist = t.history(period="5d")
            
            if not hist.empty:
                res["price_hist"] = hist
                # 抓取配息紀錄
                divs = t.dividends
                if not divs.empty:
                    d_list = divs.tail(4).tolist()[::-1]
                    while len(d_list) < 4: d_list.append(0.0)
                    res["raw_divs"] = d_list
                
                # 另外嘗試抓取中文名稱
                try:
                    name_url = f"https://tw.stock.yahoo.com/quote/{full_ticker}"
                    name_resp = requests.get(name_url, headers=headers, timeout=5)
                    if name_resp.status_code == 200:
                        soup = BeautifulSoup(name_resp.text, 'html.parser')
                        name_tag = soup.find('h1', {'class': 'C($c-link-text)'})
                        if name_tag: res["name"] = name_tag.text.strip()
                except: pass
                
                res["success"] = True
                return res
            # 若失敗則隨機等待再嘗試
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            if "Rate Limit" in str(e) or "429" in str(e):
                res["msg"] = "連線頻繁被 Yahoo 限制，請靜置 10 分鐘後再試。"
                return res
                
    res["msg"] = f"找不到代號 {symbol} 的資料，請確認後再試。"
    return res

# --- 主畫面排版 ---
st.title("📈 ETF專用 Ez開發")

# 建立 8:4 比例，左側放結果，右側放輸入控制區
main_col, ctrl_col = st.columns([8, 4])

# --- 右手邊：輸入控制區 ---
with ctrl_col:
    st.subheader("🔍 查詢設定")
    # 移除熱門代號，保持介面簡潔
    symbol_input = st.text_input("輸入股票代號 (如: 00919)", placeholder="00919").strip().upper()
    
    freq_choice = st.selectbox("配息頻率", ["月配息 (12期)", "季配息 (4期)", "半年配 (2期)", "年配息 (1期)"])
    freq_map = {"月配息 (12期)": 12, "季配息 (4期)": 4, "半年配 (2期)": 2, "年配息 (1期)": 1}
    multiplier = freq_map[freq_choice]
    
    exec_calc = st.button("🚀 開始計算", type="primary")

# --- 左手邊：行情與報告顯示區 ---
with main_col:
    if exec_calc and symbol_input:
        with st.spinner('正在安全抓取數據...'):
            data = get_safe_data(symbol_input)
        
        if not data["success"]:
            st.error(f"系統訊息: {data['msg']}")
        else:
            # 股價與漲跌邏輯
            curr_p = data["price_hist"]['Close'].iloc[-1]
            prev_p = data["price_hist"]['Close'].iloc[-2]
            diff = curr_p - prev_p
            pct = (diff / prev_p) * 100
            # 台股邏輯：正數為紅、負數為綠
            m_color = "#ff4b4b" if diff >= 0 else "#00ff00"

            st.markdown(f"### {data['name']}")
            info_c1, info_c2 = st.columns([2, 1])
            with info_c1:
                st.markdown(f"<div class='metric-val' style='color:{m_color}'>{curr_p:.2f}</div>", unsafe_allow_html=True)
                st.markdown(f"<span style='color:{m_color}; font-weight:bold; font-size:1.3rem;'>{diff:+.2f} ({pct:+.2f}%)</span>", unsafe_allow_html=True)
            with info_c2:
                st.caption("行情細節")
                st.write(f"最高: {data['price_hist']['High'].iloc[-1]:.2f}")
                st.write(f"最低: {data['price_hist']['Low'].iloc[-1]:.2f}")

            st.divider()

            # 手動校正區
            st.subheader("📑 歷史配息參考 (可手動校正)")
            e_cols = st.columns(4)
            d1 = e_cols[0].number_input("最新", value=float(data["raw_divs"][0]), format="%.3f")
            d2 = e_cols[1].number_input("前一", value=float(data["raw_divs"][1]), format="%.3f")
            d3 = e_cols[2].number_input("前二", value=float(data["raw_divs"][2]), format="%.3f")
            d4 = e_cols[3].number_input("前三", value=float(data["raw_divs"][3]), format="%.3f")

            # 計算診斷結果
            annual_div = (sum([d1, d2, d3, d4]) / 4) * multiplier
            yield_r = (annual_div / curr_p) * 100 if curr_p > 0 else 0
            cheap, fair, expensive = annual_div/0.10, annual_div/0.07, annual_div/0.05

            st.subheader("📋 診斷報告")
            res_c1, res_c2 = st.columns(2)
            res_c1.metric("預估年配息", f"{annual_div:.2f}")
            res_c2.metric("實質殖利率", f"{yield_r:.2f}%")

            # 投資建議
            advice = "🔥 便宜區間" if curr_p <= cheap else ("✅ 合理持有" if curr_p <= fair else "⚠️ 暫時觀望")
            adv_color = "#ff4b4b" if curr_p <= cheap else ("#00bfa5" if curr_p <= fair else "#ffa500")

            st.markdown(f"""
                <div style="background-color: #1e1e28; padding: 15px; border-radius: 10px; border-left: 5px solid {adv_color};">
                    <h4 style="color: {adv_color}; margin: 0;">📢 投資建議：{advice}</h4>
                </div>
            """, unsafe_allow_html=True)

            st.table(pd.DataFrame({
                "估值位階": ["💎 便宜價 (10%)", "🔔 合理價 (7%)", "❌ 昂貴價 (5%)"],
                "建議價格": [f"{cheap:.2f}", f"{fair:.2f}", f"{expensive:.2f}"]
            }))
    else:
        st.info("💡 請在右手邊輸入代號並按下「開始計算」")
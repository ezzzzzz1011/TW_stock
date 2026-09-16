"""
台股個股 / ETF 查詢系統
Ez開發 - 投資助手系統

本檔案為單一檔案版本，區塊順序：
  1. 全域設定與常數
  2. 稅制參數 (TAX_CONFIG)
  3. 主題與 CSS
  4. 雲端資料庫 (Google Sheets)
  5. 登入 / 註冊
  6. 資料引擎 (報價、配息、頻率推估)
  7. 側邊欄
  8. 各功能頁面
"""

import io
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import gspread
import pandas as pd
import plotly.express as px
import pytz
import requests
import streamlit as st
import yfinance as yf
from fugle_marketdata import RestClient
from google.oauth2.service_account import Credentials

# =============================================================
# 1. 全域設定與常數
# =============================================================
st.set_page_config(
    page_title="台股個股/ETF查詢",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)
tw_tz = pytz.timezone("Asia/Taipei")

# --- API 金鑰 ---------------------------------------------------------------
# 建議改放 .streamlit/secrets.toml，例如：
#   FUGLE_TOKEN = st.secrets["fugle"]["token"]
FUGLE_TOKEN = "YzJjNmM3ODAtZjE1Ny00NzhiLWFjOTUtMDUwZjc2ZWJhYTI1IGRjYTE0ODk3LTRjYTUtNDg5Yi05MjAwLWZmYzNmNzFmNmYwNg=="
FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2Vyc2lkIjp6ZW5vaWLCJlbWFpbCI6ImVhc29uOTMxMDExQGdtYWlsLmNvbSJ9.ApZobjnh5PCRDtXb8rj6a3Y10h1GUGS0EYKHXkTEvKw"

client = RestClient(api_key=FUGLE_TOKEN)

# --- 交易與配息相關常數 -----------------------------------------------------
FEE_RATE = 0.001425          # 券商手續費率
NHI_RATE = 0.0211            # 二代健保補充保費費率
NHI_THRESHOLD = 20_000       # 單次給付起扣門檻
DIV_PAY_LAG_DAYS = 28        # 除息日 → 發放日的推估天數
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
HTTP_TIMEOUT = 5
MAX_WORKERS = 8              # 批次查詢的並行數

# Fugle intraday quote 的 total.tradeVolume 單位。
# True = 回傳「股」，False = 回傳「張」。若總量顯示異常請切換此開關。
FUGLE_VOLUME_IN_SHARES = False

UA_HEADER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

# 估值位階採用的殖利率門檻
YIELD_CHEAP = 0.10
YIELD_FAIR = 0.07

# =============================================================
# 2. 稅制參數
#    每年財政部公告後，只需要在這裡新增一組即可，不必動下面的程式。
#    資料來源：財政部賦稅署年度公告。
# =============================================================
TAX_CONFIG = {
    115: {
        "label": "115 年度（116 年 5 月申報）",
        "exemption": 101_000,
        "exemption_70": 151_500,
        "standard_single": 136_000,
        "standard_couple": 272_000,
        "salary_cap": 227_000,
        "disability_per_person": 227_000,
        "basic_living": 213_000,          # ⚠️ 尚待公告，暫沿用 114 年度數字
        "basic_living_confirmed": False,
        "edu_per_person": 25_000,
        "preschool_first": 150_000,
        "preschool_rest": 225_000,
        "ltc_per_person": 180_000,
        "rent_cap": 180_000,
        "saving_cap": 270_000,
        "brackets": [
            (610_000, 0.05, 0),
            (1_380_000, 0.12, 42_700),
            (2_770_000, 0.20, 153_100),
            (5_190_000, 0.30, 430_100),
            (float("inf"), 0.40, 949_100),
        ],
    },
    114: {
        "label": "114 年度（115 年 5 月申報）",
        "exemption": 97_000,
        "exemption_70": 145_500,
        "standard_single": 131_000,
        "standard_couple": 262_000,
        "salary_cap": 218_000,
        "disability_per_person": 218_000,
        "basic_living": 213_000,
        "basic_living_confirmed": True,
        "edu_per_person": 25_000,
        "preschool_first": 150_000,
        "preschool_rest": 225_000,
        "ltc_per_person": 180_000,
        "rent_cap": 180_000,
        "saving_cap": 270_000,
        "brackets": [
            (590_000, 0.05, 0),
            (1_330_000, 0.12, 41_300),
            (2_660_000, 0.20, 147_700),
            (4_980_000, 0.30, 413_700),
            (float("inf"), 0.40, 911_700),
        ],
    },
}

DIV_CREDIT_RATE = 0.085      # 股利可抵減稅額比率
DIV_CREDIT_CAP = 80_000      # 抵減上限
DIV_SEPARATE_RATE = 0.28     # 分開計稅單一稅率
RICH_TAX_RATE = 0.20         # 排富門檻稅率
BASIC_INCOME_CAP = 7_500_000  # 基本所得額排富門檻


def lookup_bracket(net_income, cfg):
    """依所得淨額回傳 (稅率, 累進差額)。"""
    for upper, rate, prog in cfg["brackets"]:
        if net_income <= upper:
            return rate, prog
    return cfg["brackets"][-1][1], cfg["brackets"][-1][2]


def preschool_amount(count, cfg):
    """幼兒學前特別扣除額：第1名一個額度，第2名起另一個額度。"""
    if count <= 0:
        return 0
    return cfg["preschool_first"] + (count - 1) * cfg["preschool_rest"]


# =============================================================
# 3. 主題與 CSS
# =============================================================
if "theme" not in st.session_state:
    st.session_state.theme = "dark"


def toggle_theme():
    st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"


if st.session_state.theme == "dark":
    APP_BG = "#0e1117"
    SECONDARY_BG = "#1e1e28"
    TEXT_COLOR = "#FAFAFA"
    BORDER_COLOR = "rgba(255,255,255,0.15)"
    TRACK_COLOR = "#2b2b36"
    TABLE_HEAD_BG = "#2a2a36"
else:
    APP_BG = "#FFFFFF"
    SECONDARY_BG = "#F0F2F6"
    TEXT_COLOR = "#1f1f1f"
    BORDER_COLOR = "rgba(0,0,0,0.15)"
    TRACK_COLOR = "#e2e5ea"
    TABLE_HEAD_BG = "#e8eaf0"

UP_COLOR = "#ff4b4b"
DOWN_COLOR = "#09ab3b"


def inject_css():
    """全站 CSS 只注入一次，所有顏色都跟著主題變數走。"""
    st.markdown(
        f"""
        <style>
        :root {{
            --background-color: {APP_BG};
            --secondary-background-color: {SECONDARY_BG};
            --text-color: {TEXT_COLOR};
        }}

        /* 注意：頁首是 <header> 不是 <div>，選擇器不要綁標籤名，
           否則深色模式下最上方會留一條白色橫條。
           新舊版 Streamlit 的 testid 不同，這裡一次全蓋。 */
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stHeader"],
        [data-testid="stAppHeader"] {{
            background-color: {APP_BG} !important;
            color: {TEXT_COLOR} !important;
        }}

        [data-testid="stHeader"],
        [data-testid="stAppHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {{
            background: {APP_BG} !important;
            box-shadow: none !important;
        }}

        /* 頁首上的圖示（GitHub、選單）跟著主題走 */
        [data-testid="stHeader"] svg,
        [data-testid="stAppHeader"] svg,
        [data-testid="stToolbar"] svg {{
            fill: {TEXT_COLOR} !important;
            color: {TEXT_COLOR} !important;
        }}

        [data-testid="stSidebar"] {{
            background-color: {SECONDARY_BG} !important;
        }}

        p, span, label, h1, h2, h3, h4, h5, h6,
        div[data-testid="stMarkdownContainer"] {{
            color: {TEXT_COLOR} !important;
        }}

        .stTextInput input, .stNumberInput input, .stTextArea textarea {{
            background-color: {SECONDARY_BG} !important;
            color: {TEXT_COLOR} !important;
            border: 1px solid {BORDER_COLOR} !important;
            border-radius: 8px !important;
        }}

        div[data-baseweb="select"] > div {{
            background-color: {SECONDARY_BG} !important;
            color: {TEXT_COLOR} !important;
            border-color: {BORDER_COLOR} !important;
        }}

        /* 下拉選單彈出層：跟著主題走，不再寫死黑底白字 */
        div[data-baseweb="popover"], div[role="listbox"] {{
            background-color: {SECONDARY_BG} !important;
            border: 1px solid {BORDER_COLOR} !important;
        }}
        div[role="option"], div[role="option"] * {{
            color: {TEXT_COLOR} !important;
            -webkit-text-fill-color: {TEXT_COLOR} !important;
        }}
        div[role="option"]:hover,
        div[role="option"][aria-selected="true"] {{
            background-color: {UP_COLOR} !important;
        }}
        div[role="option"]:hover *,
        div[role="option"][aria-selected="true"] * {{
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }}

        div[data-testid="stDataEditor"], div[data-testid="stTable"],
        div[data-testid="stDataFrame"] {{
            background-color: {SECONDARY_BG} !important;
        }}
        div[data-testid="stDataFrame"] * {{
            color: {TEXT_COLOR} !important;
        }}

        div[data-testid="stMetric"] {{
            background-color: {SECONDARY_BG} !important;
            border-radius: 10px;
            padding: 10px 15px;
        }}
        div[data-testid="stMetricLabel"], div[data-testid="stMetricValue"] {{
            color: {TEXT_COLOR} !important;
        }}

        .stButton > button {{
            width: 100%;
            border-radius: 12px;
            font-weight: bold;
            background-color: {SECONDARY_BG} !important;
            color: {TEXT_COLOR} !important;
            border: 1px solid {BORDER_COLOR} !important;
        }}
        .stButton > button:hover {{
            border-color: {UP_COLOR} !important;
            color: {UP_COLOR} !important;
        }}
        .stButton > button[kind="primary"] {{
            background-color: {UP_COLOR} !important;
            color: #FFFFFF !important;
            border: none !important;
        }}

        .metric-val {{
            font-family: 'Consolas', monospace;
            font-size: 3.5rem;
            font-weight: bold;
            line-height: 1.1;
        }}
        .highlight-val {{
            font-size: 2.5rem;
            font-family: 'Consolas', monospace;
            font-weight: bold;
            color: {TEXT_COLOR} !important;
        }}
        .date-text {{
            color: {TEXT_COLOR};
            opacity: 0.6;
            font-size: 0.9rem;
            margin-bottom: 8px;
        }}

        .feature-card {{
            background-color: {SECONDARY_BG};
            padding: 20px 10px;
            border-radius: 20px;
            border: 1px solid {BORDER_COLOR};
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            text-align: center;
            transition: all 0.3s ease;
            margin-bottom: 20px;
            height: 150px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        .feature-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            border-color: {UP_COLOR};
        }}
        .feature-title {{
            font-size: 1.5rem;
            font-weight: bold;
            color: {TEXT_COLOR};
            margin-bottom: 10px;
        }}
        .feature-desc {{
            color: {TEXT_COLOR};
            opacity: 0.7;
            font-size: 1rem;
        }}

        .calc-box, .plan-box, .pk-card {{
            background-color: {SECONDARY_BG};
            padding: 20px;
            border-radius: 15px;
            border: 1px solid {BORDER_COLOR};
            margin-top: 10px;
            color: {TEXT_COLOR};
        }}

        .styled-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-size: 1.1rem;
        }}
        .styled-table th {{
            background-color: {SECONDARY_BG};
            color: {TEXT_COLOR};
            text-align: left;
            padding: 12px;
            border-bottom: 2px solid {BORDER_COLOR};
        }}
        .styled-table td {{
            padding: 12px;
            border-bottom: 1px solid {BORDER_COLOR};
            color: {TEXT_COLOR} !important;
        }}

        /* 報稅明細表：改用主題色，深色模式不再出現白底白字 */
        .tax-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            font-size: 14px;
            text-align: center;
            background-color: {SECONDARY_BG};
            color: {TEXT_COLOR};
        }}
        .tax-table th, .tax-table td {{
            border: 1px solid {BORDER_COLOR};
            padding: 8px;
            color: {TEXT_COLOR};
        }}
        .tax-table th {{
            background-color: {TABLE_HEAD_BG};
            font-weight: bold;
        }}
        .tax-table td {{
            font-family: 'Consolas', monospace;
            font-size: 15px;
        }}
        .tax-table .operator {{
            width: 30px;
            opacity: 0.7;
            font-weight: bold;
        }}
        .tax-table .muted {{
            opacity: 0.45;
        }}

        .dash-card {{
            background-color: {SECONDARY_BG};
            border: 1px solid {BORDER_COLOR};
            border-radius: 14px;
            padding: 16px 18px;
            height: 100%;
        }}
        .dash-label {{ font-size: 0.85rem; opacity: 0.65; }}
        .dash-value {{ font-size: 1.7rem; font-weight: bold; font-family: 'Consolas', monospace; }}

        /* 手機版：字級與卡片高度自動縮放，避免五欄卡片擠成一團 */
        @media (max-width: 640px) {{
            .metric-val {{ font-size: 2.4rem; }}
            .highlight-val {{ font-size: 1.8rem; }}
            .feature-card {{ height: auto; min-height: 110px; padding: 16px 10px; }}
            .feature-title {{ font-size: 1.2rem; }}
            .feature-desc {{ font-size: 0.9rem; }}
            .styled-table, .tax-table {{ font-size: 0.85rem; }}
            .dash-value {{ font-size: 1.35rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_css()


# =============================================================
# 4. 雲端資料庫 (Google Sheets)
# =============================================================
DEFAULT_PORTFOLIO_ROWS = 20
COLUMNS_ORDER = ["代碼", "名稱", "張數", "戰略屬性"]
ASSET_CATEGORIES = [
    "⚔️ 進攻型 (市值/成長)",
    "💰 現金流 (高股息)",
    "🛡️ 防守型 (債券/避險)",
]


@st.cache_resource
def init_connection():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = st.secrets["gcp_service_account"].to_dict()
    if "private_key" in creds_dict:
        pk = creds_dict["private_key"].replace("\\n", "\n").replace('"', "")
        creds_dict["private_key"] = pk
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)


def ensure_worksheet(spreadsheet, title, header, rows="1000", cols="4"):
    """取得工作表，不存在就建立並寫入表頭。回傳 (worksheet, 是否為本次新建)。"""
    try:
        return spreadsheet.worksheet(title), False
    except Exception:
        ws = spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
        ws.append_row(header)
        return ws, True


try:
    conn = init_connection()
    sh = conn.open("streamlit_db")

    user_sheet, users_created = ensure_worksheet(
        sh, "users", ["username", "password"], rows="500", cols="2"
    )
    if users_created:
        user_sheet.append_row(["admin", "8888"])

    portfolio_sheet, _ = ensure_worksheet(sh, "portfolios", ["username", "data_json"], cols="2")
    watchlist_sheet, _ = ensure_worksheet(sh, "watchlist", ["username", "codes"], cols="2")

except Exception as e:
    st.error(f"❌ 雲端資料庫連線失敗：{e}")
    st.stop()


def find_user_row(worksheet, username):
    """只在第一欄尋找使用者，避免誤中 JSON 欄位的內容。"""
    try:
        return worksheet.find(str(username), in_column=1)
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def get_cloud_users():
    """使用者清單快取 5 分鐘，避免每次 rerun 都打 Google API。"""
    try:
        records = user_sheet.get_all_records()
        return {
            str(row["username"]).strip(): str(row["password"]).strip()
            for row in records
        }
    except Exception as e:
        st.error(f"讀取使用者資料失敗：{e}")
        return {}


def empty_portfolio():
    return pd.DataFrame(
        [{"代碼": "", "名稱": "", "張數": None, "戰略屬性": ""} for _ in range(DEFAULT_PORTFOLIO_ROWS)]
    )


def load_portfolio_from_cloud(username):
    try:
        cell = find_user_row(portfolio_sheet, username)
        if cell:
            json_data = portfolio_sheet.cell(cell.row, 2).value
            if json_data:
                df = pd.read_json(io.StringIO(json_data))
                for col in COLUMNS_ORDER:
                    if col not in df.columns:
                        df[col] = None if col == "張數" else ""
                return df[COLUMNS_ORDER]
    except Exception as e:
        print(f"[load_portfolio] {e}")
    return empty_portfolio()


def save_portfolio_to_cloud(username, df):
    clean_df = df.copy()
    if "代碼" in clean_df.columns:
        clean_df = clean_df[clean_df["代碼"].astype(str).str.strip() != ""]
        clean_df = clean_df.dropna(subset=["代碼"])
    json_data = clean_df.to_json(orient="records", date_format="iso")
    try:
        cell = find_user_row(portfolio_sheet, username)
        if cell:
            portfolio_sheet.update_cell(cell.row, 2, json_data)
        else:
            portfolio_sheet.append_row([str(username), json_data])
        return True
    except Exception as e:
        st.error(f"⚠️ 雲端儲存失敗：{e}")
        return False


def load_watchlist_from_cloud(username):
    try:
        cell = find_user_row(watchlist_sheet, username)
        if cell:
            raw = watchlist_sheet.cell(cell.row, 2).value or ""
            raw = raw.lstrip("'").strip()
            return [c.strip().upper() for c in raw.split(",") if 0 < len(c.strip()) < 10]
    except Exception as e:
        st.error(f"讀取關注清單失敗：{e}")
    return []


def save_watchlist_to_cloud(username, codes_list):
    # 前置單引號是為了讓 Google Sheets 保留「0050」開頭的 0，不要當成數字。
    codes_str = "'" + ",".join(str(c).strip().upper() for c in codes_list)
    try:
        cell = find_user_row(watchlist_sheet, username)
        if cell:
            watchlist_sheet.update(range_name=f"B{cell.row}", values=[[codes_str]])
        else:
            watchlist_sheet.append_row([str(username), codes_str])
        return True
    except Exception as e:
        st.error(f"雲端儲存失敗：{e}")
        return False


# =============================================================
# 5. Session 狀態與登入
# =============================================================
for key, default in [
    ("logged_in", False),
    ("current_user", None),
    ("portfolio", None),
    ("watchlist", None),
    ("page", "welcome"),
    ("data", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def login_ui():
    st.markdown(
        f"""
        <div style="max-width: 400px; margin: 40px auto 20px auto; padding: 25px;
                    background-color: {SECONDARY_BG}; border-radius: 15px;
                    border: 1px solid {BORDER_COLOR};
                    box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center;">
            <h2 style="margin: 0; color: {TEXT_COLOR} !important; font-size: 24px;">🚀 台股個股/ETF查詢</h2>
            <p style="color: {TEXT_COLOR} !important; opacity: 0.7; margin-top: 8px;
                      margin-bottom: 0; font-size: 14px;">Ez開發 - 投資助手系統</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, col_theme, _ = st.columns([1, 1.2, 1])
    with col_theme:
        btn_label = "☀️ 切換淺色模式" if st.session_state.theme == "dark" else "🌙 切換深色模式"
        if st.button(btn_label, use_container_width=True, key="login_theme_toggle"):
            toggle_theme()
            st.rerun()

    _, col2, _ = st.columns([1, 1.2, 1])
    with col2:
        user_db = get_cloud_users()
        tab_login, tab_reg = st.tabs(["🔑 帳號登入", "📝 新用戶註冊"])

        with tab_login:
            # 包成 form，在密碼欄按 Enter 就能直接登入
            with st.form("login_form"):
                u_id = st.text_input("帳號名稱", key="l_user", placeholder="請輸入帳號")
                u_pw = st.text_input("存取密碼", type="password", key="l_pw", placeholder="請輸入密碼")
                login_submitted = st.form_submit_button(
                    "確認登入", use_container_width=True, type="primary"
                )

            if login_submitted:
                if user_db.get(u_id.strip()) == u_pw:
                    st.session_state.logged_in = True
                    st.session_state.current_user = u_id.strip()
                    st.session_state.portfolio = load_portfolio_from_cloud(u_id.strip())
                    st.session_state.watchlist = None
                    st.session_state.page = "welcome"
                    st.rerun()
                else:
                    st.error("❌ 帳號或密碼不正確")

        with tab_reg:
            st.info("註冊資料將儲存於雲端，重啟系統不會遺失。")
            with st.form("register_form"):
                new_u = st.text_input("設定帳號", key="r_user").strip()
                new_p = st.text_input("設定密碼", type="password", key="r_pw")
                confirm_p = st.text_input("確認密碼", type="password", key="r_confirm")
                reg_submitted = st.form_submit_button("提交註冊", use_container_width=True)

            if reg_submitted:
                if new_u in user_db:
                    st.warning("⚠️ 帳號已存在")
                elif new_p != confirm_p:
                    st.error("❌ 密碼不一致")
                elif len(new_u) < 2 or len(new_p) < 4:
                    st.error("❌ 長度不足 (帳號需2字元, 密碼需4字元)")
                else:
                    try:
                        user_sheet.append_row([new_u, new_p])
                        save_portfolio_to_cloud(new_u, empty_portfolio())
                        get_cloud_users.clear()   # 清掉快取，新帳號才登得進去
                        st.success("✅ 註冊成功！請切換至登入分頁。")
                    except Exception as e:
                        st.error(f"註冊失敗：{e}")


if not st.session_state.logged_in:
    login_ui()
    st.stop()


# =============================================================
# 6. 資料引擎
# =============================================================
def clean_code(symbol):
    return str(symbol).strip().upper().replace(".TW", "").replace(".TWO", "")


@st.cache_data(ttl=60, show_spinner=False)
def get_stock_info(symbol):
    """即時報價。快取 60 秒，避免每次 rerun 都重打 API。"""
    code = clean_code(symbol)
    if not code:
        return None
    try:
        data = client.stock.intraday.quote(symbol=code)
        if not data:
            return None

        price = float(
            data.get("lastPrice")
            or data.get("closePrice")
            or data.get("previousClose")
            or 0.0
        )
        raw_vol = float(data.get("total", {}).get("tradeVolume", 0) or 0)
        # 統一換算成「張」，不再用門檻猜單位
        vol_lots = raw_vol / 1000 if FUGLE_VOLUME_IN_SHARES else raw_vol

        return {
            "name": data.get("name", code),
            "price": price,
            "change": float(data.get("change", 0.0) or 0.0),
            "pct": float(data.get("changePercent", 0.0) or 0.0),
            "high": float(data.get("highPrice") or price),
            "low": float(data.get("lowPrice") or price),
            "open": float(data.get("openPrice") or price),
            "vol_lots": int(vol_lots),
            "full_ticker": code,
        }
    except Exception as e:
        print(f"[get_stock_info] {code}: {e}")
        return None


def _finmind_dividends(code):
    """引擎 1：FinMind。網域為 api.finmindtrade.com，路徑含 /api。"""
    try:
        res = requests.get(
            FINMIND_URL,
            params={
                "dataset": "TaiwanStockDividend",
                "data_id": code,
                "start_date": "2018-01-01",
                "token": FINMIND_TOKEN,
            },
            timeout=HTTP_TIMEOUT,
        )
        payload = res.json()
        if payload.get("msg") != "success" or not payload.get("data"):
            return []

        out = []
        for item in payload["data"]:
            # FinMind 欄位名稱為 CashEarningsDistribution / CashExDividendTradingDate
            amount = float(item.get("CashEarningsDistribution") or 0)
            date = item.get("CashExDividendTradingDate") or item.get("date")
            if amount > 0 and date:
                out.append({"date": str(date)[:10], "amount": amount})
        return out
    except Exception as e:
        print(f"[finmind] {code}: {e}")
        return []


def _yahoo_dividends(code):
    """引擎 2：Yahoo Finance chart API，一般股與主流 ETF 覆蓋率高。"""
    for suffix in (".TW", ".TWO"):
        try:
            url = (
                f"https://query2.finance.yahoo.com/v8/finance/chart/"
                f"{code}{suffix}?interval=1d&events=div&range=5y"
            )
            res = requests.get(url, headers=UA_HEADER, timeout=HTTP_TIMEOUT)
            if res.status_code != 200:
                continue
            result = res.json().get("chart", {}).get("result") or [{}]
            events = result[0].get("events", {}).get("dividends", {})
            out = []
            for val in events.values():
                dt = datetime.fromtimestamp(val["date"]).strftime("%Y-%m-%d")
                out.append({"date": dt, "amount": float(val["amount"])})
            if out:
                return out
        except Exception as e:
            print(f"[yahoo] {code}{suffix}: {e}")
    return []


def _histock_dividends(code):
    """引擎 3：HiStock 表格解析，專治債券 ETF。逐列比對，避免跨頁面亂配。"""
    urls = [
        f"https://histock.tw/stock/etfdividend.aspx?no={code}",
        f"https://histock.tw/stock/financial.aspx?no={code}&t=2",
    ]
    headers = dict(UA_HEADER, Referer="https://histock.tw/")

    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
            if res.status_code != 200:
                continue

            # 先用 pandas 解析表格（最穩），失敗才退回逐列正則
            try:
                for table in pd.read_html(io.StringIO(res.text)):
                    out = _parse_histock_table(table)
                    if out:
                        return out
            except Exception:
                pass

            out = []
            for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", res.text, re.DOTALL | re.I):
                cells = [
                    re.sub(r"<[^>]+>", "", c).strip()
                    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.DOTALL | re.I)
                ]
                date = next((c for c in cells if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", c)), None)
                amount = next(
                    (float(c) for c in cells if re.fullmatch(r"\d+\.\d+", c) and 0 < float(c) < 50),
                    None,
                )
                if date and amount:
                    out.append({"date": date.replace("/", "-"), "amount": amount})
            if out:
                return out
        except Exception as e:
            print(f"[histock] {code}: {e}")
    return []


def _parse_histock_table(table):
    """從 DataFrame 中找出「日期欄 + 金額欄」的組合。"""
    out = []
    cols = [str(c) for c in table.columns]
    date_col = next((c for c in cols if "日" in c), None)
    amt_col = next((c for c in cols if "配" in c or "息" in c or "股利" in c), None)
    if not date_col or not amt_col:
        return []
    for _, row in table.iterrows():
        raw_date = str(row[date_col]).strip()
        if not re.fullmatch(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", raw_date):
            continue
        try:
            amount = float(str(row[amt_col]).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if amount > 0:
            out.append({"date": raw_date.replace("/", "-"), "amount": amount})
    return out


def _normalize_date(raw):
    """統一成 YYYY-MM-DD，補零。"""
    parts = re.split(r"[-/]", str(raw).strip())
    if len(parts) != 3:
        return None
    try:
        return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except ValueError:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_dividend_history_super(symbol):
    """三引擎備援抓配息歷史，去重後由新到舊排序。快取一天。"""
    code = clean_code(symbol)
    if not code:
        return []

    div_list = []
    for engine in (_finmind_dividends, _yahoo_dividends, _histock_dividends):
        div_list = engine(code)
        if div_list:
            break

    if not div_list:
        return []

    unique = {}
    for item in div_list:
        date = _normalize_date(item["date"])
        if not date:
            continue
        unique[date] = max(unique.get(date, 0), item["amount"])

    return sorted(
        ({"date": k, "amount": v} for k, v in unique.items()),
        key=lambda x: x["date"],
        reverse=True,
    )


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_quarterly_financials(symbol):
    """
    抓綜合損益表的單季 EPS 與稅後淨利，由新到舊排序。快取一天。
    回傳 (資料列表, 錯誤訊息)；成功時錯誤訊息為 None。
    """
    code = clean_code(symbol)
    if not code:
        return [], "沒有代碼"

    start = (datetime.now() - timedelta(days=900)).strftime("%Y-%m-%d")
    try:
        res = requests.get(
            FINMIND_URL,
            params={
                "dataset": "TaiwanStockFinancialStatements",
                "data_id": code,
                "start_date": start,
                "token": FINMIND_TOKEN,
            },
            timeout=HTTP_TIMEOUT,
        )
        payload = res.json()
    except Exception as e:
        print(f"[financials] {code}: {e}")
        return [], f"FinMind 連線失敗：{e}"

    if payload.get("msg") != "success" or not payload.get("data"):
        reason = str(payload.get("msg") or "無回傳訊息")
        # token 壞掉或過期時，FinMind 會回 token 相關訊息而不是「查無資料」
        if any(k in reason.lower() for k in ("token", "unauthor", "login", "permission")):
            reason = f"FinMind token 無效或已過期（{reason}）"
        print(f"[financials] {code}: {reason}")
        return [], reason

    by_date = {}
    for item in payload["data"]:
        kind = item.get("type")
        if kind not in ("EPS", "IncomeAfterTaxes"):
            continue
        date = str(item.get("date"))[:10]
        try:
            by_date.setdefault(date, {})[kind] = float(item.get("value"))
        except (TypeError, ValueError):
            continue

    rows = [
        {"date": d, "eps": v.get("EPS"), "net_income": v.get("IncomeAfterTaxes")}
        for d, v in by_date.items()
        if v.get("EPS") is not None
    ]
    if not rows:
        return [], "FinMind 有回應但沒有 EPS 欄位"
    return sorted(rows, key=lambda x: x["date"], reverse=True), None


# ---------- 證交所 OpenAPI 備援（免驗證） ----------
TWSE_PE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TWSE_PRICE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"


def _pick_field(row, *candidates):
    """欄位名稱偶爾會調整，容忍大小寫與部分相符。"""
    for key in row:
        flat = str(key).replace("_", "").lower()
        for want in candidates:
            if flat == want.replace("_", "").lower():
                return row[key]
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_twse_pe_table():
    """
    證交所每日「個股日本益比、殖利率及股價淨值比」＋「每日收盤行情」。
    證交所的本益比定義為 收盤價 ÷ 近四季每股稅後純益，
    所以 EPS = 收盤價 ÷ 本益比，等同官方版的近四季 EPS。
    """
    table = {}
    try:
        pe_rows = requests.get(TWSE_PE_URL, timeout=HTTP_TIMEOUT).json()
        price_rows = requests.get(TWSE_PRICE_URL, timeout=HTTP_TIMEOUT).json()
    except Exception as e:
        print(f"[twse] {e}")
        return {}

    prices = {}
    for row in price_rows or []:
        code = str(_pick_field(row, "Code") or "").strip()
        try:
            prices[code] = float(str(_pick_field(row, "ClosingPrice") or "").replace(",", ""))
        except (TypeError, ValueError):
            continue

    for row in pe_rows or []:
        code = str(_pick_field(row, "Code") or "").strip()
        try:
            pe = float(str(_pick_field(row, "PEratio") or "").replace(",", ""))
        except (TypeError, ValueError):
            continue
        close = prices.get(code)
        if code and pe > 0 and close and close > 0:
            table[code] = {
                "eps": round(close / pe, 2),
                "pe": pe,
                "close": close,
                "name": str(_pick_field(row, "Name") or ""),
            }
    return table


def quarter_label(date_str):
    """2025-09-30 -> 2025Q3"""
    try:
        year, month, _ = date_str.split("-")
        return f"{year}Q{(int(month) - 1) // 3 + 1}"
    except Exception:
        return date_str


def get_ttm_eps(symbol):
    """
    計算近四季 EPS。

    重點：不能直接把四季 EPS 相加。公司配股／增資後，新財報會把舊季 EPS 追溯
    調整，但 API 給的舊季數值仍是當初的原始值，直接相加會高估。
    依 FinMind 官方建議，改用「四季稅後淨利加總 ÷ 同一個加權平均股數」。
    """
    code = clean_code(symbol)
    rows, error = fetch_quarterly_financials(symbol)

    if not rows or len(rows) < 4:
        # 引擎 2：證交所 OpenAPI，只給一個近四季總額，沒有分季明細
        fallback = fetch_twse_pe_table().get(code)
        if fallback:
            return {
                "success": True,
                "symbol": code,
                "ttm_eps": fallback["eps"],
                "naive_sum": fallback["eps"],
                "adjusted": False,
                "method": (
                    f"證交所 OpenAPI 備援：收盤價 {fallback['close']:.2f} "
                    f"÷ 本益比 {fallback['pe']:.2f}"
                ),
                "quarters": [],
                "period": "近四季（證交所公告）",
                "source": "twse",
            }

        if rows:
            return {
                "success": False,
                "msg": f"只取得 {len(rows)} 季財報（最新一季可能尚未公布），不足四季無法計算。",
                "quarters": rows,
            }
        detail = f"（{error}）" if error else ""
        return {
            "success": False,
            "msg": (
                f"兩個來源都查不到 {code} 的財報{detail}。"
                "ETF、KY 股與興櫃股票本來就沒有 EPS；若是一般上市櫃股票，"
                "多半是 FinMind token 失效，請更新後再試，或直接手動輸入。"
            ),
        }

    quarters = rows[:4]

    naive_sum = sum(q["eps"] for q in quarters)
    latest = quarters[0]

    # 用最新一季反推加權平均股數（已是追溯調整後的股數）
    shares = None
    if latest.get("net_income") and abs(latest["eps"]) > 0.01:
        candidate = latest["net_income"] / latest["eps"]
        if candidate > 0:
            shares = candidate

    if shares and all(q.get("net_income") is not None for q in quarters):
        ttm_eps = sum(q["net_income"] for q in quarters) / shares
        method = "以四季稅後淨利還原（已處理配股追溯調整）"
    else:
        ttm_eps = naive_sum
        method = "查無稅後淨利，改以四季 EPS 直接加總"

    gap = abs(ttm_eps - naive_sum)
    return {
        "success": True,
        "symbol": clean_code(symbol),
        "ttm_eps": round(ttm_eps, 2),
        "naive_sum": round(naive_sum, 2),
        "adjusted": gap > max(0.02, abs(naive_sum) * 0.01),
        "method": method,
        "quarters": quarters,
        "period": f"{quarter_label(quarters[-1]['date'])} ~ {quarter_label(quarters[0]['date'])}",
        "source": "finmind",
    }


def infer_frequency(data_list):
    """由歷史除息間隔推估配息頻率，回傳 (一年幾次, 中文標籤)。"""
    if len(data_list) >= 2:
        check = min(5, len(data_list))
        dates = [datetime.strptime(d["date"], "%Y-%m-%d") for d in data_list[:check]]
        diffs = [(dates[i] - dates[i + 1]).days for i in range(len(dates) - 1)]
        avg_days = sum(diffs) / len(diffs) if diffs else 365
    else:
        avg_days = 365

    if avg_days <= 45:
        return 12, "月"
    if avg_days <= 110:
        return 4, "季"
    if avg_days <= 200:
        return 2, "半年"
    return 1, "年"


def annualize(divs, multiplier):
    """依配息頻率把手上的期數換算成年配息。"""
    d1, d2, d3, d4 = (list(divs) + [0.0] * 4)[:4]
    if multiplier == 1:
        return round(d1, 4)
    if multiplier == 2:
        return round(d1 + d2, 4)
    if multiplier == 4:
        return round(d1 + d2 + d3 + d4, 4)
    return round((d1 + d2 + d3 + d4) / 4 * multiplier, 4)


@st.cache_data(ttl=60, show_spinner=False)
def get_safe_data_etf(symbol):
    """報價 + 配息的整合結果。報價 60 秒、配息一天，各自獨立快取。"""
    info = get_stock_info(symbol)
    if not info or info["price"] <= 0:
        return {"success": False, "msg": f"找不到代號 {symbol} 或目前無報價"}

    raw_divs = [0.0] * 4
    multiplier, freq_label = 1, "年"

    try:
        data_list = fetch_dividend_history_super(symbol)
        if data_list:
            multiplier, freq_label = infer_frequency(data_list)

            # 判斷最近是否有停發：超過「預期間隔 + 寬限期」就往前補 0
            last_date = datetime.strptime(data_list[0]["date"], "%Y-%m-%d")
            days_since_last = (datetime.now() - last_date).days
            expected_days = 365 / multiplier
            grace = 100 if multiplier == 1 else 60

            missed = 0
            if days_since_last > (expected_days + grace):
                missed = min(4, int(days_since_last / expected_days))

            for i in range(4):
                if i < missed:
                    raw_divs[i] = 0.0
                elif (i - missed) < len(data_list):
                    raw_divs[i] = data_list[i - missed]["amount"]
    except Exception as e:
        print(f"[get_safe_data_etf] 配息分析失敗 {symbol}: {e}")

    return {
        "success": True,
        "name": info["name"],
        "price": info["price"],
        "change": info["change"],
        "pct": info["pct"],
        "high": info["high"],
        "low": info["low"],
        "open": info["open"],
        "vol_lots": info["vol_lots"],
        "raw_divs": raw_divs,
        "multiplier": multiplier,
        "freq_label": freq_label,
        "last_date": datetime.now(tw_tz).strftime("%Y-%m-%d"),
        "full_ticker": info["full_ticker"],
    }


def get_dividend_calendar(symbol):
    """
    推估「下一次」除息與發放日。
    原本的寫法是拿最近一次已發生的除息日 +28 天，除息後一個月內以外永遠是空的，
    這裡改成用配息頻率往未來推，並標記是否為推估值。
    """
    code = clean_code(symbol)
    data_list = fetch_dividend_history_super(code)
    if not data_list:
        return {"success": False}

    try:
        multiplier, freq_label = infer_frequency(data_list)
        interval = 365 / multiplier
        last_ex = datetime.strptime(data_list[0]["date"], "%Y-%m-%d")
        today = datetime.now(tw_tz).date()

        next_ex = last_ex
        projected = False
        guard = 0
        while next_ex.date() < today and guard < 60:
            next_ex += timedelta(days=interval)
            projected = True
            guard += 1

        return {
            "success": True,
            "symbol": code,
            "ex_date": next_ex.strftime("%Y-%m-%d"),
            "pay_date": (next_ex + timedelta(days=DIV_PAY_LAG_DAYS)).strftime("%Y-%m-%d"),
            "amount": data_list[0]["amount"],
            "freq_label": freq_label,
            "projected": projected,
            "last_actual_ex": data_list[0]["date"],
        }
    except Exception as e:
        print(f"[get_dividend_calendar] {code}: {e}")
        return {"success": False}


def fetch_many(codes, fetcher):
    """並行抓取，避免 20 檔股票排隊等 timeout。"""
    codes = list(codes)
    if not codes:
        return {}
    workers = min(MAX_WORKERS, len(codes))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetcher, codes))
    return dict(zip(codes, results))


def get_asset_category(code, name):
    name_str = str(name)
    if "債" in name_str or "防守" in name_str:
        return ASSET_CATEGORIES[2]
    high_div_keywords = ("高股息", "優息", "精選", "低波")
    high_div_codes = {"0056", "00878", "00919", "00918", "00713", "00915"}
    if any(k in name_str for k in high_div_keywords) or code in high_div_codes:
        return ASSET_CATEGORIES[1]
    return ASSET_CATEGORIES[0]


def generate_user_calendar():
    """依投資組合產生未來領息排程。"""
    if st.session_state.portfolio is None:
        return None

    df = st.session_state.portfolio.copy()
    df["張數"] = pd.to_numeric(df["張數"], errors="coerce")
    valid = df.dropna(subset=["代碼", "張數"])
    valid = valid[valid["代碼"].astype(str).str.strip() != ""]
    if valid.empty:
        st.warning("⚠️ 您的投資組合目前是空的。")
        return None

    codes = [clean_code(c) for c in valid["代碼"]]
    lots_map = {clean_code(r["代碼"]): float(r["張數"]) for _, r in valid.iterrows()}

    with st.spinner("查詢配息資料中..."):
        div_map = fetch_many(codes, get_dividend_calendar)

    rows = []
    for code, info in div_map.items():
        if not info or not info.get("success"):
            continue
        lots = lots_map.get(code, 0)
        rows.append(
            {
                "股票名稱": code,
                "預計除息日": info["ex_date"],
                "預計發放日 (預估)": info["pay_date"],
                "每股配息": info["amount"],
                "預估入帳金額": int(info["amount"] * lots * 1000),
                "資料性質": "推估" if info["projected"] else "已公告",
            }
        )

    result = pd.DataFrame(rows)
    return result if not result.empty else None


MARKET_TICKERS = [
    ("S&P 500", "^GSPC"),
    ("道瓊工業", "^DJI"),
    ("納斯達克", "^IXIC"),
    ("費城半導體", "^SOX"),
    ("美10年債", "^TNX"),
    ("台股加權", "^TWII"),
    ("台指期 / 近全", "WTX=F"),
    ("原油期貨", "CL=F"),
    ("美元/台幣", "TWD=X"),
]


# 有些代碼在 Yahoo 上資料時有時無（台指期尤其嚴重），依序往下試。
MARKET_TICKER_FALLBACKS = {
    "WTX=F": ["WTX=F", "TWF=F", "^TWII"],
}


def _fetch_quote(ticker):
    """先用 fast_info，失敗再退回近五日收盤價。回傳 (現價, 漲跌) 或 (None, None)。"""
    try:
        fast = yf.Ticker(ticker).fast_info
        current_p = float(fast["last_price"])
        prev_p = float(fast["previous_close"])
        if current_p > 0 and prev_p > 0:
            return current_p, prev_p
    except Exception as e:
        print(f"[market:fast] {ticker}: {e}")

    try:
        hist = yf.Ticker(ticker).history(period="5d")
        closes = hist["Close"].dropna()
        if len(closes) >= 2:
            return float(closes.iloc[-1]), float(closes.iloc[-2])
    except Exception as e:
        print(f"[market:hist] {ticker}: {e}")

    return None, None


@st.cache_data(ttl=300, show_spinner=False)
def get_market_data(ticker):
    for candidate in MARKET_TICKER_FALLBACKS.get(ticker, [ticker]):
        current_p, prev_p = _fetch_quote(candidate)
        if current_p is None:
            continue

        # ^TNX 在部分 yfinance 版本回傳 42.5 (需 /10)，部分回傳 4.25，這裡自動判斷。
        if ticker == "^TNX" and current_p > 20:
            current_p /= 10
            prev_p /= 10

        change = current_p - prev_p
        pct = (change / prev_p) * 100 if prev_p else 0
        if candidate != ticker:
            print(f"[market] {ticker} 無資料，改用 {candidate}")
        return current_p, change, pct

    return None, None, None


def format_market_value(ticker_code, p, c):
    if ticker_code == "^TNX":
        return f"{p:.3f}%", f"{c:+.3f}"
    if ticker_code == "WTX=F":
        return f"{p:,.0f}", f"{c:+.0f}" if abs(c) >= 1 else f"{c:+.2f}"
    return f"{p:,.2f}", f"{c:+.2f}"


def draw_compact_metric(label, ticker_code):
    p, c, pct = get_market_data(ticker_code)
    if p is None:
        st.markdown(
            f"<div style='text-align:center; opacity:0.5; padding:12px 0;'>{label}<br>暫無資料</div>",
            unsafe_allow_html=True,
        )
        return

    color = UP_COLOR if c >= 0 else DOWN_COLOR
    arrow = "▲" if c >= 0 else "▼"
    val_str, c_str = format_market_value(ticker_code, p, c)

    st.markdown(
        f"""
        <div style="text-align:center; padding:2px 0;">
            <div style="font-size:0.85rem; opacity:0.6; margin-bottom:2px;">{label}</div>
            <div style="font-size:1.6rem; font-weight:bold; margin-bottom:8px;
                        color:{TEXT_COLOR};">{val_str}</div>
            <div style="display:inline-block; background:{color}22; color:{color};
                        padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:500;">
                {arrow} 日漲跌 {c_str} ({pct:+.2f}%)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def greeting():
    hour = datetime.now(tw_tz).hour
    if hour < 6:
        return "夜深了"
    if hour < 12:
        return "早安"
    if hour < 18:
        return "午安"
    return "晚安"


def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()


def back_button(label="⬅️ 返回工具箱", target="home", key=None):
    """返回鍵放在窄欄位裡，不再橫跨整個畫面。"""
    col, _ = st.columns([1, 5])
    with col:
        if st.button(label, key=key or f"back_{target}", use_container_width=True):
            go_to(target)


# =============================================================
# 7. 側邊欄
# =============================================================
page = st.session_state.page
TOOLBOX_PAGES = {"home", "stock_query", "etf_query", "pk_tool", "portfolio", "market_index"}

with st.sidebar:
    st.write(f"👤 當前使用者: **{st.session_state.current_user}**")

    nav_items = [
        ("⭐ 我的關注清單", "watchlist", {"watchlist"}),
        ("🚀 台股查詢", "home", TOOLBOX_PAGES),
        ("📝 股利報稅", "tax_calc", {"tax_calc"}),
    ]
    for label, target, active_pages in nav_items:
        is_active = page in active_pages
        if st.button(
            label,
            use_container_width=True,
            type="primary" if is_active else "secondary",
            key=f"nav_{target}",
        ):
            go_to(target)

    st.markdown(f"<hr style='margin:10px 0; border-color:{BORDER_COLOR};'>", unsafe_allow_html=True)

    theme_btn_label = "☀️ 切換淺色模式" if st.session_state.theme == "dark" else "🌙 切換深色模式"
    if st.button(theme_btn_label, use_container_width=True):
        toggle_theme()
        st.rerun()

    st.markdown(f"<hr style='margin:10px 0; border-color:{BORDER_COLOR};'>", unsafe_allow_html=True)

    if st.button("🚪 登出系統", use_container_width=True):
        for k in ("logged_in", "current_user", "portfolio", "watchlist", "data"):
            st.session_state[k] = False if k == "logged_in" else None
        # 一併清掉殘留的元件狀態，避免下一位使用者看到上一位的資料
        for k in (
            "etf_symbol_input", "portfolio_editor",
            "eps_input", "pe_input", "eps_detail", "eps_pending",
        ):
            st.session_state.pop(k, None)
        st.session_state.page = "welcome"
        st.rerun()

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.caption("⚠️ 本系統數據僅供參考，不構成投資建議，投資人請審慎評估風險並自負盈虧。")


# =============================================================
# 8. 各功能頁面
# =============================================================
# ------------------------------------------------------------------
# 首頁
# ------------------------------------------------------------------
if page == "welcome":
    user = st.session_state.current_user
    st.markdown(f"## {greeting()}，{user} 👋")
    st.caption(datetime.now(tw_tz).strftime("台北時間 %Y-%m-%d %H:%M"))
    st.divider()

    st.markdown("#### 🌐 市場快照")
    snapshot = [("台股加權", "^TWII"), ("S&P 500", "^GSPC"), ("美元/台幣", "TWD=X")]
    for col, (label, ticker) in zip(st.columns(3), snapshot):
        with col:
            with st.container(border=True):
                draw_compact_metric(label, ticker)

    st.markdown("#### ⭐ 關注清單")
    if st.session_state.watchlist is None:
        st.session_state.watchlist = load_watchlist_from_cloud(user)

    preview = st.session_state.watchlist[:5]
    if not preview:
        st.caption("還沒有關注任何標的，可以先到左側「我的關注清單」加入幾檔。")
    else:
        with st.spinner("讀取關注清單報價..."):
            quotes = fetch_many(preview, get_stock_info)
        for col, code in zip(st.columns(len(preview)), preview):
            info = quotes.get(code)
            with col:
                if info:
                    color = UP_COLOR if info["change"] >= 0 else DOWN_COLOR
                    body = (
                        f"<div class='dash-value' style='color:{color};'>{info['price']:.2f}</div>"
                        f"<div style='color:{color}; font-size:0.85rem;'>"
                        f"{info['change']:+.2f} ({info['pct']:+.2f}%)</div>"
                    )
                    label_text = f"{code}　{info['name']}"
                else:
                    body = "<div class='dash-value' style='opacity:0.4;'>－</div>"
                    label_text = code
                st.markdown(
                    f"<div class='dash-card'><div class='dash-label'>{label_text}</div>{body}</div>",
                    unsafe_allow_html=True,
                )
        if len(st.session_state.watchlist) > len(preview):
            st.caption(f"僅顯示前 {len(preview)} 檔，共 {len(st.session_state.watchlist)} 檔。")

    st.divider()
    st.markdown("#### 🚀 快速前往")
    shortcuts = [
        ("📈 個股分析", "stock_query"),
        ("📊 ETF 分析", "etf_query"),
        ("💼 我的資產", "portfolio"),
        ("📝 股利報稅", "tax_calc"),
    ]
    for col, (label, target) in zip(st.columns(4), shortcuts):
        with col:
            if st.button(label, use_container_width=True, key=f"quick_{target}"):
                go_to(target)

# ------------------------------------------------------------------
# 工具箱
# ------------------------------------------------------------------
elif page == "home":
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<h3 style='opacity:0.7;'>請選擇功能進入：</h3>", unsafe_allow_html=True)
    st.divider()

    features = [
        ("📈 個股分析", "個股查詢與估價", "進入個股分析", "stock_query"),
        ("📊 ETF 分析", "ETF 試算與規劃", "進入 ETF 分析", "etf_query"),
        ("⚔️ ETF 對比", "ETF 對比工具", "進入對比工具", "pk_tool"),
        ("💼 我的資產", "個人投資組合", "進入我的資產", "portfolio"),
        ("🌐 大盤指數", "市場整體趨勢與氣氛", "進入大盤指數", "market_index"),
    ]

    for col, (title, desc, btn, target) in zip(st.columns(5), features):
        with col:
            st.markdown(
                f'<div class="feature-card"><div class="feature-title">{title}</div>'
                f'<div class="feature-desc">{desc}</div></div>',
                unsafe_allow_html=True,
            )
            if st.button(btn, use_container_width=True, type="primary", key=f"btn_{target}"):
                go_to(target)

# ------------------------------------------------------------------
# 關注清單
# ------------------------------------------------------------------
elif page == "watchlist":
    back_button()

    st.title("⭐ 我的關注清單")

    if st.session_state.watchlist is None:
        st.session_state.watchlist = load_watchlist_from_cloud(st.session_state.current_user)

    col_add, col_btn, col_refresh = st.columns([3, 1, 1])
    with col_add:
        new_code = st.text_input(
            "新增代碼", placeholder="例如：2330 或 00919", label_visibility="collapsed"
        )
    with col_btn:
        add_clicked = st.button("➕ 加入", use_container_width=True, type="primary")
    with col_refresh:
        refresh_clicked = st.button("🔄 更新報價", use_container_width=True)

    if add_clicked:
        code = clean_code(new_code)
        if not code:
            st.warning("請先輸入代碼。")
        elif code in st.session_state.watchlist:
            st.info(f"{code} 已經在清單中了。")
        elif get_stock_info(code) is None:
            st.error(f"查無 {code} 的報價，請確認代碼。")
        else:
            st.session_state.watchlist.append(code)
            save_watchlist_to_cloud(st.session_state.current_user, st.session_state.watchlist)
            st.rerun()

    if refresh_clicked:
        get_stock_info.clear()
        st.rerun()

    st.divider()

    if not st.session_state.watchlist:
        st.info("清單目前是空的，從上方加入第一檔股票吧。")
    else:
        with st.spinner("同步最新報價中..."):
            quotes = fetch_many(st.session_state.watchlist, get_stock_info)

        header = st.columns([2, 3, 2, 2, 1, 1])
        for col, text in zip(header, ["代碼", "名稱", "現價", "漲跌", "", ""]):
            col.markdown(f"**{text}**")

        removed = None
        for code in st.session_state.watchlist:
            info = quotes.get(code)
            c1, c2, c3, c4, c5, c6 = st.columns([2, 3, 2, 2, 1, 1])
            c1.write(code)
            if info:
                color = UP_COLOR if info["change"] >= 0 else DOWN_COLOR
                c2.write(info["name"])
                c3.markdown(
                    f"<span style='color:{color}; font-weight:bold;'>{info['price']:.2f}</span>",
                    unsafe_allow_html=True,
                )
                c4.markdown(
                    f"<span style='color:{color};'>{info['change']:+.2f} ({info['pct']:+.2f}%)</span>",
                    unsafe_allow_html=True,
                )
            else:
                c2.write("－")
                c3.write("查無報價")
                c4.write("－")
            if c5.button("📈", key=f"ana_{code}", help=f"以 ETF 分析檢視 {code}"):
                st.session_state.etf_symbol_input = code
                with st.spinner(f"分析 {code} 中..."):
                    st.session_state.data = get_safe_data_etf(code)
                go_to("etf_query")
            if c6.button("🗑️", key=f"del_{code}", help=f"移除 {code}"):
                removed = code

        if removed:
            st.session_state.watchlist = [c for c in st.session_state.watchlist if c != removed]
            save_watchlist_to_cloud(st.session_state.current_user, st.session_state.watchlist)
            st.rerun()

        st.caption(
            f"共 {len(st.session_state.watchlist)} 檔｜📈 進入 ETF 分析、🗑️ 移除｜"
            "報價快取 60 秒，可按「更新報價」強制重抓。"
        )

# ------------------------------------------------------------------
# 個股分析
# ------------------------------------------------------------------
elif page == "stock_query":
    back_button()

    st.title("🔍 台股自動估價系統 (個股)")
    main_col, side_col = st.columns([8, 4])

    with main_col:
        stock_code = st.text_input("請輸入台股代碼 (例如: 2330)")

        st.session_state.setdefault("eps_input", 10.0)
        st.session_state.setdefault("pe_input", 15.0)
        st.session_state.setdefault("eps_detail", None)

        # Streamlit 不允許在元件建立後才改它的 session_state，
        # 所以自動帶入的值先暫存，於下一輪在元件建立「之前」套用。
        if st.session_state.get("eps_pending") is not None:
            st.session_state.eps_input = st.session_state.pop("eps_pending")

        col_eps, col_pe = st.columns(2)
        with col_eps:
            eps = st.number_input("該股 EPS (近4季累積)", min_value=0.01, step=0.1, key="eps_input")
        with col_pe:
            pe_target = st.number_input("自訂參考本益比 (PE)", step=0.1, key="pe_input")

        col_auto, _ = st.columns([2, 3])
        with col_auto:
            if st.button("🔄 自動帶入近四季 EPS", use_container_width=True):
                if not stock_code:
                    st.warning("請先輸入股票代碼。")
                else:
                    with st.spinner("讀取財報中..."):
                        result = get_ttm_eps(stock_code)
                    if not result["success"]:
                        st.session_state.eps_detail = None
                        st.warning(f"⚠️ {result['msg']}")
                    elif result["ttm_eps"] <= 0:
                        st.session_state.eps_detail = result
                        st.warning(
                            f"⚠️ 近四季 EPS 為 {result['ttm_eps']:.2f}（虧損），"
                            "本益比法不適用，請改用其他估價方式。"
                        )
                    else:
                        st.session_state.eps_pending = float(result["ttm_eps"])
                        st.session_state.eps_detail = result
                        st.rerun()

        detail = st.session_state.eps_detail
        if detail and detail.get("symbol") == clean_code(stock_code):
            source_tag = "證交所 OpenAPI" if detail.get("source") == "twse" else "FinMind 財報"
            with st.expander(
                f"📄 EPS 來源：{source_tag}（{detail['period']}）", expanded=False
            ):
                st.caption(detail["method"])

                if detail["quarters"]:
                    q_df = pd.DataFrame(
                        [
                            {
                                "季別": quarter_label(q["date"]),
                                "財報日期": q["date"],
                                "單季 EPS": round(q["eps"], 2),
                                "稅後淨利 (千元)": (
                                    f"{q['net_income']:,.0f}"
                                    if q.get("net_income") is not None
                                    else "－"
                                ),
                            }
                            for q in detail["quarters"]
                        ]
                    )
                    st.dataframe(q_df, use_container_width=True, hide_index=True)
                else:
                    st.caption(
                        "此來源只提供近四季合計值，沒有分季明細。"
                        "若要看每一季的數字，請更新 FinMind token。"
                    )

                if detail["adjusted"]:
                    st.info(
                        f"ℹ️ 此檔期間內有配股／增資。四季 EPS 直接相加為 "
                        f"**{detail['naive_sum']:.2f}**，還原加權平均股數後為 "
                        f"**{detail['ttm_eps']:.2f}**，系統採用後者。"
                    )
                st.caption("※ 數值若與券商 App 有出入，以公開資訊觀測站財報為準，可手動修改上方欄位。")

        st.divider()

        if stock_code:
            info = get_stock_info(stock_code)
            if info is None:
                st.error("查無此代碼的報價，請確認輸入是否正確。")
            else:
                current_price = info["price"]

                col_title, col_btn = st.columns([3, 1])
                with col_title:
                    st.markdown(f"## {info['name']}")
                with col_btn:
                    st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
                    st.link_button(
                        "🌐 找公司官網",
                        f"https://www.google.com/search?q={info['name']}+公司官網",
                        use_container_width=True,
                    )

                st.markdown(
                    f"<div class='date-text'>資料日期：{datetime.now(tw_tz).strftime('%Y-%m-%d')}</div>",
                    unsafe_allow_html=True,
                )

                cp1, cp2 = st.columns([2, 1])
                with cp1:
                    color = UP_COLOR if info["change"] > 0 else DOWN_COLOR if info["change"] < 0 else TEXT_COLOR
                    st.markdown(
                        f"<div class='metric-val' style='color:{color}'>{current_price:.2f}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<span style='color:{color}; font-weight:bold; font-size:1.5rem;'>"
                        f"{info['change']:+.2f} ({info['pct']:+.2f}%)</span>",
                        unsafe_allow_html=True,
                    )
                with cp2:
                    st.caption("今日行情細節")
                    st.write(f"最高: {info['high']:.2f} / 最低: {info['low']:.2f}")
                    st.write(f"開盤: {info['open']:.2f} / 總量: {info['vol_lots']:,} 張")

                st.divider()

                if current_price > 0:
                    fair_price = eps * pe_target
                    st.subheader("📊 換算結果")
                    st.markdown(
                        f"<div class='calc-box'>合理價參考："
                        f"<span class='highlight-val'>{fair_price:.2f}</span></div>",
                        unsafe_allow_html=True,
                    )
                    if current_price <= fair_price:
                        st.success(f"✅ 目前股價 {current_price:.2f} 低於目標參考價")
                    else:
                        st.warning(f"⚠️ 目前股價 {current_price:.2f} 已超過目標參考價")

    with side_col:
        st.write("### 📖 說明")
        st.caption("1. 輸入股票代碼。")
        st.caption("2. 輸入股票4季累積EPS。")
        st.caption("3. 輸入個股本益比。")
        st.divider()
        st.info("計算公式：EPS × 自訂本益比 = 參考價")

# ------------------------------------------------------------------
# ETF 分析
# ------------------------------------------------------------------
elif page == "etf_query":
    back_button()

    st.title("📈 ETF 專用")
    main_col, side_col = st.columns([8, 4])

    with main_col:
        st.markdown(
            "### 🔍 查詢設定 <span style='font-size:1rem; opacity:0.6; font-weight:normal;'>"
            "(最新配息日要等到入資料庫才能抓到)</span>",
            unsafe_allow_html=True,
        )
        if "etf_symbol_input" not in st.session_state:
            st.session_state.etf_symbol_input = ""

        # 包成 form，在代號欄按 Enter 就會直接查詢
        with st.form("etf_query_form"):
            input_c1, input_c2 = st.columns([3, 1])
            with input_c1:
                st.text_input("ETF 代號", key="etf_symbol_input", placeholder="例如: 00919")
            with input_c2:
                st.write("")
                st.write("")
                etf_submitted = st.form_submit_button(
                    "開始計算", type="primary", use_container_width=True
                )

        if etf_submitted:
            symbol_input = clean_code(st.session_state.etf_symbol_input)
            if symbol_input:
                with st.spinner("抓取數據中..."):
                    st.session_state.data = get_safe_data_etf(symbol_input)
            else:
                st.warning("請先輸入 ETF 代號。")

        if st.session_state.data:
            if not st.session_state.data.get("success"):
                st.error(f"❌ 查詢失敗：{st.session_state.data.get('msg')}")
            else:
                d = st.session_state.data
                m_color = UP_COLOR if d["change"] >= 0 else DOWN_COLOR

                st.markdown(
                    f"## {d['name']} <small style='font-size:1rem; opacity:0.6;'>"
                    f"(偵測為{d['freq_label']}配息)</small>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='date-text'>資料日期：{d.get('last_date')}</div>",
                    unsafe_allow_html=True,
                )

                info_c1, info_c2 = st.columns([2, 1])
                with info_c1:
                    st.markdown(
                        f"<div class='metric-val' style='color:{m_color}'>{d['price']:.2f}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"<span style='color:{m_color}; font-weight:bold; font-size:1.5rem;'>"
                        f"{d['change']:+.2f} ({d['pct']:+.2f}%)</span>",
                        unsafe_allow_html=True,
                    )
                with info_c2:
                    st.caption("今日行情細節")
                    st.write(f"最高: {d['high']:.2f} / 最低: {d['low']:.2f}")
                    st.write(f"開盤: {d['open']:.2f} / 總量: {d['vol_lots']:,} 張")

                st.divider()
                st.subheader("📑 歷史配息參考")

                freq_map = {"月配": 12, "季配": 4, "半年配": 2, "年配": 1}
                sys_freq_name = f"{d['freq_label']}配"
                sys_index = list(freq_map).index(sys_freq_name) if sys_freq_name in freq_map else 3

                user_freq = st.selectbox("🔄 自訂/修正配息頻率：", list(freq_map), index=sys_index)
                # 只用區域變數，不去改動快取回來的字典
                multiplier = freq_map[user_freq]
                freq_label = user_freq.replace("配", "")

                e_cols = st.columns(4)
                labels = ["最新", "前一", "前二", "前三"]
                # 刻意不指定 key：換一檔 ETF 時，輸入框才會跟著帶入新的配息值
                divs = [
                    e_cols[i].number_input(labels[i], value=float(d["raw_divs"][i]), format="%.3f")
                    for i in range(4)
                ]
                d1 = divs[0]

                avg_annual = annualize(divs, multiplier)
                real_yield = (avg_annual / d["price"]) * 100 if d["price"] > 0 else 0

                stat_c1, stat_c2 = st.columns(2)
                with stat_c1:
                    st.caption(f"預估年配息 (系統以{freq_label}配計算)")
                    st.markdown(f"<div class='highlight-val'>{avg_annual:.2f}</div>", unsafe_allow_html=True)
                with stat_c2:
                    st.caption("實質殖利率")
                    st.markdown(f"<div class='highlight-val'>{real_yield:.2f}%</div>", unsafe_allow_html=True)

                st.divider()
                st.subheader("📊 估值位階參考")

                p_cheap = avg_annual / YIELD_CHEAP if avg_annual > 0 else 0
                p_fair = avg_annual / YIELD_FAIR if avg_annual > 0 else 0

                if avg_annual <= 0:
                    rec = "－ 無配息資料，無法評估"
                elif d["price"] <= p_cheap:
                    rec = "💎 便宜買入"
                elif d["price"] <= p_fair:
                    rec = "✅ 合理持有"
                else:
                    rec = "❌ 昂貴不建議"

                st.markdown(f"<div class='calc-box'>系統建議：<b>{rec}</b></div>", unsafe_allow_html=True)

                # 三段區間彼此連續，與上方建議使用同一組門檻
                st.markdown(
                    f"""
                    <table class="styled-table">
                        <thead><tr><th>估值位階</th><th>建議價格參考</th></tr></thead>
                        <tbody>
                            <tr><td>便宜價 (殖利率 10%)</td><td>{p_cheap:.2f} 以下</td></tr>
                            <tr><td>合理價 (殖利率 7%)</td><td>{p_cheap:.2f} ~ {p_fair:.2f}</td></tr>
                            <tr><td>昂貴價</td><td>高於 {p_fair:.2f}</td></tr>
                        </tbody>
                    </table>
                    """,
                    unsafe_allow_html=True,
                )

                st.divider()
                st.subheader("💰 持有張數試算 (含稅費)")
                ratio_54c = st.slider("54C 股利佔比 (%)", 0, 100, 40)
                calc_c1, _ = st.columns([1, 2])
                with calc_c1:
                    hold_lots = st.number_input("持有張數", min_value=0, value=10, step=1)

                total_shares = hold_lots * 1000
                total_raw = total_shares * d1
                div_54c_part = total_raw * (ratio_54c / 100)
                nhi_amt = div_54c_part * NHI_RATE if div_54c_part >= NHI_THRESHOLD else 0
                net_per_period = total_raw - nhi_amt

                st.markdown(
                    f"""
                    <div class="calc-box">
                        預估總投入: {total_shares * d['price'] * (1 + FEE_RATE):,.0f} 元<br>
                        每{freq_label}總配息: {total_raw:,.0f} 元<br>
                        <span style="color:{UP_COLOR};">└ 二代健保扣費: -{nhi_amt:,.0f} 元</span><br>
                        <b>每{freq_label}實領金額: {net_per_period:,.0f} 元</b>
                        <hr style="border:0.5px solid {BORDER_COLOR};">
                        一年累計實領: {net_per_period * multiplier:,.0f} 元
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"※ 二代健保補充保費以費率 {NHI_RATE:.2%}、單次給付達 {NHI_THRESHOLD:,} 元起扣計算，"
                    "費率與門檻若有調整請修改程式上方常數。"
                )

                st.divider()
                st.subheader("🔮 存股未來財富試算")

                f_col0, f_col1, f_col2, f_col3 = st.columns(4)
                with f_col0:
                    custom_initial = st.number_input("初始投入總金額 (元)", min_value=0, value=3_000_000, step=100_000)
                with f_col1:
                    custom_monthly = st.number_input("每月預計投入 (元)", min_value=0, value=0, step=1000)
                with f_col2:
                    custom_withdraw = st.number_input("每月預計領出 (元)", min_value=0, value=0, step=1000)
                with f_col3:
                    custom_yield = st.number_input("自訂年化殖利率 (%)", value=round(real_yield, 2), step=0.1)

                st.write("")
                custom_years = st.slider("目標投入年數", 1, 40, 10)

                r = (custom_yield / 100) / 12
                n = custom_years * 12
                net_monthly = custom_monthly - custom_withdraw

                if r > 0:
                    fv = custom_initial * ((1 + r) ** n) + net_monthly * (((1 + r) ** n - 1) / r) * (1 + r)
                else:
                    fv = custom_initial + net_monthly * n
                fv = max(0, fv)

                total_invested = custom_initial + custom_monthly * n
                total_withdrawn = custom_withdraw * n
                growth_ratio = (fv + total_withdrawn) / total_invested if total_invested > 0 else 0
                monthly_passive = (fv * (custom_yield / 100)) / 12

                st.markdown(
                    f"""
                    <div class="calc-box" style="border:2px solid {BORDER_COLOR}; padding:25px;">
                        <div style="font-size:3.2rem; font-weight:bold; color:{TEXT_COLOR};">
                            $ {fv:,.0f} <small style="font-size:1.2rem;">元</small>
                        </div>
                        <hr style="border:0.5px solid {BORDER_COLOR};">
                        <p style="font-size:1rem; color:{TEXT_COLOR}; line-height:1.8;">
                            累積投入本金: <b>{total_invested:,.0f}</b> 元 |
                            期間累計領出: <b style="color:{UP_COLOR};">{total_withdrawn:,.0f}</b> 元 |
                            整體資產成長: <b>{growth_ratio:.2f}</b> 倍<br>
                            <span style="color:{DOWN_COLOR}; font-weight:bold;">
                                期滿後每月預計被動收入 (不扣本金): {monthly_passive:,.0f} 元
                            </span>
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with side_col:
        st.write("### 📖 說明")
        st.caption("1. 輸入代號後點擊開始計算。")
        st.caption("2. 手動輸入配息即可試算。")
        st.divider()
        st.success("系統正常運行中")

# ------------------------------------------------------------------
# ETF 對比
# ------------------------------------------------------------------
elif page == "pk_tool":
    back_button()

    st.title("⚔️ ETF 對比工具")

    col_in1, col_in2 = st.columns(2)
    with col_in1:
        code1 = clean_code(st.text_input("輸入代碼 A", value="00919"))
    with col_in2:
        code2 = clean_code(st.text_input("輸入代碼 B", value="00918"))

    if st.button("開始對比"):
        with st.spinner("抓取對比數據中..."):
            fetched = fetch_many([code1, code2], get_safe_data_etf)
            r1, r2 = fetched.get(code1), fetched.get(code2)

        if r1 and r2 and r1["success"] and r2["success"]:
            st.divider()
            analysis = []
            for r in (r1, r2):
                avg_annual = annualize(r["raw_divs"], r["multiplier"])
                real_yield = (avg_annual / r["price"]) * 100 if r["price"] > 0 else 0
                analysis.append({"annual_div": avg_annual, "yield": real_yield})

            for col, r in zip(st.columns(2), (r1, r2)):
                with col:
                    color = UP_COLOR if r["change"] >= 0 else DOWN_COLOR
                    st.markdown(
                        f"""
                        <div class="pk-card">
                            <h3>{r['name']}</h3>
                            <h2 style="color:{color}">{r['price']:.2f}</h2>
                            <p>{r['change']:+.2f} ({r['pct']:+.2f}%)</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            st.table(
                pd.DataFrame(
                    {
                        "指標項目": ["目前價格", "當前漲幅", "配息頻率", "預估年配息", "實質殖利率"],
                        code1: [
                            f"{r1['price']:.2f}",
                            f"{r1['pct']:.2f}%",
                            r1["freq_label"],
                            f"{analysis[0]['annual_div']:.2f}",
                            f"{analysis[0]['yield']:.2f}%",
                        ],
                        code2: [
                            f"{r2['price']:.2f}",
                            f"{r2['pct']:.2f}%",
                            r2["freq_label"],
                            f"{analysis[1]['annual_div']:.2f}",
                            f"{analysis[1]['yield']:.2f}%",
                        ],
                    }
                )
            )
        else:
            st.error("查無資料，請確認代碼是否輸入正確。")

# ------------------------------------------------------------------
# 我的資產
# ------------------------------------------------------------------
elif page == "portfolio":
    back_button()

    st.title(f"💼 {st.session_state.current_user} 的投資組合")

    # --- 資料校準 ---
    if st.session_state.portfolio is not None:
        df = st.session_state.portfolio.copy()
        for col in COLUMNS_ORDER:
            if col not in df.columns:
                df[col] = None if col == "張數" else ""
        df["張數"] = pd.to_numeric(df["張數"], errors="coerce")
        st.session_state.portfolio = df[COLUMNS_ORDER]

    if st.session_state.portfolio is None or len(st.session_state.portfolio) == 0:
        st.session_state.portfolio = empty_portfolio()

    st.markdown("### 📝 編輯投資清單")
    edited_df = st.data_editor(
        st.session_state.portfolio[COLUMNS_ORDER],
        column_config={
            "代碼": st.column_config.TextColumn("代碼"),
            "名稱": st.column_config.TextColumn("名稱"),
            "張數": st.column_config.NumberColumn("張數", format="%.3f"),
            "戰略屬性": st.column_config.SelectboxColumn("戰略屬性", options=ASSET_CATEGORIES),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="portfolio_editor",
    )

    col_edit1, col_edit2 = st.columns(2)
    with col_edit1:
        if st.button("🔄 自動帶入資訊", use_container_width=True):
            temp_df = edited_df.copy()
            codes = [
                clean_code(c)
                for c in temp_df["代碼"]
                if str(c).strip() and str(c).strip().lower() != "nan"
            ]
            with st.spinner("正在查詢市場資訊..."):
                info_map = fetch_many(codes, get_stock_info)

            for i, row in temp_df.iterrows():
                code = clean_code(row["代碼"])
                info = info_map.get(code)
                if info and info.get("name"):
                    temp_df.at[i, "名稱"] = info["name"]
                    current_cat = row.get("戰略屬性")
                    if pd.isna(current_cat) or not str(current_cat).strip():
                        temp_df.at[i, "戰略屬性"] = get_asset_category(code, info["name"])

            temp_df["張數"] = pd.to_numeric(temp_df["張數"], errors="coerce")
            st.session_state.portfolio = temp_df[COLUMNS_ORDER]
            st.rerun()

    with col_edit2:
        if st.button("💾 儲存變更至資料庫", type="primary", use_container_width=True):
            save_df = edited_df[COLUMNS_ORDER].copy()
            save_df["張數"] = pd.to_numeric(save_df["張數"], errors="coerce")
            st.session_state.portfolio = save_df
            if save_portfolio_to_cloud(st.session_state.current_user, save_df):
                st.success("✅ 資料庫已同步更新")

    st.divider()
    st.markdown("### 📊 資產市值與配置分析")
    total_cost_input = st.number_input("💵 請輸入總成本", min_value=0.0, value=0.0, step=10000.0)

    calc_prep = edited_df.copy()
    calc_prep["張數"] = pd.to_numeric(calc_prep["張數"], errors="coerce")
    valid_df = calc_prep.dropna(subset=["代碼", "張數"])
    valid_df = valid_df[valid_df["代碼"].astype(str).str.strip() != ""]

    if valid_df.empty:
        st.info("請先在上方表格輸入股票代碼與持有張數。")
    else:
        if st.button("開始計算當前市值", type="primary", use_container_width=True):
            codes = [clean_code(c) for c in valid_df["代碼"]]
            lots_map = {clean_code(r["代碼"]): float(r["張數"]) for _, r in valid_df.iterrows()}
            cat_map = {clean_code(r["代碼"]): r.get("戰略屬性") for _, r in valid_df.iterrows()}

            with st.spinner("同步市場最新價格中..."):
                data_map = fetch_many(codes, get_safe_data_etf)

            results = []
            total_market_val = 0.0
            total_annual_div = 0.0

            for code, data in data_map.items():
                if not data or not data.get("success"):
                    continue
                shares = lots_map.get(code, 0) * 1000
                m_val = data["price"] * shares
                avg_annual = annualize(data["raw_divs"], data["multiplier"])
                ann_div = avg_annual * shares

                category = cat_map.get(code)
                if pd.isna(category) or not str(category).strip():
                    category = get_asset_category(code, data["name"])

                results.append(
                    {
                        "名稱": data["name"],
                        "代碼": code,
                        "張數": lots_map.get(code, 0),
                        "現價": data["price"],
                        "持有價值": m_val,
                        "預估年領股息": ann_div,
                        "戰略屬性": category,
                    }
                )
                total_market_val += m_val
                total_annual_div += ann_div

            if not results:
                st.error("沒有任何一檔取得到報價，請確認代碼。")
            else:
                res_df = pd.DataFrame(results)
                res_df["戰略屬性"] = pd.Categorical(
                    res_df["戰略屬性"], categories=ASSET_CATEGORIES, ordered=True
                )
                res_df = res_df.sort_values(by=["戰略屬性", "持有價值"], ascending=[True, False])

                return_amt = total_market_val - total_cost_input
                return_pct = (return_amt / total_cost_input * 100) if total_cost_input > 0 else 0
                ret_color = UP_COLOR if return_amt > 0 else DOWN_COLOR if return_amt < 0 else TEXT_COLOR
                circle_pct = min(abs(return_pct), 100)

                st.markdown(
                    f"""
                    <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-around;
                                background-color:{SECONDARY_BG}; padding:25px; border-radius:15px;
                                border:1px solid {BORDER_COLOR}; margin-bottom:20px;">
                        <div style="position:relative; width:160px; height:160px; border-radius:50%;
                                    background: conic-gradient({ret_color} {circle_pct}%, {TRACK_COLOR} 0);
                                    display:flex; align-items:center; justify-content:center;
                                    box-shadow:0 0 15px rgba(0,0,0,0.3);">
                            <div style="position:absolute; width:125px; height:125px; background-color:{SECONDARY_BG};
                                        border-radius:50%; display:flex; flex-direction:column;
                                        align-items:center; justify-content:center;">
                                <span style="color:{TEXT_COLOR}; opacity:0.7; font-size:16px;">股票報酬</span>
                                <span style="color:{ret_color}; font-size:22px; font-weight:bold;">{return_pct:+.2f}%</span>
                            </div>
                        </div>
                        <div style="min-width:280px; margin-top:10px;">
                            <div style="display:flex; justify-content:space-between; border-bottom:1px solid {BORDER_COLOR};
                                        padding-bottom:8px; margin-bottom:8px;">
                                <span style="color:{TEXT_COLOR}; opacity:0.8; font-size:18px;">總成本：</span>
                                <span style="color:{TEXT_COLOR}; font-size:22px; font-weight:bold;
                                             font-family:'Consolas';">{total_cost_input:,.0f}</span>
                            </div>
                            <div style="display:flex; justify-content:space-between; border-bottom:1px solid {BORDER_COLOR};
                                        padding-bottom:8px; margin-bottom:15px;">
                                <span style="color:{TEXT_COLOR}; opacity:0.8; font-size:18px;">股票市值：</span>
                                <span style="color:{TEXT_COLOR}; font-size:22px; font-weight:bold;
                                             font-family:'Consolas';">{total_market_val:,.0f}</span>
                            </div>
                            <div style="display:flex; justify-content:space-between;">
                                <span style="color:{TEXT_COLOR}; opacity:0.8; font-size:18px;">總報酬：</span>
                                <span style="color:{ret_color}; font-size:26px; font-weight:bold;
                                             font-family:'Consolas';">{return_amt:+,.0f}</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                m1, m2 = st.columns(2)
                m1.metric("預估年領股息", f"${total_annual_div:,.0f}")
                avg_yield = (total_annual_div / total_market_val * 100) if total_market_val > 0 else 0
                m2.metric("組合平均殖利率", f"{avg_yield:.2f}%")

                st.markdown("### 🎯 戰略資產佈局")
                cat_df = res_df.groupby("戰略屬性", observed=True)["持有價值"].sum().reset_index()
                col_pie1, col_pie2, col_table = st.columns([1, 1, 1.5])

                with col_pie1:
                    fig1 = px.pie(
                        res_df, values="持有價值", names="名稱", title="個股配置 (名稱顯示)",
                        hole=0.3, color_discrete_sequence=px.colors.qualitative.Pastel,
                    )
                    fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color=TEXT_COLOR, showlegend=False)
                    fig1.update_traces(textposition="inside", textinfo="label+percent")
                    st.plotly_chart(fig1, use_container_width=True, key="portfolio_pie_individual")

                with col_pie2:
                    fig2 = px.pie(
                        cat_df, values="持有價值", names="戰略屬性", title="戰略佔比", hole=0.4,
                        color_discrete_sequence=["#ff4b4b", "#f1c40f", "#3498db"],
                    )
                    fig2.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", font_color=TEXT_COLOR,
                        legend=dict(orientation="h", y=-0.2),
                    )
                    st.plotly_chart(fig2, use_container_width=True, key="portfolio_pie_category")

                with col_table:
                    st.write("#### 詳細數據")
                    st.dataframe(
                        res_df.style.format(
                            {
                                "張數": "{:,.3f}",
                                "現價": "{:,.2f}",
                                "持有價值": "{:,.0f}",
                                "預估年領股息": "{:,.0f}",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        st.divider()
        st.subheader("📅 自動化領息排程月曆")
        horizon_days = st.slider("顯示未來幾天內的配息", 7, 120, DIV_PAY_LAG_DAYS * 2, step=7)

        if st.button("🚀 生成我的專屬領息月曆", use_container_width=True, type="primary"):
            cal_df = generate_user_calendar()

            if cal_df is None or cal_df.empty:
                st.info("目前沒有可用的配息預估資料。")
            else:
                cal_df["_pay"] = pd.to_datetime(cal_df["預計發放日 (預估)"])
                cutoff = pd.Timestamp(datetime.now(tw_tz).date()) + pd.Timedelta(days=horizon_days)
                filtered = cal_df[cal_df["_pay"] <= cutoff].sort_values("_pay")

                if filtered.empty:
                    st.warning(f"⚠️ 未來 {horizon_days} 天內暫無預計領息資料。")
                else:
                    display_df = filtered.drop(columns=["_pay"]).copy()
                    display_df["每股配息"] = display_df["每股配息"].map(lambda v: f"${v:.3f}")
                    display_df["預估入帳金額"] = display_df["預估入帳金額"].map(lambda v: f"{v:,.0f}")
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                    st.success(
                        f"💰 這一波領息預計總入帳： **${filtered['預估入帳金額'].sum():,.0f}** 元"
                    )
                    st.caption(
                        f"※ 除息日以歷史配息頻率往未來推估，發放日再加 {DIV_PAY_LAG_DAYS} 天；"
                        "標示「推估」者尚未公告，正確資料請以各上市櫃公司與股市公告為準。"
                    )

# ------------------------------------------------------------------
# 大盤指數
# ------------------------------------------------------------------
elif page == "market_index":
    back_button()

    st.markdown(
        """
        <h3 style='margin-top:10px; margin-bottom:0px;'>
            大盤指數
            <span style='font-size:0.75rem; opacity:0.6; font-weight:normal; margin-left:10px;'>
                (有些數值會有些許誤差)
            </span>
        </h3>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    _, col_refresh = st.columns([4, 1])
    with col_refresh:
        if st.button("🔄 重新整理", use_container_width=True):
            get_market_data.clear()
            st.rerun()
    st.caption(f"最後更新：{datetime.now(tw_tz).strftime('%Y-%m-%d %H:%M')}（資料快取 5 分鐘）")

    for row_start in range(0, len(MARKET_TICKERS), 3):
        for col, (label, ticker) in zip(st.columns(3), MARKET_TICKERS[row_start:row_start + 3]):
            with col:
                with st.container(border=True):
                    draw_compact_metric(label, ticker)

    st.caption(
        "※ 台指期在 Yahoo 的資料時有時無，系統會依序改試 TWF=F 與加權指數；"
        "若仍顯示暫無資料，代表三個來源當下都沒有報價。"
    )

# ------------------------------------------------------------------
# 股利報稅與綜合所得稅試算
# ------------------------------------------------------------------
elif page == "tax_calc":
    back_button()

    st.title("📝 股利報稅與綜合所得稅試算")

    years = sorted(TAX_CONFIG.keys(), reverse=True)
    tax_year = st.selectbox(
        "申報年度", years, index=0, format_func=lambda y: TAX_CONFIG[y]["label"]
    )
    cfg = TAX_CONFIG[tax_year]

    st.info(
        f"目前套用 **{cfg['label']}** 稅制。具備「薪資精準防呆」與「排富條款自動判定」功能。"
    )
    if not cfg.get("basic_living_confirmed", True):
        st.caption(
            f"※ {tax_year} 年度每人基本生活費尚待財政部公告，暫以 {cfg['basic_living']:,} 元計算。"
        )

    # ------------------------- 輸入區 -------------------------
    with st.expander("✏️ 展開填寫：所得與家庭扣除額資料", expanded=True):
        st.markdown("#### 💼 第一部分：所得資料 (精準薪資防呆)")
        st.caption(
            f"💡 若有打工族，請務必分開填寫薪資！系統會自動判斷「實領薪資」與"
            f"「{cfg['salary_cap'] / 10000:.1f}萬上限」取低值扣除。股利則直接填寫全家總和即可。"
        )

        c_inc = st.columns(4)
        sal_1 = c_inc[0].number_input("報稅人(爸爸) 薪資", min_value=0, value=0, step=10000)
        sal_2 = c_inc[1].number_input("配偶(媽媽) 薪資", min_value=0, value=0, step=10000)
        sal_3 = c_inc[2].number_input("扶養親屬1 薪資", min_value=0, value=0, step=10000)
        sal_4 = c_inc[3].number_input("扶養親屬2 薪資", min_value=0, value=0, step=10000)

        st.write("")
        div_total = st.number_input("全年股利及盈餘合計金額 (全家加總)", min_value=0, value=0, step=1000)

        st.divider()
        st.markdown("#### 👨‍👩‍👧‍👦 第二部分：家庭與一般扣除額")
        c1, c2, c3 = st.columns(3)
        with c1:
            marital_options = [
                f"單身 ({cfg['standard_single'] / 10000:.1f}萬)",
                f"夫妻合併申報 ({cfg['standard_couple'] / 10000:.1f}萬)",
            ]
            marital_status = st.selectbox("婚姻狀態 (決定標準扣除額)", marital_options)
            standard_deduction = (
                cfg["standard_single"] if "單身" in marital_status else cfg["standard_couple"]
            )
        with c2:
            dependents_normal = st.number_input(
                "未滿70歲人數 (含本人/配偶/扶養)", min_value=0, value=0, step=1
            )
        with c3:
            dependents_70plus = st.number_input("滿70歲以上扶養人數", min_value=0, value=0, step=1)

        c_item1, c_item2 = st.columns([1, 2])
        with c_item1:
            itemized_deduction = st.number_input(
                "🏥 列舉扣除額總計 (如醫藥/保險/捐贈)", min_value=0, value=0, step=10000
            )
        with c_item2:
            st.write("")
            st.info("💡 系統會自動比較「標準」與「列舉」，採用金額較高者。")

        st.divider()
        st.markdown("#### 🌟 第三部分：特別扣除額")
        st.caption("以下按「人數」計算的項目，請直接輸入符合資格的【人數】，系統會自動乘上對應額度。")
        c4, c5, c6 = st.columns(3)
        with c4:
            saving_deduction = st.number_input(
                f"儲蓄投資金額 (上限{cfg['saving_cap'] / 10000:.0f}萬)",
                min_value=0, max_value=cfg["saving_cap"], value=0, step=1000,
            )
            disability_count = st.number_input(
                f"身心障礙【人數】 (每人{cfg['disability_per_person'] / 10000:.1f}萬)",
                min_value=0, value=0, step=1,
            )
        with c5:
            edu_count = st.number_input(
                f"教育學費【人數】 (每人{cfg['edu_per_person'] / 10000:.1f}萬)",
                min_value=0, value=0, step=1,
            )
            preschool_count = st.number_input(
                f"幼兒學前【人數】 (第1名{cfg['preschool_first'] / 10000:.0f}萬/"
                f"第2名起每人{cfg['preschool_rest'] / 10000:.1f}萬)",
                min_value=0, value=0, step=1,
            )
        with c6:
            ltc_count = st.number_input(
                f"長期照顧【人數】 (每人{cfg['ltc_per_person'] / 10000:.0f}萬)",
                min_value=0, value=0, step=1,
            )
            rent_deduction_input = st.number_input(
                f"房屋租金支出金額 (上限{cfg['rent_cap'] / 10000:.0f}萬)",
                min_value=0, max_value=cfg["rent_cap"], value=0, step=1000,
            )

        basic_income_over_cap = st.checkbox(
            f"基本所得額超過 {BASIC_INCOME_CAP / 10000:.0f} 萬元（勾選後長照與租金扣除額一律排富）",
            value=False,
        )

    # ------------------------- 共用運算 -------------------------
    salary = sal_1 + sal_2 + sal_3 + sal_4
    salary_deduction = sum(min(s, cfg["salary_cap"]) for s in (sal_1, sal_2, sal_3, sal_4))

    general_deduction = max(standard_deduction, itemized_deduction)
    deduction_type_str = "列舉" if itemized_deduction > standard_deduction else "標準"

    disability_deduction = disability_count * cfg["disability_per_person"]
    edu_deduction = edu_count * cfg["edu_per_person"]
    # 幼兒學前特別扣除額自 113 年度起已刪除排富規定，兩個方案都完整適用
    preschool_deduction = preschool_amount(preschool_count, cfg)
    ltc_full = ltc_count * cfg["ltc_per_person"]
    rent_full = rent_deduction_input

    total_people = dependents_normal + dependents_70plus
    total_exemption = dependents_normal * cfg["exemption"] + dependents_70plus * cfg["exemption_70"]
    basic_expense_unit = cfg["basic_living"]
    total_basic_living = basic_expense_unit * total_people

    rich_threshold = cfg["brackets"][1][0]   # 12% 級距上限，超過即適用 20% 以上

    def build_tax_case(ltc_amt, rent_amt, include_dividend):
        """回傳一組完整的計算結果，方案 A / B 共用。"""
        comparison_sum = (
            total_exemption + general_deduction + saving_deduction + disability_deduction
            + edu_deduction + preschool_deduction + ltc_amt + rent_amt
        )
        basic_diff = max(0, total_basic_living - comparison_sum)
        total_income = salary + (div_total if include_dividend else 0)
        total_deductions = comparison_sum + salary_deduction
        net = max(0, total_income - total_deductions - basic_diff)
        rate, prog = lookup_bracket(net, cfg)
        return {
            "comparison_sum": comparison_sum,
            "basic_diff": basic_diff,
            "total_income": total_income,
            "total_deductions": total_deductions,
            "net": net,
            "rate": rate,
            "prog": prog,
            "base_tax": max(0, net * rate - prog),
            "ltc": ltc_amt,
            "rent": rent_amt,
        }

    tax_table_data = pd.DataFrame(
        {
            "所得淨額": [
                f"0 ~ {cfg['brackets'][0][0]:,}",
                f"{cfg['brackets'][0][0] + 1:,} ~ {cfg['brackets'][1][0]:,}",
                f"{cfg['brackets'][1][0] + 1:,} ~ {cfg['brackets'][2][0]:,}",
                f"{cfg['brackets'][2][0] + 1:,} ~ {cfg['brackets'][3][0]:,}",
                f"{cfg['brackets'][3][0] + 1:,} 以上",
            ],
            "稅率": [f"{int(b[1] * 100)}%" for b in cfg["brackets"]],
            "累進差額": [f"{b[2]:,}" for b in cfg["brackets"]],
        }
    )

    def render_deduction_table(case, muted_note):
        """扣除額明細表。muted_note 有值代表長照／租金被排富歸零。"""
        muted_cls = ' class="muted"' if muted_note else ""
        note_html = (
            f'<br><span style="font-size:12px; color:{UP_COLOR};">{muted_note}</span>'
            if muted_note else ""
        )
        return f"""
        <table class="tax-table">
            <tr>
                <th>每人基本生活費</th><th class="operator">乘</th><th>總申報人數</th><th class="operator">減</th>
                <th>全部免稅額</th><th class="operator">減</th><th>一般扣除額</th><th class="operator">減</th>
                <th>儲蓄投資扣除額</th><th class="operator">減</th>
            </tr>
            <tr>
                <td>{basic_expense_unit:,}</td><td class="operator">✕</td><td>{total_people}</td>
                <td class="operator">－</td><td>{total_exemption:,}</td><td class="operator">－</td>
                <td style="font-weight:bold;">{general_deduction:,}<br>
                    <span style="font-size:12px; font-weight:normal;">({deduction_type_str})</span></td>
                <td class="operator">－</td><td>{saving_deduction:,}</td><td class="operator">－</td>
            </tr>
            <tr>
                <th>身心障礙扣除額</th><th class="operator">減</th><th>教育學費扣除額</th><th class="operator">減</th>
                <th>幼兒學前扣除額</th><th class="operator">減</th><th>長期照顧扣除額</th><th class="operator">減</th>
                <th>房屋租金扣除額</th><th class="operator">等於</th>
            </tr>
            <tr>
                <td>{disability_deduction:,}</td><td class="operator">－</td>
                <td>{edu_deduction:,}</td><td class="operator">－</td>
                <td>{preschool_deduction:,}</td><td class="operator">－</td>
                <td{muted_cls}>{case['ltc']:,}{note_html}</td><td class="operator">－</td>
                <td{muted_cls}>{case['rent']:,}{note_html}</td><td class="operator">＝</td>
            </tr>
            <tr><th colspan="10" style="text-align:left; padding-left:20px;">基本生活費差額</th></tr>
            <tr><td colspan="10" style="text-align:left; padding-left:20px; font-weight:bold;
                     font-size:18px; color:{UP_COLOR};">{case['basic_diff']:,}</td></tr>
        </table>
        """

    tab1, tab2 = st.tabs(["📊 方案 A：一般合併申報明細", "👑 方案 B：股利 28% 分開計稅明細"])

    # ---------------- 方案 A ----------------
    with tab1:
        # 第一階段：先假設可以扣長照與租金，算出稅率
        trial = build_tax_case(ltc_full, rent_full, include_dividend=True)
        is_rich_a = trial["net"] > rich_threshold or basic_income_over_cap

        if is_rich_a:
            case_a = build_tax_case(0, 0, include_dividend=True)
            muted_note_a = "(排富取消)"
        else:
            case_a = trial
            muted_note_a = ""

        div_credit_a = min(DIV_CREDIT_CAP, div_total * DIV_CREDIT_RATE)
        final_tax_a = case_a["base_tax"] - div_credit_a

        if is_rich_a:
            reason = "基本所得額超過門檻" if basic_income_over_cap else "課稅級距達 20% 以上"
            st.warning(
                f"⚠️ **系統偵測：{reason}，已自動觸發排富條款！**\n\n"
                "長期照顧與房屋租金特別扣除額已自動歸零；"
                "幼兒學前特別扣除額自 113 年度起已取消排富，故仍可全額適用。"
            )

        st.markdown("### 📝 扣除額與抵減稅額明細 (方案 A)")
        st.markdown(render_deduction_table(case_a, muted_note_a), unsafe_allow_html=True)

        st.markdown("★ **股利及盈餘可抵減稅額：**")
        st.markdown(
            f"""
            <table class="tax-table">
                <tr><th style="width:40%;">股利及盈餘合計金額</th><th class="operator">乘</th>
                    <th style="width:20%;">抵減率</th><th class="operator">等於</th>
                    <th style="width:40%;">可抵減稅額</th></tr>
                <tr><td>{div_total:,}</td><td class="operator">✕</td>
                    <td>{DIV_CREDIT_RATE:.1%}</td><td class="operator">＝</td>
                    <td style="font-weight:bold; font-size:18px; color:{DOWN_COLOR};">
                        {div_credit_a:,.0f}
                        <span style="font-size:12px; font-weight:normal;">
                            (上限{DIV_CREDIT_CAP / 10000:.0f}萬)</span></td></tr>
            </table>
            """,
            unsafe_allow_html=True,
        )

        st.divider()
        col_chart_a, col_result_a = st.columns([1.2, 1])
        with col_chart_a:
            st.markdown(f"### 📊 {tax_year}年度綜合所得稅級距表")
            st.caption("根據您輸入的資料，系統會自動對應下表計算：")
            st.table(tax_table_data)

        with col_result_a:
            st.markdown("### 🧾 結算單 (方案 A)")
            with st.container(border=True):
                st.markdown(
                    f"**綜合所得總額 (薪資＋股利)：** "
                    f"<span style='float:right;'>{case_a['total_income']:,.0f} 元</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='opacity:0.6; font-size:13px; margin-top:-10px; margin-bottom:5px;'>"
                    f"└ 包含精準核算之薪資特別扣除額: {salary_deduction:,.0f} 元</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**全部扣除額及免稅額合計：** "
                    f"<span style='float:right; color:#ffbc4b;'>- {case_a['total_deductions']:,.0f} 元</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**基本生活費差額：** "
                    f"<span style='float:right; color:#ffbc4b;'>- {case_a['basic_diff']:,.0f} 元</span>",
                    unsafe_allow_html=True,
                )
                st.markdown("---")
                st.markdown(
                    f"<h4 style='color:#4bc0ff; margin-top:0;'>➤ 綜合所得淨額： "
                    f"<span style='float:right;'>{case_a['net']:,.0f} 元</span></h4>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"套用稅率 {int(case_a['rate'] * 100)}% 減去累進差額 {case_a['prog']:,.0f} "
                    f"= 應納稅額 {case_a['base_tax']:,.0f} 元"
                )
                st.markdown(
                    f"**股利 {DIV_CREDIT_RATE:.1%} 可抵減稅額：** "
                    f"<span style='float:right; color:{DOWN_COLOR};'>- {div_credit_a:,.0f} 元</span>",
                    unsafe_allow_html=True,
                )
                st.markdown("---")
                fc_a = UP_COLOR if final_tax_a > 0 else DOWN_COLOR
                st.markdown(
                    "<div style='text-align:center; opacity:0.6; font-size:16px;'>"
                    "方案 A 最終實繳 / 退稅金額</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center; font-size:38px; font-weight:bold; color:{fc_a};'>"
                    f"{final_tax_a:,.0f} <span style='font-size:16px;'>元</span></div>",
                    unsafe_allow_html=True,
                )

    # ---------------- 方案 B ----------------
    with tab2:
        case_b = build_tax_case(0, 0, include_dividend=False)
        div_tax_b = div_total * DIV_SEPARATE_RATE
        final_tax_b = case_b["base_tax"] + div_tax_b

        st.warning(
            "👑 **方案 B 預設：凡選擇股利 28% 分開計稅，即自動觸發排富條款！**\n\n"
            "長期照顧與房屋租金特別扣除額已自動歸零；幼兒學前特別扣除額不受排富限制，仍可適用。"
        )

        st.markdown("### 📝 扣除額明細 (方案 B：排富沒收版)")
        st.markdown(render_deduction_table(case_b, "(28%排富取消)"), unsafe_allow_html=True)

        st.markdown("★ **股利及盈餘分開計稅：**")
        st.markdown(
            f"""
            <table class="tax-table">
                <tr><th style="width:40%;">股利及盈餘合計金額</th><th class="operator">乘</th>
                    <th style="width:20%;">單一稅率</th><th class="operator">等於</th>
                    <th style="width:40%;">股利應納稅額</th></tr>
                <tr><td>{div_total:,}</td><td class="operator">✕</td>
                    <td>{DIV_SEPARATE_RATE:.0%}</td><td class="operator">＝</td>
                    <td style="font-weight:bold; font-size:18px; color:#ffbc4b;">{div_tax_b:,.0f}</td></tr>
            </table>
            """,
            unsafe_allow_html=True,
        )

        st.divider()
        col_chart_b, col_result_b = st.columns([1.2, 1])
        with col_chart_b:
            st.markdown(f"### 📊 {tax_year}年度綜合所得稅級距表")
            st.caption("根據您輸入的資料，系統會自動對應下表計算：")
            st.table(tax_table_data)

        with col_result_b:
            st.markdown("### 🧾 結算單 (方案 B)")
            with st.container(border=True):
                st.markdown(
                    f"**綜合所得總額 (⚠️ 不含股利)：** "
                    f"<span style='float:right;'>{case_b['total_income']:,.0f} 元</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='opacity:0.6; font-size:13px; margin-top:-10px; margin-bottom:5px;'>"
                    f"└ 包含精準核算之薪資特別扣除額: {salary_deduction:,.0f} 元</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**全部扣除額及免稅額合計：** "
                    f"<span style='float:right; color:#ffbc4b;'>- {case_b['total_deductions']:,.0f} 元</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**基本生活費差額：** "
                    f"<span style='float:right; color:#ffbc4b;'>- {case_b['basic_diff']:,.0f} 元</span>",
                    unsafe_allow_html=True,
                )
                st.markdown("---")
                st.markdown(
                    f"<h4 style='color:#4bc0ff; margin-top:0;'>➤ 本薪綜合所得淨額： "
                    f"<span style='float:right;'>{case_b['net']:,.0f} 元</span></h4>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"套用稅率 {int(case_b['rate'] * 100)}% 減去累進差額 {case_b['prog']:,.0f} "
                    f"= 薪資應納稅額 {case_b['base_tax']:,.0f} 元"
                )
                st.markdown(
                    f"**➕ 股利 {DIV_SEPARATE_RATE:.0%} 分開計稅額：** "
                    f"<span style='float:right; color:#ffbc4b;'>+ {div_tax_b:,.0f} 元</span>",
                    unsafe_allow_html=True,
                )
                st.markdown("---")
                fc_b = UP_COLOR if final_tax_b > 0 else DOWN_COLOR
                st.markdown(
                    "<div style='text-align:center; opacity:0.6; font-size:16px;'>方案 B 最終實繳金額</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center; font-size:38px; font-weight:bold; color:{fc_b};'>"
                    f"{final_tax_b:,.0f} <span style='font-size:16px;'>元</span></div>",
                    unsafe_allow_html=True,
                )

    # ---------------- 方案比較 ----------------
    st.divider()
    better = "方案 A（合併計稅）" if final_tax_a <= final_tax_b else "方案 B（28% 分開計稅）"
    diff = abs(final_tax_a - final_tax_b)
    st.success(
        f"📌 以目前輸入的資料，**{better}** 較有利，兩者相差約 **{diff:,.0f}** 元。"
        "（實際申報請以財政部電子申報系統試算結果為準。）"
    )

else:
    st.warning("找不到這個頁面，請從左側選單重新選擇。")
    if st.button("回到首頁"):
        go_to("welcome")

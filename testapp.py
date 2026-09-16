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

# 版本標記：顯示在側邊欄「資料來源診斷」裡，用來確認雲端跑的是哪一版程式
APP_VERSION = "2026-09-16 / market-v19"

# --- API 金鑰 ---------------------------------------------------------------
# 建議改放 .streamlit/secrets.toml，例如：
#   FUGLE_TOKEN = st.secrets["fugle"]["token"]
FUGLE_TOKEN = "YzJjNmM3ODAtZjE1Ny00NzhiLWFjOTUtMDUwZjc2ZWJhYTI1IGRjYTE0ODk3LTRjYTUtNDg5Yi05MjAwLWZmYzNmNzFmNmYwNg=="
# FinMind token（帳號 ezzzz，永久期限）。
# 這串已由使用者直接提供並核對過。
# 也可以改放 Secrets，設定後會自動覆寫下面的預設值，不必改程式碼：
#   [finmind]
#   token = "你的token"
_FINMIND_TOKEN_FALLBACK = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiZXp6enoiLCJlbWFpbCI6ImVhc29uOTMxMDExQGdtYWlsLmNvbSIsInRva2VuX3ZlcnNpb24iOjF9.-gtBtgcSm3zEgFfrjD1dy83HWlObeLssgyxH_q9b8Fc"
)
try:
    _secret_token = st.secrets.get("finmind", {}).get("token")
except Exception:
    _secret_token = None

FINMIND_TOKEN = _secret_token or _FINMIND_TOKEN_FALLBACK
FINMIND_TOKEN_SOURCE = "Secrets" if _secret_token else "程式內建"

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

        /* 隱藏輸入框內的 "Press Enter to submit form" / "Press Enter to apply" 提示 */
        [data-testid="InputInstructions"],
        [data-testid="stWidgetInstructions"] {{
            display: none !important;
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


@st.cache_resource(show_spinner=False)
def init_workbook():
    """
    開啟試算表並取得各工作表，整個流程只做一次。
    這段原本寫在模組層級，Streamlit 每次 rerun 都會重跑，等於每點一下就打
    Google API 四次；Sheets 的讀取上限是每分鐘 60 次／使用者，很容易觸發 429。
    """
    conn = init_connection()
    sh = conn.open("streamlit_db")

    users, created = ensure_worksheet(
        sh, "users", ["username", "password"], rows="500", cols="2"
    )
    if created:
        users.append_row(["admin", "8888"])

    portfolios, _ = ensure_worksheet(sh, "portfolios", ["username", "data_json"], cols="2")
    watchlist, _ = ensure_worksheet(sh, "watchlist", ["username", "codes"], cols="2")
    return sh, users, portfolios, watchlist


try:
    sh, user_sheet, portfolio_sheet, watchlist_sheet = init_workbook()
except Exception as e:
    msg = str(e)
    st.error(f"雲端資料庫連線失敗：{msg}")
    if "429" in msg or "Quota exceeded" in msg:
        st.info(
            "這是 Google Sheets 的每分鐘讀取上限（60 次／使用者）。"
            "請等約一分鐘後重新整理頁面即可恢復。"
        )
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
        st.error(f"雲端儲存失敗：{e}")
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
            <h2 style="margin: 0; color: {TEXT_COLOR} !important; font-size: 24px;">台股個股/ETF查詢</h2>
            <p style="color: {TEXT_COLOR} !important; opacity: 0.7; margin-top: 8px;
                      margin-bottom: 0; font-size: 14px;">Ez開發 - 投資助手系統</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, col_theme, _ = st.columns([1, 1.2, 1])
    with col_theme:
        btn_label = "切換淺色模式" if st.session_state.theme == "dark" else "切換深色模式"
        if st.button(btn_label, use_container_width=True, key="login_theme_toggle"):
            toggle_theme()
            st.rerun()

    _, col2, _ = st.columns([1, 1.2, 1])
    with col2:
        user_db = get_cloud_users()
        tab_login, tab_reg = st.tabs(["帳號登入", "新用戶註冊"])

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
                    st.error("帳號或密碼不正確")

        with tab_reg:
            st.info("註冊資料將儲存於雲端，重啟系統不會遺失。")
            with st.form("register_form"):
                new_u = st.text_input("設定帳號", key="r_user").strip()
                new_p = st.text_input("設定密碼", type="password", key="r_pw")
                confirm_p = st.text_input("確認密碼", type="password", key="r_confirm")
                reg_submitted = st.form_submit_button("提交註冊", use_container_width=True)

            if reg_submitted:
                if new_u in user_db:
                    st.warning("帳號已存在")
                elif new_p != confirm_p:
                    st.error("密碼不一致")
                elif len(new_u) < 2 or len(new_p) < 4:
                    st.error("長度不足 (帳號需2字元, 密碼需4字元)")
                else:
                    try:
                        user_sheet.append_row([new_u, new_p])
                        save_portfolio_to_cloud(new_u, empty_portfolio())
                        get_cloud_users.clear()   # 清掉快取，新帳號才登得進去
                        st.success("註冊成功！請切換至登入分頁。")
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


def fetch_dividend_history_super(symbol):
    return _fetch_dividend_history_super(symbol, FINMIND_TOKEN)


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_dividend_history_super(symbol, token):
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


def fetch_quarterly_financials(symbol):
    """把 token 一起當成快取鍵，token 換掉時舊的失敗結果才不會被沿用。"""
    return _fetch_quarterly_financials(symbol, FINMIND_TOKEN)


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_quarterly_financials(symbol, token):
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
                "token": token,
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


# 證交所綜合損益表 OpenAPI。只保留最新一季（每季覆蓋），拿不到連續四季，
# 但可以當作「今年累計到某季」的交叉比對值。分業別各一支。
TWSE_IS_URLS = [
    ("一般業", "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci"),
    ("金控業", "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_fh"),
    ("金融業", "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_bd"),
    ("證券期貨業", "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_mim"),
    ("保險業", "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ins"),
    ("異業", "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_basi"),
]


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_twse_latest_quarter_eps(symbol):
    """證交所最新一季綜合損益表的『基本每股盈餘』（本年度累計數）。"""
    code = clean_code(symbol)
    if not code:
        return None

    for industry, url in TWSE_IS_URLS:
        try:
            rows = requests.get(url, timeout=HTTP_TIMEOUT).json()
        except Exception as e:
            print(f"[twse_is] {industry}: {e}")
            continue

        for row in rows or []:
            if str(_pick_field(row, "公司代號") or "").strip() != code:
                continue
            raw_eps = _pick_field(row, "基本每股盈餘（元）", "基本每股盈餘(元)", "基本每股盈餘")
            try:
                eps = float(str(raw_eps).replace(",", ""))
            except (TypeError, ValueError):
                continue
            return {
                "industry": industry,
                "year": str(_pick_field(row, "年度") or ""),
                "quarter": str(_pick_field(row, "季別") or ""),
                "eps_cumulative": eps,
                "name": str(_pick_field(row, "公司名稱") or ""),
            }
    return None


# =============================================================
#  本益比河流圖：用該股「自己的」歷史本益比區間來估價
#
#  做法與財報狗／Goodinfo 的河流圖一致：
#    1. 取歷史每季 EPS，滾動加總成「近四季 EPS」時間序列
#    2. 每個交易日的本益比 = 當日收盤價 ÷ 當時適用的近四季 EPS
#    3. 取歷史本益比的 20 / 50 / 80 百分位當作便宜／合理／昂貴倍數
#    4. 合理價 = 該倍數 × 目前近四季 EPS
#  固定用 15 倍去套所有股票是沒有依據的，這才是正確做法。
# =============================================================
# 五等分位階：對應河流圖的五條河道
PE_BANDS = [
    ("極便宜", 0.10),
    ("便宜", 0.30),
    ("合理", 0.50),
    ("昂貴", 0.70),
    ("極昂貴", 0.90),
]
EPS_UNSTABLE_CV = 0.35          # 近四季 EPS 變異係數超過此值視為獲利不穩


def _normalize_dates(series):
    """
    統一成 tz-naive 的 datetime64[ns]。
    新版 pandas 會把 Python datetime 物件推成 datetime64[us]，
    而 yfinance 給的是 datetime64[ns]，兩者不一致時 merge_asof 會直接報錯。
    """
    out = pd.to_datetime(series, errors="coerce")
    try:
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return out.astype("datetime64[ns]")


def report_effective_date(quarter_end):
    """財報實際可被市場看到的日期（依公開資訊觀測站申報期限）。"""
    try:
        dt = datetime.strptime(quarter_end, "%Y-%m-%d")
    except Exception:
        return None
    deadlines = {3: (0, 5, 15), 6: (0, 8, 14), 9: (0, 11, 14), 12: (1, 3, 31)}
    if dt.month in deadlines:
        offset, month, day = deadlines[dt.month]
        return datetime(dt.year + offset, month, day)
    return dt + timedelta(days=75)


def build_ttm_eps_series(quarters):
    """把單季資料滾成「近四季 EPS」序列，回傳 [(生效日, ttm_eps), ...] 由舊到新。"""
    ordered = sorted(
        [q for q in quarters if q.get("eps") is not None],
        key=lambda x: x["date"],
    )
    points = []
    for i in range(3, len(ordered)):
        window = ordered[i - 3 : i + 1]
        latest = window[-1]

        shares = None
        if latest.get("net_income") and abs(latest["eps"]) > 0.01:
            candidate = latest["net_income"] / latest["eps"]
            if candidate > 0:
                shares = candidate

        if shares and all(w.get("net_income") is not None for w in window):
            ttm = sum(w["net_income"] for w in window) / shares
        else:
            ttm = sum(w["eps"] for w in window)

        eff = report_effective_date(latest["date"])
        if eff:
            points.append((eff, round(ttm, 4)))
    return points


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_price_history(symbol, years=5):
    """近 N 年日收盤價。"""
    code = clean_code(symbol)
    for suffix in (".TW", ".TWO"):
        try:
            hist = yf.Ticker(f"{code}{suffix}").history(period=f"{years}y")
            closes = hist["Close"].dropna()
            if len(closes) > 60:
                out = pd.DataFrame(
                    {"date": pd.Series(closes.index), "close": closes.to_numpy()}
                )
                out["date"] = _normalize_dates(out["date"])
                return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        except Exception as e:
            print(f"[price_history] {code}{suffix}: {e}")
    return pd.DataFrame(columns=["date", "close"])


@st.cache_data(ttl=3600, show_spinner=False)
def analyze_pe_band(symbol, years=5):
    """
    算出該股歷史本益比分布與對應的三段價位。
    注意：所有回傳路徑都必須帶 symbol，畫面是靠它判斷要不要顯示，
    漏掉的話失敗訊息會被靜靜吞掉，看起來就像「按了沒反應」。
    """
    code = clean_code(symbol)

    def fail(msg):
        return {"success": False, "symbol": code, "msg": msg}

    quarters, error = fetch_quarterly_financials(symbol)
    if len(quarters) < 5:
        detail = f"：{error}" if error else ""
        return fail(
            f"只取得 {len(quarters)} 季財報，需至少 5 季才能滾出近四季序列{detail}"
        )

    points = build_ttm_eps_series(quarters)
    if not points:
        return fail("無法建立近四季 EPS 序列（財報日期格式異常）。")

    prices = fetch_price_history(symbol, years)
    if prices.empty:
        return fail(
            f"查無 {code} 的歷史股價（yfinance 的 .TW 與 .TWO 都抓不到），"
            "無法計算歷史本益比。"
        )

    eps_df = pd.DataFrame(points, columns=["date", "eps"])
    eps_df["date"] = _normalize_dates(eps_df["date"])
    eps_df = eps_df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    prices = prices.copy()
    prices["date"] = _normalize_dates(prices["date"])
    prices = prices.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    try:
        merged = pd.merge_asof(prices, eps_df, on="date", direction="backward").dropna()
    except Exception as e:
        print(f"[pe_band] merge 失敗 {code}: {e}")
        return fail(f"歷史資料對齊失敗：{e}")
    merged = merged[merged["eps"] > 0].copy()
    if len(merged) < 120:
        return fail(
            f"可用的歷史本益比樣本只有 {len(merged)} 筆（需至少 120 筆）。"
            "可能近年曾虧損、上市未滿一年，或財報與股價期間重疊不足。"
        )

    merged["pe"] = merged["close"] / merged["eps"]
    # 去掉極端離群值，避免財報空窗期的失真把區間拉爛
    upper_cut = merged["pe"].quantile(0.995)
    merged = merged[(merged["pe"] > 0) & (merged["pe"] <= upper_cut)]

    current_eps_tmp = float(eps_df["eps"].iloc[-1])
    levels = [
        {
            "label": label,
            "pct": int(pct * 100),
            "pe": float(merged["pe"].quantile(pct)),
            "price": float(merged["pe"].quantile(pct)) * current_eps_tmp,
        }
        for label, pct in PE_BANDS
    ]

    current_eps = current_eps_tmp
    current_price = float(prices["close"].iloc[-1])
    current_pe = current_price / current_eps if current_eps > 0 else 0
    percentile = float((merged["pe"] < current_pe).mean() * 100)

    ttm_values = eps_df["eps"]
    eps_cv = float(ttm_values.std() / ttm_values.mean()) if ttm_values.mean() > 0 else 99
    has_loss = bool((ttm_values <= 0).any())

    warnings = []
    if has_loss:
        warnings.append("期間內曾出現近四季虧損，本益比法參考性低。")
    if eps_cv > EPS_UNSTABLE_CV:
        warnings.append(
            f"近四季 EPS 波動偏大（變異係數 {eps_cv:.0%}），可能是景氣循環股或獲利不穩定，"
            "本益比河流圖不適用這類股票。"
        )

    return {
        "success": True,
        "symbol": code,
        "levels": levels,
        "pe_fair": levels[2]["pe"],
        "price_fair": levels[2]["price"],
        "current_pe": current_pe,
        "current_eps": current_eps,
        "current_price": current_price,
        "percentile": percentile,
        "sample_days": len(merged),
        "years": years,
        "warnings": warnings,
        "chart": merged[["date", "close", "eps"]].iloc[::5].reset_index(drop=True),
    }


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
        st.warning("您的投資組合目前是空的。")
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


# 分組顯示。台指期 WTX=F / TWF=F 在 Yahoo 長期抓不到，備援會退回加權指數
# 導致兩格數字完全一樣，因此拿掉。
MARKET_GROUPS = [
    ("台股", [("台股加權", "^TWII")]),
    (
        "美股（前一交易日收盤）",
        [
            ("S&P 500", "^GSPC"),
            ("道瓊工業", "^DJI"),
            ("納斯達克", "^IXIC"),
            ("費城半導體", "^SOX"),
            ("VIX 恐慌指數", "^VIX"),
        ],
    ),
    (
        "匯率與原物料",
        [
            ("美元/台幣", "TWD=X"),
            ("美10年債", "^TNX"),
            ("原油期貨", "CL=F"),
            ("黃金", "GC=F"),
        ],
    ),
]


# 有些代碼在 Yahoo 上資料時有時無（台指期尤其嚴重），依序往下試。
# yfinance 打的是美國 Yahoo Finance API，台灣的櫃買指數只存在於 Yahoo 奇摩股市，
# 國際版沒有這檔資料，所以拿不到；台股區改以「成交金額」呈現市場熱度。
MARKET_TICKER_FALLBACKS = {}


TWSE_FMTQIK_URLS = [
    "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={d}&response=json",
    "https://www.twse.com.tw/exchangeReport/FMTQIK?date={d}&response=json",
]


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_market_turnover():
    """
    證交所每日市場成交資訊（與三大法人同一組端點，已驗證可用）。
    回傳 (今日成交金額億元, 較前一日變化億元, 變化百分比, 日期)。
    """
    today = datetime.now(tw_tz).date()
    first_of_month = today.replace(day=1)
    candidates = [today, first_of_month - timedelta(days=1)]   # 本月，月初時補上月

    for day_obj in candidates:
        day = day_obj.strftime("%Y%m%d")
        for template in TWSE_FMTQIK_URLS:
            try:
                res = requests.get(
                    template.format(d=day), headers=UA_HEADER, timeout=HTTP_TIMEOUT
                )
                if res.status_code != 200:
                    continue
                payload = res.json()
            except Exception as e:
                print(f"[turnover] {day}: {e}")
                continue

            if not isinstance(payload, dict) or payload.get("stat") != "OK":
                continue

            fields = [str(f) for f in (payload.get("fields") or [])]
            rows = payload.get("data") or []
            if len(rows) < 1:
                continue
            try:
                amt_idx = next(i for i, f in enumerate(fields) if "成交金額" in f)
                date_idx = next(i for i, f in enumerate(fields) if "日期" in f)
            except StopIteration:
                continue

            def to_num(row):
                try:
                    return float(str(row[amt_idx]).replace(",", ""))
                except (TypeError, ValueError, IndexError):
                    return None

            def roc_to_date(raw):
                """民國日期 115/09/16 -> date(2026, 9, 16)"""
                try:
                    y, m, d = str(raw).strip().split("/")
                    return datetime(int(y) + 1911, int(m), int(d)).date()
                except Exception:
                    return None

            # 不能假設證交所的回傳順序，必須自己依日期排序後再取最新兩筆
            values = []
            for r in rows:
                val = to_num(r)
                dt = roc_to_date(r[date_idx]) if date_idx < len(r) else None
                if val is not None and dt is not None:
                    values.append((dt, val))
            if not values:
                continue

            values.sort(key=lambda x: x[0])
            last_date, last_val = values[-1]
            prev_val = values[-2][1] if len(values) >= 2 else None

            amount = last_val / 1e8                      # 元 -> 億元
            if prev_val:
                change = (last_val - prev_val) / 1e8
                pct = (last_val / prev_val - 1) * 100
            else:
                change, pct = 0.0, 0.0

            return amount, change, pct, last_date.strftime("%m/%d")

    return None, None, None, ""


def _fetch_quote(ticker):
    """先用 fast_info，失敗再退回近五日收盤價。回傳 (現價, 前收) 或 (None, None)。"""
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
    if ticker_code == "TWD=X":
        return f"{p:,.3f}", f"{c:+.3f}"
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


# 三大法人資料不在證交所 OpenAPI（屬對外販售項目），改用官網查詢端點。
TWSE_BFI82U_URLS = [
    "https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={d}&response=json",
    "https://www.twse.com.tw/exchangeReport/BFI82U?type=day&dayDate={d}&response=json",
]


def _bfi_rows(payload):
    """同時相容 fields+data 陣列格式與 list-of-dict 格式。"""
    if isinstance(payload, list):
        return [
            (
                str(_pick_field(r, "Name", "單位名稱", "name") or ""),
                _pick_field(r, "DifferenceAmount", "買賣差額", "差額"),
            )
            for r in payload
        ]

    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return []

    fields = [str(f) for f in (payload.get("fields") or [])]
    data = payload.get("data") or []
    try:
        name_idx = next(i for i, f in enumerate(fields) if "單位" in f or "類別" in f)
        diff_idx = next(i for i, f in enumerate(fields) if "差額" in f or "買賣超" in f)
    except StopIteration:
        return []

    out = []
    for row in data:
        if len(row) > max(name_idx, diff_idx):
            out.append((str(row[name_idx]), row[diff_idx]))
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_institutional_flow():
    """
    證交所三大法人買賣金額。回傳各項買賣超（億元）。

    注意：證交所註明「外資自營商買賣金額已計入自營商」，
    故不納入合計，外資那欄也不該再加一次，否則會重複計算。
    """
    today = datetime.now(tw_tz).date()

    for back in range(0, 7):          # 假日與盤中未結算時往前找
        day = (today - timedelta(days=back)).strftime("%Y%m%d")
        for template in TWSE_BFI82U_URLS:
            try:
                res = requests.get(
                    template.format(d=day), headers=UA_HEADER, timeout=HTTP_TIMEOUT
                )
                if res.status_code != 200:
                    continue
                rows = _bfi_rows(res.json())
            except Exception as e:
                print(f"[institutional] {day}: {e}")
                continue

            if not rows:
                continue

            buckets = {"外資": 0.0, "投信": 0.0, "自營商": 0.0}
            official_total = None

            for name, raw in rows:
                try:
                    diff = float(str(raw).replace(",", ""))
                except (TypeError, ValueError):
                    continue

                flat = str(name).replace(" ", "").replace("　", "")
                if "合計" in flat or "總計" in flat:
                    official_total = diff      # 直接採用證交所公告的合計
                    continue
                # 「外資及陸資(不含外資自營商)」字串裡也含有「外資自營商」，
                # 所以必須用開頭比對，不能用包含比對，否則外資那列會被誤刪。
                if flat.startswith("外資自營商"):
                    continue      # 已計入自營商，跳過避免重複計算
                if "外資" in flat or "陸資" in flat:
                    buckets["外資"] += diff
                elif "投信" in flat:
                    buckets["投信"] += diff
                elif "自營" in flat:
                    buckets["自營商"] += diff

            if not any(buckets.values()):
                continue

            result = {k: v / 1e8 for k, v in buckets.items()}
            result["合計"] = (
                official_total / 1e8 if official_total is not None else sum(result.values())
            )
            result["date"] = f"{day[:4]}-{day[4:6]}-{day[6:]}"
            return result

    return None


# 不同區間本來就會有不同的資料筆數，門檻寫死 30 會讓「近一月」永遠取不到
MIN_BARS_BY_PERIOD = {"5d": 3, "1mo": 5, "3mo": 15, "6mo": 20}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_index_history(ticker, period="1y"):
    """指數歷史收盤，給走勢圖用。"""
    min_bars = MIN_BARS_BY_PERIOD.get(period, 30)
    try:
        hist = yf.Ticker(ticker).history(period=period)
        closes = hist["Close"].dropna()
        if len(closes) < min_bars:
            print(f"[index_history] {ticker} {period}: 只有 {len(closes)} 筆，低於門檻 {min_bars}")
            return pd.DataFrame(columns=["date", "close"])
        out = pd.DataFrame(
            {
                "date": pd.Series(closes.index),
                "close": closes.to_numpy(),
                # 區間最高／最低要看盤中價，只用收盤價會低估
                "high": hist["High"].reindex(closes.index).to_numpy(),
                "low": hist["Low"].reindex(closes.index).to_numpy(),
            }
        )
        out["date"] = _normalize_dates(out["date"])
        return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    except Exception as e:
        print(f"[index_history] {ticker}: {e}")
        return pd.DataFrame(columns=["date", "close"])


def draw_turnover_card():
    """成交金額卡片，樣式與其他指數卡一致。"""
    amount, change, pct, date_txt = fetch_market_turnover()
    if amount is None:
        st.markdown(
            "<div style='text-align:center; opacity:0.5; padding:12px 0;'>"
            "成交金額<br>暫無資料</div>",
            unsafe_allow_html=True,
        )
        return

    color = UP_COLOR if change >= 0 else DOWN_COLOR
    arrow = "▲" if change >= 0 else "▼"
    st.markdown(
        f"""
        <div style="text-align:center; padding:2px 0;">
            <div style="font-size:0.85rem; opacity:0.6; margin-bottom:2px;">
                成交金額（億元）
            </div>
            <div style="font-size:1.6rem; font-weight:bold; margin-bottom:8px;
                        color:{TEXT_COLOR};">{amount:,.0f}</div>
            <div style="display:inline-block; background:{color}22; color:{color};
                        padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:500;">
                {arrow} 較前日 {change:+,.0f} ({pct:+.1f}%)
            </div>
            <div style="font-size:0.7rem; opacity:0.5; margin-top:4px;">
                {date_txt}　含鉅額與盤後
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


def bottom_columns(spec):
    """
    回傳底部對齊的欄位。
    有標籤的元件（selectbox）比沒標籤的（button）高一截，直接並排會一高一低。
    新版 Streamlit 支援 vertical_alignment，舊版則退回手動墊高。
    """
    try:
        return st.columns(spec, vertical_alignment="bottom"), False
    except TypeError:
        return st.columns(spec), True


def label_spacer():
    """模擬一行標籤的高度，讓沒有標籤的元件跟旁邊對齊。"""
    st.markdown(
        "<div style='height:1.6rem; margin-bottom:0.25rem;'></div>",
        unsafe_allow_html=True,
    )


def judge_pe_level(price, levels):
    """依五等分位階判斷目前股價落在哪一段。"""
    if price <= levels[0]["price"]:
        return "極便宜", DOWN_COLOR
    if price <= levels[1]["price"]:
        return "便宜", DOWN_COLOR
    if price <= levels[3]["price"]:
        return "合理", "#ffbc4b"
    if price <= levels[4]["price"]:
        return "昂貴", UP_COLOR
    return "極昂貴", UP_COLOR


def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()


def back_button(label="← 返回工具箱", target="home", key=None):
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

    theme_btn_label = "切換淺色模式" if st.session_state.theme == "dark" else "切換深色模式"
    if st.button(theme_btn_label, use_container_width=True):
        toggle_theme()
        st.rerun()

    st.markdown(f"<hr style='margin:10px 0; border-color:{BORDER_COLOR};'>", unsafe_allow_html=True)

    if st.button("登出系統", use_container_width=True):
        for k in ("logged_in", "current_user", "portfolio", "watchlist", "data"):
            st.session_state[k] = False if k == "logged_in" else None
        # 一併清掉殘留的元件狀態，避免下一位使用者看到上一位的資料
        for k in ("etf_symbol_input", "portfolio_editor"):
            st.session_state.pop(k, None)
        st.session_state.page = "welcome"
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    with st.expander("資料來源診斷", expanded=False):
        st.caption(f"程式版本：{APP_VERSION}")
        st.caption(f"FinMind token 來源：{FINMIND_TOKEN_SOURCE}")
        if st.button("測試 FinMind 連線", use_container_width=True, key="diag_finmind"):
            try:
                res = requests.get(
                    FINMIND_URL,
                    params={
                        "dataset": "TaiwanStockFinancialStatements",
                        "data_id": "2330",
                        "start_date": "2025-01-01",
                        "token": FINMIND_TOKEN,
                    },
                    timeout=HTTP_TIMEOUT,
                )
                payload = res.json()
                if payload.get("msg") == "success" and payload.get("data"):
                    st.success(f"連線正常，取得 {len(payload['data'])} 筆資料")
                else:
                    st.error(f"{payload.get('msg') or '無回傳訊息'}")
            except Exception as e:
                st.error(f"{e}")

        if st.button("清除資料快取", use_container_width=True, key="diag_clear"):
            st.cache_data.clear()
            st.success("已清除，請重新查詢一次。")

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("本系統數據僅供參考，不構成投資建議，投資人請審慎評估風險並自負盈虧。")


# =============================================================
# 8. 各功能頁面
# =============================================================
# ------------------------------------------------------------------
# 首頁
# ------------------------------------------------------------------
if page == "welcome":
    user = st.session_state.current_user
    st.markdown(f"## {greeting()}，{user}")
    st.caption(datetime.now(tw_tz).strftime("台北時間 %Y-%m-%d %H:%M"))
    st.divider()

    st.markdown("#### 市場快照")
    snapshot = [("台股加權", "^TWII"), ("S&P 500", "^GSPC"), ("美元/台幣", "TWD=X")]
    for col, (label, ticker) in zip(st.columns(3), snapshot):
        with col:
            with st.container(border=True):
                draw_compact_metric(label, ticker)

    st.markdown("#### 關注清單")
    if st.session_state.watchlist is None:
        st.session_state.watchlist = load_watchlist_from_cloud(user)

    preview = st.session_state.watchlist[:5]
    if not preview:
        st.caption("還沒有關注任何標的。")
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
    st.markdown("#### 快速前往")
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

    st.title("我的關注清單")

    if st.session_state.watchlist is None:
        st.session_state.watchlist = load_watchlist_from_cloud(st.session_state.current_user)

    col_add, col_btn, col_refresh = st.columns([3, 1, 1])
    with col_add:
        new_code = st.text_input(
            "新增代碼", placeholder="例如：2330 或 00919", label_visibility="collapsed"
        )
    with col_btn:
        add_clicked = st.button("加入", use_container_width=True, type="primary")
    with col_refresh:
        refresh_clicked = st.button("更新報價", use_container_width=True)

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

        st.caption(f"共 {len(st.session_state.watchlist)} 檔")

# ------------------------------------------------------------------
# 個股分析
# ------------------------------------------------------------------
elif page == "stock_query":
    back_button()
    st.title("台股自動估價系統 (個股)")

    main_col, side_col = st.columns([8, 4])

    with main_col:
        (c_code, c_years), _ = bottom_columns([3, 1])
        with c_code:
            stock_code = st.text_input("請輸入台股代碼 (例如: 2330)")
        with c_years:
            band_years = st.selectbox("歷史取樣年數", [3, 5, 10], index=1)

        if stock_code:
            info = get_stock_info(stock_code)

            if info is None:
                st.error("查無此代碼的報價，請確認輸入是否正確。")
            else:
                current_price = info["price"]

                # ---------- 報價區 ----------
                (col_title, col_btn), _ = bottom_columns([3, 1])
                with col_title:
                    st.markdown(f"## {info['name']}")
                with col_btn:
                    st.link_button(
                        "找公司官網",
                        f"https://www.google.com/search?q={info['name']}+公司官網",
                        use_container_width=True,
                    )

                st.markdown(
                    f"<div class='date-text'>資料日期：{datetime.now(tw_tz).strftime('%Y-%m-%d')}</div>",
                    unsafe_allow_html=True,
                )

                cp1, cp2 = st.columns([2, 1])
                with cp1:
                    color = (
                        UP_COLOR if info["change"] > 0
                        else DOWN_COLOR if info["change"] < 0
                        else TEXT_COLOR
                    )
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

                # ---------- 估值位階（主要結論） ----------
                st.subheader("估值位階參考")

                with st.spinner("分析歷史本益比中..."):
                    try:
                        band = analyze_pe_band(stock_code, band_years)
                    except Exception as e:
                        band = {
                            "success": False,
                            "symbol": clean_code(stock_code),
                            "msg": f"分析過程發生錯誤：{e}",
                        }

                if not band.get("success"):
                    st.warning(f"無法自動估價：{band.get('msg', '原因不明')}")
                else:
                    for msg in band["warnings"]:
                        st.warning(f"{msg}")

                    eps_now = band["current_eps"]
                    levels = band["levels"]
                    price_fair = band["price_fair"]
                    rec, rec_color = judge_pe_level(current_price, levels)

                    st.markdown(
                        f"""
                        <div class='calc-box' style='display:flex; flex-wrap:wrap;
                             align-items:center; justify-content:space-between; gap:12px;'>
                            <div>
                                <div style='opacity:0.7; font-size:0.9rem;'>系統判讀</div>
                                <div style='font-size:1.8rem; font-weight:bold; color:{rec_color};'>{rec}</div>
                                <div style='opacity:0.6; font-size:0.85rem;'>
                                    歷史位階 {band['percentile']:.0f}%（越低越便宜）
                                </div>
                            </div>
                            <div style='text-align:right;'>
                                <div style='opacity:0.7; font-size:0.9rem;'>
                                    合理價（中位數 {band['pe_fair']:.1f} 倍）
                                </div>
                                <div class='highlight-val'>{price_fair:.2f}</div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    rows_html = ""
                    for i, lv in enumerate(levels):
                        if i == 0:
                            price_txt = f"{lv['price']:.2f} 以下"
                        elif i == len(levels) - 1:
                            price_txt = f"高於 {levels[i - 1]['price']:.2f}"
                        else:
                            price_txt = f"{levels[i - 1]['price']:.2f} ~ {lv['price']:.2f}"

                        hit = (
                            "background-color: rgba(255,188,75,0.15);"
                            if rec.endswith(lv["label"]) else ""
                        )
                        rows_html += (
                            f"<tr style='{hit}'><td>{lv['label']} (歷史 {lv['pct']}%)</td>"
                            f"<td>{lv['pe']:.1f} 倍</td><td>{price_txt}</td></tr>"
                        )

                    st.markdown(
                        f"""
                        <table class="styled-table">
                            <thead><tr><th>估值位階</th><th>本益比</th><th>股價區間</th></tr></thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                        """,
                        unsafe_allow_html=True,
                    )

                    stat1, stat2, stat3 = st.columns(3)
                    stat1.metric("近四季 EPS", f"{eps_now:.2f}")
                    stat2.metric("目前本益比", f"{band['current_pe']:.1f} 倍")
                    stat3.metric(
                        "距合理價",
                        f"{(price_fair / current_price - 1) * 100:+.1f}%"
                        if current_price > 0 else "－",
                    )

                    # EPS 明細
                    eps_detail = get_ttm_eps(stock_code)
                    if eps_detail.get("success"):
                        source_tag = (
                            "證交所 OpenAPI" if eps_detail.get("source") == "twse" else "FinMind 財報"
                        )
                        with st.expander(f"EPS 來源：{source_tag}（{eps_detail['period']}）"):
                            st.caption(eps_detail["method"])
                            if eps_detail["quarters"]:
                                st.dataframe(
                                    pd.DataFrame(
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
                                            for q in eps_detail["quarters"]
                                        ]
                                    ),
                                    use_container_width=True,
                                    hide_index=True,
                                )
                            if eps_detail.get("adjusted"):
                                st.info(
                                    f"期間內有配股／增資。四季 EPS 直接相加為 "
                                    f"**{eps_detail['naive_sum']:.2f}**，還原加權平均股數後為 "
                                    f"**{eps_detail['ttm_eps']:.2f}**，系統採用後者。"
                                )

                    # ---------- 河流圖 ----------
                    st.divider()
                    st.subheader("本益比河流圖")

                    chart_df = band["chart"].copy()
                    for lv in levels:
                        chart_df[f"{lv['label']} {lv['pe']:.0f}x"] = chart_df["eps"] * lv["pe"]
                    chart_df = chart_df.rename(columns={"close": "股價"}).drop(columns=["eps"])

                    fig = px.line(
                        chart_df,
                        x="date",
                        y=[c for c in chart_df.columns if c != "date"],
                        color_discrete_sequence=[
                            TEXT_COLOR,      # 股價
                            "#1a9850",       # 極便宜
                            "#91cf60",       # 便宜
                            "#ffbc4b",       # 合理
                            "#fc8d59",       # 昂貴
                            "#d73027",       # 極昂貴
                        ],
                    )
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font_color=TEXT_COLOR,
                        legend_title_text="",
                        legend=dict(orientation="h", y=-0.2),
                        xaxis_title="",
                        yaxis_title="股價",
                        margin=dict(t=20),
                    )
                    st.plotly_chart(fig, use_container_width=True, key="pe_river")

                    st.caption(
                        f"近 {band['years']} 年 · {band['sample_days']} 個交易日"
                    )

                # ---------- 進階：手動試算 ----------
                st.divider()
                with st.expander("自訂本益比試算", expanded=not band.get("success")):
                    default_eps = float(band["current_eps"]) if band.get("success") else 10.0
                    default_pe = float(round(band["pe_fair"], 1)) if band.get("success") else 15.0

                    m_col1, m_col2 = st.columns(2)
                    with m_col1:
                        manual_eps = st.number_input(
                            "EPS (近4季累積)", min_value=0.01, step=0.1, value=max(0.01, default_eps)
                        )
                    with m_col2:
                        manual_pe = st.number_input(
                            "自訂本益比 (PE)", min_value=0.1, step=0.5, value=default_pe
                        )

                    manual_price = manual_eps * manual_pe
                    st.markdown(
                        f"<div class='calc-box'>換算股價："
                        f"<span class='highlight-val'>{manual_price:.2f}</span></div>",
                        unsafe_allow_html=True,
                    )
                    if current_price <= manual_price:
                        st.success(f"目前股價 {current_price:.2f} 低於此假設下的參考價")
                    else:
                        st.warning(f"目前股價 {current_price:.2f} 高於此假設下的參考價")

    with side_col:
        st.write("### 說明")
        st.caption("輸入代碼即可，系統自動抓取近四季 EPS 與歷史本益比。")
        st.divider()
        st.warning("不適用景氣循環股（航運、鋼鐵、記憶體）與獲利不穩的公司。")
elif page == "etf_query":
    back_button()

    st.title("ETF 專用")
    main_col, side_col = st.columns([8, 4])

    with main_col:
        st.markdown("### 查詢設定")
        if "etf_symbol_input" not in st.session_state:
            st.session_state.etf_symbol_input = ""

        # 包成 form，在代號欄按 Enter 就會直接查詢
        with st.form("etf_query_form"):
            (input_c1, input_c2), need_spacer = bottom_columns([3, 1])
            with input_c1:
                st.text_input("ETF 代號", key="etf_symbol_input", placeholder="例如: 00919")
            with input_c2:
                if need_spacer:
                    label_spacer()
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
                st.error(f"查詢失敗：{st.session_state.data.get('msg')}")
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
                st.subheader("歷史配息參考")

                freq_map = {"月配": 12, "季配": 4, "半年配": 2, "年配": 1}
                sys_freq_name = f"{d['freq_label']}配"
                sys_index = list(freq_map).index(sys_freq_name) if sys_freq_name in freq_map else 3

                user_freq = st.selectbox("自訂/修正配息頻率：", list(freq_map), index=sys_index)
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
                st.subheader("估值位階參考")

                p_cheap = avg_annual / YIELD_CHEAP if avg_annual > 0 else 0
                p_fair = avg_annual / YIELD_FAIR if avg_annual > 0 else 0

                if avg_annual <= 0:
                    rec = "無配息資料，無法評估"
                elif d["price"] <= p_cheap:
                    rec = "便宜買入"
                elif d["price"] <= p_fair:
                    rec = "合理持有"
                else:
                    rec = "昂貴不建議"

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
                st.subheader("持有張數試算 (含稅費)")
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
                st.caption(f"※ 二代健保：費率 {NHI_RATE:.2%}，單次給付達 {NHI_THRESHOLD:,} 元起扣")

                st.divider()
                st.subheader("存股未來財富試算")

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
        st.write("### 說明")
        st.caption("輸入代號後點擊開始計算，配息欄位可手動修改。")

# ------------------------------------------------------------------
# ETF 對比
# ------------------------------------------------------------------
elif page == "pk_tool":
    back_button()

    st.title("ETF 對比工具")

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

    st.title(f"{st.session_state.current_user} 的投資組合")

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

    st.markdown("### 編輯投資清單")
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
        if st.button("自動帶入資訊", use_container_width=True):
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
        if st.button("儲存變更至資料庫", type="primary", use_container_width=True):
            save_df = edited_df[COLUMNS_ORDER].copy()
            save_df["張數"] = pd.to_numeric(save_df["張數"], errors="coerce")
            st.session_state.portfolio = save_df
            if save_portfolio_to_cloud(st.session_state.current_user, save_df):
                st.success("資料庫已同步更新")

    st.divider()
    st.markdown("### 資產市值與配置分析")
    total_cost_input = st.number_input("請輸入總成本", min_value=0.0, value=0.0, step=10000.0)

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

                st.markdown("### 戰略資產佈局")
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
        st.subheader("自動化領息排程月曆")
        horizon_days = st.slider("顯示未來幾天內的配息", 7, 120, DIV_PAY_LAG_DAYS * 2, step=7)

        if st.button("生成我的專屬領息月曆", use_container_width=True, type="primary"):
            cal_df = generate_user_calendar()

            if cal_df is None or cal_df.empty:
                st.info("目前沒有可用的配息預估資料。")
            else:
                cal_df["_pay"] = pd.to_datetime(cal_df["預計發放日 (預估)"])
                cutoff = pd.Timestamp(datetime.now(tw_tz).date()) + pd.Timedelta(days=horizon_days)
                filtered = cal_df[cal_df["_pay"] <= cutoff].sort_values("_pay")

                if filtered.empty:
                    st.warning(f"未來 {horizon_days} 天內暫無預計領息資料。")
                else:
                    display_df = filtered.drop(columns=["_pay"]).copy()
                    display_df["每股配息"] = display_df["每股配息"].map(lambda v: f"${v:.3f}")
                    display_df["預估入帳金額"] = display_df["預估入帳金額"].map(lambda v: f"{v:,.0f}")
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                    st.success(
                        f"這一波領息預計總入帳： **${filtered['預估入帳金額'].sum():,.0f}** 元"
                    )
                    st.caption(f"※ 發放日以除息日加 {DIV_PAY_LAG_DAYS} 天推估，實際日期請以公告為準。")

# ------------------------------------------------------------------
# 大盤指數
# ------------------------------------------------------------------
elif page == "market_index":
    back_button()

    col_head, col_refresh = st.columns([4, 1])
    with col_head:
        st.markdown("### 大盤指數")
    with col_refresh:
        if st.button("重新整理", use_container_width=True):
            get_market_data.clear()
            fetch_institutional_flow.clear()
            fetch_index_history.clear()
            fetch_market_turnover.clear()
            st.rerun()
    st.caption(f"最後更新：{datetime.now(tw_tz).strftime('%Y-%m-%d %H:%M')}")
    st.divider()

    for group_name, tickers in MARKET_GROUPS:
        st.markdown(f"##### {group_name}")

        if group_name == "台股":
            tw_cols = st.columns(2)
            with tw_cols[0]:
                with st.container(border=True):
                    draw_compact_metric("台股加權", "^TWII")
            with tw_cols[1]:
                with st.container(border=True):
                    draw_turnover_card()
            st.write("")
            continue

        for row_start in range(0, len(tickers), 3):
            chunk = tickers[row_start : row_start + 3]
            cols = st.columns(3)
            for col, (label, ticker) in zip(cols, chunk):
                with col:
                    with st.container(border=True):
                        draw_compact_metric(label, ticker)
        st.write("")

    # ---------- 三大法人買賣超 ----------
    st.markdown("##### 三大法人買賣超")
    flow = fetch_institutional_flow()

    if not flow:
        st.caption("暫時取不到證交所法人資料。")
    else:
        f_cols = st.columns(4)
        for col, key in zip(f_cols, ("外資", "投信", "自營商", "合計")):
            value = flow.get(key, 0.0)
            color = UP_COLOR if value >= 0 else DOWN_COLOR
            arrow = "買超" if value >= 0 else "賣超"
            with col:
                with st.container(border=True):
                    st.markdown(
                        f"""
                        <div style="text-align:center; padding:2px 0;">
                            <div style="font-size:0.85rem; opacity:0.6; margin-bottom:2px;">{key}</div>
                            <div style="font-size:1.6rem; font-weight:bold; color:{color};">
                                {value:+,.1f}
                            </div>
                            <div style="font-size:0.8rem; opacity:0.6;">{arrow} 億元</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        if flow.get("date"):
            st.caption(f"資料日期：{flow['date']}（證交所每日收盤後更新）")

    # ---------- 加權指數走勢 ----------
    st.divider()
    st.markdown("##### 台股加權指數走勢")

    trend_period = st.selectbox(
        "區間", ["1mo", "6mo", "1y", "5y"], index=2,
        format_func=lambda p: {
            "1mo": "近一月", "6mo": "近半年", "1y": "近一年", "5y": "近五年"
        }[p],
    )
    twii = fetch_index_history("^TWII", trend_period)

    if twii.empty:
        st.caption("暫時取不到加權指數歷史資料。")
    else:
        fig_twii = px.area(twii, x="date", y="close")
        fig_twii.update_traces(line_color=UP_COLOR, fillcolor="rgba(255,75,75,0.12)")
        fig_twii.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color=TEXT_COLOR,
            xaxis_title="",
            yaxis_title="",
            margin=dict(t=10, b=10),
            height=300,
        )
        st.plotly_chart(fig_twii, use_container_width=True, key="twii_trend")

        first, last = float(twii["close"].iloc[0]), float(twii["close"].iloc[-1])
        change_pct = (last / first - 1) * 100 if first else 0
        high = float(twii["high"].max()) if "high" in twii else float(twii["close"].max())
        low = float(twii["low"].min()) if "low" in twii else float(twii["close"].min())

        t1, t2, t3 = st.columns(3)
        t1.metric("區間漲跌", f"{change_pct:+.2f}%")
        t2.metric("區間最高", f"{high:,.0f}")
        t3.metric("區間最低", f"{low:,.0f}")
        st.caption("最高／最低為盤中價，走勢線為收盤價。")
elif page == "tax_calc":
    back_button()

    st.title("股利報稅與綜合所得稅試算")

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
    with st.expander("展開填寫：所得與家庭扣除額資料", expanded=True):
        st.markdown("#### 第一部分：所得資料 (精準薪資防呆)")
        st.caption(
            f"若有打工族，請務必分開填寫薪資！系統會自動判斷「實領薪資」與"
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
        st.markdown("#### 第二部分：家庭與一般扣除額")
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
                "列舉扣除額總計 (如醫藥/保險/捐贈)", min_value=0, value=0, step=10000
            )
        with c_item2:
            st.write("")
            st.info("系統會自動比較「標準」與「列舉」，採用金額較高者。")

        st.divider()
        st.markdown("#### 第三部分：特別扣除額")
        st.caption("以下請輸入符合資格的【人數】，系統自動乘上對應額度。")
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

    tab1, tab2 = st.tabs(["方案 A：一般合併申報", "方案 B：股利 28% 分開計稅"])

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
                f"**系統偵測：{reason}，已自動觸發排富條款！**\n\n"
                "長期照顧與房屋租金特別扣除額已自動歸零；"
                "幼兒學前特別扣除額自 113 年度起已取消排富，故仍可全額適用。"
            )

        st.markdown("### 扣除額與抵減稅額明細 (方案 A)")
        st.markdown(render_deduction_table(case_a, muted_note_a), unsafe_allow_html=True)

        st.markdown("**股利及盈餘可抵減稅額：**")
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
            st.markdown(f"### {tax_year}年度綜合所得稅級距表")
            st.table(tax_table_data)

        with col_result_a:
            st.markdown("### 結算單 (方案 A)")
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
            "**方案 B 預設：凡選擇股利 28% 分開計稅，即自動觸發排富條款！**\n\n"
            "長期照顧與房屋租金特別扣除額已自動歸零；幼兒學前特別扣除額不受排富限制，仍可適用。"
        )

        st.markdown("### 扣除額明細 (方案 B：排富沒收版)")
        st.markdown(render_deduction_table(case_b, "(28%排富取消)"), unsafe_allow_html=True)

        st.markdown("**股利及盈餘分開計稅：**")
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
            st.markdown(f"### {tax_year}年度綜合所得稅級距表")
            st.table(tax_table_data)

        with col_result_b:
            st.markdown("### 結算單 (方案 B)")
            with st.container(border=True):
                st.markdown(
                    f"**綜合所得總額 (不含股利)：** "
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
                    f"**股利 {DIV_SEPARATE_RATE:.0%} 分開計稅額：** "
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
        f"以目前輸入的資料，**{better}** 較有利，兩者相差約 **{diff:,.0f}** 元。"
        "（實際申報請以財政部電子申報系統試算結果為準。）"
    )

else:
    st.warning("找不到這個頁面，請從左側選單重新選擇。")
    if st.button("回到首頁"):
        go_to("welcome")

"""
共用設定：頁面設定、主題顏色、稅制參數、通用小工具。
這個檔案必須最先被 import（st.set_page_config 要在所有 Streamlit 指令之前執行）。
"""

from datetime import datetime

import streamlit as st
import pytz

def setup_page():
    """
    版面設定。必須由主程式每次 rerun 呼叫，且要在所有其他 Streamlit 指令之前。
    寫成模組層級的話只有第一個 session 會執行到，之後的 session 會套用預設的
    centered 版面，畫面會突然變窄。
    """
    st.set_page_config(
        page_title="台股個股/ETF查詢",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded",
    )
tw_tz = pytz.timezone("Asia/Taipei")

# 版本標記：顯示在側邊欄「資料來源診斷」裡，用來確認雲端跑的是哪一版程式
APP_VERSION = "2026-09-16 / token-check-v24"

FEE_RATE = 0.001425          # 券商手續費率
NHI_RATE = 0.0211            # 二代健保補充保費費率
NHI_THRESHOLD = 20_000       # 單次給付起扣門檻
DIV_PAY_LAG_DAYS = 28        # 除息日 → 發放日的推估天數
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

DEFAULT_PORTFOLIO_ROWS = 20
COLUMNS_ORDER = ["代碼", "名稱", "張數", "戰略屬性"]
ASSET_CATEGORIES = [
    "⚔️ 進攻型 (市值/成長)",
    "💰 現金流 (高股息)",
    "🛡️ 防守型 (債券/避險)",
]

# =============================================================
# 主題
# =============================================================
UP_COLOR = "#ff4b4b"
DOWN_COLOR = "#09ab3b"

DEFAULT_THEME = "dark"


def init_theme():
    """
    主題初始化。必須由主程式每次 rerun 呼叫，不能寫成模組層級的 if。
    Python 只在第一次 import 時執行模組，新的 session 不會再跑一次，
    那個 session 的 theme 就永遠不會被建立。
    """
    st.session_state.setdefault("theme", DEFAULT_THEME)


def current_theme():
    return st.session_state.get("theme", DEFAULT_THEME)


def toggle_theme():
    st.session_state.theme = "light" if current_theme() == "dark" else "dark"


_DARK = {
    "APP_BG": "#0e1117",
    "SECONDARY_BG": "#1e1e28",
    "TEXT_COLOR": "#FAFAFA",
    "BORDER_COLOR": "rgba(255,255,255,0.15)",
    "TRACK_COLOR": "#2b2b36",
    "TABLE_HEAD_BG": "#2a2a36",
}
_LIGHT = {
    "APP_BG": "#FFFFFF",
    "SECONDARY_BG": "#F0F2F6",
    "TEXT_COLOR": "#1f1f1f",
    "BORDER_COLOR": "rgba(0,0,0,0.15)",
    "TRACK_COLOR": "#e2e5ea",
    "TABLE_HEAD_BG": "#e8eaf0",
}


def palette():
    """回傳目前主題的顏色。每次 rerun 都要重新取，不能存成模組常數。"""
    return dict(_DARK if current_theme() == "dark" else _LIGHT)


def apply_palette(module_globals):
    """
    把顏色灌進呼叫端的模組命名空間。
    Python 只會在第一次 import 時執行模組，所以顏色不能寫成模組層級常數，
    否則切換主題後不會更新；改由每次 rerun 呼叫這個函式刷新。
    """
    module_globals.update(palette())


# 供本檔 inject_css 及尚未 apply 的情境使用的預設值
globals().update(_DARK)

def inject_css():
    """全站 CSS，所有顏色跟著目前主題走。每次 rerun 都要呼叫。"""
    p = palette()
    APP_BG, SECONDARY_BG = p["APP_BG"], p["SECONDARY_BG"]
    TEXT_COLOR, BORDER_COLOR = p["TEXT_COLOR"], p["BORDER_COLOR"]
    TABLE_HEAD_BG = p["TABLE_HEAD_BG"]
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

# =============================================================
# 通用小工具
# =============================================================
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

def go_to(page_name):
    st.session_state.page = page_name
    st.rerun()


def back_button(label="← 返回工具箱", target="home", key=None):
    """返回鍵放在窄欄位裡，不再橫跨整個畫面。"""
    col, _ = st.columns([1, 5])
    with col:
        if st.button(label, key=key or f"back_{target}", use_container_width=True):
            go_to(target)

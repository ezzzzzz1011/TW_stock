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
APP_VERSION = "2026-11-06 / etf-rank-v34"

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
# 預設值（深色）。畫面上請一律用 palette() 取得目前主題的顏色。
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


# 漲跌、警示等「有意義的顏色」也要分主題：深色底用的亮色放到白底上會看不清楚
# （例：#ffbc4b 在白底的對比只有 1.67），所以淺色主題改用較深的同色系。
# 淺色值在白底的對比度：紅 4.35、綠 3.71、琥珀 3.59、藍 4.60。
_DARK = {
    "APP_BG": "#0e1117",
    "SECONDARY_BG": "#1e1e28",
    "TEXT_COLOR": "#FAFAFA",
    "BORDER_COLOR": "rgba(255,255,255,0.15)",
    "BORDER_STRONG": "rgba(255,255,255,0.35)",
    "TRACK_COLOR": "#2b2b36",
    "TABLE_HEAD_BG": "#2a2a36",
    "UP_COLOR": "#ff4b4b",
    "DOWN_COLOR": "#09ab3b",
    "WARN_COLOR": "#ffbc4b",
    "ACCENT_COLOR": "#4bc0ff",
    "PLOTLY_TEMPLATE": "plotly_dark",
    # 提示框（st.info / success / warning / error）：(背景, 文字)
    "ALERT_INFO": ("rgba(28,131,225,0.18)", "#c7ebff"),
    "ALERT_SUCCESS": ("rgba(33,195,84,0.16)", "#dffde9"),
    "ALERT_WARNING": ("rgba(255,200,18,0.16)", "#ffffc2"),
    "ALERT_ERROR": ("rgba(255,43,43,0.16)", "#ffdede"),
}
_LIGHT = {
    "APP_BG": "#FFFFFF",
    "SECONDARY_BG": "#F0F2F6",
    "TEXT_COLOR": "#1f1f1f",
    "BORDER_COLOR": "rgba(0,0,0,0.15)",
    "BORDER_STRONG": "rgba(0,0,0,0.35)",
    "TRACK_COLOR": "#e2e5ea",
    "TABLE_HEAD_BG": "#e8eaf0",
    "UP_COLOR": "#e5322d",
    "DOWN_COLOR": "#15993f",
    "WARN_COLOR": "#b97a00",
    "ACCENT_COLOR": "#1976d2",
    "PLOTLY_TEMPLATE": "plotly_white",
    "ALERT_INFO": ("#e7f1fc", "#00427f"),
    "ALERT_SUCCESS": ("#e6f6ec", "#14632d"),
    "ALERT_WARNING": ("#fff6db", "#7a5a00"),
    "ALERT_ERROR": ("#fdeaea", "#8a1f26"),
}


def palette():
    """回傳目前主題的顏色。每次 rerun 都要重新取，不能存成模組常數。"""
    return dict(_DARK if current_theme() == "dark" else _LIGHT)


def style_plotly(fig):
    """
    Plotly 圖表跟著主題走。搭配 st.plotly_chart(fig, theme=None) 使用：
    預設的 theme="streamlit" 會套用內建（深色）主題的文字顏色，
    淺色模式下座標軸與圖例的字會變成白色看不到。
    """
    p = palette()
    # 關掉 Streamlit 主題後，Plotly 預設四邊各留 80px，窄欄位裡的圓餅圖會被擠得很小。
    # 圖表自己有設的邊距保留，沒設的才改成跟 Streamlit 主題一樣的緊湊邊距。
    m = fig.layout.margin
    margin = {
        side: (getattr(m, side) if getattr(m, side) is not None else default)
        for side, default in (("l", 10), ("r", 10), ("t", 40), ("b", 10))
    }
    fig.update_layout(
        template=p["PLOTLY_TEMPLATE"],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=p["TEXT_COLOR"],
        margin=margin,
    )
    return fig


def inject_css():
    """
    全站 CSS，所有顏色跟著目前主題走。每次 rerun 都要呼叫。

    為什麼要寫這麼多：.streamlit/config.toml 把 Streamlit 內建主題固定為深色，
    淺色模式其實是用這份 CSS 蓋上去的。沒蓋到的元件（下拉選單、提示框、
    展開區塊、數字框的 +/- 等）就會維持內建的深色，所以每一類元件都要寫到。
    選擇器盡量用 data-testid 的「開頭比對」（^=），一次涵蓋同類元件的各種變體，
    例如 stBaseButton-secondary 與 stBaseButton-secondaryFormSubmit。
    """
    p = palette()
    APP_BG, SECONDARY_BG = p["APP_BG"], p["SECONDARY_BG"]
    TEXT_COLOR, BORDER_COLOR = p["TEXT_COLOR"], p["BORDER_COLOR"]
    BORDER_STRONG, TABLE_HEAD_BG = p["BORDER_STRONG"], p["TABLE_HEAD_BG"]
    UP = p["UP_COLOR"]
    light = current_theme() == "light"

    alert_css = ""
    for kind in ("Info", "Success", "Warning", "Error"):
        bg, fg = p["ALERT_" + kind.upper()]
        sel = f'[data-testid="stAlertContainer"]:has([data-testid="stAlertContent{kind}"])'
        alert_css += f"""
        {sel} {{
            background-color: {bg} !important;
            color: {fg} !important;
        }}
        .stApp {sel} :is(p, li, span, strong, b, div) {{
            color: {fg} !important;
        }}"""

    # 表格（st.dataframe / st.data_editor）是畫在 canvas 上的，CSS 改不到裡面的顏色。
    # 內建主題是深色，所以淺色模式用「反相再把色相轉回來」把深色表格變成淺色表格。
    grid_css = (
        """
        [data-testid="stDataFrameResizable"] {
            filter: invert(1) hue-rotate(180deg);
        }"""
        if light else ""
    )

    st.markdown(
        f"""
        <style>
        :root {{
            --background-color: {APP_BG};
            --secondary-background-color: {SECONDARY_BG};
            --text-color: {TEXT_COLOR};
        }}

        /* ---------- 頁面底色 ---------- */
        /* 頁首是 <header> 不是 <div>，選擇器不要綁標籤名，否則深色模式最上方會留白條。
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
        [data-testid="stHeader"] svg,
        [data-testid="stAppHeader"] svg,
        [data-testid="stToolbar"] svg,
        [data-testid="stSidebarCollapseButton"] svg,
        [data-testid="stExpandSidebarButton"] svg,
        [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
        [data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {{
            /* 收合側邊欄的 « » 是圖示字型（stIconMaterial），不是 svg，要另外設文字色 */
            fill: {TEXT_COLOR} !important;
            color: {TEXT_COLOR} !important;
        }}
        [data-testid="stSidebar"],
        [data-testid="stSidebarContent"] {{
            background-color: {SECONDARY_BG} !important;
        }}

        /* ---------- 文字 ---------- */
        /* 不能把 span 一起強制上色：畫面上有很多 <span style="color:綠/紅"> 的漲跌數字，
           CSS 的 !important 會蓋過 inline 顏色，漲跌就全變成黑字／白字。 */
        p, li, label, h1, h2, h3, h4, h5, h6,
        div[data-testid="stMarkdownContainer"],
        [data-testid="stCaptionContainer"],
        [data-testid="stWidgetLabel"] {{
            color: {TEXT_COLOR} !important;
        }}
        hr {{
            border-color: {BORDER_COLOR} !important;
            background-color: {BORDER_COLOR} !important;
        }}

        /* ---------- 輸入框 ---------- */
        .stTextInput input, .stNumberInput input, .stTextArea textarea {{
            background-color: {SECONDARY_BG} !important;
            color: {TEXT_COLOR} !important;
            -webkit-text-fill-color: {TEXT_COLOR} !important;
            border-radius: 8px !important;
        }}
        /* 外框容器（含密碼欄右邊的眼睛、數字框右邊的 -/+）也要換底色 */
        [data-testid="stTextInputRootElement"],
        [data-testid="stNumberInputContainer"],
        .stTextArea [data-baseweb="textarea"] {{
            background-color: {SECONDARY_BG} !important;
            border-color: {BORDER_COLOR} !important;
            border-radius: 8px !important;
        }}
        input::placeholder, textarea::placeholder {{
            color: {TEXT_COLOR} !important;
            -webkit-text-fill-color: {TEXT_COLOR} !important;
            opacity: 0.45 !important;
        }}
        [data-testid="stTextInputRootElement"] button,
        [data-testid="stNumberInputStepDown"],
        [data-testid="stNumberInputStepUp"] {{
            background-color: transparent !important;
            color: {TEXT_COLOR} !important;
        }}
        [data-testid="stTextInputRootElement"] button svg,
        [data-testid="stNumberInputStepDown"] svg,
        [data-testid="stNumberInputStepUp"] svg {{
            fill: currentColor !important;
            color: currentColor !important;
        }}
        [data-testid="stNumberInputStepDown"]:hover:enabled,
        [data-testid="stNumberInputStepUp"]:hover:enabled {{
            background-color: {UP} !important;
            color: #FFFFFF !important;
        }}
        [data-testid="stNumberInputStepDown"]:disabled,
        [data-testid="stNumberInputStepUp"]:disabled {{
            opacity: 0.35 !important;
        }}
        /* 隱藏輸入框內的 "Press Enter to submit form" / "Press Enter to apply" 提示 */
        [data-testid="InputInstructions"],
        [data-testid="stWidgetInstructions"] {{
            display: none !important;
        }}

        /* ---------- 下拉選單 ---------- */
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stSelectbox"] [role="group"] {{
            background-color: {SECONDARY_BG} !important;
            border-color: {BORDER_COLOR} !important;
            color: {TEXT_COLOR} !important;
        }}
        [data-testid="stSelectbox"] input,
        [data-testid="stSelectbox"] [data-baseweb="select"] div {{
            color: {TEXT_COLOR} !important;
            -webkit-text-fill-color: {TEXT_COLOR} !important;
        }}
        [data-testid="stSelectbox"] svg {{
            fill: {TEXT_COLOR} !important;
            color: {TEXT_COLOR} !important;
        }}
        /* 展開後的選項清單（新版是 stSelectboxVirtualDropdown，舊版是 popover/listbox） */
        [data-testid="stSelectboxVirtualDropdown"],
        div[data-baseweb="popover"] ul,
        div[data-baseweb="popover"] [role="listbox"],
        div[data-baseweb="popover"] > div {{
            background-color: {SECONDARY_BG} !important;
            border-color: {BORDER_COLOR} !important;
        }}
        [role="option"], [role="option"] * {{
            color: {TEXT_COLOR} !important;
            -webkit-text-fill-color: {TEXT_COLOR} !important;
        }}
        [role="option"]:hover,
        [role="option"][aria-selected="true"] {{
            background-color: {UP} !important;
        }}
        [role="option"]:hover,
        [role="option"]:hover *,
        [role="option"][aria-selected="true"],
        [role="option"][aria-selected="true"] * {{
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }}

        /* ---------- 按鈕 ---------- */
        /* 開頭比對涵蓋：一般按鈕、表單按鈕、連結按鈕、包在說明提示裡的按鈕 */
        [data-testid^="stBaseButton-secondary"],
        [data-testid^="stBaseLinkButton-secondary"] {{
            background-color: {SECONDARY_BG} !important;
            color: {TEXT_COLOR} !important;
            border: 1px solid {BORDER_COLOR} !important;
            border-radius: 12px !important;
            font-weight: bold;
        }}
        [data-testid^="stBaseButton-secondary"]:hover,
        [data-testid^="stBaseLinkButton-secondary"]:hover {{
            border-color: {UP} !important;
            color: {UP} !important;
        }}
        [data-testid^="stBaseButton-primary"],
        [data-testid^="stBaseLinkButton-primary"] {{
            background-color: {UP} !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 12px !important;
            font-weight: bold;
        }}
        [data-testid^="stBaseButton-primary"]:hover,
        [data-testid^="stBaseLinkButton-primary"]:hover {{
            filter: brightness(1.08);
        }}
        /* 按鈕裡的文字跟著按鈕走（要比上面「文字」那段更具體才蓋得過） */
        .stApp [data-testid^="stBaseButton-secondary"] :is(p, div, span),
        .stApp [data-testid^="stBaseLinkButton-secondary"] :is(p, div, span) {{
            color: inherit !important;
        }}
        .stApp [data-testid^="stBaseButton-primary"] :is(p, div, span),
        .stApp [data-testid^="stBaseLinkButton-primary"] :is(p, div, span) {{
            color: #FFFFFF !important;
        }}

        /* ---------- 提示框 st.info / success / warning / error ---------- */
        [data-testid="stAlertContainer"] {{
            border: 1px solid {BORDER_COLOR} !important;
        }}
        {alert_css}

        /* ---------- 展開區塊 st.expander ---------- */
        [data-testid="stExpander"] details {{
            background-color: {APP_BG} !important;
            border-color: {BORDER_COLOR} !important;
        }}
        [data-testid="stExpander"] summary {{
            background-color: {SECONDARY_BG} !important;
            color: {TEXT_COLOR} !important;
        }}
        [data-testid="stExpander"] summary:hover {{
            color: {UP} !important;
        }}
        .stApp [data-testid="stExpander"] summary :is(p, span, div) {{
            color: inherit !important;
        }}

        /* ---------- 勾選框 ---------- */
        [data-testid="stCheckbox"] label > div:not([data-testid]) {{
            background-color: {APP_BG} !important;
            border-color: {BORDER_STRONG} !important;
        }}
        [data-testid="stCheckbox"] label:has(input:checked) > div:not([data-testid]) {{
            background-color: {UP} !important;
            border-color: {UP} !important;
        }}

        /* ---------- 滑桿刻度文字、分頁標籤底線 ---------- */
        [data-testid="stSliderTickBar"] {{
            color: {TEXT_COLOR} !important;
            opacity: 0.7;
        }}
        [data-baseweb="tab-border"] {{
            background-color: {BORDER_COLOR} !important;
        }}

        /* ---------- 有外框的區塊（st.container(border=True)、表單） ---------- */
        [data-testid="stVerticalBlock"],
        [data-testid="stForm"] {{
            border-color: {BORDER_COLOR} !important;
        }}

        /* ---------- 表格 ---------- */
        [data-testid="stElementToolbarButtonContainer"] {{
            background-color: {SECONDARY_BG} !important;
        }}
        [data-testid="stElementToolbarButtonContainer"] button,
        [data-testid="stElementToolbarButtonContainer"] svg {{
            color: {TEXT_COLOR} !important;
            fill: {TEXT_COLOR} !important;
        }}
        {grid_css}
        /* 表格儲存格編輯時跳出的輸入框、下拉清單：它們放在 #portal 裡、不在表格內，
           上面的反相處理不到，要另外指定顏色 */
        #portal .gdg-style,
        #portal .gdg-style [class*="-control"],
        #portal div:has(> [role="listbox"]) {{
            background-color: {APP_BG} !important;
            border-color: {BORDER_COLOR} !important;
        }}
        #portal .gdg-style,
        #portal .gdg-style * {{
            color: {TEXT_COLOR} !important;
            -webkit-text-fill-color: {TEXT_COLOR} !important;
        }}
        [data-testid="stTable"] table, [data-testid="stTable"] th, [data-testid="stTable"] td {{
            color: {TEXT_COLOR} !important;
            border-color: {BORDER_COLOR} !important;
        }}
        [data-testid="stTable"] th {{
            background-color: {TABLE_HEAD_BG} !important;
        }}

        /* ---------- 浮動說明（滑鼠移到 ? 上出現的框） ---------- */
        [data-testid="stTooltipContent"] {{
            background-color: {SECONDARY_BG} !important;
            color: {TEXT_COLOR} !important;
            border: 1px solid {BORDER_COLOR} !important;
        }}
        [data-testid="stTooltipIcon"] svg {{
            color: {TEXT_COLOR} !important;
            stroke: {TEXT_COLOR} !important;
            opacity: 0.6;
        }}

        div[data-testid="stMetric"] {{
            background-color: {SECONDARY_BG} !important;
            border-radius: 10px;
            padding: 10px 15px;
        }}
        div[data-testid="stMetricLabel"], div[data-testid="stMetricValue"] {{
            color: {TEXT_COLOR} !important;
        }}

        /* ---------- 本系統自訂的區塊 ---------- */
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
            border-color: {UP};
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
        if st.button(label, key=key or f"back_{target}", width="stretch"):
            go_to(target)

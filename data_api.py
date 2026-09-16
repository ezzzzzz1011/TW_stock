\"""
資料引擎：雲端資料庫（Google Sheets）、報價、配息、財報、本益比河流圖、大盤。
這裡只負責取資料與運算，畫面相關的東西放在 pages.py。
"""

import io
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import gspread
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from fugle_marketdata import RestClient
from google.oauth2.service_account import Credentials

from common import (
    ASSET_CATEGORIES,
    COLUMNS_ORDER,
    DEFAULT_PORTFOLIO_ROWS,
    DIV_PAY_LAG_DAYS,
    FUGLE_VOLUME_IN_SHARES,
    HTTP_TIMEOUT,
    MAX_WORKERS,
    UA_HEADER,
    tw_tz,
)

# =============================================================
# API 金鑰：一律從 Streamlit Secrets 讀取，程式碼裡不留任何金鑰。
#
# .streamlit/secrets.toml（或 Streamlit Cloud 的 Settings → Secrets）格式：
#
#   [finmind]
#   token = "你的 FinMind token"
#
#   [fugle]
#   token = "你的 Fugle token"
#
#   [gcp_service_account]        ← 這個區塊要放最後
#   type = "service_account"
#   ...
#
# TOML 的區塊會一直延伸到下一個標頭，所以把小區塊寫在 gcp 後面會被吃掉。
# =============================================================
def _read_secret(section, key="token"):
    try:
        value = st.secrets.get(section, {}).get(key)
    except Exception:
        value = None
    return str(value).strip() if value else ""


FINMIND_TOKEN = _read_secret("finmind")
FUGLE_TOKEN = _read_secret("fugle")

FINMIND_TOKEN_SOURCE = "Secrets" if FINMIND_TOKEN else "未設定"
FUGLE_TOKEN_SOURCE = "Secrets" if FUGLE_TOKEN else "未設定"

def require_tokens():
    """金鑰檢查。同樣要由主程式每次 rerun 呼叫，不能寫在模組層級。"""
    missing = [
        name
        for name, value in (("finmind", FINMIND_TOKEN), ("fugle", FUGLE_TOKEN))
        if not value
    ]
    if not missing:
        return
    st.error(
        "缺少 API 金鑰設定：" + "、".join(f"[{m}]" for m in missing) + "\n\n"
        "請到 Streamlit Cloud 的 Settings → Secrets 補上，格式為：\n\n"
        "```toml\n[finmind]\ntoken = \"...\"\n\n[fugle]\ntoken = \"...\"\n```"
    )
    st.stop()

client = RestClient(api_key=FUGLE_TOKEN)

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

# ===================== 雲端資料庫 =====================
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

# ===================== 報價與配息 =====================
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

# ===================== 大盤 =====================
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

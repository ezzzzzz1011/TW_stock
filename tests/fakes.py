"""
測試用的替身：Google Sheets、Google 憑證、Fugle 即時報價、FinMind token。

不改動任何程式碼，只在執行期間把外部服務換掉：
  - Google Sheets → 記憶體裡的假工作表。繼承真正的 gspread Worksheet，
    所以 get_all_records() 的「數字字串轉成數字」行為跟正式環境一模一樣。
  - Fugle 即時報價 → 用 yfinance 最近兩天收盤價代替（測試環境沒有 Fugle 金鑰）。
  - FinMind → 不帶 token 呼叫（免金鑰也能查，只是次數較少）。

使用方式：在 import data_api 之前呼叫 install()，之後再呼叫 patch_data_api()。
"""

import os
import sys

import gspread
import yfinance as yf
from google.oauth2 import service_account
from gspread.cell import Cell
from gspread.worksheet import Worksheet

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TESTS_DIR)


class FakeSheet(Worksheet):
    """只實作 data_api 用得到的方法；資料存在 self.rows（二維 list，第一列是表頭）。"""

    def __init__(self, rows=None):  # noqa: D401 - 不呼叫父類別，避免需要真正的連線
        self.rows = [list(r) for r in (rows or [])]

    def get(self, *args, **kwargs):
        return [list(r) for r in self.rows]

    def find(self, query, in_row=None, in_column=None, case_sensitive=True):
        for i, row in enumerate(self.rows, start=1):
            cols = [in_column] if in_column else range(1, len(row) + 1)
            for c in cols:
                if c <= len(row) and str(row[c - 1]) == str(query):
                    return Cell(i, c, row[c - 1])
        return None

    def cell(self, row, col, **kwargs):
        return Cell(row, col, self.rows[row - 1][col - 1])

    def update_cell(self, row, col, value):
        self.rows[row - 1][col - 1] = value

    def update(self, values=None, range_name=None, raw=True, **kwargs):
        col = ord(range_name[0]) - 64
        row = int(range_name[1:])
        self.rows[row - 1][col - 1] = values[0][0]

    def append_row(self, values, **kwargs):
        # value_input_option 預設是 RAW：存的就是字串本身
        self.rows.append([str(v) for v in values])


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    def worksheet(self, title):
        if title not in self.sheets:
            raise gspread.exceptions.WorksheetNotFound(title)
        return self.sheets[title]

    def add_worksheet(self, title, rows=None, cols=None):
        self.sheets[title] = FakeSheet()
        return self.sheets[title]


class FakeClient:
    def __init__(self):
        self.book = FakeSpreadsheet()

    def open(self, name):
        return self.book


def install():
    """在 import data_api 之前呼叫。"""
    # Streamlit 從「目前目錄/.streamlit/secrets.toml」讀測試用的假金鑰
    os.chdir(TESTS_DIR)
    if REPO_DIR not in sys.path:
        sys.path.insert(0, REPO_DIR)
    gspread.authorize = lambda creds: FakeClient()
    service_account.Credentials.from_service_account_info = staticmethod(
        lambda info, scopes=None: None
    )


def fake_quote(symbol):
    """以 yfinance 最近兩天收盤價代替 Fugle 報價，欄位與 get_stock_info 相同。"""
    from data_api import clean_code

    code = clean_code(symbol)
    if not code:
        return None
    for suffix in (".TW", ".TWO"):
        try:
            hist = yf.Ticker(code + suffix).history(period="5d")["Close"].dropna()
        except Exception:
            continue
        if len(hist) >= 2:
            price, prev = float(hist.iloc[-1]), float(hist.iloc[-2])
            return {
                "name": code, "price": price, "change": price - prev,
                "pct": (price / prev - 1) * 100, "high": price, "low": price,
                "open": price, "vol_lots": 0, "full_ticker": code,
                "date": hist.index[-1].strftime("%Y-%m-%d"),
            }
    return None


def patch_data_api():
    """import data_api 之後、啟動 AppTest 之前呼叫（pages 會在那時才 import 這些名稱）。"""
    import data_api

    data_api.FINMIND_TOKEN = ""            # 不帶 token 呼叫 FinMind
    data_api.require_tokens = lambda: None  # 測試環境不檢查金鑰
    data_api.get_stock_info = fake_quote
    return data_api

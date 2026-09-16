"""
台股個股 / ETF 查詢系統 — 進入點
Ez開發 - 投資助手系統

檔案結構：
  testapp.py   進入點：版面設定、session 狀態、登入判斷、呼叫畫面
  common.py    主題顏色、稅制參數、通用小工具
  data_api.py  資料引擎：Google Sheets、報價、配息、財報、大盤
  pages.py     登入頁、側邊欄與所有功能頁

重要：Python 只在第一次 import 時執行模組，之後的 session 不會再跑一次。
所以凡是「每個 session 都必須執行」的事情（版面設定、session 狀態初始化、
金鑰檢查）都要寫在這個檔案裡，不能放在其他模組的模組層級。
"""

import streamlit as st

import common

# set_page_config 必須是第一個 Streamlit 指令，所以要在 import pages 之前呼叫
# （import pages 會連帶 import data_api，那裡有 st 指令）。
common.setup_page()

import data_api  # noqa: E402
import pages  # noqa: E402

data_api.require_tokens()
common.init_theme()

for _key, _default in [
    ("logged_in", False),
    ("current_user", None),
    ("portfolio", None),
    ("watchlist", None),
    ("page", "welcome"),
    ("data", None),
]:
    if _key not in st.session_state:
        st.session_state[_key] = _default

common.inject_css()

if not st.session_state.logged_in:
    pages.login_ui()
    st.stop()

pages.render()

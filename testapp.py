"""
台股個股 / ETF 查詢系統 — 進入點
Ez開發 - 投資助手系統

檔案結構：
  testapp.py   進入點：session 狀態、登入判斷、呼叫畫面
  common.py    頁面設定、主題顏色、稅制參數、通用小工具
  data_api.py  資料引擎：Google Sheets、報價、配息、財報、大盤
  pages.py     登入頁、側邊欄與所有功能頁

common 必須最先 import，因為 st.set_page_config 要在所有 Streamlit 指令之前執行。
"""

import streamlit as st

import common          # noqa: F401  (import 時即完成 set_page_config)
import pages

common.inject_css()

# --- Session 狀態 ---
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

# --- 未登入就停在登入頁 ---
if not st.session_state.logged_in:
    pages.login_ui()
    st.stop()

pages.render()

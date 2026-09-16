"""
畫面：登入頁、側邊欄與所有功能頁。
資料一律透過 data_api 取得，這裡只負責呈現。
"""

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

import common
from common import (
    APP_VERSION, ASSET_CATEGORIES, BASIC_INCOME_CAP, COLUMNS_ORDER,
    DIV_CREDIT_CAP, DIV_CREDIT_RATE, DIV_PAY_LAG_DAYS, DIV_SEPARATE_RATE,
    DOWN_COLOR, FEE_RATE, NHI_RATE, NHI_THRESHOLD, TAX_CONFIG, UP_COLOR,
    HTTP_TIMEOUT, YIELD_CHEAP, YIELD_FAIR, back_button, bottom_columns, go_to,
    greeting,
    label_spacer, lookup_bracket, preschool_amount, toggle_theme, tw_tz,
)
from data_api import (
    FINMIND_TOKEN, FINMIND_TOKEN_SOURCE, FINMIND_URL, FUGLE_TOKEN_SOURCE,
    MARKET_GROUPS, analyze_pe_band, annualize, clean_code, empty_portfolio,
    fetch_index_history, fetch_institutional_flow, fetch_many,
    fetch_market_turnover, format_market_value,
    generate_user_calendar, get_asset_category, get_cloud_users,
    get_market_data, get_safe_data_etf, get_stock_info, get_ttm_eps,
    load_portfolio_from_cloud, load_watchlist_from_cloud,
    quarter_label, save_portfolio_to_cloud, save_watchlist_to_cloud, user_sheet,
)
import requests

# 顏色由 common.palette() 在每次 rerun 時刷新，先給預設值避免 NameError
APP_BG = SECONDARY_BG = TEXT_COLOR = BORDER_COLOR = TRACK_COLOR = TABLE_HEAD_BG = ""


# ===================== 小元件 =====================
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

# ===================== 登入頁 =====================
def login_ui():
    common.apply_palette(globals())   # 登入頁也要先取得主題顏色
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


# ===================== 側邊欄與路由 =====================
def render():
    """每次 rerun 由 testapp.py 呼叫。"""
    common.apply_palette(globals())

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
            st.caption(f"FinMind token：{FINMIND_TOKEN_SOURCE}"
                   f"　|　Fugle token：{FUGLE_TOKEN_SOURCE}")
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

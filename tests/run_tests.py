"""
端對端測試：用 Streamlit AppTest 實際跑整個網站。

執行方式（在專案根目錄）：
    pip install -r requirements.txt
    python tests/run_tests.py

需要網路：會實際呼叫 FinMind（不帶 token）、yfinance、證交所、櫃買中心。
Google Sheets 與 Fugle 用 tests/fakes.py 的替身，不會碰到正式資料。
全部通過時結束代碼為 0，有失敗為 1。
"""

import os
import re
import sys
import traceback
import warnings
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402

fakes.install()
warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

d = fakes.patch_data_api()
APP = os.path.join(fakes.REPO_DIR, "testapp.py")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def section(title):
    print(f"\n=== {title} ===", flush=True)


# ---------------- 測試資料 ----------------
d.user_sheet.rows += [
    ["amy", "0000"],        # 舊的明碼密碼，0 開頭
    ["bob", "secret1"],
    ["eason", "1111"],
    ["victim", "pw9999"],   # 專門給登入鎖定測試用
    ["boss", "pw1234"],     # tests/.streamlit/secrets.toml 裡的管理員
]
d.portfolio_sheet.rows.append([
    "amy",
    # 「代碼」是數字 50：模擬以前被 pandas 存壞的資料；2330 分兩列
    '[{"代碼":50,"名稱":"元大台灣50","張數":1,"戰略屬性":""},'
    '{"代碼":"2330","名稱":"台積電","張數":2,"戰略屬性":""},'
    '{"代碼":"2330","名稱":"台積電","張數":3,"戰略屬性":""}]',
])
d.get_cloud_users.clear()


def new_app(secrets=None):
    at = AppTest.from_file(APP, default_timeout=180)
    for k, v in (secrets or {}).items():
        at.secrets[k] = v
    at.run()
    return at


def login(at, user, pw):
    at.text_input(key="l_user").input(user)
    at.text_input(key="l_pw").input(pw)
    next(b for b in at.button if b.label == "確認登入").click()
    at.run()
    return bool(at.session_state["logged_in"])


def goto(at, page):
    at.session_state["page"] = page
    at.run()


def errors(at):
    return "; ".join(str(e.value)[:200] for e in at.exception)


def md(at):
    return [m.value for m in at.markdown]


try:
    # ================================================================
    section("登入與密碼")
    at = new_app()
    check("登入頁沒有程式錯誤", not at.exception, errors(at))
    check("錯誤密碼登不進去", not login(at, "amy", "0001"))
    at = new_app()
    check("0 開頭的舊明碼密碼 0000 可登入", login(at, "amy", "0000"))
    stored = next(r for r in d.user_sheet.rows if r[0] == "amy")[1]
    check("登入後明碼自動換成雜湊", stored.startswith("pbkdf2_sha256$"), stored[:30] + "...")
    pf = at.session_state["portfolio"]
    check("被存壞的代碼 50 讀取後變回 0050", list(pf["代碼"]) == ["0050", "2330", "2330"], str(list(pf["代碼"])))
    at = new_app()
    check("換成雜湊後同一組密碼仍可登入", login(at, "amy", "0000"))
    at = new_app()
    check("換成雜湊後錯誤密碼仍登不進去", not login(at, "amy", "000"))

    at = new_app()
    at.text_input(key="r_user").input("carol")
    at.text_input(key="r_pw").input("0123")
    at.text_input(key="r_confirm").input("0123")
    next(b for b in at.button if b.label == "提交註冊").click()
    at.run()
    carol = next((r for r in d.user_sheet.rows if r[0] == "carol"), None)
    check("新註冊帳號只存雜湊", carol and carol[1].startswith("pbkdf2_sha256$") and "0123" not in carol[1])
    at = new_app()
    check("新註冊帳號 carol / 0123 可登入", login(at, "carol", "0123"))

    # ================================================================
    section("登入失敗次數限制")
    for i in range(d.LOGIN_MAX_FAILURES):
        at = new_app()
        login(at, "victim", f"wrong{i}")
    at = new_app()
    ok = login(at, "victim", "pw9999")
    msgs = [e.value for e in at.error]
    check(f"連錯 {d.LOGIN_MAX_FAILURES} 次後，正確密碼也暫時登不進去", not ok)
    check("畫面顯示「失敗次數過多」與等待分鐘數", any("失敗次數過多" in m and "5 分鐘" in m for m in msgs), str(msgs))
    at = new_app()
    check("其他帳號不受影響", login(at, "bob", "secret1"))
    remaining = d.login_lock_remaining("victim")
    check("鎖定時間約 5 分鐘", d.LOGIN_LOCK_SECONDS - 10 <= remaining <= d.LOGIN_LOCK_SECONDS, f"{remaining} 秒")
    # 模擬鎖定時間已過：把到期時間改成 1 秒前（不去動全域時鐘，以免影響 Streamlit 本身）
    guard = d._login_guard()
    with guard["lock"]:
        guard["locked_until"]["victim"] = d.time.time() - 1
    at = new_app()
    check("鎖定時間過後可以正常登入", login(at, "victim", "pw9999"))
    for i in range(d.LOGIN_MAX_FAILURES - 1):
        at = new_app()
        login(at, "bob", f"wrong{i}")
    at = new_app()
    check(f"只錯 {d.LOGIN_MAX_FAILURES - 1} 次不會被鎖", login(at, "bob", "secret1"))

    # ================================================================
    section("管理員權限")
    base = {"finmind": {"token": "x"}, "fugle": {"token": "x"}, "gcp_service_account": {"type": "service_account"}}
    cases = [
        ("沒有設定 [admin]", {}, False, "沒有 [admin]"),
        ("正確設定", {"admin": {"users": ["eason"]}}, True, "有"),
        ("漏寫 [admin] 那一行", {"gcp_service_account": {"type": "service_account", "users": ["eason"]}}, False,
         "被寫進了 [gcp_service_account]"),
        ("大小寫不同", {"admin": {"users": ["Eason"]}}, False, "大小寫不一致"),
        ("名單裡是別人", {"admin": {"users": ["boss"]}}, False, "不在名單中"),
        ("users 寫成單一字串", {"admin": {"users": "eason"}}, True, "有"),
    ]
    for name, extra, want_btn, want_text in cases:
        at = new_app({**base, **extra})
        login(at, "eason", "1111")
        cap = next((c.value for c in at.caption if c.value.startswith("管理員權限")), "（沒有出現）")
        has_btn = "清除全站資料快取" in [b.label for b in at.button]
        check(f"{name}：按鈕{'有' if want_btn else '無'}、說明正確",
              has_btn == want_btn and want_text in cap and not at.exception, cap)

    # ================================================================
    section("每一頁在兩種主題下都能正常顯示")
    at = new_app()
    login(at, "boss", "pw1234")
    for theme in ("dark", "light"):
        at.session_state["theme"] = theme
        for page in list(sys.modules["pages"].PAGES) + ["no_such_page"]:
            goto(at, page)
            check(f"[{theme}] {page}", not at.exception, errors(at))
    goto(at, "no_such_page")
    check("不存在的頁面顯示提示", any("找不到這個頁面" in w.value for w in at.warning))

    # ================================================================
    section("個股分析：本益比河流圖")
    at.session_state["theme"] = "dark"
    goto(at, "stock_query")
    at.text_input[0].input("2330")
    starts = {}
    for years in (3, 5, 10):
        at.selectbox[0].select(years)
        at.run()
        texts = md(at)
        table = next((t for t in texts if "styled-table" in t and "本益比區間" in t), "")
        rows = re.findall(r"<tr style='([^']*)'><td>([^<(]+)", table)
        highlighted = [label.strip() for style, label in rows if "background-color" in style]
        box = next((t for t in texts if "系統判讀" in t), "")
        m = re.search(r"font-weight:bold; color:[^;]+;'>([^<]+)</div>", box)
        verdict = m.group(1) if m else None
        band = d.analyze_pe_band("2330", years)
        price = d.get_stock_info("2330")["price"]
        zone = next((z for z in band.get("zones", []) if z["label"] == verdict), None)
        inside = zone is not None and (zone["price_lo"] is None or price > zone["price_lo"]) and (
            zone["price_hi"] is None or price <= zone["price_hi"])
        cap = next((c.value for c in at.caption if c.value.startswith("取樣 ")), "")
        starts[years] = cap
        check(f"近 {years} 年：沒有錯誤、只標亮一列且與判讀一致",
              not at.exception and highlighted == [verdict], f"判讀={verdict} 標亮={highlighted}")
        check(f"近 {years} 年：股價確實落在「{verdict}」區間", inside)
        check(f"近 {years} 年：實際涵蓋接近 {years} 年", band.get("covered_years", 0) >= years - 0.5, cap)
        date_line = next((t for t in texts if "資料日期：" in t), "")
        check(f"近 {years} 年：資料日期顯示報價的交易日", d.get_stock_info("2330")["date"] in date_line, date_line)
    check("3／5／10 年的取樣起點都不同", len(set(starts.values())) == 3, str(starts))

    orig = d.fetch_quarterly_financials
    fake_q = [{"date": f"{y}-{m:02d}-{dd}", "eps": -0.5, "net_income": -500.0}
              for y in (2024, 2025, 2026) for m, dd in ((3, 31), (6, 30), (9, 30), (12, 31))
              if f"{y}-{m:02d}" <= "2026-06"]
    d.fetch_quarterly_financials = lambda s, days=900: (sorted(fake_q, key=lambda q: q["date"], reverse=True), None)
    d.analyze_pe_band.clear()
    loss = d.analyze_pe_band("2330", 5)
    d.fetch_quarterly_financials = orig
    d.analyze_pe_band.clear()
    check("近四季虧損時不估價並說明原因", not loss["success"] and "虧損" in loss["msg"], loss.get("msg", ""))

    # ================================================================
    section("EPS 備援（FinMind 失效時）")
    table = d.fetch_exchange_pe_table()
    n = {k: sum(v["source"] == k for v in table.values()) for k in ("twse", "tpex")}
    check("證交所（上市）可反推 EPS", n["twse"] > 700, f"{n['twse']} 檔")
    check("櫃買中心（上櫃）可反推 EPS", n["tpex"] > 500, f"{n['tpex']} 檔")
    d.fetch_quarterly_financials = lambda s, days=900: ([], "模擬 FinMind 失效")
    r_tpex, r_twse = d.get_ttm_eps("8069"), d.get_ttm_eps("2330")
    d.fetch_quarterly_financials = orig
    check("上櫃 8069 改用櫃買中心", r_tpex.get("source") == "tpex" and "櫃買中心" in r_tpex.get("method", ""),
          r_tpex.get("method", r_tpex.get("msg")))
    check("上市 2330 改用證交所", r_twse.get("source") == "twse" and "證交所" in r_twse.get("method", ""),
          r_twse.get("method", r_twse.get("msg")))

    # ================================================================
    section("配息")
    tw = d.fetch_dividend_history_super("3045")
    check("台灣大 2026 年配息含公積（4.744 元）",
          any(x["date"].startswith("2026") and abs(x["amount"] - 4.74428) < 0.01 for x in tw), str(tw[:1]))
    tcc = d.fetch_dividend_history_super("1101")
    check("台泥 2026 年只發公積 0.8 元也有算到",
          any(x["date"].startswith("2026") and abs(x["amount"] - 0.8) < 1e-6 for x in tcc), str(tcc[:1]))
    for code, label in (("2330", "季"), ("2412", "年"), ("0050", "半年"), ("00919", "季"), ("00937B", "月")):
        got = d.infer_frequency(d.fetch_dividend_history_super(code))[1]
        check(f"{code} 判斷為{label}配", got == label, got)

    # ================================================================
    section("ETF 頁")
    for code, want in (("00919", "以最近 4 次配息加總"), ("00937B", "平均 × 12 次推估"),
                       ("0050", "以最近 2 次配息加總"), ("2412", "以最新一次配息作為年配息")):
        goto(at, "etf_query")
        at.text_input(key="etf_symbol_input").input(code)
        next(b for b in at.button if b.label == "開始計算").click()
        at.run()
        caps = [c.value for c in at.caption if "預估年配息以" in c.value]
        check(f"{code}：說明「{want}」", bool(caps) and want in caps[0] and not at.exception,
              caps[0] if caps else errors(at) or "沒有出現")

    # ================================================================
    section("我的資產")
    at = new_app()
    login(at, "amy", "0000")
    goto(at, "portfolio")
    next(b for b in at.button if b.label == "開始計算當前市值").click()
    at.run()
    frames = [getattr(f.value, "data", f.value) for f in at.dataframe]
    res = next((f for f in frames if "持有價值" in f.columns), None)
    row = res[res["代碼"] == "2330"] if res is not None else pd.DataFrame()
    check("2330 分兩列（2 張 + 3 張）合計 5 張", len(row) == 1 and float(row["張數"].iloc[0]) == 5.0,
          str(row.to_dict("records")))
    next(b for b in at.button if b.label == "生成我的專屬領息月曆").click()
    at.run()
    check("領息月曆按鈕沒有錯誤", not at.exception, errors(at))
    st.session_state["portfolio"] = pd.DataFrame([{"代碼": "2330", "名稱": "", "張數": 1.0, "戰略屬性": ""}])
    edited = pd.DataFrame([{"代碼": "2330", "名稱": "", "張數": 5.0, "戰略屬性": ""}])
    cal = d.generate_user_calendar(edited)
    amt = d.get_dividend_calendar("2330")["amount"]
    check("月曆依畫面上的 5 張計算，不是儲存的 1 張",
          cal is not None and int(cal["預估入帳金額"].iloc[0]) == int(amt * 5 * 1000))

    # ================================================================
    section("股利報稅")
    goto(at, "tax_calc")
    ni = {n.label: n for n in at.number_input}
    ni["報稅人(爸爸) 薪資"].set_value(1_000_000)
    ni["全年利息所得 (存款、債券利息等，全家加總)"].set_value(300_000)
    ni["一般免稅額人數 (本人/配偶/受扶養親屬)"].set_value(1)
    ni["滿70歲：本人/配偶/受扶養直系尊親屬人數"].set_value(1)
    ni[next(k for k in ni if k.startswith("就讀大專以上子女"))].set_value(2)
    at.run()
    tuition = [n for n in at.number_input if n.label.startswith("第 ") and "學費" in n.label]
    check("填 2 位子女時出現 2 個學費欄位", len(tuition) == 2)
    tuition[0].set_value(30_000)
    tuition[1].set_value(10_000)
    at.run()
    texts = " ".join(md(at))
    cfg = sys.modules["common"].TAX_CONFIG[max(sys.modules["common"].TAX_CONFIG)]
    exemption = cfg["exemption"] + cfg["exemption_70"]
    check("報稅頁沒有錯誤", not at.exception, errors(at))
    check("儲蓄投資扣除額 = min(利息 30 萬, 上限 27 萬)", "儲蓄投資特別扣除額：**270,000**" in texts)
    check("教育學費 = min(3 萬, 2.5 萬) + 1 萬 = 35,000", "<td>35,000</td>" in texts)
    check("綜合所得總額含利息：100 萬 + 30 萬", "1,300,000 元" in texts)
    check(f"免稅額 = 一般 1 人 + 70 歲 1 人 = {exemption:,}", f"<td>{exemption:,}</td>" in texts)

    # ================================================================
    section("大盤")
    amount, change, pct, dt = d.fetch_market_turnover()
    check("成交金額有資料", amount is not None, f"{dt} {amount:,.0f} 億" if amount else "")
    orig_month = d._fetch_turnover_month

    def fake_month(day_obj):
        if day_obj.month == datetime.now(d.tw_tz).month:
            return [(date(2026, 11, 2), 5.0e11)]
        return [(date(2026, 10, 29), 4.0e11), (date(2026, 10, 30), 4.5e11)]

    d._fetch_turnover_month = fake_month
    d.fetch_market_turnover.clear()
    _, c2, p2, d2 = d.fetch_market_turnover()
    d._fetch_turnover_month = orig_month
    d.fetch_market_turnover.clear()
    check("月初只有一筆時，跟上個月最後一天比較", d2 == "11/02" and abs(c2 - 500) < 1e-6 and abs(p2 - 11.111) < 0.01,
          f"{d2} {c2:+.0f} 億 ({p2:+.2f}%)")

    # ================================================================
    section("資料日期")
    today = datetime.now(d.tw_tz).strftime("%Y-%m-%d")
    check("報價是今天：只顯示日期", d.quote_date_text({"date": today}) == today)
    check("報價是之前的交易日：標示最近一個交易日",
          d.quote_date_text({"date": "2026-01-02"}) == "2026-01-02（最近一個交易日）")
    check("沒有報價日期：顯示今天", d.quote_date_text({}) == today and d.quote_date_text(None) == today)
    check("日期格式不對時不採用", d._quote_date("abc") == "" and d._quote_date(1685338200) == "")

    # ================================================================
    section("主題（深色／淺色）")
    import plotly.express as px

    common = sys.modules["common"]
    css_by_theme = {}
    for theme in ("dark", "light"):
        st.session_state["theme"] = theme
        captured = []
        orig_md = common.st.markdown
        common.st.markdown = lambda body, **kw: captured.append(body)
        try:
            common.inject_css()
        finally:
            common.st.markdown = orig_md
        css_by_theme[theme] = captured[0]
    dark_css, light_css = css_by_theme["dark"], css_by_theme["light"]
    check("淺色模式的表格會反相成淺色、深色模式不會",
          "invert(1)" in light_css and "invert(1)" not in dark_css)
    for kind in ("Info", "Success", "Warning", "Error"):
        check(f"提示框 {kind} 兩種主題都有設定顏色",
              f"stAlertContent{kind}" in light_css and f"stAlertContent{kind}" in dark_css)
    for sel in ("stSelectbox", "stExpander", "stNumberInputStepUp", "stTextInputRootElement",
                "stBaseButton-secondary", "stBaseLinkButton-secondary", "stCheckbox", "#portal"):
        check(f"CSS 有涵蓋 {sel}", sel in light_css)
    check("文字顏色規則沒有強制 span（否則漲跌的紅綠字會被蓋掉）",
          not re.search(r"(^|[\s,])span\s*,", light_css.split("/* ---------- 輸入框")[0]))

    st.session_state["theme"] = "light"
    lp = common.palette()
    st.session_state["theme"] = "dark"
    dp = common.palette()
    check("淺色主題用較深的漲跌色（白底看得清楚）",
          lp["UP_COLOR"] != dp["UP_COLOR"] and lp["DOWN_COLOR"] != dp["DOWN_COLOR"]
          and lp["WARN_COLOR"] != dp["WARN_COLOR"])

    st.session_state["theme"] = "light"
    fig = px.line(pd.DataFrame({"x": [1, 2], "y": [1, 2]}), x="x", y="y")
    fig.update_layout(margin=dict(t=20))
    common.style_plotly(fig)
    check("圖表跟著淺色主題", fig.layout.template.layout.paper_bgcolor in (None, "white") and
          fig.layout.font.color == lp["TEXT_COLOR"])
    check("圖表自己設的邊距保留，沒設的用緊湊邊距",
          fig.layout.margin.t == 20 and fig.layout.margin.l == 10 and fig.layout.margin.b == 10)
    st.session_state["theme"] = "dark"

except Exception:
    traceback.print_exc()
    check("測試腳本執行完畢", False, "見上方錯誤")

passed = sum(ok for _, ok in results)
print(f"\n共 {len(results)} 項，通過 {passed} 項，失敗 {len(results) - passed} 項")
sys.exit(0 if passed == len(results) else 1)

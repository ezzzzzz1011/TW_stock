# 🚀 TW.stock.app (台股個股/ETF 投資助手)

這是一個基於 Streamlit 開發的台股與 ETF 專屬投資分析系統，專為台灣存股族與價值投資者打造。系統整合了多方金融數據 API 與雲端資料庫，提供即時報價、股息預估與資產視覺化等功能。

🔗 **網站連結：** [點擊這裡開始使用](https://ez-stock-fhedmdgxgniyeyhfxexy3m.streamlit.app/)

## ✨ 核心功能
* **📊 ETF 深度分析**：自動偵測配息頻率（月/季/半年/年），並具備「停發/漏發」智慧校正機制，精準計算預估殖利率。
* **💼 個人資產管理**：可自訂投資組合，並同步儲存於 Google Sheets 雲端資料庫，資料永不遺失。
* **🗓️ 自動化現金流月曆**：將預估的配息入帳日與金額，轉化為直覺的「月月配現金流柱狀圖」。
* **⚔️ ETF 數據 PK 工具**：一鍵對比兩檔 ETF 的價格、漲跌、年配息與實質殖利率。
* **⭐ 雲端關注清單**：自訂你的專屬股票池，隨時掌握最新行情。

## 🛠️ 技術架構
* **前端框架**：Streamlit
* **資料庫**：Google Sheets (透過 `gspread` 與 GCP Service Account 串接)
* **數據來源**：
  * 即時報價：Fugle (富果) API
  * 歷史配息：FinMind API、Yahoo Finance API、HiStock 爬蟲
* **視覺化圖表**：Plotly Express

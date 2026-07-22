# r11 管理員認證與狀態修正版（本機測試）

此版本直接以 Git 標籤 `v0.11.0` 的正常版本為基礎，既有 `web/app.js` 完全未修改，因此保留 r11 的側邊分頁、報表版面與資料呈現方式。

新增內容只有：

- 進入管理頁面前的管理員登入頁。
- 首次啟動自行建立管理員帳密。
- 登入後修改帳號、密碼及登出。
- 管理 API 的 Session 認證。
- Native Agent 讀取 Windows Spooler 的離線／警告／就緒狀態。
- 公開的 `/api/health` 只供 Windows Service 安裝與狀態檢查，不回傳列印資料。

此分支及安裝包只保存在本機；未經使用者確認不得 Push、建立 Pull Request 或發布 GitHub Release。

## 測試及回復

安裝前備份 `C:\ProgramData\PrintGuard`。安裝會保留既有 `data`、`logs` 與 `imports`。若需回復，重新執行原本保留的 r11 安裝包即可。

首次登入後應確認：

1. 左側選單仍為分頁顯示，不會把全部內容排在同一頁。
2. 原有印表機、列印工作與報表資料存在。
3. Windows 顯示離線的 Queue 在 Agent 下一次同步後顯示紅燈。
4. 登出後無法直接呼叫總覽、列印工作與報表 API。

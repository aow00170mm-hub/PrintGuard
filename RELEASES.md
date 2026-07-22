# PrintGuard 評估版本

大型自包含安裝包不提交到Git原始碼歷史。2026-07-22的內部封裝保存在：

`C:\code\PrintGuard-private-backup-20260722\dist\versions`

## r10 本機限定版

檔案：`PrintGuard-Windows-Service-Installer-20260722-r10.zip`

SHA-256：`04BEB7486A3B2CE33760CAC3A7BB36428C7F42B66E43A06A3EFBACCF1CABD681`

- 只監聽 `127.0.0.1:8080`。
- 不建立LAN防火牆規則。
- 保留供本機操作評估及回復。

## v0.12.1 單一 EXE 安裝版

檔案：`PrintGuard-Setup-0.12.1.exe`

- 以 Windows Service 自動啟動 Server 與 Native Agent。
- 公司 Domain 網路可使用 Print Server IP 的 TCP 8080，並提供管理者登入驗證。
- 安裝同版本或較新版本屬於升級，會保留 `C:\ProgramData\PrintGuard` 的資料庫、Log 與匯入資料。
- 從 Windows「已安裝的應用程式」主動解除安裝時，會先顯示永久刪除警告；確認後會刪除服務、防火牆規則及整個 `C:\ProgramData\PrintGuard`，不保留資料庫或其他殘留檔案。
- 安裝程式尚未簽署，正式大規模部署前建議加入程式碼簽章。

SHA-256：`5481F2B99941A5B5AD91DE4426269E7EA5036AF15B3ED4778951D0ADF2D77754`

## r11 公司LAN版

檔案：`PrintGuard-Windows-Service-LAN-Installer-20260722-r11.zip`

SHA-256：`2B6DAFBA1B7D4465A6C56B87DF95E82F70CCE955A47044F648065710593474FC`

- 監聽 `0.0.0.0:8080`。
- 安裝器只放行Windows Domain Profile的TCP 8080。
- Private／Public Profile不放行。
- 不可將8080直接公開到Internet。

## 版本切換

兩版共用 `C:\ProgramData\PrintGuard` 的資料庫、Log與匯入資料。

- r10升級r11：直接執行r11安裝器。
- r11回復r10：執行r10安裝器後，以系統管理員PowerShell移除r11防火牆規則：

```powershell
Get-NetFirewallRule -DisplayName 'PrintGuard Dashboard - Domain TCP 8080' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
```

## GitHub Release

若要在GitHub提供安裝包，請將ZIP上傳為Release Asset，不要加入Git commit。上傳前再次核對SHA-256，並確認ZIP中沒有SQLite、Log、CSV、BIN診斷或公司環境設定。

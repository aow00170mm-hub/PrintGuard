# PrintGuard 安裝、升級與解除安裝手冊

## 適用環境

- Windows Server 2019 或更新版本，x64。
- 伺服器已安裝並啟用 Windows Print Server／Print Spooler。
- 使用具有本機系統管理員權限的帳號安裝。
- LAN 管理介面使用 TCP 8080，只允許 Windows Domain 防火牆設定檔。

## 安裝前準備

若伺服器已經使用 PrintGuard，先備份：

```text
C:\ProgramData\PrintGuard
```

主要資料庫位於：

```text
C:\ProgramData\PrintGuard\data\printguard.db
```

## 使用單檔安裝程式

1. 將 `PrintGuard-Setup.exe` 複製到 Windows Print Server。
2. 雙擊執行；Windows UAC 詢問時選擇「是」。
3. 依安裝精靈按下 Install。
4. 安裝程式會自動停止舊版、更新程式、建立 Windows Service、防火牆規則並啟動服務。
5. 完成後開啟 `http://127.0.0.1:8080`。
6. 首次使用會要求建立管理員帳號與至少 10 個字元的密碼。

不需要開啟 CMD，也不需要手動執行 PowerShell。

## 升級行為

使用相同 `AppId` 的新版 `PrintGuard-Setup.exe` 直接覆蓋安裝：

- 保留 `data`、`logs`、`imports` 與管理員帳密。
- 替換 `bin` 內的 Server、Native Agent 與 Service Host。
- 重建 PrintGuard Windows Service 與 Domain TCP 8080 防火牆規則。
- 升級前仍建議備份整個 `C:\ProgramData\PrintGuard`。

## 確認服務

1. 開啟 `services.msc`。
2. 找到「PrintGuard 列印治理服務」。
3. 狀態應為「執行中」，啟動類型應為「自動（延遲啟動）」。
4. 瀏覽器開啟 `http://127.0.0.1:8080`。
5. LAN 電腦使用 `http://PrintServer-IP:8080`，且網路必須套用 Domain 防火牆設定檔。

## 完整解除安裝

1. 開啟 Windows「設定 → 應用程式 → 已安裝的應用程式」。
2. 找到「PrintGuard 列印治理服務」。
3. 選擇解除安裝。
4. 系統會警告所有資料將永久刪除；確認前先自行備份需要保留的資料。
5. 確認後會自動停止並刪除服務、防火牆規則、程式、資料庫、Log 與匯入檔案。

解除安裝完成後，下列內容都應不存在：

```text
Windows Service：PrintGuard
防火牆規則：PrintGuard Dashboard - Domain TCP 8080
資料夾：C:\ProgramData\PrintGuard
```

## 忘記管理員密碼

目前沒有預設密碼或後門帳號。忘記密碼時不要直接刪除整個資料庫；應先備份 `printguard.db`，再由維護人員執行帳密重設程序。未來版本可加入本機系統管理員專用的重設工具。

## 安全注意事項

- 管理介面目前使用 HTTP，不得直接公開到 Internet。
- 僅允許受信任的公司 Domain 網路存取 TCP 8080。
- GitHub Release 提供 SHA-256，下載後應比對雜湊。
- 未簽署的安裝程式可能顯示「未知的發行者」；正式大規模部署建議購買程式碼簽章憑證。

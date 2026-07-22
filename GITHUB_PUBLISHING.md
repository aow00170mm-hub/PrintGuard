# GitHub 發佈與資料保護說明

## 可以提交的內容

- `server.py`
- `web/`
- `native-agent/` 中的 `.cs`、`.csproj`、`README.md` 及診斷腳本
- `service-host/` 中的 `.cs` 與 `.csproj`
- `deployment-service/` 正式 Windows Service 安裝／狀態／解除安裝腳本
- `tests/`
- 專案根目錄的 Markdown 設計與維運文件
- `.gitignore`

## 不可提交的內容

- `C:\ProgramData\PrintGuard` 的任何實際資料
- `printguard.db`、SQLite WAL／SHM
- Agent／Server／Service Log 與 JSONL
- PaperCut 報表、SHARP 設備 CSV、文件名稱或 AD 使用者資料
- DEVMODE BIN／診斷輸出
- `build`、`.NET bin/obj`、PyInstaller 中間檔
- EXE、DLL、ZIP 安裝包與回復封裝
- 任何本機Agent設定、密碼、Token或內部IP設定

## 安裝包發佈方式

原始碼儲存庫不要直接提交約70MB的自包含安裝ZIP。需要公開安裝包時，應在GitHub建立 Release並將ZIP當作Release Asset上傳，同時公布SHA-256。若儲存庫可能公開，必須先確認安裝包內沒有資料庫、Log、CSV或公司環境設定。

## 首次建立Git儲存庫

本機安裝Git後，在專案根目錄執行：

```powershell
git init
git add .
git status
```

必須先逐項確認 `git status` 沒有 `.db`、`.csv`、`.jsonl`、`.log`、`.bin`、`.exe`、`.dll` 或 `.zip`，確認後才提交：

```powershell
git commit -m "Initial PrintGuard source release"
git branch -M main
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

## 發佈前檢查

```powershell
python -m unittest discover -s tests -v
dotnet build .\native-agent\PrintGuard.NativeAgent.csproj -c Release
dotnet build .\service-host\PrintGuard.ServiceHost.csproj -c Release
```

再次搜尋可能誤放的資料：

```powershell
Get-ChildItem -Recurse -File | Where-Object {
    $_.Extension -in '.db','.csv','.jsonl','.log','.bin','.exe','.dll','.zip'
}
```

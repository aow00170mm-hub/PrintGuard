"""PrintGuard - dependency-free print governance MVP."""
from __future__ import annotations

import json
import mimetypes
import sqlite3
import threading
import csv
import io
import os
import sys
import hashlib
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
APP_ROOT = Path(sys.executable).parent if FROZEN else Path(__file__).parent

def arg_value(name, default=None):
    prefix = f"--{name}="
    return next((x.split("=", 1)[1] for x in sys.argv[1:] if x.startswith(prefix)), default)

DATA_DIR = Path(arg_value("data-dir", os.environ.get("PRINTGUARD_DATA_DIR", APP_ROOT / "data" if FROZEN else APP_ROOT)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = Path(arg_value("log-dir", os.environ.get("PRINTGUARD_LOG_DIR", DATA_DIR.parent / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_RETENTION_DAYS = max(1, int(arg_value("log-retention-days", os.environ.get("PRINTGUARD_LOG_RETENTION_DAYS", "30"))))
IMPORT_DIR = Path(arg_value("import-dir", os.environ.get("PRINTGUARD_IMPORT_DIR", DATA_DIR.parent / "imports")))
IMPORT_DIR.mkdir(parents=True, exist_ok=True)
IMPORT_RETENTION_DAYS = max(1, int(arg_value("import-retention-days", os.environ.get("PRINTGUARD_IMPORT_RETENTION_DAYS", "30"))))
IMPORT_PROCESSED_DIR = IMPORT_DIR / "processed"
IMPORT_FAILED_DIR = IMPORT_DIR / "failed"
IMPORT_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
IMPORT_FAILED_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / "printguard.db"
WEB = BUNDLE_ROOT / "web"
LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Taipei")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS printers (
          id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, location TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'online', color_capable INTEGER NOT NULL DEFAULT 1,
          policy TEXT NOT NULL DEFAULT 'any', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY, printer_id INTEGER NOT NULL REFERENCES printers(id),
          username TEXT NOT NULL, document TEXT NOT NULL, pages INTEGER NOT NULL,
          requested_color INTEGER NOT NULL, effective_color INTEGER NOT NULL,
          status TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS device_profiles (
          id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
          driver_name TEXT NOT NULL DEFAULT '', driver_version INTEGER,
          color_mode TEXT NOT NULL DEFAULT 'auto', duplex_mode TEXT NOT NULL DEFAULT 'auto',
          trust_color_standard INTEGER NOT NULL DEFAULT 0,
          trust_duplex_standard INTEGER NOT NULL DEFAULT 0,
          profile_status TEXT NOT NULL DEFAULT 'auto', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS device_import_batches (
          id INTEGER PRIMARY KEY, filename TEXT NOT NULL, file_sha256 TEXT NOT NULL,
          device_model TEXT, device_serial TEXT, total_rows INTEGER NOT NULL,
          inserted_rows INTEGER NOT NULL, duplicate_rows INTEGER NOT NULL,
          error_rows INTEGER NOT NULL DEFAULT 0, imported_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS device_import_jobs (
          id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
          device_model TEXT, device_serial TEXT NOT NULL, work_id TEXT,
          account_work_id TEXT, job_mode TEXT, computer_name TEXT,
          user_name TEXT, login_name TEXT, started_at TEXT, completed_at TEXT,
          mono_pages INTEGER NOT NULL DEFAULT 0, color_pages INTEGER NOT NULL DEFAULT 0,
          two_color_pages INTEGER NOT NULL DEFAULT 0, single_color_pages INTEGER NOT NULL DEFAULT 0,
          completed_pages INTEGER NOT NULL DEFAULT 0, result TEXT, error_reason TEXT,
          duplex_setting TEXT, document_name TEXT, paper_size TEXT,
          source_file TEXT NOT NULL, imported_at TEXT NOT NULL);
        """)
        # Lightweight migrations keep existing demo databases usable.
        job_columns = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
        for name, definition in {
            "ad_identity": "TEXT", "duplex": "INTEGER NOT NULL DEFAULT 0",
            "copies": "INTEGER NOT NULL DEFAULT 1", "sheets": "INTEGER NOT NULL DEFAULT 0",
            "source": "TEXT NOT NULL DEFAULT 'simulator'",
            "color_known": "INTEGER NOT NULL DEFAULT 1", "duplex_known": "INTEGER NOT NULL DEFAULT 1",
            "source_event_id": "TEXT", "client_machine": "TEXT", "driver_name": "TEXT",
            "datatype": "TEXT", "job_size_bytes": "INTEGER", "paper_size": "INTEGER",
            "status_value": "INTEGER", "applied_policy": "TEXT", "policy_compliant": "INTEGER"
        }.items():
            if name not in job_columns:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        printer_columns = {r[1] for r in db.execute("PRAGMA table_info(printers)")}
        for name, definition in {
            "source": "TEXT NOT NULL DEFAULT 'demo'", "active": "INTEGER NOT NULL DEFAULT 1",
            "driver_name": "TEXT", "port_name": "TEXT", "shared": "INTEGER NOT NULL DEFAULT 0",
            "device_fingerprint": "TEXT", "device_profile_id": "INTEGER"
        }.items():
            if name not in printer_columns:
                db.execute(f"ALTER TABLE printers ADD COLUMN {name} {definition}")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_event ON jobs(source,source_event_id) WHERE source_event_id IS NOT NULL")
        # Event 307 is emitted only after Windows reports the print completed.
        db.execute("UPDATE jobs SET status='completed' WHERE source='windows-event-307' AND status='queued'")
        if not db.execute("SELECT 1 FROM printers").fetchone():
            db.executemany("INSERT INTO printers(name,location,status,color_capable,policy,updated_at) VALUES(?,?,?,?,?,?)", [
                ("財務部-雷射01", "3F 財務部", "online", 1, "mono", now()),
                ("設計部-彩色01", "5F 設計部", "online", 1, "color", now()),
                ("大廳-複合機", "1F 大廳", "warning", 1, "any", now()),
            ])


def rows(sql, args=()):
    with connect() as db:
        return [dict(x) for x in db.execute(sql, args).fetchall()]


def evaluate(policy, capable, requested_color):
    if requested_color and not capable:
        return False, False, "印表機不支援彩色"
    if policy == "mono":
        return True, False, "政策已強制轉為黑白" if requested_color else None
    if policy == "color":
        return True, True, "政策已強制轉為彩色" if not requested_color else None
    return True, bool(requested_color), None


def usage_export(period, value, user_filter="", printer_filter=""):
    if period not in ("daily", "monthly"): raise ValueError("period")
    datetime.strptime(value, "%Y-%m-%d" if period == "daily" else "%Y-%m")
    result = {}
    for job in rows("""SELECT j.*,p.name printer_name FROM jobs j JOIN printers p ON p.id=j.printer_id
                     WHERE j.status='completed' AND j.source!='simulator' ORDER BY j.created_at"""):
        local = datetime.fromisoformat(job["created_at"]).astimezone(LOCAL_TZ)
        key = local.strftime("%Y-%m-%d" if period == "daily" else "%Y-%m")
        identity = job.get("ad_identity") or job["username"]
        if key != value or (user_filter and user_filter.lower() not in identity.lower()): continue
        if printer_filter and str(job["printer_id"]) != str(printer_filter): continue
        group_key = (identity, job["printer_id"])
        item = result.setdefault(group_key, {"identity":identity,"printer":job["printer_name"],"jobs":0,"pages":0,"mono_pages":0,"color_pages":0,"simplex_pages":0,"duplex_pages":0,"sheets":0,"unknown_jobs":0})
        pages = job["pages"] * job.get("copies", 1)
        item["jobs"] += 1; item["pages"] += pages
        if job.get("duplex_known", 1): item["sheets"] += job.get("sheets", pages)
        if job.get("color_known", 1): item["color_pages" if job["effective_color"] else "mono_pages"] += pages
        if job.get("duplex_known", 1): item["duplex_pages" if job.get("duplex") else "simplex_pages"] += pages
        if not job.get("color_known", 1) or not job.get("duplex_known", 1): item["unknown_jobs"] += 1
    return sorted(result.values(), key=lambda x: (-x["pages"], x["identity"].lower(), x["printer"].lower()))


def _csv_int(value):
    try: return max(0, int(str(value or "0").strip()))
    except ValueError: return 0


def _device_identity(row):
    invalid={"","N/A","無驗證","服務","service"}
    for key in ("登入名稱","用戶名稱","電腦名稱"):
        value=str(row.get(key,"")).strip()
        if value not in invalid and value.lower() not in {x.lower() for x in invalid}: return value
    return "未識別使用者"


def import_device_csv(raw, filename):
    if len(raw)>25*1024*1024: raise ValueError("CSV exceeds 25 MB")
    text=None
    for encoding in ("utf-8-sig","cp950"):
        try: text=raw.decode(encoding);break
        except UnicodeDecodeError: pass
    if text is None: raise ValueError("CSV encoding must be UTF-8 or Big5/CP950")
    reader=csv.DictReader(io.StringIO(text,newline=""))
    required={"工作ID","帳戶工作ID","工作模式","開始日期","完成日期","黑白總張數","全彩總張數","結果","型號名稱","單位序號"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)): raise ValueError("Not a supported SHARP job log CSV")
    records=list(reader);inserted=duplicates=errors=0;model=serial=""
    imported=now()
    with connect() as db:
        for row in records:
            try:
                model=str(row.get("型號名稱","")).strip();serial=str(row.get("單位序號","")).strip()
                if not serial or serial=="N/A": raise ValueError("missing device serial")
                canonical="|".join([serial,str(row.get("工作ID","")).strip(),str(row.get("帳戶工作ID","")).strip(),str(row.get("開始日期","")).strip(),str(row.get("完成日期","")).strip(),str(row.get("工作模式","")).strip()])
                fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                values=(fingerprint,model,serial,str(row.get("工作ID","")).strip(),str(row.get("帳戶工作ID","")).strip(),
                  str(row.get("工作模式","")).strip(),str(row.get("電腦名稱","")).strip(),str(row.get("用戶名稱","")).strip(),
                  _device_identity(row),str(row.get("開始日期","")).strip(),str(row.get("完成日期","")).strip(),
                  _csv_int(row.get("黑白總張數")),_csv_int(row.get("全彩總張數")),_csv_int(row.get("2色總張數")),
                  _csv_int(row.get("單色總張數")),_csv_int(row.get("完成頁數")),str(row.get("結果","")).strip(),
                  str(row.get("錯誤原因","")).strip(),str(row.get("雙面設定","")).strip(),str(row.get("檔案名稱","")).strip(),
                  str(row.get("紙張規格","")).strip(),filename,imported)
                cur=db.execute("""INSERT OR IGNORE INTO device_import_jobs(fingerprint,device_model,device_serial,work_id,account_work_id,
                  job_mode,computer_name,user_name,login_name,started_at,completed_at,mono_pages,color_pages,two_color_pages,
                  single_color_pages,completed_pages,result,error_reason,duplex_setting,document_name,paper_size,source_file,imported_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",values)
                if cur.rowcount: inserted+=1
                else: duplicates+=1
            except Exception: errors+=1
        db.execute("""INSERT INTO device_import_batches(filename,file_sha256,device_model,device_serial,total_rows,inserted_rows,duplicate_rows,error_rows,imported_at)
          VALUES(?,?,?,?,?,?,?,?,?)""",(filename,hashlib.sha256(raw).hexdigest(),model,serial,len(records),inserted,duplicates,errors,imported))
    return {"ok":True,"filename":filename,"device_model":model,"device_serial":serial,"total_rows":len(records),"inserted_rows":inserted,"duplicate_rows":duplicates,"error_rows":errors}


def _archive_import(file, target_dir):
    target=target_dir/file.name
    if target.exists():
        stamp=datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target=target_dir/f"{file.stem}-{stamp}{file.suffix}"
    shutil.move(str(file),str(target))
    return target


def cleanup_device_imports():
    cutoff=datetime.now().timestamp()-IMPORT_RETENTION_DAYS*86400
    for folder in (IMPORT_PROCESSED_DIR,IMPORT_FAILED_DIR):
        for file in folder.rglob("*"):
            try:
                if file.is_file() and file.stat().st_mtime<cutoff: file.unlink()
            except OSError: pass


def scan_device_imports():
    cleanup_device_imports()
    for file in IMPORT_DIR.glob("*.csv"):
        # Avoid taking a file that is still being copied into the watched folder.
        try:
            if datetime.now().timestamp()-file.stat().st_mtime<5: continue
        except OSError: continue
        try:
            raw=file.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            with connect() as db: exists=db.execute("SELECT 1 FROM device_import_batches WHERE file_sha256=? LIMIT 1",(digest,)).fetchone()
            if not exists: import_device_csv(raw,file.name)
            _archive_import(file,IMPORT_PROCESSED_DIR)
        except Exception as exc:
            print(f"Device CSV auto-import skipped {file.name}: {exc}",file=sys.stderr,flush=True)
            try: _archive_import(file,IMPORT_FAILED_DIR)
            except OSError as archive_exc: print(f"Device CSV failure archive skipped {file.name}: {archive_exc}",file=sys.stderr,flush=True)


def import_watcher():
    while True:
        scan_device_imports()
        threading.Event().wait(60)


def device_usage_export(period,value,user_filter=""):
    if period not in ("daily","monthly"): raise ValueError("period")
    datetime.strptime(value,"%Y-%m-%d" if period=="daily" else "%Y-%m")
    result={};prefix=value
    for job in rows("SELECT * FROM device_import_jobs WHERE result='OK' AND started_at LIKE ? ORDER BY started_at",(prefix+"%",)):
        identity=job["login_name"] or "未識別使用者"
        if user_filter and user_filter.lower() not in identity.lower(): continue
        printer=f'{job["device_model"] or "未知型號"} ({job["device_serial"]})'
        group_key=(identity,job["device_serial"])
        item=result.setdefault(group_key,{"identity":identity,"printer":printer,"jobs":0,"pages":0,"mono_pages":0,"color_pages":0,"simplex_pages":0,"duplex_pages":0,"sheets":0,"unknown_jobs":0,"source":"device-import"})
        mono=job["mono_pages"];color=job["color_pages"]+job["two_color_pages"]+job["single_color_pages"];pages=mono+color
        duplex="雙面" in (job["duplex_setting"] or "")
        item["jobs"]+=1;item["pages"]+=pages;item["mono_pages"]+=mono;item["color_pages"]+=color
        item["duplex_pages" if duplex else "simplex_pages"]+=pages
        item["sheets"]+=(pages+1)//2 if duplex else pages
    return sorted(result.values(),key=lambda x:(-x["pages"],x["identity"].lower(),x["printer"].lower()))


REPORT_METRICS=("jobs","pages","mono_pages","color_pages","simplex_pages","duplex_pages","sheets","unknown_jobs")


def regroup_report(items,group):
    if group not in ("user","user_printer","printer"): raise ValueError("group")
    if group=="user_printer":
        return sorted(items,key=lambda x:(-x["pages"],x["identity"].lower(),x["printer"].lower(),x["source"]))
    result={};members={}
    for row in items:
        key=(row["source"],row["identity"] if group=="user" else row["printer"])
        if key not in result:
            result[key]={"source":row["source"],"identity":row["identity"] if group=="user" else "",
                         "printer":row["printer"] if group=="printer" else "",**{name:0 for name in REPORT_METRICS}}
            members[key]=set()
        for name in REPORT_METRICS: result[key][name]+=row[name]
        members[key].add(row["printer"] if group=="user" else row["identity"])
    for key,row in result.items(): row["printer_count" if group=="user" else "user_count"]=len(members[key])
    label="identity" if group=="user" else "printer"
    return sorted(result.values(),key=lambda x:(-x["pages"],x[label].lower(),x["source"]))


def report_by_source(source,period,value,user_filter="",printer_filter="",group="user"):
    live=usage_export(period,value,user_filter,printer_filter)
    for x in live: x["source"]="printguard"
    device=device_usage_export(period,value,user_filter)
    items=device if source=="device" else live+device if source=="combined" else live
    return regroup_report(items,group)


def sync_devices(devices):
    """Upsert discovered queues and reusable hardware/driver capability profiles."""
    if not isinstance(devices, list): raise ValueError("printers must be an array")
    with connect() as db:
        db.execute("UPDATE printers SET active=0 WHERE source IN ('windows','demo')")
        for item in devices:
            name=str(item.get("name","")).strip()
            if not name: continue
            status=item.get("status","warning")
            if status not in ("online","warning","offline"): status="warning"
            fingerprint=str(item.get("device_fingerprint") or "").strip()
            profile_id=None
            if fingerprint:
                color_mode="mono" if item.get("supports_color") is False else "auto"
                duplex_mode="simplex" if item.get("supports_duplex") is False else "auto"
                db.execute("""INSERT INTO device_profiles(fingerprint,driver_name,driver_version,color_mode,duplex_mode,profile_status,updated_at)
                  VALUES(?,?,?,?,?,'auto',?) ON CONFLICT(fingerprint) DO UPDATE SET driver_name=excluded.driver_name,
                  driver_version=excluded.driver_version,updated_at=excluded.updated_at""",
                  (fingerprint,str(item.get("driver_name","")),item.get("driver_version"),color_mode,duplex_mode,now()))
                profile_id=db.execute("SELECT id FROM device_profiles WHERE fingerprint=?",(fingerprint,)).fetchone()["id"]
            db.execute("""INSERT INTO printers(name,location,status,color_capable,policy,updated_at,source,active,driver_name,port_name,shared,device_fingerprint,device_profile_id)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET location=excluded.location,status=excluded.status,
              updated_at=excluded.updated_at,source='windows',active=1,driver_name=excluded.driver_name,port_name=excluded.port_name,
              shared=excluded.shared,device_fingerprint=excluded.device_fingerprint,device_profile_id=excluded.device_profile_id""",
              (name,str(item.get("location") or item.get("port_name") or "Windows"),status,1,"any",now(),"windows",1,
               str(item.get("driver_name","")),str(item.get("port_name","")),bool(item.get("shared")),fingerprint,profile_id))
        current=list(db.execute("""SELECT p.id,p.name,p.policy,d.color_mode,d.duplex_mode,d.trust_color_standard,d.trust_duplex_standard,d.profile_status
          FROM printers p LEFT JOIN device_profiles d ON d.id=p.device_profile_id WHERE p.source='windows' AND p.active=1"""))
        return {"ok":True,"printer_map":{r["name"]:r["id"] for r in current},
          "policy_map":{r["name"]:r["policy"] for r in current},
          "profile_map":{r["name"]:{"color_mode":r["color_mode"] or "auto","duplex_mode":r["duplex_mode"] or "auto",
            "trust_color_standard":bool(r["trust_color_standard"]),"trust_duplex_standard":bool(r["trust_duplex_standard"]),
            "profile_status":r["profile_status"] or "needs_review"} for r in current}}


class API(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        message = f"[{now()}] {fmt % args}\n"
        with (LOG_DIR / f"server-{datetime.now(LOCAL_TZ):%Y%m%d}.log").open("a", encoding="utf-8") as stream:
            stream.write(message)
        if not FROZEN: print(message, end="")

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def send_csv(self, data, filename, group="user"):
        output = io.StringIO(); writer = csv.writer(output)
        metrics=["工作數","總頁數","黑白頁數","彩色頁數","單面頁數","雙面頁數","紙張張數","資料待補筆數"]
        if group=="user":
            writer.writerow(["資料來源","使用者",*metrics,"使用印表機數"])
            for x in data: writer.writerow([x.get("source","printguard"),x["identity"],*[x[n] for n in REPORT_METRICS],x["printer_count"]])
        elif group=="printer":
            writer.writerow(["資料來源","印表機",*metrics,"使用人數"])
            for x in data: writer.writerow([x.get("source","printguard"),x["printer"],*[x[n] for n in REPORT_METRICS],x["user_count"]])
        else:
            writer.writerow(["資料來源","使用者","印表機",*metrics])
            for x in data: writer.writerow([x.get("source","printguard"),x["identity"],x["printer"],*[x[n] for n in REPORT_METRICS]])
        body = ("\ufeff" + output.getvalue()).encode("utf-8")
        self.send_response(200); self.send_header("Content-Type","text/csv; charset=utf-8")
        self.send_header("Content-Disposition",f'attachment; filename="{filename}"'); self.send_header("Content-Length",str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def body(self):
        size = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(size) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path); path = parsed.path
        if path == "/api/dashboard":
            local_now = datetime.now(LOCAL_TZ)
            local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            utc_start = local_start.astimezone(timezone.utc).isoformat(timespec="seconds")
            utc_end = (local_start + timedelta(days=1)).astimezone(timezone.utc).isoformat(timespec="seconds")
            printers = rows("""SELECT p.*,d.color_mode,d.duplex_mode,d.trust_color_standard,
              d.trust_duplex_standard,d.profile_status,d.fingerprint profile_fingerprint
              FROM printers p LEFT JOIN device_profiles d ON d.id=p.device_profile_id
              WHERE p.active=1 ORDER BY p.id""")
            jobs = rows("SELECT j.*,p.name printer_name FROM jobs j JOIN printers p ON p.id=j.printer_id WHERE j.source!='simulator' ORDER BY j.id DESC LIMIT 5")
            totals = rows("""SELECT COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),0) jobs,
              COALESCE(SUM(CASE WHEN status='completed' THEN pages*copies ELSE 0 END),0) pages,
              COALESCE(SUM(CASE WHEN status='blocked' THEN 1 ELSE 0 END),0) blocked
              FROM jobs WHERE source!='simulator' AND created_at>=? AND created_at<?""", (utc_start, utc_end))[0]
            return self.send_json({"printers": printers, "jobs": jobs, "totals": totals})
        if path == "/api/audit":
            return self.send_json(rows("SELECT * FROM audit ORDER BY id DESC LIMIT 50"))
        if path == "/api/violations":
            return self.send_json(rows("""SELECT j.*,p.name printer_name FROM jobs j JOIN printers p ON p.id=j.printer_id
              WHERE j.status='blocked' AND j.source!='simulator' ORDER BY j.id DESC LIMIT 50"""))
        if path == "/api/reports/usage":
            query=parse_qs(parsed.query)
            if query.get("period"):
                period=query["period"][0]; default=datetime.now(LOCAL_TZ).strftime("%Y-%m-%d" if period=="daily" else "%Y-%m")
                value=query.get("date" if period=="daily" else "month",[default])[0]
                try: return self.send_json(report_by_source(query.get("source",["printguard"])[0],period,value,query.get("user",[""])[0],query.get("printer_id",[""])[0],query.get("group",["user"])[0]))
                except ValueError: return self.send_json({"error":"日期或報表類型無效"},400)
            report = rows("""SELECT COALESCE(ad_identity,username) identity,COUNT(*) jobs,SUM(pages*copies) pages,
              SUM(CASE WHEN duplex_known=1 THEN sheets ELSE 0 END) sheets,SUM(CASE WHEN color_known=1 AND effective_color=1 THEN pages*copies ELSE 0 END) color_pages,
              SUM(CASE WHEN color_known=1 AND effective_color=0 THEN pages*copies ELSE 0 END) mono_pages,
              SUM(CASE WHEN duplex_known=1 AND duplex=1 THEN pages*copies ELSE 0 END) duplex_pages,
              SUM(CASE WHEN duplex_known=1 AND duplex=0 THEN pages*copies ELSE 0 END) simplex_pages,
              SUM(CASE WHEN color_known=0 OR duplex_known=0 THEN 1 ELSE 0 END) unknown_jobs
              FROM jobs WHERE status='completed' AND source!='simulator' GROUP BY COALESCE(ad_identity,username) ORDER BY pages DESC""")
            return self.send_json(report)
        if path == "/api/reports/export.csv":
            query = parse_qs(parsed.query); period = query.get("period",["daily"])[0]
            default = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d" if period == "daily" else "%Y-%m")
            value = query.get("date" if period == "daily" else "month",[default])[0]
            group=query.get("group",["user"])[0]
            try: data = report_by_source(query.get("source",["printguard"])[0],period,value,query.get("user",[""])[0],query.get("printer_id",[""])[0],group)
            except ValueError: return self.send_json({"error":"日期或報表類型無效"},400)
            return self.send_csv(data,f"printguard-{group}-{period}-{value}.csv",group)
        if path == "/api/device-imports":
            return self.send_json(rows("SELECT * FROM device_import_batches ORDER BY id DESC LIMIT 20"))
        rel = "index.html" if path == "/" else path.lstrip("/")
        target = (WEB / rel).resolve()
        if WEB.resolve() not in target.parents and target != WEB.resolve():
            return self.send_error(403)
        if not target.is_file(): return self.send_error(404)
        data = target.read_bytes(); self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_PATCH(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/printers/"): return self.send_error(404)
        try: pid = int(path.rsplit("/", 1)[1]); data = self.body()
        except (ValueError, json.JSONDecodeError): return self.send_json({"error":"格式錯誤"}, 400)
        policy = data.get("policy")
        if policy not in ("any", "mono", "color"): return self.send_json({"error":"無效政策"}, 400)
        with connect() as db:
            cur = db.execute("UPDATE printers SET policy=?,updated_at=? WHERE id=?", (policy, now(), pid))
            if not cur.rowcount: return self.send_json({"error":"找不到印表機"}, 404)
            db.execute("INSERT INTO audit(action,detail,created_at) VALUES(?,?,?)", ("policy.changed", f"印表機 #{pid} 政策改為 {policy}", now()))
        self.send_json({"ok": True})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/device-imports":
            try:
                size=int(self.headers.get("Content-Length",0))
                if size<1: raise ValueError("empty CSV")
                raw=self.rfile.read(size);filename=Path(unquote(self.headers.get("X-Filename","printer-report.csv"))).name
                return self.send_json(import_device_csv(raw,filename),201)
            except (ValueError,OSError) as exc: return self.send_json({"error":str(exc)},400)
        if path == "/api/printers/sync":
            try: return self.send_json(sync_devices(self.body().get("printers",[])))
            except (ValueError,json.JSONDecodeError) as exc: return self.send_json({"error":str(exc)},400)
        if path.startswith("/api/device-profiles/"):
            try: pid=int(path.rsplit("/",1)[1]);data=self.body()
            except (ValueError,json.JSONDecodeError): return self.send_json({"error":"invalid request"},400)
            allowed={"color_mode":("auto","mono","color"),"duplex_mode":("auto","simplex","duplex"),"profile_status":("auto","verified","needs_review")}
            changes={k:data[k] for k in (*allowed,"trust_color_standard","trust_duplex_standard") if k in data}
            if not changes or any(k in allowed and v not in allowed[k] for k,v in changes.items()): return self.send_json({"error":"invalid profile values"},400)
            with connect() as db:
                printer=db.execute("SELECT device_profile_id FROM printers WHERE id=?",(pid,)).fetchone()
                if not printer or not printer["device_profile_id"]: return self.send_json({"error":"device profile unavailable"},404)
                fields=[];values=[]
                for key,value in changes.items(): fields.append(f"{key}=?");values.append(bool(value) if key.startswith("trust_") else value)
                fields.append("updated_at=?");values.extend([now(),printer["device_profile_id"]])
                db.execute(f"UPDATE device_profiles SET {','.join(fields)} WHERE id=?",values)
                db.execute("INSERT INTO audit(action,detail,created_at) VALUES(?,?,?)",("device-profile.changed",f"printer #{pid}: {changes}",now()))
            return self.send_json({"ok":True})
        if path == "/api/jobs/native/complete":
            try: key = str(self.body()["native_job_key"])
            except (KeyError,json.JSONDecodeError): return self.send_json({"error":"缺少 native_job_key"},400)
            with connect() as db: db.execute("UPDATE jobs SET status='completed' WHERE source='windows-spooler-native' AND source_event_id=? AND status!='blocked'",(key,))
            return self.send_json({"ok":True})
        if path == "/api/jobs/native":
            try:
                data=self.body(); key=str(data["native_job_key"]); pages=max(1,int(data.get("pages",1))); copies=max(1,int(data.get("copies",1)))
            except (KeyError,ValueError,TypeError,json.JSONDecodeError) as exc: return self.send_json({"error":"原生工作格式錯誤","detail":str(exc)},400)
            color=bool(data.get("color")); duplex=bool(data.get("duplex")); identity=str(data.get("ad_identity") or data.get("username") or "unknown")
            sheets=((pages+1)//2 if duplex else pages)*copies
            with connect() as db:
                if data.get("printer_id"): printer=db.execute("SELECT id FROM printers WHERE id=?",(int(data["printer_id"]),)).fetchone()
                else: printer=db.execute("SELECT id FROM printers WHERE name=?",(str(data.get("printer_name","")),)).fetchone()
                if not printer: return self.send_json({"error":"找不到已同步的印表機","printer_name":data.get("printer_name")},404)
                pid=printer["id"]
                values=(pid,identity,str(data.get("document","列印文件")),pages,color,color,str(data.get("status","printing")),data.get("reason"),now(),identity,duplex,copies,sheets,"windows-spooler-native",bool(data.get("color_known")),bool(data.get("duplex_known")),key,data.get("client_machine"),data.get("driver_name"),data.get("datatype"),data.get("job_size_bytes"),data.get("paper_size"),data.get("status_value"),data.get("applied_policy"),data.get("policy_compliant"))
                existing=db.execute("SELECT id FROM jobs WHERE source='windows-spooler-native' AND source_event_id=?",(key,)).fetchone()
                if existing:
                    db.execute("UPDATE jobs SET pages=MAX(pages,?),copies=?,requested_color=?,effective_color=?,duplex=?,sheets=MAX(sheets,?),color_known=?,duplex_known=?,status=?,reason=?,client_machine=?,driver_name=?,datatype=?,job_size_bytes=?,paper_size=?,status_value=?,applied_policy=?,policy_compliant=? WHERE id=?",(pages,copies,color,color,duplex,sheets,bool(data.get("color_known")),bool(data.get("duplex_known")),str(data.get("status","printing")),data.get("reason"),data.get("client_machine"),data.get("driver_name"),data.get("datatype"),data.get("job_size_bytes"),data.get("paper_size"),data.get("status_value"),data.get("applied_policy"),data.get("policy_compliant"),existing["id"]))
                    jid=existing["id"]
                else:
                    cur=db.execute("INSERT INTO jobs(printer_id,username,document,pages,requested_color,effective_color,status,reason,created_at,ad_identity,duplex,copies,sheets,source,color_known,duplex_known,source_event_id,client_machine,driver_name,datatype,job_size_bytes,paper_size,status_value,applied_policy,policy_compliant) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",values);jid=cur.lastrowid
            return self.send_json({"id":jid,"ok":True},201)
        if path == "/api/printers/sync":
            try: devices = self.body().get("printers", [])
            except json.JSONDecodeError: return self.send_json({"error":"格式錯誤"}, 400)
            if not isinstance(devices, list): return self.send_json({"error":"printers 必須是陣列"}, 400)
            with connect() as db:
                db.execute("UPDATE printers SET active=0 WHERE source IN ('windows','demo')")
                for item in devices:
                    name = str(item.get("name", "")).strip()
                    if not name: continue
                    status = item.get("status", "warning")
                    if status not in ("online","warning","offline"): status = "warning"
                    db.execute("""INSERT INTO printers(name,location,status,color_capable,policy,updated_at,source,active,driver_name,port_name,shared)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET location=excluded.location,status=excluded.status,
                      updated_at=excluded.updated_at,source='windows',active=1,driver_name=excluded.driver_name,port_name=excluded.port_name,shared=excluded.shared""",
                      (name,str(item.get("location") or item.get("port_name") or "Windows"),status,1,"any",now(),"windows",1,str(item.get("driver_name", "")),str(item.get("port_name", "")),bool(item.get("shared"))))
                current = list(db.execute("SELECT id,name,policy FROM printers WHERE source='windows' AND active=1"))
                mapping = {r["name"]:r["id"] for r in current}; policies = {r["name"]:r["policy"] for r in current}
            return self.send_json({"ok":True,"printer_map":mapping,"policy_map":policies})
        if path != "/api/jobs": return self.send_error(404)
        try:
            data = self.body(); pid = int(data["printer_id"]); pages = int(data["pages"])
            if pages < 1 or pages > 10000: raise ValueError
            username = str(data["username"]).strip(); document = str(data["document"]).strip(); copies = int(data.get("copies", 1))
            if copies < 1 or copies > 1000: raise ValueError
            if not username or not document: raise ValueError
        except (KeyError, ValueError, json.JSONDecodeError): return self.send_json({"error":"請提供有效的工作資料"}, 400)
        with connect() as db:
            p = db.execute("SELECT * FROM printers WHERE id=?", (pid,)).fetchone()
            if not p: return self.send_json({"error":"找不到印表機"}, 404)
            requested = bool(data.get("color")); identity = str(data.get("ad_identity") or username)
            allowed, effective, reason = evaluate(p["policy"], p["color_capable"], requested)
            source = str(data.get("source", "simulator"))
            status = ("completed" if source == "windows-event-307" else "queued") if allowed else "blocked"
            duplex = bool(data.get("duplex"))
            sheets = ((pages + 1) // 2 if duplex else pages) * copies
            event_id = str(data["source_event_id"]) if data.get("source_event_id") is not None else None
            existing = db.execute("SELECT id,status FROM jobs WHERE source=? AND source_event_id=?", (source,event_id)).fetchone() if event_id else None
            if existing: return self.send_json({"id":existing["id"],"status":existing["status"],"duplicate":True})
            cur = db.execute("INSERT INTO jobs(printer_id,username,document,pages,requested_color,effective_color,status,reason,created_at,ad_identity,duplex,copies,sheets,source,color_known,duplex_known,source_event_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (pid, username, document, pages, requested, effective, status, reason, now(), identity, duplex, copies, sheets, source, bool(data.get("color_known", True)), bool(data.get("duplex_known", True)), event_id))
            jid = cur.lastrowid
            db.execute("INSERT INTO audit(action,detail,created_at) VALUES(?,?,?)", (f"job.{status}", f"工作 #{jid}: {document}" + (f"（{reason}）" if reason else ""), now()))
        self.send_json({"id": jid, "status": status, "effective_color": effective, "reason": reason}, 201)


def main():
    host = arg_value("host", os.environ.get("PRINTGUARD_HOST", "127.0.0.1")); port = int(arg_value("port", os.environ.get("PRINTGUARD_PORT", "8080")))
    cutoff = datetime.now().timestamp() - LOG_RETENTION_DAYS * 86400
    for file in LOG_DIR.rglob("*"):
        try:
            if file.is_file() and file.stat().st_mtime < cutoff: file.unlink()
        except OSError: pass
    if "--check" in sys.argv[1:]:
        init_db()
        if not (WEB / "index.html").is_file(): raise RuntimeError(f"Web assets missing: {WEB}")
        print(f"PrintGuard server check OK (data: {DATA_DIR}, web: {WEB})")
        return
    init_db(); scan_device_imports(); threading.Thread(target=import_watcher,daemon=True,name="device-csv-import").start(); server = ThreadingHTTPServer((host, port), API)
    print(f"PrintGuard running at http://{host}:{port} (data: {DATA_DIR})", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__": main()

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


class NativeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.original_db = server.DB
        server.DB = Path(self.temp.name) / "test.db"
        server.init_db()
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.API)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"
        self.cookie=None
        self.request("/api/auth/setup","POST",{"username":"admin","password":"PrintGuard-Test-123!"})

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        server.DB = self.original_db
        self.temp.cleanup()

    def request(self, path, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method,
                      headers={"Content-Type":"application/json",**({"Cookie":self.cookie} if self.cookie else {})})
        with urlopen(req, timeout=3) as response:
            if response.headers.get("Set-Cookie"):self.cookie=response.headers["Set-Cookie"].split(";",1)[0]
            return json.loads(response.read())

    def request_raw(self,path,body,filename="device.csv"):
        req=Request(self.base+path,data=body,method="POST",headers={"Content-Type":"text/csv","X-Filename":filename,**({"Cookie":self.cookie} if self.cookie else {})})
        with urlopen(req,timeout=3) as response: return json.loads(response.read())

    def request_text(self,path):
        req=Request(self.base+path,headers=({"Cookie":self.cookie} if self.cookie else {}))
        with urlopen(req,timeout=3) as response:return response.read().decode("utf-8-sig")

    def test_admin_login_protects_dashboard_and_reports(self):
        self.request("/api/auth/logout","POST",{});self.cookie=None
        with urlopen(self.base+"/",timeout=3) as response:
            self.assertIn("列印服務總覽",response.read().decode("utf-8"))
        public=self.request("/api/public/dashboard")
        self.assertEqual(set(public),{"totals","devices"})
        self.assertEqual(set(public["totals"]),{"jobs","pages","blocked"})
        self.assertEqual(set(public["devices"]),{"total","online","warning","offline"})
        for path in ("/api/dashboard","/api/reports/usage?period=daily&date=2026-07-22"):
            with self.assertRaises(HTTPError) as denied:self.request(path)
            self.assertEqual(denied.exception.code,401);denied.exception.close()
        with self.assertRaises(HTTPError) as wrong:self.request("/api/auth/login","POST",{"username":"admin","password":"wrong-password"})
        self.assertEqual(wrong.exception.code,401);wrong.exception.close()
        result=self.request("/api/auth/login","POST",{"username":"admin","password":"PrintGuard-Test-123!"})
        self.assertEqual(result["username"],"admin");self.assertIn("totals",self.request("/api/dashboard"))

    def test_web_policy_sync_and_blocked_jobs_are_excluded(self):
        sync_body = {"printers": [{"name": "VEN_02_test", "status": "online"}]}
        first = self.request("/api/printers/sync", "POST", sync_body)
        printer_id = first["printer_map"]["VEN_02_test"]
        self.request(f"/api/printers/{printer_id}", "PATCH", {"policy": "mono"})
        second = self.request("/api/printers/sync", "POST", sync_body)
        self.assertEqual(second["policy_map"]["VEN_02_test"], "mono")

        common = {"printer_id": printer_id, "printer_name": "VEN_02_test",
                  "username": "SERV\\tester", "document": "test.docx",
                  "pages": 2, "copies": 1, "color_known": True,
                  "duplex_known": True, "duplex": False}
        blocked = dict(common, native_job_key="blocked-1", color=True,
                       status="blocked", applied_policy="mono",
                       policy_compliant=False, reason="Blocked by mono policy")
        self.request("/api/jobs/native", "POST", blocked)
        self.request("/api/jobs/native/complete", "POST", {"native_job_key": "blocked-1"})

        completed = dict(common, native_job_key="completed-1", color=False,
                         status="printing", applied_policy="mono",
                         policy_compliant=True)
        self.request("/api/jobs/native", "POST", completed)
        self.request("/api/jobs/native/complete", "POST", {"native_job_key": "completed-1"})

        dashboard = self.request("/api/dashboard")
        self.assertEqual(dashboard["totals"]["jobs"], 1)
        self.assertEqual(dashboard["totals"]["pages"], 2)
        self.assertEqual(dashboard["totals"]["blocked"], 1)
        today = server.datetime.now(server.LOCAL_TZ).strftime("%Y-%m-%d")
        report = self.request(f"/api/reports/usage?period=daily&source=printguard&group=user_printer&date={today}")
        self.assertEqual(report[0]["printer"], "VEN_02_test")
        exported = self.request_text(f"/api/reports/export.csv?period=daily&source=printguard&group=user_printer&date={today}")
        self.assertIn("資料來源,使用者,印表機,工作數", exported.splitlines()[0])
        self.assertIn("VEN_02_test", exported)
        violations = self.request("/api/violations")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["status"], "blocked")

        # Dashboard cards are daily totals; historical jobs remain visible in
        # reports but must not be counted as today's work or policy blocks.
        with server.connect() as db:
            db.execute("UPDATE jobs SET created_at='2000-01-01T00:00:00+00:00'")
        historical_dashboard = self.request("/api/dashboard")
        self.assertEqual(historical_dashboard["totals"], {"jobs": 0, "pages": 0, "blocked": 0})

    def test_device_profile_is_reused_and_new_fingerprint_redetects(self):
        mono = {"name":"Mono-A","status":"offline","status_detail":"離線測試","status_value":128,"attributes":1024,"driver_name":"Universal PCL6",
                "driver_version":123,"port_name":"IP_1","device_fingerprint":"fingerprint-mono",
                "supports_color":False,"supports_duplex":False}
        first=self.request("/api/printers/sync","POST",{"printers":[mono]})
        pid=first["printer_map"]["Mono-A"]
        printer=next(x for x in self.request("/api/dashboard")["printers"] if x["id"]==pid)
        self.assertEqual((printer["status"],printer["status_detail"],printer["status_value"]),("offline","離線測試",128))
        self.assertEqual(first["profile_map"]["Mono-A"]["color_mode"],"mono")
        self.assertEqual(first["profile_map"]["Mono-A"]["duplex_mode"],"simplex")
        self.request(f"/api/device-profiles/{pid}","POST",{"profile_status":"verified"})

        same=dict(mono,name="Mono-B",port_name="IP_2")
        reused=self.request("/api/printers/sync","POST",{"printers":[mono,same]})
        self.assertEqual(reused["profile_map"]["Mono-B"]["profile_status"],"verified")

        changed=dict(mono,name="Mono-A",device_fingerprint="fingerprint-new",supports_color=True)
        redetected=self.request("/api/printers/sync","POST",{"printers":[changed]})
        self.assertEqual(redetected["profile_map"]["Mono-A"]["color_mode"],"auto")
        self.assertEqual(redetected["profile_map"]["Mono-A"]["profile_status"],"auto")

    def test_sharp_csv_reimport_is_deduplicated(self):
        headers=["工作ID","帳戶工作ID","工作模式","電腦名稱","用戶名稱","登入名稱","開始日期","完成日期",
                 "黑白總張數","全彩總張數","2色總張數","單色總張數","完成頁數","結果","錯誤原因",
                 "雙面設定","檔案名稱","紙張規格","型號名稱","單位序號"]
        values=["100","101","列印","PC-01","王小明","SERV\\user1","2026-07-21T09:00:00","2026-07-21T09:00:10",
                "2","1","0","0","3","OK","N/A","雙面","report.pdf","A4","MX-4140FN","4500014400"]
        import csv,io
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(headers);writer.writerow(values);raw=stream.getvalue().encode("cp950")
        first=self.request_raw("/api/device-imports",raw)
        second=self.request_raw("/api/device-imports",raw)
        self.assertEqual((first["inserted_rows"],first["duplicate_rows"]),(1,0))
        self.assertEqual((second["inserted_rows"],second["duplicate_rows"]),(0,1))
        report=self.request("/api/reports/usage?period=daily&source=device&group=user_printer&date=2026-07-21")
        self.assertEqual(len(report),1);self.assertEqual(report[0]["pages"],3)
        self.assertEqual(report[0]["printer"],"MX-4140FN (4500014400)")
        self.assertEqual(report[0]["mono_pages"],2);self.assertEqual(report[0]["color_pages"],1)

    def test_report_can_switch_between_user_detail_and_printer_groups(self):
        base={"source":"printguard","identity":"SERV\\traveler","jobs":1,"pages":2,"mono_pages":2,
              "color_pages":0,"simplex_pages":2,"duplex_pages":0,"sheets":2,"unknown_jobs":0}
        details=[dict(base,printer="PRINT_A"),dict(base,printer="PRINT_B",jobs=2,pages=4,mono_pages=4,
                 simplex_pages=4,sheets=4)]
        user=server.regroup_report(details,"user")
        self.assertEqual(len(user),1);self.assertEqual(user[0]["jobs"],3);self.assertEqual(user[0]["printer_count"],2)
        self.assertEqual(len(server.regroup_report(details,"user_printer")),2)
        printers=server.regroup_report(details,"printer")
        self.assertEqual(len(printers),2);self.assertTrue(all(x["user_count"]==1 for x in printers))


if __name__ == "__main__":
    unittest.main()

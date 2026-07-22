using System.Net.Http.Json;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text;
using System.Collections.Concurrent;
using System.Security.Cryptography;

var offline=args.Any(x=>x.Equals("--offline",StringComparison.OrdinalIgnoreCase));
var redactDocuments=args.Any(x=>x.Equals("--redact-documents",StringComparison.OrdinalIgnoreCase));
var includeExisting=args.Any(x=>x.Equals("--include-existing",StringComparison.OrdinalIgnoreCase));
var enableEnforcement=args.Any(x=>x.Equals("--enable-enforcement",StringComparison.OrdinalIgnoreCase));
var api=args.FirstOrDefault(x=>x.StartsWith("--api="))?.Split('=',2)[1] ?? "http://127.0.0.1:8080";
var queueFilter=args.FirstOrDefault(x=>x.StartsWith("--queue="))?.Split('=',2)[1];
var outputArg=args.FirstOrDefault(x=>x.StartsWith("--output="))?.Split('=',2)[1];
var policyConfigArg=args.FirstOrDefault(x=>x.StartsWith("--policy-config="))?.Split('=',2)[1];
var outputDir=Path.GetFullPath(outputArg??Path.Combine(AppContext.BaseDirectory,"logs"));
var durationText=args.FirstOrDefault(x=>x.StartsWith("--duration-minutes="))?.Split('=',2)[1];
var retentionText=args.FirstOrDefault(x=>x.StartsWith("--log-retention-days="))?.Split('=',2)[1];
var durationMinutes=double.TryParse(durationText,out var parsedDuration)?Math.Max(0,parsedDuration):0;
var retentionDays=int.TryParse(retentionText,out var parsedRetention)?Math.Clamp(parsedRetention,1,3650):30;
var stopAt=durationMinutes>0?DateTime.UtcNow.AddMinutes(durationMinutes):DateTime.MaxValue;
var stopping=false;
Console.CancelKeyPress+=(sender,eventArgs)=>{eventArgs.Cancel=true;stopping=true;};
Directory.CreateDirectory(outputDir);
var auditLock=new object();
using var http=new HttpClient { BaseAddress=new Uri(api),Timeout=TimeSpan.FromSeconds(5) };
var sent=new Dictionary<string,string>();
var retryAfter=new Dictionary<string,DateTime>();
var lastSeen=new Dictionary<string,DateTime>();
var completedUntil=new Dictionary<string,DateTime>();
var printers=FilterPrinters(Spooler.ReadPrinters());
var map=new Dictionary<string,int>();
var remotePolicies=new Dictionary<string,string>();
var remoteProfiles=new Dictionary<string,DeviceProfile>();
var nextSync=DateTime.MinValue;
var nextPoll=DateTime.MinValue;
var nextHeartbeat=DateTime.UtcNow.AddMinutes(1);
var nextCleanup=DateTime.MinValue;
var notifications=new ConcurrentQueue<(string Printer,PrintJob Job)>();
var watchers=new Dictionary<string,Task>();
var ignoredExisting=new HashSet<string>();
var policyEvaluated=new HashSet<string>();
var blockedKeys=new HashSet<string>();
var policySettings=LoadPolicySettings(policyConfigArg);
var enforcementActive=policySettings.Mode.Equals("enforce",StringComparison.OrdinalIgnoreCase)&&enableEnforcement&&policySettings.Policies.Count>0&&policySettings.Policies.Keys.All(x=>x.Contains("_test",StringComparison.OrdinalIgnoreCase));
Console.WriteLine(offline?"PrintGuard Offline Audit (read-only)":$"PrintGuard Native Agent POC -> {api}");
Console.WriteLine($"Monitoring {printers.Count} queue(s):");
foreach(var printer in printers) Console.WriteLine($"  - {printer}");
if(printers.Count==0) Console.Error.WriteLine($"No matching queue found. Filter: {queueFilter??"(none)"}");
Console.WriteLine($"Audit log: {AuditPath()}");
Console.WriteLine($"Log retention: {retentionDays} day(s).");
if(policySettings.Mode.Equals("audit",StringComparison.OrdinalIgnoreCase))Console.WriteLine($"Policy audit enabled: {policySettings.Policies.Count} configured queue(s); jobs will NOT be blocked.");
if(policySettings.Mode.Equals("enforce",StringComparison.OrdinalIgnoreCase))Console.WriteLine(enforcementActive?$"ENFORCEMENT ACTIVE for {policySettings.Policies.Count} _test queue(s).":"ENFORCEMENT REFUSED: requires --enable-enforcement and every configured queue name must contain _test. Audit logging only.");
if(!offline&&enableEnforcement)Console.WriteLine("Web policy enforcement requested; only _test queues can be blocked.");
if(durationMinutes>0) Console.WriteLine($"Automatic stop after {durationMinutes:0.##} minute(s).");
if(!includeExisting){
    foreach(var printer in printers)foreach(var job in Spooler.ReadJobs(printer))ignoredExisting.Add(JobKey(printer,job));
    if(ignoredExisting.Count>0)Console.WriteLine($"Ignoring {ignoredExisting.Count} pre-existing job(s); only new jobs will be captured.");
}
StartWatchers(printers);
Console.WriteLine("Press Ctrl+C to stop.");
AppendAudit("session-start",null,null,null);
while (!stopping && DateTime.UtcNow<stopAt) {
    try {
        if(DateTime.UtcNow>=nextSync){
            printers=FilterPrinters(Spooler.ReadPrinters());
            if(!offline){
                var devices=printers.Select(Spooler.ReadPrinterDevice).ToList();
                var sync=await PostJson(http,"/api/printers/sync",new {printers=devices});
                var response=await sync.Content.ReadFromJsonAsync<SyncResponse>(); map=response?.printer_map??[];remotePolicies=response?.policy_map??[];remoteProfiles=response?.profile_map??[];
            }
            StartWatchers(printers);
            nextSync=DateTime.UtcNow.AddSeconds(30);
        }
        var current=new HashSet<string>();
        var observed=new List<(string Printer,PrintJob Job)>();
        while(notifications.TryDequeue(out var item)) observed.Add(item);
        if(DateTime.UtcNow>=nextPoll){
            foreach(var printer in printers) observed.AddRange(Spooler.ReadJobs(printer).Select(job=>(printer,job)));
            nextPoll=DateTime.UtcNow.AddMilliseconds(500);
        }
        foreach (var item in observed) { var printer=item.Printer; var job=ApplyProfile(printer,item.Job);
            var key=JobKey(printer,job); current.Add(key);
            if(ignoredExisting.Contains(key))continue;
            if(completedUntil.TryGetValue(key,out var until) && DateTime.UtcNow<until)continue;
            var policy=PolicyFor(printer);
            var violates=job.ColorKnown&&((policy=="mono"&&job.Color)||(policy=="color"&&!job.Color));
            if(policyEvaluated.Add(key)&&policy!="any"){
                var result=!job.ColorKnown?"UNKNOWN":violates?"VIOLATION":"COMPLIANT";
                Console.WriteLine($"{DateTime.Now:T} POLICY-{result} #{job.JobId} {job.User} {printer}: policy={policy} driver={job.DriverName}");
                AppendAudit($"policy-{result.ToLowerInvariant()}",printer,job,key);
                var canEnforce=enableEnforcement&&printer.Contains("_test",StringComparison.OrdinalIgnoreCase)&&(enforcementActive||(!offline&&remotePolicies.ContainsKey(printer)));
                if(violates&&canEnforce){
                    var deleted=Spooler.DeleteJob(printer,job.JobId,out var error);
                    if(deleted)blockedKeys.Add(key);
                    Console.WriteLine(deleted?$"{DateTime.Now:T} POLICY-BLOCKED #{job.JobId} {job.User} {printer}: job deleted":$"{DateTime.Now:T} POLICY-BLOCK-FAILED #{job.JobId} {job.User} {printer}: Win32 error {error}; job was not blocked");
                    AppendAudit(deleted?"policy-blocked":"policy-block-failed",printer,job,key);
                }
            }
            lastSeen[key]=DateTime.UtcNow;
            var fingerprint=$"{job.Pages}|{job.Copies}|{job.Color}|{job.Duplex}";
            if (!sent.TryGetValue(key,out var prior) || prior!=fingerprint) {
                var isNew=!sent.ContainsKey(key);
                if(retryAfter.TryGetValue(key,out var retry) && DateTime.UtcNow<retry)continue;
                if(!offline){
                    var printerId=map.TryGetValue(printer,out var mappedId)?mappedId:0;
                    bool? compliant=policy=="any"?null:job.ColorKnown?(policy=="mono"?!job.Color:job.Color):null;
                    var blocked=blockedKeys.Contains(key);
                    var payload=new {native_job_key=key,printer_id=printerId,printer_name=printer,username=job.User,ad_identity=job.User,document=job.Document,pages=Math.Max(1,job.Pages),copies=Math.Max(1,job.Copies),color=job.Color,duplex=job.Duplex,color_known=job.ColorKnown,duplex_known=job.DuplexKnown,client_machine=job.ClientMachine,driver_name=job.DriverName,datatype=job.Datatype,job_size_bytes=job.SizeBytes,paper_size=job.PaperSize,status_value=job.StatusValue,applied_policy=policy,policy_compliant=compliant,reason=blocked?$"Blocked by {policy} policy":compliant==false?$"Policy audit: {policy}":null,source="windows-spooler-native",status=blocked?"blocked":"printing"};
                    var post=await PostJson(http,"/api/jobs/native",payload);
                    if(!post.IsSuccessStatusCode){Console.Error.WriteLine($"{DateTime.Now:T} API {(int)post.StatusCode}: {await post.Content.ReadAsStringAsync()}");retryAfter[key]=DateTime.UtcNow.AddSeconds(2);continue;}
                }
                Console.WriteLine($"{DateTime.Now:T} {(isNew?"CAPTURED":"UPDATED")} #{job.JobId} {job.User} {printer}: {(job.ColorKnown?(job.Color?"Color":"Mono"):"Color?")} {(job.DuplexKnown?(job.Duplex?"Duplex":"Simplex"):"Duplex?")} pages={job.Pages} copies={job.Copies} [fields=0x{job.RawFields:X8} color={job.RawColor} duplex={job.RawDuplex} private={job.DriverExtra}]");
                AppendAudit(isNew?"captured":"updated",printer,job,key);
                retryAfter.Remove(key);
                sent[key]=fingerprint;
            }
        }
        foreach (var done in sent.Keys.Where(x=>lastSeen.TryGetValue(x,out var seen) && DateTime.UtcNow-seen>TimeSpan.FromSeconds(2)).ToArray()) { if(!offline)await PostJson(http,"/api/jobs/native/complete",new {native_job_key=done}); AppendAudit("completed",null,null,done);sent.Remove(done);lastSeen.Remove(done);retryAfter.Remove(done);completedUntil[done]=DateTime.UtcNow.AddMinutes(5); }
        foreach(var expired in completedUntil.Where(x=>x.Value<DateTime.UtcNow).Select(x=>x.Key).ToArray())completedUntil.Remove(expired);
        if(DateTime.UtcNow>=nextCleanup){CleanupOldLogs();nextCleanup=DateTime.UtcNow.AddHours(6);}
        if(DateTime.UtcNow>=nextHeartbeat){Console.WriteLine($"{DateTime.Now:T} HEARTBEAT monitoring={printers.Count} queued-events={notifications.Count} active-jobs={sent.Count}");AppendAudit("heartbeat",null,null,null);nextHeartbeat=DateTime.UtcNow.AddMinutes(1);}
    } catch(Exception ex) { Console.Error.WriteLine($"{DateTime.Now:T} {ex.Message}"); }
    await Task.Delay(50);
}
AppendAudit("session-stop",null,null,null);
Console.WriteLine($"Stopped. Return this folder for analysis: {outputDir}");

List<string> FilterPrinters(IEnumerable<string> names)=>names.Where(x=>string.IsNullOrWhiteSpace(queueFilter)||x.Contains(queueFilter,StringComparison.OrdinalIgnoreCase)).ToList();
string JobKey(string printer,PrintJob job)=>$"{Environment.MachineName}|{printer}|{job.JobId}|{job.Instance}";
string AuditPath()=>Path.Combine(outputDir,$"PrintGuard-Audit-{Environment.MachineName}-{DateTime.Now:yyyyMMdd}.jsonl");
string PolicyFor(string printer){var value=policySettings.Policies.FirstOrDefault(x=>x.Key.Equals(printer,StringComparison.OrdinalIgnoreCase)).Value??remotePolicies.FirstOrDefault(x=>x.Key.Equals(printer,StringComparison.OrdinalIgnoreCase)).Value;value=value?.ToLowerInvariant();return value is "mono" or "color" or "any"?value:"any";}
PrintJob ApplyProfile(string printer,PrintJob job){
    if(!remoteProfiles.TryGetValue(printer,out var profile))return job;
    var color=job.Color;var colorKnown=job.ColorKnown;var duplex=job.Duplex;var duplexKnown=job.DuplexKnown;
    if(profile.color_mode=="mono"){color=false;colorKnown=true;}
    else if(profile.trust_color_standard&&(job.RawFields&0x800)!=0&&job.RawColor is 1 or 2){color=job.RawColor==2;colorKnown=true;}
    if(profile.duplex_mode=="simplex"){duplex=false;duplexKnown=true;}
    else if(profile.trust_duplex_standard&&(job.RawFields&0x1000)!=0&&job.RawDuplex is 1 or 2 or 3){duplex=job.RawDuplex is 2 or 3;duplexKnown=true;}
    return job with {Color=color,ColorKnown=colorKnown,Duplex=duplex,DuplexKnown=duplexKnown};
}

void CleanupOldLogs(){
    try{
        var cutoff=DateTime.UtcNow.AddDays(-retentionDays);var removed=0;
        foreach(var file in Directory.EnumerateFiles(outputDir,"*",SearchOption.AllDirectories)){
            try{if(File.GetLastWriteTimeUtc(file)<cutoff){File.Delete(file);removed++;}}catch(Exception ex){Console.Error.WriteLine($"Log cleanup skipped {file}: {ex.Message}");}
        }
        if(removed>0)Console.WriteLine($"{DateTime.Now:T} LOG-CLEANUP removed={removed} retention-days={retentionDays}");
    }catch(Exception ex){Console.Error.WriteLine($"Log cleanup failed: {ex.Message}");}
}

static PolicySettings LoadPolicySettings(string? path){
    if(string.IsNullOrWhiteSpace(path))return new("disabled",new Dictionary<string,string>());
    try{
        var full=Path.GetFullPath(path);
        var value=JsonSerializer.Deserialize<PolicySettings>(File.ReadAllText(full),new JsonSerializerOptions{PropertyNameCaseInsensitive=true});
        return value??new("disabled",new Dictionary<string,string>());
    }catch(Exception ex){Console.Error.WriteLine($"Policy config load failed; policy disabled: {ex.Message}");return new("disabled",new Dictionary<string,string>());}
}

void AppendAudit(string eventName,string? printer,PrintJob? job,string? key){
    try{
        var policy=printer is null?null:PolicyFor(printer);
        bool? compliant=job is null||policy=="any"?null:job.ColorKnown?(policy=="mono"?!job.Color:job.Color):null;
        // Keep one append-only audit file per day.  The original DEVMODE private
        // bytes are embedded only in the first capture record so diagnostics stay
        // available without creating a .bin/.txt pair for every print job.
        var privateDataBase64=eventName=="captured"&&job?.PrivateData.Length>0?Convert.ToBase64String(job.PrivateData):null;
        var value=new {timestamp=DateTimeOffset.Now,event_name=eventName,host=Environment.MachineName,queue_filter=queueFilter,native_job_key=key,printer,job_id=job?.JobId,instance=job?.Instance,user=job?.User,document=job is null?null:(redactDocuments?"[REDACTED]":job.Document),client=job?.ClientMachine,driver_name=job?.DriverName,datatype=job?.Datatype,job_size_bytes=job?.SizeBytes,paper_size=job?.PaperSize,status_value=job?.StatusValue,pages=job?.Pages,copies=job?.Copies,color=job?.Color,color_known=job?.ColorKnown,duplex=job?.Duplex,duplex_known=job?.DuplexKnown,policy,policy_compliant=compliant,raw_fields=job is null?null:$"0x{job.RawFields:X8}",raw_color=job?.RawColor,raw_duplex=job?.RawDuplex,driver_extra=job?.DriverExtra,private_sha256=job?.PrivateData.Length>0?Convert.ToHexString(SHA256.HashData(job.PrivateData)):null,private_data_base64=privateDataBase64,agent_version=typeof(Program).Assembly.GetName().Version?.ToString()};
        lock(auditLock)File.AppendAllText(AuditPath(),JsonSerializer.Serialize(value)+Environment.NewLine,Encoding.UTF8);
    }catch(Exception ex){Console.Error.WriteLine($"Audit write failed: {ex.Message}");}
}

void StartWatchers(IEnumerable<string> names){
    foreach(var name in names.Where(x=>!watchers.ContainsKey(x))) watchers[name]=Task.Factory.StartNew(()=>Spooler.Watch(name,(printer,jobs)=>{
        foreach(var job in jobs) notifications.Enqueue((printer,job));
    }),CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);
}

static Task<HttpResponseMessage> PostJson(HttpClient client,string path,object value){
    var json=JsonSerializer.Serialize(value);
    var content=new StringContent(json,Encoding.UTF8,"application/json");
    content.Headers.ContentLength=Encoding.UTF8.GetByteCount(json);
    return client.PostAsync(path,content);
}

record SyncResponse(Dictionary<string,int> printer_map,Dictionary<string,string> policy_map,Dictionary<string,DeviceProfile> profile_map);
record DeviceProfile(string color_mode,string duplex_mode,bool trust_color_standard,bool trust_duplex_standard,string profile_status);
record PrinterDevice(string name,string status,string status_detail,uint status_value,uint attributes,string driver_name,string port_name,bool shared,string device_fingerprint,int driver_version,bool? supports_color,bool? supports_duplex);
record PolicySettings(string Mode,Dictionary<string,string> Policies);
record PrintJob(uint JobId,string Instance,string User,string Document,string ClientMachine,string DriverName,string Datatype,uint SizeBytes,short PaperSize,uint StatusValue,int Pages,int Copies,bool Color,bool ColorKnown,bool Duplex,bool DuplexKnown,uint RawFields,short RawColor,short RawDuplex,ushort DriverExtra,byte[] PrivateData);
static class Spooler {
  public static PrinterDevice ReadPrinterDevice(string name){
    var driver="";var port="";var version=0;var status="offline";var detail="無法開啟列印佇列";uint statusValue=0,attributes=0;bool? color=null,duplex=null;
    if(NativeMethods.OpenPrinter(name,out var h,IntPtr.Zero)){
      try{
        NativeMethods.GetPrinter(h,2,IntPtr.Zero,0,out var needed);
        if(needed>0){
          var p=Marshal.AllocHGlobal(needed);
          try{if(NativeMethods.GetPrinter(h,2,p,needed,out _)){
            var info=Marshal.PtrToStructure<NativeMethods.PRINTER_INFO_2>(p);driver=NativeMethods.S(info.DriverName);port=NativeMethods.S(info.PortName);statusValue=info.Status;attributes=info.Attributes;(status,detail)=ClassifyStatus(statusValue,attributes);
            if(info.DevMode!=IntPtr.Zero)version=Marshal.PtrToStructure<NativeMethods.DEVMODE>(info.DevMode).DriverVersion;
            var c=NativeMethods.DeviceCapabilities(name,port,NativeMethods.DC_COLORDEVICE,IntPtr.Zero,info.DevMode);if(c>=0)color=c>0;
            var d=NativeMethods.DeviceCapabilities(name,port,NativeMethods.DC_DUPLEX,IntPtr.Zero,info.DevMode);if(d>=0)duplex=d>0;
          }}finally{Marshal.FreeHGlobal(p);}
        }
      }finally{NativeMethods.ClosePrinter(h);}
    }
    var identity=$"{driver.Trim().ToUpperInvariant()}|{version}|{color?.ToString()??"?"}|{duplex?.ToString()??"?"}";
    var fingerprint=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(identity)));
    return new(name,status,detail,statusValue,attributes,driver,port,name.StartsWith("\\\\"),fingerprint,version,color,duplex);
  }
  private static (string,string) ClassifyStatus(uint value,uint attributes){
    if((attributes&NativeMethods.PRINTER_ATTRIBUTE_WORK_OFFLINE)!=0||(value&(NativeMethods.PRINTER_STATUS_OFFLINE|NativeMethods.PRINTER_STATUS_NOT_AVAILABLE|NativeMethods.PRINTER_STATUS_SERVER_UNKNOWN))!=0)return("offline",$"離線（0x{value:X8}／0x{attributes:X8}）");
    var warnings=NativeMethods.PRINTER_STATUS_ERROR|NativeMethods.PRINTER_STATUS_PAPER_JAM|NativeMethods.PRINTER_STATUS_PAPER_OUT|NativeMethods.PRINTER_STATUS_MANUAL_FEED|NativeMethods.PRINTER_STATUS_PAPER_PROBLEM|NativeMethods.PRINTER_STATUS_OUTPUT_BIN_FULL|NativeMethods.PRINTER_STATUS_TONER_LOW|NativeMethods.PRINTER_STATUS_NO_TONER|NativeMethods.PRINTER_STATUS_USER_INTERVENTION|NativeMethods.PRINTER_STATUS_OUT_OF_MEMORY|NativeMethods.PRINTER_STATUS_DOOR_OPEN;
    return(value&warnings)!=0?("warning",$"需要注意（0x{value:X8}）"):("online",value==0?"就緒":$"運作中（0x{value:X8}）");
  }
  public static bool DeleteJob(string printer,uint jobId,out int error){
    var defaults=new NativeMethods.PRINTER_DEFAULTS{DesiredAccess=NativeMethods.PRINTER_ACCESS_ADMINISTER};
    if(!NativeMethods.OpenPrinterAdmin(printer,out var handle,ref defaults)){error=Marshal.GetLastWin32Error();return false;}
    try{var ok=NativeMethods.SetJob(handle,jobId,0,IntPtr.Zero,NativeMethods.JOB_CONTROL_DELETE);error=ok?0:Marshal.GetLastWin32Error();return ok;}finally{NativeMethods.ClosePrinter(handle);}
  }
  public static void Watch(string printer,Action<string,List<PrintJob>> callback){
    if(!NativeMethods.OpenPrinter(printer,out var handle,IntPtr.Zero))return;
    var change=NativeMethods.FindFirstPrinterChangeNotification(handle,NativeMethods.PRINTER_CHANGE_JOB,0,IntPtr.Zero);
    if(change==IntPtr.Zero || change==new IntPtr(-1)){NativeMethods.ClosePrinter(handle);return;}
    try { while(true){ if(NativeMethods.WaitForSingleObject(change,uint.MaxValue)!=NativeMethods.WAIT_OBJECT_0)break; if(!NativeMethods.FindNextPrinterChangeNotification(change,out _,IntPtr.Zero,IntPtr.Zero))break; callback(printer,ReadJobs(printer)); } }
    finally { NativeMethods.FindClosePrinterChangeNotification(change);NativeMethods.ClosePrinter(handle); }
  }
  public static List<string> ReadPrinters(){
    NativeMethods.EnumPrinters(NativeMethods.PRINTER_ENUM_LOCAL|NativeMethods.PRINTER_ENUM_CONNECTIONS,null,4,IntPtr.Zero,0,out var needed,out _); if(needed==0)return[];
    var p=Marshal.AllocHGlobal(needed); try { if(!NativeMethods.EnumPrinters(6,null,4,p,needed,out _,out var count))return[]; var size=Marshal.SizeOf<NativeMethods.PRINTER_INFO_4>(); return Enumerable.Range(0,count).Select(i=>Marshal.PtrToStructure<NativeMethods.PRINTER_INFO_4>(p+i*size).Name).Where(x=>!string.IsNullOrWhiteSpace(x)).ToList(); } finally { Marshal.FreeHGlobal(p); }
  }
  public static List<PrintJob> ReadJobs(string printer){
    if(!NativeMethods.OpenPrinter(printer,out var h,IntPtr.Zero))return[];
    try{
      NativeMethods.EnumJobs(h,0,999,2,IntPtr.Zero,0,out var needed,out _);if(needed==0)return[];
      var p=Marshal.AllocHGlobal(needed);
      try{
        if(!NativeMethods.EnumJobs(h,0,999,2,p,needed,out _,out var count))return[];
        var size=Marshal.SizeOf<NativeMethods.JOB_INFO_2>();var result=new List<PrintJob>();
        for(var i=0;i<count;i++){
          var j=Marshal.PtrToStructure<NativeMethods.JOB_INFO_2>(p+i*size);
          var driver=NativeMethods.S(j.DriverName);var calibratedSharp=driver.Contains("SHARP MX-2600N PCL6",StringComparison.OrdinalIgnoreCase);
          var copies=1;bool color=false,colorKnown=false,duplex=false,duplexKnown=false;uint rawFields=0;short rawColor=0,rawDuplex=0,paperSize=0;ushort driverExtra=0;byte[] privateData=[];
          if(j.DevMode!=IntPtr.Zero){
            var d=Marshal.PtrToStructure<NativeMethods.DEVMODE>(j.DevMode);copies=Math.Max(1,(int)d.Copies);rawFields=d.Fields;rawColor=d.Color;rawDuplex=d.Duplex;paperSize=d.PaperSize;driverExtra=d.DriverExtra;
            if(driverExtra>0){privateData=new byte[driverExtra];Marshal.Copy(IntPtr.Add(j.DevMode,d.Size),privateData,0,driverExtra);}
            color=d.Color==2;colorKnown=calibratedSharp&&(d.Fields&0x800)!=0;
            var standardDuplexKnown=(d.Fields&0x1000)!=0;var standardDuplex=d.Duplex is 2 or 3;
            var privateDuplexKnown=calibratedSharp&&privateData.Length>0x180&&privateData[0x180] is 1 or 2 or 3;var privateDuplex=privateDuplexKnown&&privateData[0x180] is 2 or 3;
            duplexKnown=calibratedSharp&&(standardDuplexKnown||privateDuplexKnown);duplex=standardDuplex||privateDuplex;
          }
          var s=j.Submitted;var instance=$"{s.Year:D4}{s.Month:D2}{s.Day:D2}{s.Hour:D2}{s.Minute:D2}{s.Second:D2}{s.Milliseconds:D3}";
          result.Add(new(j.JobId,instance,NativeMethods.S(j.UserName),NativeMethods.S(j.Document),NativeMethods.S(j.MachineName),driver,NativeMethods.S(j.Datatype),j.Size,paperSize,j.StatusValue,(int)Math.Max(j.TotalPages,j.PagesPrinted),copies,color,colorKnown,duplex,duplexKnown,rawFields,rawColor,rawDuplex,driverExtra,privateData));
        }
        return result;
      }finally{Marshal.FreeHGlobal(p);}
    }finally{NativeMethods.ClosePrinter(h);}
  }
}

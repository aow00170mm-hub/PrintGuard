using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

internal static class Program
{
    private const string ServiceName="PrintGuard";
    private const uint ServiceWin32OwnProcess=0x10,ServiceStartPending=2,ServiceStopPending=3,ServiceRunning=4,ServiceStopped=1;
    private const uint AcceptStop=1,AcceptShutdown=4,ControlStop=1,ControlInterrogate=4,ControlShutdown=5;
    private static readonly ManualResetEventSlim StopEvent=new(false);
    private static readonly object LogLock=new();
    private static readonly List<Process> Children=[];
    private static readonly ServiceMainDelegate ServiceMainCallback=ServiceMain;
    private static readonly HandlerDelegate HandlerCallback=Handler;
    private static IntPtr statusHandle;
    private static string root=AppContext.BaseDirectory;

    public static int Main(string[] args)
    {
        root=Path.GetFullPath(args.FirstOrDefault(x=>x.StartsWith("--root="))?.Split('=',2)[1]??AppContext.BaseDirectory);
        if(args.Contains("--check"))return Check();
        if(args.Contains("--console"))return RunConsole(args);
        var table=new[]{new ServiceTableEntry{ServiceName=ServiceName,ServiceMain=ServiceMainCallback},new ServiceTableEntry()};
        if(!StartServiceCtrlDispatcher(table)){Console.Error.WriteLine($"StartServiceCtrlDispatcher failed: {Marshal.GetLastWin32Error()}");return 1;}
        return 0;
    }

    private static int Check()
    {
        var missing=RequiredFiles().Where(x=>!File.Exists(x)).ToList();
        if(missing.Count>0){foreach(var file in missing)Console.Error.WriteLine($"Missing: {file}");return 2;}
        Console.WriteLine($"PrintGuard Service Host check OK: {root}");return 0;
    }

    private static int RunConsole(string[] args)
    {
        if(Check()!=0)return 2;
        Console.CancelKeyPress+=(_,e)=>{e.Cancel=true;StopEvent.Set();};
        if(int.TryParse(args.FirstOrDefault(x=>x.StartsWith("--duration-seconds="))?.Split('=',2)[1],out var seconds)&&seconds>0)
            _=Task.Delay(TimeSpan.FromSeconds(seconds)).ContinueWith(_=>StopEvent.Set());
        Log("Console supervision started.");RunSupervisors();StopEvent.Wait();StopChildren();Log("Console supervision stopped.");return 0;
    }

    private static void ServiceMain(uint argc,IntPtr argv)
    {
        statusHandle=RegisterServiceCtrlHandler(ServiceName,HandlerCallback);
        if(statusHandle==IntPtr.Zero)return;
        Report(ServiceStartPending,0,15000);
        try
        {
            if(Check()!=0){Report(ServiceStopped,2,0);return;}
            RunSupervisors();Report(ServiceRunning,0,0);Log("Windows service started.");
            StopEvent.Wait();Report(ServiceStopPending,0,15000);StopChildren();Log("Windows service stopped.");Report(ServiceStopped,0,0);
        }
        catch(Exception ex){Log($"Fatal service error: {ex}");StopChildren();Report(ServiceStopped,1,0);}
    }

    private static void RunSupervisors()
    {
        Directory.CreateDirectory(Path.Combine(root,"logs","service"));
        _=Task.Run(()=>Supervise("server",Path.Combine(root,"bin","PrintGuard.Server.exe"),ServerArgs()));
        _=Task.Run(()=>Supervise("agent",Path.Combine(root,"bin","PrintGuard.NativeAgent.exe"),AgentArgs()));
    }

    private static async Task Supervise(string name,string executable,string arguments)
    {
        while(!StopEvent.IsSet)
        {
            Process? process=null;
            try
            {
                var info=new ProcessStartInfo(executable,arguments){WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
                process=new Process{StartInfo=info,EnableRaisingEvents=true};
                process.OutputDataReceived+=(_,e)=>{if(e.Data is not null)Log($"{name}: {e.Data}");};
                process.ErrorDataReceived+=(_,e)=>{if(e.Data is not null)Log($"{name} ERROR: {e.Data}");};
                process.Start();lock(Children)Children.Add(process);process.BeginOutputReadLine();process.BeginErrorReadLine();Log($"Started {name} PID={process.Id}");
                await process.WaitForExitAsync();Log($"{name} exited code={process.ExitCode}");
            }
            catch(Exception ex){Log($"{name} launch failed: {ex.Message}");}
            finally{if(process is not null){lock(Children)Children.Remove(process);process.Dispose();}}
            if(!StopEvent.IsSet)await Task.Delay(TimeSpan.FromSeconds(5));
        }
    }

    private static void StopChildren()
    {
        StopEvent.Set();List<Process> snapshot;lock(Children)snapshot=Children.ToList();
        foreach(var child in snapshot)try{if(!child.HasExited)child.Kill(true);}catch(Exception ex){Log($"Stop PID failed: {ex.Message}");}
        foreach(var child in snapshot)try{child.WaitForExit(10000);}catch{}
    }

    private static string ServerArgs()=>$"--host=0.0.0.0 --port=8080 \"--data-dir={Path.Combine(root,"data")}\" \"--log-dir={Path.Combine(root,"logs")}\" \"--import-dir={Path.Combine(root,"imports")}\" --log-retention-days=30";
    private static string AgentArgs()=>$"--api=http://127.0.0.1:8080 --enable-enforcement \"--output={Path.Combine(root,"logs","agent")}\" --log-retention-days=30";
    private static IEnumerable<string> RequiredFiles(){yield return Path.Combine(root,"bin","PrintGuard.Server.exe");yield return Path.Combine(root,"bin","PrintGuard.NativeAgent.exe");}

    private static uint Handler(uint control)
    {
        if(control is ControlStop or ControlShutdown){Report(ServiceStopPending,0,15000);StopEvent.Set();}
        else if(control==ControlInterrogate)Report(ServiceRunning,0,0);
        return 0;
    }

    private static void Report(uint state,uint exitCode,uint waitHint)
    {
        var status=new ServiceStatus{ServiceType=ServiceWin32OwnProcess,CurrentState=state,ControlsAccepted=state==ServiceRunning?AcceptStop|AcceptShutdown:0,Win32ExitCode=exitCode,WaitHint=waitHint};
        if(statusHandle!=IntPtr.Zero)SetServiceStatus(statusHandle,ref status);
    }

    private static void Log(string message)
    {
        try{lock(LogLock){var dir=Path.Combine(root,"logs","service");Directory.CreateDirectory(dir);File.AppendAllText(Path.Combine(dir,$"service-{DateTime.Now:yyyyMMdd}.log"),$"[{DateTimeOffset.Now:O}] {message}{Environment.NewLine}",Encoding.UTF8);}}catch{}
    }

    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]private struct ServiceTableEntry{[MarshalAs(UnmanagedType.LPWStr)]public string? ServiceName;public ServiceMainDelegate? ServiceMain;}
    [StructLayout(LayoutKind.Sequential)]private struct ServiceStatus{public uint ServiceType,CurrentState,ControlsAccepted,Win32ExitCode,ServiceSpecificExitCode,CheckPoint,WaitHint;}
    [UnmanagedFunctionPointer(CallingConvention.Winapi)]private delegate void ServiceMainDelegate(uint argc,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Winapi)]private delegate uint HandlerDelegate(uint control);
    [DllImport("advapi32.dll",EntryPoint="StartServiceCtrlDispatcherW",CharSet=CharSet.Unicode,SetLastError=true)]private static extern bool StartServiceCtrlDispatcher([In]ServiceTableEntry[] table);
    [DllImport("advapi32.dll",EntryPoint="RegisterServiceCtrlHandlerW",CharSet=CharSet.Unicode,SetLastError=true)]private static extern IntPtr RegisterServiceCtrlHandler(string serviceName,HandlerDelegate handler);
    [DllImport("advapi32.dll",SetLastError=true)]private static extern bool SetServiceStatus(IntPtr handle,ref ServiceStatus status);
}

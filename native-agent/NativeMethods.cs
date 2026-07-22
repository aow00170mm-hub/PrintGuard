using System.Runtime.InteropServices;

internal static class NativeMethods
{
    internal const int PRINTER_ENUM_LOCAL=2, PRINTER_ENUM_CONNECTIONS=4;
    [DllImport("winspool.drv", CharSet=CharSet.Unicode, SetLastError=true)] internal static extern bool EnumPrinters(int flags,string? name,int level,IntPtr buffer,int size,out int needed,out int returned);
    [DllImport("winspool.drv", CharSet=CharSet.Unicode, SetLastError=true)] internal static extern bool OpenPrinter(string name,out IntPtr printer,IntPtr defaults);
    [DllImport("winspool.drv", EntryPoint="GetPrinterW", CharSet=CharSet.Unicode, SetLastError=true)] internal static extern bool GetPrinter(IntPtr printer,int level,IntPtr buffer,int size,out int needed);
    [DllImport("winspool.drv", EntryPoint="DeviceCapabilitiesW", CharSet=CharSet.Unicode)] internal static extern int DeviceCapabilities(string device,string port,short capability,IntPtr output,IntPtr devMode);
    [DllImport("winspool.drv", EntryPoint="OpenPrinterW", CharSet=CharSet.Unicode, SetLastError=true)] internal static extern bool OpenPrinterAdmin(string name,out IntPtr printer,ref PRINTER_DEFAULTS defaults);
    [DllImport("winspool.drv", SetLastError=true)] internal static extern bool ClosePrinter(IntPtr printer);
    [DllImport("winspool.drv", EntryPoint="SetJobW", CharSet=CharSet.Unicode, SetLastError=true)] internal static extern bool SetJob(IntPtr printer,uint jobId,uint level,IntPtr job,uint command);
    [DllImport("winspool.drv", CharSet=CharSet.Unicode, SetLastError=true)] internal static extern bool EnumJobs(IntPtr printer,int first,int count,int level,IntPtr buffer,int size,out int needed,out int returned);
    [DllImport("winspool.drv", SetLastError=true)] internal static extern IntPtr FindFirstPrinterChangeNotification(IntPtr printer,uint filter,uint options,IntPtr notifyOptions);
    [DllImport("winspool.drv", SetLastError=true)] internal static extern bool FindNextPrinterChangeNotification(IntPtr change,out uint flags,IntPtr options,IntPtr info);
    [DllImport("winspool.drv", SetLastError=true)] internal static extern bool FindClosePrinterChangeNotification(IntPtr change);
    [DllImport("kernel32.dll")] internal static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
    internal const uint PRINTER_CHANGE_JOB=0x0000FF00, WAIT_OBJECT_0=0, PRINTER_ACCESS_ADMINISTER=0x00000004, JOB_CONTROL_DELETE=5;
    internal const uint PRINTER_ATTRIBUTE_WORK_OFFLINE=0x00000400;
    internal const uint PRINTER_STATUS_ERROR=0x00000002,PRINTER_STATUS_PAPER_JAM=0x00000008,PRINTER_STATUS_PAPER_OUT=0x00000010,
      PRINTER_STATUS_MANUAL_FEED=0x00000020,PRINTER_STATUS_PAPER_PROBLEM=0x00000040,PRINTER_STATUS_OFFLINE=0x00000080,
      PRINTER_STATUS_OUTPUT_BIN_FULL=0x00000800,PRINTER_STATUS_NOT_AVAILABLE=0x00001000,PRINTER_STATUS_TONER_LOW=0x00020000,
      PRINTER_STATUS_NO_TONER=0x00040000,PRINTER_STATUS_USER_INTERVENTION=0x00100000,PRINTER_STATUS_OUT_OF_MEMORY=0x00200000,
      PRINTER_STATUS_DOOR_OPEN=0x00400000,PRINTER_STATUS_SERVER_UNKNOWN=0x00800000;
    internal const short DC_DUPLEX=7, DC_COLORDEVICE=32;

    [StructLayout(LayoutKind.Sequential)] internal struct PRINTER_DEFAULTS { public IntPtr Datatype,DevMode;public uint DesiredAccess; }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] internal struct PRINTER_INFO_4 { [MarshalAs(UnmanagedType.LPWStr)] public string Name; [MarshalAs(UnmanagedType.LPWStr)] public string ServerName; public uint Attributes; }
    [StructLayout(LayoutKind.Sequential)] internal struct PRINTER_INFO_2 {
        public IntPtr ServerName,PrinterName,ShareName,PortName,DriverName,Comment,Location,DevMode,SepFile,PrintProcessor,Datatype,Parameters,SecurityDescriptor;
        public uint Attributes,Priority,DefaultPriority,StartTime,UntilTime,Status,Jobs,AveragePPM;
    }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] internal struct JOB_INFO_2 {
        public uint JobId; public IntPtr PrinterName,MachineName,UserName,Document,NotifyName,Datatype,PrintProcessor,Parameters,DriverName; public IntPtr DevMode;
        public IntPtr Status; public IntPtr SecurityDescriptor; public uint StatusValue,Priority,Position,StartTime,UntilTime,TotalPages,Size;
        public SYSTEMTIME Submitted; public uint Time,PagesPrinted;
    }
    [StructLayout(LayoutKind.Sequential)] internal struct SYSTEMTIME { public ushort Year,Month,DayOfWeek,Day,Hour,Minute,Second,Milliseconds; }
    // Fixed section of DEVMODEW through dmPanningHeight. dmSize tells us which fields are valid.
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] internal struct DEVMODE {
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string DeviceName;
        public ushort SpecVersion,DriverVersion,Size,DriverExtra; public uint Fields;
        public short Orientation,PaperSize,PaperLength,PaperWidth,Scale,Copies,DefaultSource,PrintQuality,Color,Duplex,YResolution,TTOption,Collate;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string FormName;
        public ushort LogPixels; public uint BitsPerPel,PelsWidth,PelsHeight,DisplayFlags,DisplayFrequency,ICMMethod,ICMIntent,MediaType,DitherType,Reserved1,Reserved2,PanningWidth,PanningHeight;
    }
    internal static string S(IntPtr p)=>p==IntPtr.Zero?"":Marshal.PtrToStringUni(p)??"";
}

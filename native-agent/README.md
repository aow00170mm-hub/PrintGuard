# PrintGuard Native Agent POC

This Windows-only agent watches live spooler jobs and reads `JOB_INFO_2` / `DEVMODE` before the job disappears. It captures the requested color mode, duplex mode and copies when the driver exposes those fields.

## Build and run

Restart `server.py` first, then from an elevated PowerShell:

```powershell
cd C:\code\PrintGuard\native-agent
dotnet build
dotnet run
```

Keep the console open, print a sufficiently large test document, and watch for a line containing `Color` or `Mono`. Use `-- --api=http://server:8080` when the API is on another host.

This is a capture POC, not enforcement yet. It polls live jobs every 25 ms and prints all discovered queues at startup. Very fast virtual jobs can still leave the queue between polls; the production service will use spooler change notifications.

# 声笺 · Windows desktop app

`LocalAudio.exe` is a Windows GUI launcher and tray controller, built with the Windows .NET Framework compiler. The icon is embedded in the executable and also supplied as a multi-resolution ICO. The application window uses installed Microsoft Edge or Chrome in app mode with a separate profile; it does not use the user's normal browser profile.

The portable folder contains Python, inference dependencies, local weights, samples, FFmpeg, frontend assets and licenses. Double-clicking the desktop shortcut starts its own hidden service, waits for readiness and opens the workspace. There is no setup/build step on normal launches. The backend remains ready after the application window closes. Double-clicking again signals the existing tray controller rather than starting another backend. Use the tray **退出软件（停止后台服务）** menu to shut down gracefully. No Windows login/startup entry is installed.

The first launch after a reboot starts the service; actual transcription or instrumental generation may still load model weights when requested. Keeping the backend ready does not imply keeping all large models in memory. This is the existing local browser engine UI wrapped in a desktop launch flow, not a replacement native engraving engine.

`server/desktop.py` gives the controller an installation identity and a per-launch random token for graceful shutdown. It never takes over or kills a different service using port 8765. Logs and the isolated browser profile live in `.desktop` inside the portable folder. User project files still need to be saved explicitly. Closing the window follows the existing page-close cleanup behavior; save before closing.

Build from the prepared source checkout:

```powershell
.venv\Scripts\python.exe -B scripts/package_portable.py --output release/LocalAudio-0.7.2-Desktop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/install_desktop.ps1 -PackageDirectory "$PWD\release\LocalAudio-0.7.2-Desktop"
```

The destination must not exist when packaging. Keep the entire resulting folder; copying only the EXE or moving the folder without updating the shortcut will break startup. `Start.cmd` remains a diagnostic console entry and must not run concurrently with the desktop service. The launcher supports `--background` for maintenance testing and `--quit` for signaling graceful tray exit; neither changes Windows startup settings.

The approved hand-drawn brand icon is desktop/branding/Shengjian-line.ico. The visible app name and desktop shortcut are 声笺 (Shengjian); LocalAudio.exe remains the internal launcher filename for installation compatibility.

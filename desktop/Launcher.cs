using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("声笺 · Shengjian")]
[assembly: System.Reflection.AssemblyDescription("Shengjian music workspace")]
[assembly: System.Reflection.AssemblyVersion("0.7.2.0")]
[assembly: System.Reflection.AssemblyFileVersion("0.7.2.0")]

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        string root = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory).TrimEnd(Path.DirectorySeparatorChar);
        string identity;
        using (var sha = SHA256.Create())
            identity = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(root.ToLowerInvariant()))).Replace("-", "").ToLowerInvariant();
        string name = @"Local\LocalAudio-" + identity.Substring(0, 20);
        bool quit = Array.IndexOf(args, "--quit") >= 0;
        try
        {
            if (quit)
            {
                using (var signal = EventWaitHandle.OpenExisting(name + "-quit")) signal.Set();
                return;
            }
            using (var mutex = new Mutex(false, name))
            {
                bool ownsMutex;
                try { ownsMutex = mutex.WaitOne(1000); }
                catch (AbandonedMutexException) { ownsMutex = true; }
                if (!ownsMutex)
                {
                    if (Array.IndexOf(args, "--background") < 0)
                        using (var signal = EventWaitHandle.OpenExisting(name + "-open")) signal.Set();
                    return;
                }
                try
                {
                    using (var context = new StudioContext(root, identity, name, Array.IndexOf(args, "--background") >= 0))
                        Application.Run(context);
                }
                finally { mutex.ReleaseMutex(); }
            }
        }
        catch (WaitHandleCannotBeOpenedException) { if (!quit) MessageBox.Show("软件正在启动，请稍后再试。", "声笺"); }
        catch (Exception error) { MessageBox.Show(error.Message, "声笺 · 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
}

internal sealed class StudioContext : ApplicationContext
{
    private readonly string root, identity;
    private readonly NotifyIcon tray;
    private readonly EventWaitHandle openSignal, quitSignal;
    private readonly System.Windows.Forms.Timer timer;
    private readonly Icon icon;
    private readonly Form splash;
    private Process backend;
    private string token;
    private bool pendingOpen, ready, closing;
    private DateTime started;
    private int ticks;
    private const string Url = "http://127.0.0.1:8765";

    public StudioContext(string root, string identity, string name, bool background)
    {
        this.root = root; this.identity = identity; pendingOpen = !background;
        string python = Path.Combine(root, @"runtime\pythonw.exe");
        if (!File.Exists(python) || !File.Exists(Path.Combine(root, @"dist\index.html")))
            throw new FileNotFoundException("软件文件不完整，请保留整个安装文件夹。\n" + root);
        icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        var menu = new ContextMenuStrip();
        menu.Items.Add("打开声笺", null, delegate { Open(); });
        menu.Items.Add("打开运行日志", null, delegate {
            string path = Path.Combine(root, @".desktop\service.log");
            if (File.Exists(path)) Process.Start(new ProcessStartInfo("notepad.exe", Quote(path)) { UseShellExecute = true });
        });
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("退出软件（停止后台服务）", null, delegate { ExitThread(); });
        tray = new NotifyIcon { Icon = icon, Text = "声笺 · 正在启动", ContextMenuStrip = menu, Visible = true };
        tray.DoubleClick += delegate { Open(); };
        openSignal = new EventWaitHandle(false, EventResetMode.AutoReset, name + "-open");
        quitSignal = new EventWaitHandle(false, EventResetMode.AutoReset, name + "-quit");
        splash = new Form { Text = "声笺", Icon = icon, Size = new Size(380, 150), StartPosition = FormStartPosition.CenterScreen,
            FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, MinimizeBox = false, BackColor = Color.FromArgb(237, 240, 243) };
        splash.Controls.Add(new Label { Text = "正在打开声笺…\n首次启动后，服务会在后台保持就绪。", Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Microsoft YaHei UI", 11), ForeColor = Color.FromArgb(37, 52, 68) });
        splash.FormClosing += delegate(object sender, FormClosingEventArgs e) { if (!closing) { e.Cancel = true; splash.Hide(); } };
        if (!background) splash.Show();
        timer = new System.Windows.Forms.Timer { Interval = 500 };
        timer.Tick += Tick;
        StartBackend();
        timer.Start();
    }

    private static string Quote(string value) { return "\"" + value.Replace("\"", "") + "\""; }

    private Dictionary<string, object> Request(string path, string stopToken = null)
    {
        var request = (HttpWebRequest)WebRequest.Create(Url + path);
        request.Proxy = null; request.Timeout = 700; request.ReadWriteTimeout = 700;
        if (stopToken != null) { request.Method = "POST"; request.Headers["X-Desktop-Token"] = stopToken; request.ContentLength = 0; }
        using (var response = request.GetResponse())
        using (var reader = new StreamReader(response.GetResponseStream()))
        {
            string json = reader.ReadToEnd();
            return json.Length == 0 ? new Dictionary<string, object>() : new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(json);
        }
    }

    private void StartBackend()
    {
        if (backend != null && !backend.HasExited) return;
        // A service not owned by this launcher must never be killed or reused silently.
        try { Request("/api/health"); throw new InvalidOperationException("端口 8765 已有服务运行。请先关闭原 Start.cmd 服务，再打开桌面软件。"); }
        catch (WebException error) { if (error.Response != null) throw new InvalidOperationException("端口 8765 已被其他程序占用。"); }
        token = Guid.NewGuid().ToString("N") + Guid.NewGuid().ToString("N");
        var start = new ProcessStartInfo(Path.Combine(root, @"runtime\pythonw.exe"), "-B -m server.desktop") {
            WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden };
        start.EnvironmentVariables["LOCAL_AUDIO_DESKTOP_TOKEN"] = token;
        start.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
        backend = Process.Start(start); started = DateTime.UtcNow; ready = false;
    }

    private void Tick(object sender, EventArgs args)
    {
        if (closing) return;
        if (quitSignal.WaitOne(0)) { ExitThread(); return; }
        if (openSignal.WaitOne(0)) Open();
        if (ready)
        {
            if (backend.HasExited) { ready = false; tray.Text = "声笺 · 服务已停止，双击重启"; }
            return;
        }
        if (backend.HasExited)
        {
            if (pendingOpen) Fail("本机服务未能启动，请通过托盘菜单查看运行日志。\n" + Path.Combine(root, @".desktop\service.log"));
            return;
        }
        try
        {
            var state = Request("/api/desktop/status");
            if (!state.ContainsKey("installation") || (string)state["installation"] != identity)
                throw new InvalidOperationException("端口上运行的不是此软件的服务。请退出其他声笺实例。");
            if (++ticks % 2 != 0) return;
            var health = Request("/api/health");
            if (!(bool)health["ready"]) { Fail("本地资源不完整，请查看日志或重新安装软件。"); return; }
            ready = true; tray.Text = "声笺 · 后台已就绪"; splash.Hide();
            if (pendingOpen) { pendingOpen = false; OpenWindow(); }
        }
        catch (WebException) { if ((DateTime.UtcNow - started).TotalSeconds > 120) Fail("服务启动超时，请通过托盘查看运行日志。"); }
        catch (Exception error) { Fail(error.Message); }
    }

    private void Open()
    {
        try { if (ready) OpenWindow(); else { pendingOpen = true; StartBackend(); splash.Show(); } }
        catch (Exception error) { Fail(error.Message); }
    }

    private void OpenWindow()
    {
        string browser = null;
        foreach (string path in new[] {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Google\Chrome\Application\chrome.exe") })
            if (File.Exists(path)) { browser = path; break; }
        if (browser == null) throw new FileNotFoundException("未找到 Microsoft Edge 或 Chrome。请安装其中一个后打开软件。");
        string profile = Path.Combine(root, @".desktop\browser");
        Process.Start(new ProcessStartInfo(browser, "--app=" + Url + " --user-data-dir=" + Quote(profile) + " --no-first-run --no-default-browser-check --disable-background-mode")
            { UseShellExecute = false, WorkingDirectory = root });
    }

    private void Fail(string message)
    {
        pendingOpen = false; splash.Hide(); timer.Stop();
        MessageBox.Show(message, "声笺", MessageBoxButtons.OK, MessageBoxIcon.Error);
        ExitThread();
    }

    protected override void ExitThreadCore()
    {
        if (closing) return; closing = true; timer.Stop(); splash.Hide();
        if (backend != null && !backend.HasExited)
        {
            try { Request("/api/desktop/stop", token); } catch (WebException) { }
            if (!backend.WaitForExit(20000)) backend.Kill();
        }
        tray.Visible = false; tray.Dispose(); splash.Dispose(); timer.Dispose(); icon.Dispose();
        openSignal.Dispose(); quitSignal.Dispose(); if (backend != null) backend.Dispose();
        base.ExitThreadCore();
    }
}

"""
A small native (Tkinter) front-end for the renmori CLI — launched with
`renmori gui`. It drives the same `python -m renmori` commands as the terminal,
so it inherits everything: the plugin auto-download, verification, and the
machine-readable JSON result. Three tabs: Protect, Verify, and a renmori.toml
editor.

Tkinter ships with CPython, so this adds no dependency. The CLI stays fully
usable without ever importing this module (it is imported lazily by `cmd_gui`).
"""

import glob
import json
import os
import queue
import subprocess
import sys
import threading

from . import __version__

BRAND = "RenMori"

# Target platforms the plugin can produce (see protect_poly / docs/interface).
PLATFORMS = ("mac-universal", "linux-x64", "win-x64")
STRENGTHS = ("", "full", "auto", "baseline")  # "" = leave unset (full)

# --- i18n -------------------------------------------------------------------

_L = {
    "en": {
        "title": "%s %s" % (BRAND, __version__),
        "tab_protect": "Protect", "tab_verify": "Verify", "tab_config": "Config",
        "input": "Game build", "browse_dir": "Folder…", "browse_zip": ".zip…",
        "output": "Output (-o)", "output_hint": "leave empty to protect in place",
        "browse": "Browse…", "open": "Open…", "save_as": "Save as…",
        "options": "Options", "strength": "Strength",
        "platforms": "Platforms", "auto": "auto-detect",
        "lockdown": "Lockdown (disable console/developer/export)",
        "launcher": "Native launcher (on by default; uncheck for --no-launcher)",
        "chunk": "Chunk size", "exclude": "Exclude globs (one per line)",
        "keep_on_disk": "Keep on disk (one per line)",
        "no_backup": "No backup (in-place)", "keep_plaintext": "Keep plaintext (debug)",
        "plugin": "Plugin path", "config_file": "Config (-c)",
        "protect_btn": "Protect", "verify_btn": "Verify",
        "protected": "Protected build", "generate": "Generate preview",
        "keys": "Keys (baseline only)", "master_env": "master_env", "script_env": "script_env",
        "running": "Running…", "done_ok": "✓ Done", "done_err": "✗ Failed",
        "ready": "Ready", "need_input": "Pick a game build first.",
        "need_protected": "Pick a protected build first.",
        "confirm_title": "Protect this build?",
        "confirm_body": "Run protect on:\n%s\n\nOutput: %s\n\nProceed?",
        "no_display": "Cannot open a window (no display).",
        "preview": "renmori.toml preview", "saved": "Saved: %s",
        "open_fail": "Could not parse as TOML (%s). Loaded raw text for editing.",
    },
    "zh": {
        "title": "%s %s" % (BRAND, __version__),
        "tab_protect": "保护", "tab_verify": "校验", "tab_config": "配置",
        "input": "游戏构建", "browse_dir": "选目录…", "browse_zip": "选 .zip…",
        "output": "输出目录 (-o)", "output_hint": "留空则原地保护",
        "browse": "浏览…", "open": "打开…", "save_as": "另存为…",
        "options": "选项", "strength": "强度",
        "platforms": "目标平台", "auto": "自动检测",
        "lockdown": "锁定（关闭 console/developer/导出）",
        "launcher": "原生启动器（默认开启；取消勾选即 --no-launcher）",
        "chunk": "分块大小", "exclude": "排除 glob（每行一个）",
        "keep_on_disk": "保留在磁盘（每行一个）",
        "no_backup": "不备份（原地）", "keep_plaintext": "保留明文（调试）",
        "plugin": "插件路径", "config_file": "配置文件 (-c)",
        "protect_btn": "保护", "verify_btn": "校验",
        "protected": "受保护的构建", "generate": "生成预览",
        "keys": "密钥（仅基线）", "master_env": "master_env", "script_env": "script_env",
        "running": "运行中…", "done_ok": "✓ 完成", "done_err": "✗ 失败",
        "ready": "就绪", "need_input": "请先选择游戏构建。",
        "need_protected": "请先选择受保护的构建。",
        "confirm_title": "确认保护该构建？",
        "confirm_body": "将对以下目标运行保护：\n%s\n\n输出：%s\n\n继续？",
        "no_display": "无法打开窗口（没有可用显示）。",
        "preview": "renmori.toml 预览", "saved": "已保存：%s",
        "open_fail": "无法按 TOML 解析（%s），已载入原始文本供手动编辑。",
    },
}


# --- pure helpers (unit-tested without Tk) ----------------------------------

def build_protect_args(o):
    """Turn a protect-options dict into CLI args (no 'protect'/game_dir/-y)."""
    args = []
    if o.get("output"):
        args += ["-o", o["output"]]
    if o.get("config"):
        args += ["-c", o["config"]]
    if o.get("chunk_size"):
        args += ["--chunk-size", str(o["chunk_size"])]
    for g in o.get("exclude") or []:
        g = g.strip()
        if g:
            args += ["--exclude", g]
    if o.get("strength"):
        args += ["--strength", o["strength"]]
    if o.get("plugin"):
        args += ["--plugin", o["plugin"]]
    if o.get("platforms"):
        args += ["--platforms", o["platforms"]]
    if o.get("launcher") is False:
        args += ["--no-launcher"]
    if o.get("no_lockdown"):
        args += ["--no-lockdown"]
    if o.get("keep_plaintext"):
        args += ["--keep-plaintext"]
    if o.get("no_backup"):
        args += ["--no-backup"]
    return args


def _toml_list(values):
    return "[%s]" % ", ".join('"%s"' % v for v in values)


def build_toml(cfg):
    """Render a renmori.toml from a config dict (matches examples/renmori.toml)."""
    out = ["[protect]"]
    if cfg.get("strength"):
        out.append('strength = "%s"' % cfg["strength"])
    out.append("lockdown = %s" % ("true" if cfg.get("lockdown", True) else "false"))
    if cfg.get("chunk_size"):
        out.append("chunk_size = %d" % int(cfg["chunk_size"]))
    if cfg.get("keep_plaintext"):
        out.append("keep_plaintext = true")
    excl = [e.strip() for e in (cfg.get("exclude") or []) if e.strip()]
    if excl:
        out.append("exclude = %s" % _toml_list(excl))
    keep = [e.strip() for e in (cfg.get("keep_on_disk") or []) if e.strip()]
    if keep:
        out.append("keep_on_disk = %s" % _toml_list(keep))
    plats = [p for p in (cfg.get("platforms") or []) if p]
    if plats:
        out.append("platforms = %s" % _toml_list(plats))
    if cfg.get("launcher", True) is False:
        out.append("launcher = false")
    keys = []
    if cfg.get("master_env"):
        keys.append('master_env = "%s"' % cfg["master_env"])
    if cfg.get("script_env"):
        keys.append('script_env = "%s"' % cfg["script_env"])
    if keys:
        out += ["", "[keys]"] + keys
    return "\n".join(out) + "\n"


def _cli_cmd(sub_args):
    """The argv to run a renmori subcommand as a child process."""
    return [sys.executable, "-m", "renmori"] + sub_args


# --- the Tk application -----------------------------------------------------

def _ensure_tcl_tk():
    """Point Tk at its bundled Tcl/Tk data when the interpreter doesn't.

    uv / python-build-standalone ship Tcl/Tk 8.6 under the (base) prefix but
    leave TCL_LIBRARY/TK_LIBRARY unset, so Tk() dies with "Can't find a usable
    init.tcl". Locate the data and set them. No-op when they're already set or
    when the data isn't found (a normal framework/Homebrew Python finds its own).
    """
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return
    seen = []
    for base in (sys.prefix, sys.base_prefix,
                 os.path.dirname(os.path.dirname(os.path.realpath(sys.executable)))):
        if base in seen:
            continue
        seen.append(base)
        libdir = os.path.join(base, "lib")
        tcl = [d for d in sorted(glob.glob(os.path.join(libdir, "tcl8.*")))
               if os.path.isfile(os.path.join(d, "init.tcl"))]
        tk = [d for d in sorted(glob.glob(os.path.join(libdir, "tk8.*")))
              if os.path.isfile(os.path.join(d, "tk.tcl"))]
        if tcl and tk:
            os.environ.setdefault("TCL_LIBRARY", tcl[-1])
            os.environ.setdefault("TK_LIBRARY", tk[-1])
            return


def run(lang="en"):
    """Open the GUI. Returns an exit code (0 ok, 2 if no display)."""
    _ensure_tcl_tk()
    try:
        import tkinter as tk  # noqa: F401
        from tkinter import ttk  # noqa: F401
    except Exception as e:  # pragma: no cover - tkinter missing
        sys.stderr.write("GUI needs Tkinter, which is not available: %s\n" % e)
        return 2
    try:
        app = _App(lang)
    except tk.TclError as e:
        sys.stderr.write("%s (%s)\n" % (_L.get(lang, _L["en"])["no_display"], e))
        return 2
    app.mainloop()
    return 0


class _App:
    def __init__(self, lang):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.lang = lang if lang in _L else "en"
        self.t = _L[self.lang]
        self.proc = None
        self.q = queue.Queue()

        self.root = tk.Tk()
        self.root.title(self.t["title"])
        self.root.minsize(680, 560)
        self.root.geometry("780x660")
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        self._build_protect(nb)
        self._build_verify(nb)
        self._build_config(nb)

        self.status = ttk.Label(self.root, text=self.t["ready"], anchor="w")
        self.status.pack(fill="x", padx=12, pady=(0, 8))

        # macOS Tk (especially when run from a venv) can present a blank white
        # window until the first resize: native subwidgets like scrollbars paint,
        # but the Tk-drawn content does not. Bring the window forward and nudge
        # its geometry by 1px once the loop is running to force the first layout.
        self.root.lift()
        self.root.after(120, self._force_redraw)

    def _force_redraw(self):
        try:
            self.root.update_idletasks()
            w = self.root.winfo_width() or 780
            h = self.root.winfo_height() or 660
            self.root.geometry("%dx%d" % (w + 1, h))
            self.root.after(30, lambda: self.root.geometry("%dx%d" % (w, h)))
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def mainloop(self):
        self.root.mainloop()

    # -- shared widgets -----------------------------------------------------

    def _path_row(self, parent, label, buttons):
        tk, ttk = self.tk, self.ttk
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=14, anchor="w").pack(side="left")
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
        for text, cmd in buttons:
            ttk.Button(row, text=text, command=cmd, width=9).pack(side="left", padx=2)
        return var

    def _log_widget(self, parent):
        tk, ttk = self.tk, self.ttk
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=(8, 0))
        text = tk.Text(frame, height=12, wrap="word", state="disabled",
                       font=("Menlo", 11), background="#1e1e1e", foreground="#e0e0e0")
        sb = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        return text

    def _append(self, widget, line):
        widget.configure(state="normal")
        widget.insert("end", line)
        widget.see("end")
        widget.configure(state="disabled")

    # -- Protect tab --------------------------------------------------------

    def _build_protect(self, nb):
        tk, ttk = self.tk, self.ttk
        from tkinter import filedialog, messagebox
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text=self.t["tab_protect"])

        self.p_input = self._path_row(tab, self.t["input"], [
            (self.t["browse_dir"], lambda: self._pick_dir(self.p_input)),
            (self.t["browse_zip"], lambda: self._pick_file(self.p_input, [("zip", "*.zip")])),
        ])
        self.p_output = self._path_row(tab, self.t["output"], [
            (self.t["browse"], lambda: self._pick_dir(self.p_output)),
        ])

        opts = ttk.LabelFrame(tab, text=self.t["options"], padding=8)
        opts.pack(fill="x", pady=8)

        r1 = ttk.Frame(opts); r1.pack(fill="x", pady=3)
        ttk.Label(r1, text=self.t["strength"], width=12, anchor="w").pack(side="left")
        self.p_strength = tk.StringVar(value="")
        ttk.Combobox(r1, textvariable=self.p_strength, values=STRENGTHS,
                     state="readonly", width=12).pack(side="left")
        ttk.Label(r1, text=self.t["chunk"]).pack(side="left", padx=(18, 4))
        self.p_chunk = tk.StringVar()
        ttk.Entry(r1, textvariable=self.p_chunk, width=10).pack(side="left")

        r2 = ttk.Frame(opts); r2.pack(fill="x", pady=3)
        ttk.Label(r2, text=self.t["platforms"], width=12, anchor="w").pack(side="left")
        self.p_auto = tk.BooleanVar(value=True)
        self.p_plats = {p: tk.BooleanVar(value=False) for p in PLATFORMS}

        def _toggle_auto():
            state = "disabled" if self.p_auto.get() else "normal"
            for cb in self._plat_cbs:
                cb.configure(state=state)
        ttk.Checkbutton(r2, text=self.t["auto"], variable=self.p_auto,
                        command=_toggle_auto).pack(side="left")
        self._plat_cbs = []
        for p in PLATFORMS:
            cb = ttk.Checkbutton(r2, text=p, variable=self.p_plats[p])
            cb.pack(side="left", padx=4)
            cb.configure(state="disabled")
            self._plat_cbs.append(cb)

        self.p_lockdown = tk.BooleanVar(value=True)
        self.p_launcher = tk.BooleanVar(value=True)
        self.p_no_backup = tk.BooleanVar(value=False)
        self.p_keep = tk.BooleanVar(value=False)
        for text, var in ((self.t["lockdown"], self.p_lockdown),
                          (self.t["launcher"], self.p_launcher),
                          (self.t["no_backup"], self.p_no_backup),
                          (self.t["keep_plaintext"], self.p_keep)):
            ttk.Checkbutton(opts, text=text, variable=var).pack(anchor="w", pady=1)

        self.p_plugin = self._path_row(opts, self.t["plugin"], [
            (self.t["browse"], lambda: self._pick_file(self.p_plugin, [("all", "*")])),
        ])
        self.p_config = self._path_row(opts, self.t["config_file"], [
            (self.t["browse"], lambda: self._pick_file(self.p_config, [("toml", "*.toml")])),
        ])

        bar = ttk.Frame(tab); bar.pack(fill="x", pady=(6, 0))
        self.p_btn = ttk.Button(bar, text=self.t["protect_btn"], command=self._run_protect)
        self.p_btn.pack(side="left")
        self.p_prog = ttk.Progressbar(bar, mode="indeterminate", length=180)
        self.p_prog.pack(side="left", padx=10)
        self.p_log = self._log_widget(tab)

    def _run_protect(self):
        from tkinter import messagebox
        game = self.p_input.get().strip()
        if not game:
            messagebox.showwarning(BRAND, self.t["need_input"]); return
        out = self.p_output.get().strip()
        plats = "" if self.p_auto.get() else ",".join(
            p for p in PLATFORMS if self.p_plats[p].get())
        opts = {
            "output": out, "config": self.p_config.get().strip(),
            "chunk_size": self.p_chunk.get().strip(),
            "strength": self.p_strength.get().strip(),
            "plugin": self.p_plugin.get().strip(),
            "platforms": plats,
            "launcher": self.p_launcher.get(),
            "no_lockdown": not self.p_lockdown.get(),
            "keep_plaintext": self.p_keep.get(),
            "no_backup": self.p_no_backup.get(),
        }
        if not messagebox.askyesno(
                self.t["confirm_title"],
                self.t["confirm_body"] % (game, out or "(in place)")):
            return
        args = ["protect", game] + build_protect_args(opts) + ["-y", "--lang", self.lang]
        self._start(_cli_cmd(args), self.p_log, self.p_btn, self.p_prog)

    # -- Verify tab ---------------------------------------------------------

    def _build_verify(self, nb):
        tk, ttk = self.tk, self.ttk
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text=self.t["tab_verify"])
        self.v_input = self._path_row(tab, self.t["protected"], [
            (self.t["browse"], lambda: self._pick_dir(self.v_input)),
        ])
        bar = ttk.Frame(tab); bar.pack(fill="x", pady=(6, 0))
        self.v_btn = ttk.Button(bar, text=self.t["verify_btn"], command=self._run_verify)
        self.v_btn.pack(side="left")
        self.v_prog = ttk.Progressbar(bar, mode="indeterminate", length=180)
        self.v_prog.pack(side="left", padx=10)
        self.v_log = self._log_widget(tab)

    def _run_verify(self):
        from tkinter import messagebox
        d = self.v_input.get().strip()
        if not d:
            messagebox.showwarning(BRAND, self.t["need_protected"]); return
        self._start(_cli_cmd(["verify", d, "--lang", self.lang]),
                    self.v_log, self.v_btn, self.v_prog)

    # -- Config tab ---------------------------------------------------------

    def _build_config(self, nb):
        tk, ttk = self.tk, self.ttk
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text=self.t["tab_config"])

        form = ttk.LabelFrame(tab, text=self.t["options"], padding=8)
        form.pack(fill="x")
        r1 = ttk.Frame(form); r1.pack(fill="x", pady=3)
        ttk.Label(r1, text=self.t["strength"], width=12, anchor="w").pack(side="left")
        self.c_strength = tk.StringVar(value="")
        ttk.Combobox(r1, textvariable=self.c_strength, values=STRENGTHS,
                     state="readonly", width=12).pack(side="left")
        ttk.Label(r1, text=self.t["chunk"]).pack(side="left", padx=(18, 4))
        self.c_chunk = tk.StringVar()
        ttk.Entry(r1, textvariable=self.c_chunk, width=10).pack(side="left")

        r2 = ttk.Frame(form); r2.pack(fill="x", pady=3)
        ttk.Label(r2, text=self.t["platforms"], width=12, anchor="w").pack(side="left")
        self.c_plats = {p: tk.BooleanVar(value=False) for p in PLATFORMS}
        for p in PLATFORMS:
            ttk.Checkbutton(r2, text=p, variable=self.c_plats[p]).pack(side="left", padx=4)

        self.c_lockdown = tk.BooleanVar(value=True)
        self.c_launcher = tk.BooleanVar(value=True)
        self.c_keep = tk.BooleanVar(value=False)
        for text, var in ((self.t["lockdown"], self.c_lockdown),
                          (self.t["launcher"], self.c_launcher),
                          (self.t["keep_plaintext"], self.c_keep)):
            ttk.Checkbutton(form, text=text, variable=var).pack(anchor="w", pady=1)

        lists = ttk.Frame(form); lists.pack(fill="x", pady=3)
        ttk.Label(lists, text=self.t["exclude"]).grid(row=0, column=0, sticky="w")
        ttk.Label(lists, text=self.t["keep_on_disk"]).grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.c_exclude = tk.Text(lists, height=3, width=30)
        self.c_exclude.grid(row=1, column=0, sticky="we")
        self.c_keep_disk = tk.Text(lists, height=3, width=30)
        self.c_keep_disk.grid(row=1, column=1, sticky="we", padx=(12, 0))
        lists.columnconfigure(0, weight=1); lists.columnconfigure(1, weight=1)

        keys = ttk.LabelFrame(form, text=self.t["keys"], padding=6)
        keys.pack(fill="x", pady=(6, 0))
        self.c_master = tk.StringVar(); self.c_script = tk.StringVar()
        for i, (lbl, var) in enumerate(((self.t["master_env"], self.c_master),
                                        (self.t["script_env"], self.c_script))):
            ttk.Label(keys, text=lbl, width=12, anchor="w").grid(row=i, column=0, sticky="w")
            ttk.Entry(keys, textvariable=var, width=28).grid(row=i, column=1, sticky="w", pady=1)

        bar = ttk.Frame(tab); bar.pack(fill="x", pady=8)
        ttk.Button(bar, text=self.t["open"], command=self._config_open).pack(side="left")
        ttk.Button(bar, text=self.t["generate"], command=self._config_generate).pack(side="left", padx=6)
        ttk.Button(bar, text=self.t["save_as"], command=self._config_save).pack(side="left")

        ttk.Label(tab, text=self.t["preview"]).pack(anchor="w")
        self.c_preview = tk.Text(tab, height=12, wrap="none", font=("Menlo", 11))
        self.c_preview.pack(fill="both", expand=True)
        self._config_generate()

    def _config_collect(self):
        return {
            "strength": self.c_strength.get().strip(),
            "chunk_size": self.c_chunk.get().strip(),
            "lockdown": self.c_lockdown.get(),
            "launcher": self.c_launcher.get(),
            "keep_plaintext": self.c_keep.get(),
            "exclude": self.c_exclude.get("1.0", "end").splitlines(),
            "keep_on_disk": self.c_keep_disk.get("1.0", "end").splitlines(),
            "platforms": [p for p in PLATFORMS if self.c_plats[p].get()],
            "master_env": self.c_master.get().strip(),
            "script_env": self.c_script.get().strip(),
        }

    def _config_generate(self):
        self.c_preview.delete("1.0", "end")
        self.c_preview.insert("1.0", build_toml(self._config_collect()))

    def _config_save(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".toml", initialfile="renmori.toml",
            filetypes=[("toml", "*.toml")])
        if not path:
            return
        self._config_generate()
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.c_preview.get("1.0", "end-1c"))
        self.status.configure(text=self.t["saved"] % path)

    def _config_open(self):
        from tkinter import filedialog, messagebox
        path = filedialog.askopenfilename(filetypes=[("toml", "*.toml"), ("all", "*")])
        if not path:
            return
        raw = open(path, "r", encoding="utf-8").read()
        try:
            from .cli import _load_toml
            import pathlib
            data = _load_toml(pathlib.Path(path))
            self._config_apply(data)
            self._config_generate()
        except Exception as e:  # noqa: BLE001 - fall back to raw editing
            messagebox.showinfo(BRAND, self.t["open_fail"] % e)
            self.c_preview.delete("1.0", "end")
            self.c_preview.insert("1.0", raw)

    def _config_apply(self, data):
        p = data.get("protect", {}) if isinstance(data, dict) else {}
        k = data.get("keys", {}) if isinstance(data, dict) else {}
        self.c_strength.set(p.get("strength", "") or "")
        self.c_chunk.set(str(p.get("chunk_size", "")) if p.get("chunk_size") else "")
        self.c_lockdown.set(bool(p.get("lockdown", True)))
        self.c_launcher.set(bool(p.get("launcher", True)))
        self.c_keep.set(bool(p.get("keep_plaintext", False)))
        self.c_exclude.delete("1.0", "end")
        self.c_exclude.insert("1.0", "\n".join(p.get("exclude", []) or []))
        self.c_keep_disk.delete("1.0", "end")
        self.c_keep_disk.insert("1.0", "\n".join(p.get("keep_on_disk", []) or []))
        for plat, var in self.c_plats.items():
            var.set(plat in (p.get("platforms", []) or []))
        self.c_master.set(k.get("master_env", "") or "")
        self.c_script.set(k.get("script_env", "") or "")

    # -- file pickers -------------------------------------------------------

    def _pick_dir(self, var):
        from tkinter import filedialog
        d = filedialog.askdirectory()
        if d:
            var.set(d)

    def _pick_file(self, var, types):
        from tkinter import filedialog
        f = filedialog.askopenfilename(filetypes=types + [("all", "*")])
        if f:
            var.set(f)

    # -- subprocess runner --------------------------------------------------

    def _start(self, cmd, log, btn, prog):
        if self.proc is not None:
            return  # one job at a time
        log.configure(state="normal"); log.delete("1.0", "end"); log.configure(state="disabled")
        self._append(log, "$ %s\n\n" % " ".join(cmd))
        btn.configure(state="disabled")
        prog.start(12)
        self.status.configure(text=self.t["running"])
        t = threading.Thread(target=self._worker, args=(cmd,), daemon=True)
        t.start()
        self.root.after(80, lambda: self._drain(log, btn, prog))

    def _worker(self, cmd):
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env)
            for line in self.proc.stdout:
                self.q.put(("line", line))
            self.proc.wait()
            self.q.put(("done", self.proc.returncode))
        except Exception as e:  # noqa: BLE001
            self.q.put(("line", "error: %s\n" % e))
            self.q.put(("done", 1))
        finally:
            self.proc = None

    def _drain(self, log, btn, prog):
        last_json = None
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "line":
                    self._append(log, payload)
                    s = payload.strip()
                    if s.startswith("{") and '"status"' in s:
                        try:
                            last_json = json.loads(s)
                        except ValueError:
                            pass
                    if last_json is not None:
                        self._last_json = last_json
                elif kind == "done":
                    prog.stop()
                    btn.configure(state="normal")
                    code = payload
                    result = getattr(self, "_last_json", None)
                    ok = code == 0 and (result is None or result.get("status") == "ok")
                    self.status.configure(text=self.t["done_ok"] if ok else self.t["done_err"])
                    self._last_json = None
                    return
        except queue.Empty:
            pass
        self.root.after(80, lambda: self._drain(log, btn, prog))

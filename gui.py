import tkinter as tk
from tkinter import scrolledtext, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import subprocess
import threading
import time
import os

LOG_DIR = "logs"
APP_FONT = "Segoe UI"
LOG_FONT = "Consolas 10"

class LogTailer(threading.Thread):
    def __init__(self, filepath, text_widget, done_callback=None):
        super().__init__(daemon=True)
        self.filepath = filepath
        self.text_widget = text_widget
        self.done_callback = done_callback # Callback for when "DONE" is detected
        self._stop_event = threading.Event()

    def run(self):
        # Wait for file to exist
        while not os.path.exists(self.filepath):
            if self._stop_event.is_set():
                return
            time.sleep(0.1)

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)

                while not self._stop_event.is_set():
                    line = f.readline()
                    if line:
                        self.append_line(line)
                        # Check for the special string to trigger the clear callback
                        if "---DONE LOGGER---" in line and self.done_callback:
                            self.done_callback()
                    else:
                        time.sleep(0.1)
        except Exception as e:
            if not self._stop_event.is_set():
                self.append_line(f"[LogTailer] Error reading {self.filepath}: {e}\n")

    def append_line(self, line):
        def append():
            if self.text_widget.winfo_exists():
                self.text_widget.configure(state="normal")
                self.text_widget.insert(tk.END, line)
                self.text_widget.see(tk.END)
                self.text_widget.configure(state="disabled")
        try:
            self.text_widget.after(0, append)
        except tk.TclError:
            pass # Main window was likely destroyed

    def stop(self):
        self._stop_event.set()

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Modern Process Launcher")
        self.root.geometry("1000x700")

        self.processes = []
        self.tailer_threads = []
        self.log_widgets = {}

        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=BOTH, expand=True)

        config_frame = ttk.Labelframe(main_frame, text="Configuration", padding="10")
        config_frame.pack(fill=X, pady=5)
        config_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="Arguments:", font=(APP_FONT, 10)).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.args_entry = ttk.Entry(config_frame, font=(APP_FONT, 10))
        self.args_entry.insert(0, "--headless")
        self.args_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(config_frame, text="Concurrent Splits:", font=(APP_FONT, 10)).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.concurrent_entry = ttk.Entry(config_frame, font=(APP_FONT, 10), width=10)
        self.concurrent_entry.insert(0, "3")
        self.concurrent_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(config_frame, text="Total Runs:", font=(APP_FONT, 10)).grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.total_entry = ttk.Entry(config_frame, font=(APP_FONT, 10), width=10)
        self.total_entry.insert(0, "-1")
        self.total_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=X, pady=(5, 10))

        self.launch_btn = ttk.Button(control_frame, text="Launch", command=self.launch_processes, bootstyle="success")
        self.launch_btn.pack(side=LEFT, expand=True, fill=X, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="Stop All", command=self.cleanup, bootstyle="danger", state=DISABLED)
        self.stop_btn.pack(side=LEFT, expand=True, fill=X, padx=5)

        logs_container = ttk.Labelframe(main_frame, text="Logs", padding=5)
        logs_container.pack(fill=BOTH, expand=True)

        self.canvas = tk.Canvas(logs_container, borderwidth=0, background="#2b3e50")
        self.vscroll = ttk.Scrollbar(logs_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.vscroll.pack(side=RIGHT, fill=Y)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)

        self.logs_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.logs_frame, anchor="nw", tags="self.logs_frame")

        self.logs_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        self.status_var = tk.StringVar(value="Idle")
        self.running_procs_var = tk.StringVar(value="Running processes: 0")
        status_bar = ttk.Frame(self.root, padding=5)
        status_bar.pack(fill=X, side=BOTTOM)
        ttk.Label(status_bar, textvariable=self.status_var).pack(side=LEFT, padx=10)
        ttk.Label(status_bar, textvariable=self.running_procs_var).pack(side=LEFT, padx=10)

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig("self.logs_frame", width=event.width)

    def _on_mousewheel(self, event):
        if self.vscroll.get()[0] != 0.0 or self.vscroll.get()[1] != 1.0:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def schedule_log_clear(self, text_widget):
        """Schedules a specific log widget to be cleared after 2 seconds."""
        self.root.after(2000, lambda: self.clear_log_widget(text_widget))

    def clear_log_widget(self, text_widget):
        """Clears the content of a single log text widget."""
        try:
            if text_widget.winfo_exists():
                text_widget.configure(state="normal")
                text_widget.delete(1.0, tk.END)
                text_widget.configure(state="disabled")
        except tk.TclError:
            pass # Widget was already destroyed

    def launch_processes(self):
        self.cleanup()
        os.makedirs(LOG_DIR, exist_ok=True)

        try:
            concurrent = int(self.concurrent_entry.get())
            if concurrent < 1:
                raise ValueError("Concurrent must be a positive integer.")
            total = int(self.total_entry.get())
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return

        self.launch_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)
        self.status_var.set(f"Launching {concurrent} coroutine(s)...")

        instance_id = f"{os.getpid()}_{int(time.time())}"
        log_path_base = os.path.join(LOG_DIR, f"WebshareRegisterer_{instance_id}")

        for i in range(concurrent):
            log_path = f"{log_path_base}_coro_{i}.log"
            open(log_path, "w").close() # Create/clear log file

            # Widgets are created fresh each time since cleanup destroys them
            labelframe = ttk.Labelframe(self.logs_frame, text=f"Coroutine {i} Log", bootstyle="info")
            labelframe.pack(fill=X, expand=True, padx=10, pady=5)

            text_widget = tk.Text(
                labelframe, font=LOG_FONT, wrap="word", bg="#323232", fg="#ffffff",
                insertbackground="#ffffff", height=10, borderwidth=0, highlightthickness=0
            )
            scrollbar = ttk.Scrollbar(labelframe, orient="vertical", command=text_widget.yview)
            scrollbar.pack(side=RIGHT, fill=Y, padx=(0,5), pady=5)
            text_widget.pack(side=LEFT, fill=BOTH, expand=True, padx=(5, 0), pady=5)
            text_widget.configure(yscrollcommand=scrollbar.set, state="disabled")
            
            # Store the created widgets
            self.log_widgets[i] = (labelframe, text_widget, scrollbar)
            
            # Pass a callback to the tailer for auto-clearing.
            # Use a default argument in lambda to capture the current text_widget.
            clear_callback = lambda w=text_widget: self.schedule_log_clear(w)
            tailer = LogTailer(log_path, text_widget, done_callback=clear_callback)
            tailer.start()
            self.tailer_threads.append(tailer)

        try:
            cmd = [r".venv/Scripts/python.exe", "-u", "main.py"] + (self.args_entry.get().split() if self.args_entry.get() else []) + [
                "--instance-id", instance_id, "--concurrent", str(concurrent), "--total", str(total)
            ]
            p = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.processes.append(p)
        except Exception as e:
            messagebox.showerror("Process Error", f"Failed to start process:\n{e}")
            self.cleanup()
            return

        self.root.after(100, self.check_processes)

    def check_processes(self):
        if not self.processes:
            return
        running_count = sum(1 for p in self.processes if p.poll() is None)
        self.running_procs_var.set(f"Running processes: {running_count}")

        if running_count == 0:
            self.status_var.set("All processes finished.")
            self.launch_btn.config(state=NORMAL)
            self.stop_btn.config(state=DISABLED)
            for t in self.tailer_threads:
                t.stop()
            self.tailer_threads.clear()
            self.processes.clear()
        else:
            self.status_var.set(f"Running {running_count} process(es)...")
            self.root.after(1000, self.check_processes)

    def cleanup(self):
        self.status_var.set("Stopping processes and cleaning up...")

        for t in self.tailer_threads:
            t.stop()
        for t in self.tailer_threads:
            t.join(timeout=0.5)
        self.tailer_threads.clear()

        for p in self.processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    p.kill()
        self.processes.clear()

        # --- MODIFIED: Destroy log widgets instead of clearing them ---
        for i, (labelframe, _, _) in self.log_widgets.items():
            if labelframe.winfo_exists():
                labelframe.destroy()
        self.log_widgets.clear() # Clear the dictionary for the next run

        self.launch_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.status_var.set("Idle")
        self.running_procs_var.set("Running processes: 0")

    def on_close(self):
        self.cleanup()
        self.root.destroy()

if __name__ == "__main__":
    root = ttk.Window(themename="cyborg")
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
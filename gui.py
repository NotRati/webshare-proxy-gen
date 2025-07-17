import tkinter as tk
from tkinter import scrolledtext, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import subprocess
import threading
import time
import os

# --- Constants ---
LOG_DIR = "logs"
APP_FONT = "Segoe UI"
LOG_FONT = "Consolas 10" # A good monospaced font for logs

class LogTailer(threading.Thread):
    def __init__(self, filepath, text_widget, labelframe_widget, process):
        super().__init__(daemon=True)
        self.filepath = filepath
        self.text_widget = text_widget
        self.labelframe = labelframe_widget
        self.process = process
        self._stop_event = threading.Event()

    def run(self):
        # Update labelframe with the PID as soon as it's available
        self.labelframe.configure(text=f"Instance - PID: {self.process.pid}")
        
        # Wait for file creation (timeout after 10s)
        timeout = 10
        waited = 0
        while not os.path.exists(self.filepath) and not self._stop_event.is_set():
            if waited >= timeout:
                msg = f"Timeout waiting for log file: {os.path.basename(self.filepath)}\n"
                self.text_widget.after(0, self.append_line, msg)
                return
            time.sleep(0.1)
            waited += 0.1

        if self._stop_event.is_set():
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)
                while not self._stop_event.is_set():
                    line = f.readline()
                    if line:
                        self.text_widget.after(0, self.append_line, line)
                        if "---DONE LOGGER---" in line:
                            self.text_widget.after(100, self.clear_text)
                    else:
                        time.sleep(0.1)
        except Exception as e:
            error_msg = f"Error reading log file: {e}\n"
            try:
                self.text_widget.after(0, self.append_line, error_msg)
            except tk.TclError:
                print(error_msg)

    def append_line(self, line):
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert(tk.END, line)
            self.text_widget.see(tk.END)
            self.text_widget.configure(state="disabled")
        except tk.TclError:
            pass

    def clear_text(self):
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.delete(1.0, tk.END)
            self.text_widget.configure(state="disabled")
        except tk.TclError:
            pass

    def stop(self):
        self._stop_event.set()


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Modern Process Launcher")
        self.root.geometry("800x600")

        self.processes = []
        self.tailer_threads = []

        # --- Main Layout ---
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=BOTH, expand=True)

        # --- Configuration Section ---
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

        # --- Controls Section ---
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=X, pady=(5, 10))
        
        self.launch_btn = ttk.Button(control_frame, text="Launch", command=self.launch_processes, bootstyle="success")
        self.launch_btn.pack(side=LEFT, expand=True, fill=X, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="Stop All", command=self.cleanup, bootstyle="danger", state=DISABLED)
        self.stop_btn.pack(side=LEFT, expand=True, fill=X, padx=5)

        # --- Logs Section ---
        self.logs_frame = ttk.Frame(main_frame)
        self.logs_frame.pack(fill=BOTH, expand=True)

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="Idle")
        status_bar = ttk.Frame(self.root, padding=5)
        status_bar.pack(fill=X, side=BOTTOM)
        ttk.Label(status_bar, textvariable=self.status_var).pack(side=LEFT)


    def launch_processes(self):
        self.cleanup()
        os.makedirs(LOG_DIR, exist_ok=True)

        args = self.args_entry.get()
        try:
            concurrent = int(self.concurrent_entry.get())
            if concurrent < 1: raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Concurrent must be a positive integer.")
            return

        self.launch_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)
        self.status_var.set(f"Launching {concurrent} process(es)...")
        
        for i in range(concurrent):
            instance_id = f"{os.getpid()}_{i}"
            cmd = [r"C:\Users\Me\Workspace\Coding\webshare proxy generator\.venv\Scripts\python.exe", "-u", "main.py"] + (args.split() if args else []) + ["--instance-id", instance_id]

            try:
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                p = subprocess.Popen(cmd, creationflags=creationflags)
                self.processes.append(p)
            except Exception as e:
                messagebox.showerror("Process Error", f"Failed to start process:\n{e}")
                self.cleanup()
                return

            # --- Create Log Viewer Widget for this Process ---
            log_container = ttk.Labelframe(self.logs_frame, text=f"Instance {i} - Initializing...")
            log_container.pack(fill=BOTH, expand=True, padx=5, pady=5)
            
            # Use standard scrolledtext but style it to match the dark theme
            text_widget = scrolledtext.ScrolledText(log_container, font=LOG_FONT, wrap=WORD,
                                                    bg="#2b3e50", fg="#ffffff", insertbackground="#ffffff")
            text_widget.pack(fill=BOTH, expand=True, padx=5, pady=5)
            text_widget.configure(state="disabled") # Start as read-only
            
            log_path = os.path.join(LOG_DIR, f"WebshareRegisterer_{instance_id}.log")
            
            tailer = LogTailer(log_path, text_widget, log_container, p)
            tailer.start()
            self.tailer_threads.append(tailer)
        
        self.root.after(100, self.check_processes)

    def check_processes(self):
        running_count = sum(1 for p in self.processes if p.poll() is None)
        
        if running_count == 0 and self.processes:
            self.status_var.set("All tasks finished.")
            self.launch_btn.config(state=NORMAL)
            self.stop_btn.config(state=DISABLED)
            self.processes.clear() # Clear list for next run
        else:
            self.status_var.set(f"Running {running_count} process(es)...")
            self.root.after(1000, self.check_processes) # Check again in 1 second

    def cleanup(self):
        self.status_var.set("Stopping processes...")
        for t in self.tailer_threads: t.stop()
        for t in self.tailer_threads: t.join(timeout=0.2)
        self.tailer_threads.clear()

        for p in self.processes:
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=0.5)
                except subprocess.TimeoutExpired: p.kill()
        self.processes.clear()

        for widget in self.logs_frame.winfo_children():
            widget.destroy()

        self.launch_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.status_var.set("Idle")

    def on_close(self):
        self.cleanup()
        self.root.destroy()

if __name__ == "__main__":
    # Use the 'cyborg' theme for a professional dark look. Other good options: 'darkly', 'superhero'
    root = ttk.Window(themename="cyborg") 
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
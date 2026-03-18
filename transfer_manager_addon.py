import threading
import time
import queue
import tkinter as tk
from tkinter import ttk
import math
import os


class ProgressCallback:
    """
    Tracks per-file transfer progress and pushes UI-safe updates to a shared event queue.
    Used for both upload and download transfers.
    """
    def __init__(self, filename, filesize, ui_queue, transfer_id):
        self.filename = filename
        self.filesize = filesize
        self.ui_queue = ui_queue
        self.transfer_id = transfer_id

        self._lock = threading.Lock()
        self._start_time = time.time()
        self._last_update_time = self._start_time
        self._last_bytes = 0
        self._bytes_transferred = 0

    def __call__(self, bytes_amount):
        with self._lock:
            self._bytes_transferred += bytes_amount

            now = time.time()
            elapsed = now - self._start_time
            delta_time = now - self._last_update_time
            delta_bytes = self._bytes_transferred - self._last_bytes

            # Instant speed (MB/s)
            speed = (delta_bytes / delta_time) / (1024 * 1024) if delta_time > 0 else 0.0

            # Average speed (MB/s)
            avg_speed = (self._bytes_transferred / elapsed) / (1024 * 1024) if elapsed > 0 else 0.0

            # Percentage
            pct = (self._bytes_transferred / self.filesize) * 100 if self.filesize > 0 else 0

            # ETA
            remaining = self.filesize - self._bytes_transferred
            eta = remaining / (avg_speed * 1024 * 1024) if avg_speed > 0 else None

            self._last_update_time = now
            self._last_bytes = self._bytes_transferred

        # Send UI update event
        self.ui_queue.put((
            "progress_update",
            {
                "id": self.transfer_id,
                "filename": self.filename,
                "bytes_done": self._bytes_transferred,
                "bytes_total": self.filesize,
                "pct": pct,
                "speed": speed,
                "avg_speed": avg_speed,
                "eta": eta,
            }
        ))


class S3TransferManagerWindow(tk.Toplevel):
    """
    A popup window that lists active transfers.
    Only active transfers (1–4) are shown dynamically.
    """
    def __init__(self, parent, ui_queue):
        super().__init__(parent)
        self.title("S3 Transfer Manager")
        self.geometry("600x350")
        self.resizable(True, True)

        self.ui_queue = ui_queue
        
        # Map transfer_id -> widgets
        self.rows = {}

        self.container = ttk.Frame(self, padding=10)
        self.container.pack(fill=tk.BOTH, expand=True)

        self.update_window()

    def update_window(self):
        """Called periodically to update UI from queue."""
        try:
            while True:
                event, payload = self.ui_queue.get_nowait()
                if event == "progress_update":
                    self.update_transfer_row(payload)
                elif event == "transfer_done":
                    self.finalize_transfer(payload["id"])
        except queue.Empty:
            pass

        self.after(200, self.update_window)

    def update_transfer_row(self, data):
        tid = data["id"]
        if tid not in self.rows:
            # Create new row
            frame = ttk.Frame(self.container)
            frame.pack(fill=tk.X, pady=4)

            name_lbl = ttk.Label(frame, text=data["filename"])
            name_lbl.pack(anchor="w")

            pb = ttk.Progressbar(frame, orient="horizontal", length=500, mode="determinate")
            pb.pack(fill=tk.X, pady=2)

            stat_lbl = ttk.Label(frame, text="")
            stat_lbl.pack(anchor="w")

            self.rows[tid] = (frame, name_lbl, pb, stat_lbl)

        frame, name_lbl, pb, stat_lbl = self.rows[tid]

        pb["value"] = data["pct"]

        speed = f"{data['speed']:.1f} MB/s"
        avg = f"{data['avg_speed']:.1f} MB/s"
        pct = f"{data['pct']:.1f}%"

        if data["eta"] is None:
            eta = "ETA: --"
        else:
            eta = f"ETA: {int(data['eta'])}s"

        stat_lbl.config(text=f"{pct} • {speed} • avg {avg} • {eta}")

    def finalize_transfer(self, transfer_id):
        # Optionally mark row or remove it
        pass



class TransferManager:
    """
    Orchestrates callbacks, global progress, and the popup manager window.
    Works with existing upload/download code without refactoring.
    """
    def __init__(self, parent):
        self.parent = parent
        self.ui_queue = queue.Queue()
        self.active_transfers = {}

        # Global progress
        self.global_bytes_done = 0
        self.global_bytes_total = 0

        # Create popup lazily
        self.popup = None

        # Create global progress bar UI
        self.container = ttk.Frame(parent, padding=4)
        self.container.pack(side=tk.BOTTOM, fill=tk.X)

        self.progressbar = ttk.Progressbar(self.container, orient="horizontal", mode="determinate")
        self.progressbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.open_btn = ttk.Button(self.container, text="Show S3 Transfer Manager",
                                   command=self.open_popup)
        self.open_btn.pack(side=tk.RIGHT)

        # Poll UI queue
        self.parent.after(200, self._poll_ui_queue)

    def open_popup(self):
        if self.popup is None or not tk.Toplevel.winfo_exists(self.popup):
            self.popup = S3TransferManagerWindow(self.parent, self.ui_queue)
        else:
            self.popup.lift()

    def register_transfer(self, filename, filesize):
        """Called before starting upload/download"""
        tid = id(filename) ^ id(time.time())
        self.active_transfers[tid] = {
            "filename": filename,
            "size": filesize,
        }

        self.global_bytes_total += filesize

        return tid

    def create_callback(self, filename, filesize):
        """Return a ProgressCallback instance."""
        tid = self.register_transfer(filename, filesize)
        return ProgressCallback(filename, filesize, self.ui_queue, tid)

    def mark_done(self, tid):
        # Called after upload/download completes
        self.ui_queue.put(("transfer_done", {"id": tid}))

    def _poll_ui_queue(self):
        try:
            while True:
                event, payload = self.ui_queue.get_nowait()

                if event == "progress_update":
                    # Update global progress
                    tid = payload["id"]
                    done = payload["bytes_done"]
                    total = payload["bytes_total"]

                    # Recalculate global progress (simple sum)
                    agg_done = 0
                    agg_total = 0
                    for t in self.active_transfers.values():
                        agg_done += t.get("done", 0)
                        agg_total += t.get("size", 0)

                    # Update this transfer's done bytes
                    self.active_transfers[tid]["done"] = done

                    if agg_total > 0:
                        pct = (agg_done / agg_total) * 100
                        self.progressbar["value"] = pct

                elif event == "transfer_done":
                    # final global update
                    tid = payload["id"]
                    if tid in self.active_transfers:
                        del self.active_transfers[tid]

        except queue.Empty:
            pass

        self.parent.after(200, self._poll_ui_queue)

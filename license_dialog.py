"""
License Dialog - Activation UI for ZI Background Remover
=========================================================
Dialog sederhana untuk aktivasi lisensi.
FIXED: Tidak lagi force close setelah aktivasi sukses.
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import tkinter as tk
from tkinter import messagebox
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from license_manager import LicenseManager


class LicenseDialog:
    """License activation dialog window."""
    
    def __init__(self, parent=None, on_success=None):
        self.parent = parent
        self.on_success = on_success
        self.license_manager = LicenseManager()
        self.result = False
        
        # Create dialog window
        if parent:
            self.dialog = ttk.Toplevel(parent)
        else:
            self.dialog = ttk.Window(themename="darkly")
        
        self.dialog.title("Aktivasi Lisensi - ZI Background Remover")
        self.dialog.geometry("500x400")
        self.dialog.resizable(False, False)
        
        # Center on screen
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 500) // 2
        y = (self.dialog.winfo_screenheight() - 400) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        # Make modal if has parent  
        if parent:
            self.dialog.transient(parent)
            self.dialog.grab_set()
        
        # Prevent closing without activation
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the dialog UI."""
        main_frame = ttk.Frame(self.dialog, padding=30)
        main_frame.pack(fill=BOTH, expand=True)
        
        # Header with icon
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 25))
        
        ttk.Label(header_frame, text="🔐", font=("Segoe UI", 36)).pack(side=LEFT)
        
        header_text = ttk.Frame(header_frame)
        header_text.pack(side=LEFT, padx=(15, 0))
        
        ttk.Label(header_text, text="Aktivasi Lisensi", 
                  font=("Segoe UI", 18, "bold")).pack(anchor=W)
        ttk.Label(header_text, text="Masukkan license key dari penjual",
                  font=("Segoe UI", 10), foreground="#adb5bd").pack(anchor=W)
        
        # License Key Input Section
        license_frame = ttk.Labelframe(main_frame, text="License Key", padding=15)
        license_frame.pack(fill=X, pady=(0, 15))
        
        ttk.Label(license_frame, text="Paste license key yang diberikan oleh penjual:",
                  font=("Segoe UI", 9)).pack(anchor=W, pady=(0, 10))
        
        self.license_text = tk.Text(license_frame, height=4, font=("Consolas", 10),
                                     wrap="word")
        self.license_text.pack(fill=X)
        
        # Status label
        self.status_var = ttk.StringVar(value="")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var,
                                       font=("Segoe UI", 9))
        self.status_label.pack(fill=X, pady=(10, 20))
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X)
        
        ttk.Button(btn_frame, text="✅ Aktivasi", bootstyle="success",
                   command=self.activate, width=15).pack(side=RIGHT)
        
        ttk.Button(btn_frame, text="❌ Keluar", bootstyle="danger-outline",
                   command=self.on_close, width=15).pack(side=RIGHT, padx=(0, 10))
    
    def activate(self):
        """Validate and activate the license."""
        license_key = self.license_text.get("1.0", "end").strip()
        
        if not license_key:
            self.status_var.set("⚠️ Masukkan license key terlebih dahulu")
            self.status_label.configure(foreground="#ffc107")
            return
        
        # Validate license
        is_valid, message = self.license_manager.validate_license(license_key)
        
        if is_valid:
            # Save license (this also creates the device binding)
            if self.license_manager.save_license(license_key):
                self.status_var.set("✅ Aktivasi berhasil!")
                self.status_label.configure(foreground="#20c997")
                self.result = True
                
                messagebox.showinfo("Sukses", 
                    "Lisensi berhasil diaktifkan!\n\nAplikasi siap digunakan.",
                    parent=self.dialog)
                
                if self.on_success:
                    self.on_success()
                
                # Just destroy dialog, don't exit - let main app continue
                self.dialog.destroy()
            else:
                self.status_var.set("⚠️ Gagal menyimpan lisensi")
                self.status_label.configure(foreground="#dc3545")
        else:
            self.status_var.set(f"❌ {message}")
            self.status_label.configure(foreground="#dc3545")
    
    def on_close(self):
        """Handle window close."""
        if not self.result:
            if messagebox.askyesno("Konfirmasi", 
                "Aplikasi tidak dapat digunakan tanpa lisensi.\n\nYakin ingin keluar?",
                parent=self.dialog):
                self.result = False
                self.dialog.destroy()
                # Only exit if user confirms they want to quit
                sys.exit(0)
        else:
            self.dialog.destroy()
    
    def show(self):
        """Show the dialog and wait for it to close."""
        self.dialog.wait_window()
        return self.result


def check_license_on_startup(root=None) -> bool:
    """
    Check license on application startup.
    Shows activation dialog if not licensed.
    """
    lm = LicenseManager()
    
    is_valid, message = lm.is_licensed()
    
    if is_valid:
        return True
    
    # Show activation dialog
    if root:
        root.withdraw()
    
    dialog = LicenseDialog(parent=None)  # Don't parent to avoid focus issues
    result = dialog.show()
    
    if result and root:
        root.deiconify()
    
    return result


# Test the dialog standalone
if __name__ == '__main__':
    root = ttk.Window(themename="darkly")
    root.withdraw()
    
    if check_license_on_startup(root):
        root.deiconify()
        root.title("Test App")
        root.geometry("400x300")
        ttk.Label(root, text="License Valid! App is running.", 
                  font=("Segoe UI", 14)).pack(expand=True)
        root.mainloop()
    else:
        print("License check failed, exiting.")

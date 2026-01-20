import os
import sys

# Application Version
APP_VERSION = "1.0.5"

# Update Server URL (change this to your actual server)
UPDATE_VERSION_URL = "https://raw.githubusercontent.com/mandash12/zi-bg-remover/main/version.json"

# --- BAGIAN PENCEGAHAN ERROR DLL (Wajib di Paling Atas) ---
try:
    import onnxruntime as ort
    capi_path = os.path.join(os.path.dirname(ort.__file__), 'capi')
    if os.path.exists(capi_path):
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(capi_path)
        os.environ['PATH'] = capi_path + os.pathsep + os.environ.get('PATH', '')
except Exception as e:
    print(f"[PRE-LOAD] Gagal mengatur path DLL: {e}")

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox
import tkinter as tk
import threading

# License Manager for status display
try:
    from license_manager import LicenseManager
    LICENSE_AVAILABLE = True
except ImportError:
    LICENSE_AVAILABLE = False

# Updater Module
try:
    from updater import Updater
    UPDATER_AVAILABLE = True
except ImportError:
    UPDATER_AVAILABLE = False

# --- BAGIAN PENCEGAHAN ERROR IMPORT ---
try:
    from rembg import remove, new_session
    from PIL import Image, ImageTk
    import io
except ImportError as e:
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Library Hilang", f"Error: {e}\n\nLibrary belum terinstall. Harap jalankan di terminal:\npip install rembg[cli] pillow")
    sys.exit()

class BackgroundRemoverApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"ZI Advanced Background Remover v{APP_VERSION}")
        self.root.geometry("950x750")
        self.root.resizable(True, True)
        
        # Set Application Icon
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
            icon_image = Image.open(icon_path)
            icon_photo = ImageTk.PhotoImage(icon_image)
            self.root.iconphoto(True, icon_photo)
            self._icon_photo = icon_photo
        except Exception:
            pass

        # Variabel Path
        self.input_folder = ttk.StringVar()
        self.output_folder = ttk.StringVar()
        
        # Variabel Kontrol Proses
        self.is_processing = False
        self.stop_flag = False
        
        # Theme Mode
        self.is_dark_mode = False
        self.light_theme = "minty"
        self.dark_theme = "darkly"
        
        # Variabel Mode (Bulk / Single)
        self.mode = ttk.StringVar(value="bulk")
        
        # Variabel Single Mode
        self.single_input_path = None
        self.single_output_data = None
        self.before_photo = None
        self.after_photo = None
        self.single_filename = ttk.StringVar(value="Tidak ada gambar terpilih")
        
        # Zoom state for after canvas
        self.after_zoom_level = 1.0
        self.after_pan_x = 0
        self.after_pan_y = 0
        self.after_original_img = None
        self.after_drag_start = None
        
        # Model Selection with Display Name Mapping
        # Format: "Display Name": ("internal_model_name", "Description")
        # You can freely change "Display Name" without affecting model loading!
        self.models = {
            "Standar": ("u2net", "Umum - Model standar untuk kebanyakan gambar"),
            "Lite": ("u2netp", "Ringan - Lebih cepat, ukuran lebih kecil"),
            "Human": ("u2net_human_seg", "Manusia - Dioptimalkan untuk segmentasi orang"),
            "Cloth": ("u2net_cloth_seg", "Pakaian - Untuk parsing pakaian"),
            "IsGeneral": ("isnet-general-use", "Akurasi tinggi untuk umum"),
            "IsAnime": ("isnet-anime", "Dioptimalkan untuk karakter anime/2D"),
            "Silueta": ("silueta", "Mirip Standar tapi ukuran lite"),
            "AI PREMIUM": ("birefnet-general", "Model terbaru, akurasi sangat tinggi"),
            "AI PREMIUM Lite": ("birefnet-general-lite", "Versi lebih ringan"),
            "AI PREMIUM Portrait": ("birefnet-portrait", "Untuk foto portrait/wajah"),
            "AI PREMIUM Massive": ("birefnet-massive", "Dilatih dataset besar, paling akurat")
        }
        self.selected_model = ttk.StringVar(value="Silueta")  # Default display name
        
        # Low PC Mode (Resource Saver)
        self.low_pc_mode = ttk.BooleanVar(value=False)
        self.max_image_size = 1024  # Max dimension for low PC mode
        
        # Alpha Matting (Remove dark fringe)
        self.alpha_matting = ttk.BooleanVar(value=True)  # Enabled by default
        
        # Processing Device Selection (CPU/GPU)
        self.available_devices = self.detect_available_devices()
        self.selected_device = ttk.StringVar(value=self.available_devices[0] if self.available_devices else "CPU")

        self.setup_ui()
    
    def detect_available_devices(self):
        """Detect available processing devices (CPU/GPU) with actual names"""
        devices = []
        
        # 1. Detect GPU
        try:
            providers = ort.get_available_providers()
            device_type = ort.get_device()
            
            # If GPU is detected and CUDA provider is available
            if device_type == "GPU" and "CUDAExecutionProvider" in providers:
                gpu_label = "GPU (CUDA)" # Default
                
                # Get GPU name via nvidia-smi (no torch dependency = smaller build)
                try:
                    import subprocess
                    name = subprocess.check_output(
                        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], 
                        encoding='utf-8',
                        creationflags=subprocess.CREATE_NO_WINDOW
                    ).strip()
                    if name:
                        gpu_label = f"GPU: {name}"
                except:
                    pass
                
                devices.append(gpu_label)
        except Exception as e:
            print(f"[INFO] Error detecting GPU: {e}")
        
        # 2. Detect CPU
        cpu_label = "CPU"
        try:
            import subprocess
            # Try to get CPU name via wmic on Windows
            if sys.platform == "win32":
                name = subprocess.check_output("wmic cpu get name /format:list", shell=True, encoding='utf-8').strip()
                if "Name=" in name:
                    cpu_name = name.split("=")[1].strip()
                    cpu_label = f"CPU: {cpu_name}"
        except:
            pass
            
        devices.append(cpu_label)
        return devices
    
    def get_session_providers(self):
        """Get ONNX session providers based on selected device"""
        device = self.selected_device.get()
        if device.startswith("GPU"):
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            return ["CPUExecutionProvider"]
    
    def set_device_mode(self):
        """Set device mode by patching ort.get_device for CPU mode"""
        # Save original function if not already saved
        if not hasattr(self, '_original_get_device'):
            self._original_get_device = ort.get_device
        
        device = self.selected_device.get()
        if device.startswith("CPU"):
            # Force CPU mode by patching get_device
            ort.get_device = lambda: "CPU"
        else:
            # Restore original get_device for GPU modes
            ort.get_device = self._original_get_device


    def setup_ui(self):
        # Main container with padding
        main_container = ttk.Frame(self.root, padding=20)
        main_container.pack(fill=BOTH, expand=True)
        
        # === HEADER ===
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=X, pady=(0, 15))
        
        # Logo (full logo with text)
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "header_logo.png")
            logo_img = Image.open(logo_path)
            # Resize maintaining aspect ratio, height = 45px
            aspect = logo_img.width / logo_img.height
            new_height = 45
            new_width = int(new_height * aspect)
            logo_img = logo_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.header_logo = ImageTk.PhotoImage(logo_img)
            ttk.Label(header_frame, image=self.header_logo).pack(side=LEFT)
        except:
            # Fallback to text if image fails
            ttk.Label(header_frame, text="ZI Advanced Background Remover", 
                      font=("Segoe UI", 16, "bold")).pack(side=LEFT)
        
        # Dark mode toggle button
        self.btn_theme = ttk.Button(header_frame, text="🌙", width=3,
                                     bootstyle="secondary-outline",
                                     command=self.toggle_theme)
        self.btn_theme.pack(side=RIGHT)
        
        # Update button
        if UPDATER_AVAILABLE:
            self.btn_update = ttk.Button(header_frame, text="🔄", width=3,
                                          bootstyle="info-outline",
                                          command=self.check_for_updates)
            self.btn_update.pack(side=RIGHT, padx=(0, 5))
        
        # CPU/GPU Device Selection
        device_frame = ttk.Frame(header_frame)
        device_frame.pack(side=RIGHT, padx=(0, 10))
        
        device_top_row = ttk.Frame(device_frame)
        device_top_row.pack(fill=X)
        
        ttk.Label(device_top_row, text="⚡", font=("Segoe UI", 10)).pack(side=LEFT)
        self.device_combo = ttk.Combobox(device_top_row, textvariable=self.selected_device,
                                          values=self.available_devices, state="readonly", width=18)
        self.device_combo.pack(side=LEFT, padx=(3, 0))
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_change)
        
        # Advantage Label
        self.device_info_label = ttk.Label(device_frame, text="", font=("Segoe UI", 8), 
                                            foreground="#6c757d")
        self.device_info_label.pack(anchor=E, padx=(5, 0))
        
        # Initial description
        self.update_device_description()
        
        # Low PC Mode checkbox
        self.chk_low_pc = ttk.Checkbutton(header_frame, text="💻 Mode Hemat", 
                                           variable=self.low_pc_mode,
                                           bootstyle="success-round-toggle",
                                           command=self.on_low_pc_toggle)
        self.chk_low_pc.pack(side=RIGHT, padx=(0, 15))
        
        # License Status Display
        self.setup_license_status(header_frame)
        
        # === SEGMENTED CONTROL ===
        toggle_frame = ttk.Frame(main_container)
        toggle_frame.pack(pady=(0, 20))
        
        # Create button container with rounded appearance
        btn_container = ttk.Frame(toggle_frame)
        btn_container.pack()
        
        self.btn_bulk = ttk.Button(btn_container, text="Bulk", width=10,
                                    bootstyle="success" if self.mode.get() == "bulk" else "secondary-outline",
                                    command=lambda: self.switch_mode("bulk"))
        self.btn_bulk.pack(side=LEFT, padx=2)
        
        self.btn_single = ttk.Button(btn_container, text="Single", width=10,
                                      bootstyle="success" if self.mode.get() == "single" else "secondary-outline",
                                      command=lambda: self.switch_mode("single"))
        self.btn_single.pack(side=LEFT, padx=2)
        
        # === CONTENT AREA ===
        self.content_frame = ttk.Frame(main_container)
        self.content_frame.pack(fill=BOTH, expand=True)
        
        # Create both mode frames
        self.create_bulk_mode()
        self.create_single_mode()
        
        # Show bulk mode by default
        self.frame_bulk.pack(fill=BOTH, expand=True)
        
        # === FOOTER ===
        footer = ttk.Label(main_container, text="© 2026 ZI Advanced Background Remover. All Rights Reserved.",
                           font=("Segoe UI", 8), foreground="#6c757d")
        footer.pack(side=BOTTOM, pady=(10, 0))
    
    def setup_license_status(self, parent_frame):
        """Setup license status display in header."""
        if not LICENSE_AVAILABLE:
            return
        
        try:
            lm = LicenseManager()
            info = lm.get_license_info()
            
            if not info:
                return
            
            license_frame = ttk.Frame(parent_frame)
            license_frame.pack(side=RIGHT, padx=(0, 15))
            
            package_name = info.get('package_name', 'Unknown')
            remaining = info.get('remaining_days', -1)
            is_expired = info.get('is_expired', False)
            
            # Determine status text and color
            if is_expired:
                status_text = f"⚠️ {package_name} - EXPIRED"
                status_color = "#ef4444"  # Red
            elif remaining == -1:
                status_text = f"✓ {package_name}"
                status_color = "#22c55e"  # Green
            elif remaining <= 3:
                status_text = f"⚠️ {package_name} - {remaining} hari"
                status_color = "#f59e0b"  # Orange/warning
            else:
                status_text = f"✓ {package_name} - {remaining} hari"
                status_color = "#22c55e"  # Green
            
            ttk.Label(license_frame, text=status_text,
                      font=("Segoe UI", 9, "bold"),
                      foreground=status_color).pack()
        except Exception as e:
            # Silently ignore license display errors
            pass

    def create_bulk_mode(self):
        """Create Bulk Mode UI"""
        self.frame_bulk = ttk.Frame(self.content_frame)
        
        # === LOKASI FILE ===
        file_frame = ttk.Labelframe(self.frame_bulk, text="Lokasi File", padding=15)
        file_frame.pack(fill=X, pady=(0, 15))
        
        # Input folder row
        input_row = ttk.Frame(file_frame)
        input_row.pack(fill=X, pady=5)
        ttk.Label(input_row, text="Folder Input:", width=12).pack(side=LEFT)
        ttk.Entry(input_row, textvariable=self.input_folder).pack(side=LEFT, fill=X, expand=True, padx=10)
        ttk.Button(input_row, text="Pilih", bootstyle="secondary-outline",
                   command=self.select_input_folder).pack(side=RIGHT)
        
        # Output folder row
        output_row = ttk.Frame(file_frame)
        output_row.pack(fill=X, pady=5)
        ttk.Label(output_row, text="Folder Output:", width=12).pack(side=LEFT)
        ttk.Entry(output_row, textvariable=self.output_folder).pack(side=LEFT, fill=X, expand=True, padx=10)
        ttk.Button(output_row, text="Pilih", bootstyle="secondary-outline",
                   command=self.select_output_folder).pack(side=RIGHT)
        
        # === MODEL SELECTION ===
        model_frame = ttk.Labelframe(self.frame_bulk, text="Pilih Model AI", padding=15)
        model_frame.pack(fill=X, pady=(0, 15))
        
        model_row = ttk.Frame(model_frame)
        model_row.pack(fill=X)
        ttk.Label(model_row, text="Model:", width=12).pack(side=LEFT)
        
        self.bulk_model_combo = ttk.Combobox(model_row, textvariable=self.selected_model,
                                              values=list(self.models.keys()), state="readonly")
        self.bulk_model_combo.pack(side=LEFT, fill=X, expand=True, padx=10)
        self.bulk_model_combo.bind("<<ComboboxSelected>>", self.on_model_change)
        
        ttk.Button(model_row, text="ⓘ", width=3, bootstyle="info-outline",
                   command=self.show_model_info).pack(side=RIGHT)
        
        # Model description (extract description from tuple)
        initial_model_info = self.models.get(self.selected_model.get(), ("", ""))
        self.bulk_model_desc = ttk.Label(model_frame, text=initial_model_info[1],
                                          font=("Segoe UI", 9), foreground="gray")
        self.bulk_model_desc.pack(anchor=W, pady=(10, 0))
        
        # === ALPHA MATTING ===
        matting_frame = ttk.Frame(self.frame_bulk)
        matting_frame.pack(fill=X, pady=(0, 15))
        
        self.bulk_matting_check = ttk.Checkbutton(
            matting_frame, 
            text="✨ Perhalus (hapus tepi kehitaman)",
            variable=self.alpha_matting,
            bootstyle="success-round-toggle"
        )
        self.bulk_matting_check.pack(side=LEFT)
        
        # === STATUS ===
        status_frame = ttk.Frame(self.frame_bulk)
        status_frame.pack(fill=X, pady=(0, 10))
        
        ttk.Label(status_frame, text="Status", bootstyle="success", 
                  font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        self.status_label = ttk.Label(status_frame, text="Siap memulai...", foreground="gray")
        self.status_label.pack(side=RIGHT)
        
        self.progress_bar = ttk.Progressbar(self.frame_bulk, bootstyle="success-striped", 
                                             mode="determinate")
        self.progress_bar.pack(fill=X, pady=(0, 15))
        
        # === SYSTEM LOG ===
        log_header = ttk.Frame(self.frame_bulk)
        log_header.pack(fill=X)
        
        ttk.Label(log_header, text="📋 SYSTEM LOG", font=("Segoe UI", 10, "bold")).pack(side=LEFT)
        ttk.Button(log_header, text="Clear", bootstyle="link",
                   command=self.clear_log).pack(side=RIGHT)
        
        self.log_text = tk.Text(self.frame_bulk, height=8, font=("Consolas", 9))
        self.log_text.pack(fill=BOTH, expand=True, pady=5)
        
        # === ACTION BUTTONS ===
        btn_frame = ttk.Frame(self.frame_bulk)
        btn_frame.pack(fill=X, pady=(15, 0))
        
        self.btn_stop = ttk.Button(btn_frame, text="⬛ STOP", bootstyle="danger",
                                    command=self.stop_thread, state="disabled")
        self.btn_stop.pack(side=RIGHT, padx=(10, 0))
        
        self.btn_start = ttk.Button(btn_frame, text="▶ MULAI PROSES", bootstyle="success",
                                     command=self.start_thread)
        self.btn_start.pack(side=RIGHT)

    def create_single_mode(self):
        """Create Single Mode UI"""
        self.frame_single = ttk.Frame(self.content_frame)
        
        # Main split layout
        main_pane = ttk.Frame(self.frame_single)
        main_pane.pack(fill=BOTH, expand=True)
        
        # === LEFT SIDE: Preview ===
        left_frame = ttk.Labelframe(main_pane, text="📷 Single Image Processing", padding=15)
        left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        
        # File selection row
        file_row = ttk.Frame(left_frame)
        file_row.pack(fill=X, pady=(0, 15))
        
        self.single_file_label = ttk.Label(file_row, textvariable=self.single_filename, 
                                            foreground="gray", font=("Segoe UI", 9))
        self.single_file_label.pack(side=LEFT, fill=X, expand=True)
        
        ttk.Button(file_row, text="📁 Pilih Gambar", bootstyle="info",
                   command=self.select_single_image).pack(side=RIGHT)
        
        # Preview area with labels
        preview_container = ttk.Frame(left_frame)
        preview_container.pack(fill=BOTH, expand=True)
        
        # Before section
        before_section = ttk.Frame(preview_container)
        before_section.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        
        ttk.Label(before_section, text="SEBELUM", font=("Segoe UI", 10, "bold"), 
                  foreground="#6c757d").pack(anchor=W, pady=(0, 5))
        
        # Blue bordered frame for Before canvas
        before_border = ttk.Frame(before_section, bootstyle="info")
        before_border.pack(fill=BOTH, expand=True)
        
        self.canvas_before = tk.Canvas(before_border, width=280, height=280, 
                                        bg="white", highlightthickness=2, 
                                        highlightbackground="#0dcaf0")
        self.canvas_before.pack(fill=BOTH, expand=True, padx=2, pady=2)
        
        # After section
        after_section = ttk.Frame(preview_container)
        after_section.pack(side=LEFT, fill=BOTH, expand=True, padx=(10, 0))
        
        # Header with zoom controls
        after_header = ttk.Frame(after_section)
        after_header.pack(fill=X, pady=(0, 5))
        
        ttk.Label(after_header, text="SESUDAH", font=("Segoe UI", 10, "bold"),
                  foreground="#6c757d").pack(side=LEFT)
        
        # Zoom controls on the right
        zoom_controls = ttk.Frame(after_header)
        zoom_controls.pack(side=RIGHT)
        
        self.zoom_label = ttk.Label(zoom_controls, text="🔍 100%", font=("Segoe UI", 8),
                                     foreground="#6c757d")
        self.zoom_label.pack(side=LEFT, padx=(0, 5))
        
        self.btn_reset_zoom = ttk.Button(zoom_controls, text="⟳", width=2,
                                          bootstyle="secondary-outline",
                                          command=self.reset_zoom, state="disabled")
        self.btn_reset_zoom.pack(side=LEFT)
        
        # Border frame for After canvas
        after_border = ttk.Frame(after_section)
        after_border.pack(fill=BOTH, expand=True)
        
        self.canvas_after = tk.Canvas(after_border, width=280, height=280, 
                                       bg="white", highlightthickness=2,
                                       highlightbackground="#dee2e6", cursor="crosshair")
        self.canvas_after.pack(fill=BOTH, expand=True, padx=2, pady=2)
        
        # Bind zoom and pan events
        self.canvas_after.bind("<MouseWheel>", self.on_after_zoom)
        self.canvas_after.bind("<ButtonPress-1>", self.on_after_drag_start)
        self.canvas_after.bind("<B1-Motion>", self.on_after_drag)
        self.canvas_after.bind("<ButtonRelease-1>", self.on_after_drag_end)
        self.canvas_after.bind("<Double-Button-1>", lambda e: self.reset_zoom())
        
        # Placeholder text on After canvas
        self.canvas_after.create_text(140, 140, text="Hasil akan muncul di sini",
                                       fill="#adb5bd", font=("Segoe UI", 11))
        
        # Action buttons
        action_frame = ttk.Frame(left_frame)
        action_frame.pack(fill=X, pady=(15, 0))
        
        self.btn_process = ttk.Button(action_frame, text="▶ Proses", bootstyle="info",
                                       command=self.process_single_image, state="disabled")
        self.btn_process.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
        
        self.btn_save = ttk.Button(action_frame, text="💾 Simpan Hasil", bootstyle="warning",
                                    command=self.save_single_result, state="disabled")
        self.btn_save.pack(side=LEFT, fill=X, expand=True, padx=5)
        
        self.btn_reset = ttk.Button(action_frame, text="🔄 Reset", bootstyle="danger",
                                     command=self.reset_after_canvas)
        self.btn_reset.pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
        
        # === RIGHT SIDE: Controls ===
        right_frame = ttk.Frame(main_pane, width=260)
        right_frame.pack(side=RIGHT, fill=Y)
        right_frame.pack_propagate(False)
        
        # AI Model card
        model_card = ttk.Labelframe(right_frame, text="🤖 AI Model", padding=12)
        model_card.pack(fill=X, pady=(0, 10))
        
        ttk.Label(model_card, text="Pilih Model", font=("Segoe UI", 9)).pack(anchor=W, pady=(0, 5))
        
        model_select_row = ttk.Frame(model_card)
        model_select_row.pack(fill=X, pady=(0, 10))
        
        self.single_model_combo = ttk.Combobox(model_select_row, textvariable=self.selected_model,
                                                values=list(self.models.keys()), state="readonly")
        self.single_model_combo.pack(side=LEFT, fill=X, expand=True)
        self.single_model_combo.bind("<<ComboboxSelected>>", self.on_model_change)
        
        ttk.Button(model_select_row, text="ⓘ", width=3, bootstyle="info-outline",
                   command=self.show_model_info).pack(side=RIGHT, padx=(5, 0))
        
        # Model info box with light blue background
        info_container = tk.Frame(model_card, bg="#d4edfc", padx=10, pady=10)
        info_container.pack(fill=X)
        
        # Info icon + text
        info_inner = tk.Frame(info_container, bg="#d4edfc")
        info_inner.pack(fill=X)
        
        tk.Label(info_inner, text="ℹ", font=("Segoe UI", 12), fg="#0d6efd", 
                 bg="#d4edfc").pack(side=LEFT, padx=(0, 8))
        
        single_model_info = self.models.get(self.selected_model.get(), ("", ""))
        self.single_model_desc = tk.Label(info_inner, text=single_model_info[1],
                                           wraplength=200, font=("Segoe UI", 9), 
                                           fg="#0d6efd", bg="#d4edfc", justify=LEFT)
        self.single_model_desc.pack(side=LEFT, fill=X, expand=True)
        
        # Alpha Matting checkbox
        matting_card = ttk.Frame(right_frame)
        matting_card.pack(fill=X, pady=(0, 10))
        
        self.single_matting_check = ttk.Checkbutton(
            matting_card,
            text="✨ Perhalus (hapus tepi kehitaman)",
            variable=self.alpha_matting,
            bootstyle="success-round-toggle"
        )
        self.single_matting_check.pack(side=LEFT)
        
        # Status card
        status_card = ttk.Labelframe(right_frame, text="Status", padding=12)
        status_card.pack(fill=X, pady=(0, 10))
        
        status_row = ttk.Frame(status_card)
        status_row.pack(fill=X)
        ttk.Label(status_row, text="Status", font=("Segoe UI", 9)).pack(side=LEFT)
        self.single_status = ttk.Label(status_row, text="Siap untuk mulai...", 
                                        foreground="#20c997", font=("Segoe UI", 9))
        self.single_status.pack(side=RIGHT)
        
        self.single_progress = ttk.Progressbar(status_card, bootstyle="info-striped",
                                                mode="indeterminate", length=200)
        self.single_progress.pack(fill=X, pady=(10, 0))
        
        # Application Log card
        log_card = ttk.Labelframe(right_frame, text="📋 Application Log", padding=10)
        log_card.pack(fill=BOTH, expand=True)
        
        log_header = ttk.Frame(log_card)
        log_header.pack(fill=X)
        ttk.Button(log_header, text="Clear", bootstyle="link",
                   command=self.clear_log).pack(side=RIGHT)
        
        self.single_log = tk.Text(log_card, height=8, font=("Consolas", 8), wrap="word")
        self.single_log.pack(fill=BOTH, expand=True, pady=(5, 0))

    def switch_mode(self, mode):
        """Switch between Bulk and Single mode"""
        self.mode.set(mode)
        
        if mode == "bulk":
            self.btn_bulk.configure(bootstyle="success")
            self.btn_single.configure(bootstyle="secondary-outline")
            self.frame_single.pack_forget()
            self.frame_bulk.pack(fill=BOTH, expand=True)
        else:
            self.btn_bulk.configure(bootstyle="secondary-outline")
            self.btn_single.configure(bootstyle="success")
            self.frame_bulk.pack_forget()
            self.frame_single.pack(fill=BOTH, expand=True)

    def toggle_theme(self):
        """Toggle between light and dark mode"""
        self.is_dark_mode = not self.is_dark_mode
        
        if self.is_dark_mode:
            # Switch to dark mode
            self.root.style.theme_use(self.dark_theme)
            self.btn_theme.configure(text="☀️")
            
            # Update canvas colors for dark mode
            canvas_bg = "#2b3035"
            border_color = "#495057"
            text_color = "#adb5bd"
            info_bg = "#1a3a4d"
            info_fg = "#6bb9f0"
        else:
            # Switch to light mode
            self.root.style.theme_use(self.light_theme)
            self.btn_theme.configure(text="🌙")
            
            # Update canvas colors for light mode
            canvas_bg = "white"
            border_color = "#0dcaf0"
            text_color = "#adb5bd"
            info_bg = "#d4edfc"
            info_fg = "#0d6efd"
        
        # Update canvas backgrounds
        if hasattr(self, 'canvas_before'):
            self.canvas_before.configure(bg=canvas_bg, highlightbackground=border_color)
        if hasattr(self, 'canvas_after'):
            self.canvas_after.configure(bg=canvas_bg, highlightbackground="#dee2e6" if not self.is_dark_mode else "#495057")
            # Redraw placeholder if empty
            if not self.single_output_data:
                self.canvas_after.delete("all")
                self.canvas_after.create_text(140, 140, text="Hasil akan muncul di sini",
                                               fill=text_color, font=("Segoe UI", 11))
        
        # Update info box colors
        if hasattr(self, 'single_model_desc') and hasattr(self.single_model_desc, 'master'):
            try:
                info_container = self.single_model_desc.master.master
                info_container.configure(bg=info_bg)
                self.single_model_desc.master.configure(bg=info_bg)
                self.single_model_desc.configure(bg=info_bg, fg=info_fg)
                # Update info icon
                for widget in self.single_model_desc.master.winfo_children():
                    if isinstance(widget, tk.Label) and widget != self.single_model_desc:
                        widget.configure(bg=info_bg, fg=info_fg)
            except:
                pass

    def on_low_pc_toggle(self):
        """Handle Low PC Mode toggle"""
        if self.low_pc_mode.get():
            # Enable low PC mode - switch to lightweight model
            self.selected_model.set("Silueta")  # Use display name
            self.on_model_change()
            self.log_message("[INFO] Mode Hemat AKTIF - Model diubah ke silueta (ringan)")
            self.log_message("[INFO] Gambar besar akan di-resize untuk hemat memori")
        else:
            self.log_message("[INFO] Mode Hemat NONAKTIF")
    
    def on_device_change(self, event=None):
        """Handle device selection change"""
        device = self.selected_device.get()
        self.log_message(f"[INFO] Device diubah ke: {device}")
        self.update_device_description()

    def update_device_description(self):
        """Update the advantage description label"""
        device = self.selected_device.get()
        if device.startswith("GPU"):
            desc = "🚀 Super Cepat - Performa Maksimal"
        else:
            desc = "⚖️ Stabil - Kompatibilitas Tinggi"
            
        if hasattr(self, 'device_info_label'):
            self.device_info_label.configure(text=desc)

    def resize_for_low_pc(self, image_data):
        """Resize image if Low PC Mode is enabled and image is too large"""
        if not self.low_pc_mode.get():
            return image_data
        
        try:
            img = Image.open(io.BytesIO(image_data))
            width, height = img.size
            
            # Check if resize is needed
            if width <= self.max_image_size and height <= self.max_image_size:
                return image_data
            
            # Calculate new dimensions maintaining aspect ratio
            if width > height:
                new_width = self.max_image_size
                new_height = int(height * (self.max_image_size / width))
            else:
                new_height = self.max_image_size
                new_width = int(width * (self.max_image_size / height))
            
            # Resize image
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert back to bytes
            buffer = io.BytesIO()
            img_resized.save(buffer, format='PNG')
            resized_data = buffer.getvalue()
            
            self.log_message(f"[INFO] Gambar di-resize: {width}x{height} → {new_width}x{new_height}")
            return resized_data
        except Exception as e:
            self.log_message(f"[WARN] Gagal resize: {str(e)}")
            return image_data

    def get_internal_model_name(self, display_name):
        """Get internal model name from display name"""
        model_info = self.models.get(display_name, (display_name, ""))
        return model_info[0]  # Return internal name
    
    def get_model_description(self, display_name):
        """Get model description from display name"""
        model_info = self.models.get(display_name, ("", ""))
        return model_info[1]  # Return description

    def on_model_change(self, event=None):
        """Update description when model changes"""
        display_name = self.selected_model.get()
        desc = self.get_model_description(display_name)
        
        # Update bulk model description (ttk.Label)
        if hasattr(self, 'bulk_model_desc'):
            self.bulk_model_desc.configure(text=desc)
        # Update single model description (tk.Label)
        if hasattr(self, 'single_model_desc'):
            self.single_model_desc.config(text=desc)
        
        internal_name = self.get_internal_model_name(display_name)
        self.log_message(f"[INFO] Model changed to: {display_name} ({internal_name})")


    def show_model_info(self):
        """Show all models information"""
        info_text = "--- Daftar Model AI ---\n\n"
        for display_name, (internal_name, desc) in self.models.items():
            info_text += f"• {display_name}\n  {desc}\n\n"
        info_text += "TIPS:\n"
        info_text += "• Untuk foto orang: Human atau AI PREMIUM Portrait\n"
        info_text += "• Untuk anime: IsAnime\n"
        info_text += "• Untuk kecepatan: Lite atau Silueta\n"
        info_text += "• Untuk akurasi: AI PREMIUM Massive\n"
        messagebox.showinfo("Informasi Model", info_text)

    def select_input_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_folder.set(folder)

    def select_output_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder.set(folder)

    def apply_alpha_matting(self, image_data):
        """Apply alpha matting to remove dark fringe from edges"""
        if not self.alpha_matting.get():
            return image_data
        
        try:
            import numpy as np
            from scipy import ndimage
            
            img = Image.open(io.BytesIO(image_data))
            if img.mode != 'RGBA':
                return image_data
            
            img_array = np.array(img, dtype=np.float32)
            r, g, b, a = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2], img_array[:,:,3]
            
            # Step 1: Un-premultiply alpha to recover true colors
            alpha_safe = np.maximum(a, 1)
            semi_trans = (a > 0) & (a < 255)
            r[semi_trans] = np.clip(r[semi_trans] * 255.0 / alpha_safe[semi_trans], 0, 255)
            g[semi_trans] = np.clip(g[semi_trans] * 255.0 / alpha_safe[semi_trans], 0, 255)
            b[semi_trans] = np.clip(b[semi_trans] * 255.0 / alpha_safe[semi_trans], 0, 255)
            
            # Step 2: Iterative color push from interior to edges
            for _ in range(5):
                edge_mask = (a > 5) & (a < 250)
                if not np.any(edge_mask):
                    break
                
                weight = a / 255.0
                r_weighted = r * weight
                g_weighted = g * weight
                b_weighted = b * weight
                
                r_exp = ndimage.maximum_filter(r_weighted, size=3)
                g_exp = ndimage.maximum_filter(g_weighted, size=3)
                b_exp = ndimage.maximum_filter(b_weighted, size=3)
                w_exp = ndimage.maximum_filter(weight, size=3)
                
                w_safe = np.maximum(w_exp, 0.01)
                r[edge_mask] = r[edge_mask] * 0.3 + (r_exp[edge_mask] / w_safe[edge_mask]) * 0.7
                g[edge_mask] = g[edge_mask] * 0.3 + (g_exp[edge_mask] / w_safe[edge_mask]) * 0.7
                b[edge_mask] = b[edge_mask] * 0.3 + (b_exp[edge_mask] / w_safe[edge_mask]) * 0.7
            
            # Step 3: Brightness boost for remaining dark edges
            edge_band = (a > 5) & (a < 240)
            interior = a >= 240
            if np.any(edge_band) and np.any(interior):
                brightness = 0.299 * r + 0.587 * g + 0.114 * b
                interior_bright = np.median(brightness[interior])
                dark_edges = edge_band & (brightness < interior_bright * 0.5)
                if np.any(dark_edges):
                    boost = np.clip(interior_bright * 0.7 / np.maximum(brightness[dark_edges], 1), 1, 2)
                    r[dark_edges] = np.clip(r[dark_edges] * boost, 0, 255)
                    g[dark_edges] = np.clip(g[dark_edges] * boost, 0, 255)
                    b[dark_edges] = np.clip(b[dark_edges] * boost, 0, 255)
            
            img_array[:,:,0] = np.clip(r, 0, 255)
            img_array[:,:,1] = np.clip(g, 0, 255)
            img_array[:,:,2] = np.clip(b, 0, 255)
            
            result = Image.fromarray(img_array.astype(np.uint8))
            buffer = io.BytesIO()
            result.save(buffer, format='PNG')
            
            self.log_message("[INFO] Alpha Matting applied")
            return buffer.getvalue()
            
        except ImportError:
            self.log_message("[WARN] scipy tidak tersedia untuk Alpha Matting")
            return image_data
        except Exception as e:
            self.log_message(f"[WARN] Alpha Matting gagal: {str(e)}")
            return image_data

    def select_single_image(self):
        """Select a single image for processing"""
        filetypes = [("Image files", "*.jpg *.jpeg *.png *.webp"), ("All files", "*.*")]
        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if filepath:
            self.single_input_path = filepath
            self.single_output_data = None
            self.single_filename.set(os.path.basename(filepath))
            
            # Display before image
            self.display_image_on_canvas(filepath, self.canvas_before)
            
            # Clear after canvas
            self.canvas_after.delete("all")
            self.canvas_after.create_text(125, 125, text="Hasil akan muncul di sini",
                                          fill="gray", font=("Segoe UI", 10))
            
            self.btn_process.configure(state="normal")
            self.btn_save.configure(state="disabled")
            self.log_message(f"[INFO] Gambar dipilih: {os.path.basename(filepath)}")

    def display_image_on_canvas(self, image_source, canvas, is_bytes=False):
        """Display image on canvas, resized to fit"""
        try:
            if is_bytes:
                img = Image.open(io.BytesIO(image_source))
            else:
                img = Image.open(image_source)
            
            # Store original image for zoom (only for after canvas)
            if canvas == self.canvas_after:
                self.after_original_img = img.copy()
                self.after_zoom_level = 1.0
                self.after_pan_x = 0
                self.after_pan_y = 0
                self.zoom_label.configure(text="🔍 100%")
                self.btn_reset_zoom.configure(state="disabled")
            
            # Get canvas size
            canvas.update()
            canvas_w = canvas.winfo_width() or 250
            canvas_h = canvas.winfo_height() or 250
            
            # Calculate scale
            img_w, img_h = img.size
            scale = min(canvas_w / img_w, canvas_h / img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            
            img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_resized)
            
            if canvas == self.canvas_before:
                self.before_photo = photo
            else:
                self.after_photo = photo
            
            canvas.delete("all")
            x = canvas_w // 2
            y = canvas_h // 2
            canvas.create_image(x, y, anchor="center", image=photo)
            
        except Exception as e:
            self.log_message(f"[ERROR] Tampilkan gambar: {str(e)}")

    def process_single_image(self):
        """Process single image"""
        if not self.single_input_path:
            messagebox.showwarning("Warning!", "Tolong pilih gambar terlebih dahulu!")
            return
        
        self.btn_process.configure(state="disabled", text="Processing...")
        self.btn_save.configure(state="disabled")
        self.single_progress.start()
        self.single_status.configure(text="Processing...", foreground="#0dcaf0")
        
        threading.Thread(target=self._process_single_thread, daemon=True).start()

    def _process_single_thread(self):
        """Thread worker for single image processing"""
        try:
            display_name = self.selected_model.get()
            model_name = self.get_internal_model_name(display_name)  # Get internal name for rembg
            
            # Check if model might need downloading (first time use)
            self.root.after(0, lambda: self.log_message(f"[LOAD] Memuat model AI: {display_name}..."))
            self.root.after(0, lambda: self.log_message("[INFO] Jika pertama kali, model akan didownload (~150-300MB). Mohon tunggu..."))
            
            self.set_device_mode()  # Set CPU/GPU mode
            sess_opts = ort.SessionOptions()
            session = new_session(model_name, sess_opts)
            
            self.root.after(0, lambda: self.log_message(f"[OK] Model {display_name} berhasil dimuat!"))
            
            # Check actual provider used and VRAM
            actual_providers = session.inner_session.get_providers()
            vram_msg = ""
            if "CUDAExecutionProvider" in actual_providers:
                try:
                    import torch
                    if torch.cuda.is_available():
                        free_mem, total_mem = torch.cuda.mem_get_info()
                        vram_msg = f" | VRAM: {(total_mem - free_mem) // (1024**2)}MB/{(total_mem) // (1024**2)}MB"
                except: pass
            
            used_provider = "GPU" if any("CUDA" in p or "TensorRT" in p for p in actual_providers) else "CPU"
            self.root.after(0, lambda: self.log_message(f"[INFO] Provider: {actual_providers[0]} ({used_provider}){vram_msg}"))
            
            with open(self.single_input_path, 'rb') as f:
                input_data = f.read()
            
            # Resize if Low PC Mode is enabled
            input_data = self.resize_for_low_pc(input_data)
            
            output_data = remove(input_data, session=session)
            
            # Apply alpha matting if enabled
            output_data = self.apply_alpha_matting(output_data)
            
            self.single_output_data = output_data
            
            # Display result
            def show_result(data=output_data):
                self.display_image_on_canvas(data, self.canvas_after, is_bytes=True)
            
            self.root.after(0, show_result)
            self.root.after(0, lambda: self.log_message("[OK] Gambar berhasil diproses!"))
            self.root.after(0, lambda: self.btn_save.configure(state="normal"))
            self.root.after(0, lambda: self.single_status.configure(text="Selesai!", foreground="#20c997"))
            
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"[ERROR] {str(e)}"))
            self.root.after(0, lambda: messagebox.showerror("Error", f"Processing failed:\n{str(e)}"))
            self.root.after(0, lambda: self.single_status.configure(text="Error!", foreground="#dc3545"))
        
        finally:
            self.root.after(0, lambda: self.btn_process.configure(state="normal", text="▶ Proses"))
            self.root.after(0, lambda: self.single_progress.stop())

    def save_single_result(self):
        """Save single image result"""
        if not self.single_output_data:
            messagebox.showwarning("Warning", "No result to save!")
            return
        
        original_name = os.path.splitext(os.path.basename(self.single_input_path))[0]
        default_name = f"{original_name}_nobg.png"
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png")],
            initialfile=default_name
        )
        
        if filepath:
            try:
                with open(filepath, 'wb') as f:
                    f.write(self.single_output_data)
                self.log_message(f"[OK] Tersimpan: {filepath}")
                messagebox.showinfo("Success", f"Image saved:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Save failed:\n{str(e)}")

    def reset_after_canvas(self):
        """Reset after canvas"""
        self.canvas_after.delete("all")
        self.canvas_after.create_text(125, 125, text="Hasil akan muncul di sini",
                                       fill="gray", font=("Segoe UI", 10))
        self.after_photo = None
        self.single_output_data = None
        self.after_original_img = None
        self.after_zoom_level = 1.0
        self.after_pan_x = 0
        self.after_pan_y = 0
        self.zoom_label.configure(text="🔍 100%")
        self.btn_reset_zoom.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        self.log_message("[INFO] Canvas direset.")

    def reset_zoom(self):
        """Reset zoom to 100%"""
        if not self.after_original_img:
            return
        self.after_zoom_level = 1.0
        self.after_pan_x = 0
        self.after_pan_y = 0
        self.zoom_label.configure(text="🔍 100%")
        self.btn_reset_zoom.configure(state="disabled")
        self.render_after_zoomed()
        self.log_message("[INFO] Zoom direset ke 100%")

    def on_after_zoom(self, event):
        """Handle mouse wheel zoom on after canvas"""
        if not self.after_original_img:
            return
        
        # Get mouse position relative to canvas
        canvas_w = self.canvas_after.winfo_width()
        canvas_h = self.canvas_after.winfo_height()
        mouse_x = event.x / canvas_w - 0.5
        mouse_y = event.y / canvas_h - 0.5
        
        # Calculate zoom change
        old_zoom = self.after_zoom_level
        if event.delta > 0:
            self.after_zoom_level = min(10.0, self.after_zoom_level * 1.2)
        else:
            self.after_zoom_level = max(0.5, self.after_zoom_level / 1.2)
        
        # Adjust pan to keep mouse position stable
        zoom_ratio = self.after_zoom_level / old_zoom
        self.after_pan_x = self.after_pan_x * zoom_ratio + mouse_x * (1 - zoom_ratio) * canvas_w
        self.after_pan_y = self.after_pan_y * zoom_ratio + mouse_y * (1 - zoom_ratio) * canvas_h
        
        # Update zoom label and button
        zoom_percent = int(self.after_zoom_level * 100)
        self.zoom_label.configure(text=f"🔍 {zoom_percent}%")
        
        if abs(self.after_zoom_level - 1.0) < 0.01 and abs(self.after_pan_x) < 1 and abs(self.after_pan_y) < 1:
            self.btn_reset_zoom.configure(state="disabled")
        else:
            self.btn_reset_zoom.configure(state="normal")
        
        self.render_after_zoomed()

    def on_after_drag_start(self, event):
        """Start dragging to pan"""
        if not self.after_original_img:
            return
        self.after_drag_start = (event.x, event.y)
        self.canvas_after.configure(cursor="fleur")

    def on_after_drag(self, event):
        """Handle drag to pan"""
        if not self.after_original_img or not self.after_drag_start:
            return
        
        dx = event.x - self.after_drag_start[0]
        dy = event.y - self.after_drag_start[1]
        
        self.after_pan_x += dx
        self.after_pan_y += dy
        self.after_drag_start = (event.x, event.y)
        
        # Enable reset button if panned
        if abs(self.after_pan_x) > 1 or abs(self.after_pan_y) > 1 or abs(self.after_zoom_level - 1.0) > 0.01:
            self.btn_reset_zoom.configure(state="normal")
        
        self.render_after_zoomed()

    def on_after_drag_end(self, event):
        """End dragging"""
        self.after_drag_start = None
        self.canvas_after.configure(cursor="crosshair")

    def render_after_zoomed(self):
        """Render the after image with current zoom and pan"""
        if not self.after_original_img:
            return
        
        try:
            # Get canvas size
            self.canvas_after.update()
            canvas_w = self.canvas_after.winfo_width() or 280
            canvas_h = self.canvas_after.winfo_height() or 280
            
            # Get original image
            img = self.after_original_img.copy()
            img_w, img_h = img.size
            
            # Calculate base scale (fit to canvas)
            base_scale = min(canvas_w / img_w, canvas_h / img_h)
            
            # Apply zoom
            final_scale = base_scale * self.after_zoom_level
            new_w = int(img_w * final_scale)
            new_h = int(img_h * final_scale)
            
            # Resize image
            img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # Calculate position with pan
            x = canvas_w // 2 + int(self.after_pan_x)
            y = canvas_h // 2 + int(self.after_pan_y)
            
            # Create photo and display
            photo = ImageTk.PhotoImage(img_resized)
            self.after_photo = photo
            
            self.canvas_after.delete("all")
            self.canvas_after.create_image(x, y, anchor="center", image=photo)
            
        except Exception as e:
            self.log_message(f"[ERROR] Render zoom: {str(e)}")

    def log_message(self, message):
        """Add message to log with colors"""
        # Configure tags if not done yet
        def setup_tags(text_widget):
            text_widget.tag_configure("ok", foreground="#28a745")      # Green
            text_widget.tag_configure("info", foreground="#6c757d")    # Gray
            text_widget.tag_configure("load", foreground="#fd7e14")    # Orange
            text_widget.tag_configure("error", foreground="#dc3545")   # Red
            text_widget.tag_configure("warn", foreground="#dc3545")    # Red
            text_widget.tag_configure("sys", foreground="#6c757d")     # Gray
        
        # Determine tag based on message prefix
        tag = None
        if "[OK]" in message:
            tag = "ok"
        elif "[INFO]" in message:
            tag = "info"
        elif "[LOAD]" in message:
            tag = "load"
        elif "[ERROR]" in message:
            tag = "error"
        elif "[WARN]" in message:
            tag = "warn"
        elif "[SYS]" in message:
            tag = "sys"
        
        # Add to bulk log
        if hasattr(self, 'log_text'):
            setup_tags(self.log_text)
            if tag:
                self.log_text.insert("end", message + "\n", tag)
            else:
                self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
        
        # Add to single log
        if hasattr(self, 'single_log'):
            setup_tags(self.single_log)
            if tag:
                self.single_log.insert("end", message + "\n", tag)
            else:
                self.single_log.insert("end", message + "\n")
            self.single_log.see("end")

    def clear_log(self):
        """Clear all logs"""
        if hasattr(self, 'log_text'):
            self.log_text.delete("1.0", "end")
        if hasattr(self, 'single_log'):
            self.single_log.delete("1.0", "end")

    def stop_thread(self):
        """Stop processing"""
        if self.is_processing:
            if messagebox.askyesno("Konfirmasi Hentikan", "Yakin ingin menghentikan proses?"):
                self.stop_flag = True
                self.log_message("[WARN] Proses dihentikan oleh user. Menunggu file selesai...")
                self.btn_stop.configure(text="Stopping...", state="disabled")

    def start_thread(self):
        """Start bulk processing"""
        if not self.input_folder.get() or not self.output_folder.get():
            messagebox.showwarning("Warning!", "Tolong pilih folder input dan output!")
            return
        
        if self.is_processing:
            return

        self.is_processing = True
        self.stop_flag = False
        
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal", text="⬛ STOP")
        
        self.clear_log()
        threading.Thread(target=self.process_images, daemon=True).start()

    def process_images(self):
        """Bulk process images"""
        try:
            input_dir = self.input_folder.get()
            output_dir = self.output_folder.get()

            valid_ext = ('.jpg', '.jpeg', '.png', '.webp')
            files = [f for f in os.listdir(input_dir) if f.lower().endswith(valid_ext)]
            
            if not files:
                self.root.after(0, lambda: messagebox.showinfo("Info", "No images in input folder."))
                self.reset_ui()
                return

            self.root.after(0, lambda: self.progress_bar.configure(maximum=len(files), value=0))
            
            display_name = self.selected_model.get()
            model_name = self.get_internal_model_name(display_name)  # Get internal name
            device = self.selected_device.get()
            self.log_message(f"[LOAD] Memuat model AI: {display_name} ({device})...")
            self.set_device_mode()  # Set CPU/GPU mode
            sess_opts = ort.SessionOptions()
            session = new_session(model_name, sess_opts)
            
            actual_providers = session.inner_session.get_providers()
            used_provider = "GPU" if any("CUDA" in p or "TensorRT" in p for p in actual_providers) else "CPU"
            self.log_message(f"[INFO] Model siap. Provider aktif: {actual_providers[0] if actual_providers else 'Unknown'} ({used_provider})")

            success_count = 0
            
            for index, filename in enumerate(files):
                if self.stop_flag:
                    self.log_message("[WARN] >>> PROSES DIHENTIKAN OLEH USER <<<")
                    break
                
                try:
                    input_path = os.path.join(input_dir, filename)
                    output_filename = os.path.splitext(filename)[0] + ".png"
                    output_path = os.path.join(output_dir, output_filename)

                    self.root.after(0, lambda m=f"Processing [{index+1}/{len(files)}]: {filename}": 
                                    self.status_label.configure(text=m))

                    with open(input_path, 'rb') as i:
                        input_data = i.read()
                        # Resize if Low PC Mode is enabled
                        input_data = self.resize_for_low_pc(input_data)
                        output_data = remove(input_data, session=session)
                        # Apply alpha matting if enabled
                        output_data = self.apply_alpha_matting(output_data)

                    with open(output_path, 'wb') as o:
                        o.write(output_data)

                    success_count += 1
                    self.root.after(0, lambda m=f"[OK] {filename}": self.log_message(m))

                except Exception as e:
                    self.root.after(0, lambda m=f"[ERROR] {filename}: {str(e)}": self.log_message(m))

                self.root.after(0, lambda v=index+1: self.progress_bar.configure(value=v))

            if self.stop_flag:
                self.root.after(0, lambda: messagebox.showwarning("Dihentikan", 
                    f"Proses dihentikan.\nSelesai: {success_count} dari {len(files)}"))
            else:
                self.root.after(0, lambda: messagebox.showinfo("Selesai", 
                    f"Berhasil: {success_count} / {len(files)}"))
        
        except Exception as global_e:
            self.root.after(0, lambda: messagebox.showerror("Critical Error", 
                f"Fatal error:\n{str(global_e)}"))
        
        finally:
            self.reset_ui()

    def reset_ui(self):
        """Reset UI after processing"""
        self.is_processing = False
        self.stop_flag = False
        self.root.after(0, lambda: self.btn_start.configure(state="normal", text="▶ MULAI PROSES"))
        self.root.after(0, lambda: self.btn_stop.configure(state="disabled", text="⬛ STOP"))
        self.root.after(0, lambda: self.status_label.configure(text="Siap memulai..."))
        self.root.after(0, lambda: self.progress_bar.configure(value=0))

    # ==================== UPDATE METHODS ====================
    
    def check_for_updates(self):
        """Check for available updates."""
        if not UPDATER_AVAILABLE:
            messagebox.showwarning("Update", "Modul updater tidak tersedia.")
            return
        
        self.log_message("[INFO] Memeriksa update...")
        self.btn_update.configure(state="disabled", text="⏳")
        
        def check_thread():
            try:
                updater = Updater(UPDATE_VERSION_URL, APP_VERSION)
                has_update, info = updater.check_for_updates()
                
                self.root.after(0, lambda: self.btn_update.configure(state="normal", text="🔄"))
                
                if has_update:
                    self.root.after(0, lambda: self.show_update_dialog(info, updater))
                else:
                    self.root.after(0, lambda: self.log_message("[INFO] Aplikasi sudah versi terbaru."))
                    self.root.after(0, lambda: messagebox.showinfo("Update", 
                        f"Anda sudah menggunakan versi terbaru (v{APP_VERSION})."))
            except Exception as e:
                self.root.after(0, lambda: self.btn_update.configure(state="normal", text="🔄"))
                self.root.after(0, lambda: self.log_message(f"[ERROR] Gagal memeriksa update: {e}"))
                self.root.after(0, lambda: messagebox.showerror("Error", 
                    f"Gagal memeriksa update:\n{str(e)}"))
        
        threading.Thread(target=check_thread, daemon=True).start()
    
    def show_update_dialog(self, info: dict, updater):
        """Show update available dialog."""
        new_version = info.get('version', 'Unknown')
        changelog = info.get('changelog', 'No changelog.')
        
        message = (
            f"Versi baru tersedia!\n\n"
            f"Versi saat ini: v{APP_VERSION}\n"
            f"Versi terbaru: v{new_version}\n\n"
            f"Changelog:\n{changelog}\n\n"
            f"Apakah Anda ingin mengunduh dan menginstall update sekarang?"
        )
        
        if messagebox.askyesno("Update Tersedia", message):
            self.start_update(info, updater)
    
    def start_update(self, update_info: dict, updater):
        """Start downloading and installing the update."""
        self.log_message("[INFO] Mengunduh update...")
        
        # Create progress dialog
        self.update_dialog = tk.Toplevel(self.root)
        self.update_dialog.title("Mengunduh Update")
        self.update_dialog.geometry("400x150")
        self.update_dialog.resizable(False, False)
        self.update_dialog.transient(self.root)
        self.update_dialog.grab_set()
        
        # Center the dialog
        self.update_dialog.update_idletasks()
        x = (self.update_dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.update_dialog.winfo_screenheight() // 2) - (150 // 2)
        self.update_dialog.geometry(f"+{x}+{y}")
        
        frame = ttk.Frame(self.update_dialog, padding=20)
        frame.pack(fill=BOTH, expand=True)
        
        ttk.Label(frame, text="Mengunduh update...", font=("Segoe UI", 11)).pack(pady=(0, 10))
        
        self.update_progress = ttk.Progressbar(frame, bootstyle="info-striped", 
                                                mode="determinate", length=350)
        self.update_progress.pack(pady=5)
        
        self.update_label = ttk.Label(frame, text="0%", font=("Segoe UI", 9))
        self.update_label.pack()
        
        btn_cancel = ttk.Button(frame, text="Batal", bootstyle="danger-outline",
                                 command=lambda: self.cancel_update(updater))
        btn_cancel.pack(pady=(10, 0))
        
        # Store updater reference and update info
        self._current_updater = updater
        self._current_update_info = update_info
        
        # Start async download with delta update support
        updater.download_and_apply_async(
            update_info,
            use_delta=True,  # Try delta update first
            progress_callback=self.on_download_progress,
            complete_callback=self.on_download_complete,
            error_callback=self.on_download_error
        )
    
    def on_download_progress(self, downloaded: int, total: int):
        """Update download progress."""
        if total > 0:
            percent = int((downloaded / total) * 100)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            
            self.root.after(0, lambda: self.update_progress.configure(value=percent))
            self.root.after(0, lambda: self.update_label.configure(
                text=f"{percent}% ({mb_downloaded:.1f} MB / {mb_total:.1f} MB)"))
    
    def on_download_complete(self, path: str, is_full: bool = False):
        """Handle download completion."""
        self.root.after(0, lambda: self.update_dialog.destroy())
        
        update_type = "full" if is_full else "delta (hanya file yang berubah)"
        self.log_message(f"[INFO] Download {update_type} selesai: {path}")
        
        if messagebox.askyesno("Update", 
            f"Download selesai!\n\nTipe update: {update_type}\n\nAplikasi akan ditutup dan diperbarui.\nLanjutkan?"):
            self._current_updater.apply_update(path, is_full)
        else:
            self.log_message("[INFO] Update dibatalkan oleh user.")
    
    def on_download_error(self, error_msg: str):
        """Handle download error."""
        self.root.after(0, lambda: self.update_dialog.destroy())
        self.log_message(f"[ERROR] Download gagal: {error_msg}")
        self.root.after(0, lambda: messagebox.showerror("Error", 
            f"Gagal mengunduh update:\n{error_msg}"))
    
    def cancel_update(self, updater):
        """Cancel ongoing update."""
        updater.cancel_download()
        self.update_dialog.destroy()
        self.log_message("[INFO] Download dibatalkan.")

if __name__ == "__main__":
    # Track if user just activated license (to skip splash)
    _just_activated = False
    
    # Helper function to load app icon
    def get_app_icon_path():
        return os.path.join(os.path.dirname(__file__), "icon.png")
    
    def set_window_icon(window):
        """Set application icon on a window."""
        try:
            icon_path = get_app_icon_path()
            if os.path.exists(icon_path):
                icon_image = Image.open(icon_path)
                icon_photo = ImageTk.PhotoImage(icon_image)
                window.iconphoto(True, icon_photo)
                # Keep reference to prevent garbage collection
                window._app_icon = icon_photo
        except Exception as e:
            print(f"[WARN] Could not set icon: {e}")
    
    # === 1. LICENSE CHECK FIRST ===
    try:
        from license_manager import LicenseManager
        from license_dialog import LicenseDialog
        
        lm = LicenseManager()
        is_valid, msg = lm.is_licensed()
        
        if not is_valid:
            # Show license dialog (creates its own window)
            dialog = LicenseDialog(parent=None)
            result = dialog.show()
            
            if not result:
                sys.exit(0)
            
            # User just activated, skip splash to avoid Tkinter conflicts
            _just_activated = True
                
    except ImportError as e:
        print(f"[WARN] License module not found: {e}")
    except Exception as e:
        print(f"[WARN] License check error: {e}")
    
    # === 2. SPLASH SCREEN (Only shown if NOT just activated) ===
    if not _just_activated:
        def show_splash():
            splash = tk.Tk()
            splash.overrideredirect(True)
            
            # Set icon
            try:
                icon_path = get_app_icon_path()
                if os.path.exists(icon_path):
                    icon_image = Image.open(icon_path)
                    icon_photo = ImageTk.PhotoImage(icon_image)
                    splash.iconphoto(True, icon_photo)
                    splash._icon = icon_photo
            except:
                pass
            
            screen_width = splash.winfo_screenwidth()
            screen_height = splash.winfo_screenheight()
            splash_width, splash_height = 600, 350
            x = (screen_width - splash_width) // 2
            y = (screen_height - splash_height) // 2
            splash.geometry(f"{splash_width}x{splash_height}+{x}+{y}")
            splash.configure(bg="white")
            
            try:
                splash_path = os.path.join(os.path.dirname(__file__), "splash.jpg")
                splash_img = Image.open(splash_path)
                splash_img = splash_img.resize((500, 200), Image.Resampling.LANCZOS)
                splash_photo = ImageTk.PhotoImage(splash_img)
                img_label = tk.Label(splash, image=splash_photo, bg="white")
                img_label.image = splash_photo
                img_label.pack(pady=(40, 20))
            except:
                tk.Label(splash, text="ZI Advanced Background Remover", 
                         font=("Segoe UI", 24, "bold"), fg="#2196F3", bg="white").pack(pady=60)
            
            tk.Label(splash, text="Memuat aplikasi...", font=("Segoe UI", 11), 
                     fg="#666", bg="white").pack(pady=10)
            
            progress_frame = tk.Frame(splash, bg="#e0e0e0", height=6, width=400)
            progress_frame.pack(pady=10)
            progress_frame.pack_propagate(False)
            progress_bar = tk.Frame(progress_frame, bg="#2196F3", height=6, width=0)
            progress_bar.place(x=0, y=0)
            
            tk.Label(splash, text=f"v{APP_VERSION} © 2026 ZI Advanced Background Remover", 
                     font=("Segoe UI", 8), fg="#999", bg="white").pack(side="bottom", pady=10)
            
            def animate(w=0):
                if w <= 400:
                    progress_bar.configure(width=w)
                    splash.after(8, lambda: animate(w + 5))
                else:
                    splash.destroy()
            
            animate()
            splash.mainloop()
        
        show_splash()
    
    # === 3. MAIN APP ===
    app = ttk.Window(themename="minty")
    set_window_icon(app)
    BackgroundRemoverApp(app)
    app.mainloop()
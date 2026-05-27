# ImageBatch 图速 v1.0 — 批量图片处理工具
import os
import sys

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageOps
import threading

try:
    from w32_drop import enable_drop
except ImportError:
    enable_drop = None

try:
    import operations
except ImportError:
    operations = None

APP_TITLE = "图速 ImageBatch"
APP_VERSION = "1.0"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 750
SUPPORTED_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif")


class ImageBatchApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(900, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.files = []
        self.images = {}
        self.current_preview = None
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        self._cancel_flag = False
        self._batch_log = []

        self.wm_select_mode = False
        self.wm_rect_start = None
        self.wm_rect_id = None
        self.wm_region = None
        self.wm_full_img_size = None
        self._thumb_cache = {}
        self._thumb_orig_sizes = {}

        self._build_ui()
        self._setup_dnd()

    def _build_ui(self):
        self._build_topbar()
        self._build_main_area()
        self._build_statusbar()

    def _build_topbar(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=(8, 0))

        ttk.Label(top, text=f"{APP_TITLE}", font=("Microsoft YaHei", 14, "bold")).pack(side="left")
        tk.Label(top, text=f"v{APP_VERSION}", fg="#999", font=("Microsoft YaHei", 9)).pack(side="left", padx=(6, 0))

    def _build_main_area(self):
        main_pane = ttk.PanedWindow(self.root, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=10, pady=8)

        left = self._build_left_panel()
        right = self._build_right_panel()

        main_pane.add(left, weight=1)
        main_pane.add(right, weight=2)

    def _build_left_panel(self):
        frame = ttk.Frame(self.root)

        self.drop_frame = tk.Frame(frame, bg="#e8e8e8", height=56, relief="ridge", bd=1)
        self.drop_frame.pack(fill="x")
        self.drop_frame.pack_propagate(False)

        self.drop_label = tk.Label(self.drop_frame, text="📁 拖拽图片到此处 或点击选择文件",
                                   bg="#e8e8e8", fg="#666", font=("Microsoft YaHei", 10))
        self.drop_label.pack(expand=True)
        self.drop_label.bind("<Button-1>", lambda e: self._add_files())
        self.drop_frame.bind("<Button-1>", lambda e: self._add_files())

        list_header = ttk.Frame(frame)
        list_header.pack(fill="x", pady=(10, 2))
        ttk.Label(list_header, text="文件列表", font=("Microsoft YaHei", 10, "bold")).pack(side="left")
        ttk.Label(list_header, text=f"({len(self.files)} 张)").pack(side="left")

        self.file_listbox = tk.Listbox(frame, selectmode="extended", font=("Microsoft YaHei", 9),
                                       activestyle="none", exportselection=False)
        self.file_listbox.pack(fill="both", expand=True)
        self.file_listbox.bind("<<ListboxSelect>>", self._on_file_select)

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="添加文件", command=self._add_files).pack(side="left")
        ttk.Button(btn_row, text="清空列表", command=self._clear_files).pack(side="left", padx=5)
        ttk.Button(btn_row, text="移除选中", command=self._remove_selected).pack(side="left")

        out_row = ttk.Frame(frame)
        out_row.pack(fill="x", pady=(10, 0))
        ttk.Label(out_row, text="输出目录:").pack(side="left")
        ttk.Entry(out_row, textvariable=self.output_dir, font=("Microsoft YaHei", 9)).pack(
            side="left", fill="x", expand=True, padx=5)
        ttk.Button(out_row, text="选择", command=self._choose_output_dir, width=6).pack(side="left")

        return frame

    def _build_right_panel(self):
        frame = ttk.Frame(self.root)

        self.op_notebook = ttk.Notebook(frame)
        self.op_notebook.pack(fill="x")

        self._build_compress_tab()
        self._build_resize_tab()
        self._build_dpi_tab()
        self._build_watermark_tab()
        self._build_convert_tab()
        self._build_border_tab()
        self._build_grid_tab()
        self._build_rmwatermark_tab()

        self.info_frame = ttk.LabelFrame(frame, text="文件详情", padding=3)
        self.info_frame.pack(fill="x", pady=(6, 0))
        self.info_text = tk.StringVar(value="请选择文件查看详情")
        tk.Label(self.info_frame, textvariable=self.info_text, fg="#555",
                 font=("Microsoft YaHei", 9)).pack(padx=5, pady=3, anchor="w")

        action_row = ttk.Frame(frame)
        action_row.pack(fill="x", pady=(8, 4))
        ttk.Button(action_row, text="预览效果", command=self._do_preview).pack(side="left")
        ttk.Button(action_row, text="开始处理", command=self._start_batch).pack(side="left", padx=5)
        ttk.Button(action_row, text="取消", command=self._cancel_batch).pack(side="left")
        ttk.Checkbutton(action_row, text="覆盖原图", variable=tk.BooleanVar()).pack(side="right")

        preview_frame = ttk.LabelFrame(frame, text="预览", padding=3)
        preview_frame.pack(fill="both", expand=True, pady=(6, 0))

        self.preview_notebook = ttk.Notebook(preview_frame)
        self.preview_notebook.pack(fill="both", expand=True)

        before_frame = tk.Frame(self.preview_notebook, bg="#f0f0f0")
        self.preview_notebook.add(before_frame, text="处理前")
        self.preview_before_label = tk.Label(before_frame, bg="#f0f0f0")
        self.preview_before_label.pack(fill="both", expand=True)
        self.preview_before_canvas = tk.Canvas(
            before_frame, bg="#f0f0f0", highlightthickness=0)
        self.preview_before_canvas.bind("<ButtonPress-1>", self._wm_mouse_down)
        self.preview_before_canvas.bind("<B1-Motion>", self._wm_mouse_drag)
        self.preview_before_canvas.bind("<ButtonRelease-1>", self._wm_mouse_up)

        self.preview_after_label = tk.Label(self.preview_notebook, bg="#f0f0f0")
        self.preview_notebook.add(self.preview_after_label, text="处理后")

        return frame

    def _build_compress_tab(self):
        tab = ttk.Frame(self.op_notebook)
        self.op_notebook.add(tab, text="压缩")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(row1, text="压缩质量 (1-100):").pack(side="left")
        self.compress_quality = tk.IntVar(value=85)
        ttk.Scale(row1, from_=1, to=100, variable=self.compress_quality, length=200).pack(side="left", padx=10)
        ttk.Label(row1, textvariable=self.compress_quality).pack(side="left")
        ttk.Label(row1, text=" (越低体积越小)").pack(side="left")

        row2 = ttk.Frame(tab)
        row2.pack(fill="x", padx=10, pady=5)
        ttk.Label(row2, text="目标格式:").pack(side="left")
        self.compress_fmt = ttk.Combobox(row2, values=["保持原格式", "JPEG", "PNG", "WebP"], state="readonly", width=12)
        self.compress_fmt.current(0)
        self.compress_fmt.pack(side="left", padx=10)

    def _build_resize_tab(self):
        tab = ttk.Frame(self.op_notebook)
        self.op_notebook.add(tab, text="尺寸")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(row1, text="预设尺寸:").pack(side="left")

        presets = ttk.Frame(tab)
        presets.pack(fill="x", padx=10, pady=2)
        self.resize_preset = tk.StringVar(value="custom")
        for text, val in [("自定义", "custom"), ("小红书 3:4 (1080x1440)", "xhs34"),
                          ("正方形 1:1 (1080x1080)", "11"), ("全屏 9:16 (1080x1920)", "916"),
                          ("公众号头图 (900x383)", "wechat")]:
            ttk.Radiobutton(presets, text=text, value=val, variable=self.resize_preset,
                            command=self._on_resize_preset).pack(anchor="w")

        row2 = ttk.Frame(tab)
        row2.pack(fill="x", padx=10, pady=(8, 2))
        ttk.Label(row2, text="宽度:").pack(side="left")
        self.resize_w = tk.StringVar(value="1080")
        ttk.Entry(row2, textvariable=self.resize_w, width=8).pack(side="left", padx=5)
        ttk.Label(row2, text="高度:").pack(side="left", padx=(15, 5))
        self.resize_h = tk.StringVar(value="1440")
        ttk.Entry(row2, textvariable=self.resize_h, width=8).pack(side="left", padx=5)

        row3 = ttk.Frame(tab)
        row3.pack(fill="x", padx=10, pady=5)
        ttk.Label(row3, text="裁剪模式:").pack(side="left")
        self.resize_mode = ttk.Combobox(row3, values=["中心裁剪（不拉伸）", "缩放填充（可能变形）", "缩放到适合（留白）"],
                                        state="readonly", width=22)
        self.resize_mode.current(0)
        self.resize_mode.pack(side="left", padx=10)

    def _build_dpi_tab(self):
        tab = ttk.Frame(self.op_notebook)
        self.op_notebook.add(tab, text="DPI")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Label(row1, text="预设 DPI:").pack(side="left")

        presets = ttk.Frame(tab)
        presets.pack(fill="x", padx=10, pady=2)
        self.dpi_preset = tk.StringVar(value="custom")
        for text, val in [("72 (屏幕/Web)", "72"), ("96 (Windows默认)", "96"),
                          ("150 (草稿打印)", "150"), ("300 (标准打印)", "300"),
                          ("自定义", "custom")]:
            ttk.Radiobutton(presets, text=text, value=val, variable=self.dpi_preset,
                            command=self._on_dpi_preset).pack(anchor="w")

        row2 = ttk.Frame(tab)
        row2.pack(fill="x", padx=10, pady=5)
        ttk.Label(row2, text="自定义 DPI:").pack(side="left")
        self.dpi_value = tk.StringVar(value="300")
        ttk.Entry(row2, textvariable=self.dpi_value, width=8).pack(side="left", padx=10)

        tk.Label(tab, text="仅修改DPI元数据，不改变像素尺寸（图片清晰度不变）",
                 fg="#999", font=("Microsoft YaHei", 8)).pack(padx=10, pady=(15, 5), anchor="w")

    def _build_watermark_tab(self):
        tab = ttk.Frame(self.op_notebook)
        self.op_notebook.add(tab, text="水印")

        wm_notebook = ttk.Notebook(tab)
        wm_notebook.pack(fill="x", padx=5, pady=5)

        txt_tab = ttk.Frame(wm_notebook)
        wm_notebook.add(txt_tab, text="文字水印")

        r1 = ttk.Frame(txt_tab)
        r1.pack(fill="x", padx=8, pady=(8, 3))
        ttk.Label(r1, text="文字内容:").pack(side="left")
        self.wm_text = tk.StringVar(value="© 图速")
        ttk.Entry(r1, textvariable=self.wm_text, width=30).pack(side="left", padx=8)

        r2 = ttk.Frame(txt_tab)
        r2.pack(fill="x", padx=8, pady=3)
        ttk.Label(r2, text="字体大小:").pack(side="left")
        self.wm_font_size = tk.IntVar(value=36)
        ttk.Scale(r2, from_=8, to=120, variable=self.wm_font_size, length=150).pack(side="left", padx=8)
        ttk.Label(r2, textvariable=self.wm_font_size).pack(side="left")

        r3 = ttk.Frame(txt_tab)
        r3.pack(fill="x", padx=8, pady=3)
        ttk.Label(r3, text="透明度 (%):").pack(side="left")
        self.wm_txt_opacity = tk.IntVar(value=50)
        ttk.Scale(r3, from_=10, to=100, variable=self.wm_txt_opacity, length=150).pack(side="left", padx=8)
        ttk.Label(r3, textvariable=self.wm_txt_opacity).pack(side="left")

        r4 = ttk.Frame(txt_tab)
        r4.pack(fill="x", padx=8, pady=3)
        ttk.Label(r4, text="位置:").pack(side="left")
        self.wm_position = ttk.Combobox(r4, values=[
            "右下角", "左下角", "左上角", "右上角", "居中", "平铺"
        ], state="readonly", width=10)
        self.wm_position.current(0)
        self.wm_position.pack(side="left", padx=8)

        img_tab = ttk.Frame(wm_notebook)
        wm_notebook.add(img_tab, text="图片水印")

        ir1 = ttk.Frame(img_tab)
        ir1.pack(fill="x", padx=8, pady=(8, 5))
        self.wm_img_path = tk.StringVar()
        ttk.Label(ir1, text="水印图片:").pack(side="left")
        ttk.Entry(ir1, textvariable=self.wm_img_path, width=25).pack(side="left", padx=8)
        ttk.Button(ir1, text="选择", command=self._choose_wm_image, width=6).pack(side="left")

        ir2 = ttk.Frame(img_tab)
        ir2.pack(fill="x", padx=8, pady=3)
        ttk.Label(ir2, text="缩放 (%):").pack(side="left")
        self.wm_img_scale = tk.IntVar(value=15)
        ttk.Scale(ir2, from_=5, to=50, variable=self.wm_img_scale, length=150).pack(side="left", padx=8)
        ttk.Label(ir2, textvariable=self.wm_img_scale).pack(side="left")

        ir3 = ttk.Frame(img_tab)
        ir3.pack(fill="x", padx=8, pady=3)
        ttk.Label(ir3, text="位置:").pack(side="left")
        self.wm_img_position = ttk.Combobox(ir3, values=["右下角", "左下角", "左上角", "右上角", "居中"],
                                            state="readonly", width=10)
        self.wm_img_position.current(0)
        self.wm_img_position.pack(side="left", padx=8)

    def _build_convert_tab(self):
        tab = ttk.Frame(self.op_notebook)
        self.op_notebook.add(tab, text="格式")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x", padx=10, pady=(15, 5))
        ttk.Label(row1, text="转换为:").pack(side="left")
        self.convert_fmt = ttk.Combobox(row1, values=["JPEG", "PNG", "WebP", "BMP", "HEIC"],
                                        state="readonly", width=12)
        self.convert_fmt.current(0)
        self.convert_fmt.pack(side="left", padx=10)

        row2 = ttk.Frame(tab)
        row2.pack(fill="x", padx=10, pady=5)
        ttk.Label(row2, text="JPEG/WebP 质量 (1-100):").pack(side="left")
        self.convert_quality = tk.IntVar(value=85)
        ttk.Scale(row2, from_=1, to=100, variable=self.convert_quality, length=200).pack(side="left", padx=10)
        ttk.Label(row2, textvariable=self.convert_quality).pack(side="left")

    def _build_border_tab(self):
        tab = ttk.Frame(self.op_notebook)
        self.op_notebook.add(tab, text="边框")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x", padx=10, pady=(10, 3))
        ttk.Label(row1, text="边框宽度 (px):").pack(side="left")
        self.border_width = tk.IntVar(value=20)
        ttk.Scale(row1, from_=0, to=100, variable=self.border_width, length=180).pack(side="left", padx=10)
        ttk.Label(row1, textvariable=self.border_width).pack(side="left")

        row2 = ttk.Frame(tab)
        row2.pack(fill="x", padx=10, pady=3)
        ttk.Label(row2, text="边框颜色:").pack(side="left")
        self.border_color = tk.StringVar(value="#FFFFFF")
        ttk.Entry(row2, textvariable=self.border_color, width=10).pack(side="left", padx=10)
        tk.Label(row2, text="(白色=#FFFFFF)", fg="#999", font=("Microsoft YaHei", 8)).pack(side="left")

        row3 = ttk.Frame(tab)
        row3.pack(fill="x", padx=10, pady=3)
        ttk.Label(row3, text="圆角半径 (px):").pack(side="left")
        self.corner_radius = tk.IntVar(value=0)
        ttk.Scale(row3, from_=0, to=80, variable=self.corner_radius, length=180).pack(side="left", padx=10)
        ttk.Label(row3, textvariable=self.corner_radius).pack(side="left")

        row4 = ttk.Frame(tab)
        row4.pack(fill="x", padx=10, pady=3)
        ttk.Label(row4, text="阴影模糊:").pack(side="left")
        self.shadow_blur = tk.IntVar(value=0)
        ttk.Scale(row4, from_=0, to=40, variable=self.shadow_blur, length=180).pack(side="left", padx=10)
        ttk.Label(row4, textvariable=self.shadow_blur).pack(side="left")
        tk.Label(row4, text="(0=无阴影)", fg="#999", font=("Microsoft YaHei", 8)).pack(side="left")

    def _build_grid_tab(self):
        tab = ttk.Frame(self.op_notebook)
        self.op_notebook.add(tab, text="九宫格")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x", padx=10, pady=(10, 3))
        ttk.Label(row1, text="输出尺寸 (宽x高):").pack(side="left")
        self.grid_w = tk.StringVar(value="1080")
        ttk.Entry(row1, textvariable=self.grid_w, width=6).pack(side="left", padx=5)
        ttk.Label(row1, text="x").pack(side="left")
        self.grid_h = tk.StringVar(value="1080")
        ttk.Entry(row1, textvariable=self.grid_h, width=6).pack(side="left", padx=5)

        row2 = ttk.Frame(tab)
        row2.pack(fill="x", padx=10, pady=3)
        ttk.Label(row2, text="间隙 (px):").pack(side="left")
        self.grid_gap = tk.IntVar(value=4)
        ttk.Scale(row2, from_=0, to=20, variable=self.grid_gap, length=150).pack(side="left", padx=10)
        ttk.Label(row2, textvariable=self.grid_gap).pack(side="left")

        row3 = ttk.Frame(tab)
        row3.pack(fill="x", padx=10, pady=3)
        ttk.Label(row3, text="背景色:").pack(side="left")
        self.grid_bg = tk.StringVar(value="#FFFFFF")
        ttk.Entry(row3, textvariable=self.grid_bg, width=10).pack(side="left", padx=10)

    def _build_rmwatermark_tab(self):
        tab = ttk.Frame(self.op_notebook)
        self.op_notebook.add(tab, text="去水印")

        row1 = ttk.Frame(tab)
        row1.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Button(row1, text="在预览图上框选水印区域",
                   command=self._start_wm_select).pack(side="left")
        ttk.Button(row1, text="清除选区", command=self._clear_wm_region).pack(side="left", padx=10)

        row2 = ttk.Frame(tab)
        row2.pack(fill="x", padx=10, pady=5)
        ttk.Label(row2, text="水印区域:").pack(side="left")
        self.wm_region_label = tk.Label(row2, text="未选择", fg="#999",
                                         font=("Microsoft YaHei", 9))
        self.wm_region_label.pack(side="left", padx=8)

        row3 = ttk.Frame(tab)
        row3.pack(fill="x", padx=10, pady=3)
        ttk.Label(row3, text="去水印强度:").pack(side="left")
        self.wm_inpaint_radius = tk.IntVar(value=5)
        ttk.Scale(row3, from_=1, to=20, variable=self.wm_inpaint_radius, length=180).pack(side="left", padx=10)
        ttk.Label(row3, textvariable=self.wm_inpaint_radius).pack(side="left")
        tk.Label(row3, text="(值越大越模糊)", fg="#999", font=("Microsoft YaHei", 8)).pack(side="left")

        tk.Label(tab, text="框选后批量处理会对所有图片的同一位置去水印",
                 fg="#999", font=("Microsoft YaHei", 8)).pack(padx=10, pady=(15, 5), anchor="w")

    def _start_wm_select(self):
        if not self.files:
            messagebox.showwarning("提示", "请先添加图片文件")
            return
        self.wm_select_mode = True
        self.preview_before_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        thumb = next(iter(self._thumb_cache.values()), None)
        if thumb:
            self.preview_before_canvas.config(width=thumb.width(), height=thumb.height())
        self._set_status("请在左侧预览图上拖拽框选水印区域")
        self.preview_notebook.select(0)

    def _clear_wm_region(self):
        self.wm_select_mode = False
        self.wm_region = None
        self.wm_full_img_size = None
        self.wm_region_label.config(text="未选择")
        self.preview_before_canvas.place_forget()
        self.preview_before_canvas.delete("all")
        self.wm_rect_id = None

    def _wm_mouse_down(self, event):
        if not self.wm_select_mode:
            return
        self.wm_rect_start = (event.x, event.y)
        if self.wm_rect_id:
            self.preview_before_canvas.delete(self.wm_rect_id)

    def _wm_mouse_drag(self, event):
        if not self.wm_select_mode or not self.wm_rect_start:
            return
        x1, y1 = self.wm_rect_start
        x2, y2 = event.x, event.y
        if self.wm_rect_id:
            self.preview_before_canvas.coords(self.wm_rect_id, x1, y1, x2, y2)
        else:
            self.wm_rect_id = self.preview_before_canvas.create_rectangle(
                x1, y1, x2, y2, outline="#FF0000", width=2, dash=(4, 2))

    def _wm_mouse_up(self, event):
        if not self.wm_select_mode or not self.wm_rect_start:
            return
        x1, y1 = self.wm_rect_start
        x2, y2 = event.x, event.y
        if abs(x2 - x1) < 10 or abs(y2 - y1) < 10:
            return

        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)

        if self.wm_full_img_size:
            fw, fh = self.wm_full_img_size
            pw = self.preview_before_canvas.winfo_width()
            ph = self.preview_before_canvas.winfo_height()
            scale_x = fw / pw if pw > 0 else 1
            scale_y = fh / ph if ph > 0 else 1
            rx = int(x1 * scale_x)
            ry = int(y1 * scale_y)
            rw = int((x2 - x1) * scale_x)
            rh = int((y2 - y1) * scale_y)
            self.wm_region = (rx, ry, rw, rh)
            self.wm_full_img_size = (fw, fh)
            self.wm_region_label.config(text=f"X:{rx} Y:{ry}  宽:{rw} 高:{rh}")
            self._set_status(f"水印区域已选择: {rw}x{rh}")
        else:
            self.wm_region = (x1, y1, x2 - x1, y2 - y1)
            self.wm_region_label.config(text=f"X:{x1} Y:{y1}  宽:{x2-x1} 高:{y2-y1}")

        self.wm_select_mode = False

    def _build_statusbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=(0, 6))

        self.progress = ttk.Progressbar(bar, mode="determinate", length=300)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.status_label = tk.Label(bar, text="就绪", fg="#666", font=("Microsoft YaHei", 9))
        self.status_label.pack(side="left")

    def _setup_dnd(self):
        if enable_drop:
            enable_drop(self.drop_frame, self._on_drop)
            enable_drop(self.file_listbox, self._on_drop)

    def _on_drop(self, file_paths):
        added = 0
        for p in file_paths:
            if p.lower().endswith(SUPPORTED_EXT) and p not in self.files:
                self.files.append(p)
                added += 1
        if added:
            self._refresh_file_list()
            self._build_thumb_cache()
            if self.files and len(self.files) == added:
                self.file_listbox.selection_set(0)
                self._show_cached_preview(self.files[0])
            self._set_status(f"已添加 {added} 个文件")

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择图片文件",
            filetypes=[("图片文件", "*.jpg;*.jpeg;*.png;*.bmp;*.webp;*.heic"), ("所有文件", "*.*")]
        )
        added = 0
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                added += 1
        if added:
            self._refresh_file_list()
            self._build_thumb_cache()
            if self.files:
                self.file_listbox.selection_set(0)
                self._show_cached_preview(self.files[0])
            self._set_status(f"已添加 {added} 个文件，共 {len(self.files)} 张")

    def _clear_files(self):
        self.files.clear()
        self.images.clear()
        self._thumb_cache.clear()
        self._thumb_orig_sizes.clear()
        self._refresh_file_list()
        self._clear_preview()
        self._set_status("已清空")

    def _remove_selected(self):
        selected = self.file_listbox.curselection()
        if not selected:
            return
        for i in reversed(selected):
            path = self.files[i]
            del self.files[i]
            self.images.pop(path, None)
            self._thumb_cache.pop(path, None)
            self._thumb_orig_sizes.pop(path, None)
        self._refresh_file_list()
        self._set_status(f"剩余 {len(self.files)} 张")

    def _refresh_file_list(self):
        self.file_listbox.delete(0, "end")
        for p in self.files:
            self.file_listbox.insert("end", os.path.basename(p))
        list_header = self.file_listbox.master.winfo_children()[0].winfo_children()[0]
        children = self.file_listbox.master.winfo_children()[0].winfo_children()
        if len(children) >= 2:
            children[1].config(text=f"({len(self.files)} 张)")

    def _on_file_select(self, event=None):
        selection = self.file_listbox.curselection()
        if not selection:
            return
        path = self.files[selection[0]]
        self._show_cached_preview(path)

    def _update_file_info(self, path):
        img = None
        try:
            img = Image.open(path)
            w, h = img.size
            fmt = img.format or "未知"
            dpi = img.info.get("dpi", (72, 72))
            dpi_x = dpi[0] if isinstance(dpi, (tuple, list)) else dpi
            size_bytes = os.path.getsize(path)
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.0f} KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            self.info_text.set(f"原尺寸: {w}x{h}  |  原大小: {size_str}  |  格式: {fmt}  |  DPI: {dpi_x:.0f}")
        except Exception:
            self.info_text.set("无法读取文件信息")
        finally:
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass

    def _choose_output_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.output_dir.set(d)

    def _build_thumb_cache(self):
        self._thumb_cache.clear()
        self._thumb_orig_sizes.clear()
        for path in self.files:
            img = None
            try:
                img = Image.open(path)
                img = ImageOps.exif_transpose(img)
                orig_w, orig_h = img.size
                self._thumb_orig_sizes[path] = (orig_w, orig_h)
                img.thumbnail((420, 350), Image.LANCZOS)
                preview_img = img
                if preview_img.mode == "RGBA":
                    bg = Image.new("RGBA", preview_img.size, (240, 240, 240, 255))
                    preview_img = Image.alpha_composite(bg, preview_img).convert("RGB")
                elif preview_img.mode != "RGB":
                    preview_img = preview_img.convert("RGB")
                self._thumb_cache[path] = ImageTk.PhotoImage(preview_img)
            except Exception:
                self._thumb_cache[path] = None
                self._thumb_orig_sizes[path] = (0, 0)
            finally:
                if img is not None:
                    try:
                        img.close()
                    except Exception:
                        pass

    def _show_cached_preview(self, path):
        thumb = self._thumb_cache.get(path)
        self.preview_notebook.select(0)
        if thumb is None:
            self.preview_before_label.config(image="", text="无法预览")
            return
        self.preview_before_label.config(image=thumb, text="")
        self.wm_full_img_size = self._thumb_orig_sizes.get(path, (thumb.width(), thumb.height()))
        self._update_file_info(path)

    def _clear_preview(self):
        self.preview_before_label.config(image="", text="")
        self.preview_after_label.config(image="", text="")
        self.current_preview = None

    def _do_preview(self):
        if not self.files:
            messagebox.showwarning("提示", "请先添加图片文件")
            return
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先在文件列表中选择一张图片")
            return
        path = self.files[selection[0]]
        img = None
        result = None
        try:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            result = self._apply_operation(img)
            if result:
                self._show_preview_on_label(result, self.preview_after_label)
                self.preview_notebook.select(1)
                self._set_status("预览完成")
        except Exception as e:
            messagebox.showerror("预览失败", str(e))
        finally:
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass
            if result is not None:
                try:
                    result.close()
                except Exception:
                    pass

    def _show_preview_on_label(self, img, label):
        preview = img.copy()
        preview.thumbnail((420, 350), Image.LANCZOS)
        if preview.mode == "RGBA":
            bg = Image.new("RGBA", preview.size, (240, 240, 240, 255))
            preview = Image.alpha_composite(bg, preview).convert("RGB")
        elif preview.mode != "RGB":
            preview = preview.convert("RGB")
        self.current_preview = ImageTk.PhotoImage(preview)
        label.config(image=self.current_preview, text="")

    def _get_active_tab_name(self):
        return self.op_notebook.tab(self.op_notebook.select(), "text")

    def _apply_operation(self, img):
        tab = self._get_active_tab_name()
        if operations is None:
            return img

        if tab == "压缩":
            q = self.compress_quality.get()
            fmt = self.compress_fmt.get()
            return operations.compress_image(img, quality=q, target_fmt=fmt)
        elif tab == "尺寸":
            try:
                w = int(self.resize_w.get())
                h = int(self.resize_h.get())
            except ValueError:
                w, h = 1080, 1440
            mode_map = {"中心裁剪（不拉伸）": "crop", "缩放填充（可能变形）": "stretch", "缩放到适合（留白）": "fit"}
            return operations.resize_image(img, w, h, mode_map.get(self.resize_mode.get(), "crop"))
        elif tab == "水印":
            active = self.op_notebook.nametowidget(self.op_notebook.select()).winfo_children()
            if not active:
                return img
            wm_notebook = active[0]
            if isinstance(wm_notebook, ttk.Notebook):
                wm_tab = wm_notebook.tab(wm_notebook.select(), "text")
                if wm_tab == "文字水印":
                    return operations.add_text_watermark(
                        img, text=self.wm_text.get(),
                        position=self.wm_position.get(),
                        font_size=self.wm_font_size.get(),
                        opacity=int(self.wm_txt_opacity.get() * 255 / 100)
                    )
                elif wm_tab == "图片水印" and self.wm_img_path.get():
                    wm_img = Image.open(self.wm_img_path.get())
                    result = operations.add_image_watermark(
                        img, wm_img, position=self.wm_img_position.get(),
                        scale=self.wm_img_scale.get() / 100
                    )
                    wm_img.close()
                    return result
        elif tab == "DPI":
            try:
                dpi_val = int(self.dpi_value.get())
            except ValueError:
                dpi_val = 300
            return operations.change_dpi(img, dpi=dpi_val)
        elif tab == "格式":
            fmt = self.convert_fmt.get()
            return operations.convert_format(img, target_fmt=fmt, quality=self.convert_quality.get())
        elif tab == "边框":
            return operations.add_border_effect(
                img, border_px=self.border_width.get(),
                color=self.border_color.get(),
                corner_radius=self.corner_radius.get(),
                shadow_blur=self.shadow_blur.get()
            )
        elif tab == "九宫格":
            try:
                gw = int(self.grid_w.get())
                gh = int(self.grid_h.get())
            except ValueError:
                gw, gh = 1080, 1080
            return operations.make_9grid(
                img, output_size=(gw, gh),
                gap=self.grid_gap.get(), bg_color=self.grid_bg.get()
            )
        elif tab == "去水印":
            if not self.wm_region:
                return img
            rx, ry, rw, rh = self.wm_region
            return operations.remove_watermark(img, rx, ry, rw, rh,
                                               inpaint_radius=self.wm_inpaint_radius.get())
        return img

    def _start_batch(self):
        if not self.files:
            messagebox.showwarning("提示", "请先添加图片文件")
            return
        out_dir = self.output_dir.get()
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建输出目录:\n{e}")
                return

        self._cancel_flag = False
        self.progress["value"] = 0
        self.progress["maximum"] = len(self.files)

        t = threading.Thread(target=self._process_batch, daemon=True)
        t.start()

    def _process_batch(self):
        out_dir = self.output_dir.get()
        total = len(self.files)
        success = 0
        self._batch_log = []

        for i, path in enumerate(self.files):
            if self._cancel_flag:
                break
            img = None
            result = None
            try:
                img = Image.open(path)
                img = ImageOps.exif_transpose(img)
                orig_w, orig_h = img.size
                orig_size = os.path.getsize(path)
                result = self._apply_operation(img)
                img.close()
                img = None

                new_w, new_h = result.size
                name, _ = os.path.splitext(os.path.basename(path))
                ext = ".jpg"
                if result.mode == "RGBA":
                    ext = ".png"
                out_path = os.path.join(out_dir, f"{name}_processed{ext}")
                if result.mode == "RGBA":
                    result.save(out_path, "PNG")
                else:
                    result.save(out_path, "JPEG", quality=90, optimize=True)

                new_size = os.path.getsize(out_path)
                result.close()
                self._batch_log.append({
                    "name": os.path.basename(path),
                    "orig_size": orig_size,
                    "new_size": new_size,
                    "orig_dims": f"{orig_w}x{orig_h}",
                    "new_dims": f"{new_w}x{new_h}",
                })
                success += 1
            except Exception as e:
                print(f"处理失败: {path} - {e}")
            finally:
                if img is not None:
                    try:
                        img.close()
                    except Exception:
                        pass
                if result is not None:
                    try:
                        result.close()
                    except Exception:
                        pass

            if (i + 1) % 5 == 0 or i == total - 1:
                self.root.after(0, self._update_progress, i + 1)

        final_msg = f"完成 {success}/{total}"
        if self._cancel_flag:
            final_msg += " [已取消]"
        self.root.after(0, self._batch_done, final_msg)

    def _update_progress(self, n):
        self.progress["value"] = n
        self._set_status(f"处理中... {n}/{len(self.files)}")

    def _cancel_batch(self):
        self._cancel_flag = True
        self._set_status("取消中...")

    def _batch_done(self, msg):
        self._set_status(msg)
        self.progress["value"] = 0
        if self._cancel_flag:
            return
        if self._batch_log:
            details = []
            for item in self._batch_log[:20]:
                size_change = ""
                if item["new_size"] != item["orig_size"]:
                    delta = item["new_size"] - item["orig_size"]
                    sign = "+" if delta >= 0 else ""
                    pct = abs(delta) / item["orig_size"] * 100 if item["orig_size"] > 0 else 0
                    dir_sign = "↑" if delta >= 0 else "↓"
                    size_change = f"  {dir_sign}{sign}{pct:.0f}%"
                dim_change = ""
                if item["new_dims"] != item["orig_dims"]:
                    dim_change = f"  尺寸: {item['orig_dims']} -> {item['new_dims']}"
                details.append(f"{item['name']}{size_change}{dim_change}")
            if len(self._batch_log) > 20:
                details.append(f"... 还有 {len(self._batch_log) - 20} 个文件")
            messagebox.showinfo("处理完成", f"{msg}\n\n" + "\n".join(details))

    def _on_resize_preset(self):
        mapping = {"xhs34": (1080, 1440), "11": (1080, 1080), "916": (1080, 1920), "wechat": (900, 383)}
        val = self.resize_preset.get()
        if val in mapping:
            w, h = mapping[val]
            self.resize_w.set(str(w))
            self.resize_h.set(str(h))

    def _on_dpi_preset(self):
        val = self.dpi_preset.get()
        if val != "custom":
            self.dpi_value.set(val)

    def _choose_wm_image(self):
        path = filedialog.askopenfilename(
            title="选择水印图片",
            filetypes=[("图片文件", "*.png;*.jpg;*.jpeg;*.bmp"), ("所有文件", "*.*")]
        )
        if path:
            self.wm_img_path.set(path)

    def _set_status(self, text):
        self.status_label.config(text=text)

    def _on_close(self):
        self._thumb_cache.clear()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ImageBatchApp()
    app.run()

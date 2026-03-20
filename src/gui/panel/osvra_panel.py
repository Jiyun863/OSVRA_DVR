"""
Phase 7: OSVRA 전용 UI 패널
SOI 설정, 파라미터 제어, depth histogram 표시, fusion 결과 표시
"""

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QComboBox, QCheckBox,
    QFrame, QSizePolicy, QDoubleSpinBox, QSpinBox,
    QGroupBox, QProgressBar,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont


class SlicePreviewCanvas(QLabel):
    """SOI PET 슬라이스 즉시 미리보기 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(120)
        self.setMaximumHeight(200)
        self.setStyleSheet(
            "background-color: #1a1a1a; border: 1px solid #444;"
            "color: #555; font-size: 11px;"
        )
        self.setText("SOI preview")
        self._pixmap_cache = None
        self._img_data_ref = None
        self._in_resize = False

    def display_preview(self, rgba_array: np.ndarray):
        """TF 적용된 RGBA float [0,1] array를 검은 배경 위에 alpha premultiply로 표시

        Args:
            rgba_array: (H, W, 4) float [0, 1]
        """
        if rgba_array is None or rgba_array.size == 0:
            self.setText("No slice data")
            self._pixmap_cache = None
            self._img_data_ref = None
            return

        rgba = np.clip(rgba_array, 0, 1)
        # Alpha premultiply over black background: RGB = RGB * A
        rgb = rgba[..., :3] * rgba[..., 3:4]
        img_uint8 = (rgb * 255).astype(np.uint8)
        h, w = img_uint8.shape[:2]

        # Pad to 4 channels (RGBA) with full opacity for QImage
        alpha_full = np.full((h, w, 1), 255, dtype=np.uint8)
        img_rgba = np.concatenate([img_uint8, alpha_full], axis=2)

        self._img_data_ref = np.ascontiguousarray(img_rgba)
        stride = self._img_data_ref.strides[0]
        qimage = QImage(self._img_data_ref.data, w, h, stride,
                        QImage.Format.Format_RGBA8888)
        qimage = qimage.copy()
        self._pixmap_cache = QPixmap.fromImage(qimage)
        self._update_display()

    def _update_display(self):
        if self._pixmap_cache is None:
            return
        self.setText("")
        scaled = self._pixmap_cache.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._in_resize:
            self._in_resize = True
            self._update_display()
            self._in_resize = False


class HistogramCanvas(QLabel):
    """Depth histogram 시각화 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(120)
        self.setMaximumHeight(150)
        self.setStyleSheet("background-color: #1a1a1a; border: 1px solid #444;")
        self.setText("No histogram data")
        self.setStyleSheet(
            "background-color: #1a1a1a; border: 1px solid #444;"
            "color: #555; font-size: 11px;"
        )

        self._hist_data = None
        self._peaks = []
        self._selected_D = None
        self._in_resize = False

    def set_histogram(self, hist_result: dict, selected_D: float = None):
        """histogram 데이터 설정 및 렌더링"""
        self._hist_data = hist_result
        self._selected_D = selected_D
        self._peaks = hist_result.get('peak_distances', [])
        self._draw_histogram()

    def _draw_histogram(self):
        if self._hist_data is None:
            return

        smoothed = self._hist_data.get('smoothed', np.array([]))
        bin_centers = self._hist_data.get('bin_centers', np.array([]))

        if len(smoothed) == 0 or len(bin_centers) == 0:
            return

        w = max(self.width(), 200)
        h = max(self.height(), 100)

        img = QImage(w, h, QImage.Format.Format_RGB32)
        img.fill(QColor(26, 26, 26))

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin_l, margin_r, margin_t, margin_b = 10, 10, 10, 20
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b

        max_val = smoothed.max() if smoothed.max() > 0 else 1.0
        n_bins = len(smoothed)

        # Draw histogram bars
        bar_w = max(1, plot_w / n_bins)
        painter.setPen(Qt.PenStyle.NoPen)

        for i in range(n_bins):
            bar_h = int((smoothed[i] / max_val) * plot_h)
            x = margin_l + int(i * plot_w / n_bins)
            y = margin_t + plot_h - bar_h

            painter.setBrush(QColor(42, 130, 218, 180))
            painter.drawRect(int(x), y, max(1, int(bar_w)), bar_h)

        # Draw peak markers
        peaks_idx = self._hist_data.get('peaks', [])
        painter.setPen(QPen(QColor(255, 80, 80), 2))
        for pidx in peaks_idx:
            if pidx < n_bins:
                x = margin_l + int(pidx * plot_w / n_bins) + int(bar_w / 2)
                painter.drawLine(x, margin_t, x, margin_t + plot_h)

        # Draw selected D marker
        if self._selected_D is not None and len(bin_centers) > 0:
            d_min, d_max = bin_centers[0], bin_centers[-1]
            if d_max > d_min:
                d_frac = (self._selected_D - d_min) / (d_max - d_min)
                x = margin_l + int(d_frac * plot_w)
                painter.setPen(QPen(QColor(0, 255, 100), 2, Qt.PenStyle.DashLine))
                painter.drawLine(x, margin_t, x, margin_t + plot_h)

        # Axis label
        painter.setPen(QColor(150, 150, 150))
        painter.setFont(QFont("monospace", 8))
        if len(bin_centers) > 0:
            painter.drawText(margin_l, h - 3, f"{bin_centers[0]:.0f}mm")
            painter.drawText(w - margin_r - 40, h - 3, f"{bin_centers[-1]:.0f}mm")

        painter.end()

        self.setPixmap(QPixmap.fromImage(img))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._hist_data is not None and not self._in_resize:
            self._in_resize = True
            self._draw_histogram()
            self._in_resize = False


class FusionResultCanvas(QLabel):
    """Fusion 결과 이미지 표시 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 200)
        self.setStyleSheet(
            "background-color: #111111; border: 1px solid #444;"
            "color: #555; font-size: 12px;"
        )
        self.setText("OSVRA result will appear here")
        self._pixmap_cache = None
        self._img_data_ref = None
        self._in_resize = False

    def set_image(self, rgba_array: np.ndarray):
        """RGBA float [0,1] array를 표시

        Args:
            rgba_array: (H, W, 4) float [0, 1]
        """
        if rgba_array is None or rgba_array.size == 0:
            self.setText("No result")
            self._pixmap_cache = None
            self._img_data_ref = None
            return

        # float [0,1] -> uint8
        img_uint8 = (np.clip(rgba_array, 0, 1) * 255).astype(np.uint8)
        h, w = img_uint8.shape[:2]

        if img_uint8.shape[2] == 4:
            fmt = QImage.Format.Format_RGBA8888
        else:
            fmt = QImage.Format.Format_RGB888
            img_uint8 = img_uint8[:, :, :3]

        # numpy 배열을 contiguous로 보장하고 멤버에 보관 (GC 방지)
        self._img_data_ref = np.ascontiguousarray(img_uint8)
        stride = self._img_data_ref.strides[0]
        qimage = QImage(self._img_data_ref.data, w, h, stride, fmt)
        qimage = qimage.copy()  # QImage가 자체 메모리 소유
        self._pixmap_cache = QPixmap.fromImage(qimage)
        self._update_display()

    def clear(self):
        self._pixmap_cache = None
        self.setText("OSVRA result will appear here")

    def _update_display(self):
        if self._pixmap_cache is None:
            return
        self.setText("")
        self.setStyleSheet("background-color: #111111; border: 1px solid #444;")
        scaled = self._pixmap_cache.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._in_resize:
            self._in_resize = True
            self._update_display()
            self._in_resize = False


class OSVRAPanel(QWidget):
    """OSVRA 파라미터 제어 및 결과 표시 패널"""

    # Signals
    osvra_enabled_changed = pyqtSignal(bool)
    soi_changed = pyqtSignal(str, int)              # (axis_name, slice_index)
    opacity_limit_changed = pyqtSignal(float)
    sample_step_changed = pyqtSignal(float)
    d_value_changed = pyqtSignal(float)              # manual D value change
    peak_selection_changed = pyqtSignal(int)         # peak index
    fusion_ratio_changed = pyqtSignal(float)
    render_requested = pyqtSignal()
    debug_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # State
        self.current_axis = "Axial"
        self.current_slice = 0
        self.opacity_limit = 0.95
        self.sample_step = 1.0
        self.smoothing_sigma = 2.0
        self.selected_peak_index = 0
        self.fusion_ratio = 0.5
        self.current_D = 50.0
        self._enabled = False

        self._hist_result = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Title
        title = QLabel("OSVRA PET-CT Augmentation")
        title.setStyleSheet("font-size: 15px; font-weight: bold; padding: 4px;")
        root.addWidget(title)

        # Enable checkbox
        self.enable_checkbox = QCheckBox("OSVRA Enable")
        self.enable_checkbox.setChecked(False)
        self.enable_checkbox.toggled.connect(self._on_enable_changed)
        self.enable_checkbox.setStyleSheet("""
            QCheckBox { spacing: 5px; color: white; font-weight: bold; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #777;
                                   background: #353535; border-radius: 3px; }
            QCheckBox::indicator:checked { background: #2a82da; }
        """)
        root.addWidget(self.enable_checkbox)

        # Content area (disabled until enabled)
        self.content_frame = QFrame()
        self.content_frame.setEnabled(False)
        content_layout = QVBoxLayout(self.content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        # === SOI Settings ===
        soi_group = self._create_section("SOI Settings")
        soi_layout = soi_group.layout()

        # Axis selection
        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("Axis:"))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["Axial", "Coronal", "Sagittal"])
        self.axis_combo.currentTextChanged.connect(self._on_axis_changed)
        axis_row.addWidget(self.axis_combo, 1)
        soi_layout.addLayout(axis_row)

        # Slice index
        slice_row = QHBoxLayout()
        slice_row.addWidget(QLabel("Slice:"))
        self.slice_spin = QSpinBox()
        self.slice_spin.setRange(0, 512)
        self.slice_spin.setValue(0)
        self.slice_spin.valueChanged.connect(self._on_slice_changed)
        slice_row.addWidget(self.slice_spin, 1)
        soi_layout.addLayout(slice_row)

        # SOI slice preview
        self.slice_preview = SlicePreviewCanvas()
        soi_layout.addWidget(self.slice_preview)

        content_layout.addWidget(soi_group)

        # === Parameters ===
        param_group = self._create_section("Parameters")
        param_layout = param_group.layout()

        # Opacity limit
        ol_row = QHBoxLayout()
        ol_row.addWidget(QLabel("Opacity Limit:"))
        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.1, 1.0)
        self.opacity_spin.setValue(0.95)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setDecimals(2)
        self.opacity_spin.valueChanged.connect(self._on_opacity_limit_changed)
        ol_row.addWidget(self.opacity_spin, 1)
        param_layout.addLayout(ol_row)

        # Sample step
        ss_row = QHBoxLayout()
        ss_row.addWidget(QLabel("Sample Step (mm):"))
        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(0.5, 5.0)
        self.step_spin.setValue(1.0)
        self.step_spin.setSingleStep(0.5)
        self.step_spin.setDecimals(1)
        self.step_spin.valueChanged.connect(self._on_sample_step_changed)
        ss_row.addWidget(self.step_spin, 1)
        param_layout.addLayout(ss_row)

        # Smoothing sigma
        sm_row = QHBoxLayout()
        sm_row.addWidget(QLabel("Smoothing:"))
        self.smooth_spin = QDoubleSpinBox()
        self.smooth_spin.setRange(0.5, 10.0)
        self.smooth_spin.setValue(2.0)
        self.smooth_spin.setSingleStep(0.5)
        self.smooth_spin.setDecimals(1)
        sm_row.addWidget(self.smooth_spin, 1)
        param_layout.addLayout(sm_row)

        content_layout.addWidget(param_group)

        # === Depth (D) Selection ===
        depth_group = self._create_section("Depth (D) Selection")
        depth_layout = depth_group.layout()

        # Histogram canvas
        self.hist_canvas = HistogramCanvas()
        depth_layout.addWidget(self.hist_canvas)

        # Peak selection
        peak_row = QHBoxLayout()
        peak_row.addWidget(QLabel("Peak:"))
        self.peak_combo = QComboBox()
        self.peak_combo.addItem("Auto (first)")
        self.peak_combo.currentIndexChanged.connect(self._on_peak_changed)
        peak_row.addWidget(self.peak_combo, 1)
        depth_layout.addLayout(peak_row)

        # D value display / manual override
        d_row = QHBoxLayout()
        d_row.addWidget(QLabel("D ="))
        self.d_label = QLabel("-- mm")
        self.d_label.setStyleSheet("color: #2a82da; font-weight: bold; font-size: 13px;")
        d_row.addWidget(self.d_label)
        d_row.addStretch()

        self.d_spin = QDoubleSpinBox()
        self.d_spin.setRange(1.0, 500.0)
        self.d_spin.setValue(50.0)
        self.d_spin.setSingleStep(5.0)
        self.d_spin.setDecimals(1)
        self.d_spin.setPrefix("Manual: ")
        self.d_spin.setSuffix(" mm")
        self.d_spin.valueChanged.connect(self._on_d_manual_changed)
        d_row.addWidget(self.d_spin)
        depth_layout.addLayout(d_row)

        content_layout.addWidget(depth_group)

        # === Fusion ===
        fusion_group = self._create_section("Fusion")
        fusion_layout = fusion_group.layout()

        ratio_row = QHBoxLayout()
        ratio_row.addWidget(QLabel("PET"))
        self.fusion_slider = QSlider(Qt.Orientation.Horizontal)
        self.fusion_slider.setRange(0, 100)
        self.fusion_slider.setValue(50)
        self.fusion_slider.valueChanged.connect(self._on_fusion_changed)
        self.fusion_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px; background: #444; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #2a82da; width: 14px; height: 14px;
                margin: -4px 0; border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, x2:1, stop:0 #ff4444, stop:1 #2a82da);
                border-radius: 3px;
            }
        """)
        ratio_row.addWidget(self.fusion_slider, 1)
        ratio_row.addWidget(QLabel("CT"))
        self.ratio_label = QLabel("0.50")
        self.ratio_label.setFixedWidth(35)
        self.ratio_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ratio_row.addWidget(self.ratio_label)
        fusion_layout.addLayout(ratio_row)

        content_layout.addWidget(fusion_group)

        # === Action Buttons ===
        btn_row = QHBoxLayout()
        self.render_btn = QPushButton("Render")
        self.render_btn.setMinimumHeight(36)
        self.render_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a82da; color: white;
                font-weight: bold; border-radius: 4px; font-size: 13px;
            }
            QPushButton:hover { background-color: #3a92ea; }
            QPushButton:pressed { background-color: #1a72ca; }
            QPushButton:disabled { background-color: #555; color: #888; }
        """)
        self.render_btn.clicked.connect(self._on_render_clicked)
        btn_row.addWidget(self.render_btn)

        self.debug_btn = QPushButton("Debug View")
        self.debug_btn.setMinimumHeight(36)
        self.debug_btn.setEnabled(False)
        self.debug_btn.setStyleSheet("""
            QPushButton {
                background-color: #555; color: #aaa;
                font-weight: bold; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background-color: #666; color: #fff; }
            QPushButton:pressed { background-color: #444; }
            QPushButton:disabled { background-color: #444; color: #666; }
        """)
        self.debug_btn.clicked.connect(self._on_debug_clicked)
        btn_row.addWidget(self.debug_btn)

        content_layout.addLayout(btn_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #333; border-radius: 4px; }
            QProgressBar::chunk { background: #2a82da; border-radius: 4px; }
        """)
        content_layout.addWidget(self.progress_bar)

        # === Result ===
        self.result_canvas = FusionResultCanvas()
        content_layout.addWidget(self.result_canvas, stretch=1)

        root.addWidget(self.content_frame, stretch=1)

    def _create_section(self, title: str) -> QGroupBox:
        """스타일이 적용된 section 생성"""
        group = QGroupBox(title)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; color: #ccc;
                border: 1px solid #444; border-radius: 4px;
                margin-top: 8px; padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 4px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)
        return group

    # ── Signal handlers ──────────────────────────────────────

    def _on_enable_changed(self, checked):
        self._enabled = checked
        self.content_frame.setEnabled(checked)
        self.osvra_enabled_changed.emit(checked)

    def _on_axis_changed(self, text):
        self.current_axis = text
        self.soi_changed.emit(self.current_axis, self.current_slice)

    def _on_slice_changed(self, value):
        self.current_slice = value
        self.soi_changed.emit(self.current_axis, self.current_slice)

    def _on_opacity_limit_changed(self, value):
        self.opacity_limit = value
        self.opacity_limit_changed.emit(value)

    def _on_sample_step_changed(self, value):
        self.sample_step = value
        self.sample_step_changed.emit(value)

    def _on_peak_changed(self, index):
        self.selected_peak_index = index
        self._update_d_from_peak()
        self.peak_selection_changed.emit(index)

    def _on_d_manual_changed(self, value):
        self.current_D = value
        self.d_label.setText(f"{value:.1f} mm")
        self.d_value_changed.emit(value)

    def _on_fusion_changed(self, value):
        self.fusion_ratio = value / 100.0
        self.ratio_label.setText(f"{self.fusion_ratio:.2f}")
        self.fusion_ratio_changed.emit(self.fusion_ratio)

    def _on_render_clicked(self):
        self.render_requested.emit()

    def _on_debug_clicked(self):
        self.debug_requested.emit()

    # ── Public API ───────────────────────────────────────────

    def set_slice_range(self, max_index: int):
        """슬라이스 범위 업데이트"""
        self.slice_spin.setRange(0, max(0, max_index - 1))
        self.slice_spin.setValue(max_index // 2)

    def display_histogram(self, hist_result: dict):
        """Histogram 분석 결과 표시"""
        self._hist_result = hist_result

        # Peak combo 업데이트
        self.peak_combo.blockSignals(True)
        self.peak_combo.clear()
        peak_distances = hist_result.get('peak_distances', [])
        if peak_distances:
            for i, d in enumerate(peak_distances):
                label = "First" if i == 0 else f"#{i+1}"
                self.peak_combo.addItem(f"{label} ({d:.1f} mm)")
        else:
            self.peak_combo.addItem("No peaks found")
        self.peak_combo.blockSignals(False)

        self._update_d_from_peak()
        self.hist_canvas.set_histogram(hist_result, self.current_D)

    def display_result(self, fused_rgba: np.ndarray):
        """Fusion 결과 이미지 표시"""
        self.result_canvas.set_image(fused_rgba)

    def set_progress(self, value: int):
        """Progress bar 업데이트 (0-100)"""
        self.progress_bar.setVisible(value < 100)
        self.progress_bar.setValue(value)

    def set_debug_available(self, enabled: bool):
        """Debug View 버튼 활성화/비활성화"""
        self.debug_btn.setEnabled(enabled)

    def _update_d_from_peak(self):
        """선택된 peak에서 D 값 업데이트"""
        if self._hist_result is None:
            return
        peak_distances = self._hist_result.get('peak_distances', [])
        if peak_distances and self.selected_peak_index < len(peak_distances):
            self.current_D = peak_distances[self.selected_peak_index]
        else:
            self.current_D = self._hist_result.get('default_D', 50.0)

        self.d_label.setText(f"{self.current_D:.1f} mm")
        self.d_spin.blockSignals(True)
        self.d_spin.setValue(self.current_D)
        self.d_spin.blockSignals(False)

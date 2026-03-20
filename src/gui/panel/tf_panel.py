"""
Transfer Function 패널 - PET-CT Multimodal Support
CT / PET 각각 독립적인 TF 탭 보유.
PET 탭은 기본적으로 hot colormap 프리셋으로 초기화.
"""

import json
import numpy as np
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QCheckBox, QLabel,
    QPushButton, QColorDialog, QSlider,
    QFileDialog, QMessageBox, QWidget, QGroupBox,
    QSizePolicy, QTabWidget, QDoubleSpinBox
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor

from src.gui.panel.base_panel import BasePanel
from src.gui.widget.transfer_function_widget import TransferFunctionWidget
from src.gui.widget.light_sphere_widget import LightSphereWidget
from src.gui.panel.clipping_panel import ClippingPanel


# PET hot colormap 프리셋 (renderer_widget과 동기화)
PET_DEFAULT_TF = [
    [0.00, 0.0, 0.0, 0.0, 0.00],
    [0.10, 0.0, 0.0, 0.0, 0.00],
    [0.20, 0.5, 0.0, 0.0, 0.15],
    [0.40, 1.0, 0.0, 0.0, 0.35],
    [0.60, 1.0, 0.5, 0.0, 0.50],
    [0.80, 1.0, 1.0, 0.0, 0.65],
    [1.00, 1.0, 1.0, 1.0, 0.80],
]

CT_DEFAULT_TF = [
    [0.0, 0.0, 0.0, 0.0, 0.0],
    [0.3, 1.0, 0.5, 0.0, 0.1],
    [0.7, 1.0, 1.0, 1.0, 0.8],
    [1.0, 1.0, 1.0, 1.0, 1.0],
]


class TransferFunctionPanel(BasePanel):
    """PET-CT 멀티모달 Transfer Function 패널"""

    # ── 시그널 ──────────────────────────────────────────────────
    tf_changed = pyqtSignal(object)                         # CT TF 변경 (기존 호환)
    ct_tf_changed = pyqtSignal(object)                      # CT TF 변경
    pet_tf_changed = pyqtSignal(object)                     # PET TF 변경
    background_color_changed = pyqtSignal(tuple, tuple)
    shading_changed = pyqtSignal(bool)
    ambient_color_changed = pyqtSignal(float, float, float)
    diffuse_color_changed = pyqtSignal(float, float, float)
    specular_color_changed = pyqtSignal(float, float, float)
    lighting_changed = pyqtSignal(str, float)
    light_direction_changed = pyqtSignal(float, float, float)
    follow_camera_changed = pyqtSignal(bool)
    clipping_changed = pyqtSignal(str, float, float)
    clipping_enabled_changed = pyqtSignal(bool)
    # ────────────────────────────────────────────────────────────

    def __init__(self):
        super().__init__("Transfer Function", collapsible=False)
        self.rendering_panel = None
        self.global_tf = None
        self.volume_data = None
        self.pet_volume_data = None

    def setup_content(self):
        self.content_layout.setSpacing(5)

        # ── 헤더 ─────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        title_label = QLabel("🎨 Transfer Function")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 10px 5px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        self.content_layout.addLayout(header_layout)

        # ── CT / PET TF 탭 ───────────────────────────────────────
        self.tf_tab = QTabWidget()
        self.tf_tab.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #555;
                border-radius: 4px;
                background: transparent;
            }
            QTabBar::tab {
                background: #3a3a3a;
                color: #ccc;
                padding: 6px 20px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
            }
            QTabBar::tab:selected { background: #2196F3; color: white; }
            QTabBar::tab:hover    { background: #555; }
        """)

        # CT 탭
        ct_tab_widget = QWidget()
        ct_tab_layout = QVBoxLayout(ct_tab_widget)
        ct_tab_layout.setContentsMargins(0, 5, 0, 0)

        self.ct_tf_widget = TransferFunctionWidget()
        self.ct_tf_widget.tf_changed.connect(self.on_ct_tf_changed)
        ct_tab_layout.addWidget(self.ct_tf_widget)

        ct_btn_layout, _ = self.create_button_horizontal([
            {"text": "Reset", "callback": self.reset_ct_tf, "height": 28},
            {"text": "Save",  "callback": self.save_ct_tf,  "height": 28},
            {"text": "Load",  "callback": self.load_ct_tf,  "height": 28},
        ])
        ct_tab_layout.addLayout(ct_btn_layout)
        self.tf_tab.addTab(ct_tab_widget, "🔵 CT")

        # PET 탭
        pet_tab_widget = QWidget()
        pet_tab_layout = QVBoxLayout(pet_tab_widget)
        pet_tab_layout.setContentsMargins(0, 5, 0, 0)

        self.pet_tf_widget = TransferFunctionWidget()
        self.pet_tf_widget.tf_changed.connect(self.on_pet_tf_changed)
        pet_tab_layout.addWidget(self.pet_tf_widget)

        pet_btn_layout, _ = self.create_button_horizontal([
            {"text": "Reset", "callback": self.reset_pet_tf, "height": 28},
            {"text": "Save",  "callback": self.save_pet_tf,  "height": 28},
            {"text": "Load",  "callback": self.load_pet_tf,  "height": 28},
        ])
        pet_tab_layout.addLayout(pet_btn_layout)

        # # PET Opacity 전체 스케일 슬라이더
        # pet_opacity_row = QHBoxLayout()
        # pet_opacity_row.addWidget(QLabel("PET Opacity:"))
        # self.pet_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        # self.pet_opacity_slider.setRange(0, 100)
        # self.pet_opacity_slider.setValue(100)
        # self.pet_opacity_slider.valueChanged.connect(self.on_pet_opacity_scale_changed)
        # pet_opacity_row.addWidget(self.pet_opacity_slider, stretch=1)
        # self.pet_opacity_label = QLabel("1.00")
        # self.pet_opacity_label.setFixedWidth(35)
        # pet_opacity_row.addWidget(self.pet_opacity_label)
        # pet_tab_layout.addLayout(pet_opacity_row)

        self.tf_tab.addTab(pet_tab_widget, "🔴 PET")

        self.content_layout.addWidget(self.tf_tab)

        # ── 배경색 ───────────────────────────────────────────────
        bg_group, bg_layout = self.create_group_box("Background", "horizontal")
        
        self.bg_color_btn = QPushButton()
        self.bg_color_btn.setStyleSheet("background-color: #000000;")
        self.bg_color_btn.setMinimumHeight(25)
        self.bg_color_btn.clicked.connect(self.select_background_color)
        bg_layout.addWidget(self.bg_color_btn)

        reset_bg_btn = QPushButton("Reset")
        reset_bg_btn.clicked.connect(self.reset_background_color)
        reset_bg_btn.setMaximumWidth(60)
        bg_layout.addWidget(reset_bg_btn)
        
        self.content_layout.addWidget(bg_group)

        # ── Shading ──────────────────────────────────────────────
        self._setup_shading_controls()

        # ── Clipping ─────────────────────────────────────────────
        self._setup_clipping_controls()

        self.content_layout.addStretch(1)

        # PET 기본 TF 적용
        self._apply_tf_to_widget(self.pet_tf_widget, PET_DEFAULT_TF)

    # ── CT TF 핸들러 ─────────────────────────────────────────────

    def on_ct_tf_changed(self):
        nodes = self.ct_tf_widget.get_nodes()
        self.global_tf = nodes
        self.tf_changed.emit(nodes)       # 기존 호환
        self.ct_tf_changed.emit(nodes)

    def reset_ct_tf(self):
        self.ct_tf_widget.reset_to_default()
        self.on_ct_tf_changed()

    def save_ct_tf(self):
        self._save_tf(self.ct_tf_widget, "CT")

    def load_ct_tf(self):
        nodes = self._load_tf_file("CT")
        if nodes:
            self._apply_tf_to_widget(self.ct_tf_widget, nodes)
            self.on_ct_tf_changed()

    # ── PET TF 핸들러 ────────────────────────────────────────────

    def on_pet_tf_changed(self):
        nodes = self.pet_tf_widget.get_nodes()
        self.pet_tf_changed.emit(nodes)

    def reset_pet_tf(self):
        self.apply_pet_hot_preset()

    def apply_pet_hot_preset(self):
        """PET hot colormap 프리셋 적용"""
        self._apply_tf_to_widget(self.pet_tf_widget, PET_DEFAULT_TF)
        self.pet_tf_changed.emit(PET_DEFAULT_TF)

    def save_pet_tf(self):
        self._save_tf(self.pet_tf_widget, "PET")

    def load_pet_tf(self):
        nodes = self._load_tf_file("PET")
        if nodes:
            self._apply_tf_to_widget(self.pet_tf_widget, nodes)
            self.on_pet_tf_changed()

    def on_pet_opacity_scale_changed(self, value):
        """PET 전체 opacity 스케일 조절"""
        scale = value / 100.0
        self.pet_opacity_label.setText(f"{scale:.2f}")
        # rendering_panel을 통해 renderer에 전달
        if self.rendering_panel and hasattr(self.rendering_panel, 'vtk_renderer'):
            renderer = self.rendering_panel.vtk_renderer
            if hasattr(renderer, 'set_pet_opacity_scale'):
                renderer.set_pet_opacity_scale(scale)

    # ── TF 파일 공통 유틸 ────────────────────────────────────────

    def _apply_tf_to_widget(self, widget, tf_nodes):
        """TF 노드를 위젯에 적용"""
        try:
            if hasattr(widget, 'set_transfer_function_from_array'):
                widget.set_transfer_function_from_array(tf_nodes)
        except Exception as e:
            print(f"TF 위젯 적용 실패: {e}")

    def _save_tf(self, widget, label):
        file_path, _ = QFileDialog.getSaveFileName(
            self, f"Save {label} Transfer Function",
            f"./resources/TFs/TF_{label.lower()}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith('.json'):
            file_path += '.json'
        try:
            data = {'nodes': widget.get_nodes(), 'modality': label, 'version': '3.1'}
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            self.emit_status(f"{label} TF saved: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {str(e)}")

    def _load_tf_file(self, label):
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Load {label} Transfer Function", "./resources/TFs",
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return None
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            # 새 포맷 (nodes 키) 또는 구 포맷 (global 키) 모두 지원
            if 'nodes' in data:
                return data['nodes']
            elif 'global' in data:
                return data['global']
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load: {str(e)}")
        return None

    # ── 볼륨 데이터 설정 ─────────────────────────────────────────

    def set_volume_data(self, volume_data):
        """CT 볼륨 데이터 설정 (히스토그램용)"""
        self.volume_data = volume_data
        if volume_data is not None:
            self.ct_tf_widget.set_volume_data(volume_data)
            if self.clipping_panel and hasattr(volume_data, 'shape'):
                self.clipping_panel.set_volume_shape(volume_data.shape)

    def set_pet_volume_data(self, volume_data):
        """PET 볼륨 데이터 설정 (히스토그램용)"""
        self.pet_volume_data = volume_data
        if volume_data is not None:
            self.pet_tf_widget.set_volume_data(volume_data)
            # PET 탭으로 자동 전환
            self.tf_tab.setCurrentIndex(1)

    # ── 배경색 ───────────────────────────────────────────────────

    def select_background_color(self):
        color = QColorDialog.getColor(QColor(255, 255, 255), self, "배경색 선택")
        if color.isValid():
            bg = (color.red()/255.0, color.green()/255.0, color.blue()/255.0)
            self.bg_color_btn.setStyleSheet(f"background-color: {color.name()};")
            self.background_color_changed.emit(bg, bg)

    def reset_background_color(self):
        bg = (1.0, 1.0, 1.0)
        self.bg_color_btn.setStyleSheet("background-color: #FFFFFF;")
        self.background_color_changed.emit(bg, bg)

    # ── Shading 컨트롤 ───────────────────────────────────────────

    def _setup_shading_controls(self):
        shading_widget = QWidget()
        shading_widget.setStyleSheet("""
            QWidget { border: 1px solid #555; border-radius: 5px; background-color: rgba(64,64,64,50); }
        """)
        shading_layout = QVBoxLayout(shading_widget)
        shading_layout.setContentsMargins(0, 0, 0, 0)
        shading_layout.setSpacing(0)

        self.shade_header_btn = QPushButton("▶ Shading Controls")
        self.shade_header_btn.setCheckable(True)
        self.shade_header_btn.setChecked(False)
        self.shade_header_btn.clicked.connect(self.toggle_shading_section)
        self.shade_header_btn.setStyleSheet("""
            QPushButton { text-align:left; border:none; background:#404040; color:white;
                          padding:10px; font-weight:bold; border-radius:5px; }
            QPushButton:hover { background:#505050; }
            QPushButton:checked { background:#606060; }
        """)
        shading_layout.addWidget(self.shade_header_btn)

        self.shade_content_widget = QWidget()
        self.shade_content_widget.setVisible(False)
        self.shade_content_widget.setStyleSheet("QWidget { border:none; background:transparent; }")
        shade_content_layout = QVBoxLayout(self.shade_content_widget)
        shade_content_layout.setContentsMargins(10, 10, 10, 10)
        shade_content_layout.setSpacing(8)

        self.shade_toggle = QCheckBox("Enable Shading")
        self.shade_toggle.setChecked(False)
        self.shade_toggle.stateChanged.connect(self.on_shading_changed)
        self.shade_toggle.setStyleSheet("""
            QCheckBox { spacing:5px; color:white; }
            QCheckBox::indicator { width:13px; height:13px; border:1px solid #777;
                                   background:#353535; border-radius:3px; }
            QCheckBox::indicator:checked { background:#0078d7; }
        """)
        shade_content_layout.addWidget(self.shade_toggle)

        lighting_widget = QWidget()
        lighting_main_layout = QHBoxLayout(lighting_widget)
        lighting_main_layout.setContentsMargins(20, 0, 0, 0)
        lighting_main_layout.setSpacing(15)

        self.light_sphere = LightSphereWidget()
        self.light_sphere.setEnabled(False)
        self.light_sphere.setFixedSize(80, 80)
        self.light_sphere.light_changed.connect(self.on_light_direction_changed)
        lighting_main_layout.addWidget(self.light_sphere)

        sliders_widget = QWidget()
        sliders_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sliders_layout = QVBoxLayout(sliders_widget)
        sliders_layout.setContentsMargins(0, 0, 0, 0)
        sliders_layout.setSpacing(5)

        self.ambient_slider, self.ambient_label, self.ambient_color_btn = self._create_lighting_row(
            sliders_layout, "Ambient:", 40, self.on_ambient_changed, self.on_ambient_color_clicked)
        self.diffuse_slider, self.diffuse_label, self.diffuse_color_btn = self._create_lighting_row(
            sliders_layout, "Diffuse:", 60, self.on_diffuse_changed, self.on_diffuse_color_clicked, max_val=500)
        self.specular_slider, self.specular_label, self.specular_color_btn = self._create_lighting_row(
            sliders_layout, "Specular:", 20, self.on_specular_changed, self.on_specular_color_clicked)

        self.follow_camera_checkbox = QCheckBox("Follow Camera")
        self.follow_camera_checkbox.setChecked(False)
        self.follow_camera_checkbox.setEnabled(False)
        self.follow_camera_checkbox.toggled.connect(self.on_follow_camera_changed)
        self.follow_camera_checkbox.setStyleSheet(self.shade_toggle.styleSheet())
        sliders_layout.addWidget(self.follow_camera_checkbox)

        lighting_main_layout.addWidget(sliders_widget, 1)
        shade_content_layout.addWidget(lighting_widget)
        shading_layout.addWidget(self.shade_content_widget)
        self.content_layout.addWidget(shading_widget)

    def _create_lighting_row(self, parent_layout, label_text, default_val,
                              slider_callback, color_callback, max_val=100):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        label_fixed = QLabel(label_text)
        label_fixed.setMinimumWidth(60)
        layout.addWidget(label_fixed)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, max_val)
        slider.setValue(default_val)
        slider.valueChanged.connect(slider_callback)
        slider.setEnabled(False)
        layout.addWidget(slider, 1)
        value_label = QLabel(f"{default_val/100:.1f}")
        value_label.setMinimumWidth(30)
        layout.addWidget(value_label)
        color_btn = QPushButton()
        color_btn.setFixedSize(20, 20)
        color_btn.setStyleSheet("background-color: white; border: 1px solid gray;")
        color_btn.clicked.connect(color_callback)
        color_btn.setEnabled(False)
        layout.addWidget(color_btn)
        parent_layout.addWidget(widget)
        return slider, value_label, color_btn

    # ── Clipping 컨트롤 ──────────────────────────────────────────

    def _setup_clipping_controls(self):
        clipping_widget = QWidget()
        clipping_widget.setStyleSheet("""
            QWidget { border:1px solid #555; border-radius:5px; background-color:rgba(64,64,64,50); }
        """)
        clipping_layout = QVBoxLayout(clipping_widget)
        clipping_layout.setContentsMargins(0, 0, 0, 0)
        clipping_layout.setSpacing(0)

        self.clip_header_btn = QPushButton("▶ Clipping Controls")
        self.clip_header_btn.setCheckable(True)
        self.clip_header_btn.setChecked(False)
        self.clip_header_btn.clicked.connect(self.toggle_clipping_section)
        self.clip_header_btn.setStyleSheet(self.shade_header_btn.styleSheet())
        clipping_layout.addWidget(self.clip_header_btn)

        self.clip_content_widget = QWidget()
        self.clip_content_widget.setVisible(False)
        self.clip_content_widget.setStyleSheet("QWidget { border:none; background:transparent; }")
        clip_content_layout = QVBoxLayout(self.clip_content_widget)
        clip_content_layout.setContentsMargins(10, 10, 10, 10)
        clip_content_layout.setSpacing(10)

        self.clipping_panel = ClippingPanel()
        self.clipping_panel.setTitle("")
        self.clipping_panel.setStyleSheet("QGroupBox { border:none; margin-top:0; padding-top:0; }")
        self.clipping_panel.clipping_changed.connect(self.clipping_changed.emit)
        self.clipping_panel.clipping_enabled_changed.connect(self.clipping_enabled_changed.emit)

        clip_content_layout.addWidget(self.clipping_panel)
        clipping_layout.addWidget(self.clip_content_widget)
        self.content_layout.addWidget(clipping_widget)

    # ── 섹션 토글 ────────────────────────────────────────────────

    def toggle_shading_section(self):
        is_expanded = self.shade_header_btn.isChecked()
        if is_expanded and self.clip_header_btn.isChecked():
            self.clip_header_btn.setChecked(False)
            self.clip_content_widget.setVisible(False)
            self.clip_header_btn.setText("▶ Clipping Controls")
        self.shade_header_btn.setText(("▼ " if is_expanded else "▶ ") + "Shading Controls")
        self.shade_content_widget.setVisible(is_expanded)

    def toggle_clipping_section(self):
        is_expanded = self.clip_header_btn.isChecked()
        if is_expanded and self.shade_header_btn.isChecked():
            self.shade_header_btn.setChecked(False)
            self.shade_content_widget.setVisible(False)
            self.shade_header_btn.setText("▶ Shading Controls")
        self.clip_header_btn.setText(("▼ " if is_expanded else "▶ ") + "Clipping Controls")
        self.clip_content_widget.setVisible(is_expanded)

    # ── Shading 이벤트 ───────────────────────────────────────────

    def on_shading_changed(self, state):
        enabled = bool(state)
        self._set_lighting_sliders_enabled(enabled)
        self.shading_changed.emit(enabled)

    def _set_lighting_sliders_enabled(self, enabled):
        self.ambient_slider.setEnabled(enabled)
        self.diffuse_slider.setEnabled(enabled)
        self.specular_slider.setEnabled(enabled)
        self.light_sphere.setEnabled(enabled)
        self.follow_camera_checkbox.setEnabled(enabled)
        self.ambient_color_btn.setEnabled(enabled)
        self.diffuse_color_btn.setEnabled(enabled)
        self.specular_color_btn.setEnabled(enabled)

    def on_ambient_changed(self, v):
        self.ambient_label.setText(f"{v/100:.1f}")
        self.lighting_changed.emit("ambient", v/100.0)

    def on_diffuse_changed(self, v):
        self.diffuse_label.setText(f"{v/100:.1f}")
        self.lighting_changed.emit("diffuse", v/100.0)

    def on_specular_changed(self, v):
        self.specular_label.setText(f"{v/100:.1f}")
        self.lighting_changed.emit("specular", v/100.0)

    def on_light_direction_changed(self, x, y, z):
        self.light_direction_changed.emit(x, y, z)

    def on_follow_camera_changed(self, checked):
        self.follow_camera_changed.emit(checked)

    def on_ambient_color_clicked(self):
        c = QColorDialog.getColor(Qt.GlobalColor.white, self, "Select Ambient Color")
        if c.isValid():
            self.ambient_color_btn.setStyleSheet(f"background-color:{c.name()};border:1px solid gray;")
            self.ambient_color_changed.emit(c.redF(), c.greenF(), c.blueF())

    def on_diffuse_color_clicked(self):
        c = QColorDialog.getColor(Qt.GlobalColor.white, self, "Select Diffuse Color")
        if c.isValid():
            self.diffuse_color_btn.setStyleSheet(f"background-color:{c.name()};border:1px solid gray;")
            self.diffuse_color_changed.emit(c.redF(), c.greenF(), c.blueF())

    def on_specular_color_clicked(self):
        c = QColorDialog.getColor(Qt.GlobalColor.white, self, "Select Specular Color")
        if c.isValid():
            self.specular_color_btn.setStyleSheet(f"background-color:{c.name()};border:1px solid gray;")
            self.specular_color_changed.emit(c.redF(), c.greenF(), c.blueF())

    # ── 클리핑 유틸 ──────────────────────────────────────────────

    def reset_clipping_safe(self):
        if self.clipping_panel is not None:
            self.clipping_panel.reset_clipping()

    def get_clipping_ranges(self):
        if self.clipping_panel:
            return self.clipping_panel.get_clipping_ranges()
        return None

    # ── 기존 단일 TF 인터페이스 유지 ─────────────────────────────

    def on_tf_widget_changed(self):
        """기존 호환용"""
        self.on_ct_tf_changed()

    def reset_tf(self):
        self.reset_ct_tf()

    def save_tf(self):
        self.save_ct_tf()

    def load_tf(self):
        self.load_ct_tf()

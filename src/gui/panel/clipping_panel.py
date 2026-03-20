"""
Volume Clipping Panel
6방향 볼륨 클리핑 컨트롤 패널 - tf_panel.py에서 분리됨
"""

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, 
    QSlider, QGroupBox, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt

class ClippingPanel(QGroupBox):
    """6방향 볼륨 클리핑 컨트롤 패널"""
    
    # 클리핑 변경 시그널 - (axis, min_value, max_value)
    clipping_changed = pyqtSignal(str, float, float)
    clipping_enabled_changed = pyqtSignal(bool)
    
    def __init__(self):
        super().__init__("Volume Clipping")
        
        # 클리핑 범위 (정규화된 값 0.0 ~ 1.0)
        self.clipping_ranges = {
            'x': [0.0, 1.0],
            'y': [0.0, 1.0], 
            'z': [0.0, 1.0]
        }
        
        # 실제 볼륨 크기
        self.volume_shape = None
        
        # UI 요소들
        self.enable_checkbox = None
        self.sliders = {}
        self.value_labels = {}
        self.reset_buttons = {}
        self.reset_all_btn = None # __init__에 추가
        
        self.setup_ui()
        
    def setup_ui(self):
        """UI 구성"""
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        
        # 클리핑 활성화 체크박스
        self.enable_checkbox = QCheckBox("Enable Clipping")
        self.enable_checkbox.setChecked(False)
        self.enable_checkbox.toggled.connect(self.on_clipping_enabled_changed)
        layout.addWidget(self.enable_checkbox)
        # ⭐ 여기에 Shading 체크박스와 동일한 스타일을 추가합니다.
        self.enable_checkbox.setStyleSheet("""
            QCheckBox {
                spacing: 5px;
                color: white; /* 텍스트 색상 */
            }
            QCheckBox::indicator {
                width: 13px;
                height: 13px;
                border: 1px solid #777; /* 체크 박스 테두리 */
                background-color: #353535; /* 체크 박스 내부 배경 (빈 상태) */
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d7; /* 체크됐을 때 배경색 */
                /* image: url(path_to_a_checkmark_icon.png); */ 
            }
        """)
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # 각 축에 대한 클리핑 컨트롤
        axes_info = [
            ('X', 'x', 'Left/Right'),
            ('Y', 'y', 'Front/Back'),
            ('Z', 'z', 'Top/Bottom')
        ]
        
        for axis_label, axis_key, direction_label in axes_info:
            # 축 라벨
            axis_title = QLabel(f"{axis_label}-Axis ({direction_label})")
            # axis_title.setFont(QFont("", 9, QFont.Weight.Bold))
            layout.addWidget(axis_title)
            
            # Min 슬라이더
            min_layout = QHBoxLayout()
            min_label = QLabel("Min:")
            min_label.setFixedWidth(35)
            min_layout.addWidget(min_label)
            
            min_slider = QSlider(Qt.Orientation.Horizontal)
            min_slider.setRange(0, 1000)
            min_slider.setValue(0)
            min_slider.setEnabled(False)
            min_slider.valueChanged.connect(
                lambda v, ax=axis_key, is_min=True: self.on_slider_changed(ax, is_min, v)
            )
            self.sliders[f"{axis_key}_min"] = min_slider
            min_layout.addWidget(min_slider)
            
            min_value_label = QLabel("0")
            min_value_label.setFixedWidth(40)
            min_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.value_labels[f"{axis_key}_min"] = min_value_label
            min_layout.addWidget(min_value_label)
            
            layout.addLayout(min_layout)
            
            # Max 슬라이더
            max_layout = QHBoxLayout()
            max_label = QLabel("Max:")
            max_label.setFixedWidth(35)
            max_layout.addWidget(max_label)
            
            max_slider = QSlider(Qt.Orientation.Horizontal)
            max_slider.setRange(0, 1000)
            max_slider.setValue(1000)
            max_slider.setEnabled(False)
            max_slider.valueChanged.connect(
                lambda v, ax=axis_key, is_min=False: self.on_slider_changed(ax, is_min, v)
            )
            self.sliders[f"{axis_key}_max"] = max_slider
            max_layout.addWidget(max_slider)
            
            max_value_label = QLabel("100")
            max_value_label.setFixedWidth(40)
            max_value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.value_labels[f"{axis_key}_max"] = max_value_label
            max_layout.addWidget(max_value_label)
            
            layout.addLayout(max_layout)
            
            # 축 간 간격
            if axis_key != 'z':
                spacer_line = QFrame()
                spacer_line.setFrameShape(QFrame.Shape.HLine)
                spacer_line.setFrameShadow(QFrame.Shadow.Sunken)
                spacer_line.setStyleSheet("QFrame { margin: 5px 0px; }")
                layout.addWidget(spacer_line)
        
        # 전체 리셋 버튼
        # reset_all_btn = QPushButton("Reset All Axes")
        # reset_all_btn.setEnabled(False)
        # reset_all_btn.clicked.connect(self.reset_all_axes)
        # reset_all_btn.setStyleSheet("""
        #     QPushButton {
        #         background-color: #f44336;
        #         color: white;
        #         font-weight: bold;
        #         padding: 5px;
        #     }
        #     QPushButton:hover {
        #         background-color: #da190b;
        #     }
        #     QPushButton:disabled {
        #         background-color: #cccccc;
        #         color: #666666;
        #     }
        # """)
        # self.reset_all_btn = reset_all_btn
        # layout.addWidget(reset_all_btn)
        
        # 하단 여백
        layout.addStretch()
        
    def on_clipping_enabled_changed(self, enabled):
        """클리핑 활성화/비활성화 처리"""
        for slider in self.sliders.values():
            slider.setEnabled(enabled)
        # self.reset_all_btn.setEnabled(enabled)
        
        self.clipping_enabled_changed.emit(enabled)
        
        # if not enabled:
        #     # 체크 해제 시: 모든 축 리셋 및 시그널 발생 (정상)
        #     self.reset_all_axes() 
        
        # ⭐ 추가된 코드: 다시 활성화될 때 (enabled=True)
        # 현재의 클리핑 범위(리셋된 0.0, 1.0)를 렌더러에 다시 적용하도록 시그널을 강제로 보냅니다.
        if enabled:
            for axis in ['x', 'y', 'z']:
                min_val = self.clipping_ranges[axis][0]
                max_val = self.clipping_ranges[axis][1]
                # 이 시그널을 받으면 렌더러는 클리핑을 0.0~1.0으로 설정합니다.
                self.clipping_changed.emit(axis, min_val, max_val)
            
    def on_slider_changed(self, axis, is_min, value):
        """슬라이더 값 변경 처리"""
        normalized_value = value / 1000.0
        
        key = f"{axis}_{'min' if is_min else 'max'}"
        other_key = f"{axis}_{'max' if is_min else 'min'}"
        
        # 범위 검증 (min은 max보다 작아야 함)
        if is_min:
            max_value = self.sliders[other_key].value() / 1000.0
            if normalized_value > max_value:
                normalized_value = max_value
                self.sliders[key].setValue(int(normalized_value * 1000))
        else:
            min_value = self.sliders[other_key].value() / 1000.0
            if normalized_value < min_value:
                normalized_value = min_value
                self.sliders[key].setValue(int(normalized_value * 1000))
        
        # 클리핑 범위 업데이트
        if is_min:
            self.clipping_ranges[axis][0] = normalized_value
        else:
            self.clipping_ranges[axis][1] = normalized_value
        
        self.update_value_label(axis, is_min)
        
        # 시그널 발생
        self.clipping_changed.emit(
            axis, 
            self.clipping_ranges[axis][0],
            self.clipping_ranges[axis][1]
        )
        
    def update_value_label(self, axis, is_min):
        """값 라벨 업데이트 - 물리적 좌표 표시"""
        key = f"{axis}_{'min' if is_min else 'max'}"
        value = self.sliders[key].value() / 1000.0
        
        # 실제 물리적 bounds 가져오기 (있다면)
        if hasattr(self.parent(), 'rendering_panel') and self.parent().rendering_panel:
            renderer = self.parent().rendering_panel.vtk_renderer
            if renderer and hasattr(renderer.clipping_manager, 'get_current_volume'):
                volume = renderer.clipping_manager.get_current_volume()
                if volume and volume.GetMapper() and volume.GetMapper().GetInput():
                    bounds = volume.GetMapper().GetInput().GetBounds()
                    
                    if axis == 'x':
                        actual_value = bounds[0] + value * (bounds[1] - bounds[0])
                    elif axis == 'y':
                        actual_value = bounds[2] + value * (bounds[3] - bounds[2])
                    else:  # z
                        actual_value = bounds[4] + value * (bounds[5] - bounds[4])
                    
                    self.value_labels[key].setText(f"{actual_value:.1f}")
                    return
        
        # Fallback: 퍼센트로 표시
        self.value_labels[key].setText(f"{int(value * 100)}%")
            
    def reset_axis(self, axis):
        """특정 축 리셋"""
        self.sliders[f"{axis}_min"].setValue(0)
        self.sliders[f"{axis}_max"].setValue(1000)
        self.clipping_ranges[axis] = [0.0, 1.0]
        
        # 시그널 발생
        self.clipping_changed.emit(axis, 0.0, 1.0)
        
    def reset_all_axes(self):
        """모든 축 리셋"""
        for axis in ['x', 'y', 'z']:
            self.reset_axis(axis)

    def reset_clipping(self):
        """클리핑 리셋"""
        for axis in ['x', 'y', 'z']:
            self.reset_axis(axis)
        
        # 활성화된 클릭도 비활성화
        self.enable_checkbox.setChecked(False)
            
    def set_volume_shape(self, shape):
        """볼륨 크기 설정"""
        self.volume_shape = shape
        
        # 모든 라벨 업데이트
        for axis in ['x', 'y', 'z']:
            self.update_value_label(axis, True)
            self.update_value_label(axis, False)
            
    def get_clipping_ranges(self):
        """현재 클리핑 범위 반환"""
        return self.clipping_ranges.copy()
    
    def set_clipping_ranges(self, ranges):
        """클리핑 범위 설정"""
        if not ranges:
            return
            
        for axis in ['x', 'y', 'z']:
            if axis in ranges:
                min_val, max_val = ranges[axis]
                self.clipping_ranges[axis] = [min_val, max_val]
                self.sliders[f"{axis}_min"].setValue(int(min_val * 1000))
                self.sliders[f"{axis}_max"].setValue(int(max_val * 1000))
                self.update_value_label(axis, True)
                self.update_value_label(axis, False)

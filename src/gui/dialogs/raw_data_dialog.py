"""
Raw Data Import Dialog
Raw 볼륨 데이터 로드 파라미터 다이얼로그 - file_panel.py에서 분리됨
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox, QPushButton
)


# Raw Data Dialog (기존 코드 재사용)
class RawDataDialog(QDialog):
    """Raw 데이터 로드 파라미터 다이얼로그"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Raw Data Parameters")
        self.setModal(True)
        self.resize(450, 400)
        self.setup_ui()
    
    def setup_ui(self):
        """UI 설정"""
        layout = QVBoxLayout(self)
        
        # 제목
        title = QLabel("Raw Volume Data Import")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)
        
        # 차원 설정
        dims_group = QGroupBox("Volume Dimensions")
        dims_layout = QHBoxLayout(dims_group)
        
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 2048)
        self.width_spin.setValue(256)
        dims_layout.addWidget(QLabel("Width:"))
        dims_layout.addWidget(self.width_spin)
        
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 2048)
        self.height_spin.setValue(256)
        dims_layout.addWidget(QLabel("Height:"))
        dims_layout.addWidget(self.height_spin)
        
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(1, 2048)
        self.depth_spin.setValue(256)
        dims_layout.addWidget(QLabel("Depth:"))
        dims_layout.addWidget(self.depth_spin)
        
        layout.addWidget(dims_group)
        
        # 데이터 타입과 Endian
        controls_group = QGroupBox("Data Format")
        controls_layout = QVBoxLayout(controls_group)
        
        # 데이터 타입
        dtype_layout = QHBoxLayout()
        dtype_layout.addWidget(QLabel("Data Type:"))
        self.dtype_combo = QComboBox()
        self.dtype_combo.addItems([
            "uint8", "int8", "uint16", "int16", 
            "uint32", "int32", "float32", "float64"
        ])
        self.dtype_combo.setCurrentText("uint8")
        dtype_layout.addWidget(self.dtype_combo)
        controls_layout.addLayout(dtype_layout)
        
        # Endian
        endian_layout = QHBoxLayout()
        endian_layout.addWidget(QLabel("Byte Order:"))
        self.endian_combo = QComboBox()
        self.endian_combo.addItems(["little", "big", "native"])
        self.endian_combo.setCurrentText("little")
        endian_layout.addWidget(self.endian_combo)
        controls_layout.addLayout(endian_layout)
        
        layout.addWidget(controls_group)
        
        # Voxel Spacing
        spacing_group = QGroupBox("Voxel Spacing (mm)")
        spacing_layout = QVBoxLayout(spacing_group)
        
        # X, Y, Z Spacing
        for axis in ['X', 'Y', 'Z']:
            axis_layout = QHBoxLayout()
            axis_layout.addWidget(QLabel(f"{axis} Spacing:"))
            spacing_spin = QDoubleSpinBox()
            spacing_spin.setRange(0.001, 5.0)
            spacing_spin.setValue(1.0)
            spacing_spin.setDecimals(4)
            axis_layout.addWidget(spacing_spin)
            spacing_layout.addLayout(axis_layout)
            
            setattr(self, f'spacing_{axis.lower()}', spacing_spin)
        
        layout.addWidget(spacing_group)
        
        # 예상 파일 크기 표시
        self.size_label = QLabel()
        self.update_size_estimate()
        layout.addWidget(self.size_label)
        
        # 차원 변경 시 크기 업데이트 연결
        for spin in [self.width_spin, self.height_spin, self.depth_spin]:
            spin.valueChanged.connect(self.update_size_estimate)
        self.dtype_combo.currentTextChanged.connect(self.update_size_estimate)
        
        # 버튼들
        button_layout = QHBoxLayout()
        
        ok_btn = QPushButton("Import")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def update_size_estimate(self):
        """예상 파일 크기 계산"""
        w, h, d = self.width_spin.value(), self.height_spin.value(), self.depth_spin.value()
        dtype = self.dtype_combo.currentText()
        
        dtype_sizes = {
            'uint8': 1, 'int8': 1, 'uint16': 2, 'int16': 2,
            'uint32': 4, 'int32': 4, 'float32': 4, 'float64': 8
        }
        
        total_bytes = w * h * d * dtype_sizes.get(dtype, 4)
        
        if total_bytes < 1024:
            size_str = f"{total_bytes} bytes"
        elif total_bytes < 1024**2:
            size_str = f"{total_bytes/1024:.1f} KB"
        elif total_bytes < 1024**3:
            size_str = f"{total_bytes/(1024**2):.1f} MB"
        else:
            size_str = f"{total_bytes/(1024**3):.1f} GB"
        
        self.size_label.setText(f"Expected file size: {size_str}")
        self.size_label.setStyleSheet("color: #607D8B; font-style: italic;")
    
    def get_parameters(self):
        """파라미터 반환"""
        return {
            'shape': (self.width_spin.value(), self.height_spin.value(), self.depth_spin.value()),
            'dtype_str': self.dtype_combo.currentText(),
            'endian': self.endian_combo.currentText(),
            'voxel_spacing': (self.spacing_x.value(), self.spacing_y.value(), self.spacing_z.value())
        }
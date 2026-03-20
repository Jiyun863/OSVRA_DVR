"""
간결화된 파일 로드 패널 - 볼륨 로드 기능만
"""

import os
import numpy as np
from PyQt6.QtWidgets import *
from PyQt6.QtCore import pyqtSignal, Qt

from src.gui.panel.base_panel import BasePanel
from src.gui.dialogs.raw_data_dialog import RawDataDialog
from src.gui.data.volume_loader import VolumeLoader


class FilePanel(BasePanel):
    """간결화된 파일 로드 패널"""
    
    # 시그널 정의
    volume_loaded = pyqtSignal(object)   # 기존 호환용
    ct_loaded = pyqtSignal(object)       # ★ CT 로드 완료
    pet_loaded = pyqtSignal(object)      # ★ PET 로드 완료
    pet_cleared = pyqtSignal()           # ★ PET 제거
    
    def __init__(self):
        super().__init__("Load Data", collapsible=False)
        self.volume_loader = VolumeLoader() 
        self.volume_data = None
        self.voxel_spacing = (1.0, 1.0, 1.0)
        self.pet_volume_data = None        # ★ 추가
        self.pet_voxel_spacing = (1.0, 1.0, 1.0)  # ★ 추가
        
    def setup_content(self):
        """내용 설정"""
        btn_style_ct = """
            QPushButton { 
                background-color: #2196F3;
                color: white;
                font-weight: bold; 
                border-radius: 5px; 
                font-size: 13px; 
            }
            QPushButton:hover {
                background-color: #1976D2; 
            }
        """
        btn_style_pet = """
            QPushButton { 
                background-color: #e53935; 
                color: white; 
                font-weight: bold; 
                border-radius: 5px; 
                font-size: 13px; 
            }
            QPushButton:hover {
                background-color: #b71c1c; 
            }
        """
        btn_style_clear = """
            QPushButton { background-color: #555; color: white; font-weight: bold; border-radius: 5px; font-size: 11px; }
            QPushButton:hover { background-color: #777; }
        """

        # ── CT ──
        self.load_ct_btn = QPushButton("📂 Load CT Volume")
        self.load_ct_btn.setMinimumHeight(40)
        self.load_ct_btn.setStyleSheet(btn_style_ct)
        self.load_ct_btn.clicked.connect(self.load_ct_data)
        self.content_layout.addWidget(self.load_ct_btn)

        self.ct_info_label = QLabel("No CT volume loaded")
        self.ct_info_label.setStyleSheet("color: #888; padding: 5px;")
        self.ct_info_label.setWordWrap(True)
        self.content_layout.addWidget(self.ct_info_label)

        # ── 구분선 ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #555;")
        self.content_layout.addWidget(line)

        # ── PET ──
        pet_row = QHBoxLayout()
        self.load_pet_btn = QPushButton("🔴 Load PET Volume")
        self.load_pet_btn.setMinimumHeight(40)
        self.load_pet_btn.setStyleSheet(btn_style_pet)
        self.load_pet_btn.clicked.connect(self.load_pet_data)
        pet_row.addWidget(self.load_pet_btn)

        self.clear_pet_btn = QPushButton("✕")
        self.clear_pet_btn.setFixedSize(40, 40)
        self.clear_pet_btn.setStyleSheet(btn_style_clear)
        self.clear_pet_btn.clicked.connect(self.clear_pet_data)
        pet_row.addWidget(self.clear_pet_btn)
        self.content_layout.addLayout(pet_row)

        self.pet_info_label = QLabel("No PET volume loaded")
        self.pet_info_label.setStyleSheet("color: #888; padding: 5px;")
        self.pet_info_label.setWordWrap(True)
        self.content_layout.addWidget(self.pet_info_label)

        # 기존 호환용 (volume_loaded 시그널 쓰는 코드 있을 경우)
        self.load_volume_btn = self.load_ct_btn
        self.info_label = self.ct_info_label
    
    def _load_file(self, file_path):
        """★ 공통 파일 로드 로직"""
        raw_params = None
        if file_path.endswith(('.raw', '.dat')):
            dialog = RawDataDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                raw_params = dialog.get_parameters()
            else:
                self.emit_status("Raw data load cancelled")
                return None, None
        volume_data, voxel_spacing = self.volume_loader.load(file_path, raw_params)
        if volume_data is None:
            raise ValueError("볼륨 데이터 처리 실패")
        return volume_data, voxel_spacing

    def load_ct_data(self):
        """★ CT 볼륨 로드"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Volume Data", "./resources/Volume_Data", 
            "All Supported Files (*.nii *.nii.gz *.npy *.raw *.dat);;"
            "Volume Files (*.nii *.nii.gz *.npy);;"
            "Raw Files (*.raw *.dat);;"
            "All Files (*)"
        )
        if not file_path:
            return
        try:
            self.volume_data, self.voxel_spacing = self._load_file(file_path)
            if self.volume_data is None:
                return
            filename = os.path.basename(file_path)
            shape = self.volume_data.shape
            s = self.voxel_spacing
            self.ct_info_label.setText(
                f"📊 {filename}\n"
                f"Shape: {shape[0]} × {shape[1]} × {shape[2]}\n"
                f"Spacing: {s[0]:.2f} × {s[1]:.2f} × {s[2]:.2f}"
            )
            self.ct_info_label.setStyleSheet("color: #4CAF50; padding: 5px;")
            self.volume_loaded.emit(self.volume_data)   # 기존 호환
            self.ct_loaded.emit(self.volume_data)
            self.emit_status(f"CT loaded: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load CT: {str(e)}")
            self.ct_info_label.setText(f"❌ Load failed: {str(e)}")
            self.ct_info_label.setStyleSheet("color: #f44336; padding: 5px;")

    def load_pet_data(self):
        """★ PET 볼륨 로드"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Volume Data", "./resources/Volume_Data", 
            "All Supported Files (*.nii *.nii.gz *.npy *.raw *.dat);;"
            "Volume Files (*.nii *.nii.gz *.npy);;"
            "Raw Files (*.raw *.dat);;"
            "All Files (*)"
        )
        if not file_path:
            return
        try:
            self.pet_volume_data, self.pet_voxel_spacing = self._load_file(file_path)
            if self.pet_volume_data is None:
                return
            filename = os.path.basename(file_path)
            shape = self.pet_volume_data.shape
            s = self.pet_voxel_spacing
            self.pet_info_label.setText(
                f"🔴 {filename}\n"
                f"Shape: {shape[0]} × {shape[1]} × {shape[2]}\n"
                f"Spacing: {s[0]:.2f} × {s[1]:.2f} × {s[2]:.2f}"
            )
            self.pet_info_label.setStyleSheet("color: #ef9a9a; padding: 5px;")
            self.pet_loaded.emit(self.pet_volume_data)
            self.emit_status(f"PET loaded: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load PET: {str(e)}")
            self.pet_info_label.setText(f"❌ Load failed: {str(e)}")
            self.pet_info_label.setStyleSheet("color: #f44336; padding: 5px;")

    def clear_pet_data(self):
        """★ PET 볼륨 제거"""
        self.pet_volume_data = None
        self.pet_voxel_spacing = (1.0, 1.0, 1.0)
        self.pet_info_label.setText("No PET volume loaded")
        self.pet_info_label.setStyleSheet("color: #888; padding: 5px;")
        self.pet_cleared.emit()

   
"""
OSVRA Debug View Dialog
파이프라인 중간 결과 5개를 2행 그리드로 표시
"""

import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap


class _DebugImageCell(QLabel):
    """제목 + 이미지 표시 셀 (240×240 고정)"""

    CELL_SIZE = 240

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(self.CELL_SIZE, self.CELL_SIZE)
        self.setStyleSheet(
            "background-color: #111; border: 1px solid #555; color: #888; font-size: 11px;"
        )
        self._title = title
        self._pixmap_cache = None
        self.setText(title)

    def set_array(self, arr: np.ndarray):
        """numpy 배열을 QImage로 변환하여 표시

        Args:
            arr: (H,W) float [0,1] grayscale  or  (H,W,4) float [0,1] RGBA
        """
        if arr is None or arr.size == 0:
            self.setText(f"{self._title}\n(empty)")
            return

        if arr.ndim == 2:
            # grayscale → RGB
            arr_u8 = (arr * 255).clip(0, 255).astype(np.uint8)
            arr_rgb = np.ascontiguousarray(np.stack([arr_u8] * 3, axis=-1))
        else:
            # RGBA → RGB
            arr_rgb = np.ascontiguousarray((arr[..., :3] * 255).clip(0, 255).astype(np.uint8))

        h, w = arr_rgb.shape[:2]
        stride = arr_rgb.strides[0]
        qimg = QImage(arr_rgb.data, w, h, stride, QImage.Format.Format_RGB888).copy()
        self._pixmap_cache = QPixmap.fromImage(qimg)
        self._refresh()

    def set_depth_array(self, depth_map: np.ndarray):
        """depth map (NaN 포함) 표시. 전체 NaN 시 텍스트 표시."""
        d = np.nan_to_num(depth_map, nan=0.0)
        d_max = float(d.max())
        if d_max <= 0:
            self.setText(f"{self._title}\nNo occlusion hits")
            self._pixmap_cache = None
            return

        d_norm = (d / d_max * 255).clip(0, 255).astype(np.uint8)
        arr_rgb = np.ascontiguousarray(np.stack([d_norm] * 3, axis=-1))
        h, w = arr_rgb.shape[:2]
        stride = arr_rgb.strides[0]
        qimg = QImage(arr_rgb.data, w, h, stride, QImage.Format.Format_RGB888).copy()
        self._pixmap_cache = QPixmap.fromImage(qimg)
        self._refresh()

    def _refresh(self):
        if self._pixmap_cache is None:
            return
        self.setText("")
        scaled = self._pixmap_cache.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)


class OSVRADebugDialog(QDialog):
    """OSVRA 파이프라인 중간 결과 디버그 뷰 (non-modal)

    Args:
        debug_data: _osvra_debug_data dict from MainWindow
        parent: parent widget
    """

    def __init__(self, debug_data: dict, parent=None):
        super().__init__(parent)
        axis = debug_data.get('axis_name', '?')
        idx = debug_data.get('slice_index', '?')
        ts = debug_data.get('timestamp', '')
        self.setWindowTitle(f"OSVRA Debug — {axis} slice {idx}  [{ts}]")
        self.setMinimumSize(780, 560)
        self.resize(820, 600)
        self.setStyleSheet("background-color: #1e1e1e; color: #ddd;")

        self._build_ui(debug_data)

    def _build_ui(self, data: dict):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # Row 1: PET Slice, Depth Map
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._cell_pet_slice = _DebugImageCell("PET Slice")
        self._cell_depth_map = _DebugImageCell("Depth Map")

        for cell in (self._cell_pet_slice, self._cell_depth_map):
            col = self._wrap_with_title(cell, cell._title)
            row1.addLayout(col)
        row1.addStretch()

        # Row 2: CT Aug, PET RGBA, Fused
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self._cell_ct_aug = _DebugImageCell("CT Aug")
        self._cell_pet_rgba = _DebugImageCell("PET RGBA")
        self._cell_fused = _DebugImageCell("Fused")

        for cell in (self._cell_ct_aug, self._cell_pet_rgba, self._cell_fused):
            col = self._wrap_with_title(cell, cell._title)
            row2.addLayout(col)

        root.addLayout(row1)
        root.addLayout(row2)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet(
            "QPushButton { background: #444; color: #ddd; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background: #555; }"
        )
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        # Populate images
        self._populate(data)

    def _wrap_with_title(self, cell: _DebugImageCell, title: str) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #aaa; font-size: 11px; font-weight: bold;")
        col.addWidget(lbl)
        col.addWidget(cell)
        return col

    def _populate(self, data: dict):
        pet_slice = data.get('pet_slice')
        depth_map = data.get('depth_map')
        ct_aug = data.get('ct_aug')
        pet_rgba = data.get('pet_rgba')
        fused = data.get('fused')

        if pet_slice is not None:
            self._cell_pet_slice.set_array(pet_slice)
        if depth_map is not None:
            self._cell_depth_map.set_depth_array(depth_map)
        if ct_aug is not None:
            self._cell_ct_aug.set_array(ct_aug)
        if pet_rgba is not None:
            self._cell_pet_rgba.set_array(pet_rgba)
        if fused is not None:
            self._cell_fused.set_array(fused)

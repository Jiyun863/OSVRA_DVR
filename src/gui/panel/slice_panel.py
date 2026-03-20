"""
2D Slice Viewer Panel
볼륨 데이터를 Axial / Sagittal / Coronal 뷰로 슬라이싱하여 표시하는 패널
right_container 에 배치하여 사용
"""

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QButtonGroup, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont


# ──────────────────────────────────────────────────────────────
# SliceCanvas  :  QLabel 기반 이미지 표시 위젯
# ──────────────────────────────────────────────────────────────
class SliceCanvas(QLabel):
    """슬라이스 이미지를 렌더링하는 캔버스"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 200)
        self.setStyleSheet("background-color: #111111; border: 1px solid #444;")

        self._pixmap_cache = None  # 원본 픽스맵 캐시

        self._show_placeholder()

    # ── 외부 API ──────────────────────────────────────────────

    def set_slice_array(self, arr: np.ndarray):
        """
        arr : 2D numpy array (float 또는 int)
              값 범위는 임의 – 내부에서 [0, 255] 로 정규화
        """
        if arr is None or arr.size == 0:
            self._show_placeholder()
            return

        img_uint8 = self._normalize(arr)
        h, w = img_uint8.shape

        # numpy 배열을 contiguous로 보장하고 멤버에 보관 (GC 방지)
        self._img_data_ref = np.ascontiguousarray(img_uint8)
        qimage = QImage(self._img_data_ref.data, w, h, w, QImage.Format.Format_Grayscale8)
        qimage = qimage.copy()  # QImage가 자체 메모리 소유
        self._pixmap_cache = QPixmap.fromImage(qimage)
        self._update_display()

    def clear(self):
        self._pixmap_cache = None
        self._show_placeholder()

    # ── 내부 헬퍼 ─────────────────────────────────────────────

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        arr = arr.astype(np.float32)
        mn, mx = arr.min(), arr.max()
        if mx > mn:
            arr = (arr - mn) / (mx - mn) * 255.0
        else:
            arr = np.zeros_like(arr)
        return np.clip(arr, 0, 255).astype(np.uint8)

    def _show_placeholder(self):
        self.setText("No Volume Data")
        self.setStyleSheet(
            "background-color: #111111; border: 1px solid #444;"
            "color: #555; font-size: 14px;"
        )
        self._pixmap_cache = None

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
        self._update_display()


# ──────────────────────────────────────────────────────────────
# SliceViewerPanel  :  메인 패널
# ──────────────────────────────────────────────────────────────
class SliceViewerPanel(QWidget):
    """
    Axial / Sagittal / Coronal 슬라이스 뷰어 패널.
    main_window 의 right_container 에 addWidget 하여 사용.
    """

    # 외부로 현재 슬라이스 인덱스를 알릴 시그널 (필요 시 활용)
    slice_changed = pyqtSignal(str, int)   # (view_axis, index)

    # 축 이름 → numpy axis 인덱스 매핑
    #   볼륨 shape : (X, Y, Z)  기준 (실측 확인 결과)
    #   Axial    → axis 2  (Z 방향 슬라이싱)
    #   Coronal  → axis 1  (Y 방향 슬라이싱)
    #   Sagittal → axis 0  (X 방향 슬라이싱)
    _AXIS_MAP = {
        "Axial":    2,   # Z 축 슬라이싱
        "Coronal":  1,   # Y 축 슬라이싱
        "Sagittal": 0,   # X 축 슬라이싱
    }
    _AXIS_ORDER = ["Axial", "Coronal", "Sagittal"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.volume_data: np.ndarray | None = None
        self.current_axis: str = "Axial"
        self.current_index: int = 0

        self._build_ui()

    # ── UI 구성 ───────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # 제목
        title = QLabel("🔬  2D Slice Viewer")
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 6px 4px;"
        )
        root.addWidget(title)

        # ── 뷰 선택 버튼 3개 ──────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._view_buttons: dict[str, QPushButton] = {}
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        for name in self._AXIS_ORDER:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setStyleSheet(self._btn_style(active=False))
            btn.clicked.connect(lambda checked, n=name: self._on_view_clicked(n))
            self._view_buttons[name] = btn
            self._btn_group.addButton(btn)
            btn_row.addWidget(btn)

        self._view_buttons["Axial"].setChecked(True)
        self._view_buttons["Axial"].setStyleSheet(self._btn_style(active=True))

        root.addLayout(btn_row)

        # ── 캔버스 ────────────────────────────────────────────
        self.canvas = SliceCanvas()
        root.addWidget(self.canvas, stretch=1)

        # ── 슬라이더 영역 ─────────────────────────────────────
        slider_frame = QFrame()
        slider_frame.setStyleSheet(
            "QFrame { background-color: #2a2a2a; border-radius: 4px; }"
        )
        slider_layout = QVBoxLayout(slider_frame)
        slider_layout.setContentsMargins(8, 6, 8, 6)
        slider_layout.setSpacing(4)

        # 슬라이더 상단 레이블 행
        label_row = QHBoxLayout()
        self.axis_label = QLabel("Axial (Z)")
        self.axis_label.setStyleSheet("color: #aaa; font-size: 12px;")
        self.index_label = QLabel("0 / 0")
        self.index_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.index_label.setStyleSheet("color: #ccc; font-size: 12px;")
        label_row.addWidget(self.axis_label)
        label_row.addStretch()
        label_row.addWidget(self.index_label)
        slider_layout.addLayout(label_row)

        # 슬라이더
        self.slice_slider = QSlider(Qt.Orientation.Horizontal)
        self.slice_slider.setMinimum(0)
        self.slice_slider.setMaximum(0)
        self.slice_slider.setValue(0)
        self.slice_slider.setEnabled(False)
        self.slice_slider.valueChanged.connect(self._on_slider_changed)
        self.slice_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #444;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #2a82da;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background: #2a82da;
                border-radius: 3px;
            }
        """)
        slider_layout.addWidget(self.slice_slider)

        # 첫/끝 이동 버튼
        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)
        for label, delta in [("◀◀ First", "first"), ("◀ Prev", -1),
                              ("Next ▶", +1), ("Last ▶▶", "last")]:
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setStyleSheet(
                "QPushButton { font-size: 11px; padding: 0 6px; }"
                "QPushButton:disabled { color: #555; }"
            )
            b.clicked.connect(lambda _, d=delta: self._navigate(d))
            nav_row.addWidget(b)
        slider_layout.addLayout(nav_row)

        root.addWidget(slider_frame)

    # ── 스타일 헬퍼 ───────────────────────────────────────────

    @staticmethod
    def _btn_style(active: bool) -> str:
        if active:
            return (
                "QPushButton { background-color: #2a82da; color: white;"
                "font-weight: bold; border-radius: 4px; }"
            )
        return (
            "QPushButton { background-color: #3a3a3a; color: #ccc;"
            "border-radius: 4px; }"
            "QPushButton:hover { background-color: #4a4a4a; }"
        )

    # ── 공개 API ──────────────────────────────────────────────

    def set_volume_data(self, volume_data: np.ndarray):
        """
        볼륨 데이터 설정.
        nibabel 기준 shape : (X, Y, Z)
        """
        if volume_data is None:
            self.volume_data = None
            self.canvas.clear()
            self._reset_slider()
            return

        self.volume_data = volume_data

        # ── 진단 출력 (방향 디버깅용) ─────────────────────────
        print(f"[SliceViewer] volume shape : {volume_data.shape}")
        print(f"[SliceViewer] dtype        : {volume_data.dtype}")
        print(f"[SliceViewer] value range  : {volume_data.min():.1f} ~ {volume_data.max():.1f}")
        print(f"[SliceViewer] Axial slices (axis2): {volume_data.shape[2]}")
        print(f"[SliceViewer] Coronal slices (axis1): {volume_data.shape[1]}")
        print(f"[SliceViewer] Sagittal slices (axis0): {volume_data.shape[0]}")
        # ──────────────────────────────────────────────────────

        self._switch_axis(self.current_axis, reset_index=True)

    def clear(self):
        """볼륨 데이터 해제 및 초기화"""
        self.volume_data = None
        self.canvas.clear()
        self._reset_slider()

    # ── 내부 로직 ─────────────────────────────────────────────

    def _on_view_clicked(self, axis_name: str):
        """뷰 버튼 클릭"""
        # 버튼 스타일 갱신
        for name, btn in self._view_buttons.items():
            btn.setStyleSheet(self._btn_style(active=(name == axis_name)))
        self._switch_axis(axis_name, reset_index=True)

    def _switch_axis(self, axis_name: str, reset_index: bool = False):
        self.current_axis = axis_name
        axis_idx = self._AXIS_MAP[axis_name]

        axis_labels = {
            "Axial":    "Axial  (Z-axis)",
            "Coronal":  "Coronal  (Y-axis)",
            "Sagittal": "Sagittal  (X-axis)",
        }
        self.axis_label.setText(axis_labels[axis_name])

        if self.volume_data is None:
            self._reset_slider()
            return

        n_slices = self.volume_data.shape[axis_idx]

        # 슬라이더 범위 설정
        self.slice_slider.blockSignals(True)
        self.slice_slider.setMinimum(0)
        self.slice_slider.setMaximum(n_slices - 1)
        if reset_index:
            self.current_index = n_slices // 2
        self.current_index = max(0, min(self.current_index, n_slices - 1))
        self.slice_slider.setValue(self.current_index)
        self.slice_slider.setEnabled(True)
        self.slice_slider.blockSignals(False)

        self._render_slice()

    def _on_slider_changed(self, value: int):
        self.current_index = value
        self._render_slice()

    def _navigate(self, delta):
        if self.volume_data is None:
            return
        axis_idx = self._AXIS_MAP[self.current_axis]
        n = self.volume_data.shape[axis_idx]
        if delta == "first":
            new_idx = 0
        elif delta == "last":
            new_idx = n - 1
        else:
            new_idx = max(0, min(self.current_index + delta, n - 1))
        self.slice_slider.setValue(new_idx)  # valueChanged 가 _render_slice 호출

    def _render_slice(self):
        if self.volume_data is None:
            return

        axis_idx = self._AXIS_MAP[self.current_axis]
        n_slices = self.volume_data.shape[axis_idx]
        idx = max(0, min(self.current_index, n_slices - 1))

        slice_2d = np.take(self.volume_data, idx, axis=axis_idx)

        if self.current_axis == "Axial":
            slice_2d = slice_2d.T          # (X,Y) → (Y,X)
            # Z=0=Superior이고 Coronal이 맞으므로 Axial도 flip 불필요

        elif self.current_axis == "Coronal":
            slice_2d = slice_2d.T          # (X,Z) → (Z,X)
            # 이미 방향 맞음

        elif self.current_axis == "Sagittal":
            # flipud 제거: Z=0=Superior가 이미 위에 있으므로 뒤집지 않음
            slice_2d = slice_2d      # (Y,Z) → (Z,Y)

        self.canvas.set_slice_array(slice_2d)

        # 레이블 갱신
        self.index_label.setText(f"{idx} / {n_slices - 1}")
        self.slice_changed.emit(self.current_axis, idx)

    def _reset_slider(self):
        self.slice_slider.blockSignals(True)
        self.slice_slider.setMinimum(0)
        self.slice_slider.setMaximum(0)
        self.slice_slider.setValue(0)
        self.slice_slider.setEnabled(False)
        self.slice_slider.blockSignals(False)
        self.index_label.setText("0 / 0")
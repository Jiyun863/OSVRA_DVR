"""2D Slice Viewer Panel — vtkImageReslice 기반
PET 볼륨 데이터를 Axial / Coronal / Sagittal 뷰로 슬라이싱하여
VTK 렌더링 파이프라인으로 표시하는 패널.
right_container 에 배치하여 사용.
"""

import numpy as np
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QButtonGroup, QFrame, QSizePolicy,
    QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal

import vtk
from vtkmodules.util import numpy_support
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


class SliceViewerPanel(QWidget):
    """
    PET 전용 Axial / Coronal / Sagittal 슬라이스 뷰어.
    vtkImageReslice → vtkImageMapToColors → vtkImageActor 파이프라인 사용.
    고정 inverted grayscale TF 사용 (intensity 0→black/opaque, max→white/transparent).
    """

    slice_changed = pyqtSignal(str, int)   # (view_axis, index)

    _AXIS_MAP = {
        "Axial":    2,   # Z 축 슬라이싱
        "Coronal":  1,   # Y 축 슬라이싱
        "Sagittal": 0,   # X 축 슬라이싱
    }
    _AXIS_ORDER = ["Axial", "Coronal", "Sagittal"]

    # 고정 inverted grayscale TF: [position, R, G, B, alpha]
    _INVERTED_GRAY_TF = [
        [0.0, 1.0, 1.0, 1.0, 1.0],  # intensity 0 → white, alpha=1
        [1.0, 0.0, 0.0, 0.0, 0.0],  # intensity 1 → black, alpha=0
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.volume_data: np.ndarray | None = None
        self.voxel_spacing = (1.0, 1.0, 1.0)
        self.current_axis: str = "Axial"
        self.current_index: int = 0

        self._has_data = False
        self._vtk_initialized = False

        # VTK 파이프라인 객체
        self._pet_vtk_image = None
        self._reslice = None
        self._color_mapper = None
        self._image_actor = None
        self._lut = None
        self._placeholder_actor = None

        self._build_ui()

    # ── UI 구성 ───────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # 제목
        title = QLabel("🔬  2D Slice Viewer")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; padding: 10px;"
        )
        root.addWidget(title)

        # ── VTK 렌더 위젯 ──────────────────────────────────────
        self.vtk_widget = QVTKRenderWindowInteractor(self)
        self.vtk_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.vtk_widget.setMinimumSize(200, 200)
        root.addWidget(self.vtk_widget, stretch=1)

        # VTK 렌더러 설정 — 흰색 배경
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(1.0, 1.0, 1.0)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)

        # 인터랙션: 휠 줌만 허용
        interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
        style = vtk.vtkInteractorStyleUser()
        interactor.SetInteractorStyle(style)
        interactor.AddObserver("MouseWheelForwardEvent", self._on_wheel_forward)
        interactor.AddObserver("MouseWheelBackwardEvent", self._on_wheel_backward)

        # placeholder 텍스트
        self._setup_placeholder()

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

        # ── Save Image 버튼 ──────────────────────────────────
        save_row = QHBoxLayout()
        save_row.setSpacing(4)
        save_row.addStretch()
        self._save_btn = QPushButton("Save Image")
        self._save_btn.setFixedHeight(28)
        self._save_btn.setStyleSheet(
            "QPushButton { background-color: #3a7d3a; color: white;"
            "font-weight: bold; border-radius: 4px; padding: 0 12px; }"
            "QPushButton:hover { background-color: #4a9a4a; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save_image)
        save_row.addWidget(self._save_btn)
        root.addLayout(save_row)

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

        # 네비게이션 버튼
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

    def _setup_placeholder(self):
        """빈 상태 placeholder 텍스트 액터 (NormalizedViewport 좌표로 항상 중앙)"""
        self._placeholder_actor = vtk.vtkTextActor()
        self._placeholder_actor.SetInput("No PET Volume Data")
        prop = self._placeholder_actor.GetTextProperty()
        prop.SetFontSize(18)
        prop.SetColor(0.7, 0.7, 0.7)
        prop.SetJustificationToCentered()
        prop.SetVerticalJustificationToCentered()
        coord = self._placeholder_actor.GetPositionCoordinate()
        coord.SetCoordinateSystemToNormalizedViewport()
        coord.SetValue(0.5, 0.5)
        self.renderer.AddActor2D(self._placeholder_actor)

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

    def set_pet_data(self, volume_data: np.ndarray, voxel_spacing: tuple):
        """PET 볼륨 데이터 설정, VTK 파이프라인 구성, 고정 inverted grayscale TF 적용"""
        self._ensure_vtk_initialized()

        self.volume_data = volume_data
        self.voxel_spacing = voxel_spacing

        print(f"[SliceViewer] PET volume shape : {volume_data.shape}")
        print(f"[SliceViewer] voxel spacing    : {voxel_spacing}")
        print(f"[SliceViewer] value range      : {volume_data.min():.3f} ~ {volume_data.max():.3f}")

        # numpy → vtkImageData
        self._pet_vtk_image = self._numpy_to_vtk_imagedata(volume_data, voxel_spacing)
        if self._pet_vtk_image is None:
            return

        # LUT 생성 — 고정 inverted grayscale TF 사용
        self._lut = self._build_vtk_lut_from_tf_nodes(self._INVERTED_GRAY_TF)

        # 파이프라인 구성
        self._build_vtk_pipeline()
        self._has_data = True

        # placeholder 제거
        if self._placeholder_actor:
            self.renderer.RemoveActor2D(self._placeholder_actor)

        # Save 버튼 활성화
        self._save_btn.setEnabled(True)

        # 초기 슬라이스 표시
        self._switch_axis(self.current_axis, reset_index=True)

    def set_axis_and_index(self, axis: str, index: int):
        """외부에서 축/인덱스 설정 (OSVRA 동기화용). slice_changed 미발신."""
        if axis not in self._AXIS_MAP:
            return
        # Update button styles
        for name, btn in self._view_buttons.items():
            btn.setStyleSheet(self._btn_style(active=(name == axis)))
        self._view_buttons[axis].setChecked(True)

        axis_changed = (axis != self.current_axis)
        self.current_axis = axis
        self.current_index = index

        axis_labels = {
            "Axial": "Axial  (Z-axis)",
            "Coronal": "Coronal  (Y-axis)",
            "Sagittal": "Sagittal  (X-axis)",
        }
        self.axis_label.setText(axis_labels[axis])

        if not self._has_data or self.volume_data is None:
            return

        axis_idx = self._AXIS_MAP[axis]
        n_slices = self.volume_data.shape[axis_idx]
        self.current_index = max(0, min(index, n_slices - 1))

        # Update slider without signals
        self.slice_slider.blockSignals(True)
        self.slice_slider.setMinimum(0)
        self.slice_slider.setMaximum(n_slices - 1)
        self.slice_slider.setValue(self.current_index)
        self.slice_slider.setEnabled(True)
        self.slice_slider.blockSignals(False)

        # Update reslice
        if self._reslice:
            if axis_changed:
                axes = self._get_reslice_axes(axis)
                self._reslice.SetResliceAxes(axes)
            origin = self._get_reslice_origin(axis, self.current_index)
            self._reslice.SetResliceAxesOrigin(*origin)
            self._reslice.Update()

        self.index_label.setText(f"{self.current_index} / {n_slices - 1}")
        self._render()
        if axis_changed:
            self._reset_camera()

    def clear(self):
        """PET 데이터 해제 및 파이프라인 정리"""
        self._teardown_vtk_pipeline()
        self.volume_data = None
        self._pet_vtk_image = None
        self._has_data = False

        # Save 버튼 비활성화
        self._save_btn.setEnabled(False)

        # placeholder 복원
        if self._placeholder_actor is None:
            self._setup_placeholder()
        else:
            self.renderer.AddActor2D(self._placeholder_actor)
        self._center_placeholder()

        self._reset_slider()
        self._render()

    def cleanup(self):
        """위젯 종료 시 VTK 리소스 정리"""
        self._teardown_vtk_pipeline()
        if self._placeholder_actor:
            self.renderer.RemoveActor2D(self._placeholder_actor)
            self._placeholder_actor = None
        try:
            iren = self.vtk_widget.GetRenderWindow().GetInteractor()
            if iren:
                iren.TerminateApp()
        except Exception:
            pass

    # ── VTK 파이프라인 ────────────────────────────────────────

    def _ensure_vtk_initialized(self):
        """VTK 인터랙터 초기화 (최초 1회)"""
        if not self._vtk_initialized:
            self.vtk_widget.GetRenderWindow().GetInteractor().Initialize()
            self._vtk_initialized = True

    def _build_vtk_pipeline(self):
        """vtkImageReslice → vtkImageMapToColors → vtkImageActor 파이프라인 구성"""
        self._teardown_vtk_pipeline()

        # 1. Reslice
        self._reslice = vtk.vtkImageReslice()
        self._reslice.SetInputData(self._pet_vtk_image)
        self._reslice.SetOutputDimensionality(2)
        self._reslice.SetInterpolationModeToLinear()

        # 초기 축 설정
        axes = self._get_reslice_axes(self.current_axis)
        self._reslice.SetResliceAxes(axes)

        # 2. Color Mapper
        self._color_mapper = vtk.vtkImageMapToColors()
        self._color_mapper.SetLookupTable(self._lut)
        self._color_mapper.SetInputConnection(self._reslice.GetOutputPort())
        self._color_mapper.SetOutputFormatToRGB()

        # 3. Image Actor
        self._image_actor = vtk.vtkImageActor()
        self._image_actor.GetMapper().SetInputConnection(
            self._color_mapper.GetOutputPort()
        )

        self.renderer.AddActor(self._image_actor)

    def _teardown_vtk_pipeline(self):
        """VTK 파이프라인 객체 해제"""
        if self._image_actor:
            self.renderer.RemoveActor(self._image_actor)
        self._image_actor = None
        self._color_mapper = None
        self._reslice = None

    def _numpy_to_vtk_imagedata(self, numpy_array, voxel_spacing):
        """numpy float32 배열을 vtkImageData로 변환 (Fortran order)"""
        try:
            vtk_data = vtk.vtkImageData()
            dims = (numpy_array.shape[0], numpy_array.shape[1], numpy_array.shape[2])
            vtk_data.SetDimensions(dims)
            vtk_data.SetSpacing(voxel_spacing)
            vtk_data.SetOrigin(0.0, 0.0, 0.0)

            flat_data = numpy_array.ravel(order='F').astype(np.float32)
            vtk_array = numpy_support.numpy_to_vtk(
                flat_data, deep=True, array_type=vtk.VTK_FLOAT,
            )
            vtk_array.SetName("scalars")
            vtk_array.SetNumberOfComponents(1)
            vtk_data.GetPointData().SetScalars(vtk_array)
            return vtk_data
        except Exception as e:
            print(f"[SliceViewer] VTK 데이터 변환 실패: {e}")
            return None

    def _build_vtk_lut_from_tf_nodes(self, tf_nodes):
        """TF 컨트롤 포인트를 256-entry vtkLookupTable로 변환"""
        lut = vtk.vtkLookupTable()
        lut.SetNumberOfTableValues(256)
        lut.SetRange(0.0, 1.0)
        lut.Build()

        if not tf_nodes or len(tf_nodes) < 2:
            # 기본 그레이스케일
            for i in range(256):
                v = i / 255.0
                lut.SetTableValue(i, v, v, v, 1.0)
            lut.Modified()
            return lut

        sorted_nodes = sorted(tf_nodes, key=lambda x: x[0])
        positions = [n[0] for n in sorted_nodes]
        reds = [n[1] for n in sorted_nodes]
        greens = [n[2] for n in sorted_nodes]
        blues = [n[3] for n in sorted_nodes]
        alphas = [n[4] for n in sorted_nodes]

        x = np.linspace(0, 1, 256)
        r_lut = np.interp(x, positions, reds)
        g_lut = np.interp(x, positions, greens)
        b_lut = np.interp(x, positions, blues)
        a_lut = np.interp(x, positions, alphas)

        for i in range(256):
            lut.SetTableValue(i, r_lut[i], g_lut[i], b_lut[i], a_lut[i])

        lut.Modified()
        return lut

    # ── Reslice 축/원점 설정 ──────────────────────────────────

    def _get_reslice_axes(self, axis_name: str) -> vtk.vtkMatrix4x4:
        """축별 reslice 4x4 행렬 반환"""
        m = vtk.vtkMatrix4x4()

        if axis_name == "Axial":
            # 출력 X=입력 X, 출력 Y=입력 Y, 법선=Z
            m.DeepCopy((
                1, 0, 0, 0,
                0, 1, 0, 0,
                0, 0, 1, 0,
                0, 0, 0, 1,
            ))
        elif axis_name == "Coronal":
            # 출력 X=입력 X, 출력 Y=입력 Z, 법선=Y
            m.DeepCopy((
                1, 0, 0, 0,
                0, 0, 1, 0,
                0, 1, 0, 0,
                0, 0, 0, 1,
            ))
        elif axis_name == "Sagittal":
            # 출력 X=입력 Y, 출력 Y=입력 Z, 법선=X
            m.DeepCopy((
                0, 0, 1, 0,
                1, 0, 0, 0,
                0, 1, 0, 0,
                0, 0, 0, 1,
            ))

        return m

    def _get_reslice_origin(self, axis_name: str, index: int) -> tuple:
        """축과 인덱스로부터 reslice 원점 좌표 계산"""
        sx, sy, sz = self.voxel_spacing
        if axis_name == "Axial":
            return (0, 0, index * sz)
        elif axis_name == "Coronal":
            return (0, index * sy, 0)
        elif axis_name == "Sagittal":
            return (index * sx, 0, 0)
        return (0, 0, 0)

    # ── 슬라이스 네비게이션 ───────────────────────────────────

    def _on_view_clicked(self, axis_name: str):
        """뷰 버튼 클릭"""
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

        if not self._has_data or self.volume_data is None:
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

        # reslice 축 업데이트
        if self._reslice:
            axes = self._get_reslice_axes(axis_name)
            self._reslice.SetResliceAxes(axes)

        self._render_slice()
        self._reset_camera()

    def _on_slider_changed(self, value: int):
        self.current_index = value
        self._render_slice()

    def _navigate(self, delta):
        if not self._has_data or self.volume_data is None:
            return
        axis_idx = self._AXIS_MAP[self.current_axis]
        n = self.volume_data.shape[axis_idx]
        if delta == "first":
            new_idx = 0
        elif delta == "last":
            new_idx = n - 1
        else:
            new_idx = max(0, min(self.current_index + delta, n - 1))
        self.slice_slider.setValue(new_idx)

    def _render_slice(self):
        """현재 축과 인덱스로 reslice 원점 업데이트 후 렌더"""
        if not self._has_data or self._reslice is None:
            return

        axis_idx = self._AXIS_MAP[self.current_axis]
        n_slices = self.volume_data.shape[axis_idx]
        idx = max(0, min(self.current_index, n_slices - 1))

        origin = self._get_reslice_origin(self.current_axis, idx)
        self._reslice.SetResliceAxesOrigin(*origin)
        self._reslice.Update()

        self._render()

        # 레이블 갱신
        self.index_label.setText(f"{idx} / {n_slices - 1}")
        self.slice_changed.emit(self.current_axis, idx)

    def _render(self):
        """VTK 렌더 윈도우 렌더"""
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass

    def _reset_camera(self):
        """2D 뷰에 맞게 카메라 리셋"""
        self.renderer.GetActiveCamera().ParallelProjectionOn()
        self.renderer.ResetCamera()
        self._render()

    def _reset_slider(self):
        self.slice_slider.blockSignals(True)
        self.slice_slider.setMinimum(0)
        self.slice_slider.setMaximum(0)
        self.slice_slider.setValue(0)
        self.slice_slider.setEnabled(False)
        self.slice_slider.blockSignals(False)
        self.index_label.setText("0 / 0")

    def _center_placeholder(self):
        """placeholder 위치 갱신 (NormalizedViewport이므로 render만 호출)"""
        self._render()

    # ── 휠 줌 핸들러 ──────────────────────────────────────────

    def _on_wheel_forward(self, obj, event):
        """마우스 휠 앞으로 → 줌 인 (ParallelScale ×0.9)"""
        cam = self.renderer.GetActiveCamera()
        cam.SetParallelScale(cam.GetParallelScale() * 0.9)
        self._render()

    def _on_wheel_backward(self, obj, event):
        """마우스 휠 뒤로 → 줌 아웃 (ParallelScale ×1.1)"""
        cam = self.renderer.GetActiveCamera()
        cam.SetParallelScale(cam.GetParallelScale() * 1.1)
        self._render()

    # ── Save Image ────────────────────────────────────────────

    def _on_save_image(self):
        """현재 뷰를 PNG로 저장"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Slice Image", "", "PNG Files (*.png);;All Files (*)"
        )
        if not path:
            return

        win = self.vtk_widget.GetRenderWindow()
        win.Render()

        w2i = vtk.vtkWindowToImageFilter()
        w2i.SetInput(win)
        w2i.SetInputBufferTypeToRGBA()
        w2i.ReadFrontBufferOff()
        w2i.Update()

        writer = vtk.vtkPNGWriter()
        writer.SetFileName(path)
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Write()
        print(f"[SliceViewer] Image saved: {path}")

    # ── 이벤트 ────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_vtk_initialized()
        self._center_placeholder()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_placeholder()

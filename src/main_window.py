import os
from datetime import datetime
from PIL import Image
import numpy as np

# VTK 환경 설정
os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'
os.environ['MESA_GL_VERSION_OVERRIDE'] = '3.2'
os.environ['VTK_USE_OSMESA'] = '1'

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

# 패널 임포트
from src.gui.panel.file_panel import FilePanel
from src.gui.panel.tf_panel import TransferFunctionPanel
from src.gui.panel.rendering_panel import RenderingPanel
from src.gui.panel.slice_panel import SliceViewerPanel
from src.gui.panel.osvra_panel import OSVRAPanel

# OSVRA 모듈
from src.osvra.volume_bridge import VolumeBridge
from src.osvra.soi_plane import SOIPlaneBuilder
from src.osvra.occlusion_depth import OcclusionDepthComputer
from src.osvra.histogram_depth import DepthHistogramAnalyzer
from src.osvra.logistic_weight import LogisticWeightFunction
from src.osvra.osvra_ct_renderer import OSVRACTRenderer
from src.osvra.fusion import FusionRenderer
from src.gui.dialogs.osvra_debug_dialog import OSVRADebugDialog


class VolumeRenderingMainWindow(QMainWindow):
    """간결화된 메인 윈도우 - Multi-volume 렌더링 지원"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Volume Rendering & Optimization Tool")
        self.setGeometry(50, 50, 2200, 950)
        self.setMinimumSize(1800, 900)

        self.volume_data = None
        self.voxel_spacing = (1.0, 1.0, 1.0)
        self.pet_volume_data = None
        self.pet_voxel_spacing = (1.0, 1.0, 1.0)

        self._osvra_debug_data = None
        self._debug_dialog = None

        self.init_ui()
        self.create_panels()
        self.connect_signals()

        self.statusBar().showMessage("Ready - Load volume data to start")
        self.tf_panel.reset_background_color()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # 1. 왼쪽 패널
        left_container = QWidget()
        left_container.setFixedWidth(600)
        left_container.setStyleSheet("background-color: #2d2d2d;")

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(
            "QScrollArea { border: none; background-color: #2d2d2d; }"
        )

        scroll_content = QWidget()
        self.left_layout = QVBoxLayout(scroll_content)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        scroll_area.setWidget(scroll_content)

        left_main_layout = QVBoxLayout(left_container)
        left_main_layout.addWidget(scroll_area)
        main_layout.addWidget(left_container)

        # 2. 중앙 렌더링 영역
        self.center_widget = QWidget()
        self.center_layout = QVBoxLayout(self.center_widget)
        self.center_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.center_widget, stretch=1)

        # 3. 오른쪽 뷰어 영역
        self.right_container = QWidget()
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.right_container, stretch=1)

        # 4. OSVRA 패널 영역 (오른쪽 끝)
        self.osvra_container = QWidget()
        self.osvra_container.setFixedWidth(380)
        self.osvra_container.setStyleSheet("background-color: #2d2d2d;")
        osvra_scroll = QScrollArea()
        osvra_scroll.setWidgetResizable(True)
        osvra_scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: #2d2d2d; }"
        )
        osvra_scroll_content = QWidget()
        self.osvra_layout = QVBoxLayout(osvra_scroll_content)
        self.osvra_layout.setContentsMargins(0, 0, 0, 0)
        osvra_scroll.setWidget(osvra_scroll_content)
        osvra_main_layout = QVBoxLayout(self.osvra_container)
        osvra_main_layout.addWidget(osvra_scroll)
        main_layout.addWidget(self.osvra_container)

    def create_panels(self):
        self.file_panel = FilePanel()
        self.left_layout.addWidget(self.file_panel)

        self.tf_panel = TransferFunctionPanel()
        self.left_layout.addWidget(self.tf_panel)
        self.left_layout.addStretch(1)

        self.rendering_panel = RenderingPanel()
        self.center_layout.addWidget(self.rendering_panel)

        self.tf_panel.rendering_panel = self.rendering_panel

        self.slice_viewer = SliceViewerPanel()
        self.right_layout.addWidget(self.slice_viewer)

        # OSVRA 패널
        self.osvra_panel = OSVRAPanel()
        self.osvra_layout.addWidget(self.osvra_panel)
        self.osvra_layout.addStretch(1)

    def connect_signals(self):
        self.file_panel.volume_loaded.connect(self.on_volume_loaded)
        self.file_panel.ct_loaded.connect(self.on_ct_loaded)
        self.file_panel.pet_loaded.connect(self.on_pet_loaded)
        self.file_panel.pet_cleared.connect(self.on_pet_cleared)

        self.tf_panel.tf_changed.connect(self.on_tf_changed)
        self.tf_panel.pet_tf_changed.connect(self.on_pet_tf_changed)
        self.tf_panel.background_color_changed.connect(self.on_background_color_changed)
        self.tf_panel.shading_changed.connect(self.on_shading_changed)
        self.tf_panel.lighting_changed.connect(self.on_lighting_changed)
        self.tf_panel.light_direction_changed.connect(self.on_light_direction_changed)
        self.tf_panel.follow_camera_changed.connect(self.on_follow_camera_changed)
        self.tf_panel.ambient_color_changed.connect(self.on_ambient_color_changed)
        self.tf_panel.diffuse_color_changed.connect(self.on_diffuse_color_changed)
        self.tf_panel.specular_color_changed.connect(self.on_specular_color_changed)
        self.tf_panel.clipping_changed.connect(self.on_clipping_changed)
        self.tf_panel.clipping_enabled_changed.connect(self.on_clipping_enabled_changed)

        if hasattr(self.rendering_panel.vtk_renderer, 'point_2d_picked'):
            self.rendering_panel.vtk_renderer.point_2d_picked.connect(self.on_point_2d_picked)

        self.slice_viewer.slice_changed.connect(self._on_slice_changed)

        # OSVRA signals
        self.osvra_panel.render_requested.connect(self._run_osvra_pipeline)
        self.osvra_panel.fusion_ratio_changed.connect(self._on_osvra_fusion_ratio_changed)
        self.osvra_panel.debug_requested.connect(self._on_debug_view_clicked)
        self.osvra_panel.soi_changed.connect(self._on_osvra_soi_changed)

    def on_set_mode_changed(self, enabled):
        """Set 모드 변경 시 데이터 및 화면 강제 초기화"""
        if hasattr(self, 'optimization_panel') and self.optimization_panel:
            self.optimization_panel.picked_points = []
            self.optimization_panel.points_updated.emit([])

        if self.rendering_panel.vtk_renderer:
            self.rendering_panel.vtk_renderer.clear_overlay_points()
            self.rendering_panel.set_overlay_visible(enabled)

        if self.rendering_panel.vtk_renderer:
            self.rendering_panel.vtk_renderer.set_interaction_enabled(not enabled)
            self.rendering_panel.vtk_renderer.set_picking_enabled(enabled)

        status = "SET MODE: ON (Pick Points)" if enabled else "SET MODE: OFF (Navigation)"
        self.statusBar().showMessage(status)

    def on_point_type_changed(self, p_type):
        if self.rendering_panel.vtk_renderer:
            self.rendering_panel.vtk_renderer.current_pick_type = p_type

    def on_point_2d_picked(self, vtk_x, vtk_y):
        """점이 찍혔을 때 - VTK 좌표 그대로 사용"""
        if not hasattr(self, 'optimization_panel') or self.optimization_panel is None:
            return

        p_type = self.optimization_panel.current_point_type
        new_point = {'pos': (vtk_x, vtk_y), 'type': p_type}
        self.optimization_panel.picked_points.append(new_point)
        self.rendering_panel.add_point_2d(vtk_x, vtk_y, p_type)
        print(f"Point Added: {vtk_x}, {vtk_y} ({p_type})")

    # --- 볼륨 핸들러들 ---
    def on_volume_loaded(self, volume_data):
        pass  # on_ct_loaded 에서 처리 (중복 방지)

    def _on_slice_changed(self, axis: str, idx: int):
        self.statusBar().showMessage(f"Slice  {axis}  index: {idx}")
        # Sync OSVRA panel with slice viewer
        if hasattr(self, 'osvra_panel'):
            self.osvra_panel.axis_combo.blockSignals(True)
            self.osvra_panel.axis_combo.setCurrentText(axis)
            self.osvra_panel.axis_combo.blockSignals(False)
            self.osvra_panel.current_axis = axis
            self.osvra_panel.slice_spin.blockSignals(True)
            self.osvra_panel.slice_spin.setValue(idx)
            self.osvra_panel.slice_spin.blockSignals(False)
            self.osvra_panel.current_slice = idx

    def on_ct_loaded(self, volume_data):
        """CT 로드 처리"""
        self.volume_data = volume_data
        self.voxel_spacing = self.file_panel.voxel_spacing
        self.rendering_panel.vtk_renderer.voxel_spacing = self.voxel_spacing
        self.rendering_panel.set_volume_data(volume_data)
        self.tf_panel.set_volume_data(volume_data)
        self.tf_panel.reset_clipping_safe()

        # OSVRA: update slice range based on current axis
        if hasattr(self, 'osvra_panel'):
            axis_map = {"Axial": 2, "Coronal": 1, "Sagittal": 0}
            axis_idx = axis_map.get(self.osvra_panel.current_axis, 2)
            self.osvra_panel.set_slice_range(volume_data.shape[axis_idx])

        shape_str = "×".join(str(s) for s in volume_data.shape)
        self.statusBar().showMessage(f"CT loaded  {shape_str}  (Z×Y×X)")

    def on_pet_loaded(self, volume_data):
        """PET 로드 처리"""
        self.pet_volume_data = volume_data
        self.pet_voxel_spacing = self.file_panel.pet_voxel_spacing
        self.rendering_panel.vtk_renderer.set_pet_volume_data(
            volume_data,
            self.pet_voxel_spacing,
        )
        self.tf_panel.set_pet_volume_data(volume_data)

        self.slice_viewer.set_pet_data(volume_data, self.pet_voxel_spacing)

        shape_str = "×".join(str(s) for s in volume_data.shape)
        self.statusBar().showMessage(f"PET loaded  {shape_str}  (Z×Y×X)")

    def on_pet_cleared(self):
        """PET 제거 처리"""
        self.pet_volume_data = None
        self.rendering_panel.vtk_renderer.clear_pet_volume()
        self.slice_viewer.clear()
        self.statusBar().showMessage("PET volume cleared")

    def on_tf_changed(self, tf_array):
        self.rendering_panel.update_transfer_function(tf_array)

    def on_pet_tf_changed(self, tf_array):
        self.rendering_panel.vtk_renderer.update_pet_transfer_function(tf_array)

    def on_background_color_changed(self, color1, color2):
        self.rendering_panel.set_background_color(color1, color2)

    def on_shading_changed(self, enabled):
        self.rendering_panel.set_shading(enabled)

    def on_lighting_changed(self, property_type, value):
        self.rendering_panel.set_lighting_property(property_type, value)

    def on_light_direction_changed(self, x, y, z):
        if self.rendering_panel.vtk_renderer:
            self.rendering_panel.vtk_renderer.set_light_position('key', x, y, z)

    def on_follow_camera_changed(self, enabled):
        self.rendering_panel.vtk_renderer.set_follow_camera(enabled)

    def on_ambient_color_changed(self, r, g, b):
        self.rendering_panel.vtk_renderer.set_ambient_color(r, g, b)

    def on_diffuse_color_changed(self, r, g, b):
        self.rendering_panel.vtk_renderer.set_diffuse_color(r, g, b)

    def on_specular_color_changed(self, r, g, b):
        self.rendering_panel.vtk_renderer.set_specular_color(r, g, b)

    def on_clipping_changed(self, axis, min_val, max_val):
        self.rendering_panel.apply_clipping(axis, min_val, max_val)

    def on_clipping_enabled_changed(self, enabled):
        self.rendering_panel.set_clipping_enabled(enabled)

    # ── OSVRA Pipeline ──────────────────────────────────────────

    def _on_osvra_soi_changed(self, axis_name: str, slice_index: int):
        """OSVRA panel SOI 변경 → slice_panel 동기화"""
        if hasattr(self, 'slice_viewer') and self.slice_viewer._has_data:
            self.slice_viewer.set_axis_and_index(axis_name, slice_index)

    def _on_osvra_fusion_ratio_changed(self, ratio):
        """Fusion ratio 변경 시 기존 결과를 재합성"""
        if not hasattr(self, '_osvra_last_ct_aug') or self._osvra_last_ct_aug is None:
            return
        if not hasattr(self, '_osvra_last_pet_rgba') or self._osvra_last_pet_rgba is None:
            return

        fused = FusionRenderer.fuse(
            pet_rgba=self._osvra_last_pet_rgba,
            ct_aug_rgba=self._osvra_last_ct_aug,
            fusion_ratio=ratio,
        )
        self.osvra_panel.display_result(fused)

    def _run_osvra_pipeline(self):
        """OSVRA 전체 파이프라인 실행"""
        # 데이터 검증
        if self.volume_data is None:
            self.statusBar().showMessage("OSVRA: CT volume not loaded")
            return
        if self.pet_volume_data is None:
            self.statusBar().showMessage("OSVRA: PET volume not loaded")
            return

        self.statusBar().showMessage("OSVRA: Running pipeline...")
        self.osvra_panel.set_progress(10)
        QApplication.processEvents()

        try:
            # 1. SOI plane 생성
            soi = SOIPlaneBuilder.build_axis_aligned(
                axis_name=self.osvra_panel.current_axis,
                slice_index=self.osvra_panel.current_slice,
                pet_volume=self.pet_volume_data,
                pet_spacing=self.pet_voxel_spacing,
                ct_volume=self.volume_data,
                ct_spacing=self.voxel_spacing,
            )
            print(f"\n{'='*60}")
            print(f"[OSVRA-DEBUG] SOI: {soi.axis_name} slice {soi.slice_index}")
            print(f"[OSVRA-DEBUG]   origin={soi.origin}, normal={soi.normal}")
            print(f"[OSVRA-DEBUG]   resolution={soi.resolution}, pixel_spacing={soi.pixel_spacing}")
            print(f"[OSVRA-DEBUG]   pet_slice range=[{soi.pet_slice.min():.4f}, {soi.pet_slice.max():.4f}]")
            self.osvra_panel.set_progress(20)
            QApplication.processEvents()

            # 2. SOI normal 기반 view direction (카메라 무관, SOI 평면에 수직)
            view_dir = -soi.normal.astype(np.float64)
            print(f"[OSVRA-DEBUG]   view_dir={view_dir}")

            # 3. CT TF 노드 가져오기
            ct_tf_nodes = self.tf_panel.ct_tf_widget.get_nodes()

            # 4. Occlusion depth map 계산
            depth_computer = OcclusionDepthComputer(
                ct_volume=self.volume_data,
                ct_spacing=self.voxel_spacing,
                ct_tf_nodes=ct_tf_nodes,
                opacity_limit=self.osvra_panel.opacity_limit,
                sample_step_mm=self.osvra_panel.sample_step,
            )
            depth_map, valid_mask = depth_computer.compute(soi, view_dir)
            print(f"[OSVRA-DEBUG] DepthMap: valid={valid_mask.sum()}/{valid_mask.size} ({100*valid_mask.mean():.1f}%)")
            if valid_mask.any():
                print(f"[OSVRA-DEBUG]   range=[{np.nanmin(depth_map[valid_mask]):.1f}, {np.nanmax(depth_map[valid_mask]):.1f}] mm")
                print(f"[OSVRA-DEBUG]   mean={np.nanmean(depth_map[valid_mask]):.1f} mm")
            self.osvra_panel.set_progress(50)
            QApplication.processEvents()

            # 5. Histogram 분석 & D 선택
            analyzer = DepthHistogramAnalyzer(
                smoothing_sigma=self.osvra_panel.smoothing_sigma,
            )
            hist_result = analyzer.analyze(depth_map, valid_mask)
            self.osvra_panel.display_histogram(hist_result)

            print(f"[OSVRA-DEBUG] Histogram peaks: {hist_result['peak_distances']}")
            print(f"[OSVRA-DEBUG]   default_D={hist_result['default_D']:.1f} mm")

            # D 값 결정 (peak 또는 manual)
            D = self.osvra_panel.current_D
            print(f"[OSVRA-DEBUG]   selected D={D:.1f} mm")
            self.osvra_panel.set_progress(60)
            QApplication.processEvents()

            # 6. Logistic weight 생성
            weight_func = LogisticWeightFunction(D=D)
            print(f"[OSVRA-DEBUG] LogisticWeight: D={D:.1f}, B={weight_func.B:.6f}")
            test_d = np.array([0.0, D/2, D, 2*D])
            test_w = weight_func(test_d)
            print(f"[OSVRA-DEBUG]   w(0)={test_w[0]:.6f}, w(D/2)={test_w[1]:.6f}, w(D)={test_w[2]:.6f}, w(2D)={test_w[3]:.6f}")

            # 7. Weighted CT augmentation
            ct_renderer = OSVRACTRenderer(
                ct_volume=self.volume_data,
                ct_spacing=self.voxel_spacing,
                ct_tf_nodes=ct_tf_nodes,
                sample_step_mm=self.osvra_panel.sample_step,
            )
            ct_aug = ct_renderer.render(soi, view_dir, weight_func)
            print(f"[OSVRA-DEBUG] CT Aug: alpha mean={ct_aug[:,:,3].mean():.4f}, max={ct_aug[:,:,3].max():.4f}")
            print(f"[OSVRA-DEBUG]   non-zero alpha: {(ct_aug[:,:,3]>0.01).sum()}/{ct_aug.shape[0]*ct_aug.shape[1]}")
            self.osvra_panel.set_progress(90)
            QApplication.processEvents()

            # 8. PET SOI 슬라이스에 TF 적용 → pet_rgba
            pet_tf_nodes = self.tf_panel.pet_tf_widget.get_nodes()
            opacity_lut, color_lut = VolumeBridge.build_tf_luts(pet_tf_nodes)
            pet_slice = soi.pet_slice  # (H, W) float [0,1]
            lut_idx = np.clip((pet_slice * 255).astype(np.int32), 0, 255)
            h, w = pet_slice.shape
            pet_rgba = np.zeros((h, w, 4), dtype=np.float32)
            pet_rgba[..., :3] = color_lut[lut_idx]
            pet_rgba[..., 3] = opacity_lut[lut_idx]

            # 9. Fusion
            fused = FusionRenderer.fuse(
                pet_rgba=pet_rgba,
                ct_aug_rgba=ct_aug,
                fusion_ratio=self.osvra_panel.fusion_ratio,
            )

            print(f"[OSVRA-DEBUG] Fused: range=[{fused.min():.4f}, {fused.max():.4f}]")
            print(f"{'='*60}\n")

            # 캐시 저장 (fusion ratio 변경 시 재사용)
            self._osvra_last_ct_aug = ct_aug
            self._osvra_last_pet_rgba = pet_rgba

            # Debug 캐시
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._osvra_debug_data = {
                'pet_slice': soi.pet_slice,
                'depth_map': depth_map,
                'ct_aug': ct_aug,
                'pet_rgba': pet_rgba,
                'fused': fused,
                'axis_name': soi.axis_name,
                'slice_index': soi.slice_index,
                'timestamp': ts,
            }
            self.osvra_panel.set_debug_available(True)
            self._save_osvra_debug_images(self._osvra_debug_data)

            # 10. UI 업데이트
            self.osvra_panel.display_result(fused)
            self.osvra_panel.set_progress(100)

            self.statusBar().showMessage(
                f"OSVRA: Complete (D={D:.1f}mm, "
                f"{soi.axis_name} slice {soi.slice_index})"
            )

        except Exception as e:
            self.osvra_panel.set_progress(100)
            self.statusBar().showMessage(f"OSVRA Error: {e}")
            print(f"OSVRA pipeline error: {e}")
            import traceback
            traceback.print_exc()

    def _save_osvra_debug_images(self, data: dict):
        """파이프라인 중간 결과 5개를 PNG로 자동 저장"""
        try:
            ts = data['timestamp']
            axis = data['axis_name']
            idx = data['slice_index']
            save_dir = os.path.join(
                "resources", "OSVRA_debug", f"{ts}_{axis}_{idx}"
            )
            os.makedirs(save_dir, exist_ok=True)

            def _save_rgba(arr, filename):
                rgb = (arr[..., :3] * 255).clip(0, 255).astype(np.uint8)
                Image.fromarray(rgb, 'RGB').save(os.path.join(save_dir, filename))

            def _save_gray(arr, filename):
                gray = (arr * 255).clip(0, 255).astype(np.uint8)
                Image.fromarray(gray).convert('RGB').save(os.path.join(save_dir, filename))

            def _save_depth(arr, filename):
                d = np.nan_to_num(arr, nan=0.0)
                d_max = float(d.max())
                if d_max > 0:
                    d_norm = (d / d_max * 255).clip(0, 255).astype(np.uint8)
                else:
                    d_norm = np.zeros_like(d, dtype=np.uint8)
                Image.fromarray(d_norm).convert('RGB').save(os.path.join(save_dir, filename))

            _save_gray(data['pet_slice'], "1_pet_slice.png")
            _save_depth(data['depth_map'], "2_depth_map.png")
            _save_rgba(data['ct_aug'], "3_ct_aug.png")
            _save_rgba(data['pet_rgba'], "4_pet_rgba.png")
            _save_rgba(data['fused'], "5_fused.png")

        except Exception as e:
            self.statusBar().showMessage(f"OSVRA Debug: save failed — {e}")

    def _on_debug_view_clicked(self):
        """Debug View 버튼 핸들러 — OSVRADebugDialog 열기"""
        if self._osvra_debug_data is None:
            return
        if self._debug_dialog is not None:
            self._debug_dialog.close()
        self._debug_dialog = OSVRADebugDialog(self._osvra_debug_data, parent=self)
        self._debug_dialog.show()

    def closeEvent(self, event):
        if hasattr(self, 'rendering_panel'):
            self.rendering_panel.cleanup()
        super().closeEvent(event)

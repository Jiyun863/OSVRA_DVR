"""
VTK Volume Renderer with Native 2D Overlay
- Qt 오버레이 대신 VTK 자체 2D 렌더링 사용
- OS 독립적으로 동작

수정 사항
- vtkMultiVolume + vtkOpenGLGPUVolumeRayCastMapper 구조 유지
- 조명/쉐이딩은 vtkMultiVolume 자체가 아니라 각 포트별 vtkVolumeProperty(CT/PET)에 적용
- 파이프라인 재구성 후에도 쉐이딩/조명 상태가 유지되도록 상태 저장 및 재적용 로직 추가
"""

import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from src.gui.rendering.clipping_manager import VolumeClippingManager
from src.gui.rendering.screenshot_manager import ScreenshotManager
from src.gui.rendering.camera_controller import CameraController
from src.gui.rendering.lighting_manager import LightingManager

import traceback
try:
    import vtk
    from vtkmodules.util import numpy_support
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    from vtkmodules.vtkRenderingVolume import vtkMultiVolume
    from vtkmodules.vtkRenderingVolumeOpenGL2 import (
        vtkOpenGLGPUVolumeRayCastMapper as _OpenGLMapper,
    )
    VTK_AVAILABLE = True
    MULTI_VOLUME_AVAILABLE = True
except ImportError as _vtk_err:
    VTK_AVAILABLE = False
    MULTI_VOLUME_AVAILABLE = False
    print(f"VTK 라이브러리가 설치되지 않았습니다: {_vtk_err}")


class VTKVolumeRenderer(QWidget):
    camera_angles_changed = pyqtSignal(float, float)
    point_2d_picked = pyqtSignal(int, int)  # VTK 디스플레이 좌표 (좌하단 기준)

    def __init__(self):
        super().__init__()

        if VTK_AVAILABLE:
            vtk.vtkObject.GlobalWarningDisplayOff()
        else:
            self.setup_fallback_ui()
            return

        # VTK 위젯 설정
        self.vtk_widget = QVTKRenderWindowInteractor(self)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.vtk_widget)
        self.setLayout(layout)

        # VTK 파이프라인
        self.renderer = vtk.vtkRenderer()
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()

        # --- 피킹 및 인터랙션 상태 관리 ---
        self.picking_enabled = False
        self.current_pick_type = "positive"
        self.picking_observer_tag = None

        # 렌더링 데이터
        self.volume_data = None  # W x H x D numpy array
        self.voxel_spacing = (1.0, 1.0, 1.0)

        self.pet_volume_data = None
        self.pet_voxel_spacing = (1.0, 1.0, 1.0)

        self.class_transfer_functions = {}
        self.class_volumes = {}
        self.class_mappers = {}
        self.class_properties = {}

        # 조명 / 쉐이딩 상태 (파이프라인 재구성 시 재적용)
        self.shading_enabled = False
        self.shade_ct = True
        self.shade_pet = False  # PET는 기본적으로 emissive look을 권장
        self.ambient = 0.15
        self.diffuse = 0.75
        self.specular = 0.10
        self.specular_power = 8.0

        # ── Multi-volume 파이프라인 (VTK 9.x 공식 패턴) ──────────────
        # vtkOpenGLGPUVolumeRayCastMapper  : port 0=CT, port 1=PET
        # vtkMultiVolume                   : renderer 에 추가되는 단일 액터
        #   └─ SetVolume(ct_vol,  0)  ct_vol.SetProperty(ct_property)
        #   └─ SetVolume(pet_vol, 1)  pet_vol.SetProperty(pet_property)
        #
        # 하위 호환 alias:
        #   standard_volume / standard_mapper / standard_property → multi_* 를 참조
        self.multi_volume = None    # vtkMultiVolume  (renderer 에 추가)
        self.multi_mapper = None    # vtkOpenGLGPUVolumeRayCastMapper
        self.ct_vol_actor = None    # vtkVolume (port 0 전용 액터)
        self.pet_vol_actor = None   # vtkVolume (port 1 전용 액터)
        self.ct_property = None     # vtkVolumeProperty (CT)
        self.pet_property = None    # vtkVolumeProperty (PET)

        # 입력 포트 producer를 멤버로 보관해 참조 유지
        self.ct_producer = None
        self.pet_producer = None

        # 하위 호환 alias (clipping_manager 등 외부 코드가 참조)
        self.standard_volume = None
        self.standard_mapper = None
        self.standard_property = None
        self.pet_volume = None
        self.pet_mapper = None

        self.current_sample_distance = 0.5

        self.clipping_manager = VolumeClippingManager(self)
        self.screenshot_manager = ScreenshotManager(self)
        self.camera_controller = CameraController(self)
        self.lighting_manager = LightingManager(self)

        self.setup_renderer()
        self.setup_interactor()

    # ------------------------------------------------------------------
    # 공통 헬퍼
    # ------------------------------------------------------------------
    def _render(self):
        if hasattr(self, 'vtk_widget') and self.vtk_widget:
            self.vtk_widget.GetRenderWindow().Render()

    def _iter_volume_properties(self):
        """현재 존재하는 포트별 vtkVolumeProperty 순회"""
        if self.ct_property is not None:
            yield 'ct', self.ct_property
        if self.pet_property is not None:
            yield 'pet', self.pet_property

    def _should_shade_modality(self, modality):
        if not self.shading_enabled:
            return False
        if modality == 'ct':
            return bool(self.shade_ct)
        if modality == 'pet':
            return bool(self.shade_pet)
        return False

    def _apply_saved_lighting_state(self, prop, modality='ct'):
        """저장된 쉐이딩 / 머티리얼 파라미터를 property에 적용"""
        prop.IndependentComponentsOn()
        prop.SetInterpolationTypeToLinear()

        if self._should_shade_modality(modality):
            prop.ShadeOn()
        else:
            prop.ShadeOff()

        prop.SetAmbient(float(self.ambient))
        prop.SetDiffuse(float(self.diffuse))
        prop.SetSpecular(float(self.specular))
        prop.SetSpecularPower(float(self.specular_power))

    def cleanup(self):
        """VTK 리소스 정리"""
        try:
            if hasattr(self, 'point_overlay'):
                self.point_overlay.clear_points()
            if hasattr(self, 'renderer') and self.renderer:
                camera = self.renderer.GetActiveCamera()
                if camera:
                    camera.RemoveAllObservers()
            self.volume_data = None
            self.pet_volume_data = None
        except Exception:
            pass

    # ============================================================
    # 2D 오버레이 관련 메서드
    # ============================================================
    def add_overlay_point(self, vtk_x, vtk_y, point_type):
        """VTK 좌표계로 포인트 추가 (좌하단 기준)"""
        if hasattr(self, 'point_overlay'):
            self.point_overlay.add_point(vtk_x, vtk_y, point_type)
            self._render()

    def clear_overlay_points(self):
        """오버레이 포인트 모두 제거"""
        if hasattr(self, 'point_overlay'):
            self.point_overlay.clear_points()
            self._render()

    def set_overlay_visible(self, visible):
        """오버레이 표시/숨김"""
        if hasattr(self, 'point_overlay'):
            self.point_overlay.set_visible(visible)
            self._render()

    # ============================================================
    # 피킹 및 카메라 제어
    # ============================================================
    def set_interaction_enabled(self, enabled):
        """카메라 조작 활성화/비활성화"""
        if enabled:
            style = vtk.vtkInteractorStyleTrackballCamera()
            self.interactor.SetInteractorStyle(style)
            self.renderer.GetActiveCamera().AddObserver(
                'ModifiedEvent', self.on_camera_modified
            )
        else:
            from vtkmodules.vtkInteractionStyle import vtkInteractorStyleUser
            style = vtkInteractorStyleUser()
            self.interactor.SetInteractorStyle(style)

        self.setup_picking_observer()

    def set_picking_enabled(self, enabled):
        """피킹 모드 활성화 여부"""
        self.picking_enabled = enabled
        if hasattr(self, 'point_overlay'):
            self.point_overlay.set_visible(enabled)
        self._render()

    def setup_picking_observer(self):
        """마우스 클릭 이벤트 관찰자 설정"""
        if self.picking_observer_tag is not None:
            self.interactor.RemoveObserver(self.picking_observer_tag)
            self.picking_observer_tag = None

        self.picking_observer_tag = self.interactor.AddObserver(
            "LeftButtonPressEvent", self.on_left_button_press, 10.0
        )

    def on_left_button_press(self, obj, event):
        """마우스 클릭 시 좌표 추출 - VTK 네이티브 좌표 사용"""
        if not self.picking_enabled:
            return
        click_pos = self.interactor.GetEventPosition()
        vtk_x, vtk_y = click_pos[0], click_pos[1]
        self.point_2d_picked.emit(vtk_x, vtk_y)

    # ============================================================
    # 기존 메서드들
    # ============================================================
    def set_clipping_range(self, axis_index, min_pos, max_pos):
        if self.clipping_manager:
            self.clipping_manager.set_clipping_range(axis_index, min_pos, max_pos)

    def enable_clipping(self, enabled):
        if self.clipping_manager:
            self.clipping_manager.enable_clipping(enabled)

    def reset_clipping(self):
        if self.clipping_manager:
            self.clipping_manager.reset_clipping()

    # ================================================================
    # Multi-volume 파이프라인 내부 헬퍼 (VTK 9.x — vtkMultiVolume 패턴)
    # ================================================================
    def _make_ct_property(self):
        prop = vtk.vtkVolumeProperty()
        default_tf = self.class_transfer_functions.get(0) or self._create_default_tf_array()
        color_func, opacity_func = self._create_vtk_tf_from_array(default_tf)
        prop.SetColor(color_func)
        prop.SetScalarOpacity(opacity_func)
        self.class_transfer_functions[0] = default_tf
        self._apply_saved_lighting_state(prop, 'ct')
        return prop

    def _make_pet_property(self):
        prop = vtk.vtkVolumeProperty()
        default_tf = self.class_transfer_functions.get(1) or self._create_default_pet_tf_array()
        color_func, opacity_func = self._create_vtk_tf_from_array(default_tf)
        prop.SetColor(color_func)
        prop.SetScalarOpacity(opacity_func)
        self.class_transfer_functions[1] = default_tf
        self._apply_saved_lighting_state(prop, 'pet')
        return prop

    def _create_default_pet_tf_array(self):
        """PET 기본 TF — 검정→빨강→노랑 핫 컬러맵"""
        return [
            [0.0, 0.0, 0.0, 0.0, 0.00],
            [0.25, 0.5, 0.0, 0.0, 0.00],
            [0.35, 1.0, 0.2, 0.0, 0.15],
            [0.60, 1.0, 0.8, 0.0, 0.50],
            [1.0, 1.0, 1.0, 0.8, 0.90],
        ]

    def _rebuild_pipeline(self):
        """
        CT / PET 데이터 상태에 따라 multi-volume 파이프라인을 전체 재구성.
        """
        try:
            if self.multi_volume and self.renderer:
                self.renderer.RemoveVolume(self.multi_volume)

            # Mapper
            mapper = _OpenGLMapper()
            mapper.SetBlendModeToComposite()
            mapper.SetSampleDistance(self.current_sample_distance)
            mapper.SetAutoAdjustSampleDistances(False)

            ct_vtk = self._numpy_to_vtk_imagedata(self.volume_data, self.voxel_spacing)
            self.ct_producer = vtk.vtkTrivialProducer()
            self.ct_producer.SetOutput(ct_vtk)
            mapper.SetInputConnection(0, self.ct_producer.GetOutputPort())

            if self.pet_volume_data is not None:
                pet_vtk = self._numpy_to_vtk_imagedata(
                    self.pet_volume_data,
                    self.pet_voxel_spacing,
                )
                self.pet_producer = vtk.vtkTrivialProducer()
                self.pet_producer.SetOutput(pet_vtk)
                mapper.SetInputConnection(1, self.pet_producer.GetOutputPort())
            else:
                self.pet_producer = None

            # CT actor
            if self.ct_property is None:
                self.ct_property = self._make_ct_property()
            else:
                self._apply_saved_lighting_state(self.ct_property, 'ct')

            self.ct_vol_actor = vtk.vtkVolume()
            self.ct_vol_actor.SetProperty(self.ct_property)

            # PET actor
            if self.pet_volume_data is not None:
                if self.pet_property is None:
                    self.pet_property = self._make_pet_property()
                else:
                    self._apply_saved_lighting_state(self.pet_property, 'pet')
                self.pet_vol_actor = vtk.vtkVolume()
                self.pet_vol_actor.SetProperty(self.pet_property)
            else:
                self.pet_vol_actor = None
                self.pet_property = None

            # vtkMultiVolume 조합
            mv = vtkMultiVolume()
            mv.SetMapper(mapper)
            mv.SetVolume(self.ct_vol_actor, 0)
            if self.pet_vol_actor is not None:
                mv.SetVolume(self.pet_vol_actor, 1)

            self.multi_volume = mv
            self.multi_mapper = mapper
            self.renderer.AddVolume(self.multi_volume)

            # 하위 호환 alias 동기화
            self.standard_volume = self.multi_volume
            self.standard_mapper = self.multi_mapper
            self.standard_property = self.ct_property
            self.pet_volume = self.multi_volume
            self.pet_mapper = self.multi_mapper

            # 클리핑 갱신
            if self.clipping_manager:
                self.clipping_manager.reset_clipping()
                if self.clipping_manager.clipping_enabled:
                    self.clipping_manager.update_clipping_target()

            # 저장된 lighting/shading 상태 재적용
            # if self.lighting_manager:
            #     self.lighting_manager.reapply_to_current_properties()

            print(
                "Multi-volume 파이프라인 재구성 완료 "
                f"(PET={'연결됨' if self.pet_vol_actor else '없음'})"
            )

        except Exception as e:
            print(f"파이프라인 재구성 실패: {e}")
            traceback.print_exc()

    # ================================================================
    # 공개 API
    # ================================================================
    def set_volume_data(self, volume_data):
        if not VTK_AVAILABLE or self.renderer is None:
            return

        is_first_load = (self.volume_data is None)
        if not is_first_load:
            self.save_camera_state()

        self.volume_data = volume_data
        print(self.volume_data.shape)

        if volume_data is not None:
            self.ct_property = None  # 새 데이터에 맞춰 재생성
            self._rebuild_pipeline()

            if is_first_load:
                self.setup_camera(force_reset=True)
                self.reset_camera_manual()
            else:
                if not self.restore_camera_state():
                    self.setup_camera(force_reset=True)

            self._render()

    def _setup_standard_volume(self, volume_data):
        """하위 호환 stub"""
        self.ct_property = None
        self._rebuild_pipeline()

    def _create_vtk_tf_from_array(self, tf_nodes, return_array=False):
        tf_array = np.zeros((256, 4))
        if not tf_nodes or len(tf_nodes) < 2:
            return None, None

        sorted_nodes = sorted(tf_nodes, key=lambda x: x[0])

        def interpolate_value(intensity, channel):
            if intensity <= sorted_nodes[0][0]:
                return sorted_nodes[0][channel]
            if intensity >= sorted_nodes[-1][0]:
                return sorted_nodes[-1][channel]
            for i in range(len(sorted_nodes) - 1):
                if sorted_nodes[i][0] <= intensity <= sorted_nodes[i + 1][0]:
                    t = (intensity - sorted_nodes[i][0]) / (
                        sorted_nodes[i + 1][0] - sorted_nodes[i][0]
                    )
                    return sorted_nodes[i][channel] * (1 - t) + sorted_nodes[i + 1][channel] * t
            return 0.0

        color_func = vtk.vtkColorTransferFunction()
        opacity_func = vtk.vtkPiecewiseFunction()

        for i in range(256):
            normalized_x = i / 255.0
            r = interpolate_value(normalized_x, 1)
            g = interpolate_value(normalized_x, 2)
            b = interpolate_value(normalized_x, 3)
            alpha = interpolate_value(normalized_x, 4)

            color_func.AddRGBPoint(normalized_x, r, g, b)
            opacity_func.AddPoint(normalized_x, alpha)
            tf_array[i] = [r, g, b, alpha]

        if return_array:
            color_array = np.zeros((256, 256, 3), dtype=np.uint8)
            opacity_array = np.zeros((256, 256, 1), dtype=np.uint8)
            for y in range(256):
                for x in range(256):
                    color_array[y, x, 0] = int(tf_array[x, 0] * 255)
                    color_array[y, x, 1] = int(tf_array[x, 1] * 255)
                    color_array[y, x, 2] = int(tf_array[x, 2] * 255)
                    opacity_array[y, x, 0] = int(tf_array[x, 3] * 255)
            return color_array, opacity_array

        return color_func, opacity_func

    def _create_default_tf_array(self, prob=False):
        return [
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [0.3, 1.0, 0.5, 0.0, 0.1],
            [0.7, 1.0, 1.0, 1.0, 0.8],
            [1.0, 1.0, 1.0, 1.0, 1.0],
        ]

    def update_transfer_function_optimized(self, tf_nodes):
        """CT TF 실시간 업데이트 — ct_property 직접 수정"""
        try:
            self.class_transfer_functions[0] = tf_nodes
            if self.ct_property:
                color_func, opacity_func = self._create_vtk_tf_from_array(tf_nodes)
                self.ct_property.SetColor(color_func)
                self.ct_property.SetScalarOpacity(opacity_func)
                self._apply_saved_lighting_state(self.ct_property, 'ct')
            self._render()
        except Exception as e:
            print(f"CT TF 업데이트 실패: {e}")

    def _clear_ct_volume(self):
        """전체 multi-volume 파이프라인 제거 (CT 재로드 시 호출)"""
        if self.multi_volume and self.renderer:
            self.renderer.RemoveVolume(self.multi_volume)
        self.multi_volume = None
        self.multi_mapper = None
        self.ct_vol_actor = None
        self.pet_vol_actor = None
        self.ct_property = None
        self.pet_property = None
        self.ct_producer = None
        self.pet_producer = None

        # alias 초기화
        self.standard_volume = None
        self.standard_mapper = None
        self.standard_property = None
        self.pet_volume = None
        self.pet_mapper = None

    def _clear_pet_volume(self):
        """PET 만 해제 후 CT 단독으로 파이프라인 재구성"""
        self.pet_volume_data = None
        self.pet_property = None
        self.pet_vol_actor = None
        self.pet_producer = None
        if self.volume_data is not None:
            self._rebuild_pipeline()

    def set_pet_volume_data(self, volume_data, voxel_spacing=None):
        """PET 볼륨 로드 — multi-volume 파이프라인 재구성으로 port 1 에 연결"""
        if voxel_spacing is not None:
            self.pet_voxel_spacing = voxel_spacing
        self.pet_volume_data = volume_data
        self.pet_property = None  # 재생성 강제
        if self.volume_data is not None:
            self._rebuild_pipeline()
        self._render()

    def _setup_pet_volume(self, volume_data):
        """하위 호환 stub"""
        self.set_pet_volume_data(volume_data)

    def clear_pet_volume(self):
        """외부 호출용 PET 제거 (✕ 버튼) — CT 단독으로 파이프라인 재구성"""
        self.pet_volume_data = None
        self.pet_property = None
        self.pet_vol_actor = None
        self.pet_producer = None
        if self.volume_data is not None:
            self._rebuild_pipeline()
        self._render()

    def update_pet_transfer_function(self, tf_nodes):
        """PET TF 실시간 업데이트 — pet_property 직접 수정"""
        try:
            self.class_transfer_functions[1] = tf_nodes
            if self.pet_property:
                color_func, opacity_func = self._create_vtk_tf_from_array(tf_nodes)
                self.pet_property.SetColor(color_func)
                self.pet_property.SetScalarOpacity(opacity_func)
                self._apply_saved_lighting_state(self.pet_property, 'pet')
            self._render()
        except Exception as e:
            print(f"PET TF 업데이트 실패: {e}")

    def clear_all_volumes(self):
        self._clear_ct_volume()
        self.pet_volume_data = None
        self.pet_property = None

    def _numpy_to_vtk_imagedata(self, numpy_array, voxel_spacing):
        try:
            vtk_data = vtk.vtkImageData()
            dims = (numpy_array.shape[0], numpy_array.shape[1], numpy_array.shape[2])
            vtk_data.SetDimensions(dims)
            vtk_data.SetSpacing(voxel_spacing)
            vtk_data.SetOrigin(0.0, 0.0, 0.0)
            flat_data = numpy_array.ravel(order='F').astype(np.float32)
            vtk_array = numpy_support.numpy_to_vtk(
                flat_data,
                deep=True,
                array_type=vtk.VTK_FLOAT,
            )
            vtk_array.SetName("scalars")
            vtk_array.SetNumberOfComponents(1)
            vtk_data.GetPointData().SetScalars(vtk_array)
            return vtk_data
        except Exception as e:
            print(f"VTK 데이터 변환 실패: {e}")
            return None

    def setup_renderer(self):
        self.renderer.SetBackground(1.0, 1.0, 1.0)
        self.renderer.SetBackground2(0.8, 0.8, 0.8)
        self.renderer.SetGradientBackground(True)
        self.setup_lighting()
        render_window = self.vtk_widget.GetRenderWindow()
        render_window.SetMultiSamples(8)

    def setup_interactor(self):
        style = vtk.vtkInteractorStyleTrackballCamera()
        self.interactor.SetInteractorStyle(style)
        style.SetMotionFactor(2.0)
        self.renderer.GetActiveCamera().AddObserver('ModifiedEvent', self.on_camera_modified)
        self.setup_picking_observer()

    def on_camera_modified(self, obj, event):
        if hasattr(self, 'camera_controller') and self.camera_controller.is_sync_in_progress():
            return
        angles = self.get_camera_angles()
        if angles is not None:
            self.camera_angles_changed.emit(angles[0], angles[1])

    def save_camera_state(self):
        return self.camera_controller.save_camera_state()

    def restore_camera_state(self):
        return self.camera_controller.restore_camera_state()

    def get_camera_state(self):
        return self.camera_controller.get_camera_state()

    def set_camera_state(self, state):
        return self.camera_controller.set_camera_state(state)

    def setup_camera(self, force_reset=False):
        self.camera_controller.setup_camera(force_reset)

    def reset_camera_manual(self):
        self.camera_controller.reset_camera_manual()

    def get_current_zoom_factor(self):
        return self.camera_controller.get_current_zoom_factor()

    def set_zoom_factor(self, zoom_factor):
        return self.camera_controller.set_zoom_factor(zoom_factor)

    def get_camera(self):
        return self.camera_controller.get_camera()

    def set_camera_angles(self, longitude: float, latitude: float):
        if hasattr(self, 'camera_controller'):
            return self.camera_controller.set_camera_from_angles(longitude, latitude)
        return False

    def get_camera_angles(self):
        if hasattr(self, 'camera_controller'):
            return self.camera_controller.get_camera_angles()
        return (0.0, 0.0)

    def set_background_color(self, color1, color2=None):
        if not VTK_AVAILABLE or self.renderer is None:
            return
        if color2 is None:
            self.renderer.SetBackground(color1[0], color1[1], color1[2])
            self.renderer.SetGradientBackground(False)
        else:
            self.renderer.SetBackground(color1[0], color1[1], color1[2])
            self.renderer.SetBackground2(color2[0], color2[1], color2[2])
            self.renderer.SetGradientBackground(True)
        self._render()

    def get_depth_map_array(self, use_square_ratio=False):
        # """[Optimizer] 현재 뷰의 Depth Map (Z-Buffer) 추출 (0.0=Near, 1.0=Far)"""
        render_window = self.vtk_widget.GetRenderWindow()
        current_size = render_window.GetSize()
        
        try:
            # 1. 사이즈 설정
            if use_square_ratio:
                target_size = 512
                render_window.SetSize(target_size, target_size)
            
            # 2. 매퍼 설정 (깊이 모드 ON)
            self.set_depth_mode(True)
            render_window.Render()
            
            # 3. 데이터 추출 (분리된 로직 사용)
            depth_output = self.capture_depth_buffer()
            
            # 4. 매퍼 원복 (깊이 모드 OFF)
            self.set_depth_mode(False)
            
            if use_square_ratio:
                render_window.SetSize(current_size[0], current_size[1])
            render_window.Render()
            
            return depth_output

        except Exception as e:
            print(f"깊이 저장 중 오류 발생: {e}")
            # 복구 시도
            self.set_depth_mode(False)
            if use_square_ratio:
                render_window.SetSize(current_size[0], current_size[1])
            return None

        return depth_output # Y축 반전


    def set_sample_distance(self, distance):
        if not VTK_AVAILABLE:
            return
        try:
            self.current_sample_distance = distance
            if self.standard_mapper:
                self.standard_mapper.SetSampleDistance(distance)
            self._render()
        except Exception as e:
            print(f"샘플링 거리 설정 실패: {e}")

    def get_renderer(self):
        return self.renderer

    def setup_fallback_ui(self):
        layout = QVBoxLayout()
        label = QLabel("VTK가 설치되지 않았습니다.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.setLayout(layout)

    # Lighting manager façade -------------------------------------------------
    def setup_lighting(self):
        self.lighting_manager.setup_lighting()

    def set_shading(self, enabled):
        self.lighting_manager.set_shading(enabled)

    def set_ct_shading(self, enabled):
        self.lighting_manager.set_ct_shading(enabled)

    def set_pet_shading(self, enabled):
        self.lighting_manager.set_pet_shading(enabled)

    def set_ambient(self, ambient):
        self.lighting_manager.set_ambient(ambient)

    def set_diffuse(self, diffuse):
        self.lighting_manager.set_diffuse(diffuse)

    def set_specular(self, specular):
        self.lighting_manager.set_specular(specular)

    def set_specular_power(self, specular_power):
        self.lighting_manager.set_specular_power(specular_power)

    def set_ambient_color(self, r, g, b):
        self.lighting_manager.set_ambient_color(r, g, b)

    def set_diffuse_color(self, r, g, b):
        self.lighting_manager.set_diffuse_color(r, g, b)

    def set_specular_color(self, r, g, b):
        self.lighting_manager.set_specular_color(r, g, b)

    def set_light_position(self, light_type, x, y, z):
        self.lighting_manager.set_light_position(light_type, x, y, z)

    def set_follow_camera(self, enabled):
        self.lighting_manager.set_follow_camera(enabled)

    def set_ray_sampling_rate(self, rate):
        try:
            sample_distance = 1.0 / max(0.01, float(rate))
            self.set_sample_distance(sample_distance)
        except Exception:
            pass

    def save_current_rendering(self, use_square_ratio=False):
        return self.screenshot_manager.save_current_rendering(use_square_ratio)

    def save_multiview_rendering(self, use_square_ratio=False, num_images=14):
        return self.screenshot_manager.save_multiview_rendering(use_square_ratio, num_images)

    def export_screenshot(self, filename, resolution=(1920, 1080)):
        return self.screenshot_manager.export_screenshot(filename, resolution)

    def get_world_position_from_display(self, x, y):
        """[Tracking] 화면 클릭(2D) -> 3D World 좌표 반환"""
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.005)
        if picker.Pick(x, y, 0, self.renderer):
            return picker.GetPickPosition()
        return None

    def project_world_to_display(self, world_pos):
        """[Tracking] 3D World 좌표 -> 현재 뷰의 2D 화면 좌표 변환"""
        coordinate = vtk.vtkCoordinate()
        coordinate.SetCoordinateSystemToWorld()
        coordinate.SetValue(world_pos)
        display_coord = coordinate.GetComputedDisplayValue(self.renderer)
        return display_coord

    def set_depth_mode(self, enabled: bool):
        """외부에서 Depth 추출 모드를 제어하기 위한 메서드"""
        if self.standard_mapper:
            self.standard_mapper.SetRenderToImage(1 if enabled else 0)

    def capture_depth_buffer(self):
        """현재 상태에서 Depth Buffer 값만 가져와서 처리 (모드 전환 없음)"""
        if not self.standard_mapper:
            return None

        depth_vtk = vtk.vtkImageData()
        self.standard_mapper.GetDepthImage(depth_vtk)

        near, far = self.renderer.GetActiveCamera().GetClippingRange()

        dims = depth_vtk.GetDimensions()
        vtk_array = depth_vtk.GetPointData().GetScalars()
        if not vtk_array:
            return None

        d = numpy_support.vtk_to_numpy(vtk_array).reshape(dims[1], dims[0])
        d = np.flipud(d)

        z_linear = (2.0 * near * far) / (far + near - (2.0 * d - 1.0) * (far - near))
        return z_linear
"""
간결화된 3D 렌더링 패널 - VTK 네이티브 2D 오버레이 사용
Qt 오버레이 문제 해결을 위해 VTK 자체 2D 렌더링 기능 활용
"""

from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                           QSlider, QRadioButton, QFrame, QMessageBox, QWidget, 
                           QSizePolicy, QSpinBox) 
from PyQt6.QtCore import pyqtSignal, Qt
from src.gui.panel.base_panel import BasePanel
import vtk


class RenderingPanel(BasePanel):
    """3D 렌더링 패널 - VTK 네이티브 오버레이 사용"""
    
    zoom_changed = pyqtSignal(float)
    camera_reset = pyqtSignal()
    sampling_rate_changed = pyqtSignal(float)
    rendering_saved = pyqtSignal(str)
    
    def __init__(self):
        try:
            from src.gui.widget.renderer_widget import VTKVolumeRenderer
            self.vtk_renderer = VTKVolumeRenderer()
        except Exception as e:
            print(f"❌ VTK 렌더러 생성 실패: {e}")
            self.vtk_renderer = None
            
        super().__init__("3D Volume Rendering", collapsible=False)
        
    def cleanup(self):
        """패널 정리"""
        if hasattr(self, 'vtk_renderer') and self.vtk_renderer:
            self.vtk_renderer.cleanup()

    def setup_content(self):
        """내용 설정"""
        # 1. 헤더
        header_layout = QHBoxLayout()
        self.title_label = QLabel("🎮 3D Volume Rendering")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        self.content_layout.addLayout(header_layout)
        
        # 2. VTK 렌더러 (오버레이 내장)
        if self.vtk_renderer:
            self.vtk_renderer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.content_layout.addWidget(self.vtk_renderer, stretch=1)
        
        # 3. 카메라 컨트롤
        camera_group, camera_layout = self.create_group_box("", "horizontal")
        camera_layout.setSpacing(8)
        camera_layout.setContentsMargins(10, 5, 10, 5)

        btn_style = "QPushButton { height: 32px; padding: 0 5px; font-weight: bold; }"
        
        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_in_btn.setFixedWidth(80)
        self.zoom_in_btn.setStyleSheet(btn_style)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        
        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_out_btn.setFixedWidth(80)
        self.zoom_out_btn.setStyleSheet(btn_style)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setFixedWidth(60)
        self.reset_btn.setStyleSheet(btn_style)
        self.reset_btn.clicked.connect(self.reset_view)

        camera_layout.addWidget(self.zoom_in_btn)
        camera_layout.addWidget(self.zoom_out_btn)
        camera_layout.addWidget(self.reset_btn)

        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.VLine)
        line1.setStyleSheet("background-color: #444;")
        camera_layout.addWidget(line1)

        camera_layout.addWidget(QLabel("🔍 Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 150)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        camera_layout.addWidget(self.zoom_slider, stretch=1) 
        
        self.zoom_label = QLabel("1.0x")
        self.zoom_label.setFixedWidth(40)
        camera_layout.addWidget(self.zoom_label)

        self.content_layout.addWidget(camera_group)
        
        # 4. 샘플링 레이트
        quality_group, quality_layout = self.create_group_box("", "horizontal")
        quality_layout.setContentsMargins(10, 5, 10, 5)
        quality_layout.addWidget(QLabel("🔬 Sampling Rate:"))
        
        self.sampling_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.sampling_rate_slider.setRange(1, 1000)
        self.sampling_rate_slider.setValue(50)
        self.sampling_rate_slider.valueChanged.connect(self.on_sampling_rate_changed)
        quality_layout.addWidget(self.sampling_rate_slider, stretch=1)
        
        self.sampling_rate_label = QLabel("0.50x")
        self.sampling_rate_label.setFixedWidth(45)
        quality_layout.addWidget(self.sampling_rate_label)
        
        self.content_layout.addWidget(quality_group)
        
        # 5. 저장 컨트롤
        save_group, save_layout = self.create_group_box("", "horizontal")
        save_layout.setContentsMargins(10, 5, 10, 5)
        
        self.save_current_size_radio = QRadioButton("Current")
        save_layout.addWidget(self.save_current_size_radio)
        
        self.save_square_radio = QRadioButton("1:1")
        self.save_square_radio.setChecked(True)
        save_layout.addWidget(self.save_square_radio)

        save_btn_style = "QPushButton { height: 35px; padding: 0 10px; }"

        save_render_btn = QPushButton("📸 Save Image")
        save_render_btn.setStyleSheet(save_btn_style)
        save_render_btn.clicked.connect(self.save_current_rendering)
        save_layout.addWidget(save_render_btn)
        
        save_cam_btn = QPushButton("💾 Save Cam")
        save_cam_btn.setStyleSheet(save_btn_style)
        save_cam_btn.clicked.connect(self.save_current_camera_to_file)
        save_layout.addWidget(save_cam_btn)
        
        load_cam_btn = QPushButton("📥 Load Cam")
        load_cam_btn.setStyleSheet(save_btn_style)
        load_cam_btn.clicked.connect(self.load_camera_from_file)
        save_layout.addWidget(load_cam_btn)
        
        self.content_layout.addWidget(save_group)
        
        # 6. Dmesh를 위한 멀티뷰 저장 컨트롤
        multi_group, multi_layout = self.create_group_box("", "horizontal")
        multi_layout.setContentsMargins(10, 5, 10, 5)
        multi_layout.addWidget(QLabel("🔬 이미지 개수 [기본값: 14x14 = 196]:"))

        self.num_image_box = QSpinBox()
        self.num_image_box.setRange(0, 20)        # 최소, 최대값 설정
        self.num_image_box.setSingleStep(1)        # 화살표 클릭 시 증감 단위
        self.num_image_box.setValue(14)            # 초기값 설정
        multi_layout.addWidget(self.num_image_box)

        save_multiview_btn = QPushButton("📸 Save Multi-view Image")
        save_multiview_btn.setStyleSheet(save_btn_style)
        save_multiview_btn.clicked.connect(self.save_multiview_rendering)
        multi_layout.addWidget(save_multiview_btn)
        
        self.content_layout.addWidget(multi_group)

        if self.vtk_renderer:
            self.vtk_renderer.update_zoom_callback = self.update_zoom_slider_from_camera

    # ============================================================
    # 오버레이 제어 - VTK 네이티브 오버레이 사용
    # ============================================================

    def add_point_2d(self, vtk_x, vtk_y, p_type):
        """VTK 좌표계로 포인트 추가"""
        if self.vtk_renderer:
            self.vtk_renderer.add_overlay_point(vtk_x, vtk_y, p_type)

    def set_overlay_visible(self, visible):
        """오버레이 표시/숨김"""
        if self.vtk_renderer:
            if not visible:
                self.vtk_renderer.clear_overlay_points()
            self.vtk_renderer.set_overlay_visible(visible)
            self.vtk_renderer.vtk_widget.GetRenderWindow().Render()

    def clear_overlay(self):
        """오버레이 클리어"""
        if self.vtk_renderer:
            self.vtk_renderer.clear_overlay_points()
            self.vtk_renderer.vtk_widget.GetRenderWindow().Render()

    # ============================================================
    # 데이터 및 렌더링 설정
    # ============================================================

    def set_volume_data(self, volume_data):
        if self.vtk_renderer:
            self.vtk_renderer.set_volume_data(volume_data)

    def update_transfer_function(self, tf_array):
        if self.vtk_renderer:
            self.vtk_renderer.update_transfer_function_optimized(tf_array)
    
    def set_background_color(self, color1, color2=None):
        if self.vtk_renderer:
            self.vtk_renderer.set_background_color(color1, color2)
    
    def set_shading(self, enabled):
        if self.vtk_renderer:
            self.vtk_renderer.set_shading(enabled)
    
    def set_lighting_property(self, property_type, value):
        if self.vtk_renderer:
            if property_type == "ambient":
                self.vtk_renderer.set_ambient(value)
            elif property_type == "diffuse":
                self.vtk_renderer.set_diffuse(value)
            elif property_type == "specular":
                self.vtk_renderer.set_specular(value)

    # ============================================================
    # 카메라 조작
    # ============================================================

    def zoom_in(self):
        current_value = self.zoom_slider.value()
        self.zoom_slider.setValue(min(150, current_value + 20))
    
    def zoom_out(self):
        current_value = self.zoom_slider.value()
        self.zoom_slider.setValue(max(10, current_value - 20))
    
    def reset_view(self):
        if self.vtk_renderer:
            self.vtk_renderer.reset_camera_manual()
            self.zoom_slider.setValue(100)
            self.zoom_label.setText("1.0x")
            self.camera_reset.emit()
    
    def on_zoom_slider_changed(self, value):
        if self.vtk_renderer:
            zoom_factor = value / 100.0
            if self.vtk_renderer.set_zoom_factor(zoom_factor):
                self.zoom_label.setText(f"{zoom_factor:.1f}x")
                self.zoom_changed.emit(zoom_factor)
    
    def update_zoom_slider_from_camera(self):
        if self.vtk_renderer:
            zoom_factor = self.vtk_renderer.get_current_zoom_factor()
            slider_value = int(zoom_factor * 100)
            slider_value = max(10, min(150, slider_value))
            
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(slider_value)
            self.zoom_slider.blockSignals(False)
            
            self.zoom_label.setText(f"{zoom_factor:.1f}x")
    
    def on_sampling_rate_changed(self, value):
        rate = value / 100.0
        self.sampling_rate_label.setText(f"{rate:.2f}x")
        
        if self.vtk_renderer:
            self.vtk_renderer.set_ray_sampling_rate(rate)
        
        self.sampling_rate_changed.emit(rate)

    # ============================================================
    # 파일 저장/로드
    # ============================================================

    def save_current_rendering(self, return_filename=False):
        if not self.vtk_renderer:
            QMessageBox.critical(self, "Error", "VTK 렌더러가 초기화되지 않았습니다.")
            return
        self.set_overlay_visible(False)
        use_square = self.save_square_radio.isChecked()
        filename = self.vtk_renderer.save_current_rendering(use_square_ratio=use_square)

        self.set_overlay_visible(True)
        if return_filename:
            return filename
        
        if filename:
            import os
            ratio_info = "1:1 ratio" if use_square else "current size"
            self.emit_status(f"Rendering saved ({ratio_info}): {os.path.basename(filename)}")
            QMessageBox.information(self, "Rendering Saved", f"Rendering saved:\n{filename}")
            self.rendering_saved.emit(filename)
        else:
            QMessageBox.critical(self, "Error", "Failed to save rendering")
    def save_multiview_rendering(self, return_filename=False, num_images=14):
        if not self.vtk_renderer:
            QMessageBox.critical(self, "Error", "VTK 렌더러가 초기화되지 않았습니다.")
            return
        self.set_overlay_visible(False)
        use_square = self.save_square_radio.isChecked()
        num_images = self.num_image_box.value()
        filename = self.vtk_renderer.save_multiview_rendering(use_square_ratio=use_square, num_images=num_images)

        self.set_overlay_visible(True)
        if return_filename:
            return filename
        
        if filename:
            import os
            ratio_info = "1:1 ratio" if use_square else "current size"
            self.emit_status(f"Rendering saved ({ratio_info}): {os.path.basename(filename)}")
            QMessageBox.information(self, "Rendering Saved", f"Rendering saved:\n{filename}")
            self.rendering_saved.emit(filename)
        else:
            QMessageBox.critical(self, "Error", "Failed to save rendering")

    def apply_clipping(self, axis, min_val, max_val):
        if hasattr(self, 'vtk_renderer') and self.vtk_renderer:
            # CT 볼륨 bounds 우선, 없으면 PET bounds 사용
            volume = None
            if hasattr(self.vtk_renderer, 'clipping_manager'):
                volume = self.vtk_renderer.clipping_manager.get_current_volume()

            # PET fallback
            if (volume is None or not volume.GetMapper() or not volume.GetMapper().GetInput()):
                if hasattr(self.vtk_renderer, 'pet_volume') and self.vtk_renderer.pet_volume:
                    pet = self.vtk_renderer.pet_volume
                    if pet.GetMapper() and pet.GetMapper().GetInput():
                        volume = pet

            if volume and volume.GetMapper() and volume.GetMapper().GetInput():
                bounds = volume.GetMapper().GetInput().GetBounds()

                axis_map = {'x': 0, 'y': 1, 'z': 2}
                if axis in axis_map:
                    axis_index = axis_map[axis]

                    if axis_index == 0:
                        axis_min, axis_max = bounds[0], bounds[1]
                    elif axis_index == 1:
                        axis_min, axis_max = bounds[2], bounds[3]
                    else:
                        axis_min, axis_max = bounds[4], bounds[5]

                    min_pos = axis_min + min_val * (axis_max - axis_min)
                    max_pos = axis_min + max_val * (axis_max - axis_min)

                    self.vtk_renderer.set_clipping_range(axis_index, min_pos, max_pos)
    
    def set_clipping_enabled(self, enabled):
        if hasattr(self, 'vtk_renderer') and self.vtk_renderer:
            self.vtk_renderer.enable_clipping(enabled)
            if not enabled:
                self.vtk_renderer.reset_clipping()
            else:
                self.apply_clipping('x', 0.0, 1.0)
                self.apply_clipping('y', 0.0, 1.0)
                self.apply_clipping('z', 0.0, 1.0)

    def save_current_camera_to_file(self):
        from PyQt6.QtWidgets import QFileDialog
        import json
        from datetime import datetime
        
        camera_info = self.get_camera_info()
        if not camera_info:
            QMessageBox.warning(self, "Warning", "카메라 정보를 가져올 수 없습니다.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Camera State", 
            f"./resources/Camera/camera_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            if not file_path.lower().endswith('.json'):
                file_path += '.json'
            
            try:
                camera_data = {
                    'camera_state': {
                        'position': list(camera_info['position']),
                        'focal_point': list(camera_info['focal_point']),
                        'view_up': list(camera_info['view_up']),
                        'view_angle': camera_info['view_angle'],
                        'distance': camera_info.get('distance', 0)
                    },
                    'zoom_factor': self.zoom_slider.value() / 100.0,
                    'timestamp': datetime.now().isoformat(),
                    'version': '3.0'
                }
                
                with open(file_path, 'w') as f:
                    json.dump(camera_data, f, indent=2)
                
                self.emit_status(f"Camera state saved: {file_path}")
                QMessageBox.information(self, "Save Complete", f"Camera state saved!\n{file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save camera state:\n{str(e)}")

    def load_camera_from_file(self):
        from PyQt6.QtWidgets import QFileDialog
        import json
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Camera State", "./resources/Camera",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    camera_data = json.load(f)
                
                if 'camera_state' in camera_data:
                    camera_state = camera_data['camera_state']
                    
                    camera_info = {
                        'position': tuple(camera_state['position']),
                        'focal_point': tuple(camera_state['focal_point']),
                        'view_up': tuple(camera_state['view_up']),
                        'view_angle': camera_state['view_angle'],
                        'distance': camera_state.get('distance', 0)
                    }
                    
                    if self.set_camera_info(camera_info):
                        if 'zoom_factor' in camera_data:
                            zoom_value = int(camera_data['zoom_factor'] * 100)
                            self.zoom_slider.setValue(zoom_value)
                        
                        self.emit_status(f"Camera state loaded")
                        QMessageBox.information(self, "Load Complete", "Camera state loaded!")
                    else:
                        QMessageBox.warning(self, "Warning", "Failed to apply camera state")
                else:
                    QMessageBox.warning(self, "Warning", "Invalid camera state file format")
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load camera state:\n{str(e)}")

    def get_camera_info(self):
        if self.vtk_renderer and hasattr(self.vtk_renderer, 'renderer'):
            renderer = self.vtk_renderer.renderer
            if renderer:
                camera = renderer.GetActiveCamera()
                if camera:
                    return {
                        'position': camera.GetPosition(),
                        'focal_point': camera.GetFocalPoint(),
                        'view_up': camera.GetViewUp(),
                        'view_angle': camera.GetViewAngle(),
                        'distance': camera.GetDistance()
                    }
        return None
    
    def set_camera_info(self, camera_info):
        if (self.vtk_renderer and hasattr(self.vtk_renderer, 'renderer') and 
            self.vtk_renderer.renderer and camera_info):
            camera = self.vtk_renderer.renderer.GetActiveCamera()
            if camera:
                try:
                    camera.SetPosition(camera_info['position'])
                    camera.SetFocalPoint(camera_info['focal_point'])
                    camera.SetViewUp(camera_info['view_up'])
                    camera.SetViewAngle(camera_info['view_angle'])
                    
                    if hasattr(self.vtk_renderer, 'vtk_widget'):
                        self.vtk_renderer.vtk_widget.GetRenderWindow().Render()
                    return True
                except Exception as e:
                    print(f"❌ 카메라 설정 실패: {e}")
        return False
    
    def add_point_3d(self, world_pos, p_type="positive"):
        """
        3D 월드 좌표에 구(Sphere) 마커 추가 (카메라 회전 시 객체에 고정됨)
        """
        if not self.vtk_renderer or not hasattr(self.vtk_renderer, 'renderer'):
            return

        x, y, z = world_pos
        
        # 1. Sphere Source 생성
        sphere = vtk.vtkSphereSource()
        sphere.SetCenter(x, y, z)
        sphere.SetRadius(2.0)  # 볼륨 크기에 맞춰 조절 필요 (예: 2mm)
        sphere.SetThetaResolution(16)
        sphere.SetPhiResolution(16)
        
        # 2. Mapper & Actor 설정
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(sphere.GetOutputPort())
        
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        
        # 색상 설정 (Pos: 파랑, Neg: 빨강)
        if p_type == "positive":
            actor.GetProperty().SetColor(0.0, 1.0, 0.0) # Green for clarity
        else:
            actor.GetProperty().SetColor(1.0, 0.0, 0.0)
            
        # 3. 렌더러에 추가 및 저장 (나중에 삭제를 위해)
        self.vtk_renderer.renderer.AddActor(actor)
        
        if not hasattr(self, 'markers_3d'):
            self.markers_3d = []
        self.markers_3d.append(actor)
        
        self.vtk_renderer.vtk_widget.GetRenderWindow().Render()
        print(f"📍 3D Marker Added at ({x:.2f}, {y:.2f}, {z:.2f})")

    def clear_3d_markers(self):
        """모든 3D 마커 제거"""
        if hasattr(self, 'markers_3d'):
            for actor in self.markers_3d:
                self.vtk_renderer.renderer.RemoveActor(actor)
            self.markers_3d = []
            self.vtk_renderer.vtk_widget.GetRenderWindow().Render()
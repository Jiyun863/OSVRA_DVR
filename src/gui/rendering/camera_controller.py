"""
Camera Controller
renderer_widget.py에서 카메라 제어 로직이 분리되었습니다.

[Phase 8 추가]
- 구면 좌표(longitude, latitude) ↔ 카메라 위치 변환
- Navigation Sphere와 양방향 동기화 지원
"""
import math

try:
    import vtk
    VTK_AVAILABLE = True
except ImportError:
    VTK_AVAILABLE = False


class CameraController:
    """VTK 카메라 상태 및 줌을 제어하는 매니저 클래스"""

    def __init__(self, renderer_widget):
        """
        Args:
            renderer_widget: VTKMultiVolumeRenderer 인스턴스
        """
        self.widget = renderer_widget
        self.saved_camera_state = None
        self.current_zoom_factor = 1.0
        
        # 동기화 플래그 (무한 루프 방지)
        self._sync_in_progress = False

    def get_camera(self):
        """렌더러로부터 활성 카메라 객체 획득"""
        if VTK_AVAILABLE and self.widget.renderer:
            return self.widget.renderer.GetActiveCamera()
        return None

    def save_camera_state(self):
        """현재 카메라의 위치, 초점, 각도 등 상태 저장"""
        camera = self.get_camera()
        if camera:
            self.saved_camera_state = {
                'position': camera.GetPosition(),
                'focal_point': camera.GetFocalPoint(),
                'view_up': camera.GetViewUp(),
                'view_angle': camera.GetViewAngle(),
                'clipping_range': camera.GetClippingRange(),
                'distance': camera.GetDistance()
            }
            return True
        return False

    def restore_camera_state(self):
        """저장된 카메라 상태를 복원하고 렌더링 갱신"""
        camera = self.get_camera()
        if camera and self.saved_camera_state:
            try:
                camera.SetPosition(self.saved_camera_state['position'])
                camera.SetFocalPoint(self.saved_camera_state['focal_point'])
                camera.SetViewUp(self.saved_camera_state['view_up'])
                camera.SetViewAngle(self.saved_camera_state['view_angle'])
                camera.SetClippingRange(self.saved_camera_state['clipping_range'])
                
                if hasattr(self.widget, 'vtk_widget'):
                    self.widget.vtk_widget.GetRenderWindow().Render()
                return True
            except Exception as e:
                print(f"카메라 상태 복원 실패: {e}")
        return False

    def get_camera_state(self):
        """외부 반환용 카메라 상태 획득"""
        camera = self.get_camera()
        if camera:
            return {
                'position': camera.GetPosition(),
                'focal_point': camera.GetFocalPoint(),
                'view_up': camera.GetViewUp(),
                'view_angle': camera.GetViewAngle(),
                'clipping_range': camera.GetClippingRange(),
                'distance': camera.GetDistance()
            }
        return None

    def set_camera_state(self, state):
        """외부에서 전달받은 카메라 상태 적용"""
        camera = self.get_camera()
        if camera and state:
            try:
                camera.SetPosition(state['position'])
                camera.SetFocalPoint(state['focal_point'])
                camera.SetViewUp(state['view_up'])
                camera.SetViewAngle(state['view_angle'])
                camera.SetClippingRange(state['clipping_range'])
                
                if hasattr(self.widget, 'vtk_widget'):
                    self.widget.vtk_widget.GetRenderWindow().Render()
                return True
            except Exception as e:
                print(f"카메라 상태 적용 실패: {e}")
        return False

    def setup_camera(self, force_reset=False):
        """카메라 초기 설정 및 자동 리셋"""
        if not VTK_AVAILABLE or not self.widget.renderer:
            return
        
        # 강제 리셋이 아니고 저장된 상태가 있다면 복원 시도
        if not force_reset and self.saved_camera_state:
            if self.restore_camera_state():
                return
        
        camera = self.get_camera()
        if camera:
            camera.SetPosition(1.5, 1.5, 1.5)
            camera.SetFocalPoint(0, 0, 0)
            camera.SetViewUp(0, 0, 1)
            camera.SetViewAngle(30)
            camera.SetClippingRange(0.1, 100.0)
            
            if force_reset or self.saved_camera_state is None:
                self.widget.renderer.ResetCamera()
                camera.Zoom(0.8)

    def reset_camera_manual(self):
        """카메라를 초기 위치로 수동 리셋"""
        self.saved_camera_state = None
        self.setup_camera(force_reset=True)

    def get_current_zoom_factor(self):
        """현재 ViewAngle 기반 줌 팩터 계산"""
        camera = self.get_camera()
        if camera:
            view_angle = camera.GetViewAngle()
            zoom_factor = 30.0 / view_angle if view_angle > 0 else 1.0
            self.current_zoom_factor = zoom_factor
            return zoom_factor
        return 1.0
    
    def set_zoom_factor(self, zoom_factor):
        """줌 팩터에 따른 ViewAngle 설정"""
        camera = self.get_camera()
        if camera:
            new_view_angle = 30.0 / max(0.1, zoom_factor)
            camera.SetViewAngle(new_view_angle)
            self.current_zoom_factor = zoom_factor
            
            if hasattr(self.widget, 'vtk_widget'):
                self.widget.vtk_widget.GetRenderWindow().Render()
            return True
        return False

    # ============================================================
    # Phase 8: 구면 좌표 ↔ 카메라 위치 변환
    # ============================================================
    
    def set_camera_from_angles(self, longitude: float, latitude: float):
        """
        구면 좌표(longitude, latitude)로 카메라 위치 설정
        
        Navigation Sphere에서 viewpoint 선택 시 호출됩니다.
        
        Args:
            longitude: 경도 (도, 0~360)
            latitude: 위도 (도, -90~90)
        """
        if self._sync_in_progress:
            return False
        
        camera = self.get_camera()
        if not camera:
            return False
        
        try:
            self._sync_in_progress = True
            
            # 현재 focal point와 distance 유지
            focal_point = camera.GetFocalPoint()
            distance = camera.GetDistance()
            
            # 구면 좌표 → 직교 좌표 변환
            lon_rad = math.radians(longitude)
            lat_rad = math.radians(latitude)
            
            # 카메라 위치 계산 (focal point 중심으로 구면 위의 점)
            x = focal_point[0] + distance * math.cos(lat_rad) * math.cos(lon_rad)
            y = focal_point[1] + distance * math.cos(lat_rad) * math.sin(lon_rad)
            z = focal_point[2] + distance * math.sin(lat_rad)
            
            camera.SetPosition(x, y, z)
            
            # View Up 벡터 조정 (극점 근처에서 gimbal lock 방지)
            if abs(latitude) > 85:
                # 극점 근처: view up을 y축 방향으로
                view_up = (0, 1, 0) if latitude > 0 else (0, -1, 0)
            else:
                # 일반적인 경우: z축이 위
                view_up = (0, 0, 1)
            
            camera.SetViewUp(view_up)
            
            # 렌더링 갱신
            if hasattr(self.widget, 'vtk_widget'):
                self.widget.vtk_widget.GetRenderWindow().Render()
            
            return True
            
        except Exception as e:
            print(f"카메라 각도 설정 실패: {e}")
            return False
        finally:
            self._sync_in_progress = False
    
    def get_camera_angles(self) -> tuple:
        """
        현재 카메라 위치를 구면 좌표(longitude, latitude)로 변환
        
        VTK 카메라 변경 시 Navigation Sphere 업데이트에 사용됩니다.
        
        Returns:
            (longitude°, latitude°) 튜플, 실패 시 (0.0, 0.0)
        """
        if self._sync_in_progress:
            return None
        
        camera = self.get_camera()
        if not camera:
            return (0.0, 0.0)
        
        try:
            position = camera.GetPosition()
            focal_point = camera.GetFocalPoint()
            
            # focal point 기준 상대 위치
            dx = position[0] - focal_point[0]
            dy = position[1] - focal_point[1]
            dz = position[2] - focal_point[2]
            
            # 거리 계산
            distance = math.sqrt(dx*dx + dy*dy + dz*dz)
            if distance < 1e-8:
                return (0.0, 0.0)
            
            # 직교 좌표 → 구면 좌표 변환
            # latitude: z 성분으로부터
            latitude = math.degrees(math.asin(dz / distance))
            
            # longitude: x, y 성분으로부터
            longitude = math.degrees(math.atan2(dy, dx))
            
            # longitude를 0~360 범위로 정규화
            if longitude < 0:
                longitude += 360
            
            return (longitude, latitude)
            
        except Exception as e:
            print(f"카메라 각도 계산 실패: {e}")
            return (0.0, 0.0)
    
    def is_sync_in_progress(self) -> bool:
        """동기화 진행 중인지 확인 (무한 루프 방지용)"""
        return self._sync_in_progress
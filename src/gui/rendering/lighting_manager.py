"""
Lighting Manager
renderer_widget.py에서 조명 관리 로직이 분리되었습니다.

멀티 볼륨(vtkMultiVolume)에서는 vtkMultiVolume.GetProperty()가 아니라
각 포트별 vtkVolumeProperty(CT/PET)를 직접 제어해야 합니다.
"""
try:
    import vtk
    VTK_AVAILABLE = True
except ImportError:
    VTK_AVAILABLE = False


class LightingManager:
    """VTK 멀티볼륨 조명/쉐이딩 상태를 관리하는 클래스"""

    def __init__(self, renderer_widget):
        self.widget = renderer_widget
        self.key_light = None
        self.fill_light = None

        # 기본 조명 위치 정보
        self.light_positions = {
            'key': [1, 1, 1],
            'fill': [-1, 0.5, 0.5],
        }

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    def _iter_target_properties(self):
        """현재 렌더링 중인 포트별 vtkVolumeProperty 순회"""
        if not hasattr(self.widget, '_iter_volume_properties'):
            return []
        return list(self.widget._iter_volume_properties())

    def _render(self):
        """렌더링 갱신"""
        if hasattr(self.widget, 'vtk_widget') and self.widget.vtk_widget:
            self.widget.vtk_widget.GetRenderWindow().Render()

    # ------------------------------------------------------------------
    # 조명 객체 생성/제어
    # ------------------------------------------------------------------
    def setup_lighting(self):
        """초기 조명(Key, Fill) 설정"""
        if not VTK_AVAILABLE or not getattr(self.widget, 'renderer', None):
            return

        self.widget.renderer.RemoveAllLights()

        # Key light
        self.key_light = vtk.vtkLight()
        self.key_light.SetLightTypeToSceneLight()
        self.key_light.SetPosition(*self.light_positions['key'])
        self.key_light.SetFocalPoint(0, 0, 0)
        self.key_light.SetColor(1.0, 0.95, 0.8)
        self.key_light.SetIntensity(0.8)
        self.widget.renderer.AddLight(self.key_light)

        # Fill light
        self.fill_light = vtk.vtkLight()
        self.fill_light.SetLightTypeToSceneLight()
        self.fill_light.SetPosition(*self.light_positions['fill'])
        self.fill_light.SetFocalPoint(0, 0, 0)
        self.fill_light.SetColor(0.8, 0.9, 1.0)
        self.fill_light.SetIntensity(0.3)
        self.widget.renderer.AddLight(self.fill_light)

    # ------------------------------------------------------------------
    # 쉐이딩 / 머티리얼 파라미터
    # ------------------------------------------------------------------
    def reapply_to_current_properties(self):
        """파이프라인 재구성 후 저장된 조명 상태를 현재 property들에 재적용"""
        try:
            for modality, prop in self._iter_target_properties():
                should_shade = self.widget._should_shade_modality(modality)
                if should_shade:
                    prop.ShadeOn()
                else:
                    prop.ShadeOff()

                prop.SetAmbient(float(self.widget.ambient))
                prop.SetDiffuse(float(self.widget.diffuse))
                prop.SetSpecular(float(self.widget.specular))
                prop.SetSpecularPower(float(self.widget.specular_power))
        except Exception as e:
            print(f"조명 상태 재적용 실패: {e}")

    def set_shading(self, enabled):
        """전역 쉐이딩 on/off. 켜질 때는 modality별 정책(CT/PET)을 따름"""
        try:
            self.widget.shading_enabled = bool(enabled)
            self.reapply_to_current_properties()
            self._render()
        except Exception as e:
            print(f"쉐이딩 설정 실패: {e}")

    def set_ct_shading(self, enabled):
        """CT 포트 쉐이딩 개별 제어"""
        try:
            self.widget.shade_ct = bool(enabled)
            self.reapply_to_current_properties()
            self._render()
        except Exception as e:
            print(f"CT 쉐이딩 설정 실패: {e}")

    def set_pet_shading(self, enabled):
        """PET 포트 쉐이딩 개별 제어"""
        try:
            self.widget.shade_pet = bool(enabled)
            self.reapply_to_current_properties()
            self._render()
        except Exception as e:
            print(f"PET 쉐이딩 설정 실패: {e}")

    def set_ambient(self, value):
        self._set_property('ambient', value)

    def set_diffuse(self, value):
        self._set_property('diffuse', value)

    def set_specular(self, value):
        self._set_property('specular', value)

    def set_specular_power(self, value):
        self._set_property('specular_power', value)

    def _set_property(self, prop_name, value):
        """Ambient / Diffuse / Specular / SpecularPower 공통 설정"""
        try:
            value = float(value)

            if prop_name == 'ambient':
                self.widget.ambient = value
            elif prop_name == 'diffuse':
                self.widget.diffuse = value
            elif prop_name == 'specular':
                self.widget.specular = value
            elif prop_name == 'specular_power':
                self.widget.specular_power = value

            for _, prop in self._iter_target_properties():
                if prop_name == 'ambient':
                    prop.SetAmbient(value)
                elif prop_name == 'diffuse':
                    prop.SetDiffuse(value)
                elif prop_name == 'specular':
                    prop.SetSpecular(value)
                elif prop_name == 'specular_power':
                    prop.SetSpecularPower(value)

            self._render()
        except Exception as e:
            print(f"{prop_name} 설정 실패: {e}")

    # ------------------------------------------------------------------
    # Light color / position
    # ------------------------------------------------------------------
    def set_ambient_color(self, r, g, b):
        if self.key_light:
            self.key_light.SetAmbientColor(r, g, b)
        if self.fill_light:
            self.fill_light.SetAmbientColor(r, g, b)
        self._render()

    def set_diffuse_color(self, r, g, b):
        if self.key_light:
            self.key_light.SetDiffuseColor(r, g, b)
        if self.fill_light:
            self.fill_light.SetDiffuseColor(r, g, b)
        self._render()

    def set_specular_color(self, r, g, b):
        if self.key_light:
            self.key_light.SetSpecularColor(r, g, b)
        if self.fill_light:
            self.fill_light.SetSpecularColor(r, g, b)
        self._render()

    def set_light_position(self, light_type, x, y, z):
        """라이트 위치 설정"""
        if light_type == 'key' and self.key_light:
            self.key_light.SetPosition(x, y, z)
            self.light_positions['key'] = [x, y, z]
        elif light_type == 'fill' and self.fill_light:
            self.fill_light.SetPosition(x, y, z)
            self.light_positions['fill'] = [x, y, z]
        self._render()

    def set_follow_camera(self, enabled):
        """Follow Camera 모드 설정"""
        if not VTK_AVAILABLE:
            return

        if enabled:
            if self.key_light:
                self.key_light.SetLightTypeToCameraLight()
            if self.fill_light:
                self.fill_light.SetLightTypeToCameraLight()
        else:
            if self.key_light:
                self.key_light.SetLightTypeToSceneLight()
            if self.fill_light:
                self.fill_light.SetLightTypeToSceneLight()
        self._render()

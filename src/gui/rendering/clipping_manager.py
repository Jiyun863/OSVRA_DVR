"""
Volume Clipping Manager
renderer_widget.py의 내부 클래스에서 분리됨
"""
import vtk


class VolumeClippingManager:
    """볼륨 클리핑을 관리하는 클래스"""
    
    def __init__(self, parent_renderer):
        """
        Args:
            parent_renderer: VTKMultiVolumeRenderer 인스턴스
        """
        self.parent = parent_renderer
        self.clipping_planes = vtk.vtkPlaneCollection()
        self.clipping_enabled = False
        
        # 각 축에 대한 클리핑 평면 (min, max)
        self.planes = {
            'x_min': vtk.vtkPlane(),
            'x_max': vtk.vtkPlane(),
            'y_min': vtk.vtkPlane(),
            'y_max': vtk.vtkPlane(),
            'z_min': vtk.vtkPlane(),
            'z_max': vtk.vtkPlane()
        }
        
        self.setup_clipping_planes()
    
    def setup_clipping_planes(self):
        """클리핑 평면 초기 설정 - 수정 버전"""
        
        # 평면을 볼륨 외부에 초기화 (매우 큰 값으로)
        LARGE_VALUE = 10000
        
        # X축 평면 (min: x좌표가 작은 쪽을 잘라냄, max: x좌표가 큰 쪽을 잘라냄)
        self.planes['x_min'].SetOrigin(-LARGE_VALUE, 0, 0)
        self.planes['x_min'].SetNormal(1, 0, 0)
        
        self.planes['x_max'].SetOrigin(LARGE_VALUE, 0, 0)
        self.planes['x_max'].SetNormal(-1, 0, 0)
        
        # Y축 평면
        self.planes['y_min'].SetOrigin(0, -LARGE_VALUE, 0)
        self.planes['y_min'].SetNormal(0, 1, 0)
        
        self.planes['y_max'].SetOrigin(0, LARGE_VALUE, 0)
        self.planes['y_max'].SetNormal(0, -1, 0)
        
        # Z축 평면
        self.planes['z_min'].SetOrigin(0, 0, -LARGE_VALUE)
        self.planes['z_min'].SetNormal(0, 0, 1)
        
        self.planes['z_max'].SetOrigin(0, 0, LARGE_VALUE)
        self.planes['z_max'].SetNormal(0, 0, -1)
        
        # 평면 컬렉션에 추가
        self.clipping_planes.RemoveAllItems()
        for plane in self.planes.values():
            self.clipping_planes.AddItem(plane)
        
        # print("✅ Clipping planes initialized at safe positions")

    def get_current_volume(self):
        """현재 활성화된 CT 볼륨 객체 반환 (하위 호환용)"""
        if self.parent.standard_volume:
            return self.parent.standard_volume
        return None

    def get_all_clipping_targets(self):
        """클리핑을 적용할 모든 볼륨 반환 (CT + PET)"""
        targets = []
        if self.parent.standard_volume:
            targets.append(self.parent.standard_volume)
        # PET 볼륨 지원
        if hasattr(self.parent, 'pet_volume') and self.parent.pet_volume:
            targets.append(self.parent.pet_volume)
        # class_volumes 지원
        targets += [v for v in self.parent.class_volumes.values() if v]
        return targets

    def update_clipping_target(self):
        """CT + PET 모든 볼륨에 클리핑 적용 또는 제거"""
        all_targets = self.get_all_clipping_targets()

        for vol in all_targets:
            if not vol or not vol.GetMapper():
                continue
            if self.clipping_enabled:
                vol.GetMapper().SetClippingPlanes(self.clipping_planes)
            else:
                vol.GetMapper().RemoveAllClippingPlanes()

        # 렌더링 업데이트
        if hasattr(self.parent, 'vtk_widget') and self.parent.vtk_widget:
            self.parent.vtk_widget.GetRenderWindow().Render()

    def set_clipping_range(self, axis_index, min_pos, max_pos):
        """특정 축의 클리핑 범위 설정 (0=X, 1=Y, 2=Z)"""
        if axis_index == 0:  # X축
            self.planes['x_min'].SetOrigin(min_pos, 0, 0)
            self.planes['x_max'].SetOrigin(max_pos, 0, 0)
        elif axis_index == 1:  # Y축
            self.planes['y_min'].SetOrigin(0, min_pos, 0)
            self.planes['y_max'].SetOrigin(0, max_pos, 0)
        elif axis_index == 2:  # Z축
            self.planes['z_min'].SetOrigin(0, 0, min_pos)
            self.planes['z_max'].SetOrigin(0, 0, max_pos)
        
        if self.clipping_enabled:
            self.update_clipping_target()

    def enable_clipping(self, enabled):
        """클리핑 활성화/비활성화"""
        
        if self.clipping_enabled == enabled:
            return 
        
        self.clipping_enabled = enabled

        # CT 또는 PET 중 하나라도 없으면 경고
        if not self.get_all_clipping_targets():
            print("⚠️ No volume/mapper available for clipping")
            return

        if enabled:
            # ✅ 클리핑 재활성화 시 강제 리프레시 (CT + PET 모두)
            all_targets = self.get_all_clipping_targets()

            # 1. 모든 볼륨의 클리핑 평면 제거
            for vol in all_targets:
                if vol and vol.GetMapper():
                    vol.GetMapper().RemoveAllClippingPlanes()

            # 2. 평면 위치 리셋
            self.reset_clipping()

            # 3. 평면 컬렉션 재생성
            self.clipping_planes = vtk.vtkPlaneCollection()
            for plane in self.planes.values():
                self.clipping_planes.AddItem(plane)

            # 4. 모든 볼륨에 새 평면 컬렉션 적용
            for vol in all_targets:
                if vol and vol.GetMapper():
                    vol.GetMapper().SetClippingPlanes(self.clipping_planes)
                    vol.GetMapper().Modified()

            print(f"✅ Clipping enabled (CT+PET, forced refresh) with {self.clipping_planes.GetNumberOfItems()} planes")
        else:
            # 모든 볼륨의 클리핑 해제
            all_targets = self.get_all_clipping_targets()
            for vol in all_targets:
                if vol and vol.GetMapper():
                    vol.GetMapper().RemoveAllClippingPlanes()
            print("✅ Clipping disabled (CT+PET)")
        
        # 렌더 윈도우 강제 업데이트
        if hasattr(self.parent, 'vtk_widget') and self.parent.vtk_widget:
            render_window = self.parent.vtk_widget.GetRenderWindow()
            render_window.Render()


    def reset_clipping(self):
        """모든 클리핑 평면을 초기 볼륨 경계로 리셋 - 개선된 버전"""
        
        # 먼저 안전한 위치로 초기화
        self.setup_clipping_planes()
        
        current_volume = self.get_current_volume()
        
        if current_volume and current_volume.GetMapper():
            mapper = current_volume.GetMapper()
            
            # VTK ImageData의 실제 bounds 가져오기
            if mapper.GetInput():
                bounds = mapper.GetInput().GetBounds()
                # bounds = [xmin, xmax, ymin, ymax, zmin, zmax]
                
                # print(f"📊 Volume bounds: X[{bounds[0]:.1f}, {bounds[1]:.1f}], Y[{bounds[2]:.1f}, {bounds[3]:.1f}], Z[{bounds[4]:.1f}, {bounds[5]:.1f}]")
                
                # 약간의 여유를 두고 설정 (볼륨이 잘리지 않도록)
                epsilon = 0.1
                self.set_clipping_range(0, bounds[0] - epsilon, bounds[1] + epsilon)  # X
                self.set_clipping_range(1, bounds[2] - epsilon, bounds[3] + epsilon)  # Y
                self.set_clipping_range(2, bounds[4] - epsilon, bounds[5] + epsilon)  # Z
                
                return
        
        # Fallback: 볼륨 데이터가 있으면 shape 사용
        if self.parent.volume_data is not None:
            shape = self.parent.volume_data.shape
            spacing = getattr(self.parent, 'voxel_spacing', [1.0, 1.0, 1.0])
            
            if spacing is None:
                spacing = [1.0, 1.0, 1.0]
            
            # 물리적 크기 계산
            physical_bounds = [
                -0.1, shape[0] * spacing[0] + 0.1,
                -0.1, shape[1] * spacing[1] + 0.1,
                -0.1, shape[2] * spacing[2] + 0.1
            ]
            
            print(f"📊 Using shape {shape} with spacing {spacing}")
            print(f"📊 Physical bounds: X[{physical_bounds[0]:.1f}, {physical_bounds[1]:.1f}], Y[{physical_bounds[2]:.1f}, {physical_bounds[3]:.1f}], Z[{physical_bounds[4]:.1f}, {physical_bounds[5]:.1f}]")
            
            self.set_clipping_range(0, physical_bounds[0], physical_bounds[1])
            self.set_clipping_range(1, physical_bounds[2], physical_bounds[3])
            self.set_clipping_range(2, physical_bounds[4], physical_bounds[5])
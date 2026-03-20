"""
Screenshot Manager
renderer_widget.py에서 분리됨
"""
import os
from datetime import datetime
import nibabel as nib
import numpy as np
import math
import traceback
import json
import cv2
try:
    import vtk
    VTK_AVAILABLE = True
except ImportError:
    VTK_AVAILABLE = False


## screenshot_manager.py 수정본

class ScreenshotManager:
    """렌더링 스크린샷 관리 클래스"""
    
    def __init__(self, renderer_widget):
        """
        Args:
            renderer_widget: VTKMultiVolumeRenderer 인스턴스
        """
        self.renderer_widget = renderer_widget
        # 자주 사용하는 속성들을 미리 참조해두면 코드가 깔끔해집니다.
        self.output_dir = "./resources/Rendered_Image"
    
    def save_rgba_img(self, filename):
        try:
            render_window = self.renderer_widget.vtk_widget.GetRenderWindow()
            
            # 스크린샷 촬영
            screenshot_filter = vtk.vtkWindowToImageFilter()
            screenshot_filter.SetInput(render_window)
            screenshot_filter.SetInputBufferTypeToRGBA()
            screenshot_filter.ReadFrontBufferOff()
            screenshot_filter.Update()
            
            # PNG 저장
            writer = vtk.vtkPNGWriter()
            writer.SetFileName(filename)
            writer.SetInputConnection(screenshot_filter.GetOutputPort())
            writer.Write()
            
        except Exception as e:
            print(">>> Failed to save_rgba_img()")
            traceback.print_exc()
        return filename
        
    def save_current_rendering(self, use_square_ratio=False):
        """현재 렌더링 저장"""
        if not VTK_AVAILABLE or self.renderer_widget.renderer is None:
            return None
        
        render_window = self.renderer_widget.vtk_widget.GetRenderWindow()
        current_size = render_window.GetSize()

        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ratio_suffix = "_1to1" if use_square_ratio else "_current" # 촬영 렌더링 비율 설정
            filename = os.path.join(self.output_dir, f"render_{timestamp}{ratio_suffix}.png")   
            depth_filename = os.path.join(self.output_dir, f"depth_{timestamp}{ratio_suffix}.png")

            if use_square_ratio: # 1:1 비율 기준 저장 
                max_size = 512
                render_window.SetSize(max_size, max_size)
                render_window.Render()

            # RGBA & Depth 이미지 저장
            _ = self.save_rgba_img(filename)
            depth = self.renderer_widget.get_depth_map_array()
            cv2.imwrite(depth_filename, depth)
            print(f"렌더링 저장: {filename}")

            return filename
        except Exception as e:
            print(f">>> Failed save_current_rendering()")
            traceback.print_exc()
            return None
        finally:
            if use_square_ratio:
                render_window.SetSize(current_size[0], current_size[1])
                render_window.Render()
            
    
    def export_screenshot(self, filename, resolution=(1920, 1080)):
        """고해상도 스크린샷 저장"""
        # 에러 발생 지점 수정
        if not VTK_AVAILABLE or self.renderer_widget.renderer is None:
            return False
        
        try:
            render_window = self.renderer_widget.vtk_widget.GetRenderWindow()
            original_size = render_window.GetSize()
            
            # 고해상도로 설정
            render_window.SetSize(resolution[0], resolution[1])
            render_window.Render()
            
            # 스크린샷 촬영 및 저장 로직 동일...
            # (중략)
            
            return True
        except Exception as e:
            print(f"스크린샷 저장 실패: {e}")
            return False
    
    ### Multi-view Rendering 관련 기능 ###
    def _calculate_camera_pose(self, az_idx, az_count, pol_idx, pol_count, distance):
        """generate_mvrecon_3d_input.py의 카메라 위치 계산 로직 이식"""
        # phi (Azimuth)
        phi = az_idx * (2 * np.pi / az_count)
        
        # phi_rot (Rotation around Y)
        # Row-major convention for numpy arrays when creating manually
        phi_rot = np.eye(4)
        phi_rot[0,0] = np.cos(phi)
        phi_rot[0,2] = np.sin(phi)
        phi_rot[2,0] = -np.sin(phi)
        phi_rot[2,2] = np.cos(phi)

        # theta (Polar)
        # Note: script uses th.arange(1,P+1) for P=1 -> theta = 0
        theta = (pol_idx + 1) * (np.pi / (pol_count + 1)) - np.pi/2
        
        # theta_rot (Rotation around X)
        theta_rot = np.eye(4)
        theta_rot[1,1] = np.cos(theta)
        theta_rot[1,2] = -np.sin(theta)
        theta_rot[2,1] = np.sin(theta)
        theta_rot[2,2] = np.cos(theta)

        # Combined Rotation R = theta_rot @ phi_rot
        R = theta_rot @ phi_rot
        
        # Translation T (shift camera back by distance along Z)
        T = np.eye(4)
        T[2,3] = -distance
        
        # ModelView = T @ R
        MV = T @ R
        
        # CameraExtrinsics (World to Camera) is MV.
        # We need Camera Position in World Space -> Inverse of MV
        CamToWorld = np.linalg.inv(MV)
        
        # Position is origin (0,0,0) in Camera Space transformed to World
        pos = CamToWorld[:3, 3]
        
        # View Up vector is (0,1,0) in Camera Space transformed to World (rotate only)
        # Using full matrix is fine since W component of vector is 0
        up_vec = CamToWorld @ np.array([0, 1, 0, 0])
        
        return pos, up_vec[:3]

    def save_multiview_rendering(self, use_square_ratio=False, num_images=14):
        """원형 좌표계에서 다각도 렌더링 촬영"""
        def get_raw_matrices(cam, radius):
            """Dmesh++ 규격에 맞게 정규화된 MV, Proj 행렬 생성"""
            # 1. Model-View Matrix (World -> Camera) 정규화 (요구사항 2-B, 2-C)
            pos = np.array(cam.GetPosition())
            focal = np.array(cam.GetFocalPoint())
            up = np.array(cam.GetViewUp())

            z_axis = (pos - focal) / np.linalg.norm(pos - focal)
            x_axis = np.cross(up, z_axis)
            x_axis /= (np.linalg.norm(x_axis) + 1e-6)
            y_axis = np.cross(z_axis, x_axis)

            mv = np.eye(4, dtype=np.float32)
            mv[0, :3] = x_axis
            mv[1, :3] = y_axis
            mv[2, :3] = z_axis
            
            # [핵심] 카메라의 물리적 거리를 볼륨 반지름으로 나누어 정규화 (dist / radius)
            # 이렇게 하면 Dmesh++ 기준에서 물체는 원점에 있고 카메라 거리는 2.0 내외가 됩니다.
            dist_phys = np.linalg.norm(pos - focal)
            mv[2, 3] = -dist_phys / radius

            # 2. Projection Matrix 정규화 (요구사항 2-D)
            # Dmesh++ 표준 n=1.0, f=50.0 및 flip_y=True 적용
            fov_rad = np.radians(cam.GetViewAngle())
            n, f = 1.0, 10.0
            r = np.tan(fov_rad / 2.0) * n # right plane
            
            proj = np.zeros((4, 4), dtype=np.float32)
            proj[0, 0] = n / r
            proj[1, 1] = -n / r # flip_y
            proj[2, 2] = -(f + n) / (f - n)
            proj[2, 3] = -(2 * f * n) / (f - n)
            proj[3, 2] = -1.0
            
            return mv, proj
    
        # 폴더 제작
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_dir = os.path.join(self.output_dir, timestamp)
        image_dir = os.path.join(save_dir, "images_o")
        os.makedirs(image_dir, exist_ok=True)

        # 현재 카메라 상태 저장
        camera = self.renderer_widget.renderer.GetActiveCamera()
        original_focal_point = np.array(camera.GetFocalPoint())
        original_position = np.array(camera.GetPosition())
        original_view_up = np.array(camera.GetViewUp())
        
        # 현재 거리 계산 (반지름으로 사용)
        current_distance = np.linalg.norm(original_position - original_focal_point)
        
        # 메타데이터 저장을 위한 리스트
        mv_list = []
        proj_list = []
        
        cnt = 0 # 이미지 카운트
        try:
            # 볼륨의 물리적 반지름을 계산하여 Dmesh++의 DOMAIN=1.0 세상을 만듭니다.
            dims = np.array(self.renderer_widget.volume_data.shape)
            spacing = np.array(self.renderer_widget.voxel_spacing)
            physical_radius = np.max((dims * spacing) / 2.0) # 볼륨의 절반 크기 중 최대값을 1.0 단위(Radius)로 정의합니다.

            render_window = self.renderer_widget.vtk_widget.GetRenderWindow()
            current_size = render_window.GetSize()
            if use_square_ratio: # 1:1 비율 기준 저장 
                max_size = 512
                render_window.SetSize(max_size, max_size)
                render_window.Render()

            w2i = vtk.vtkWindowToImageFilter()
            w2i.SetInput(render_window)
            w2i.SetInputBufferTypeToRGBA()
            w2i.ReadFrontBufferOff()
            
            writer = vtk.vtkPNGWriter()
            writer.SetInputConnection(w2i.GetOutputPort())
            # Multi-view 촬영 루프
            for i in range(num_images):
                for j in range(num_images):
                    # 파일 경로 및 이름 설정
                    filename_rel = f"diffuse_{cnt:03d}.png"
                    depth_filename_rel = f"depth_{cnt:03d}.png"
                    filename_abs = os.path.join(image_dir, filename_rel)
                    depth_filename_abs = os.path.join(image_dir, depth_filename_rel)

                    # 카메라 위치 계산
                    pos_offset, new_view_up = self._calculate_camera_pose(i, num_images, j, num_images, current_distance)
                    
                    # 새로운 카메라 위치 설정
                    new_position = original_focal_point + pos_offset
                    camera.SetPosition(new_position)
                    camera.SetFocalPoint(original_focal_point)
                    camera.SetViewUp(new_view_up)
                    
                    # 렌더링 업데이트
                    self.renderer_widget.renderer.ResetCameraClippingRange()
                    self.renderer_widget.vtk_widget.GetRenderWindow().Render()
                    
                    # RGB & Depth이미지 저장
                    # _ = self.save_rgba_img(filename_abs)
                    # RGB 저장 (Optimized reuse)
                    w2i.Modified() # 변경 사항 반영 요청
                    w2i.Update()   # 필터 업데이트
                    writer.SetFileName(filename_abs)
                    writer.Write()
                    depth = self.renderer_widget.get_depth_map_array()
                    cv2.imwrite(depth_filename_abs, cv2.cvtColor(depth, cv2.COLOR_GRAY2BGR))

                    # Dmesh++용 파라미터 추출 및 저장
                    mv_raw, proj_raw = get_raw_matrices(camera, physical_radius)
                    mv_list.append(mv_raw)
                    proj_list.append(proj_raw)

                    cnt += 1
            mv_final = np.stack(mv_list, axis=0)
            proj_final = np.stack(proj_list, axis=0)

            np.save(os.path.join(save_dir, "mv.npy"), mv_final)
            np.save(os.path.join(save_dir, "proj.npy"), proj_final)
            return save_dir
        except Exception as e:
            print(f">>> Failed save_multiview_rendering()")
            traceback.print_exc()
            
        finally:
            # 카메라 상태 복구
            camera.SetPosition(original_position)
            camera.SetFocalPoint(original_focal_point)
            camera.SetViewUp(original_view_up)
            self.renderer_widget.renderer.ResetCameraClippingRange()
            self.renderer_widget.vtk_widget.GetRenderWindow().Render()
            if use_square_ratio:
                render_window.SetSize(current_size[0], current_size[1])
                render_window.Render()
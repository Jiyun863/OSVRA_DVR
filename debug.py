import numpy as np
import vtk
import json
import os

def create_frustum_actor(mv_matrix, proj_matrix, color=(0, 1, 0), opacity=0.4):
    """
    MVP 행렬의 역행렬을 이용해 NDC 공간을 World 공간으로 투영하여 Frustum 생성
    """
    # 1. MVP 행렬 계산 및 역행렬
    mvp = proj_matrix @ mv_matrix
    try:
        inv_mvp = np.linalg.inv(mvp)
    except np.linalg.LinAlgError:
        print("❌ 역행렬 계산 실패")
        return None

    # 2. NDC 정육면체 8개 꼭짓점 (OpenGL 표준: -1 to 1)
    ndc_corners = np.array([
        [-1, -1, -1, 1], [1, -1, -1, 1], [1, 1, -1, 1], [-1, 1, -1, 1], # Near Plane
        [-1, -1,  1, 1], [1, -1,  1, 1], [1, 1,  1, 1], [-1, 1,  1, 1]  # Far Plane
    ])

    # 3. World 공간으로 좌표 변환
    points = vtk.vtkPoints()
    for ndc in ndc_corners:
        world_pt = inv_mvp @ ndc
        world_pt /= world_pt[3] # Homogeneous divide
        points.InsertNextPoint(world_pt[:3])

    # 4. 선(Edge) 연결 정의
    lines = vtk.vtkCellArray()
    edges = [
        (0,1), (1,2), (2,3), (3,0), # Near rectangle
        (4,5), (5,6), (6,7), (7,4), # Far rectangle
        (0,4), (1,5), (2,6), (3,7)  # Connecting lines
    ]
    for e in edges:
        line = vtk.vtkLine()
        line.GetPointIds().SetId(0, e[0])
        line.GetPointIds().SetId(1, e[1])
        lines.InsertNextCell(line)

    poly_data = vtk.vtkPolyData()
    poly_data.SetPoints(points)
    poly_data.SetLines(lines)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(poly_data)

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(color)
    actor.GetProperty().SetLineWidth(2)
    actor.GetProperty().SetOpacity(opacity)
    
    return actor

def create_camera_pos_actor(mv_matrix, color=(1, 0, 0)):
    """카메라의 광심(Position)을 작은 구체로 표시"""
    inv_mv = np.linalg.inv(mv_matrix)
    cam_pos = inv_mv[:3, 3] # Translation vector in World Space

    sphere = vtk.vtkSphereSource()
    sphere.SetCenter(cam_pos)
    sphere.SetRadius(0.05)
    sphere.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(sphere.GetOutputPort())
    
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(color)
    return actor

def visualize_cameras(json_path, tmv, tproj):
    # 1. JSON 데이터 로드
    if not os.path.exists(json_path):
        print(f"❌ 파일을 찾을 수 없습니다: {json_path}")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)
    
    cameras = data.get('cameras', [])
    print(f"✅ 총 {len(cameras)}개의 카메라 데이터를 시각화합니다.")

    # 2. VTK 렌더링 환경 설정
    renderer = vtk.vtkRenderer()
    render_win = vtk.vtkRenderWindow()
    render_win.AddRenderer(renderer)
    render_win.SetWindowName("Camera Frustum Debugger (Y-up Space)")
    render_win.SetSize(1000, 800)
    
    interactor = vtk.vtkRenderWindowInteractor()
    interactor.SetRenderWindow(render_win)
    
    # 배경색 (어두운 회색)
    renderer.SetBackground(0.15, 0.15, 0.15)

    # 3. 월드 좌표축 추가 (Red:X, Green:Y, Blue:Z)
    axes = vtk.vtkAxesActor()
    axes.SetTotalLength(1.0, 1.0, 1.0)
    axes.SetAxisLabels(True)
    renderer.AddActor(axes)

    # 4. 참조용 타겟 볼륨(원점 sphere) 추가
    # 볼륨이 정규화된 0.8 반지름 구 안에 있다고 가정
    target = vtk.vtkSphereSource()
    target.SetCenter(0, 0, 0)
    target.SetRadius(0.8)
    target.SetThetaResolution(20)
    target.SetPhiResolution(20)
    target.Update()
    
    t_mapper = vtk.vtkPolyDataMapper()
    t_mapper.SetInputConnection(target.GetOutputPort())
    t_actor = vtk.vtkActor()
    t_actor.SetMapper(t_mapper)
    t_actor.GetProperty().SetRepresentationToWireframe()
    t_actor.GetProperty().SetColor(0.5, 0.5, 0.5)
    t_actor.GetProperty().SetOpacity(0.2)
    renderer.AddActor(t_actor)

    # 5. 카메라 Frustum들 추가
    for cam in cameras:
        mv = np.array(cam['model_view_matrix'])
        proj = np.array(cam['projection_matrix'])
        idx = cam['index']
        
        # 0번 카메라는 강조색(빨강), 나머지는 녹색/파랑 계열
        color = (1, 0, 0) if idx == 0 else (0, 0.8, 0.3)
        
        f_actor = create_frustum_actor(mv, proj, color=color)
        c_actor = create_camera_pos_actor(mv, color=color)
        
        if f_actor: renderer.AddActor(f_actor)
        if c_actor: renderer.AddActor(c_actor)
        break
    color=(0, 0, 1)
    f_actor = create_frustum_actor(tmv, tproj, color=color)
    c_actor = create_camera_pos_actor(tmv, color=color)
    
    if f_actor: renderer.AddActor(f_actor)
    if c_actor: renderer.AddActor(c_actor)
    # 6. 카메라 시점 초기화 및 실행
    renderer.ResetCamera()
    render_win.Render()
    print("💡 마우스 좌클릭: 회전 | 우클릭: 줌 | 휠 클릭: 이동")
    interactor.Start()

def vis_cam_npy(mv, proj):
    # 2. VTK 렌더링 환경 설정
    renderer = vtk.vtkRenderer()
    render_win = vtk.vtkRenderWindow()
    render_win.AddRenderer(renderer)
    render_win.SetWindowName("Camera Frustum Debugger (Y-up Space)")
    render_win.SetSize(1000, 800)
    
    interactor = vtk.vtkRenderWindowInteractor()
    interactor.SetRenderWindow(render_win)
    
    # 배경색 (어두운 회색)
    renderer.SetBackground(0.15, 0.15, 0.15)

    # 3. 월드 좌표축 추가 (Red:X, Green:Y, Blue:Z)
    axes = vtk.vtkAxesActor()
    axes.SetTotalLength(1.0, 1.0, 1.0)
    axes.SetAxisLabels(True)
    renderer.AddActor(axes)

    # 4. 참조용 타겟 볼륨(원점 sphere) 추가
    # 볼륨이 정규화된 0.8 반지름 구 안에 있다고 가정
    target = vtk.vtkSphereSource()
    target.SetCenter(0, 0, 0)
    target.SetRadius(1.0)
    target.SetThetaResolution(20)
    target.SetPhiResolution(20)
    target.Update()
    
    t_mapper = vtk.vtkPolyDataMapper()
    t_mapper.SetInputConnection(target.GetOutputPort())
    t_actor = vtk.vtkActor()
    t_actor.SetMapper(t_mapper)
    t_actor.GetProperty().SetRepresentationToWireframe()
    t_actor.GetProperty().SetColor(0.5, 0.5, 0.5)
    t_actor.GetProperty().SetOpacity(0.2)
    renderer.AddActor(t_actor)

    cnt = 0
    for i in range(mv.shape[0]):
        
        mv_matrix = mv[i]
        proj_matrix = proj[i]
        color = (1, 0, 0) if i == 0 else (0, 0.8, 0.3)
        
        f_actor = create_frustum_actor(mv_matrix, proj_matrix, color=color)
        c_actor = create_camera_pos_actor(mv_matrix, color=color)
        
        if f_actor: renderer.AddActor(f_actor)
        if c_actor: renderer.AddActor(c_actor)
        cnt += 1
    # 6. 카메라 시점 초기화 및 실행
    renderer.ResetCamera()
    render_win.Render()
    print("💡 마우스 좌클릭: 회전 | 우클릭: 줌 | 휠 클릭: 이동")
    interactor.Start()

if __name__ == "__main__":
    # 여기에 생성된 cameras.json 경로를 입력하세요.
    folder= '20260126_183620'
    JSON_PATH = f"./resources/Rendered_Image/{folder}/cameras.json"
    mv_gt = np.load(f'./resources/Rendered_Image/{folder}/mv.npy')
    proj_gt = np.load(f'./resources/Rendered_Image/{folder}/proj.npy')

    # Dmesh++ Renderer GT
    mv_gt = np.load(f'./dmesh_mv.npy')
    proj_gt = np.load(f'./dmesh_proj.npy')
    t_mv = mv_gt[0]
    t_proj = proj_gt[0]
    # visualize_cameras(JSON_PATH, t_mv, t_proj)
    vis_cam_npy(mv_gt, proj_gt)
나의 목표는 
**논문을 재현하는 수준의 “OSVRA형 PET-CT 렌더링 모듈”을 현재의 Python+VTK 기반 단일/멀티 볼륨 렌더러에 붙이는 것**이라면, 가장 중요한 판단은 하나야.

**권장 방향은 “VTK를 버리는 것”이 아니라, VTK는 그대로 두고 OSVRA에 필요한 두 개의 핵심 패스만 별도로 구현하는 하이브리드 구조**로 가는 거야. 이유는 논문 자체가 SOI를 back face로 놓고 CT ray를 따라 누적 opacity가 CT DVR의 opacity limit에 도달할 때 ray를 멈춰 occlusion distance map을 만들고, 그 거리로부터 (D)와 logistic weight를 계산한 뒤 다시 CT를 가중 ray-casting해서 PET SOI와 fuse하는 구조이기 때문이야. 반면 VTK의 기본 composite volume rendering은 front-to-back alpha blending이 기본이라 논문 식을 stock mapper 설정만으로 그대로 재현하기가 까다롭다. 다만 VTK의 GPU ray-cast mapper 자체는 존재하고, OpenGL ray-casting 구현과 shader update 경로도 있으므로 “완전 불가능”은 아니고, **초기 구현은 외부 custom ray marcher**, 최적화 단계에서 **VTK shader/custom mapper**로 옮기는 순서가 가장 안전하다.  ([VTK][1])

아래는 바로 구현 계획서로 쓸 수 있게 정리한 마크다운이다.

---

# OSVRA 기반 PET-CT 렌더링 구현 계획

## 0. 목표 정의

현재 보유한 Python + VTK 기반 렌더러에 다음 기능을 추가한다.

1. PET에서 SOI(slice of interest) plane을 정의한다.
2. 해당 SOI plane을 기준으로 CT 볼륨에 대해 occlusion distance map을 계산한다.
3. distance histogram에서 augmentation depth (D)를 선택한다.
4. (D)를 inflection point로 하는 logistic opacity weight를 생성한다.
5. weight가 반영된 CT augmentation rendering을 생성한다.
6. 이를 PET SOI와 fuse하여 OSVRA 스타일 결과를 만든다.

논문 기준 핵심은 **단순 clipping이 아니라, occlusion distance 기반으로 (D)를 정하고 logistic weight를 사용해 CT 기여도를 부드럽게 감쇠시키는 것**이다. 기본 depth는 histogram의 첫 번째 peak이며, PET SOI와 CT DVR은 기본적으로 50:50 fusion ratio로 합쳐진다. 

---

## 1. 구현 전략 요약

## 권장 전략: Hybrid Architecture

### VTK가 맡을 역할

* 볼륨 로딩
* PET/CT 정합 좌표계 관리
* 카메라/뷰 제어
* SOI plane 선택 UI
* PET slice reslice 및 표시
* 최종 fusion 결과 표시

### 별도 구현할 역할

* **Occlusion distance map 생성 패스**
* **Logistic-weighted CT augmentation ray marching 패스**

이렇게 나누는 이유는, 논문 알고리즘의 핵심이 **SOI 기준 back-to-front 누적과 거리 기반 가중**인데, VTK 기본 composite 모드는 front-to-back가 기본이기 때문이다. 따라서 **VTK는 scene management와 display layer**, **OSVRA는 custom compute/render layer**로 분리하는 게 가장 깔끔하다. VTK의 GPU volume ray-cast mapper는 OpenGL ray-casting 구현이며 multi-input, two-pass, shader update 이벤트 등을 갖고 있어 추후 고급 최적화 경로는 열려 있다. 하지만 초기 재현 단계에서는 stock mapper 위에 억지로 맞추는 것보다, **별도의 ray marcher를 구현한 뒤 결과를 VTK에 다시 올리는 방식**이 훨씬 디버깅하기 쉽다. ([VTK][1])

---

## 2. 현재 VTK 코드에서 수정해야 할 부분

## 2-1. 데이터 계층

### 추가해야 하는 것

* PET/CT를 **같은 physical coordinate system**에서 다루는 래퍼
* `origin`, `spacing`, `direction`, `extent`를 공통 인터페이스로 접근하는 유틸
* `vtkImageData -> numpy` 또는 `vtk_to_numpy` 브리지
* PET와 CT가 서로 다른 해상도면 **하나의 기준 공간으로 resample**하는 전처리

논문도 hardware coaligned PET를 CT dimensions로 resample해서 사용했다. 구현에서도 가장 먼저 **거리 계산이 voxel index가 아니라 물리 좌표(mm)** 기준으로 일관되게 돌아가야 한다. 그렇지 않으면 SOI-plane 거리, histogram bin, logistic weight가 전부 틀어질 수 있다. 

## 2-2. 렌더링 계층

### 기존 VTK volume mapper는 유지

* 일반 CT DVR
* 일반 멀티볼륨 확인용 렌더
* 디버깅용 baseline view

### 새로 추가할 renderer path

* `PETSliceRenderer`
* `OcclusionDepthMapComputer`
* `DepthHistogramAnalyzer`
* `OSVRACustomCTRenderer`
* `FusionRenderer`

즉, 기존 렌더러를 없애지 말고 **OSVRA 전용 렌더 경로를 하나 더 만든다**고 생각하면 된다.

## 2-3. UI/Interaction 계층

### 추가해야 하는 것

* SOI plane index / orientation 선택
* 현재 카메라 방향에서 depth map 재계산 트리거
* histogram 표시
* first/second/last peak 선택 옵션
* fusion ratio 슬라이더
* sample distance / opacity limit / histogram smoothing 조절 옵션

논문에서도 (D)는 slice와 view angle에 따라 다시 계산되며, 기본은 first peak지만 다른 peak도 선택 가능하도록 UI를 제공했다. 

---

## 3. 핵심 아키텍처

## 3-1. 추천 모듈 구조

### `volume_bridge.py`

* VTK image data ↔ NumPy 배열 변환
* world ↔ voxel 좌표 변환
* spacing/origin/direction 처리

### `soi_plane.py`

* SOI plane 생성
* plane local coordinate system 구성
* PET slice resampling

### `occlusion_depth.py`

* SOI plane의 각 sample에서 CT에 대해 ray cast
* opacity limit 도달 시 거리 기록
* occlusion depth map 생성

### `histogram_depth.py`

* depth map에서 background 제거
* histogram 생성
* peak detection
* 기본 (D) 선택

### `logistic_weight.py`

* (A=0.0001), (C=1.0), (B=\ln(A)/D)
* (w(d)=\frac{C}{1 + A e^{Bd}})

### `osvra_ct_render.py`

* CT ray marching
* voxel opacity에 (w(d)) 적용
* CT augmentation image 생성

### `fusion.py`

* PET SOI와 CT augmentation intermixing
* fusion ratio 적용

### `vtk_overlay.py`

* 결과 이미지를 VTK actor/image actor/plane texture로 scene에 표시

---

## 4. 단계별 구현 계획

## Phase 1. SOI plane 정의

### 목표

PET에서 사용자가 선택한 slice를 물리적으로 정의된 plane으로 만든다.

### 해야 할 일

* axial/coronal/sagittal 우선 지원
* plane origin, normal, in-plane axes (u, v) 계산
* PET 볼륨에서 plane reslice 수행
* plane 해상도는 우선 PET 해상도 또는 CT 기준 해상도 중 하나로 고정
* 결과:

  * `pet_soi_image`
  * `plane_origin`
  * `plane_normal`
  * `plane_u`, `plane_v`

### 구현 포인트

* 처음에는 **축정렬 SOI**만 구현하는 것이 좋다.
* 이후 자유 회전 plane으로 확장한다.
* SOI는 결국 ray의 출발면이자 거리 기준면이다.

### 완료 기준

* 원하는 slice를 바꾸면 PET SOI가 정확히 바뀐다.
* plane 위 임의 pixel을 world 좌표로 정확히 복원할 수 있다.

---

## Phase 2. Occlusion distance map 생성

### 목표

SOI plane의 각 유효 sample에 대해, CT 볼륨에서 **SOI에서 viewpoint 방향으로** ray를 쏘고, CT opacity 누적이 CT DVR opacity limit에 도달하는 지점까지의 Euclidean distance를 기록한다.

논문은 PET SOI 각 sample에서 ray를 viewpoint로 던지고, CT voxel opacity를 누적하다가 **CT DVR opacity limit**에 도달하면 ray를 종료하고 그 거리로 occlusion distance를 만든다. background sample은 histogram 전에 제거한다. 

### 구현 포인트

* 입력:

  * CT volume
  * CT transfer function
  * SOI plane
  * current camera/view direction
  * CT opacity limit
* 출력:

  * `depth_map[h, w]`
  * `valid_mask[h, w]`

### 추천 구현 방식

#### 1차: CPU/NumPy/Numba 프로토타입

* plane pixel마다 ray 시작점 계산
* ray direction = camera toward plane 반대 방향 또는 plane→viewpoint 방향으로 통일
* 일정 `sample_step_mm` 간격으로 CT를 trilinear interpolation
* TF로 opacity 변환
* 누적 opacity 계산
* limit 도달 시 distance 저장
* 끝까지 도달 못하면 `NaN` 또는 max distance

#### 왜 CPU로 먼저?

* depth map이 맞는지 시각화하기 가장 쉽다.
* VTK mapper 내부를 건드리지 않아도 된다.
* 논문 식 검증이 먼저다.

### 주의

* 종료 조건은 **opacity = 1**이 아니라 **CT DVR opacity limit 도달**이다.
* 거리 계산은 voxel count가 아니라 **Euclidean distance(mm)** 로 둔다.
* PET background/air 영역은 histogram에서 제외한다.

### 완료 기준

* depth map을 grayscale로 띄웠을 때 구조 경계별로 의미 있는 층이 보인다.
* 시점을 바꾸면 depth map이 같이 바뀐다.
* CT TF를 바꾸면 depth map도 일관되게 변한다.

---

## Phase 3. Depth histogram과 (D) 계산

### 목표

depth map으로 histogram을 만들고 default (D)를 first peak로 선택한다.

논문에서는 occlusion distance histogram의 first peak를 기본 depth로 쓰며, 이것이 SOI와 가장 가까운 관련 구조를 반영하는 경향이 있고 실제 평가에서도 46개 NSCLC 사례 중 42개, 즉 91%에서 first peak가 가장 적절한 depth로 선호되었다. 

### 해야 할 일

* `valid_mask`가 참인 depth만 수집
* histogram bin을 mm 기준으로 생성
* smoothing 적용
* local maxima 탐색
* 기본은 first peak
* 옵션으로 second/last peak 선택 가능하게 설계

### 구현 팁

* 초기에는 `scipy.signal.find_peaks` 수준으로 충분
* 너무 noisy하면

  * histogram smoothing
  * minimum peak prominence
  * minimum peak distance
    를 사용

### 완료 기준

* first peak를 고르면 얕은 구조 위주
* second/third peak를 고르면 더 많은 구조가 들어온다
* view angle 변경 시 (D)가 다시 계산된다

---

## Phase 4. Logistic weight 함수 구현

### 목표

구한 (D)를 inflection point로 하는 inverted logistic curve를 만든다.

논문 식은 (w(d_i)=\frac{C}{1 + A e^{B d_i}}), (B=\ln(A)/D), (A=0.0001), (C=1.0) 이다. 이 weight는 SOI 근처 구조를 상대적으로 더 살리고, 더 먼 구조는 점차 약화시켜 contextual cue를 유지하게 한다. 

### 해야 할 일

* `distance_to_soi_mm -> weight` 함수 구현
* LUT 형태로도 만들기
* plot으로 curve 확인

### 완료 기준

* (d=0) 근처에서 weight가 높고
* (d \approx D)에서 inflection을 가지며
* (d \gg D)에서 weight가 작아진다

---

## Phase 5. Logistic-weighted CT augmentation rendering

### 목표

CT 볼륨을 논문 방식으로 다시 ray marching해서, 각 sample의 opacity contribution에 `w(distance_to_soi)`를 곱해 CT augmentation image를 만든다.

논문은 이 weight를 back-to-front volume ray-casting 누적식에 직접 넣어 CT voxel의 optical contribution을 조절한 뒤, 그 결과를 PET SOI와 fuse한다. 같은 (D)를 쓰더라도 단순 clipping보다 OSVRA가 더 자연스럽게 adjacent structure만 남기는 이유가 여기 있다. 

### 구현 전략

#### 추천: 최종 CT augmentation도 custom pass로 구현

* stock VTK composite mapper로 억지로 맞추지 말고
* SOI plane 기준 ray marching 결과를 **2D image**로 생성
* 그 이미지를 VTK 쪽으로 넘겨서 overlay/fusion

### 입력

* CT volume
* CT TF
* SOI plane
* camera/view direction
* logistic weight LUT
* sample step

### 출력

* `ct_aug_rgba[h, w]`

### 누적 방식

* 논문 식에 맞춰 back-to-front로 구현
* 혹은 수학적으로 동등한 front-to-back 변환을 직접 유도해도 되지만,
  **초기 구현은 논문 식 그대로 back-to-front 순회**가 가장 안전하다

### 핵심 포인트

* 여기서 필요한 distance는 **각 CT sample의 SOI plane까지의 거리**
* depth map은 (D)를 정하기 위한 통계적 입력
* 최종 렌더에서는 각 sample마다 개별 거리 (d_i)가 들어간다

### 완료 기준

* plain clipping보다 silhouette/context가 더 자연스럽게 남는다
* (D)를 낮추면 얕은 구조만 보이고, 높이면 더 많은 구조가 보인다
* 같은 (D)에서 clipping보다 weighted result가 덜 거칠다

---

## Phase 6. PET SOI와 CT augmentation fusion

### 목표

PET SOI image와 `ct_aug_rgba`를 fuse하여 최종 결과를 표시한다.

논문은 voxel-level intermixing으로 PET SOI와 CT DVR을 합치고, 기본값은 50:50 fusion ratio를 사용한다. 

### 해야 할 일

* 기본 fusion ratio 0.5 / 0.5
* UI에서 30:70, 70:30 조절 가능하게
* 출력은

  * plane texture
  * screen-space overlay
    둘 중 하나로 표시

### 추천

* 처음에는 **screen-aligned 2D fusion image**
* 이후 필요하면 **plane-textured actor**로 확장

### 완료 기준

* slice navigation 시 결과가 바로 따라온다
* fusion ratio 변경이 즉시 반영된다

---

## 5. VTK back-to-front 문제를 어떻게 우회할 것인가

## 결론

**OSVRA 핵심 계산을 VTK stock volume renderer 안에서 해결하려고 하지 않는 것**이 가장 중요하다.

VTK의 기본 composite blend는 front-to-back가 기본이다. 그래서 논문처럼 SOI를 back face로 두고 ray를 직접 제어하는 로직을 그대로 구현하려면 stock pipeline만으로는 불편하다. 대신 다음 3단계 전략이 좋다. ([VTK][1])

### 전략 A. 가장 추천: 외부 custom ray marcher + VTK 표시

* SOI / camera / TF / fusion은 VTK에서 관리
* depth map과 weighted CT render는 Python custom 모듈에서 계산
* 결과만 VTK actor로 표시

#### 장점

* 구현이 가장 명확
* 논문 식을 그대로 따라가기 쉬움
* 디버깅이 편함

#### 단점

* 성능 최적화는 직접 해야 함

### 전략 B. 중간 단계: Numba/CuPy/PyTorch로 가속

* CPU 구현이 맞는지 확인 후
* ray batch를 GPU tensor 연산으로 옮김
* texture sampling은 직접 구현 또는 torch grid_sample 활용

#### 장점

* Python 유지
* 점진적 가속 가능

#### 단점

* VTK와 GPU 메모리 공유는 직접 관리 필요

### 전략 C. 최종 고급 단계: vtkOpenGLGPUVolumeRayCastMapper 기반 custom shader/custom mapper

* VTK OpenGL GPU ray caster를 사용
* shader update/custom replacement 경로 활용
* 필요 시 mapper subclass

VTK의 OpenGL GPU ray-cast mapper는 실제로 ray-casting 구현체이며 multiple input, two-pass, shader update event를 가진다. 따라서 장기적으로는 이 경로가 가장 VTK-native하다. 다만 초기 재현 단계에서는 개발 난도가 높다. ([VTK][2])

### 내 추천

* **1차 완성:** 전략 A
* **2차 성능 개선:** 전략 B
* **3차 VTK 완전 통합:** 전략 C

---

## 6. 구현 순서 제안

## 1단계: 논문 재현용 최소 기능

* axial SOI만 지원
* CPU depth map
* CPU histogram + first peak
* CPU weighted CT render
* 2D fusion output

이 단계에서 목표는 **정확도 검증**이다.

## 2단계: 기존 툴과 통합

* 기존 카메라와 slice navigation 연결
* PET/CT TF UI 연결
* VTK scene 안에 결과 표시
* debug panel 추가

  * depth map
  * histogram
  * selected (D)

## 3단계: 성능 최적화

* ray marching을 Numba/CuPy/PyTorch로 이전
* plane sampling 벡터화
* sample distance adaptive tuning
* background mask 최적화

## 4단계: 일반화

* coronal/sagittal 지원
* arbitrary oblique plane 지원
* single-volume OSVRA-like mode 지원
* multi-volume generalization

---

## 7. 디버깅 체크리스트

## 꼭 확인해야 할 것

* PET와 CT가 같은 world 좌표계에 있는가
* SOI plane과 camera direction이 일관적인가
* ray 시작점이 plane 위에 정확히 놓이는가
* CT TF에서 opacity가 예상대로 나오는가
* opacity limit이 PET/CT fusion 설정과 논리적으로 맞는가
* distance가 voxel index가 아니라 mm로 계산되는가
* histogram에서 background가 제거되었는가
* (D)가 slice/view 변경 시 재계산되는가

## 시각화 디버깅 추천

* SOI plane 위 ray start point 찍기
* ray termination point point cloud로 표시
* depth map heatmap 보기
* histogram + selected peak overlay
* logistic curve plot
* clipping vs weighted 결과 나란히 비교

---

## 8. 예상 리스크와 대응

## 리스크 1. 성능이 너무 느림

### 대응

* 먼저 작은 해상도 SOI로 검증
* sample step 키우기
* early termination 적극 사용
* foreground mask로 ray 수 줄이기
* Numba/GPU 이전

## 리스크 2. VTK와 custom 결과의 좌표가 어긋남

### 대응

* 모든 계산을 world coordinate 기준으로 통일
* plane local 좌표계를 명시적으로 저장
* `origin/spacing/direction` 테스트 코드 작성

## 리스크 3. 논문처럼 보이지 않음

### 대응

* plain clipping과 나란히 비교
* same (D)에서 clipping vs weighted 비교
* first/second/last peak 비교
* CT TF를 논문처럼 lungs / bones 강조형으로 조정

논문에서도 same depth clipping보다 OSVRA가 주변 구조를 더 자연스럽게 남기고, 너무 얕거나 깊은 depth는 각각 정보 손실과 과도한 occlusion을 만든다고 보여준다. 

---

## 9. 최종 권장 로드맵

### Week 1

* PET/CT 좌표계 통합
* SOI plane + PET reslice 구현

### Week 2

* CPU depth map 구현
* depth map 시각화
* histogram + peak detection

### Week 3

* logistic weight 구현
* CPU weighted CT augmentation 구현

### Week 4

* PET/CT fusion
* 기존 VTK 툴과 연결
* axial view end-to-end 완성

### Week 5

* coronal/sagittal 확장
* 시점 변화 시 재계산
* 디버그 UI 추가

### Week 6+

* 성능 최적화
* GPU/Numba/CuPy/PyTorch 이전
* 필요 시 VTK shader/custom mapper 검토

---

## 10. 최종 판단

지금 네 상황에서는 **VTK가 back-to-front를 stock path로 바로 지원하지 않는다는 점을 “막힌 문제”로 보지 말고, OSVRA 핵심 패스를 VTK 밖에서 구현할 이유**로 보는 게 맞아.
즉,

* **VTK는 유지**
* **SOI, camera, display, interaction은 VTK**
* **depth map과 weighted CT ray marching만 custom 구현**
* **검증 후에만 VTK 내부 shader/custom mapper로 이동**

이 순서가 가장 현실적이고, 논문 재현에도 가장 가깝다. 논문 자체도 depth map 계산과 histogram 계산을 별도 GPU pass로 구성했고, (D)와 weight가 slice 및 view에 따라 동적으로 다시 계산되는 구조를 취한다. 

원하면 다음 답변에서 내가 이 계획을 바탕으로
**“구현 TODO 리스트 + 파일 구조 + 클래스 설계안”** 형태로 더 실전적으로 풀어줄게.

[1]: https://vtk.org/doc/nightly/html/classvtkVolumeMapper.html "VTK: vtkVolumeMapper Class Reference"
[2]: https://vtk.org/doc/nightly/html/classvtkOpenGLGPUVolumeRayCastMapper.html "VTK: vtkOpenGLGPUVolumeRayCastMapper Class Reference"
# OSVRA PET-CT 렌더링 구현 계획서

> 기반: `code_plan.md` (논문 재현 전략) + 현재 베이스라인 코드 분석
> 작성일: 2026-03-19

---

## 0. 현재 코드베이스 요약

### 기존 아키텍처 (유지)

```
main.py → VolumeRenderingMainWindow (src/main_window.py)
  ├─ FilePanel        : CT/PET 파일 로드 → numpy + spacing
  ├─ TFPanel          : CT/PET Transfer Function 편집 (노드 기반 스플라인)
  ├─ RenderingPanel   : VTKVolumeRenderer 래퍼 (vtkMultiVolume, port 0=CT, port 1=PET)
  └─ SliceViewerPanel : Axial/Coronal/Sagittal 2D 슬라이스 뷰
```

### 활용 가능한 기존 인프라

| 기존 요소 | 위치 | OSVRA에서의 용도 |
|-----------|------|----------------|
| `VTKVolumeRenderer.get_camera()` | `renderer_widget.py` | 카메라 방향 → ray direction 계산 |
| `VTKVolumeRenderer._numpy_to_vtk_imagedata()` | `renderer_widget.py` | fusion 결과를 VTK scene에 표시 |
| `VTKVolumeRenderer._create_vtk_tf_from_array()` | `renderer_widget.py` | TF 노드 → 256 LUT 변환 (opacity 계산에 재사용) |
| `SliceViewerPanel._AXIS_MAP` | `slice_panel.py` | SOI plane axis 매핑 |
| `SliceViewerPanel.slice_changed` signal | `slice_panel.py` | SOI 변경 트리거 |
| `VolumeClippingManager.planes` | `clipping_manager.py` | 기존 클리핑과 OSVRA 비교 디버깅 |
| `FilePanel.voxel_spacing` / `pet_voxel_spacing` | `file_panel.py` | 물리 좌표(mm) 거리 계산 |
| TF 노드 형식 `[pos, r, g, b, alpha]` | 전체 | CT opacity 계산에 직접 사용 |

---

## 1. 새로 추가할 파일 구조

```
src/
├── osvra/                              ← 새 패키지
│   ├── __init__.py
│   ├── volume_bridge.py                ← Phase 0: VTK↔NumPy 좌표계 브리지
│   ├── soi_plane.py                    ← Phase 1: SOI plane 정의 & PET reslice
│   ├── occlusion_depth.py              ← Phase 2: Occlusion distance map 생성
│   ├── histogram_depth.py              ← Phase 3: Depth histogram & peak detection
│   ├── logistic_weight.py              ← Phase 4: Logistic weight 함수
│   ├── osvra_ct_renderer.py            ← Phase 5: Weighted CT augmentation ray marching
│   └── fusion.py                       ← Phase 6: PET SOI + CT augmentation fusion
│
├── gui/
│   ├── panel/
│   │   └── osvra_panel.py              ← Phase 7: OSVRA 전용 UI 패널
│   └── widget/
│       └── osvra_viewer_widget.py      ← Phase 7: Fusion 결과 표시 위젯
│
└── main_window.py                      ← 수정: OSVRA signal 연결 추가
```

---

## 2. Phase별 구현 상세

---

### Phase 0: Volume Bridge (데이터 계층 통합)

**파일:** `src/osvra/volume_bridge.py`

**목적:** PET/CT를 같은 physical coordinate system에서 다루는 유틸리티

**현재 상태:**
- `renderer_widget.py:_numpy_to_vtk_imagedata()`에 numpy→VTK 변환이 있지만 origin이 항상 (0,0,0)
- spacing은 `FilePanel.voxel_spacing`으로 접근 가능
- PET/CT 해상도가 다를 수 있음 (현재 코드는 각각 독립 로드)

**구현 내용:**

```python
class VolumeBridge:
    """PET/CT 좌표계 통합 유틸리티"""

    @staticmethod
    def voxel_to_world(voxel_ijk, origin, spacing, direction=None):
        """(i,j,k) voxel index → (x,y,z) world coordinate (mm)"""
        # world = origin + direction @ (voxel * spacing)
        # direction 미지정 시 identity (축정렬 가정)

    @staticmethod
    def world_to_voxel(world_xyz, origin, spacing, direction=None):
        """(x,y,z) world coordinate → (i,j,k) voxel index (float)"""

    @staticmethod
    def resample_to_reference(source_vol, source_spacing, ref_shape, ref_spacing, order=1):
        """source 볼륨을 reference 격자로 리샘플링"""
        # scipy.ndimage.zoom 또는 affine_transform 사용
        # PET → CT 해상도 맞춤에 사용

    @staticmethod
    def trilinear_interpolate(volume, positions_voxel):
        """연속 voxel 좌표에서 trilinear interpolation"""
        # scipy.ndimage.map_coordinates(volume, positions.T, order=1)
        # ray marching에서 사용

    @staticmethod
    def get_view_direction(camera):
        """vtkCamera → 정규화된 view direction 벡터"""
        pos = np.array(camera.GetPosition())
        focal = np.array(camera.GetFocalPoint())
        direction = focal - pos
        return direction / np.linalg.norm(direction)
```

**의존성:** `numpy`, `scipy.ndimage`
**완료 기준:** 단위 테스트 — voxel↔world 왕복 변환 정확성

---

### Phase 1: SOI Plane 정의

**파일:** `src/osvra/soi_plane.py`

**목적:** PET에서 사용자가 선택한 slice를 물리적 plane으로 정의하고 reslice 수행

**현재 활용 가능 코드:**
- `SliceViewerPanel._AXIS_MAP`: `{"Axial": 2, "Coronal": 1, "Sagittal": 0}`
- `SliceViewerPanel.current_axis`, `current_index` — 현재 선택된 축/인덱스
- `SliceViewerPanel.slice_changed` signal — `(view_axis: str, index: int)`

**구현 내용:**

```python
@dataclass
class SOIPlane:
    """Slice of Interest 물리적 정의"""
    origin: np.ndarray       # (3,) plane 중심점 world 좌표 (mm)
    normal: np.ndarray       # (3,) plane 법선 벡터 (정규화)
    u_axis: np.ndarray       # (3,) plane 내 수평 축
    v_axis: np.ndarray       # (3,) plane 내 수직 축
    resolution: tuple        # (width, height) pixel 수
    pixel_spacing: tuple     # (du, dv) mm per pixel
    pet_slice: np.ndarray    # (height, width) PET SOI 이미지
    axis_name: str           # "Axial" | "Coronal" | "Sagittal"
    slice_index: int         # 볼륨 내 슬라이스 인덱스


class SOIPlaneBuilder:
    """SOI plane 생성기"""

    @staticmethod
    def build_axis_aligned(
        axis_name: str,          # "Axial" | "Coronal" | "Sagittal"
        slice_index: int,
        pet_volume: np.ndarray,  # (X, Y, Z) shape
        pet_spacing: tuple,      # (sx, sy, sz) mm
        ct_volume: np.ndarray,   # 해상도 기준용
        ct_spacing: tuple,
    ) -> SOIPlane:
        """축정렬 SOI plane 생성

        Axial (Z축):
          origin = (cx, cy, slice_index * sz)
          normal = (0, 0, 1)
          u = (1, 0, 0), v = (0, 1, 0)
          resolution = (X, Y), pixel_spacing = (sx, sy)
          pet_slice = pet_volume[:, :, slice_index].T

        Coronal (Y축):
          origin = (cx, slice_index * sy, cz)
          normal = (0, 1, 0)
          u = (1, 0, 0), v = (0, 0, 1)
          resolution = (X, Z), pixel_spacing = (sx, sz)
          pet_slice = pet_volume[:, slice_index, :].T

        Sagittal (X축):
          origin = (slice_index * sx, cy, cz)
          normal = (1, 0, 0)
          u = (0, 1, 0), v = (0, 0, 1)
          resolution = (Y, Z), pixel_spacing = (sy, sz)
          pet_slice = pet_volume[slice_index, :, :]
        """
        pass

    def get_ray_start_points(self, soi: SOIPlane) -> np.ndarray:
        """SOI plane 각 픽셀의 world 좌표 반환

        Returns:
            (H, W, 3) array of world coordinates
        """
        # 각 (i,j)에 대해:
        # point = origin + (i - W/2) * pixel_spacing[0] * u + (j - H/2) * pixel_spacing[1] * v
        pass
```

**SliceViewerPanel과의 연동 방식:**

현재 `SliceViewerPanel`에서 축/인덱스가 바뀌면 `slice_changed` signal이 emit됨.
이 signal을 MainWindow에서 받아 OSVRA 파이프라인을 트리거하면 됨.

```python
# main_window.py에 추가할 연결:
self.slice_viewer.slice_changed.connect(self._on_osvra_soi_changed)
```

**완료 기준:**
- SOI plane의 각 픽셀 좌표를 3D scene에 점으로 표시했을 때 plane 위에 정확히 위치
- PET slice가 `SliceViewerPanel`의 표시와 일치

---

### Phase 2: Occlusion Distance Map 생성

**파일:** `src/osvra/occlusion_depth.py`

**목적:** SOI 각 샘플에서 viewpoint 방향으로 CT ray를 쏘고, opacity limit에 도달하는 거리(mm) 기록

**현재 활용 가능 코드:**
- `VTKVolumeRenderer._create_vtk_tf_from_array()` — TF 노드 → 256 LUT 변환 로직
  - 이 로직을 참조하여 numpy 기반 TF LUT 생성
- `VTKVolumeRenderer.get_camera()` → view direction 계산

**구현 내용:**

```python
class OcclusionDepthComputer:
    """SOI에서 viewpoint 방향 CT ray marching으로 occlusion distance map 생성"""

    def __init__(
        self,
        ct_volume: np.ndarray,      # (X, Y, Z) normalized [0,1]
        ct_spacing: tuple,           # (sx, sy, sz) mm
        ct_tf_nodes: list,           # [[pos, r, g, b, alpha], ...]
        opacity_limit: float = 0.95, # CT DVR opacity limit
        sample_step_mm: float = 1.0, # ray marching step (mm)
        max_distance_mm: float = 500.0,
    ):
        self.ct_volume = ct_volume
        self.ct_spacing = np.array(ct_spacing)
        self.opacity_lut = self._build_opacity_lut(ct_tf_nodes)  # 256-entry
        self.opacity_limit = opacity_limit
        self.sample_step = sample_step_mm
        self.max_distance = max_distance_mm

    def _build_opacity_lut(self, tf_nodes) -> np.ndarray:
        """TF 노드 → 256-entry opacity LUT

        기존 renderer_widget.py의 _create_vtk_tf_from_array() 로직을
        numpy 버전으로 재구현.
        tf_nodes: [[pos_0_1, r, g, b, alpha_0_1], ...]
        returns: np.ndarray shape (256,) — position 기반 alpha 보간
        """
        lut = np.zeros(256)
        positions = [n[0] for n in tf_nodes]
        alphas = [n[4] for n in tf_nodes]
        for i in range(256):
            x = i / 255.0
            # 인접 노드 사이 linear interpolation
            lut[i] = np.interp(x, positions, alphas)
        return lut

    def compute(
        self,
        soi_plane: SOIPlane,
        view_direction: np.ndarray,   # (3,) 정규화된 카메라→focal 방향
    ) -> tuple:
        """
        Returns:
            depth_map: np.ndarray (H, W) — Euclidean distance (mm), NaN if no hit
            valid_mask: np.ndarray (H, W) — bool, True if opacity limit reached
        """
        H, W = soi_plane.resolution
        ray_starts = soi_plane.get_ray_start_points()  # (H, W, 3) world coords

        # ray direction: SOI에서 viewpoint 방향 (= -view_direction)
        # 논문: SOI를 back face로 놓고 viewpoint 쪽으로 ray를 쏨
        ray_dir = -view_direction  # SOI → viewpoint
        ray_dir = ray_dir / np.linalg.norm(ray_dir)

        depth_map = np.full((H, W), np.nan, dtype=np.float32)
        valid_mask = np.zeros((H, W), dtype=bool)

        # ---- 핵심 루프 (1차: 순수 NumPy, 2차: Numba @njit) ----
        step_vec = ray_dir * self.sample_step  # (3,) mm
        max_steps = int(self.max_distance / self.sample_step)

        for j in range(H):
            for i in range(W):
                pos = ray_starts[j, i].copy()     # (3,) world mm
                accumulated_opacity = 0.0

                for step in range(max_steps):
                    # world → voxel
                    voxel = pos / self.ct_spacing

                    # bounds check
                    if not self._in_bounds(voxel):
                        pos += step_vec
                        continue

                    # trilinear interpolation
                    intensity = trilinear(self.ct_volume, voxel)

                    # TF lookup
                    lut_idx = int(np.clip(intensity * 255, 0, 255))
                    alpha = self.opacity_lut[lut_idx]

                    # front-to-back opacity 누적
                    accumulated_opacity += (1.0 - accumulated_opacity) * alpha

                    if accumulated_opacity >= self.opacity_limit:
                        distance = step * self.sample_step
                        depth_map[j, i] = distance
                        valid_mask[j, i] = True
                        break

                    pos += step_vec

        return depth_map, valid_mask
```

**성능 고려사항:**
- 1차 구현: 순수 Python/NumPy (정확도 검증용)
- `@numba.njit` 데코레이터 적용으로 즉시 10-50x 가속 가능
- 이후 PyTorch `grid_sample`로 GPU 이전

**완료 기준:**
- depth map을 grayscale heatmap으로 표시했을 때 뼈/피부 경계에서 층이 보임
- 시점 변경 시 depth map이 일관되게 변화
- CT TF 변경 시 depth map이 반영

---

### Phase 3: Depth Histogram & Peak Detection

**파일:** `src/osvra/histogram_depth.py`

**목적:** depth map에서 histogram 생성, peak detection으로 기본 D 선택

**구현 내용:**

```python
class DepthHistogramAnalyzer:
    """Occlusion distance histogram 분석 및 D 선택"""

    def __init__(
        self,
        bin_width_mm: float = 1.0,
        smoothing_sigma: float = 2.0,
        min_peak_prominence: float = 0.01,
        min_peak_distance_bins: int = 5,
    ):
        self.bin_width = bin_width_mm
        self.smoothing_sigma = smoothing_sigma
        self.min_peak_prominence = min_peak_prominence
        self.min_peak_distance = min_peak_distance_bins

    def analyze(
        self,
        depth_map: np.ndarray,
        valid_mask: np.ndarray,
    ) -> dict:
        """
        Returns:
            {
                'histogram': np.ndarray,      # bin counts
                'bin_edges': np.ndarray,       # bin edges (mm)
                'bin_centers': np.ndarray,     # bin centers (mm)
                'smoothed': np.ndarray,        # smoothed histogram
                'peaks': list[int],            # peak bin indices
                'peak_distances': list[float], # peak distances (mm)
                'default_D': float,            # first peak distance (mm)
            }
        """
        # 1. valid depth만 수집
        valid_depths = depth_map[valid_mask]

        # 2. histogram 생성
        max_depth = np.nanmax(valid_depths)
        bins = np.arange(0, max_depth + self.bin_width, self.bin_width)
        hist, bin_edges = np.histogram(valid_depths, bins=bins)

        # 3. Gaussian smoothing
        from scipy.ndimage import gaussian_filter1d
        smoothed = gaussian_filter1d(hist.astype(float), sigma=self.smoothing_sigma)

        # 4. peak detection
        from scipy.signal import find_peaks
        peaks, properties = find_peaks(
            smoothed,
            prominence=self.min_peak_prominence * smoothed.max(),
            distance=self.min_peak_distance,
        )

        # 5. bin center 변환
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
        peak_distances = bin_centers[peaks].tolist()

        # 6. default D = first peak
        default_D = peak_distances[0] if peak_distances else max_depth / 2.0

        return {
            'histogram': hist,
            'bin_edges': bin_edges,
            'bin_centers': bin_centers,
            'smoothed': smoothed,
            'peaks': peaks.tolist(),
            'peak_distances': peak_distances,
            'default_D': default_D,
        }
```

**UI 연동 (Phase 7에서 구현):**
- histogram을 matplotlib 또는 pyqtgraph로 표시
- peak 위치를 marker로 표시
- 사용자가 first/second/last peak 선택 가능

**완료 기준:**
- first peak → 얕은 구조 위주, second peak → 더 많은 구조 포함
- view angle 변경 시 D 재계산

---

### Phase 4: Logistic Weight 함수

**파일:** `src/osvra/logistic_weight.py`

**목적:** D를 inflection point로 하는 inverted logistic curve 생성

**구현 내용:**

```python
class LogisticWeightFunction:
    """논문 식: w(d) = C / (1 + A * exp(B * d))

    Parameters (논문 기본값):
        A = 0.0001
        C = 1.0
        B = ln(A) / D

    특성:
        - d ≈ 0 에서 w ≈ C (≈1.0) : SOI 근처 구조 보존
        - d = D 에서 inflection point
        - d >> D 에서 w → 0 : 먼 구조 감쇠
    """

    def __init__(self, D: float, A: float = 0.0001, C: float = 1.0):
        self.D = D
        self.A = A
        self.C = C
        self.B = np.log(A) / D if D > 0 else 0.0

    def __call__(self, distances: np.ndarray) -> np.ndarray:
        """distance (mm) → weight [0, C]"""
        return self.C / (1.0 + self.A * np.exp(self.B * distances))

    def as_lut(self, max_distance: float, num_entries: int = 1024) -> tuple:
        """사전 계산된 LUT 반환

        Returns:
            (distances, weights) — 둘 다 np.ndarray shape (num_entries,)
        """
        distances = np.linspace(0, max_distance, num_entries)
        weights = self(distances)
        return distances, weights
```

**완료 기준:**
- curve plot에서 d=0 → weight≈1.0, d=D → inflection, d>>D → weight≈0 확인

---

### Phase 5: Weighted CT Augmentation Rendering

**파일:** `src/osvra/osvra_ct_renderer.py`

**목적:** logistic weight를 적용한 CT augmentation image 생성

**현재 활용 가능 코드:**
- Phase 2의 ray marching 구조 재사용
- TF LUT 빌드 로직 재사용

**구현 내용:**

```python
class OSVRACTRenderer:
    """Logistic-weighted CT augmentation ray marching"""

    def __init__(
        self,
        ct_volume: np.ndarray,
        ct_spacing: tuple,
        ct_tf_nodes: list,
        sample_step_mm: float = 1.0,
        max_distance_mm: float = 500.0,
    ):
        self.ct_volume = ct_volume
        self.ct_spacing = np.array(ct_spacing)
        self.opacity_lut = self._build_opacity_lut(ct_tf_nodes)
        self.color_lut = self._build_color_lut(ct_tf_nodes)  # (256, 3) RGB
        self.sample_step = sample_step_mm
        self.max_distance = max_distance_mm

    def render(
        self,
        soi_plane: SOIPlane,
        view_direction: np.ndarray,
        weight_func: LogisticWeightFunction,
    ) -> np.ndarray:
        """
        논문 방식: back-to-front ray marching with logistic weight

        각 sample의 SOI까지의 거리 d_i를 계산하고,
        해당 voxel의 opacity에 w(d_i)를 곱하여 CT augmentation image 생성

        Returns:
            ct_aug_rgba: np.ndarray (H, W, 4) — RGBA float [0,1]
        """
        H, W = soi_plane.resolution
        ray_starts = soi_plane.get_ray_start_points()  # (H, W, 3)

        ray_dir = -view_direction
        ray_dir = ray_dir / np.linalg.norm(ray_dir)
        step_vec = ray_dir * self.sample_step
        max_steps = int(self.max_distance / self.sample_step)

        ct_aug = np.zeros((H, W, 4), dtype=np.float32)

        for j in range(H):
            for i in range(W):
                # --- Back-to-front: 먼저 모든 sample 수집, 역순 누적 ---
                samples = []
                pos = ray_starts[j, i].copy()

                for step in range(max_steps):
                    voxel = pos / self.ct_spacing
                    if self._in_bounds(voxel):
                        intensity = trilinear(self.ct_volume, voxel)
                        distance_to_soi = step * self.sample_step
                        samples.append((intensity, distance_to_soi))
                    pos += step_vec

                # Back-to-front 누적 (논문 식 그대로)
                r_acc, g_acc, b_acc, a_acc = 0.0, 0.0, 0.0, 0.0
                for intensity, d in reversed(samples):
                    lut_idx = int(np.clip(intensity * 255, 0, 255))
                    alpha = self.opacity_lut[lut_idx]
                    color = self.color_lut[lut_idx]  # (r, g, b)

                    # logistic weight 적용
                    w = weight_func(np.array([d]))[0]
                    weighted_alpha = alpha * w

                    # back-to-front compositing
                    r_acc = color[0] * weighted_alpha + r_acc * (1 - weighted_alpha)
                    g_acc = color[1] * weighted_alpha + g_acc * (1 - weighted_alpha)
                    b_acc = color[2] * weighted_alpha + b_acc * (1 - weighted_alpha)
                    a_acc = weighted_alpha + a_acc * (1 - weighted_alpha)

                ct_aug[j, i] = [r_acc, g_acc, b_acc, a_acc]

        return ct_aug
```

**성능 참고:**
- Phase 2와 동일: 1차 CPU, 2차 Numba, 3차 PyTorch
- 핵심 차이: Phase 2는 거리만 기록, Phase 5는 색상까지 누적

**완료 기준:**
- plain clipping보다 silhouette가 더 자연스러움
- D를 낮추면 얕은 구조만, 높이면 더 많은 구조
- 같은 D에서 clipping보다 덜 거친 결과

---

### Phase 6: PET SOI + CT Augmentation Fusion

**파일:** `src/osvra/fusion.py`

**구현 내용:**

```python
class FusionRenderer:
    """PET SOI와 CT augmentation의 pixel-level fusion"""

    @staticmethod
    def fuse(
        pet_soi_image: np.ndarray,     # (H, W) normalized [0,1]
        ct_aug_rgba: np.ndarray,       # (H, W, 4) RGBA float [0,1]
        pet_colormap: str = 'hot',     # PET 컬러맵
        fusion_ratio: float = 0.5,     # PET 비율 (0.0=CT only, 1.0=PET only)
    ) -> np.ndarray:
        """
        Returns:
            fused_rgba: np.ndarray (H, W, 4) RGBA float [0,1]
        """
        # PET → RGBA (hot colormap 적용)
        import matplotlib.cm as cm
        pet_rgba = cm.get_cmap(pet_colormap)(pet_soi_image)  # (H, W, 4)

        # Fusion: pixel-level intermixing
        fused = fusion_ratio * pet_rgba + (1.0 - fusion_ratio) * ct_aug_rgba
        fused = np.clip(fused, 0, 1)

        return fused.astype(np.float32)
```

**완료 기준:**
- fusion ratio 슬라이더 조절 시 즉시 반영
- PET 핫스팟이 CT 해부학적 맥락 위에 자연스럽게 표시

---

### Phase 7: UI 통합 & Signal 연결

**파일:** `src/gui/panel/osvra_panel.py`

**목적:** OSVRA 파라미터 제어 및 결과 표시 UI

**패널 구성:**

```
┌─ OSVRA Panel ──────────────────────┐
│                                     │
│  [☑ OSVRA 활성화]                   │
│                                     │
│  ── SOI 설정 ──                     │
│  축: [Axial ▾]  슬라이스: [128 ◄►]  │
│                                     │
│  ── 파라미터 ──                     │
│  Opacity Limit: [0.95 ◄►]          │
│  Sample Step:   [1.0 mm ◄►]        │
│  Smoothing:     [2.0 ◄►]           │
│                                     │
│  ── Depth (D) 선택 ──              │
│  ┌─────────────────────────┐       │
│  │  ▓▓▓▓░▓▓░░░░░░░░░░░░░  │       │ ← histogram
│  │     ↑   ↑               │       │ ← peak markers
│  └─────────────────────────┘       │
│  Peak: [First ▾]  D = 45.2 mm     │
│                                     │
│  ── Fusion ──                      │
│  Ratio: PET [====|====] CT         │
│          0.5                        │
│                                     │
│  [렌더링 실행]  [비교 보기]          │
│                                     │
│  ── 결과 ──                        │
│  ┌─────────────────────────┐       │
│  │                         │       │
│  │    Fusion 결과 이미지     │       │
│  │                         │       │
│  └─────────────────────────┘       │
└─────────────────────────────────────┘
```

**Signal 정의:**

```python
class OSVRAPanel(QWidget):
    # Signals
    osvra_enabled_changed = pyqtSignal(bool)
    soi_changed = pyqtSignal(str, int)           # (axis_name, slice_index)
    opacity_limit_changed = pyqtSignal(float)
    sample_step_changed = pyqtSignal(float)
    peak_selection_changed = pyqtSignal(int)      # peak index (0=first, 1=second, ...)
    fusion_ratio_changed = pyqtSignal(float)
    render_requested = pyqtSignal()
```

**MainWindow 연결 추가:**

```python
# src/main_window.py에 추가할 코드:

def _setup_osvra(self):
    """OSVRA 모듈 초기화 및 signal 연결"""
    from src.gui.panel.osvra_panel import OSVRAPanel

    self.osvra_panel = OSVRAPanel()
    # 레이아웃: TFPanel 아래 또는 별도 탭으로 추가

    # Signal 연결
    self.osvra_panel.render_requested.connect(self._run_osvra_pipeline)
    self.osvra_panel.soi_changed.connect(self._on_osvra_soi_changed)
    self.osvra_panel.fusion_ratio_changed.connect(self._on_fusion_ratio_changed)

def _run_osvra_pipeline(self):
    """OSVRA 전체 파이프라인 실행"""
    # 1. SOI plane 생성
    soi = SOIPlaneBuilder.build_axis_aligned(
        axis_name=self.osvra_panel.current_axis,
        slice_index=self.osvra_panel.current_slice,
        pet_volume=self.pet_volume_data,
        pet_spacing=self.pet_voxel_spacing,
        ct_volume=self.volume_data,
        ct_spacing=self.voxel_spacing,
    )

    # 2. 카메라 방향 가져오기
    camera = self.rendering_panel.vtk_renderer.get_camera()
    view_dir = VolumeBridge.get_view_direction(camera)

    # 3. CT TF 노드 가져오기
    ct_tf_nodes = self.tf_panel.ct_tf_widget.get_nodes()

    # 4. Occlusion depth map 계산
    depth_computer = OcclusionDepthComputer(
        ct_volume=self.volume_data,
        ct_spacing=self.voxel_spacing,
        ct_tf_nodes=ct_tf_nodes,
        opacity_limit=self.osvra_panel.opacity_limit,
    )
    depth_map, valid_mask = depth_computer.compute(soi, view_dir)

    # 5. Histogram 분석 & D 선택
    analyzer = DepthHistogramAnalyzer()
    hist_result = analyzer.analyze(depth_map, valid_mask)
    D = hist_result['peak_distances'][self.osvra_panel.selected_peak_index]

    # 6. Logistic weight 생성
    weight_func = LogisticWeightFunction(D=D)

    # 7. Weighted CT augmentation
    ct_renderer = OSVRACTRenderer(
        ct_volume=self.volume_data,
        ct_spacing=self.voxel_spacing,
        ct_tf_nodes=ct_tf_nodes,
    )
    ct_aug = ct_renderer.render(soi, view_dir, weight_func)

    # 8. Fusion
    fused = FusionRenderer.fuse(
        pet_soi_image=soi.pet_slice,
        ct_aug_rgba=ct_aug,
        fusion_ratio=self.osvra_panel.fusion_ratio,
    )

    # 9. UI 업데이트
    self.osvra_panel.display_result(fused)
    self.osvra_panel.display_histogram(hist_result)
```

---

## 3. 구현 순서 & 마일스톤

| 주차 | Phase | 핵심 산출물 | 검증 방법 |
|------|-------|-----------|----------|
| **1주** | Phase 0 + 1 | `volume_bridge.py`, `soi_plane.py` | SOI 좌표를 3D scene에 점으로 표시 |
| **2주** | Phase 2 | `occlusion_depth.py` (CPU) | depth map heatmap 시각화 |
| **3주** | Phase 3 + 4 | `histogram_depth.py`, `logistic_weight.py` | histogram plot + logistic curve plot |
| **4주** | Phase 5 | `osvra_ct_renderer.py` (CPU) | clipping vs weighted 나란히 비교 |
| **5주** | Phase 6 + 7 | `fusion.py`, `osvra_panel.py` | End-to-end axial view 완성 |
| **6주** | 통합 | MainWindow 연결, coronal/sagittal 확장 | 모든 축 + 시점 변경 동작 |
| **7주+** | 최적화 | Numba/PyTorch 가속 | 인터랙티브 속도 (< 1초) |

---

## 4. 기존 코드 수정 목록

### 수정이 필요한 파일 (최소 변경)

| 파일 | 변경 내용 |
|------|----------|
| `src/main_window.py` | OSVRA panel 추가, signal 연결, `_run_osvra_pipeline()` 슬롯 |
| `src/gui/panel/tf_panel.py` | CT TF 노드 접근 메서드 공개 (이미 `get_nodes()` 존재) |
| `src/gui/widget/renderer_widget.py` | `get_camera()` 이미 존재 — 변경 불필요 |
| `src/gui/panel/slice_panel.py` | `slice_changed` signal 이미 존재 — 변경 불필요 |

### 수정하지 않을 파일

- `src/gui/data/*` — 기존 로더/프로세서 그대로 유지
- `src/gui/rendering/*` — 기존 클리핑/조명/카메라 그대로 유지
- `src/core/tf_optimizer.py` — 독립 모듈, 변경 불필요

---

## 5. 의존성 추가

```
# requirements.txt에 추가 필요:
scipy          # 이미 존재 — histogram, peak detection, interpolation
numba          # Phase 2+ 가속 시 추가 (선택)
matplotlib     # PET colormap & debug 시각화 (선택, pyqtgraph 대안)
```

---

## 6. 리스크 & 대응 (코드 기반 구체화)

### 리스크 1: PET/CT 좌표 불일치

**현재 상태:** `renderer_widget.py`에서 origin이 항상 `(0,0,0)`으로 설정됨. PET/CT 해상도가 다르면 voxel 좌표가 어긋남.

**대응:** `volume_bridge.py`에서 spacing 기반 world 좌표 변환을 반드시 사용. resample 함수로 PET→CT 격자 정렬.

### 리스크 2: CPU ray marching 성능

**예상:** 512x512 SOI, 500mm max distance, 1mm step → 약 1.3억 sample → 순수 Python으로 수십 분

**대응:**
1. 1차: 작은 해상도 (128x128)로 검증
2. 2차: `@numba.njit` 적용 (10-50x 가속 → 수십 초)
3. 3차: PyTorch `grid_sample` GPU 이전 (< 1초 목표)

### 리스크 3: TF LUT 재구현 불일치

**현재 상태:** `renderer_widget.py`의 `_create_vtk_tf_from_array()`는 VTK 함수 사용.

**대응:** `_build_opacity_lut()`에서 동일한 linear interpolation 로직을 numpy로 구현하고, VTK 결과와 비교 검증.

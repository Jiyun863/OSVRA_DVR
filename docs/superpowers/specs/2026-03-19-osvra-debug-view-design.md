# OSVRA Debug View — Design Spec

**Date:** 2026-03-19
**Status:** Approved

---

## Overview

SOI plane이 올바르게 지정되었는지 검증하기 위해, OSVRA 파이프라인의 5개 중간 결과를 팝업 다이얼로그로 표시하고 PNG 파일로 자동 저장하는 기능을 추가한다.

---

## Goals

- Render 완료 시 중간 결과(pet_slice, depth_map, ct_aug, pet_rgba, fused) 5개를 자동으로 PNG 저장
- "Debug View" 버튼으로 팝업 다이얼로그에서 즉시 확인
- 기존 파이프라인 동작 변경 없음 (캐싱/저장은 부가 동작)

---

## Architecture

### New File

**`src/gui/dialogs/osvra_debug_dialog.py`**
`QDialog` subclass. `_osvra_debug_data` dict를 받아 5개 이미지를 2행 레이아웃으로 표시.

### Modified Files

| 파일 | 변경 내용 |
|------|-----------|
| `src/main_window.py` | 캐싱 코드 추가, 자동 저장 로직, debug_btn 활성화, 버튼 클릭 핸들러 |
| `src/gui/panel/osvra_panel.py` | "Debug View" 버튼 추가 (초기 비활성), `set_debug_available()` 공개 메서드 추가 |

---

## Data Flow

### 캐싱 (main_window.py — `_run_osvra_pipeline()`, Fusion 완료 후)

기존 `self._osvra_last_ct_aug` / `self._osvra_last_pet_rgba` 캐시 변수는 **그대로 유지**하고,
`_osvra_debug_data`는 이에 더해 추가로 저장한다.

```python
# 기존 캐시 (변경 없음)
self._osvra_last_ct_aug = ct_aug
self._osvra_last_pet_rgba = pet_rgba

# 신규 debug 캐시 (추가)
self._osvra_debug_data = {
    'pet_slice': soi.pet_slice,     # (H,W) float32 [0,1] grayscale
    'depth_map': depth_map,         # (H,W) float32 mm, NaN = no hit
    'ct_aug': ct_aug,               # (H,W,4) float32 RGBA [0,1]
    'pet_rgba': pet_rgba,           # (H,W,4) float32 RGBA [0,1]
    'fused': fused,                 # (H,W,4) float32 RGBA [0,1]
    'axis_name': soi.axis_name,
    'slice_index': soi.slice_index,
    'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
}
self.osvra_panel.set_debug_available(True)
```

### 자동 저장

저장 경로: `resources/OSVRA_debug/<timestamp>_<axis>_<slice>/`
예: `resources/OSVRA_debug/20260319_142305_Axial_45/`

`os.makedirs(save_dir, exist_ok=True)` 로 디렉토리 생성. 경로는 프로젝트 루트 기준 상대경로 (기존 `screenshot_manager.py` 패턴과 동일).

| 파일명 | 소스 | 변환 |
|--------|------|------|
| `1_pet_slice.png` | `pet_slice` (H,W) float32 | grayscale→RGB uint8 |
| `2_depth_map.png` | `depth_map` (H,W) float32 | NaN→0, normalize→grayscale uint8 |
| `3_ct_aug.png` | `ct_aug` (H,W,4) float32 | RGBA→RGB uint8 |
| `4_pet_rgba.png` | `pet_rgba` (H,W,4) float32 | RGBA→RGB uint8 |
| `5_fused.png` | `fused` (H,W,4) float32 | RGBA→RGB uint8 |

PIL 사용 (기존 코드 패턴 일치). 저장 실패 시 statusBar 경고, 파이프라인 중단 없음.

---

## OSVRADebugDialog

### 레이아웃

두 개의 `QHBoxLayout`을 `QVBoxLayout`으로 쌓는 구조 (non-modal):

```
┌────────────────────────────────────────────────┐
│  OSVRA Debug — Axial slice 45  [20260319_...] │
├───────────────┬────────────────────────────────┤
│  PET Slice    │       Depth Map                │
│  240×240 px   │       240×240 px               │
├────────┬──────┴──────┬──────────────────────────┤
│CT Aug  │  PET RGBA   │       Fused              │
│240×240 │   240×240   │       240×240            │
└────────┴─────────────┴──────────────────────────┘
│                   [ Close ]                     │
└────────────────────────────────────────────────┘
```

- row1: `QHBoxLayout` — PET Slice, Depth Map (2개)
- row2: `QHBoxLayout` — CT Aug, PET RGBA, Fused (3개)
- 각 셀: 제목 `QLabel` + 이미지 `QLabel` (240×240 px, aspect ratio 유지)
- 다이얼로그 크기: ~780×560 px, 리사이즈 가능
- `show()` 사용 (non-modal)

### numpy → QImage 변환 규칙

**중요:** `tobytes()` 전에 반드시 `np.ascontiguousarray()` 호출.

```python
# RGBA float [0,1] → QImage RGB
arr_u8 = np.ascontiguousarray((arr[..., :3] * 255).clip(0, 255).astype(np.uint8))
h, w = arr_u8.shape[:2]
qimg = QImage(arr_u8.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()

# Grayscale float [0,1] → QImage RGB
arr_u8 = (arr * 255).clip(0, 255).astype(np.uint8)
arr_rgb = np.ascontiguousarray(np.stack([arr_u8] * 3, axis=-1))
qimg = QImage(arr_rgb.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()

# Depth map (NaN 포함) → QImage RGB
d = np.nan_to_num(depth_map, nan=0.0)
d_max = d.max()
if d_max > 0:
    d_norm = (d / d_max * 255).clip(0, 255).astype(np.uint8)
else:
    # 모든 픽셀이 NaN (occlusion hit 없음) → 셀에 "No hits" 텍스트 표시
    d_norm = np.zeros_like(d, dtype=np.uint8)
    # 호출부에서 image_label.setText("No hits") 처리
arr_rgb = np.ascontiguousarray(np.stack([d_norm] * 3, axis=-1))
qimg = QImage(arr_rgb.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888).copy()
```

Depth map all-NaN 케이스: 이미지 `QLabel`에 `setText("No occlusion hits")` 표시 (검은 이미지 대신).

### 다이얼로그 수명 관리

다이얼로그를 `MainWindow` 인스턴스 변수로 보관하여 GC 방지:

```python
# main_window.py 핸들러
def _on_debug_view_clicked(self):
    if self._osvra_debug_data is None:
        return
    self._debug_dialog = OSVRADebugDialog(self._osvra_debug_data, parent=self)
    self._debug_dialog.show()
```

---

## OSVRAPanel UI 변경

- "Render" 버튼 오른쪽에 "Debug View" 버튼 추가
- 초기 상태: `setEnabled(False)`
- 공개 메서드 `set_debug_available(enabled: bool)` 추가 — MainWindow가 직접 `debug_btn` 속성에 접근하지 않음

```python
# osvra_panel.py
def set_debug_available(self, enabled: bool):
    self.debug_btn.setEnabled(enabled)
```

- 클릭 시 `debug_requested` 시그널 emit → `MainWindow._on_debug_view_clicked()` 연결

---

## Error Handling

| 상황 | 처리 |
|------|------|
| PNG 저장 실패 | `try/except` → `statusBar().showMessage(f"OSVRA Debug: save failed — {e}")`. 렌더 결과 표시 영향 없음 |
| Depth map 전체 NaN | 이미지 셀에 "No occlusion hits" 텍스트 표시 |
| `_osvra_debug_data` None 상태에서 버튼 클릭 | 버튼이 비활성 상태이므로 불가능 (방어적으로 `_on_debug_view_clicked`에서도 None 체크) |

---

## `__init__` 초기화

`VolumeRenderingMainWindow.__init__`에 아래 두 줄 추가 (기존 `hasattr` 가드 패턴을 반복하지 않기 위해):

```python
self._osvra_debug_data = None
self._debug_dialog = None
```

`datetime`, `PIL`, `os` 임포트는 `main_window.py`에 이미 존재 — 추가 불필요.

`OSVRADebugDialog` 임포트는 `main_window.py` 상단 OSVRA 모듈 블록에 추가:
```python
from src.gui.dialogs.osvra_debug_dialog import OSVRADebugDialog
```

## 다이얼로그 재열기 동작

Render를 다시 실행하고 "Debug View"를 클릭하면 기존 다이얼로그를 닫고 새로 연다:

```python
def _on_debug_view_clicked(self):
    if self._osvra_debug_data is None:
        return
    if self._debug_dialog is not None:
        self._debug_dialog.close()
    self._debug_dialog = OSVRADebugDialog(self._osvra_debug_data, parent=self)
    self._debug_dialog.show()
```

---

## Files Changed Summary

```
src/gui/dialogs/osvra_debug_dialog.py   ← NEW
src/main_window.py                       ← ADD __init__ vars, import, caching, save, btn enable, handler
src/gui/panel/osvra_panel.py             ← ADD debug_btn, set_debug_available(), debug_requested signal
```

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A PyQt6-based 3D medical volume renderer for image-to-mesh reconstruction work. It loads CT/PET medical images and renders them interactively using VTK GPU ray-casting, with transfer function editing, multi-modal visualization, clipping, and slice viewing.

## Running the Application

```bash
pip install -r requirements.txt
# Install PyTorch separately for your CUDA version: https://pytorch.org/get-started/previous-versions/
python main.py
```

Test environment: CUDA 12.4, Python 3.10, PyTorch 2.6.0.

No build step — pure Python. No automated tests.

## Architecture

### Entry Point & Main Window

`main.py` sets VTK/OpenGL env vars, creates a PyQt6 dark-themed (Fusion) `QApplication`, and launches `VolumeRenderingMainWindow` from `src/main_window.py`.

`src/main_window.py` is the central coordinator: a 3-column layout (fixed 600px left controls | center renderer | right slice viewer) that wires ~20 signals between panels.

### Data Flow

```
User selects file → FilePanel → VolumeLoader (strategy pattern) →
  NIfTILoader / RawLoader / NpyLoader / MataLoader →
VolumeProcessor (reshape, normalize axis order) →
MainWindow.on_ct_loaded() / on_pet_loaded() →
  ├─ RenderingPanel: numpy → vtkImageData → GPU ray-casting
  ├─ TFPanel: update histogram display
  └─ SlicePanel: extract 2D axial/sagittal/coronal slices
```

### VTK Rendering Pipeline (renderer_widget.py)

Uses `vtkMultiVolume` with `vtkOpenGLGPUVolumeRayCastMapper`:
- **Port 0:** CT volume with intensity-based transfer function
- **Port 1:** PET volume with hot colormap

Transfer function changes flow: `TransferFunctionWidget` → signal → `MainWindow.on_tf_changed()` → `RenderingPanel.update_transfer_function()` → updates `vtkVolumeProperty` color/opacity functions in-place.

### Rendering Managers (`src/gui/rendering/`)

Extracted subsystems attached to `VTKVolumeRenderer`:
- `LightingManager` — Phong shading, key/fill lights, material properties
- `ClippingManager` — 6-plane axis-aligned clipping (min/max per X/Y/Z)
- `CameraController` — VTK camera state, spherical coordinates, zoom
- `ScreenshotManager` — Save rendered scene to image

### Transfer Function System

`TransferFunctionWidget` (`src/gui/widget/transfer_function_widget.py`) is a node-based spline editor with histogram display. It supports two modes:
- **Global mode:** intensity → opacity/color for CT
- **Class mode:** class probability → opacity for segmentation overlays

`TFPanel` (`src/gui/panel/tf_panel.py`) hosts CT and PET tabs and integrates lighting controls and clipping panel. TF presets are saved/loaded as JSON in `resources/TFs/`.

### Supported File Formats

| Extension | Loader |
|-----------|--------|
| `.nii`, `.nii.gz` | NIfTILoader (nibabel) |
| `.npy` | NpyLoader |
| `.raw`, `.dat` | RawLoader (configurable shape/dtype/endianness via dialog) |
| `.mha` | via VTK's built-in reader (sample data in `resources/Volume_Data/`) |

### Key Signal Connections in MainWindow

- `file_panel.ct_loaded` → `on_ct_loaded()` — loads primary CT volume
- `file_panel.pet_loaded` → `on_pet_loaded()` — loads secondary PET overlay
- `tf_panel.tf_changed` → `on_tf_changed()` — updates CT transfer function
- `tf_panel.shading_changed` → `on_shading_changed()` — toggles Phong shading
- `tf_panel.clipping_changed` → `on_clipping_changed()` — updates clip planes
- `rendering_panel.vtk_renderer.point_2d_picked` → `on_point_2d_picked()` — point picking for TF optimization

### TF Optimization

`src/core/tf_optimizer.py` uses scipy L-BFGS-B to optimize transfer function parameters for feature visibility based on picked 2D points.

### OSVRA PET-CT Augmentation Pipeline (`src/osvra/`)

Occlusion and Slice-Based Volume Rendering Augmentation for PET-CT fusion:

1. `SOIPlaneBuilder` → axis-aligned Slice of Interest
2. `OcclusionDepthComputer` → CT ray marching occlusion depth map
3. `DepthHistogramAnalyzer` → peak detection for D parameter
4. `LogisticWeightFunction` → distance-based weight
5. `OSVRACTRenderer` → vectorized front-to-back CT augmentation (all N=H*W rays per step)
6. PET TF applied via `VolumeBridge.build_tf_luts()` shared LUT builder
7. `FusionRenderer` → weighted blend of PET RGBA + CT aug RGBA

Key design: PET uses the user's Transfer Function (from TFPanel PET tab), not a matplotlib colormap. TF LUT building is shared in `VolumeBridge.build_tf_luts()`.

QImage usage: always call `.copy()` after constructing from `tobytes()` to prevent dangling pointer segfaults.

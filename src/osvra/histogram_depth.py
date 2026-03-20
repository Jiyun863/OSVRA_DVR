"""
Phase 3: Depth Histogram & Peak Detection
depth map에서 histogram 생성 후 peak detection으로 기본 D 값 선택
"""

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks


class DepthHistogramAnalyzer:
    """Occlusion distance histogram 분석 및 D 선택"""

    def __init__(
        self,
        bin_width_mm: float = 1.0,
        smoothing_sigma: float = 2.0,
        min_peak_prominence: float = 0.01,
        min_peak_distance_bins: int = 5,
    ):
        """
        Args:
            bin_width_mm: histogram bin 너비 (mm)
            smoothing_sigma: Gaussian smoothing sigma (bins)
            min_peak_prominence: 최소 peak prominence (smoothed max의 비율)
            min_peak_distance_bins: peak 간 최소 거리 (bins)
        """
        self.bin_width = bin_width_mm
        self.smoothing_sigma = smoothing_sigma
        self.min_peak_prominence = min_peak_prominence
        self.min_peak_distance = min_peak_distance_bins

    def analyze(
        self,
        depth_map: np.ndarray,
        valid_mask: np.ndarray,
    ) -> dict:
        """Depth histogram 분석

        Args:
            depth_map: (H, W) depth values in mm (NaN for invalid)
            valid_mask: (H, W) bool mask

        Returns:
            dict with keys:
                histogram: bin counts
                bin_edges: bin edges (mm)
                bin_centers: bin centers (mm)
                smoothed: smoothed histogram
                peaks: peak bin indices
                peak_distances: peak distances (mm)
                default_D: first peak distance (mm)
        """
        # 1. valid depth 수집
        valid_depths = depth_map[valid_mask]

        if len(valid_depths) == 0:
            return {
                'histogram': np.array([]),
                'bin_edges': np.array([]),
                'bin_centers': np.array([]),
                'smoothed': np.array([]),
                'peaks': [],
                'peak_distances': [],
                'default_D': 50.0,  # fallback
            }

        # 2. histogram 생성
        max_depth = np.nanmax(valid_depths)
        min_depth = np.nanmin(valid_depths)
        bins = np.arange(min_depth, max_depth + self.bin_width, self.bin_width)

        if len(bins) < 2:
            bins = np.array([min_depth, max_depth + self.bin_width])

        hist, bin_edges = np.histogram(valid_depths, bins=bins)

        # 3. Gaussian smoothing
        if len(hist) > 1:
            smoothed = gaussian_filter1d(hist.astype(np.float64), sigma=self.smoothing_sigma)
        else:
            smoothed = hist.astype(np.float64)

        # 4. peak detection
        peaks = np.array([], dtype=int)
        if len(smoothed) > 2 and smoothed.max() > 0:
            prominence_threshold = self.min_peak_prominence * smoothed.max()
            peaks, _ = find_peaks(
                smoothed,
                prominence=prominence_threshold,
                distance=self.min_peak_distance,
            )

        # 5. bin center 변환
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
        peak_distances = bin_centers[peaks].tolist() if len(peaks) > 0 else []

        # 6. default D = first peak (또는 median depth)
        if peak_distances:
            default_D = peak_distances[0]
        else:
            default_D = float(np.median(valid_depths))

        return {
            'histogram': hist,
            'bin_edges': bin_edges,
            'bin_centers': bin_centers,
            'smoothed': smoothed,
            'peaks': peaks.tolist() if isinstance(peaks, np.ndarray) else peaks,
            'peak_distances': peak_distances,
            'default_D': default_D,
        }

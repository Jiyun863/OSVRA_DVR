"""
Phase 4: Logistic Weight 함수
D를 inflection point로 하는 inverted logistic curve
논문 식: w(d) = C / (1 + A * exp(B * d))
"""

import numpy as np


class LogisticWeightFunction:
    """Inverted logistic weight function

    w(d) = C / (1 + A * exp(B * d))

    Parameters:
        D: inflection point distance (mm)
        A: steepness parameter (default 0.0001)
        C: maximum weight (default 1.0)
        B: computed as ln(A) / D

    Properties:
        - d ~ 0:  w ~ C (~1.0) : SOI 근처 구조 보존
        - d = D:  inflection point
        - d >> D: w -> 0 : 먼 구조 감쇠
    """

    def __init__(self, D: float, A: float = 0.0001, C: float = 1.0):
        self.D = D
        self.A = A
        self.C = C
        self.B = np.log(A) / D if D > 0 else 0.0

    def __call__(self, distances: np.ndarray) -> np.ndarray:
        """distance (mm) -> weight [0, C]

        Args:
            distances: array of distances in mm

        Returns:
            weights array, same shape as distances
        """
        distances = np.asarray(distances, dtype=np.float64)
        return self.C / (1.0 + self.A * np.exp(self.B * distances))

    def as_lut(self, max_distance: float, num_entries: int = 1024) -> tuple:
        """사전 계산된 LUT 반환

        Args:
            max_distance: LUT가 커버할 최대 거리 (mm)
            num_entries: LUT entry 수

        Returns:
            (distances, weights) — 둘 다 np.ndarray shape (num_entries,)
        """
        distances = np.linspace(0, max_distance, num_entries)
        weights = self(distances)
        return distances, weights

import numpy as np
import SimpleITK as sitk
from typing import Tuple, Optional

from base_volume_loader import BaseVolumeLoader


class MetaImageLoader(BaseVolumeLoader):
    """MHA / MHD 볼륨 로더"""

    def load(self, file_path: str) -> Tuple[np.ndarray, Optional[Tuple[float, float, float]]]:
        """
        MetaImage 파일 로드

        Returns
        -------
        volume_data : np.ndarray (W, H, D)
        voxel_spacing : (x, y, z)
        """

        # 파일 읽기
        img = sitk.ReadImage(file_path)

        # numpy 변환 (SimpleITK는 기본적으로 Z,Y,X)
        volume = sitk.GetArrayFromImage(img)  # (D, H, W)

        # (W, H, D)로 변환
        volume = np.transpose(volume, (2, 1, 0))

        # voxel spacing
        spacing = img.GetSpacing()  # (x, y, z)

        return volume.astype(np.float32), spacing

    def get_supported_extensions(self) -> list:
        return [".mha", ".mhd"]
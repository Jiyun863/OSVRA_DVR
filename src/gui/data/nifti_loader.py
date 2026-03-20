"""
NIfTI 파일 로더
"""
import numpy as np
import nibabel as nib
from typing import Tuple, Optional
from .base_loader import BaseVolumeLoader


class NIfTILoader(BaseVolumeLoader):
    """NIfTI (.nii, .nii.gz) 파일 로더"""
    
    def load(self, file_path: str) -> Tuple[np.ndarray, Optional[Tuple]]:
        nii_img = nib.load(file_path)
        volume_data = np.array(nii_img.get_fdata(), order='F')
        voxel_spacing = nii_img.header.get_zooms()[:3]
        return volume_data, voxel_spacing
    
    def get_supported_extensions(self) -> list:
        return ['.nii', '.nii.gz']
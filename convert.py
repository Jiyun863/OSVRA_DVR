import os
import cv2
import numpy as np
from tqdm import tqdm
import shutil
from pathlib import Path
from tqdm import tqdm
import argparse

def convert2GS(source_path):
    input_dir = os.path.join(source_path, "images_rgb") 
    output_base = source_path

    # 생성할 폴더 리스트 (원본 RGB 포함)
    folders = ["images", "images_2", "images_4", "images_8"]
    for f in folders:
        os.makedirs(os.path.join(output_base, f), exist_ok=True)

    # 파일 목록 가져오기
    files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

    print(f"Processing {len(files)} images (RGBA to RGB & Resizing)...")

    for file in tqdm(files):
        source_file = os.path.join(input_dir, file)
        
        # 1. 원본 이미지 읽기 (알파 채널 포함)
        img = cv2.imread(source_file, cv2.IMREAD_UNCHANGED)
        if img is None:
            continue

        # 2. RGBA인 경우 RGB로 변환
        if img.shape[2] == 4:
            bgr_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        else:
            bgr_img = img

        # 3. 원본 크기 RGB 저장 (images 폴더)
        cv2.imwrite(os.path.join(output_base, "images", file), bgr_img)

        # 4. 단계별 리사이징 및 저장
        h, w = bgr_img.shape[:2]
        factors = [2, 4, 8]
        for f in factors:
            new_size = (w // f, h // f)
            resized_img = cv2.resize(bgr_img, new_size, interpolation=cv2.INTER_AREA)
            
            destination_file = os.path.join(output_base, f"images_{f}", file)
            cv2.imwrite(destination_file, resized_img)

    print("Conversion and resizing completed!")

def rename_files(source_path, idx):
    old_file = os.path.join(source_path, f"rgba_{idx:03d}.png")
    new_file = os.path.join(source_path, f"diffuse_{idx:03d}.png")
    os.rename(old_file, new_file)

def RGBA2RGB(source_path):
    " RGBA 이미지들을 RGB로 변환 (Alpha 채널 제거)"
    files = Path(os.path.join(source_path,"images_o")).glob("diffuse_*")
    save_path = os.path.join(source_path,"images_rgb")
    os.makedirs(save_path, exist_ok=True)
    for file in tqdm(files):
        img = cv2.imread(file, cv2.IMREAD_UNCHANGED)
        if img is None:
            print(">>> 이미지 로드 실패")
            break

        if img.shape[2] == 4:
            bgr_img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            cv2.imwrite(os.path.join(save_path, file.name), bgr_img)
    

if __name__ == "__main__":
    argparse = argparse.ArgumentParser()
    argparse.add_argument('-s',"--source_path",  default=None)
    args = argparse.parse_args()
    dir = "./resources/Rendered_Image"
    source_path = os.path.join(dir, args.source_path) if args.source_path else os.path.join(dir, "20260203_224833")

    print(f">>> Processing {source_path} ...")

    RGBA2RGB(source_path)
    convert2GS(source_path)
    
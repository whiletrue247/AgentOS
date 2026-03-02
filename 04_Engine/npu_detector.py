"""
04_Engine — NPU / Hardware Accelerator Detector
=================================================
偵測本機可用的硬體加速器：
  - Apple MPS (M-series Neural Engine)
  - NVIDIA CUDA
  - AMD ROCm
  - Intel NPU / OpenVINO
  - ONNX Runtime providers (DirectML, CoreML, TensorRT, etc.)

Router 可據此決定是否將推論任務導向本地模型 (如 Ollama + NPU offload)。
"""

import logging
import platform
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class HardwareProfile:
    """本機硬體加速能力摘要"""
    cpu_arch: str = ""
    os_name: str = ""
    accelerators: List[str] = field(default_factory=list)
    torch_available: bool = False
    onnx_available: bool = False
    recommended_local_backend: str = "cpu"  # cpu, mps, cuda, rocm


class NPUDetector:
    """
    偵測本機可用的神經處理單元 (NPU) 與硬體加速器。
    支援 torch、onnxruntime、以及平台原生偵測。
    """

    @staticmethod
    def detect() -> HardwareProfile:
        profile = HardwareProfile(
            cpu_arch=platform.machine(),
            os_name=platform.system(),
        )

        # === 1. PyTorch 偵測 ===
        try:
            import torch
            profile.torch_available = True
            profile.accelerators.append(f"torch={torch.__version__}")

            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                profile.accelerators.append(f"cuda ({gpu_name})")
                profile.recommended_local_backend = "cuda"
                logger.info(f"🟢 CUDA detected: {gpu_name}")

            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                profile.accelerators.append("apple-mps")
                profile.recommended_local_backend = "mps"
                logger.info("🟢 Apple MPS (Neural Engine) detected")

            elif hasattr(torch, "xpu") and torch.xpu.is_available():
                profile.accelerators.append("intel-xpu")
                profile.recommended_local_backend = "xpu"
                logger.info("🟢 Intel XPU detected")

            else:
                logger.info("🟡 PyTorch available, but no GPU/NPU accelerator found (CPU only)")

        except ImportError:
            logger.debug("ℹ️ PyTorch not installed — skipping torch-based detection")

        # === 2. ONNX Runtime 偵測 ===
        try:
            import onnxruntime as ort
            profile.onnx_available = True
            providers = ort.get_available_providers()
            profile.accelerators.append(f"onnxruntime={ort.__version__}")

            # 按優先順序偵測加速器
            accel_map = {
                "TensorrtExecutionProvider": "tensorrt",
                "CUDAExecutionProvider": "cuda",
                "DmlExecutionProvider": "directml",       # Windows NPU/GPU
                "CoreMLExecutionProvider": "coreml",       # macOS
                "QNNExecutionProvider": "qualcomm-npu",    # Snapdragon X Elite
                "OpenVINOExecutionProvider": "openvino",   # Intel NPU
                "ROCMExecutionProvider": "rocm",           # AMD
            }

            for prov, label in accel_map.items():
                if prov in providers:
                    profile.accelerators.append(f"onnx-{label}")
                    # 如果 torch 沒有偵測到 GPU，以 ONNX 的結果覆蓋
                    if profile.recommended_local_backend == "cpu":
                        profile.recommended_local_backend = label
                    logger.info(f"🟢 ONNX Runtime accelerator: {label}")

        except ImportError:
            logger.debug("ℹ️ onnxruntime not installed — skipping ONNX-based detection")

        # === 3. 平台原生偵測 (純推論，不依賴 torch/onnx) ===
        if platform.system() == "Darwin" and "arm" in platform.machine().lower():
            if "apple-mps" not in profile.accelerators:
                profile.accelerators.append("apple-silicon (inferred)")
                if profile.recommended_local_backend == "cpu":
                    profile.recommended_local_backend = "mps"

        # === Summary ===
        if not profile.accelerators:
            profile.accelerators.append("cpu-only")

        logger.info(
            f"🔍 Hardware Profile: arch={profile.cpu_arch}, os={profile.os_name}, "
            f"backend={profile.recommended_local_backend}, "
            f"accelerators={profile.accelerators}"
        )
        return profile

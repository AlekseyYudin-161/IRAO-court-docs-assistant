import gc
import torch
from backend.src.core.config import settings


class GPUUtils:
    """Simplified utilities for GPU memory management"""

    @staticmethod
    def get_device() -> str:
        """Determines the device considering settings and availability or forces the required one."""
        force_device = settings.FORCE_DEVICE
        if force_device != "auto":
            if force_device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA is selected in settings but is not available.")
            if force_device == "mps" and not (
                hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
            ):
                raise RuntimeError("MPS is selected in settings but is not available.")
            if force_device not in ("cpu", "cuda", "mps"):
                raise ValueError(f"Unsupported device: {force_device}")
            return force_device
        # Auto-detection
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def cleanup():
        """Simple GPU memory cleanup"""
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if torch.cuda.is_initialized():
                torch.cuda.synchronize()

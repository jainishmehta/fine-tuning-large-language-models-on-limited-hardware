from psutil import Process
from pynvml import nvmlInit, nvmlDeviceGetHandleByIndex, nvmlDeviceGetMemoryInfo

import logging
logger = logging.getLogger(__name__)


class SystemMonitor:
    def __init__(self):
        # Initialize NVML for GPU monitoring
        self.nvml_initialized = self._initialize_nvml()

    def _initialize_nvml(self):
        try:
            nvmlInit()
            return True
        except Exception as e:
            logger.error(f"Error initializing NVML: {e}")
            return False

    def get_gpu_memory_usage(self):
        if not self.nvml_initialized:
            logger.error("NVML not initialized.")
            return None

        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            info = nvmlDeviceGetMemoryInfo(handle)
            return info.used // 1024 ** 2
        except Exception as e:
            logger.error(f"Error retrieving GPU memory info: {e}")
            return None

    def print_gpu_utilization(self):
        gpu_memory = self.get_gpu_memory_usage()
        if gpu_memory is not None:
            logger.info(f"GPU memory occupied: {gpu_memory} MB.")

    def get_ram_usage(self):
        return Process().memory_info().rss / (1024 * 1024)
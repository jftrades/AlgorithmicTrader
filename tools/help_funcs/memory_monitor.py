import psutil
import os
from typing import Dict, Any

class MemoryMonitor:    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.initial_memory = self.get_current_memory()
        self.peak_memory = self.initial_memory
        self.memory_log = []
        
    def get_current_memory(self) -> float:
        try:
            memory_info = self.process.memory_info()
            return memory_info.rss / 1024 / 1024  # Convert to MB
        except Exception:
            return 0.0
    
    def log_memory(self, label: str = "") -> Dict[str, Any]:
        current_memory = self.get_current_memory()
        self.peak_memory = max(self.peak_memory, current_memory)
        
        memory_data = {
            'label': label,
            'current_mb': round(current_memory, 2),
            'peak_mb': round(self.peak_memory, 2),
            'growth_mb': round(current_memory - self.initial_memory, 2),
            'growth_pct': round((current_memory - self.initial_memory) / self.initial_memory * 100, 1)
        }
        
        self.memory_log.append(memory_data)
        return memory_data
    
    def get_memory_summary(self) -> str:
        current = self.get_current_memory()
        return (f"Memory: Initial={self.initial_memory:.1f}MB, "
                f"Current={current:.1f}MB, "
                f"Peak={self.peak_memory:.1f}MB, "
                f"Growth={current-self.initial_memory:.1f}MB "
                f"({(current-self.initial_memory)/self.initial_memory*100:.1f}%)")
    
    def print_memory_log(self):
        print("\n" + "="*70)
        print("MEMORY USAGE LOG")
        print("="*70)
        for entry in self.memory_log:
            print(f"{entry['label']:30} | "
                  f"Current: {entry['current_mb']:8.1f}MB | "
                  f"Growth: +{entry['growth_mb']:8.1f}MB ({entry['growth_pct']:+5.1f}%)")
        print("="*70)
        print(f"PEAK MEMORY: {self.peak_memory:.1f}MB")
        print("="*70)

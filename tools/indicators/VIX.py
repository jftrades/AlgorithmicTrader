import json
from pathlib import Path
from typing import List, Dict, Any, Optional

def load_vix_jsonl(relative_path: str) -> List[Dict[str, Any]]:
    path = Path(relative_path)
    if not path.is_absolute():
        # Relativ zum Projekt-Root (drei Ebenen hoch von diesem File)
        path = Path(__file__).parents[3] / relative_path
    data = []
    with open(path, "r") as f:
        for line in f:
            data.append(json.loads(line))
    return data

def extract_vix_close(row: Dict[str, Any]) -> float:
    close_dict = row.get("close", {})
    close_val = close_dict.get("0", None)
    return float(close_val) if close_val is not None else None

def market_in_fear_VIX(vix_value: float) -> bool:
    return vix_value is not None and vix_value > 25

def market_chilling_VIX(vix_value: float) -> bool:
    return vix_value is not None and vix_value < 25

class VIXIndicator:
    def __init__(self, vix_data: List[Dict[str, Any]]):
        self.vix_data = sorted(vix_data, key=lambda x: int(x["ts_event"]))
        self.timestamps = [int(row["ts_event"]) for row in self.vix_data]

    def get_vix_for_timestamp(self, ts_event: int) -> Optional[float]:
        for i in reversed(range(len(self.timestamps))):
            if self.timestamps[i] <= ts_event:
                return extract_vix_close(self.vix_data[i])
        return None

# in die yaml kommt morgen:

# vix_data_path: "data/DATA_STORAGE/data_catalog_wrangled/data/bar/^VIX.CBOE-1-DAY-LAST-EXTERNAL/2007-12-28T23-59-59-999999999Z_2024-12-31T23-59-59-999999999Z.parquet.as.json"


# in die strategy kommmt z.B.

# from tools.indicators.VIX import load_vix_jsonl, VIXIndicator, market_in_fear_VIX, market_chilling_VIX

# class DeineStrategy(...):
#     def __init__(self, config):
#         super().__init__(config)
#         self.vix_indicator = None
#         self.vix_data_path = config.get("vix_data_path")  # aus YAML

#     def on_start(self):
#         self.vix_indicator = VIXIndicator(load_vix_jsonl(self.vix_data_path))

#     def on_bar(self, bar):
#         vix_value = self.vix_indicator.get_vix_for_timestamp(bar.ts_event)
#         if market_in_fear_VIX(vix_value):
#             # z.B. keine Longs, Hedge aktivieren etc.
#             pass
#         elif market_chilling_VIX(vix_value):
#             # z.B. normal traden
#             pass
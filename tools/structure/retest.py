from typing import List, Dict, Tuple, Any
from decimal import Decimal

class RetestAnalyser:
    def __init__(self):
        self.box_retest_zones: List[Dict[str, Any]] = []  # List of Box Retest zones with direction
        self.level_retest_zones: List[Dict[str, Any]] = []  # List of Level Retest zones with tolerance and direction

    def set_box_retest_zone(self, upper: Decimal, lower: Decimal, long_retest: bool = True) -> None:
        self.box_retest_zones.append({"upper": upper, "lower": lower, "long_retest": long_retest})

    def check_box_retest_zone(self, price: Decimal, filter: str = None) -> Tuple[bool, Dict[str, Any]]:
        for zone in self.box_retest_zones:
            # Apply filter if specified
            if filter == "long" and not zone["long_retest"]:
                continue
            elif filter == "short" and zone["long_retest"]:
                continue
            
            if zone["lower"] <= price <= zone["upper"]:
                return True, zone
        return False, {}

    def set_level_retest_zone(self, level: Decimal, tolerance: Decimal, long_retest: bool = True) -> None:
        self.level_retest_zones.append({"level": level, "tolerance": tolerance, "long_retest": long_retest})

    def check_level_retest_zone(self, price: Decimal, filter: str = None) -> Tuple[bool, Dict[str, Any]]:
        for zone in self.level_retest_zones:
            # Apply filter if specified
            if filter == "long" and not zone["long_retest"]:
                continue
            elif filter == "short" and zone["long_retest"]:
                continue
                
            level = zone["level"]
            tolerance = zone["tolerance"]
            lower_bound = level * (1 - tolerance)
            upper_bound = level * (1 + tolerance)
            if lower_bound <= price <= upper_bound:
                return True, zone
        return False, {}

    def remove_box_retest_zone(self, upper: Decimal, lower: Decimal) -> None:
        self.box_retest_zones = [
            zone for zone in self.box_retest_zones if zone["upper"] != upper or zone["lower"] != lower
        ]

    def remove_level_retest_zone(self, level: Decimal) -> None:
        self.level_retest_zones = [zone for zone in self.level_retest_zones if zone["level"] != level]

    def remove_all_box_retest_zones(self) -> None:
        self.box_retest_zones.clear()

    def remove_all_level_retest_zones(self) -> None:
        self.level_retest_zones.clear()

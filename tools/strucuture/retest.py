from typing import List, Dict, Tuple, Any
from decimal import Decimal

class RetestAnalyser:
    def __init__(self):
        """
        Initializes the RetestAnalyser with storage for multiple retest zones.
        """
        self.box_retest_zones: List[Dict[str, Any]] = []  # List of Box Retest zones with direction
        self.level_retest_zones: List[Dict[str, Any]] = []  # List of Level Retest zones with tolerance and direction

    def set_box_retest_zone(self, upper: Decimal, lower: Decimal, long_retest: bool = True) -> None:
        """
        Sets a new Box Retest zone and stores it in the list.
        :param upper: Upper boundary of the box.
        :param lower: Lower boundary of the box.
        :param long_retest: Boolean indicating if the retest is for a long position (True) or short position (False).
        """
        self.box_retest_zones.append({"upper": upper, "lower": lower, "long_retest": long_retest})

    def check_box_retest_zone(self, price: Decimal, filter: str = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Checks if the given price is within any of the stored Box Retest zones.
        :param price: The current price to check.
        :param filter: Filter zones by direction - "long" for long_retest=True, "short" for long_retest=False, None for all.
        :return: Tuple (True/False, zone) indicating if a retest occurred and the zone details.
        """
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
        """
        Sets a new Level Retest zone with a tolerance range and stores it in the list.
        :param level: The horizontal level to be tested.
        :param tolerance: The percentage tolerance around the level.
        :param long_retest: Boolean indicating if the retest is for a long position (True) or short position (False).
        """
        self.level_retest_zones.append({"level": level, "tolerance": tolerance, "long_retest": long_retest})

    def check_level_retest_zone(self, price: Decimal, filter: str = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Checks if the given price is within the tolerance range of any stored Level Retest zones.
        :param price: The current price to check.
        :param filter: Filter zones by direction - "long" for long_retest=True, "short" for long_retest=False, None for all.
        :return: Tuple (True/False, zone) indicating if a retest occurred and the zone details.
        """
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
        """
        Removes a specific Box Retest zone from the list.
        :param upper: Upper boundary of the box.
        :param lower: Lower boundary of the box.
        """
        self.box_retest_zones = [
            zone for zone in self.box_retest_zones if zone["upper"] != upper or zone["lower"] != lower
        ]

    def remove_level_retest_zone(self, level: Decimal) -> None:
        """
        Removes a specific Level Retest zone from the list.
        :param level: The horizontal level to remove.
        """
        self.level_retest_zones = [zone for zone in self.level_retest_zones if zone["level"] != level]

    def remove_all_box_retest_zones(self) -> None:
        """
        Removes all Box Retest zones from the list.
        """
        self.box_retest_zones.clear()

    def remove_all_level_retest_zones(self) -> None:
        """
        Removes all Level Retest zones from the list.
        """
        self.level_retest_zones.clear()

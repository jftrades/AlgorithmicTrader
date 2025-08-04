import numpy as np
from collections import deque
import datetime

class VWAPZScoreHTF:
    def __init__(
        self,
        zscore_window: int = 60,
        vwap_lookback: int = 20,
        gap_threshold_pct: float = 0.1,
        rth_start = (15, 40),
        rth_end = (21, 50),
        **kwargs
    ):
        self.zscore_window = zscore_window
        self.vwap_lookback = vwap_lookback
        self.price_volume_window = deque(maxlen=vwap_lookback)
        self.volume_window = deque(maxlen=vwap_lookback)
        self.diff_window = deque(maxlen=zscore_window)
        self.current_vwap_value = None
        self.last_close = None
        self.gap_offsets = []
        self.cumulative_gap = 0.0
        self.bar_index = 0
        self.gap_threshold_pct = gap_threshold_pct
        self.rth_start = rth_start
        self.rth_end = rth_end

        self.rth_session_volumes = deque(maxlen=3)
        self.current_rth_volume = 0.0
        self.last_bar_was_rth = False

    def is_rth(self, bar):
        t = datetime.datetime.fromtimestamp(bar.ts_event // 1_000_000_000, tz=datetime.timezone.utc).time()
        rth_start = datetime.time(*self.rth_start)
        rth_end = datetime.time(*self.rth_end)
        return rth_start <= t <= rth_end

    def update(self, bar):
        price = float(bar.close)
        volume = float(bar.volume)

        # 1. Gap-Erkennung (z.B. Wochenende)
        if self.last_close is not None:
            gap = float(bar.open) - float(self.last_close)
            gap_pct = abs(gap) / float(self.last_close) * 100
            if gap_pct > self.gap_threshold_pct:
                self.cumulative_gap += gap
                self.gap_offsets.append((self.bar_index, self.cumulative_gap))

        # 2. Kumulierten Gap-Offset für diese Bar berechnen
        offset = 0.0
        if self.gap_offsets:
            for idx, gap in reversed(self.gap_offsets):
                if idx <= self.bar_index:
                    offset = gap
                    break

        # 3. RTH-Session-Volumen tracken
        is_rth = self.is_rth(bar)
        if is_rth:
            self.current_rth_volume += volume
            self.last_bar_was_rth = True
        else:
            # Wenn die letzte Bar RTH war und jetzt ETH beginnt, Session abschließen
            if self.last_bar_was_rth:
                self.rth_session_volumes.append(self.current_rth_volume)
                self.current_rth_volume = 0.0
                self.last_bar_was_rth = False

        # 4. Volumen für ETH automatisch auf Durchschnitt der letzten 3 RTH-Sessions setzen
        if is_rth:
            adj_price = price - offset
            adj_volume = volume
        else:
            avg_rth_volume = np.mean(self.rth_session_volumes) if self.rth_session_volumes else volume
            adj_price = price - offset
            adj_volume = avg_rth_volume

        price_volume = adj_price * adj_volume
        self.price_volume_window.append(price_volume)
        self.volume_window.append(adj_volume)

        if len(self.price_volume_window) < self.vwap_lookback or sum(self.volume_window) == 0:
            self.current_vwap_value = None
            self.last_close = price
            self.bar_index += 1
            return None, None

        vwap_value = sum(self.price_volume_window) / sum(self.volume_window)
        self.current_vwap_value = vwap_value

        diff = adj_price - vwap_value
        self.diff_window.append(diff)

        if len(self.diff_window) < self.zscore_window:
            self.last_close = price
            self.bar_index += 1
            return vwap_value, None

        mean = np.mean(self.diff_window)
        std = np.std(self.diff_window)
        zscore = (diff - mean) / std if std > 0 else 0.0

        self.last_close = price
        self.bar_index += 1
        return vwap_value, zscore
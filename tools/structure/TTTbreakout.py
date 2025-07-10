from typing import List, Tuple
from decimal import Decimal
from nautilus_trader.model.data import Bar

class TTTBreakout_Analyser:
    def __init__(self, lookback: int = 20, atr_mult: float = 1.5, max_counter: int = 6):
        self.lookback = lookback
        self.bars: List[Bar] = []
        self.state = "SEARCH_STRONG"
        self.direction = None
        self.strong_bar = None
        self.boundary = None
        self.counter = 0
        self.counter_bars = []
        self.range_candle = None
        self.effective_boundary = None
        self.atr_mult = atr_mult
        self.max_counter = max_counter
        self.last_breakout = None

    def update_bars(self, bar: Bar):
        self.bars.append(bar)
        if len(self.bars) > self.lookback:
            self.bars.pop(0)
        
    def _calc_atr(self, n=14):
        if len(self.bars) < n + 1:
            return None
        trs = [max(b.high - b.low, abs(b.high - self.bars[i-1].close), abs(b.low - self.bars[i-1].close))
               for i, b in enumerate(self.bars[-n:], start=len(self.bars)-n)]
        return sum(trs) / n

    def is_tttbreakout(self) -> Tuple[bool, str]:
        """
        Implementiert die exakte TTT-Breakout-Logik.
        Gibt (True, "long"/"short") bei Breakout, sonst (False, "").
        """
        # Schritt 1: Starke Candle finden
        atr = self._calc_atr()
        if atr is None or len(self.bars) < 8:
            return False, ""

        bar = self.bars[-1]

        # Schritt 2: STARKE Kerze finden mit ATR
        if self.state == "SEARCH_STRONG":
            if (bar.close > bar.open) and ((bar.close - bar.open) > self.atr_mult * atr):
                self.state = "COUNT_BEARISH"
                self.direction = "long"
                self.strong_bar = bar
                self.counter = 0
                self.counter_bars = []
    
            elif (bar.open > bar.close) and ((bar.open - bar.close) > self.atr_mult * atr):
                self.state = "COUNT_BULLISH"
                self.direction = "short"
                self.strong_bar = bar
                self.counter = 0
                self.counter_bars = []
            return False, ""
        
        # Schritt 3: Mind. 2, max. 6 Gegenkerzen
        elif self.state == "COUNT_BEARISH":
            if bar.close < bar.open:
                self.counter += 1
                self.counter_bars.append(bar)
                if self.counter > self.max_counter:
                    self._reset()
            elif self.counter >= 2:
                self.boundary = self.strong_bar.close
                self.state = "WAIT_BULLISH"
            else:
                self._reset()
            return False, ""

        elif self.state == "COUNT_BULLISH":
            if bar.close > bar.open:
                self.counter += 1
                self.counter_bars.append(bar)
                if self.counter > self.max_counter:
                    self._reset()
            elif self.counter >= 2:
                self.boundary = self.strong_bar.close
                self.state = "WAIT_BEARISH"
            else:
                self._reset()
            return False, ""
        
        # Schritt 4: Candle in Ursprungsrichtung
        elif self.state == "WAIT_BULLISH":
            if bar.close > bar.open:
                self.range_candle = bar
                self.state = "CONFIRM_RANGE_BULLISH"
            return False, ""

        elif self.state == "WAIT_BEARISH":
            if bar.close < bar.open:
                self.range_candle = bar
                self.state = "CONFIRM_RANGE_BEARISH"
            return False, ""
        
        # Schritt 5: Close der darauffolgenden Candle prüft Boundary und Open
        elif self.state == "CONFIRM_RANGE_BULLISH":
            if bar.close > self.boundary or bar.close < self.range_candle.open:
                self._reset()
            else:
                self.effective_boundary = self.range_candle.open
                self.state = "ACTIVE_RANGE_LONG"
            return False, ""

        elif self.state == "CONFIRM_RANGE_BEARISH":
            if bar.close < self.boundary or bar.close > self.range_candle.open:
                self._reset()
            else:
                self.effective_boundary = self.range_candle.open
                self.state = "ACTIVE_RANGE_SHORT"
            return False, ""

        # Schritt 7: Breakout abwarten
        elif self.state == "ACTIVE_RANGE_LONG":
            if bar.close > self.effective_boundary and (bar.close - self.effective_boundary) > 0.2 * atr:
                self.last_breakout = ("long", bar)
                self._reset()
                return True, "long"
            return False, ""

        elif self.state == "ACTIVE_RANGE_SHORT":
            if bar.close < self.effective_boundary and (self.effective_boundary - bar.close) > 0.2 * atr:
                self.last_breakout = ("short", bar)
                self._reset()
                return True, "short"
            return False, ""

        return False, ""
    
    def _reset(self):
        self.state = "SEARCH_STRONG"
        self.direction = None
        self.strong_bar = None
        self.boundary = None
        self.counter = 0
        self.counter_bars = []
        self.range_candle = None
        self.effective_boundary = None



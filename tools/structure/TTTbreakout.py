from typing import List, Tuple
from decimal import Decimal
from nautilus_trader.model.data import Bar

class TTTBreakout_Analyser:
    def __init__(self, lookback: int = 15, atr_mult: float = 1.25, max_counter: int = 6):
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
        if len(self.bars) > self.lookback + 1:
            self.bars.pop(0)
        
    def _calc_atr(self, n=None):
        n = self.lookback
        if len(self.bars) < n + 1:
            return None
        trs = []
        bars = self.bars
        for i in range(len(bars) - n, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close if i > 0 else bars[i].close 
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return sum(trs) / n

    def is_tttbreakout(self) -> Tuple[bool, str]:
        # Schritt 1: ATR holen
        atr = self._calc_atr()
        if atr is None or len(self.bars) < self.lookback:
            return False, ""
        atr = float(atr)

        bar = self.bars[-1]

        # Schritt 2: STARKE Kerze finden mit ATR
        if self.state == "SEARCH_STRONG":
            print(f"SEARCH_STRONG: Bar O:{bar.open} C:{bar.close} ATR:{self._calc_atr()}")
            if (bar.close > bar.open) and ((bar.close - bar.open) > self.atr_mult * atr):
                print(f"STATE: {self.state}, Counter: {self.counter}, Dir: {self.direction}, Bar: O:{bar.open} C:{bar.close}")
                self.state = "COUNT_BEARISH"
                self.direction = "long"
                self.strong_bar = bar
                self.counter = 0
                self.counter_bars = []
    
            elif (bar.open > bar.close) and ((bar.open - bar.close) > self.atr_mult * atr):
                print(f"STATE: {self.state}, Counter: {self.counter}, Dir: {self.direction}, Bar: O:{bar.open} C:{bar.close}")
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
                print(f"STATE: {self.state}, Counter: {self.counter}, Dir: {self.direction}, Bar: O:{bar.open} C:{bar.close}")
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
                print(f"STATE: {self.state}, Counter: {self.counter}, Dir: {self.direction}, Bar: O:{bar.open} C:{bar.close}") 
                self.state = "WAIT_BEARISH"
            else:
                self._reset()
            return False, ""
        
        # Schritt 4: Candle in Ursprungsrichtung
        elif self.state == "WAIT_BULLISH":
            if bar.close > bar.open:
                self.range_candle = bar
                print(f"STATE: {self.state}, Counter: {self.counter}, Dir: {self.direction}, Bar: O:{bar.open} C:{bar.close}")
                self.state = "CONFIRM_RANGE_BULLISH"
            return False, ""

        elif self.state == "WAIT_BEARISH":
            if bar.close < bar.open:
                self.range_candle = bar
                print(f"STATE: {self.state}, Counter: {self.counter}, Dir: {self.direction}, Bar: O:{bar.open} C:{bar.close}")
                self.state = "CONFIRM_RANGE_BEARISH"
            return False, ""
        
        # Schritt 5: Close der darauffolgenden Candle prüft Boundary und Open
        elif self.state == "CONFIRM_RANGE_BULLISH":
            if bar.close > self.boundary or bar.close < self.range_candle.open:
                self._reset()
            else:
                self.effective_boundary = self.range_candle.open
                print(f"STATE: {self.state}, Counter: {self.counter}, Dir: {self.direction}, Bar: O:{bar.open} C:{bar.close}")    
                self.state = "ACTIVE_RANGE_LONG"
            return False, ""

        elif self.state == "CONFIRM_RANGE_BEARISH":
            if bar.close < self.boundary or bar.close > self.range_candle.open:
                self._reset()
            else:
                self.effective_boundary = self.range_candle.open
                print(f"STATE: {self.state}, Counter: {self.counter}, Dir: {self.direction}, Bar: O:{bar.open} C:{bar.close}")    
                self.state = "ACTIVE_RANGE_SHORT"
            return False, ""

        # Schritt 6: Breakout abwarten
        elif self.state in ("ACTIVE_RANGE_LONG", "ACTIVE_RANGE_SHORT"):
            print(f"ACTIVE_RANGE: close={bar.close}, eff_boundary={self.effective_boundary}")
            # Breakout nach oben
            if bar.close > self.effective_boundary:
                self.last_breakout = ("long", bar)
                self._reset()
                return True, "long"
            # Breakout nach unten
            elif bar.close < self.effective_boundary:
                self.last_breakout = ("short", bar)
                self._reset()
                return True, "short"
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



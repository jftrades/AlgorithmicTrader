# Strategiekonzept: “VolSpike CloseBias Reversal”

# Kurzbeschreibung:
# Die Strategie erkennt außergewöhnlich volatile Marktbewegungen mit gleichzeitig überdurchschnittlichem 
# Volumen und reagiert darauf, wenn der Markt zum Ende der Candle hin Stärke zeigt 
# – unabhängig davon, ob es sich um eine Rejection (Reversal) oder ein Momentum-Break handelt. 
# Die Reversion wird zusätzlich durch ein strukturelles Überdehnungssignal (Z-Score) abgesichert.

# Wir nutzen die robuste ATR Berechnung nach Welles Wilder (robuster gegen z.B. gaps)


class VSCBRReversal:
    def __init__(self, config):
        self.tr_factor = config.VSCBR_truerange_factor
        self.vol_factor = config.VSCBR_volume_factor
        self.zscore_threshold = config.VSCBR_zscore_threshold
        self.atr_window = config.VSCBR_atr_window
        self.volume_window = config.VSCBR_volume_window
        self.tr_history = []
        self.volume_history = []
        self.prev_close = None

    def update(self, bar):
        if self.prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - self.prev_close),
                abs(bar.low - self.prev_close)
            )
        self.tr_history.append(tr)
        self.volume_history.append(bar.volume)
        if len(self.tr_history) > self.atr_window:
            self.tr_history.pop(0)
        if len(self.volume_history) > self.volume_window:
            self.volume_history.pop(0)
        self.prev_close = bar.close

    def is_signal(self, bar, zscore):
        if len(self.tr_history) < self.atr_window or len(self.volume_history) < self.volume_window:
            return False, False

        avg_tr = sum(self.tr_history) / len(self.tr_history)
        avg_vol = sum(self.volume_history) / len(self.volume_history)
        # Berechne TR für aktuelle Bar (mit prev_close)
        tr = max(
            bar.high - bar.low,
            abs(bar.high - self.prev_close),
            abs(bar.low - self.prev_close)
        ) if self.prev_close is not None else bar.high - bar.low

        rel_close = (bar.close - bar.low) / (bar.high - bar.low) if (bar.high - bar.low) > 0 else 0.5


        tr_ok = float(tr) > float(self.tr_factor) * float(avg_tr)
        vol_ok = float(bar.volume) > float(self.vol_factor) * float(avg_vol)
        rel_close_ok = rel_close >= 0.5

        long_ok = zscore < -self.zscore_threshold
        short_ok = zscore > self.zscore_threshold

        long_signal = tr_ok and vol_ok and rel_close_ok and long_ok
        short_signal = tr_ok and vol_ok and rel_close_ok and short_ok

        return long_signal, short_signal
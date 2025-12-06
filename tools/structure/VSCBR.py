# volspike closebias reversal - detects volatile moves with high volume and close bias for reversals

class VSCBRReversal:
    def __init__(self, config):
        self.tr_factor = config.VSCBR_truerange_factor
        self.vol_factor = config.VSCBR_volume_factor
        self.zscore_threshold = config.VSCBR_zscore_threshold
        self.atr_window = config.VSCBR_atr_window
        self.volume_window = config.VSCBR_volume_window
        self.long_rel_close_threshold = getattr(config, "VSCBR_long_rel_close_threshold", 0.75)
        self.short_rel_close_threshold = getattr(config, "VSCBR_short_rel_close_threshold", 0.25)
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
        tr = max(
            bar.high - bar.low,
            abs(bar.high - self.prev_close),
            abs(bar.low - self.prev_close)
        ) if self.prev_close is not None else bar.high - bar.low

        rel_close = (bar.close - bar.low) / (bar.high - bar.low) if (bar.high - bar.low) > 0 else 0.5

        tr_ok = float(tr) > float(self.tr_factor) * float(avg_tr)
        vol_ok = float(bar.volume) > float(self.vol_factor) * float(avg_vol)

        long_rel_close_ok = rel_close >= self.long_rel_close_threshold
        short_rel_close_ok = rel_close <= self.short_rel_close_threshold

        long_ok = zscore < -self.zscore_threshold
        short_ok = zscore > self.zscore_threshold

        long_signal = tr_ok and vol_ok and long_rel_close_ok and long_ok
        short_signal = tr_ok and vol_ok and short_rel_close_ok and short_ok

        return long_signal, short_signal
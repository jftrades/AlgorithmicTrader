import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from arch import arch_model
from collections import deque

class GARCH:
    def __init__(self, returns: pd.Series, window: int = 500):
        self.returns = self.fix_returns_scale(returns.dropna())
        self.window = window
        self.model = None
        self.result = None

    @staticmethod
    def fix_returns_scale(returns):
        mean_abs = abs(returns).mean()
        scale = 1
        if mean_abs < 1:
            scale = int(1 / mean_abs)
        return returns * scale

    def fit(self, p=1, q=1):
        if len(self.returns) > self.window:
            returns_window = self.returns.iloc[-self.window:]
        else:
            returns_window = self.returns
        self.model = arch_model(returns_window, vol='Garch', p=p, q=q)
        self.result = self.model.fit(disp='off')
        return self.result
    
    def update(self, close, prev_close):
        if prev_close is not None:
            ret = np.log(float(close) / float(prev_close))
            self.returns_window.append(ret)
            returns_series = pd.Series(self.returns_window)
            returns_series = self.fix_returns_scale(returns_series)
            self.model = arch_model(returns_series, vol='Garch', p=self.p, q=self.q)
            self.result = self.model.fit(disp='off')
            self.current_volatility = self.result.conditional_volatility.iloc[-1]
        else:
            self.current_volatility = None

    def get_volatility(self):
        return self.current_volatility

    def plot_volatility(self):
        if self.result is None:
            raise ValueError("Modell muss zuerst gefittet werden.")
        plt.figure(figsize=(12, 5))
        plt.plot(self.result.conditional_volatility, label='GARCH Volatilität')
        plt.title('Geschätzte GARCH-Volatilität')
        plt.legend()
        plt.show()

    def forecast_volatility(self, steps=5):
        if self.result is None:
            raise ValueError("Modell muss zuerst gefittet werden.")
        forecast = self.result.forecast(horizon=steps)
        return np.sqrt(forecast.variance.iloc[-1])
    
def update_garch_vola_window(window, current_vola, maxlen):
    if window is None:
        window = deque(maxlen=maxlen)
    if current_vola is not None:
        window.append(current_vola)
    return window

def get_garch_vola_threshold(window, quantile=0.8, min_bars=200):
    if window is not None and len(window) >= min_bars:
        vola_series = pd.Series(window)
        return vola_series.quantile(quantile)
    return None
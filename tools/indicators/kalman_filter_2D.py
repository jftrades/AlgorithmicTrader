import numpy as np
from collections import deque

class KalmanFilterRegression:
    def __init__(
        self,
        process_var: float = 0.00001,
        measurement_var: float = 0.01,
        window: int = 10,
        initial_state_mean: float = None,
        initial_state_covariance: float = 1.0,
    ):
        self.process_var = process_var
        self.measurement_var = measurement_var
        self.mean = initial_state_mean
        self.var = initial_state_covariance
        self.initialized = False if initial_state_mean is None else True
        self.window = []
        self.window_size = window
        self.buffer = deque(maxlen=window)  # Für Regression

    def update(self, value: float):
        self.buffer.append(value)
        
        # Initialisierung
        if not self.initialized:
            self.window.append(value)
            if len(self.window) == self.window_size:
                self.mean = np.mean(self.window)
                self.initialized = True
            return self.mean if self.initialized else None, 0.0

        # Prediction
        pred_mean = self.mean
        pred_var = self.var + self.process_var

        # Update
        K = pred_var / (pred_var + self.measurement_var)
        self.mean = pred_mean + K * (value - pred_mean)
        self.var = (1 - K) * pred_var

        if len(self.buffer) >= 2:
            y = np.array(self.buffer)
            x = np.arange(len(y))
            raw_slope = np.polyfit(x, y, 1)[0]
            slope = raw_slope * 1  
        else:
            slope = 0.0

        return self.mean, slope

    def reset(self):
        self.mean = None
        self.var = 1.0
        self.initialized = False
        self.window = []
        self.buffer.clear()

    def is_initialized(self) -> bool:
        return self.initialized

    def get_state(self):
        return self.mean, self.var

    def get_regression_slope(self):
        if len(self.buffer) >= 2:
            y = np.array(self.buffer)
            x = np.arange(len(y))
            raw_slope = np.polyfit(x, y, 1)[0]
            # Scale up the slope to make trends more pronounced
            return raw_slope * 100  # Scale factor of 100
        return 0.0

class KalmanFilter1D:
    def __init__(
        self,
        process_var: float = 0.00001,         # Prozessrauschen (transition_covariance)
        measurement_var: float = 0.01,     # Messrauschen (observation_covariance)
        window: int = 10,                  # Initialisierungsfenster
        initial_state_mean: float = None,  # Optional: Startwert
        initial_state_covariance: float = 1.0,
    ):
        self.process_var = process_var
        self.measurement_var = measurement_var
        self.mean = initial_state_mean
        self.var = initial_state_covariance
        self.initialized = False if initial_state_mean is None else True
        self.window = []
        self.window_size = window


    def update(self, value: float) -> float:
        if not self.initialized:
            self.window.append(value)
            if len(self.window) == self.window_size:
                self.mean = np.mean(self.window)
                self.initialized = True
            return self.mean if self.initialized else None

        # Prediction
        pred_mean = self.mean
        pred_var = self.var + self.process_var

        # Update
        K = pred_var / (pred_var + self.measurement_var)
        self.mean = pred_mean + K * (value - pred_mean)
        self.var = (1 - K) * pred_var


        return self.mean

    def reset(self):
        self.mean = None
        self.var = 1.0
        self.initialized = False
        self.window = []

    def is_initialized(self) -> bool:
        return self.initialized
    
    def get_state(self):
        return self.mean, self.var

from decimal import Decimal
from nautilus_trader.model.currencies import USDT, USD
from nautilus_trader.model.identifiers import AccountId

class RiskManager:
    def __init__(self, strategy, risk_percent: Decimal = Decimal(0.01), max_leverage: Decimal = Decimal("5.0"), min_account_balance: Decimal = Decimal("10"), risk_reward_ratio: Decimal = Decimal("2")) -> None:
        self.strategy = strategy
        self.risk_percent = risk_percent
        self.max_leverage = max_leverage
        self.min_account_balance = min_account_balance
        self.risk_reward_ratio = risk_reward_ratio

    def calculate_position_size(self, entry_price: Decimal, stop_loss_price: Decimal) -> Decimal:
        valid_position = True
        account_balance = self.get_account_balance()
        risk_amount = Decimal(account_balance) * Decimal(self.risk_percent)
        risk_per_unit = abs(entry_price - stop_loss_price)

        # Ensure the risk per unit is valid
        if risk_per_unit <= 0:
            valid_position = False
            return 0, valid_position
            
        position_size = risk_amount / risk_per_unit

        max_position_value = account_balance * self.max_leverage
        max_position_size = max_position_value / entry_price

        if position_size > max_position_size:
            position_size = max_position_size
        if position_size <= 0:
            valid_position = False
            #raise ValueError(f"Calculated position size must be greater than zero. {position_size} is not valid.")
        return position_size, valid_position


    def update_risk_percent(self, new_risk_percent: Decimal) -> None:
        self.risk_percent = new_risk_percent
    
    def check_if_balance_is_sufficient(self, required_balance: Decimal = None) -> bool:
        account_balance = self.get_account_balance()
        if required_balance is None:
            required_balance = self.min_account_balance
        return account_balance >= required_balance
    
    def calculate_tp_price(self, entry_price: Decimal, stop_loss: Decimal, risk_reward_ratio: Decimal = None) -> Decimal:
        if risk_reward_ratio is None:
            risk_reward_ratio = self.risk_reward_ratio
        if risk_reward_ratio <= 0:
            raise ValueError("Risk-reward ratio must be greater than zero.")
        
        risk = abs(entry_price - stop_loss)
        
        # Determine if it's a long or short position based on stop loss position
        if stop_loss < entry_price:  # Long position
            take_profit = entry_price + risk_reward_ratio * risk
        else:  # Short position
            take_profit = entry_price - risk_reward_ratio * risk
            
        return take_profit
    
    # Hilfsfunktion
    def get_account_balance(self) -> Decimal:
        venue = self.strategy.instrument_id.venue
        account_id = AccountId(f"{venue}-001")
        account = self.strategy.cache.account(account_id)
        if account is None:
            return Decimal("0")

        # Versuche zuerst USD, dann USDT
        for currency in (USD, USDT):
            balance_obj = account.balance(currency)
            if balance_obj is not None and balance_obj.free is not None:
                try:
                    return Decimal(str(balance_obj.free).split(" ")[0])
                except Exception:
                    continue
        # Fallback: 0, falls keine passende Balance gefunden
        return Decimal("0")

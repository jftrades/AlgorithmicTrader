from decimal import Decimal
from nautilus_trader.model.currencies import USDT, USD
from nautilus_trader.model.identifiers import AccountId

class RiskManager:
    def __init__(self, config) -> None:
        self.config = config
        self.strategy = None
        self.starting_balance = None
        self.max_leverage = None

    def set_strategy(self, strategy):
        self.strategy = strategy

    def set_max_leverage(self, leverage: Decimal):
        self.max_leverage = leverage

    def get_starting_balance(self):
        if self.starting_balance is None:
            if hasattr(self.strategy, 'config') and hasattr(self.strategy.config, 'starting_account_balance'):
                balance_str = self.strategy.config.starting_account_balance
                if isinstance(balance_str, str):
                    self.starting_balance = Decimal(balance_str.split(" ")[0])
                else:
                    self.starting_balance = Decimal(str(balance_str))
            else:
                self.starting_balance = Decimal("1000")
        return self.starting_balance

    def exp_growth_atr_risk(self, entry_price: Decimal, stop_loss_price: Decimal, risk_percent: Decimal) -> Decimal:
        current_balance = self.get_current_balance()
        if current_balance <= Decimal("0"):
            return Decimal("0")
        
        risk_amount = current_balance * risk_percent
        sl_distance = abs(entry_price - stop_loss_price)
        
        if sl_distance <= Decimal("0"):
            return Decimal("0")
        
        contracts_needed = risk_amount / sl_distance
        
        if self.max_leverage is not None and self.max_leverage > Decimal("0"):
            max_position_value = current_balance * self.max_leverage
            max_contracts_allowed = max_position_value / entry_price
            contracts_needed = min(contracts_needed, max_contracts_allowed)

        return contracts_needed

    def log_growth_atr_risk(self, entry_price: Decimal, stop_loss_price: Decimal, risk_percent: Decimal) -> Decimal:
        starting_balance = self.get_starting_balance()
        if starting_balance <= Decimal("0"):
            return Decimal("0")
        
        risk_amount = starting_balance * risk_percent
        sl_distance = abs(entry_price - stop_loss_price)
        
        if sl_distance <= Decimal("0"):
            return Decimal("0")
        
        contracts_needed = risk_amount / sl_distance
        
        if self.max_leverage is not None and self.max_leverage > Decimal("0"):
            max_position_value = starting_balance * self.max_leverage
            max_contracts_allowed = max_position_value / entry_price
            contracts_needed = min(contracts_needed, max_contracts_allowed)

        return contracts_needed

    def exp_fixed_trade_risk(self, entry_price: Decimal, invest_percent: Decimal) -> Decimal:
        current_balance = self.get_current_balance()
        invest_amount = current_balance * invest_percent
        return invest_amount / entry_price

    def log_fixed_trade_risk(self, entry_price: Decimal, investment_size: Decimal) -> Decimal:
        return investment_size / entry_price

    def get_current_balance(self) -> Decimal:
        if self.strategy is None:
            return Decimal("0")
        
        if hasattr(self.strategy, 'instrument_dict') and self.strategy.instrument_dict:
            venue = next(iter(self.strategy.instrument_dict.keys())).venue
        else:
            return Decimal("0")
        
        account_id = AccountId(f"{venue}-001")
        account = self.strategy.cache.account(account_id)
        if account is None:
            return Decimal("0")

        for currency in (USD, USDT):
            balance_obj = account.balance(currency)
            if balance_obj is not None and balance_obj.free is not None:
                try:
                    return Decimal(str(balance_obj.free).split(" ")[0])
                except Exception:
                    continue
        return Decimal("0")

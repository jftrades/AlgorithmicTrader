#this file contains helper functions 


def create_tags(type=None, action=None, sl=None, tp=None):
    tags = []
    if sl is not None:
        tags.append(f"SL:{sl}")
    if tp is not None:
        tags.append(f"TP:{tp}")
    if type is not None:
        tags.append(f"TYPE:{type}")
    if action is not None:
        tags.append(f"ACTION:{action}")
    return tags

def extract_interval_from_bar_type(bar_type_str: str) -> str:
    """
    Extrahiert den Schritt+Aggregation-Teil (z.B. '5-MINUTE' oder '1-HOUR')
    aus einem NautilusTrader BarType-String.
    
    Beispiele:
    'BTCUSDT-PERP.BINANCE-5-MINUTE-LAST-EXTERNAL' -> '5-MINUTE'
    '6EH4.XCME-1-HOUR-LAST-INTERNAL@5-MINUTE-INTERNAL' -> '1-HOUR'
    """
    # Linke Seite vom evtl. @ nehmen
    left_part = bar_type_str.split("@")[0]
    # In Segmente splitten
    parts = left_part.split("-")
    if len(parts) >= 4:
        # Index 1 = step, Index 2 = aggregation
        return f"{parts[1]}-{parts[2]}"
    else:
        raise ValueError(f"BarType-String hat unerwartetes Format: {bar_type_str}")


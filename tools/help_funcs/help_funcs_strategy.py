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

def extract_interval_from_bar_type(bar_type_str: str, instrument_id: str) -> str:
    """
    Liefert kompaktes Intervall:
      5-MINUTE -> 5M
      1-HOUR   -> 1h
    Vorgehen:
      1. Entfernt führendes '<instrument_id>-' falls vorhanden.
      2. Trennt am '@' (nur linken Teil nutzen).
      3. Splittet Rest per '-'.
      4. Nimmt erste beiden Tokens = step, unit.
      5. Mappt unit auf Kurzform.
    """
    if not bar_type_str:
        raise ValueError("bar_type_str leer.")
    # 1) Linke Seite vor '@'
    left_part = bar_type_str.split("@", 1)[0]
    # 2) Instrument-Prefix entfernen falls exakt passend
    prefix = f"{instrument_id}-"
    if left_part.startswith(prefix):
        left_part = left_part[len(prefix):]
    parts = left_part.split("-")
    if len(parts) < 2:
        raise ValueError(f"Unerwartetes BarType-Format (zu wenige Segmente): {bar_type_str}")
    step = parts[0]
    unit = parts[1].upper()

    # 3) Mapping für Kurzformen
    unit_map = {
        "SECOND": "s",
        "SECONDS": "s",
        "MINUTE": "M",
        "MINUTES": "M",
        "HOUR": "h",
        "HOURS": "h",
        "DAY": "D",
        "DAYS": "D",
        "WEEK": "W",
        "WEEKS": "W",
    }
    suffix = unit_map.get(unit, unit[0])  # Fallback: erster Buchstabe
    return f"{step}{suffix}"


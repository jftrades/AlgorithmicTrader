# yaml_loader.py
import yaml
from typing import List, Dict, Any, Tuple


def load_params(yaml_path: str) -> Dict[str, Any]:
    """
    Lädt YAML als Dict. Leere Dateien werden als {} behandelt.
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _normalize_instruments(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Erwartet params["instruments"] als Liste von Dicts.

    Normalisiert JEDE Instrument-Definition so, dass mindestens folgende Felder
    garantiert vorhanden sind:

      - instrument_id: <str>             (PFLICHT)
      - bar_types: List[str]             (PFLICHT; mindestens 1 Element)
      - trade_size_usdt: <Any>           (optional; fällt auf globalen Wert zurück, wenn vorhanden)

    Unterstützte Eingaben je Instrument:
      - bar_type: "<...>"                          # einzelner String
      - bar_types: ["<...>", "<...>"]              # Liste von Strings
      - bar_types: [{"bar_type":"<...>"}, ...]     # Liste von Dicts mit Schlüssel "bar_type"

    Alle weiteren (benutzerdefinierten) Felder werden unverändert übernommen
    (z. B. paramXY, paramAB, ...).

    Fehlerfälle:
      - Fehlender Schlüssel 'instruments'
      - 'instruments' ist nicht Liste
      - Eintrag ist kein Mapping
      - instrument_id fehlt/ist nicht str
      - bar_type/bar_types fehlen oder ergeben nach Normalisierung leere Liste
      - bar_types-Elemente haben unbekanntes Format
    """
    if "instruments" not in params or params["instruments"] is None:
        raise KeyError("YAML fehlt Schlüssel 'instruments'. Bitte in der YAML 'instruments' spezifizieren.")

    raw_list = params["instruments"]
    if not isinstance(raw_list, list):
        raise TypeError("'instruments' muss eine Liste sein.")

    global_size = params.get("trade_size_usdt", None)

    normalized: List[Dict[str, Any]] = []
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            raise TypeError(f"instruments[{i}] muss ein Mapping (dict) sein, erhalten: {type(item)}")

        # --- instrument_id prüfen ---
        instr_id = item.get("instrument_id")
        if not instr_id or not isinstance(instr_id, str):
            raise ValueError(
                f"instruments[{i}]: 'instrument_id' fehlt oder ist kein String. "
                f"Bitte in der YAML angeben: instrument_id: \"<YOUR_ID>\""
            )

        # --- bar_types normalisieren ---
        bar_types: List[str] = []
        if "bar_types" in item and item["bar_types"] is not None:
            bt = item["bar_types"]
            if isinstance(bt, list):
                for j, e in enumerate(bt):
                    if isinstance(e, str):
                        bar_types.append(e)
                    elif isinstance(e, dict) and "bar_type" in e and isinstance(e["bar_type"], str):
                        bar_types.append(e["bar_type"])
                    else:
                        raise ValueError(
                            f"instruments[{i}].bar_types[{j}] hat unbekanntes Format: {e!r}. "
                            f"Erlaubt sind Strings oder Dicts mit Schlüssel 'bar_type'."
                        )
            else:
                raise TypeError(f"instruments[{i}].'bar_types' muss eine Liste sein.")
        elif "bar_type" in item and item["bar_type"] is not None:
            if isinstance(item["bar_type"], str):
                bar_types.append(item["bar_type"])
            else:
                raise TypeError(f"instruments[{i}].'bar_type' muss ein String sein.")
        else:
            raise ValueError(
                f"instruments[{i}]: Es muss mindestens ein 'bar_type' oder 'bar_types' angegeben sein. "
                f"Bitte in der YAML spezifizieren."
            )

        # Nach-Normalisierung: leere Liste verbieten
        if not bar_types:
            raise ValueError(f"instruments[{i}]: 'bar_types' ist leer nach Normalisierung. Bitte in der YAML prüfen.")

        # Duplikate stabil entfernen
        seen_bt = set()
        bar_types_dedup = []
        for bt in bar_types:
            if bt not in seen_bt:
                seen_bt.add(bt)
                bar_types_dedup.append(bt)

        # --- trade_size_usdt mit Fallback auf globalen Wert (falls vorhanden) ---
        trade_size = item.get("trade_size_usdt", global_size)

        # --- Alle benutzerdefinierten Felder übernehmen ---
        # Start mit einer flachen Kopie des Items (damit z. B. paramXY/paramAB erhalten bleiben)
        out: Dict[str, Any] = dict(item)
        # Pflichtfelder/normalisierte Felder setzen/überschreiben
        out["instrument_id"] = instr_id
        out["bar_types"] = bar_types_dedup
        # Nur setzen, wenn vorhanden (wir wollen das Feld nicht erzwingen)
        if trade_size is not None:
            out["trade_size_usdt"] = trade_size

        # Optional: 'bar_type' Einzelschlüssel entfernen, da in 'bar_types' überführt
        if "bar_type" in out:
            del out["bar_type"]

        normalized.append(out)

    return normalized


def load_and_split_params(yaml_path: str) -> Tuple[
    Dict[str, Any],                # params (inkl. normalisiertem 'instruments')
    Dict[str, List[Any]],          # param_grid (nur Nicht-Instrument-Keys mit Listenlänge > 1)
    List[str],                     # keys (Grid-Keys in stabiler Reihenfolge)
    List[List[Any]],               # values (Listen von Grid-Werten; gleiche Reihenfolge wie keys)
    Dict[str, Any],                # static_params (Nicht-Grid-Parameter; Single-Listen -> Skalar)
    List[str],                     # all_instrument_ids (duplikatfrei)
    List[str],                     # all_bar_types (duplikatfrei)
]:
    """
    Lädt die YAML, normalisiert 'instruments' und splittet in Grid-/Static-Parameter.

    Regeln:
      - 'instruments' wird NICHT als Grid-Parameter behandelt (die Liste beschreibt
        konkrete Instrument-Spezifikationen, nicht einen Grid).
      - Für alle anderen Keys gilt:
          * Wenn Wert eine Liste mit Länge > 1 -> kommt in param_grid
          * Wenn Wert eine Liste mit Länge == 1 -> wird in static_params zu Skalar reduziert
          * Ansonsten -> direkt in static_params übernommen
      - all_instrument_ids / all_bar_types werden aus instruments aggregiert (stabil, duplikatfrei)

    Fehler/Validierungen passieren in _normalize_instruments.
    """
    params = load_params(yaml_path)

    # 1) instruments normalisieren (inkl. Pflicht-Validierungen)
    instruments_normalized = _normalize_instruments(params)
    params["instruments"] = instruments_normalized  # optional: Original-Objekt anreichern/ersetzen

    # 2) param_grid: nur Keys mit Listen-Länge > 1 (exkl. 'instruments')
    param_grid: Dict[str, List[Any]] = {}
    for k, v in params.items():
        if k == "instruments":
            continue
        if isinstance(v, list) and len(v) > 1:
            param_grid[k] = v

    # 3) static_params: alle Keys, die nicht im Grid sind. Single-Element-Listen -> Skalar.
    static_params: Dict[str, Any] = {}
    for k, v in params.items():
        if k in param_grid:
            continue
        if k == "instruments":
            static_params[k] = instruments_normalized
        else:
            if isinstance(v, list) and len(v) == 1:
                static_params[k] = v[0]
            else:
                static_params[k] = v

    # 4) keys/values für das Grid (stabile Reihenfolge anhand Einfüge-Reihenfolge von dict)
    if param_grid:
        keys, values = zip(*param_grid.items())
        keys, values = list(keys), list(values)
    else:
        keys, values = [], []

    # 5) Aggregationen für IDs und BarTypes (duplikatfrei, stabil)
    seen_ids, all_instrument_ids = set(), []
    seen_bt, all_bar_types = set(), []
    for instr in instruments_normalized:
        iid = instr.get("instrument_id")
        if isinstance(iid, str) and iid not in seen_ids:
            seen_ids.add(iid)
            all_instrument_ids.append(iid)

        for bt in instr.get("bar_types", []) or []:
            if isinstance(bt, str) and bt not in seen_bt:
                seen_bt.add(bt)
                all_bar_types.append(bt)

    return params, param_grid, keys, values, static_params, all_instrument_ids, all_bar_types

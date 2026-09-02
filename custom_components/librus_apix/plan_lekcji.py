"""Czysta logika przetwarzania planu lekcji z Librusa.

Modul celowo nie importuje Home Assistanta ani biblioteki librus_apix,
dzieki czemu da sie go testowac samodzielnie.
"""

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

# Nazwy dni tygodnia zwracane przez librus_apix.timetable.Period.weekday
DNI_TYGODNIA_PL = {
    "Monday": "Poniedzialek",
    "Tuesday": "Wtorek",
    "Wednesday": "Sroda",
    "Thursday": "Czwartek",
    "Friday": "Piatek",
    "Saturday": "Sobota",
    "Sunday": "Niedziela",
}


# Mapowanie polskich znakow diakrytycznych na ASCII - etykiety z Librusa
# ("Zastepstwo", "Lekcja odwolana") pisane sa z ogonkami.
_OGONKI = str.maketrans(
    "\u0105\u0107\u0119\u0142\u0144\u00f3\u015b\u017a\u017c",
    "acelnoszz",
)


def _zawiera(tekst: str, *rdzenie: str) -> bool:
    """Sprawdz czy tekst zawiera ktorykolwiek z rdzeni, ignorujac wielkosc liter i ogonki."""
    maly = tekst.lower().translate(_OGONKI)
    return any(rdzen in maly for rdzen in rdzenie)


def _opis_zmiany(info: Dict[str, Any]) -> str:
    """Zwroc etykiete zmiany (np. 'Zastepstwo') z pola info okresu."""
    return "; ".join(k.strip() for k in info.keys() if k and k.strip()) if info else ""


def przetworz_plan(tygodnie: Iterable[Iterable[Iterable[Any]]]) -> List[Dict[str, Any]]:
    """Zamien surowy plan z librus_apix na plaska, posortowana liste lekcji.

    Args:
        tygodnie: kolekcja tygodni, gdzie kazdy tydzien to lista dni,
            a kazdy dzien to lista obiektow Period.

    Returns:
        Lista slownikow z polskimi kluczami, posortowana po dacie i numerze lekcji.
        Puste okienka (Period bez przedmiotu) sa pomijane.
    """
    lekcje: Dict[tuple, Dict[str, Any]] = {}

    for tydzien in tygodnie or []:
        for dzien in tydzien or []:
            for period in dzien or []:
                przedmiot = (getattr(period, "subject", "") or "").strip()
                if not przedmiot:
                    continue

                info = getattr(period, "info", None) or {}
                opis = _opis_zmiany(info)
                weekday = getattr(period, "weekday", "") or ""
                data = getattr(period, "date", "") or ""
                numer = getattr(period, "number", None)

                lekcje[(data, numer)] = {
                    "data": data,
                    "dzien_tygodnia": DNI_TYGODNIA_PL.get(weekday, weekday),
                    "numer": numer,
                    "przedmiot": przedmiot,
                    # Biblioteka sklada to pole dzielac tekst po "-", wiec w praktyce
                    # bywa to sama sala albo nauczyciel z sala - nie rozbijamy tego dalej.
                    "nauczyciel_sala": (
                        getattr(period, "teacher_and_classroom", "") or ""
                    ).strip(),
                    "od": (getattr(period, "date_from", "") or "").strip(),
                    "do": (getattr(period, "date_to", "") or "").strip(),
                    "przerwa_od": getattr(period, "next_recess_from", None),
                    "przerwa_do": getattr(period, "next_recess_to", None),
                    "odwolana": _zawiera(opis, "odwol"),
                    "zastepstwo": _zawiera(opis, "zastep"),
                    "info": opis,
                    "szczegoly": info,
                }

    return sorted(lekcje.values(), key=lambda l: (l["data"], l["numer"] or 0))


def _polacz(data: str, godzina: str) -> Optional[datetime]:
    """Zloz date (YYYY-MM-DD) i godzine (H:MM lub HH:MM) w datetime."""
    if not data or not godzina:
        return None
    try:
        return datetime.strptime(f"{data} {godzina}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def lekcje_dnia(plan: List[Dict[str, Any]], dzien: date) -> List[Dict[str, Any]]:
    """Zwroc lekcje z podanego dnia."""
    iso = dzien.strftime("%Y-%m-%d")
    return [l for l in plan if l["data"] == iso]


def pogrupuj_wg_dni(plan: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Pogrupuj plan wedlug daty, zachowujac kolejnosc chronologiczna."""
    dni: Dict[str, List[Dict[str, Any]]] = {}
    for lekcja in plan:
        dni.setdefault(lekcja["data"], []).append(lekcja)
    return dni


def nastepna_lekcja(
    plan: List[Dict[str, Any]], teraz: datetime
) -> Optional[Dict[str, Any]]:
    """Znajdz trwajaca lub najblizsza przyszla lekcje.

    Lekcje odwolane sa pomijane. Zwraca kopie slownika lekcji wzbogacona
    o pola 'trwa_teraz' i 'za_minut' (0 dla lekcji trwajacej).
    """
    for lekcja in plan:
        if lekcja.get("odwolana"):
            continue

        start = _polacz(lekcja["data"], lekcja["od"])
        if start is None:
            continue
        koniec = _polacz(lekcja["data"], lekcja["do"])

        # Bez poprawnej godziny konca przyjmujemy, ze lekcja minela wraz ze startem.
        if (koniec or start) <= teraz:
            continue

        trwa = start <= teraz
        pozostalo = 0 if trwa else int((start - teraz).total_seconds() // 60)
        return {**lekcja, "trwa_teraz": trwa, "za_minut": pozostalo}

    return None

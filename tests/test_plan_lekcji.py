"""Testy czystej logiki planu lekcji."""

from datetime import date, datetime
from types import SimpleNamespace

from custom_components.librus_apix.plan_lekcji import (
    lekcje_dnia,
    nastepna_lekcja,
    pogrupuj_wg_dni,
    przetworz_plan,
)


def period(
    subject="Matematyka",
    date_="2026-09-07",
    number=1,
    date_from="08:00",
    date_to="08:45",
    weekday="Monday",
    info=None,
    teacher_and_classroom=" 12",
    next_recess_from=None,
    next_recess_to=None,
):
    """Zbuduj atrape obiektu Period z librus_apix."""
    return SimpleNamespace(
        subject=subject,
        teacher_and_classroom=teacher_and_classroom,
        date=date_,
        date_from=date_from,
        date_to=date_to,
        weekday=weekday,
        info=info or {},
        number=number,
        next_recess_from=next_recess_from,
        next_recess_to=next_recess_to,
    )


def tydzien(*periods):
    """Owin okresy w strukture tygodnia (lista dni, kazdy dzien to lista okresow)."""
    return [list(periods)]


def test_przetworz_plan_pomija_puste_okienka():
    plan = przetworz_plan([tydzien(period(subject=""), period(subject="  "), period())])

    assert len(plan) == 1
    assert plan[0]["przedmiot"] == "Matematyka"


def test_przetworz_plan_tlumaczy_dzien_i_sortuje():
    plan = przetworz_plan(
        [
            tydzien(
                period(date_="2026-09-08", number=2, weekday="Tuesday"),
                period(date_="2026-09-07", number=3, weekday="Monday"),
                period(date_="2026-09-07", number=1, weekday="Monday"),
            )
        ]
    )

    assert [(l["data"], l["numer"]) for l in plan] == [
        ("2026-09-07", 1),
        ("2026-09-07", 3),
        ("2026-09-08", 2),
    ]
    assert plan[0]["dzien_tygodnia"] == "Poniedzialek"
    assert plan[-1]["dzien_tygodnia"] == "Wtorek"


def test_przetworz_plan_wykrywa_zastepstwo_i_odwolanie():
    plan = przetworz_plan(
        [
            tydzien(
                period(number=1, info={"Zastępstwo": {"teacher_swap": "Nowak"}}),
                period(number=2, info={"Lekcja odwołana": ""}),
                period(number=3),
            )
        ]
    )

    zastepstwo, odwolana, zwykla = plan
    assert zastepstwo["zastepstwo"] is True and zastepstwo["odwolana"] is False
    assert odwolana["odwolana"] is True and odwolana["zastepstwo"] is False
    assert zwykla["zastepstwo"] is False and zwykla["odwolana"] is False
    assert zwykla["info"] == ""


def test_przetworz_plan_deduplikuje_powtorzone_tygodnie():
    plan = przetworz_plan([tydzien(period()), tydzien(period())])

    assert len(plan) == 1


def test_nastepna_lekcja_zwraca_najblizsza_przyszla():
    plan = przetworz_plan(
        [
            tydzien(
                period(number=1, date_from="08:00", date_to="08:45"),
                period(number=2, date_from="09:00", date_to="09:45", subject="Fizyka"),
            )
        ]
    )

    wynik = nastepna_lekcja(plan, datetime(2026, 9, 7, 8, 50))

    assert wynik["przedmiot"] == "Fizyka"
    assert wynik["trwa_teraz"] is False
    assert wynik["za_minut"] == 10


def test_nastepna_lekcja_zwraca_trwajaca():
    plan = przetworz_plan([tydzien(period(date_from="08:00", date_to="08:45"))])

    wynik = nastepna_lekcja(plan, datetime(2026, 9, 7, 8, 30))

    assert wynik["trwa_teraz"] is True
    assert wynik["za_minut"] == 0


def test_nastepna_lekcja_pomija_odwolane():
    plan = przetworz_plan(
        [
            tydzien(
                period(number=1, date_from="08:00", info={"Lekcja odwołana": ""}),
                period(number=2, date_from="09:00", date_to="09:45", subject="Fizyka"),
            )
        ]
    )

    wynik = nastepna_lekcja(plan, datetime(2026, 9, 7, 7, 0))

    assert wynik["przedmiot"] == "Fizyka"


def test_nastepna_lekcja_brak_gdy_wszystko_minelo():
    plan = przetworz_plan([tydzien(period(date_from="08:00", date_to="08:45"))])

    assert nastepna_lekcja(plan, datetime(2026, 9, 7, 9, 0)) is None


def test_nastepna_lekcja_ignoruje_bledne_godziny():
    plan = przetworz_plan([tydzien(period(date_from="", date_to=""))])

    assert nastepna_lekcja(plan, datetime(2026, 9, 7, 7, 0)) is None


def test_lekcje_dnia_i_grupowanie():
    plan = przetworz_plan(
        [
            tydzien(
                period(date_="2026-09-07", number=1),
                period(date_="2026-09-07", number=2),
                period(date_="2026-09-08", number=1, weekday="Tuesday"),
            )
        ]
    )

    assert len(lekcje_dnia(plan, date(2026, 9, 7))) == 2
    assert lekcje_dnia(plan, date(2026, 9, 9)) == []

    dni = pogrupuj_wg_dni(plan)
    assert list(dni.keys()) == ["2026-09-07", "2026-09-08"]
    assert len(dni["2026-09-07"]) == 2

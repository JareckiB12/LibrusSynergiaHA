"""Test the Librus APIX integration."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.librus_apix.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Wlacz ladowanie custom_components w testach."""
    return


def _lekcja(numer, przedmiot, od, do, dzien=None, zastepstwo=False, odwolana=False):
    """Zbuduj wpis planu lekcji w formacie zwracanym przez async_get_timetable."""
    dzien = dzien or date.today()
    return {
        "data": dzien.strftime("%Y-%m-%d"),
        "dzien_tygodnia": "Poniedziałek",
        "numer": numer,
        "przedmiot": przedmiot,
        "nauczyciel_sala": "12",
        "od": od,
        "do": do,
        "przerwa_od": None,
        "przerwa_do": None,
        "odwolana": odwolana,
        "zastepstwo": zastepstwo,
        "info": "Zastepstwo" if zastepstwo else ("Lekcja odwolana" if odwolana else ""),
        "szczegoly": {},
    }


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Librus",
        data={"username": "test_user", "password": "test_password"},
    )


@pytest.fixture
def mock_librus_client():
    """Return a mock Librus client."""
    client = MagicMock()
    client.async_authenticate = AsyncMock(return_value=True)
    client.async_get_student_information = AsyncMock(
        return_value=SimpleNamespace(
            name="Jan Kowalski",
            class_name="8A",
            number=7,
            tutor="Anna Nowak",
            school="SP nr 1",
            lucky_number=13,
        )
    )
    client.async_get_grades = AsyncMock(return_value=[
        {
            "subject": "Matematyka",
            "grade": "5",
            "date": "2025-01-01",
            "category": "Test",
            "teacher": "Jan Kowalski",
            "semester": 1,
            "type": "numeric",
        }
    ])
    client.async_get_messages = AsyncMock(return_value=[])
    client.async_get_homework = AsyncMock(return_value=[])
    client.async_get_schedule = AsyncMock(return_value=[])
    client.async_get_timetable = AsyncMock(return_value=[
        _lekcja(1, "Matematyka", "08:00", "08:45"),
        _lekcja(2, "Fizyka", "09:00", "09:45", zastepstwo=True),
        _lekcja(1, "Historia", "08:00", "08:45", dzien=date.today() + timedelta(days=1)),
    ])
    return client


async def _setup(hass: HomeAssistant, entry, client) -> None:
    """Skonfiguruj integracje z zamockowanym klientem."""
    entry.add_to_hass(hass)
    with patch("custom_components.librus_apix.LibrusApiClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_setup_entry(hass: HomeAssistant, mock_config_entry, mock_librus_client):
    """Test the setup entry."""
    await _setup(hass, mock_config_entry, mock_librus_client)

    assert mock_config_entry.entry_id in hass.data[DOMAIN]


async def test_unload_entry(hass: HomeAssistant, mock_config_entry, mock_librus_client):
    """Test unloading an entry."""
    await _setup(hass, mock_config_entry, mock_librus_client)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.entry_id not in hass.data[DOMAIN]


async def test_plan_lekcji_sensor(hass: HomeAssistant, mock_config_entry, mock_librus_client):
    """Czujnik planu lekcji wystawia dzisiejsze lekcje i wykryte zmiany."""
    # Ostatnia lekcja konczy sie o 23:59, wiec dzien jest "biezacy" niezaleznie
    # od tego, o ktorej uruchomiono testy.
    mock_librus_client.async_get_timetable.return_value = [
        _lekcja(1, "Matematyka", "00:00", "00:45"),
        _lekcja(2, "Fizyka", "23:10", "23:59", zastepstwo=True),
        _lekcja(1, "Historia", "08:00", "08:45", dzien=date.today() + timedelta(days=1)),
    ]

    await _setup(hass, mock_config_entry, mock_librus_client)

    stan = hass.states.get("sensor.librus_jan_kowalski_plan_lekcji")
    assert stan is not None
    assert stan.state == "2"
    assert stan.attributes["pierwsza_lekcja"] == "00:00"
    assert stan.attributes["ostatnia_lekcja"] == "23:59"
    jutro = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    assert [l["przedmiot"] for l in stan.attributes["tydzien"][jutro]] == ["Historia"]
    assert stan.attributes["sa_zmiany"] is True
    assert [l["przedmiot"] for l in stan.attributes["zmiany"]] == ["Fizyka"]


async def test_nastepna_lekcja_sensor(hass: HomeAssistant, mock_config_entry, mock_librus_client):
    """Czujnik nastepnej lekcji wybiera pierwsza lekcje, ktora sie nie skonczyla."""
    mock_librus_client.async_get_timetable.return_value = [
        _lekcja(1, "Matematyka", "00:00", "00:01"),
        _lekcja(2, "Fizyka", "23:58", "23:59"),
    ]

    await _setup(hass, mock_config_entry, mock_librus_client)

    stan = hass.states.get("sensor.librus_jan_kowalski_nastepna_lekcja")
    assert stan is not None
    assert stan.state == "Fizyka"
    assert stan.attributes["numer"] == 2
    assert stan.attributes["od"] == "23:58"


async def test_plan_lekcji_przeskakuje_na_kolejny_dzien(
    hass: HomeAssistant, mock_config_entry, mock_librus_client
):
    """Po ostatniej lekcji dnia czujnik pokazuje plan nastepnego dnia."""
    jutro = date.today() + timedelta(days=1)
    mock_librus_client.async_get_timetable.return_value = [
        # Dzisiejsze lekcje sa juz po czasie (koncza sie o 00:01).
        _lekcja(1, "Matematyka", "00:00", "00:01"),
        _lekcja(1, "Historia", "08:00", "08:45", dzien=jutro),
        _lekcja(2, "Chemia", "09:00", "09:45", dzien=jutro),
    ]

    await _setup(hass, mock_config_entry, mock_librus_client)

    stan = hass.states.get("sensor.librus_jan_kowalski_plan_lekcji")
    assert [l["przedmiot"] for l in stan.attributes["tydzien"][stan.attributes["biezacy_dzien_data"]]] == [
        "Historia",
        "Chemia",
    ]
    assert stan.attributes["biezacy_dzien_data"] == jutro.strftime("%Y-%m-%d")
    assert stan.attributes["biezacy_dzien_nazwa"]

    # Zakonczony dzien znika rowniez z planu tygodnia.
    assert list(stan.attributes["tydzien"]) == [jutro.strftime("%Y-%m-%d")]

    # Liczniki nadal opisuja doslownie dzisiaj.
    assert stan.attributes["liczba_lekcji_dzisiaj"] == 1


async def test_plan_lekcji_trzyma_sie_dzis_w_trakcie_zajec(
    hass: HomeAssistant, mock_config_entry, mock_librus_client
):
    """Dopoki trwa ostatnia lekcja, pokazywany jest biezacy dzien."""
    mock_librus_client.async_get_timetable.return_value = [
        _lekcja(1, "Matematyka", "00:00", "23:59"),
        _lekcja(1, "Historia", "08:00", "08:45", dzien=date.today() + timedelta(days=1)),
    ]

    await _setup(hass, mock_config_entry, mock_librus_client)

    stan = hass.states.get("sensor.librus_jan_kowalski_plan_lekcji")
    assert [l["przedmiot"] for l in stan.attributes["tydzien"][stan.attributes["biezacy_dzien_data"]]] == ["Matematyka"]
    assert stan.attributes["biezacy_dzien_data"] == date.today().strftime("%Y-%m-%d")


async def test_plan_lekcji_zaznacza_wydarzenia_i_zadania(
    hass: HomeAssistant, mock_config_entry, mock_librus_client
):
    """Kartkowka trafia na swoja lekcje, wywiadowka do wydarzen calodniowych."""
    dzis = date.today().strftime("%Y-%m-%d")
    mock_librus_client.async_get_timetable.return_value = [
        _lekcja(1, "matematyka", "00:00", "00:45"),
        _lekcja(4, "fizyka", "23:10", "23:59"),
    ]
    mock_librus_client.async_get_schedule.return_value = [
        {
            "data": dzis, "tydzien": "Wednesday", "tytul": "kartkówka",
            "przedmiot": "fizyka", "godzina": "unknown", "numer_lekcji": 4,
            "szczegoly": {"Nauczyciel": "Anna Nowak", "Opis": "wielkości fizyczne"},
            "href": "",
        },
        {
            "data": dzis, "tydzien": "Wednesday", "tytul": "godz.: 17:00",
            "przedmiot": "Wywiadówka: zebranie rodziców", "godzina": "17:00",
            "numer_lekcji": "unknown", "szczegoly": {}, "href": "",
        },
    ]
    mock_librus_client.async_get_homework.return_value = [
        SimpleNamespace(
            subject="matematyka", category="Praca domowa", teacher="Danuta Kowalska",
            lesson="", task_date=dzis, completion_date=dzis, href="",
        )
    ]

    await _setup(hass, mock_config_entry, mock_librus_client)

    stan = hass.states.get("sensor.librus_jan_kowalski_plan_lekcji")
    lekcje = {l["przedmiot"]: l for l in stan.attributes["tydzien"][stan.attributes["biezacy_dzien_data"]]}

    assert [w["tytul"] for w in lekcje["fizyka"]["wydarzenia"]] == ["kartkówka"]
    assert lekcje["fizyka"]["wydarzenia"][0]["opis"] == "wielkości fizyczne"
    assert [z["kategoria"] for z in lekcje["matematyka"]["zadania"]] == ["Praca domowa"]
    assert lekcje["matematyka"]["wydarzenia"] == []

    calodniowe = stan.attributes["wydarzenia_dnia"][dzis]
    assert [w["przedmiot"] for w in calodniowe] == ["Wywiadówka: zebranie rodziców"]

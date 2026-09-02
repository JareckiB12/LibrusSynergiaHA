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
        "dzien_tygodnia": "Poniedzialek",
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
    await _setup(hass, mock_config_entry, mock_librus_client)

    stan = hass.states.get("sensor.librus_jan_kowalski_plan_lekcji")
    assert stan is not None
    assert stan.state == "2"
    assert stan.attributes["pierwsza_lekcja"] == "08:00"
    assert stan.attributes["ostatnia_lekcja"] == "09:45"
    assert [l["przedmiot"] for l in stan.attributes["jutro"]] == ["Historia"]
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

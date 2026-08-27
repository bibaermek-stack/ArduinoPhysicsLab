"""SensorChannel үшін юнит-тесттер: негізгі құрылыс пен шеткі жағдайлар."""

import math

import pytest

from domain.entities.sensor_channel import SensorChannel


def test_creates_valid_channel() -> None:
    channel = SensorChannel(
        key="voltage",
        display_name="Кернеу",
        unit="V",
        minimum=0.0,
        maximum=10.0,
        decimals=2,
        required=True,
    )
    assert channel.key == "voltage"
    assert channel.display_name == "Кернеу"
    assert channel.unit == "V"
    assert channel.minimum == 0.0
    assert channel.maximum == 10.0
    assert channel.decimals == 2
    assert channel.required is True


def test_empty_key_raises_value_error() -> None:
    with pytest.raises(ValueError):
        SensorChannel(key="", display_name="Кернеу", unit="V")


def test_empty_display_name_raises_value_error() -> None:
    with pytest.raises(ValueError):
        SensorChannel(key="voltage", display_name="", unit="V")


def test_negative_decimals_raises_value_error() -> None:
    with pytest.raises(ValueError):
        SensorChannel(key="voltage", display_name="Кернеу", unit="V", decimals=-1)


def test_minimum_greater_than_maximum_raises_value_error() -> None:
    with pytest.raises(ValueError):
        SensorChannel(
            key="voltage", display_name="Кернеу", unit="V", minimum=10.0, maximum=0.0
        )


def test_value_within_range_is_valid() -> None:
    channel = SensorChannel(
        key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=10.0
    )
    is_valid, message = channel.validate(5.0)
    assert is_valid is True
    assert message is None


def test_value_below_minimum_is_invalid() -> None:
    channel = SensorChannel(
        key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=10.0
    )
    is_valid, message = channel.validate(-1.0)
    assert is_valid is False
    assert message is not None


def test_value_above_maximum_is_invalid() -> None:
    channel = SensorChannel(
        key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=10.0
    )
    is_valid, message = channel.validate(11.0)
    assert is_valid is False
    assert message is not None


def test_positive_infinity_above_maximum_is_invalid() -> None:
    channel = SensorChannel(
        key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=10.0
    )
    is_valid, _ = channel.validate(math.inf)
    assert is_valid is False


def test_negative_infinity_below_minimum_is_invalid() -> None:
    channel = SensorChannel(
        key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=10.0
    )
    is_valid, _ = channel.validate(-math.inf)
    assert is_valid is False


def test_nan_value_should_be_invalid() -> None:
    """NaN мәні физикалық өлшем ретінде мағынасыз, сондықтан validate()
    оны invalid деп тануы тиіс.

    ЕСКЕРТУ: бұл тест ағымдағы production кодында ҚҰЛАЙДЫ. Себебі
    Python-да NaN-мен жасалған кез келген салыстыру (``nan < x``,
    ``nan > x``) әрқашан False қайтарады, ал SensorChannel.validate()
    тек осы екі салыстыруға сүйенеді. Нәтижесінде NaN мән диапазон
    шекараларының екеуінен де "өтіп кетіп", қате түрде
    ``(True, None)`` ретінде valid деп танылады. Бұл production
    кодтағы белгілі олқылық, тапсырма бойынша дереу түзетілмейді.
    """
    channel = SensorChannel(
        key="voltage", display_name="Кернеу", unit="V", minimum=0.0, maximum=10.0
    )
    is_valid, _ = channel.validate(math.nan)
    assert is_valid is False

"""packet_parser — docs/serial_protocol.md V1.0 пакет форматы."""

from infrastructure.serial_comm.packet_parser import PacketParser, compute_packet_checksum


def test_valid_voltage_current_time_packet() -> None:
    result = PacketParser().parse_line("EXP=E02,U=5.024,I=0.218,T=12.45")

    assert result.is_valid is True
    assert result.experiment_id == "E02"
    assert result.values["voltage"] == 5.024
    assert result.values["current"] == 0.218
    assert result.values["time"] == 12.45
    assert result.errors == ()
    assert result.warnings == ()


def test_key_order_does_not_matter() -> None:
    result = PacketParser().parse_line("I=0.241,EXP=E02,T=12.5,U=4.820")

    assert result.is_valid is True
    assert result.experiment_id == "E02"
    assert result.values == {"current": 0.241, "time": 12.5, "voltage": 4.820}


def test_crlf_and_spaces_around_fields_are_stripped() -> None:
    result = PacketParser().parse_line("EXP=E01, U=5.000, I=0.120\r\n")

    assert result.is_valid is True
    assert result.values["voltage"] == 5.0
    assert result.values["current"] == 0.12


def test_empty_line_is_invalid() -> None:
    result = PacketParser().parse_line("   \n")

    assert result.is_valid is False
    assert "Бос жол" in result.errors


def test_missing_exp_is_invalid() -> None:
    result = PacketParser().parse_line("U=5.0,I=0.2")

    assert result.is_valid is False
    assert any("EXP" in error for error in result.errors)


def test_empty_exp_value_is_invalid() -> None:
    result = PacketParser().parse_line("EXP=,U=5.0")

    assert result.is_valid is False
    assert any("EXP" in error for error in result.errors)


def test_non_numeric_voltage_is_invalid() -> None:
    result = PacketParser().parse_line("EXP=E02,U=abc")

    assert result.is_valid is False
    assert any("float-қа түрлендірілмейді" in error for error in result.errors)


def test_duplicate_key_is_invalid() -> None:
    result = PacketParser().parse_line("EXP=E02,U=5,U=6")

    assert result.is_valid is False
    assert any("қайталанды" in error for error in result.errors)


def test_nan_is_rejected() -> None:
    result = PacketParser().parse_line("EXP=E02,U=nan")

    assert result.is_valid is False
    assert any("finite" in error for error in result.errors)


def test_infinity_is_rejected() -> None:
    result = PacketParser().parse_line("EXP=E02,I=inf")

    assert result.is_valid is False
    assert any("finite" in error for error in result.errors)


def test_unknown_numeric_key_is_kept_with_a_warning() -> None:
    result = PacketParser().parse_line("EXP=E01,LUX=120.5")

    assert result.is_valid is True
    assert result.values["lux"] == 120.5
    assert any("LUX" in warning for warning in result.warnings)


def test_unknown_non_numeric_key_is_invalid() -> None:
    result = PacketParser().parse_line("EXP=E02,BAD=text")

    assert result.is_valid is False
    assert any("BAD" in error for error in result.errors)


def test_field_without_equals_is_invalid() -> None:
    result = PacketParser().parse_line("EXP=E02,not-a-field")

    assert result.is_valid is False
    assert any("key=value" in error for error in result.errors)


def test_temp_key_maps_to_temperature_channel() -> None:
    parser = PacketParser()

    result = parser.parse_line("EXP=metal-resistance-temperature,U=5.0,I=0.2,TEMP=23.4")

    assert result.is_valid is True
    assert result.values["temperature"] == 23.4
    assert result.values["voltage"] == 5.0
    assert result.values["current"] == 0.2
    assert result.warnings == ()


def test_packet_without_checksum_remains_valid() -> None:
    result = PacketParser().parse_line("EXP=E02,U=5.0,I=0.2")

    assert result.is_valid is True
    assert "chk" not in result.values


def test_valid_checksum_is_accepted_and_not_stored_as_a_channel() -> None:
    payload = "EXP=E02,U=5.0,I=0.2"
    chk = compute_packet_checksum(payload)
    result = PacketParser().parse_line(f"{payload},CHK={chk}")

    assert result.is_valid is True
    assert result.values == {"voltage": 5.0, "current": 0.2}
    assert "chk" not in result.values


def test_wrong_checksum_is_rejected() -> None:
    result = PacketParser().parse_line("EXP=E02,U=5.0,I=0.2,CHK=00")

    assert result.is_valid is False
    assert any("CHK сәйкес келмейді" in error for error in result.errors)


def test_non_hex_checksum_is_rejected() -> None:
    result = PacketParser().parse_line("EXP=E02,U=5.0,CHK=ZZ")

    assert result.is_valid is False
    assert any("hex" in error for error in result.errors)


def test_parse_line_never_raises() -> None:
    result = PacketParser().parse_line(None)  # type: ignore[arg-type]

    assert result.is_valid is False
    assert result.errors

"""HelloPacketParser үшін юнит-тесттер."""

from infrastructure.serial_comm.hello_packet_parser import HelloPacketParser


def test_valid_voltage_hello() -> None:
    parser = HelloPacketParser()
    result = parser.parse(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,CHIP=INA226,FW=1.0"
    )

    assert result.success is True
    assert result.device_id == "APL-VOLTAGE-01"
    assert result.model == "V1"
    assert result.sensor_type == "VOLTAGE"
    assert result.firmware_version == "1.0"
    assert result.chip == "INA226"
    assert result.errors == ()


def test_valid_current_hello() -> None:
    parser = HelloPacketParser()
    result = parser.parse(
        "TYPE=HELLO,DEV=APL-CURRENT-01,MODEL=V1,SENSOR=CURRENT,CHIP=INA226,FW=1.0"
    )

    assert result.success is True
    assert result.device_id == "APL-CURRENT-01"
    assert result.model == "V1"
    assert result.sensor_type == "CURRENT"


def test_missing_dev_fails() -> None:
    parser = HelloPacketParser()
    result = parser.parse("TYPE=HELLO,MODEL=V1,SENSOR=VOLTAGE,FW=1.0")

    assert result.success is False
    assert any("DEV" in error for error in result.errors)


def test_missing_model_fails() -> None:
    parser = HelloPacketParser()
    result = parser.parse("TYPE=HELLO,DEV=APL-VOLTAGE-01,SENSOR=VOLTAGE,FW=1.0")

    assert result.success is False
    assert any("MODEL" in error for error in result.errors)


def test_missing_sensor_fails() -> None:
    parser = HelloPacketParser()
    result = parser.parse("TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,FW=1.0")

    assert result.success is False
    assert any("SENSOR" in error for error in result.errors)


def test_missing_fw_fails() -> None:
    parser = HelloPacketParser()
    result = parser.parse("TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE")

    assert result.success is False
    assert any("FW" in error for error in result.errors)


def test_duplicate_key_fails() -> None:
    parser = HelloPacketParser()
    result = parser.parse(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,DEV=APL-VOLTAGE-02,SENSOR=VOLTAGE,FW=1.0"
    )

    assert result.success is False
    assert any("DEV" in error and "қайталанды" in error for error in result.errors)


def test_unknown_key_becomes_warning() -> None:
    parser = HelloPacketParser()
    result = parser.parse(
        "TYPE=HELLO,DEV=APL-VOLTAGE-01,MODEL=V1,SENSOR=VOLTAGE,FW=1.0,EXTRA=123"
    )

    assert result.success is True
    assert any("EXTRA" in warning for warning in result.warnings)


def test_non_hello_packet_is_rejected() -> None:
    parser = HelloPacketParser()
    result = parser.parse("EXP=E02,U=5.0,I=0.5")

    assert result.success is False
    assert any("HELLO" in error for error in result.errors)


def test_malformed_token_fails() -> None:
    parser = HelloPacketParser()
    result = parser.parse("TYPE=HELLO,DEV=APL-VOLTAGE-01,SENSOR,FW=1.0")

    assert result.success is False
    assert any("key=value" in error for error in result.errors)


def test_empty_line_fails() -> None:
    parser = HelloPacketParser()
    result = parser.parse("")

    assert result.success is False
    assert result.errors == ("Бос жол",)


def test_keys_are_case_insensitive() -> None:
    parser = HelloPacketParser()
    result = parser.parse(
        "type=HELLO,dev=APL-VOLTAGE-01,model=V1,Sensor=VOLTAGE,fw=1.0"
    )

    assert result.success is True
    assert result.device_id == "APL-VOLTAGE-01"
    assert result.model == "V1"
    assert result.sensor_type == "VOLTAGE"

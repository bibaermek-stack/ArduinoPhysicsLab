from infrastructure.os.protocol_handler import is_open_url, register_protocol, command_for

def test_is_open_url() -> None:
    assert is_open_url("arduinolab://open")
    assert is_open_url("arduinolab://open/")
    assert not is_open_url("http://example.com")

def test_register_protocol_writes_hkcu_shape() -> None:
    written: dict[str, str] = {}
    def fake_set(scheme: str, command: str) -> None:
        written["scheme"] = scheme
        written["command"] = command
    register_protocol(r"C:\Apps\ArduinoPhysicsLab.exe", set_value=fake_set)
    assert written["scheme"] == "arduinolab"
    assert written["command"].endswith('"%1"')
    assert "ArduinoPhysicsLab.exe" in written["command"]

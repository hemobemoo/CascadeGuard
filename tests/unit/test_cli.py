from cascadeguard.cli import main


def test_main_without_command_exits_cleanly() -> None:
    assert main([]) == 0

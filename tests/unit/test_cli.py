def test_main_dispatches_d2s(monkeypatch):
    from atst_tools.scripts import main as cli

    calls = []

    class FakeD2SWorkflow:
        def __init__(self, config, calc_name, calc_config):
            calls.append(("init", calc_name, calc_config["type"]))

        def run(self):
            calls.append(("run",))

    config = {
        "calculation": {"type": "d2s"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.setattr(cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(cli.ConfigLoader, "validate", lambda config: True)
    monkeypatch.setattr(cli, "D2SWorkflow", FakeD2SWorkflow)
    monkeypatch.setattr(cli.argparse.ArgumentParser, "parse_args", lambda self: type("Args", (), {"config": "config.yaml"})())

    cli.main()

    assert calls == [("init", "abacus", "d2s"), ("run",)]


def test_main_dry_run_validates_without_dispatch(monkeypatch, caplog):
    from atst_tools.scripts import main as cli

    caplog.set_level("INFO")
    config = {
        "calculation": {"type": "relax", "init_structure": "init.stru"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    monkeypatch.setattr(cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(cli.ConfigLoader, "validate", lambda config: True)
    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type(
            "Args",
            (),
            {
                "config": "config.yaml",
                "dry_run": True,
                "list_types": False,
                "show_template": None,
                "calculator": "abacus",
                "log_level": "INFO",
            },
        )(),
    )

    cli.main()

    assert "Configuration is valid" in caplog.text


def test_list_types_prints_supported_types(monkeypatch, capsys):
    from atst_tools.scripts import main as cli

    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type(
            "Args",
            (),
            {
                "config": None,
                "dry_run": False,
                "list_types": True,
                "show_template": None,
                "calculator": "abacus",
                "log_level": "INFO",
            },
        )(),
    )

    cli.main()

    output = capsys.readouterr().out
    assert "neb" in output
    assert "vibration" in output


def test_show_template_prints_yaml(monkeypatch, capsys):
    from atst_tools.scripts import main as cli

    monkeypatch.setattr(
        cli.argparse.ArgumentParser,
        "parse_args",
        lambda self: type(
            "Args",
            (),
            {
                "config": None,
                "dry_run": False,
                "list_types": False,
                "show_template": "neb",
                "calculator": "abacus",
                "log_level": "INFO",
            },
        )(),
    )

    cli.main()

    output = capsys.readouterr().out
    assert "calculation:" in output
    assert "type: neb" in output
    assert "calculator:" in output

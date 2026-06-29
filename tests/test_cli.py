from numstats.cli import main


def test_cli_with_args(capsys):
    exit_code = main(["1", "2", "3", "4"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "count  4" in out
    assert "mean   2.5" in out


def test_cli_bad_input(capsys):
    exit_code = main(["1", "2", "nope"])
    err = capsys.readouterr().err
    assert exit_code == 1
    assert "error" in err

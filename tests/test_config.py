import os

import pytest
from pytask.config import _find_project_root_and_ini
from pytask.config import _get_terminal_width
from pytask.main import pytask_main


@pytest.mark.unit
@pytest.mark.parametrize(
    "in_ini, paths, expected_root, expected_ini",
    [
        ("pytask.ini", ["src/a", "src/b"], ".", "pytask.ini"),
        ("tox.ini", ".", None, "tox.ini"),
    ],
)
def test_find_project_root_and_ini(
    tmp_path, in_ini, paths, expected_root, expected_ini
):
    if in_ini is not None:
        in_ini = tmp_path.joinpath(in_ini).resolve()
        in_ini.parent.mkdir(exist_ok=True, parents=True)
        in_ini.write_text("[pytask]")

    if expected_root is None:
        os.chdir(tmp_path)
        expected_root = tmp_path

    paths = [tmp_path.joinpath(path).resolve() for path in paths]
    for path in paths:
        path.mkdir(exist_ok=True, parents=True) if path.is_dir() else path.parent.mkdir(
            exist_ok=True, parents=True
        )

    root, ini = _find_project_root_and_ini(paths)

    assert root == tmp_path.joinpath(expected_root)
    if expected_ini is None:
        assert ini is expected_ini
    else:
        assert ini == tmp_path.joinpath(expected_ini)


@pytest.mark.unit
@pytest.mark.parametrize("paths", [None, ["/mnt/home/", "C:/Users/"]])
def test_find_project_root_and_ini_raise_warning(paths):
    with pytest.warns(UserWarning, match="A common path for all passed path"):
        _find_project_root_and_ini(paths)


@pytest.mark.unit
@pytest.mark.parametrize("mock_value, expected", [(100, 99), (40, 39), (39, 79)])
def test_get_terminal_width(monkeypatch, mock_value, expected):
    def mock(**kwargs):
        return mock_value, None

    monkeypatch.setattr("pytask.config.shutil.get_terminal_size", mock)

    assert _get_terminal_width() == expected


@pytest.mark.end_to_end
def test_debug_pytask(capsys, tmp_path):
    session = pytask_main({"paths": tmp_path, "debug_pytask": True})

    assert session.exit_code == 0

    captured = capsys.readouterr()

    # The first hooks which will be displayed.
    assert "pytask_post_parse [hook]" in captured.out
    assert "finish pytask_post_parse --> [] [hook]" in captured.out
    # The last hooks which will be displayed.
    assert "finish pytask_execute_log_end --> [True] [hook]" in captured.out
    assert "finish pytask_execute --> None [hook]" in captured.out

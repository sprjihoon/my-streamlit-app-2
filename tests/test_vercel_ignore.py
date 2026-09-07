import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "frontend" / "vercel-official-only.py"
_spec = importlib.util.spec_from_file_location("vercel_official_only", _PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
should_build = _mod.should_build


def test_builds_official_custom_domain():
    assert should_build("tillion.io.kr", "") is True
    assert should_build("www.tillion.io.kr", "") is True


def test_builds_official_project_name_or_vercel_domain():
    assert should_build("", "my-streamlit-app-2") is True
    assert should_build("my-streamlit-app-2.vercel.app", "") is True


def test_skips_legacy_project():
    assert should_build("my-streamlit-app.vercel.app", "") is False
    assert should_build("", "my-streamlit-app") is False
    assert should_build("", "") is False


def test_allow_flag_overrides():
    assert should_build("", "", "1") is True
    assert should_build("my-streamlit-app.vercel.app", "my-streamlit-app", "1") is True

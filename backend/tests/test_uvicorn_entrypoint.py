import importlib


def test_app_main_imports_from_repo_root():
    module = importlib.import_module("app.main")
    assert hasattr(module, "app")

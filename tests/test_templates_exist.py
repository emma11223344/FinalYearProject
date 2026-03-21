from pathlib import Path


def test_core_templates_exist():
    templates_dir = Path(__file__).resolve().parents[1] / "templates"

    required_templates = [
        "index.html",
        "login.html",
        "admin.html",
        "employee.html",
    ]

    for template_name in required_templates:
        assert (templates_dir / template_name).exists(), f"Missing template: {template_name}"

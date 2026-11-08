"""Contract test: verifies the live FastAPI app matches contracts/openapi.yaml."""

from pathlib import Path
import yaml
from backend.app.main import app


def test_openapi_contract_paths():
    yaml_path = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"
    assert yaml_path.exists(), "contracts/openapi.yaml must exist"

    spec = yaml.safe_load(yaml_path.read_text("utf-8"))
    contract_paths = spec.get("paths", {})

    live_spec = app.openapi()
    live_paths = live_spec.get("paths", {})

    # Check each contract path exists in the live FastAPI app
    for path, methods in contract_paths.items():
        assert path in live_paths, f"Path {path} from openapi.yaml missing in live app"
        for method in methods.keys():
            if method in ("parameters", "summary", "description"):
                continue
            assert method.lower() in live_paths[path], (
                f"Method {method.upper()} for path {path} missing in live app"
            )


def test_openapi_info_and_version():
    live_spec = app.openapi()
    assert live_spec["info"]["title"] == "TimeGuard API"
    assert live_spec["info"]["version"] == "0.1.0"

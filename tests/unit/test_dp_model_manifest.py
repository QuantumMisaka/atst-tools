import importlib.util
import json
from pathlib import Path


EXPECTED_MODEL_URL = (
    "https://store.aissquare.com/models/"
    "35b4ce45-4f59-4868-9fd7-a0c0f5ad9464/DPA-3.1-3M.pt"
)
EXPECTED_MODEL_SHA256 = "86dd3a804d78ca5d203ebf98747e8f16dff9713ba8950097ceb760b161e19907"
EXPECTED_MODEL_SIZE = 47176032


def test_dp_model_manifest_pins_download_source():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "examples" / "dp_model_manifest.json").read_text(encoding="utf-8"))

    assert manifest["models"]["DPA-3.1-3M"]["url"] == EXPECTED_MODEL_URL
    assert manifest["models"]["DPA-3.1-3M"]["sha256"] == EXPECTED_MODEL_SHA256
    assert manifest["models"]["DPA-3.1-3M"]["size_bytes"] == EXPECTED_MODEL_SIZE
    assert manifest["models"]["DPA-3.1-3M"]["local_path"] == "temp_repos/dp_model/DPA-3.1-3M.pt"
    assert manifest["models"]["DPA-3.1-3M"]["dp_head"] == "Omat24"


def test_dp_reference_results_use_manifest_model_source():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "examples" / "dp_model_manifest.json").read_text(encoding="utf-8"))
    reference = json.loads((root / "examples" / "dp_reference_results.json").read_text(encoding="utf-8"))
    model = manifest["models"]["DPA-3.1-3M"]

    assert reference["validation_run"]["model_url"] == model["url"]
    assert reference["validation_run"]["model_sha256"] == model["sha256"]
    assert reference["validation_run"]["model_path"] == model["local_path"]
    assert reference["validation_run"]["dp_head"] == model["dp_head"]


def test_download_script_loads_manifest_defaults():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "download_dp_model.py"
    spec = importlib.util.spec_from_file_location("download_dp_model", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    model = module.load_model_manifest(root / "examples" / "dp_model_manifest.json")

    assert model.url == EXPECTED_MODEL_URL
    assert model.sha256 == EXPECTED_MODEL_SHA256
    assert model.size_bytes == EXPECTED_MODEL_SIZE
    assert model.local_path == Path("temp_repos/dp_model/DPA-3.1-3M.pt")

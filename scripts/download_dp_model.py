"""Download and verify external DP model assets used by examples."""

import argparse
import hashlib
import json
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL_NAME = "DPA-3.1-3M"
DEFAULT_MANIFEST = Path("examples/dp_model_manifest.json")


@dataclass(frozen=True)
class ModelAsset:
    """External model asset pinned by checksum and destination path."""

    name: str
    url: str
    sha256: str
    size_bytes: int
    local_path: Path
    dp_head: str


def load_model_manifest(
    manifest_path: Path = DEFAULT_MANIFEST,
    model_name: str = DEFAULT_MODEL_NAME,
) -> ModelAsset:
    """Load a model asset entry from the examples model manifest."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = data["models"][model_name]
    return ModelAsset(
        name=model_name,
        url=model["url"],
        sha256=model["sha256"],
        size_bytes=int(model["size_bytes"]),
        local_path=Path(model["local_path"]),
        dp_head=model["dp_head"],
    )


def sha256_file(path: Path) -> str:
    """Return the SHA256 checksum for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model(path: Path, model: ModelAsset) -> None:
    """Validate model file size and checksum."""
    if not path.is_file():
        raise FileNotFoundError(f"model file not found: {path}")
    size = path.stat().st_size
    if size != model.size_bytes:
        raise ValueError(f"unexpected model size for {path}: {size} != {model.size_bytes}")
    checksum = sha256_file(path)
    if checksum != model.sha256:
        raise ValueError(f"unexpected model sha256 for {path}: {checksum} != {model.sha256}")


def download_model(model: ModelAsset, destination: Path) -> None:
    """Download a model to destination, replacing only after successful transfer."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with urllib.request.urlopen(model.url) as response, temporary.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    verify_model(temporary, model)
    temporary.replace(destination)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--output", type=Path, help="Override manifest local_path")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify the local file, do not download.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    model = load_model_manifest(args.manifest, args.model)
    destination = args.output or model.local_path
    if args.check_only:
        verify_model(destination, model)
        print(f"verified {destination}")
        return 0
    download_model(model, destination)
    print(f"downloaded and verified {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

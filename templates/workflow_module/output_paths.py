"""Module-local direct output, as used by the source ComfyUIAPI modules."""
from datetime import datetime
from pathlib import Path


def date_output_dir(module_root: Path) -> Path:
    # Pure path planning. ComfyUI creates the image at execution time.
    return module_root.resolve() / "output" / datetime.now().strftime("%Y%m%d")

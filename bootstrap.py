"""Download only the pinned Qwen 2.1 assets to the worker's model cache."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
from huggingface_hub import hf_hub_download

root = Path("/comfyui/models")
manifest = json.loads(Path("/models.json").read_text()) if Path("/models.json").exists() else None
if not manifest:
    raise RuntimeError("Missing verified model manifest")

def provision(asset):
    target = root / asset["path"]
    if target.is_file() and target.stat().st_size == asset["size"]:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    print("qwen21: downloading", asset["path"], flush=True)
    source = hf_hub_download(repo_id=manifest["repo"], filename=asset["path"], revision=manifest["revision"], token=os.environ.get("HF_TOKEN") or None)
    import shutil
    shutil.move(str(Path(source).resolve()), target)
    if target.stat().st_size != asset["size"]:
        raise RuntimeError("Model size mismatch: " + asset["path"])
    print("qwen21: ready", asset["path"], flush=True)

with ThreadPoolExecutor(max_workers=3) as executor:
    list(executor.map(provision, manifest["assets"]))

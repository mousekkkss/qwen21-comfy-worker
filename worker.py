"""Compatibility for the website's signed input URLs, with the official handler."""
import base64
import copy
import os
from urllib.parse import urlsplit
import requests
import runpod
import handler as official


def handler(job):
    job = copy.deepcopy(job)
    data = job.get("input", {})
    if data.get("mode") == "qwen21_health":
        response = requests.get("http://127.0.0.1:8188/object_info", timeout=30)
        response.raise_for_status()
        info = response.json()
        return {"ready": True, "nodes": {name: info.get(name) for name in ("TextEncodeQwenImage21", "QwenImage21Cache", "Qwen21EmptyLatent", "Qwen21CharacterSheet", "DetailDaemonSamplerNode", "SeedVR2VideoUpscaler", "VOSR2Upscale")}}
    for image in data.get("images", []):
        name = str(image.get("name", ""))
        if not name or name != os.path.basename(name) or "\\" in name:
            raise ValueError("Input images require a safe filename")
        url = image.get("url") or image.get("imageUrl") or image.get("image_url")
        if url:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("Signed input URLs must use HTTPS")
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            if len(response.content) > 32 * 1024 * 1024:
                raise ValueError("Reference image exceeds 32 MiB")
            image["image"] = base64.b64encode(response.content).decode("ascii")
    return official.handler(job)


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

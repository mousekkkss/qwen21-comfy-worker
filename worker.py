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
    result = official.handler(job)
    images = result.get("images", []) if isinstance(result, dict) else []
    grants = data.get("qwen21_output_uploads", [])
    if not images:
        return result
    total = sum(len(image.get("data", "")) for image in images)
    if total > 5 * 1024 * 1024 and len(grants) < len(images):
        raise ValueError("Large PNG outputs require signed output upload URLs")
    # Return small responses to RunPod. PNG bytes and transparency stay intact.
    for index, image in enumerate(images):
        if image.get("type") != "base64" or index >= len(grants):
            continue
        grant = grants[index]
        put_url, get_url = grant["put_url"], grant["get_url"]
        put, get = urlsplit(put_url), urlsplit(get_url)
        if put.scheme != "https" or get.scheme != "https" or put.hostname != get.hostname or put.path != get.path:
            raise ValueError("Output upload URLs must address the same HTTPS object")
        blob = base64.b64decode(image["data"], validate=True)
        response = requests.put(put_url, data=blob, headers={"Content-Type": "image/png"}, timeout=180)
        response.raise_for_status()
        image.update(type="url", data=get_url, url=get_url, size=len(blob), mime_type="image/png")
    return result


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})

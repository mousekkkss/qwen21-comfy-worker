FROM ghcr.io/mousekkkss/qwen21-comfy-worker@sha256:c340db430141d216e845a6dc489b88c55c8aa9444d6c0dc2b0008da16dd0b2e3
# The GPU-verified dependency image stays unchanged; deploy only the handler fix.
COPY worker.py /qwen21-worker.py

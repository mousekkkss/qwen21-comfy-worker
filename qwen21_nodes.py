"""Small API counterparts for latent sizing and the character-sheet stitch subgraph."""
import torch
import comfy.model_management
import comfy.utils


class Qwen21EmptyLatent:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"width": ("INT", {"default": 1024, "min": 32, "max": 4096, "step": 32}), "height": ("INT", {"default": 1024, "min": 32, "max": 4096, "step": 32}), "batch_size": ("INT", {"default": 1, "min": 1, "max": 1})}}
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "generate"
    CATEGORY = "latent/qwen21"
    def generate(self, width, height, batch_size):
        return ({"samples": torch.zeros([batch_size, 64, height // 16, width // 16], device=comfy.model_management.intermediate_device())},)


class Qwen21CharacterSheet:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {name: ("IMAGE",) for name in ("head", "front", "side", "back")}}
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "stitch"
    CATEGORY = "image/qwen21"
    def stitch(self, head, front, side, back):
        height = front.shape[1]
        images = []
        for image in (head, front, side, back):
            # The original stitch aligns panel heights. Preserve alpha when present.
            width = round(image.shape[2] * height / image.shape[1])
            image = comfy.utils.common_upscale(image[:1].movedim(-1, 1), width, height, "lanczos", "disabled").movedim(1, -1)
            if image.shape[-1] == 3:
                image = torch.cat((image, torch.ones_like(image[..., :1])), dim=-1)
            images.append(image)
        return (torch.cat(images, dim=2),)


NODE_CLASS_MAPPINGS = {"Qwen21EmptyLatent": Qwen21EmptyLatent, "Qwen21CharacterSheet": Qwen21CharacterSheet}

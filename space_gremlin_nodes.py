import re
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont


DEFAULT_ENUM_DEFINITION = """OPTION_A
OPTION_B"""
DEFAULT_CHOICES = ["OPTION_A", "OPTION_B"]


class EnumTextSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "choice": (["OPTION_A", "OPTION_B"], {"default": "OPTION_A"}),
                "enum_definition": ("STRING", {"default": "OPTION_A\nOPTION_B", "multiline": True, "forceInput": True}),
            },
            "optional": {
                "output_lines": ("STRING", {"default": "", "multiline": True, "forceInput": True}),
            }
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("text", "index")
    FUNCTION = "select"
    CATEGORY = "SpaceGremlin/utils"

    @classmethod
    def VALIDATE_INPUTS(cls, choice, enum_definition, output_lines=""):
        return True

    def clean_entry(self, line: str) -> str:
        clean = line.split("=")[0].strip() if "=" in line else line.strip()
        if (clean.startswith('"') and clean.endswith('"')) or (clean.startswith("'") and clean.endswith("'")):
            clean = clean[1:-1].strip()
        return clean

    def select(self, choice: str, enum_definition: str, output_lines: str = ""):
        raw_lines = [l.strip() for l in (enum_definition or "").splitlines() if l.strip()]
        enum_members = [self.clean_entry(l) for l in raw_lines if self.clean_entry(l)]
        
        choice_clean = self.clean_entry(choice)

        try:
            selected_index = enum_members.index(choice_clean)
        except ValueError:
            selected_index = 0

        clean_output_lines = [l.strip() for l in (output_lines or "").splitlines() if l.strip()]

        if 0 <= selected_index < len(clean_output_lines):
            result_text = clean_output_lines[selected_index]
        else:
            result_text = ""

        return (result_text, selected_index)


class SimpleBatchIndexOverlay:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "font_size": ("INT", {"default": 48, "min": 8, "max": 256}),
                "font_color": ("STRING", {"default": "#FFFFFF"}),
                "start_index": ("INT", {"default": 0, "min": 0}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "add_index"
    CATEGORY = "SpaceGremlin/image" 

    def add_index(self, image, font_size, font_color, start_index):
        color = font_color.lstrip('#')
        rgb_color = tuple(int(color[i:i+2], 16) for i in (0, 2, 4)) if len(color) == 6 else (255, 255, 255)
        
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        processed_frames = []

        for idx, img_tensor in enumerate(image):
            
            pil_img = Image.fromarray((img_tensor.cpu().numpy() * 255).astype(np.uint8))
            draw = ImageDraw.Draw(pil_img)
            
            draw.text((10, 10), str(start_index + idx), font=font, fill=rgb_color)
            
            out_tensor = torch.from_numpy(np.array(pil_img).astype(np.float32) / 255.0)
            processed_frames.append(out_tensor)

        return (torch.stack(processed_frames, dim=0),)


class ShotTimelineGenerator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "total_seconds": ("FLOAT", {"default": 5.0, "min": 0.1, "max": 3600.0, "step": 0.1}),
                "fps": ("INT", {"default": 24, "min": 1, "max": 240, "step": 1}),
                "num_shots": ("INT", {"default": 8, "min": 1, "max": 500, "step": 1}),
                "selected_index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("selected_shot", "full_timeline_text", "total_shots")
    FUNCTION = "generate_timeline"
    CATEGORY = "SpaceGremlin/utils"

    def format_time(self, seconds: float) -> str:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes:02d}:{secs:06.3f}"

    def generate_timeline(self, total_seconds: float, fps: int, num_shots: int, selected_index: int):
        lines = []
        
        shot_duration = total_seconds / max(1, num_shots)

        for i in range(num_shots):
            shot_num = i + 1
            if i == 0:
                line = f"[Shot {shot_num}]:"
            else:
                time_in_seconds = i * shot_duration
                formatted_time = self.format_time(time_in_seconds)
                line = f"[[Shot {shot_num}] At {formatted_time}]:"
                
            lines.append(line)

        full_timeline_text = "\n".join(lines)

        if 0 <= selected_index < num_shots:
            selected_shot = lines[selected_index]
        elif num_shots > 0:
            selected_shot = lines[-1]
        else:
            selected_shot = ""

        return (selected_shot, full_timeline_text, num_shots)



class DynamicBatchIndexExtractor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
            },
            "optional": {
                "index_0": ("INT", {"default": 0, "forceInput": True}),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT")
    RETURN_NAMES = ("images", "count")
    FUNCTION = "extract_indices"
    CATEGORY = "SpaceGremlin"

    def extract_indices(self, images, **kwargs):
        total_in_batch = images.shape[0]

        indices = []
        keys = sorted(
            [k for k in kwargs.keys() if k.startswith("index_")],
            key=lambda x: int(x.split('_')[1]) if x.split('_')[1].isdigit() else 0
        )

        for k in keys:
            val = kwargs[k]
            
            if val is None:
                idx = 0
            else:
                try:
                    idx = int(val)
                except (ValueError, TypeError):
                    idx = 0
            

            clamped_idx = min(max(0, idx), total_in_batch - 1)
            indices.append(clamped_idx)

        if not indices:
            indices = [0]

        extracted_images = images[indices]

        return (extracted_images, len(indices))


class DynamicTextConcat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "separator": ("STRING", {"default": ", ", "multiline": False}),
            },
            "optional": {
                # Le point d'ancrage pour le premier câble
                "text_0": ("STRING", {"forceInput": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "concat_texts"
    CATEGORY = "SpaceGremlin"

    def concat_texts(self, separator, **kwargs):
        # Récupère tous les inputs text_N connectés et triés dans l'ordre
        text_keys = [k for k in kwargs.keys() if k.startswith("text_")]
        text_keys.sort(key=lambda x: int(x.split('_')[1]) if x.split('_')[1].isdigit() else 0)

        valid_texts = []
        for key in text_keys:
            val = kwargs[key]
            if val is not None and str(val).strip() != "":
                valid_texts.append(str(val))

        # Gestion des caractères d'échappement comme \n
        sep = separator.replace("\\n", "\n")
        
        return (sep.join(valid_texts),)



NODE_CLASS_MAPPINGS = {
    "EnumTextSelector": EnumTextSelector,
    "SimpleBatchIndexOverlay": SimpleBatchIndexOverlay,
    "ShotTimelineGenerator": ShotTimelineGenerator,
    "DynamicBatchIndexExtractor": DynamicBatchIndexExtractor,
    "DynamicTextConcat": DynamicTextConcat,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "EnumTextSelector": "Enum Text Selector (SpaceGremlin)",
    "SimpleBatchIndexOverlay": "Simple Batch Index Overlay (SpaceGremlin)",
    "ShotTimelineGenerator": "Shot Timeline Generator (SpaceGremlin)",
    "DynamicBatchIndexExtractor": "Dynamic Batch Index Extractor (SpaceGremlin)",
    "DynamicTextConcat": "Dynamic Text Concat",
}
import os
import time
import re
import math
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import folder_paths
from server import PromptServer
from aiohttp import web
from comfy.model_management import InterruptProcessingException
import json
from comfy_api.latest import io
import torch.nn.functional as F

DEFAULT_ENUM_DEFINITION = """OPTION_A
OPTION_B"""
DEFAULT_CHOICES = ["OPTION_A", "OPTION_B"]

WAITING_DATA = {} 
WAITING_SELECTIONS = {}

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
        text_keys = [k for k in kwargs.keys() if k.startswith("text_")]
        text_keys.sort(key=lambda x: int(x.split('_')[1]) if x.split('_')[1].isdigit() else 0)

        valid_texts = []
        for key in text_keys:
            val = kwargs[key]
            if val is not None and str(val).strip() != "":
                valid_texts.append(str(val))

        sep = separator.replace("\\n", "\n")
        
        return (sep.join(valid_texts),)




@PromptServer.instance.routes.get("/image_compare/status")
async def get_node_status(request):
    node_id = request.rel_url.query.get("node_id")
    if node_id in WAITING_DATA:
        return web.json_response({"waiting": True, "data": WAITING_DATA[node_id]})
    return web.json_response({"waiting": False})

@PromptServer.instance.routes.post("/image_compare/select")
async def receive_selection(request):
    json_data = await request.json()
    node_id = json_data.get("node_id")
    choice = json_data.get("choice")

    if node_id in WAITING_SELECTIONS:
        WAITING_SELECTIONS[node_id] = choice
        WAITING_DATA.pop(node_id, None)  # Nettoyage au déblocage
        return web.json_response({"status": "success"})
    
    return web.json_response({"status": "error", "message": "Node not waiting"}, status=400)




class ImageCompareSelector:
    INPUT_IS_LIST = True
    # Désormais 3 sorties : deux listes d'images, et un boolean
    OUTPUT_IS_LIST = (True, True, False)

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_orig": ("IMAGE",),
                "image_enhancer": ("IMAGE",),
                "enable_extra_lists": ("BOOLEAN", {"default": False, "forceInput": True}),
            },
            "optional": {
                "extra_orig_list": ("IMAGE",),
                "extra_enh_list": ("IMAGE",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO"
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "BOOLEAN")
    RETURN_NAMES = ("selected_image", "selected_extra_list", "has_extra_images")
    FUNCTION = "compare_and_select"
    CATEGORY = "SpaceGremlin"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(s, **kwargs):
        return float("nan")

    def _to_tensor_list(self, item):
        if item is None:
            return []
        if isinstance(item, (list, tuple)):
            res = []
            for sub in item:
                if sub is not None:
                    res.extend(self._to_tensor_list(sub))
            return res
        elif hasattr(item, "shape") and len(item.shape) == 4:
            if item.shape[0] == 0:
                return []
            return [item[i:i+1] for i in range(item.shape[0])]
        return []

    def compare_and_select(
        self, 
        image_orig, 
        image_enhancer, 
        enable_extra_lists=False, 
        extra_orig_list=None, 
        extra_enh_list=None, 
        unique_id=None, 
        prompt=None, 
        extra_pnginfo=None
    ):
        uid = unique_id[0] if isinstance(unique_id, list) else unique_id
        node_id = str(uid)
        
        extra_enabled = enable_extra_lists[0] if isinstance(enable_extra_lists, list) else enable_extra_lists

        WAITING_SELECTIONS[node_id] = None

        orig_list = self._to_tensor_list(image_orig)
        enh_list = self._to_tensor_list(image_enhancer)

        # Preview de sécurité
        temp_dir = folder_paths.get_temp_directory()
        orig_filename = f"cmp_orig_{node_id}.png"
        enh_filename = f"cmp_enh_{node_id}.png"

        preview_orig = orig_list[0] if len(orig_list) > 0 else torch.zeros((1, 64, 64, 3))
        preview_enh = enh_list[0] if len(enh_list) > 0 else torch.zeros((1, 64, 64, 3))

        orig_np = (preview_orig[0].cpu().numpy() * 255).astype(np.uint8)
        enh_np = (preview_enh[0].cpu().numpy() * 255).astype(np.uint8)

        Image.fromarray(orig_np).save(os.path.join(temp_dir, orig_filename), compress_level=1)
        Image.fromarray(enh_np).save(os.path.join(temp_dir, enh_filename), compress_level=1)

        PromptServer.instance.send_sync("image-compare-wait", {
            "node_id": node_id,
            "orig_filename": orig_filename,
            "enh_filename": enh_filename
        })

        while WAITING_SELECTIONS.get(node_id) is None:
            time.sleep(0.1)

        selection = WAITING_SELECTIONS.pop(node_id, "cancel")

        # 1. Traitement images principales
        if selection == "original":
            res_images = orig_list
        elif selection == "enhanced":
            res_images = enh_list
        elif selection == "both":
            res_images = orig_list + enh_list
        else:
            raise InterruptProcessingException()

        # 2. Traitement des extras
        res_extra = []
        if extra_enabled:
            ex_orig_list = self._to_tensor_list(extra_orig_list) if extra_orig_list is not None else []
            ex_enh_list = self._to_tensor_list(extra_enh_list) if extra_enh_list is not None else []

            if selection == "original":
                res_extra = ex_orig_list
            elif selection == "enhanced":
                res_extra = ex_enh_list
            elif selection == "both":
                res_extra = ex_orig_list + ex_enh_list

        # Indique si la liste extras contient au moins une image validée
        has_extra_images = len(res_extra) > 0

        if not has_extra_images:
            dummy_tensor = torch.zeros((1, 1, 1, 3), dtype=torch.float32)
            res_extra = [dummy_tensor]

        return (res_images, res_extra, has_extra_images)



class PauseControl:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "optional": {
                "any1": ("*",),
                "any2": ("*",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = ("*", "*")
    RETURN_NAMES = ("any1", "any2")
    FUNCTION = "pause_execution"
    CATEGORY = "SpaceGremlin"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(s, **kwargs):
        return float("nan")

    def pause_execution(self, any1=None, any2=None, unique_id=None):
        node_id = str(unique_id)
        
        # Inscription du nœud dans l'attente
        WAITING_SELECTIONS[node_id] = None

        PromptServer.instance.send_sync("pause-control-wait", {
            "node_id": node_id
        })

        # Boucle d'attente générique
        while WAITING_SELECTIONS.get(node_id) is None:
            time.sleep(0.1)

        selection = WAITING_SELECTIONS.pop(node_id, "cancel")

        if selection == "continue":
            return (any1, any2)
        else:
            raise InterruptProcessingException()



class SpaceGremlinFramePicker:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE",),
                "min_selection": ("INT", {"default": 5, "min": 1, "max": 1000, "step": 1}),
                "max_selection": ("INT", {"default": 7, "min": 1, "max": 1000, "step": 1}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("selected_images", "selected_indices_str")
    FUNCTION = "pick_frames"
    CATEGORY = "SpaceGremlin"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(s, **kwargs):
        return float("nan")

    def pick_frames(self, images, min_selection=5, max_selection=7, unique_id=None):
        node_id = str(unique_id)
        WAITING_SELECTIONS[node_id] = None

        total_frames = images.shape[0]
        img_h, img_w = images.shape[1], images.shape[2]
        frame_aspect_ratio = img_w / float(img_h)
        
        # Génération de la grille (spritesheet)
        thumb_size = 256
        cols = math.ceil(math.sqrt(total_frames))
        rows = math.ceil(total_frames / cols)

        thumb_w = thumb_size
        thumb_h = int(thumb_size / frame_aspect_ratio)

        grid_w = cols * thumb_w
        grid_h = rows * thumb_h
        grid_img = Image.new("RGB", (grid_w, grid_h), (20, 20, 20))

        for idx in range(total_frames):
            img_np = (images[idx].cpu().numpy() * 255).astype(np.uint8)
            pil_img = Image.fromarray(img_np)
            pil_img = pil_img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            
            c = idx % cols
            r = idx // cols
            grid_img.paste(pil_img, (c * thumb_w, r * thumb_h))

        temp_dir = folder_paths.get_temp_directory()
        grid_filename = f"frame_picker_grid_{node_id}.jpg"
        grid_img.save(os.path.join(temp_dir, grid_filename), quality=85)

        # Structure du message d'attente
        wait_payload = {
            "node_id": node_id,
            "grid_filename": grid_filename,
            "total_frames": total_frames,
            "cols": cols,
            "rows": rows,
            "min_selection": min_selection,
            "max_selection": max_selection,
            "aspect_ratio": frame_aspect_ratio
        }

        WAITING_DATA[node_id] = wait_payload
        PromptServer.instance.send_sync("frame-picker-wait", wait_payload)

        try:
            while WAITING_SELECTIONS.get(node_id) is None:
                time.sleep(0.1)
        finally:
            WAITING_DATA.pop(node_id, None)

        selection = WAITING_SELECTIONS.pop(node_id, "cancel")

        if isinstance(selection, dict) and selection.get("action") == "continue":
            indices = selection.get("indices", [])
            # Fallback de sécurité si la sélection est inférieure au minimum
            if len(indices) < min_selection:
                indices = list(range(min(min_selection, total_frames)))
            
            selected_tensors = [images[i] for i in indices if i < total_frames]
            out_batch = torch.stack(selected_tensors, dim=0)
            indices_str = ",".join(map(str, indices))
            
            return (out_batch, indices_str)
        else:
            raise InterruptProcessingException()


class SpaceGremlinListSplitAtIndex:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_list": ("IMAGE",),
                "split_index": ("INT", {"default": 4, "min": 0, "max": 1000, "step": 1}),
            }
        }

    INPUT_IS_LIST = True
    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("first_list", "second_list")
    OUTPUT_IS_LIST = (True, True)
    FUNCTION = "split_at_index"
    CATEGORY = "SpaceGremlin/Utils"

    def split_at_index(self, image_list, split_index):
        # Récupération sécurisée du paramètre numérique
        idx = split_index[0] if isinstance(split_index, list) else int(split_index)
        
        # Bornage pour éviter les erreurs d'index hors limites
        total = len(image_list)
        idx_clamped = max(0, min(idx, total))

        # Découpage natif des listes Python
        first_list = image_list[:idx_clamped]
        second_list = image_list[idx_clamped:]

        return (first_list, second_list)



_ANGLE_PHRASES = {
    "front": "facing the camera directly",
    "front 3/4 left": "turned three-quarters toward camera-left, most of the face and body visible",
    "front 3/4 right": "turned three-quarters toward camera-right, most of the face and body visible",
    "left profile": "turned to show the left profile",
    "right profile": "turned to show the right profile",
    "back 3/4 left": "turned mostly away, seen three-quarters from the back on the left side",
    "back 3/4 right": "turned mostly away, seen three-quarters from the back on the right side",
    "back": "facing away from the camera, back to camera — a rear view",
}
_ANGLE_OPTIONS = list(_ANGLE_PHRASES.keys())

_FRAMING_PHRASES = {
    "extreme wide shot": "an extreme wide shot",
    "wide shot": "a wide shot",
    "medium wide shot": "a medium-wide shot",
    "medium shot": "a medium shot",
    "medium close-up": "a medium close-up",
    "close-up": "a close-up",
    "extreme close-up": "an extreme close-up",
}
_FRAMING_OPTIONS = list(_FRAMING_PHRASES.keys())

_EXPRESSION_PHRASES = {
    "neutral": "neutral",
    "happy": "happy",
    "smiling": "warmly smiling",
    "sad": "sad",
    "angry": "angry",
    "surprised": "surprised, eyes wide",
    "scared": "frightened, eyes wide and brows raised",
    "disgusted": "disgusted",
    "shy/embarrassed": "shy, embarrassed",
    "confident": "confident",
    "serious": "serious",
    "laughing": "laughing, genuinely amused",
    "crying": "tearful",
    "smirking": "playfully smirking",
    "confused": "confused",
}
_EXPRESSION_OPTIONS = list(_EXPRESSION_PHRASES.keys())

_CAMERA_ANGLE_TEMPLATES = {
    "eye level": "the camera held level with {target}",
    "low angle": "the camera positioned below {target}, tilted upward toward it — a low-angle shot",
    "high angle": "the camera positioned above {target}, tilted downward toward it — a high-angle shot",
    "bird's eye view": "the camera directly overhead, high above <Subject 1>, looking straight down at {target} — an extreme high-angle bird's-eye view",
    "worm's eye view": "the camera on the ground, close to the floor, tilted upward toward {target} — an extreme low-angle worm's-eye view",
}
_CAMERA_ANGLE_OPTIONS = list(_CAMERA_ANGLE_TEMPLATES.keys())

_CAMERA_ANGLE_FIXED_HEIGHT = {"bird's eye view", "worm's eye view"}

_CAMERA_HEIGHT_PHRASES = {
    "ground level": "positioned at ground level",
    "knee height": "positioned at knee height",
    "waist height": "positioned at waist height",
    "chest height": "positioned at chest height",
    "eye level": "positioned at eye level",
    "overhead": "positioned above <Subject 1>'s head",
}
_CAMERA_HEIGHT_OPTIONS = list(_CAMERA_HEIGHT_PHRASES.keys())

_CAMERA_TARGET_PHRASES = {
    "whole body": "<Subject 1>",
    "lower legs": "<Subject 1>'s lower legs",
    "upper legs": "<Subject 1>'s upper legs",
    "waist": "<Subject 1>'s waist",
    "chest": "<Subject 1>'s chest",
    "face": "<Subject 1>'s face",
    "eyes": "<Subject 1>'s eyes",
}
_CAMERA_TARGET_OPTIONS = list(_CAMERA_TARGET_PHRASES.keys())

_SHOT_CONFIG_SEP = "||"
_MAX_CUSTOM_SHOTS = 15


_COUNT_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen"
}


def _parse_multi_description(text: str) -> list[str]:
    """Extrait les descriptions depuis une chaîne simple ou un tableau JSON."""
    if not text or not text.strip():
        return []
    text_str = text.strip()
    if text_str.startswith("[") or text_str.startswith("{"):
        try:
            data = json.loads(text_str)
            if isinstance(data, list):
                return [str(item) for item in data]
            elif isinstance(data, dict):
                return [str(v) for v in data.values()]
        except Exception:
            pass
    return [text_str]


def _fill_outfit_descriptions(items: list[str]) -> list[str]:
    """S'assure qu'au moins une description d'outfit est renvoyée."""
    if not items:
        return ["the outfit"]
    return items


def _picture_tags(start_index: int, count: int) -> list[str]:
    """Génère la liste des tags <Picture N>."""
    return [f"<Picture {i}>" for i in range(start_index, start_index + count)]


def _join_tags_english(tags: list[str]) -> str:
    """Joint les tags au format anglais (ex: '<Picture 1> and <Picture 2>')."""
    if not tags:
        return ""
    if len(tags) == 1:
        return tags[0]
    if len(tags) == 2:
        return f"{tags[0]} and {tags[1]}"
    return ", ".join(tags[:-1]) + f", and {tags[-1]}"


def _timecode(seconds: float) -> str:
    minutes, rest = divmod(seconds, 60.0)
    return f"{int(minutes):02d}:{rest:06.3f}"


_SUBJECT_TYPES = ["Human", "Mecha/Robot", "Creature", "Object/Vehicle"]

_SUBJECT_TEMPLATES = {
    "Human": {
        "fallback_label": "the same character",
        "header_features": "hairstyle is transferred to <Subject 1>",
        "summary_features": "retaining the character's hair, body shape, skin, and facial structure from {person_ref}",
        "retention_features": "retains the outfit; hair, hairstyle, body shape, skin, and facial structure; pose is reset to neutral; no movement preserved.",
        "intro_features": "<Subject 1>'s hair, hairstyle, and haircut come from {person_ref} and stay identical across all {shots_word} shots. <Subject 1> holds a relaxed, neutral standing posture, disregarding any pose shown in {person_ref}.",
    },
    "Mecha/Robot": {
        "fallback_label": "the same unit",
        "header_features": "chassis design, paneling, and surface finish are transferred to <Subject 1>",
        "summary_features": "retaining the unit's chassis, mechanical structure, plating, and surface details from {person_ref}",
        "retention_features": "retains the overall chassis, mechanical components, surface finish, and plating; pose is reset to neutral; no movement preserved.",
        "intro_features": "<Subject 1>'s chassis, mechanical design, and surface plating come from {person_ref} and stay identical across all {shots_word} shots. <Subject 1> stands in a neutral, stationary stance, disregarding any pose shown in {person_ref}.",
    },
    "Creature": {
        "fallback_label": "the same creature",
        "header_features": "scales, and anatomical features are transferred to <Subject 1>",
        "summary_features": "retaining the creature's body shape, skin texture, eyes, and anatomical features from {person_ref}",
        "retention_features": "retains the overall body structure, skin texture, fur, and features; pose is reset to neutral; no movement preserved.",
        "intro_features": "<Subject 1>'s skin texture, anatomical features, and fur come from {person_ref} and stay identical across all {shots_word} shots. <Subject 1> rests in a natural neutral posture, disregarding any pose shown in {person_ref}.",
    },
    "Object/Vehicle": {
        "fallback_label": "the same object",
        "header_features": "form factor, surface materials, and design details are transferred to <Subject 1>",
        "summary_features": "retaining the object's form factor, material finish, paint, and mechanical details from {person_ref}",
        "retention_features": "retains the form factor, materials, surface details, and paint; default resting orientation; no movement preserved.",
        "intro_features": "<Subject 1>'s form factor, surface finish, and design details come from {person_ref} and stay identical across all {shots_word} shots. <Subject 1> is placed in a neutral resting position, disregarding any angle shown in {person_ref}.",
    },
}



class SpaceGremlinSheetsConfig:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "angle": (_ANGLE_OPTIONS,),
                "framing": (_FRAMING_OPTIONS,),
                "camera_angle": (_CAMERA_ANGLE_OPTIONS,),
                "camera_height": (_CAMERA_HEIGHT_OPTIONS,),
                "camera_target": (_CAMERA_TARGET_OPTIONS,),
                "expression": (_EXPRESSION_OPTIONS,),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("shot_config",)
    FUNCTION = "build"
    CATEGORY = "SpaceGremlin"

    def build(self, angle, framing, camera_angle, camera_height, camera_target, expression):
        result = _SHOT_CONFIG_SEP.join(
            (angle, framing, camera_angle, camera_height, camera_target, expression)
        )
        return (result,)



class SheetsCustomPrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SheetsCustomPrompt",
            display_name="Sheet Prompt - Custom Shots (SpaceGremlin)",
            category="SpaceGremlin",
            inputs=[
                io.String.Input("person_description", multiline=True, default=""),
                io.Combo.Input("subject_type", options=_SUBJECT_TYPES, default="human", optional=True),
                io.String.Input("backdrop", default="plain light neutral white studio backdrop", multiline=True, optional=True),
                io.Float.Input("video_duration_seconds", default=5.0, min=1.0, max=60.0, step=0.1, optional=True,
                    tooltip="The take's actual length in seconds."),
                io.Int.Input("fps", default=24, min=1, max=120, optional=True,
                    tooltip="Framerate used to convert seconds into frame count (length)."),
                
                # --- OVERRIDES OPTIONNELS ---
                io.String.Input("override_subject_definitions", multiline=True, default="", optional=True,
                    tooltip="Remplace totalement la section subject_definitions."),
                io.String.Input("override_summary_features", multiline=True, default="", optional=True,
                    tooltip="Remplace la description dans summary."),
                io.String.Input("override_retention_analysis", multiline=True, default="", optional=True,
                    tooltip="Remplace le texte de rétention après les tags [Shot X]."),
                
                io.Autogrow.Input(
                    "shots",
                    template=io.Autogrow.TemplatePrefix(
                        input=io.String.Input("shot"),
                        prefix="shot_", min=1, max=_MAX_CUSTOM_SHOTS,
                    ),
                ),
            ],
            outputs=[
                io.String.Output(display_name="prompt"),
                io.Int.Output(display_name="length"),
            ],
        )

    @classmethod
    def execute(cls, person_description, shots,
                subject_type="human",
                backdrop="plain light neutral white studio backdrop",
                video_duration_seconds=5.0,
                fps=24,
                override_subject_definitions="",
                override_summary_features="",
                override_retention_analysis="") -> io.NodeOutput:
        
        tpl = _SUBJECT_TEMPLATES.get(subject_type, _SUBJECT_TEMPLATES["Human"])
        
        person_items = [t.strip().rstrip(".") for t in _parse_multi_description(person_description) if t.strip()]
        person = person_items[0] if person_items else tpl["fallback_label"]
        set_dressing = backdrop.strip().rstrip(".") or "plain light neutral white studio backdrop"
        person_count = max(1, len(person_items))
        person_tags = _picture_tags(1, person_count)
        person_ref = _join_tags_english(person_tags)

        parsed: list[tuple[str, str, str, str, str, str]] = []
        for value in (shots or {}).values():
            if not value:
                continue
            parts = value.split(_SHOT_CONFIG_SEP)
            if len(parts) != 6:
                continue
            parsed.append(tuple(parts))

        total_shots = max(1, len(parsed))
        duration = float(video_duration_seconds)
        step = max(0.1, math.floor((duration / total_shots) * 10) / 10)
        at = [_timecode(i * step) for i in range(total_shots)]
        shot_tags = ", ".join(f"[Shot {i + 1}]" for i in range(total_shots))
        shots_word = _COUNT_WORDS.get(total_shots, str(total_shots))

        # 1. SUBJECT DEFINITIONS
        if override_subject_definitions and override_subject_definitions.strip():
            header = f"subject_definitions:\n{override_subject_definitions.strip()}"
        else:
            header = (
                f"subject_definitions:\n<Subject 1> {person}, and the same figure "
                f"and proportions established in {person_ref}. "
                f"{person_ref} {tpl['header_features']}"
            )

        # 2. SUMMARY (Point fixe après 'static shots' en cas d'override)
        if override_summary_features and override_summary_features.strip():
            txt = override_summary_features.strip().rstrip(".")
            summary_feat = f". {txt}."
        else:
            summary_feat = f", {tpl['summary_features'].format(person_ref=person_ref)}."

        summary = (
            "summary:\n[reference generation] The target video presents "
            f"<Subject 1> in a {duration:g}-second sequence of "
            f"{total_shots} static shots{summary_feat} The background remains "
            f"{set_dressing}. Framing, angle and expression change shot to "
            "shot as described below; pose is otherwise held still within "
            "each shot."
        )

        # 3. RETENTION ANALYSIS (Retrait du 'fully_preserved - ' forcé sur override)
        if override_retention_analysis and override_retention_analysis.strip():
            retention_body = override_retention_analysis.strip()
            retention = (
                "retention_analysis:\n"
                f"<Subject 1> (appears in {shot_tags}) - {retention_body}"
            )
        else:
            retention_body = tpl['retention_features']
            retention = (
                "retention_analysis:\n"
                f"<Subject 1> (appears in {shot_tags}): fully_preserved - {retention_body}"
            )

        intro_feat = tpl['intro_features'].format(person_ref=person_ref, shots_word=shots_word)
        intro = (
            f"The target video uses a static studio lighting setup against "
            f"{set_dressing}. All shots are framed with generous empty "
            "margins on every side, ensuring the entire figure and any "
            "extensions remain fully within the frame without touching or "
            f"crossing edges. {set_dressing[0].upper()}{set_dressing[1:]} "
            "and its bright, even lighting stay completely identical across "
            f"all {shots_word} shots. No text, watermark, logo, caption, or "
            f"writing of any kind appears anywhere in the video. "
            f"{intro_feat} "
            "Each shot is an instant hard cut to a new camera position and "
            "angle around <Subject 1> — closer or farther, higher or "
            "lower, tilted up or down. Within each shot, the camera is a "
            "single static, locked-off shot, as if mounted on a tripod: "
            "completely still from the first frame of the shot to the "
            "last, right up to the next hard cut. <Subject 1> remains "
            "completely motionless throughout, holding one exact pose "
            "without turning, walking, gesturing, or otherwise moving "
            "between cuts.\n"
        )

        shot_lines = []
        for i, (angle, framing, camera_angle, camera_height, camera_target, expression) in enumerate(parsed):
            framing_text = _FRAMING_PHRASES.get(framing, framing)
            angle_text = _ANGLE_PHRASES.get(angle, angle)
            target_text = _CAMERA_TARGET_PHRASES.get(camera_target, camera_target)
            angle_template = _CAMERA_ANGLE_TEMPLATES.get(camera_angle)
            camera_angle_text = (
                angle_template.format(target=target_text) if angle_template is not None else camera_angle
            )
            expr_text = _EXPRESSION_PHRASES.get(expression, expression)
            if i == 0:
                opener = "[Shot 1] "
            else:
                opener = f"[Shot {i + 1}] At {at[i]}, a hard cut to "
            camera_text = camera_angle_text
            if camera_angle not in _CAMERA_ANGLE_FIXED_HEIGHT:
                camera_text += f", {_CAMERA_HEIGHT_PHRASES.get(camera_height, camera_height)}"
            shot_lines.append(
                f"{opener}{framing_text} of {target_text}, "
                f"{angle_text}, {camera_text}, a static, "
                f"locked-off shot, with a {expr_text} expression."
            )
        detail = "detailed_description:\n" + intro + "\n" + "\n".join(shot_lines)

        prompt = (
            f"{header}\n\n{summary}\n\n{retention}\n\n{detail}\n\n"
            "overall_soundscape:\nN/A\n\nnon_diegetic_music:\nN/A"
        )

        frame_length = int(round(duration * fps))
        return io.NodeOutput(prompt, frame_length)



class AddImageToList(io.ComfyNode):
    # Indique à ComfyUI que le nœud manipule/retourne des listes
    INPUT_IS_LIST = True
    OUTPUT_IS_LIST = (True,)

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="AddImageToList",
            display_name="Add Image to List (SpaceGremlin)",
            category="SpaceGremlin",
            inputs=[
                io.Image.Input("images"),
                io.Image.Input("image_to_add"),
                io.Combo.Input("position", options=["start", "end"], default="start"),
            ],
            outputs=[io.Image.Output(display_name="images")],
        )

    @classmethod
    def execute(cls, images, image_to_add, position="start") -> io.NodeOutput:
        # Quand INPUT_IS_LIST = True, 'images' et 'image_to_add' sont toujours reçus sous forme de listes Python
        # position est une liste d'un seul élément [ "start" ]
        pos = position[0] if isinstance(position, list) else position

        if pos == "start":
            result = image_to_add + images
        else:
            result = images + image_to_add

        return io.NodeOutput(result)




class DemuxAlpha:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("rgb_image", "alpha_mask")
    FUNCTION = "demux"
    CATEGORY = "SpaceGremlin/Alpha"

    def demux(self, image: torch.Tensor):
        # Format ComfyUI : [B, H, W, C]
        channels = image.shape[-1]

        if channels == 4:
            rgb = image[..., :3]
            # Extraction du canal 3 (Alpha) et conversion en MASK [B, H, W]
            alpha = image[..., 3]
        else:
            rgb = image
            # Si pas de canal Alpha, masque blanc opaque (1.0)
            alpha = torch.ones(image.shape[:3], device=image.device, dtype=image.dtype)

        return (rgb, alpha)


class RemuxAlpha:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "rgb_image": ("IMAGE",),
                "alpha_mask": ("MASK",),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("rgba_image",)
    FUNCTION = "remux"
    CATEGORY = "SpaceGremlin/Alpha"

    def remux(self, rgb_image: torch.Tensor, alpha_mask: torch.Tensor):
        rgb = rgb_image[..., :3]
        target_h, target_w = rgb.shape[1], rgb.shape[2]

        # Garantir le format [B, 1, H, W] pour PyTorch interpolate
        if len(alpha_mask.shape) == 2:
            mask = alpha_mask.unsqueeze(0).unsqueeze(0)
        elif len(alpha_mask.shape) == 3:
            mask = alpha_mask.unsqueeze(1)
        else:
            mask = alpha_mask

        # Redimensionnement du masque si les résolutions ne correspondent pas
        if mask.shape[2] != target_h or mask.shape[3] != target_w:
            mask = F.interpolate(mask, size=(target_h, target_w), mode="bilinear", align_corners=False)

        # Réalignement au format [B, H, W, 1]
        alpha = mask.squeeze(1).unsqueeze(-1)

        # Recombinaison RGBA [B, H, W, 4]
        rgba = torch.cat([rgb, alpha], dim=-1)

        return (rgba,)


class CustomTransparentPadding:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "left": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "right": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "top": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "bottom": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
            },
            "optional": {
                "mask": ("MASK",),  # Masque existant optionnel
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "add_padding"
    CATEGORY = "SpaceGremlin/Image"

    def add_padding(self, image, left, right, top, bottom, mask=None):
        # Sécurité : conversion en valeur absolue pour garantir des marges positives
        left, right = abs(int(left)), abs(int(right))
        top, bottom = abs(int(top)), abs(int(bottom))

        # Si aucun padding n'est demandé, on renvoie l'image et le masque d'origine
        if left == 0 and right == 0 and top == 0 and bottom == 0:
            if mask is None:
                # Création d'un masque opaque par défaut [B, H, W]
                b, h, w, _ = image.shape
                mask = torch.ones((b, h, w), dtype=torch.float32, device=image.device)
            return (image, mask)

        b, h, w, c = image.shape
        new_h = h + top + bottom
        new_w = w + left + right

        # 1. Gestion du Tensor Image (RGB ou RGBA)
        padded_image = torch.zeros((b, new_h, new_w, c), dtype=image.dtype, device=image.device)
        # Insertion de l'image d'origine aux coordonnées exactes
        padded_image[:, top:top+h, left:left+w, :] = image

        # 2. Gestion du canal Alpha / Masque
        # Si un masque est fourni, on l'utilise ; sinon on considère l'image d'origine à 100% opaque (1.0)
        if mask is not None:
            # Sécurité pour les dimensions [B, H, W]
            if len(mask.shape) == 2:
                mask = mask.unsqueeze(0)
            orig_mask = mask
        else:
            orig_mask = torch.ones((b, h, w), dtype=torch.float32, device=image.device)

        # Création du nouveau masque agrandi (0.0 = transparent sur les bordures)
        padded_mask = torch.zeros((b, new_h, new_w), dtype=torch.float32, device=image.device)
        padded_mask[:, top:top+h, left:left+w] = orig_mask

        # Si l'image d'origine avait déjà un canal alpha (4 canaux), on met à jour le canal alpha
        if c == 4:
            padded_image[:, :, :, 3] = padded_mask

        return (padded_image, padded_mask)



class ConditionalAlphaCrop:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "crop_horizontal": ("BOOLEAN", {"default": True, "label_on": "enabled", "label_off": "disabled"}),
                "crop_vertical": ("BOOLEAN", {"default": True, "label_on": "enabled", "label_off": "disabled"}),
            },
            "optional": {
                "mask": ("MASK",),  # Optionnel : si l'alpha est transmis séparément
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "crop_by_alpha"
    CATEGORY = "SpaceGremlin/Image"

    def crop_by_alpha(self, image, crop_horizontal=True, crop_vertical=True, mask=None):
        b, h, w, c = image.shape

        # 1. Extraction du canal alpha pour calculer la zone utile
        if mask is not None:
            # Masque externe fourni [B, H, W]
            alpha_channel = mask
            if len(alpha_channel.shape) == 2:
                alpha_channel = alpha_channel.unsqueeze(0)
        elif c == 4:
            # Alpha directement présent dans le tensor RGBA [B, H, W, 4]
            alpha_channel = image[:, :, :, 3]
        else:
            # Ni masque ni canal alpha : rien à cropper
            default_mask = torch.ones((b, h, w), dtype=torch.float32, device=image.device)
            return (image, default_mask)

        # Si aucun crop n'est coché, on renvoie l'entrée intacte
        if not crop_horizontal and not crop_vertical:
            if mask is None:
                mask = alpha_channel
            return (image, mask)

        # 2. Détection globale des pixels non transparents (> 0.0) sur tout le batch
        non_zero_coords = torch.nonzero(alpha_channel > 0.0)

        if non_zero_coords.numel() == 0:
            # L'image est totalement transparente
            return (image, alpha_channel)

        # Bounding box exacte de la transparence
        min_h = int(torch.min(non_zero_coords[:, 1]).item())
        max_h = int(torch.max(non_zero_coords[:, 1]).item()) + 1
        min_w = int(torch.min(non_zero_coords[:, 2]).item())
        max_w = int(torch.max(non_zero_coords[:, 2]).item()) + 1

        # 3. Application conditionnelle selon les booléens
        top = min_h if crop_vertical else 0
        bottom = max_h if crop_vertical else h

        left = min_w if crop_horizontal else 0
        right = max_w if crop_horizontal else w

        # 4. Rognage des Tensors
        cropped_image = image[:, top:bottom, left:right, :]
        cropped_mask = alpha_channel[:, top:bottom, left:right]

        return (cropped_image, cropped_mask)


class HexToColorValue:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "hex_code": ("STRING", {"default": "#FFFFFF", "multiline": False}),
            }
        }

    RETURN_TYPES = ("INT", "STRING", "FLOAT", "FLOAT", "FLOAT", "INT", "INT", "INT")
    RETURN_NAMES = (
        "int_24bit",     # La valeur numérique exacte (ex: 16777215 pour le blanc)
        "hex_clean",    # Le code hex nettoyé sans le #
        "r_float",      # Rouge [0.0 - 1.0] pour PyTorch
        "g_float",      # Vert [0.0 - 1.0]
        "b_float",      # Bleu [0.0 - 1.0]
        "r_255",        # Rouge [0 - 255]
        "g_255",        # Vert [0 - 255]
        "b_255"         # Bleu [0 - 255]
    )
    FUNCTION = "convert_hex"
    CATEGORY = "SpaceGremlin/Utils"

    def convert_hex(self, hex_code):
        # 1. Nettoyage de la chaîne
        clean_hex = hex_code.strip().lstrip("#")

        # Raccourci pour gérer le format à 3 caractères (ex: "FFF" -> "FFFFFF")
        if len(clean_hex) == 3:
            clean_hex = "".join([c * 2 for c in clean_hex])

        # Trim si la chaîne dépasse 6 caractères
        if len(clean_hex) > 6:
            clean_hex = clean_hex[:6]

        # Sécurité si la chaîne est invalide : fallback sur du blanc
        if len(clean_hex) != 6:
            clean_hex = "FFFFFF"

        try:
            # 2. Conversion Hex -> INT 24-bits (ex: FFFFFF -> 16777215)
            int_val = int(clean_hex, 16)
        except ValueError:
            int_val = 16777215
            clean_hex = "FFFFFF"

        # 3. Extraction des canaux RGB (0-255)
        r_255 = (int_val >> 16) & 255
        g_255 = (int_val >> 8) & 255
        b_255 = int_val & 255

        # 4. Normalisation Float (0.0 - 1.0)
        r_float = r_255 / 255.0
        g_float = g_255 / 255.0
        b_float = b_255 / 255.0

        return (int_val, clean_hex, r_float, g_float, b_float, r_255, g_255, b_255)


class SpaceGremlinStitchImages:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image1": ("IMAGE",),
                "direction": (["right", "down", "left", "up"], {"default": "right"}),
                "spacing": ("INT", {"default": 10, "min": -8192, "max": 8192, "step": 1}),
                "match_image_size": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "image2": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("IMAGE", "MASK")
    FUNCTION = "stitch"
    CATEGORY = "SpaceGremlin/Image"

    def _ensure_rgba(self, img):
        """ S'assure que le Tensor est au format RGBA (B, H, W, 4) """
        if img.shape[-1] == 3:
            alpha = torch.ones((*img.shape[:-1], 1), dtype=img.dtype, device=img.device)
            return torch.cat([img, alpha], dim=-1)
        return img

    def stitch(self, image1, direction, spacing, match_image_size, image2=None):
        # 1. Sécurité sur la valeur d'espacement (toujours positive)
        spacing = abs(int(spacing))

        # 2. Si image2 n'est pas connectée, on renvoie image1 propre
        if image2 is None:
            img1_rgba = self._ensure_rgba(image1)
            return (img1_rgba, img1_rgba[:, :, :, 3])

        # Convertir en RGBA 4 canaux
        img1 = self._ensure_rgba(image1)
        img2 = self._ensure_rgba(image2)

        # Prendre la première image de chaque batch/liste si nécessaire
        b1, h1, w1, _ = img1.shape
        b2, h2, w2, _ = img2.shape

        # 3. Redimensionnement optionnel (Match Size)
        if match_image_size:
            if direction in ["right", "left"] and h1 != h2:
                # Aligner la hauteur de image2 sur image1
                img2 = torch.nn.functional.interpolate(
                    img2.permute(0, 3, 1, 2), size=(h1, int(w2 * (h1 / h2))), mode="bicubic", align_corners=False
                ).permute(0, 2, 3, 1)
                _, h2, w2, _ = img2.shape
            elif direction in ["down", "up"] and w1 != w2:
                # Aligner la largeur de image2 sur image1
                img2 = torch.nn.functional.interpolate(
                    img2.permute(0, 3, 1, 2), size=(int(h2 * (w1 / w2)), w1), mode="bicubic", align_corners=False
                ).permute(0, 2, 3, 1)
                _, h2, w2, _ = img2.shape

        # 4. Inversion si direction "left" ou "up"
        first, second = (img1, img2) if direction in ["right", "down"] else (img2, img1)
        _, fh, fw, _ = first.shape
        _, sh, sw, _ = second.shape

        # 5. Calcul des dimensions de la nouvelle toile
        if direction in ["right", "left"]:
            out_h = max(fh, sh)
            out_w = fw + spacing + sw
        else:  # down, up
            out_h = fh + spacing + sh
            out_w = max(fw, sw)

        # 6. Création du Tensor vide (transparence totale Alpha = 0)
        out_img = torch.zeros((1, out_h, out_w, 4), dtype=first.dtype, device=first.device)

        # 7. Placement des images
        if direction in ["right", "left"]:
            out_img[:, :fh, :fw, :] = first
            out_img[:, :sh, fw + spacing:fw + spacing + sw, :] = second
        else:
            out_img[:, :fh, :fw, :] = first
            out_img[:, fw:fw + sh, :sw, :] = second if direction == "down" else second # Correction position verticale
            out_img[:, fh + spacing:fh + spacing + sh, :sw, :] = second

        # Extrait le masque alpha correspondant
        out_mask = out_img[..., 3]

        return (out_img, out_mask)


class SpaceGremlinResizeAndPad:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "target_width": ("INT", {"default": 512, "min": 1, "max": 16384, "step": 1}),
                "target_height": ("INT", {"default": 512, "min": 1, "max": 16384, "step": 1}),
                "alignment": ([
                    "center", 
                    "top", 
                    "bottom", 
                    "left", 
                    "right", 
                    "top-left", 
                    "top-right", 
                    "bottom-left", 
                    "bottom-right"
                ], {"default": "center"}),
                "interpolation": (["lanczos", "bicubic", "bilinear", "nearest", "area"], {"default": "lanczos"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("IMAGE", "MASK")
    FUNCTION = "resize_and_pad"
    CATEGORY = "SpaceGremlin/Image"

    def _ensure_rgba(self, img):
        if img.shape[-1] == 3:
            alpha = torch.ones((*img.shape[:-1], 1), dtype=img.dtype, device=img.device)
            return torch.cat([img, alpha], dim=-1)
        return img

    def resize_and_pad(self, image, target_width, target_height, alignment, interpolation):
        target_w = abs(int(target_width))
        target_h = abs(int(target_height))

        img_rgba = self._ensure_rgba(image)
        batch_size, h, w, _ = img_rgba.shape

        # Mappage des modes d'interpolation PIL
        pil_resample_map = {
            "lanczos": Image.Resampling.LANCZOS,
            "bicubic": Image.Resampling.BICUBIC,
            "bilinear": Image.Resampling.BILINEAR,
            "nearest": Image.Resampling.NEAREST,
            "area": Image.Resampling.BOX,
        }
        resample_mode = pil_resample_map.get(interpolation, Image.Resampling.LANCZOS)

        # Calcul du ratio d'adaptation (Fit)
        scale = min(target_w / w, target_h / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))

        # Calcul des offsets X et Y selon l'alignement choisi
        pad_x_free = target_w - new_w
        pad_y_free = target_h - new_h

        # Gestion axe Horizontal (X)
        if "left" in alignment:
            pad_left = 0
        elif "right" in alignment:
            pad_left = pad_x_free
        else:  # center, top, bottom
            pad_left = pad_x_free // 2

        # Gestion axe Vertical (Y)
        if "top" in alignment:
            pad_top = 0
        elif "bottom" in alignment:
            pad_top = pad_y_free
        else:  # center, left, right
            pad_top = pad_y_free // 2

        output_list = []

        for b in range(batch_size):
            # Conversion Tensor PyTorch (0.0-1.0) -> Image PIL RGBA
            img_np = (img_rgba[b].cpu().numpy() * 255).astype(np.uint8)
            pil_img = Image.fromarray(img_np, mode="RGBA")

            # Redimensionnement avec le filtre choisi
            resized_pil = pil_img.resize((new_w, new_h), resample=resample_mode)

            # Toile cible entièrement transparente (0, 0, 0, 0)
            canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            canvas.paste(resized_pil, (pad_left, pad_top))

            # Reconversion Image PIL -> Tensor PyTorch (0.0-1.0)
            canvas_np = np.array(canvas).astype(np.float32) / 255.0
            output_list.append(torch.from_numpy(canvas_np))

        out_img = torch.stack(output_list, dim=0).to(image.device)
        out_mask = out_img[..., 3]

        return (out_img, out_mask)


class SpaceGremlinListCount:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_list": ("IMAGE",),
            }
        }

    INPUT_IS_LIST = True
    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("count",)
    FUNCTION = "get_list_count"
    CATEGORY = "SpaceGremlin/Utils"

    def get_list_count(self, image_list):
        # Grâce à INPUT_IS_LIST = True, image_list est toujours une liste Python
        count = len(image_list)
        return (count,)


class SpaceGremlinBoolOR:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "bool_a": ("BOOLEAN", {"default": False, "forceInput": True}),
                "bool_b": ("BOOLEAN", {"default": False, "forceInput": True}),
            },
            "optional": {
                "bool_c": ("BOOLEAN", {"default": False, "forceInput": True}),
                "bool_d": ("BOOLEAN", {"default": False, "forceInput": True}),
            }
        }

    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("bool",)
    FUNCTION = "logic_or"
    CATEGORY = "SpaceGremlin/Logic"

    def logic_or(self, bool_a, bool_b, bool_c=False, bool_d=False):
        # Retourne True si au moins une des entrées est True
        result = bool(bool_a or bool_b or bool_c or bool_d)
        return (result,)


class SpaceGremlinBoolAND:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "bool_a": ("BOOLEAN", {"default": False, "forceInput": True}),
                "bool_b": ("BOOLEAN", {"default": False, "forceInput": True}),
            },
            "optional": {
                "bool_c": ("BOOLEAN", {"default": True, "forceInput": True}),
                "bool_d": ("BOOLEAN", {"default": True, "forceInput": True}),
            }
        }

    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("bool",)
    FUNCTION = "logic_and"
    CATEGORY = "SpaceGremlin/Logic"

    def logic_and(self, bool_a, bool_b, bool_c=True, bool_d=True):
        # True uniquement si TOUTES les entrées actives sont True
        result = bool(bool_a and bool_b and bool_c and bool_d)
        return (result,)


class SpaceGremlinBoolXOR:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "bool_a": ("BOOLEAN", {"default": False, "forceInput": True}),
                "bool_b": ("BOOLEAN", {"default": False, "forceInput": True}),
            }
        }

    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("bool",)
    FUNCTION = "logic_xor"
    CATEGORY = "SpaceGremlin/Logic"

    def logic_xor(self, bool_a, bool_b):
        # Ou exclusif : True si l'un est True et l'autre False
        result = bool(bool(bool_a) ^ bool(bool_b))
        return (result,)


class SpaceGremlinIntCompare:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "a": ("INT", {"default": 0, "forceInput": True}),
                "comparison": (["==", "!=", ">", "<", ">=", "<="], {"default": "=="}),
                "b": ("INT", {"default": 0, "forceInput": True}),
            }
        }

    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("bool",)
    FUNCTION = "compare"
    CATEGORY = "SpaceGremlin/Logic"

    def compare(self, a, comparison, b):
        a_val = int(a)
        b_val = int(b)

        if comparison == "==":
            result = (a_val == b_val)
        elif comparison == "!=":
            result = (a_val != b_val)
        elif comparison == ">":
            result = (a_val > b_val)
        elif comparison == "<":
            result = (a_val < b_val)
        elif comparison == ">=":
            result = (a_val >= b_val)
        elif comparison == "<=":
            result = (a_val <= b_val)
        else:
            result = False

        return (result,)


class SpaceGremlinListSelect:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_list": ("IMAGE",),
                "indexes": ("STRING", {"default": "0", "multiline": False}),
            }
        }

    INPUT_IS_LIST = True
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("selected_images",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "select_from_list"
    CATEGORY = "SpaceGremlin/Utils"

    def select_from_list(self, image_list, indexes):
        # Récupération de la chaîne d'index (traité comme liste en raison de INPUT_IS_LIST)
        idx_str = indexes[0] if isinstance(indexes, list) else str(indexes)
        
        # Nettoyage et découpage par virgule
        raw_parts = idx_str.split(",")
        selected_indices = []

        for part in raw_parts:
            part_clean = part.strip()
            if part_clean.lstrip("-").isdigit():
                selected_indices.append(int(part_clean))

        total_items = len(image_list)
        selected_output = []

        for idx in selected_indices:
            # Saisie sécurisée des index (gestion indexation Python classique)
            if -total_items <= idx < total_items:
                selected_output.append(image_list[idx])
            else:
                print(f"[SpaceGremlinListSelect] Attention: Index {idx} hors limites (taille liste: {total_items})")

        # Sécurité : si aucun index valide n'a pu être extrait, on retourne la liste d'origine
        if not selected_output:
            print("[SpaceGremlinListSelect] Aucun index valide fourni, retour de la liste complète par défaut.")
            selected_output = image_list

        return (selected_output,)


class SpaceGremlinSheetLayout:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_list": ("IMAGE",),
                "start_index": ("INT", {"default": 1, "min": 0, "max": 100, "step": 1}),
            }
        }

    INPUT_IS_LIST = True
    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("skipped_images", "top_images", "bottom_images")
    OUTPUT_IS_LIST = (True, True, True)
    FUNCTION = "split_layout"
    CATEGORY = "SpaceGremlin/Layout"

    def split_layout(self, image_list, start_index):
        offset = start_index[0] if isinstance(start_index, list) else int(start_index)
        
        total = len(image_list)
        
        # Isolation de l'image ignorée (ex: index 0)
        skipped_list = image_list[:offset]
        
        # Liste effective d'images secondaires à répartir
        effective_list = image_list[offset:]

        # Logique basée sur le TOTAL global d'images dans la liste initiale :
        if total in (5, 6):
            # L'image 0 occupe déjà la 1ère place du haut.
            # On ne prend donc que l'index 1 pour 'top_images' (soit 1 image supplémentaire).
            top_count = 1  
        elif total == 7:
            # Pour 7 images : 3 en haut au total (1 ignorée + 2 secondaires dans top_images).
            top_count = 2  
        else:
            # Comportement par défaut si < 5 ou > 7
            top_count = max(0, (total // 2) - offset)

        top_list = effective_list[:top_count]
        bottom_list = effective_list[top_count:]

        return (skipped_list, top_list, bottom_list)


class SpaceGremlinFlattenAlpha:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "apply_background": ("BOOLEAN", {"default": True}),
                "bg_hex": ("STRING", {"default": "#FFFFFF"}),
            }
        }

    INPUT_IS_LIST = True
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "process_alpha"
    CATEGORY = "SpaceGremlin/Image"

    def hex_to_rgb(self, hex_str):
        # Nettoyage et isolation des 6 premiers caractères
        clean_hex = hex_str.lstrip('#')[:6]
        
        # Validation de la longueur exacte et des caractères Hexa (0-9, A-F)
        if len(clean_hex) < 6 or not all(c in "0123456789abcdefABCDEF" for c in clean_hex):
            clean_hex = "FFFFFF"  # Fallback blanc de sécurité

        return [int(clean_hex[i:i+2], 16) / 255.0 for i in (0, 2, 4)]

    def process_alpha(self, image, apply_background, bg_hex):
        # Récupération sécurisée du booléen et de la chaîne Hexa
        keep_bg = apply_background[0] if isinstance(apply_background, list) else apply_background
        hex_color = bg_hex[0] if isinstance(bg_hex, list) else bg_hex

        output_list = []
        r_bg, g_bg, b_bg = self.hex_to_rgb(hex_color)

        for img in image:
            # Si l'image n'a pas de canal Alpha (RGB classique) ou si la fonction est désactivée
            if not keep_bg or img.shape[-1] < 4:
                output_list.append(img)
                continue

            # Extraction des canaux RGB et du canal Alpha
            rgb = img[..., :3]
            alpha = img[..., 3:4]

            # Création de la couleur de fond
            bg_tensor = torch.tensor([r_bg, g_bg, b_bg], dtype=img.dtype, device=img.device)
            bg_tensor = bg_tensor.expand_as(rgb)

            # Composition alpha : Result = RGB * Alpha + BG * (1 - Alpha)
            flattened = rgb * alpha + bg_tensor * (1.0 - alpha)

            output_list.append(flattened)

        return (output_list,)



NODE_CLASS_MAPPINGS = {
    "EnumTextSelector": EnumTextSelector,
    "SimpleBatchIndexOverlay": SimpleBatchIndexOverlay,
    "ShotTimelineGenerator": ShotTimelineGenerator,
    "DynamicBatchIndexExtractor": DynamicBatchIndexExtractor,
    "DynamicTextConcat": DynamicTextConcat,
    "ImageCompareSelector": ImageCompareSelector,
    "PauseControl": PauseControl,
    "SpaceGremlinFramePicker": SpaceGremlinFramePicker,
    "SpaceGremlinSheetsConfig": SpaceGremlinSheetsConfig,
    "SheetsCustomPrompt": SheetsCustomPrompt,
    "AddImageToList": AddImageToList,
    "DemuxAlpha": DemuxAlpha,
    "RemuxAlpha": RemuxAlpha,
    "CustomTransparentPadding": CustomTransparentPadding,
    "ConditionalAlphaCrop": ConditionalAlphaCrop,
    "HexToColorValue": HexToColorValue,
    "SpaceGremlinStitchImages": SpaceGremlinStitchImages,
    "SpaceGremlinResizeAndPad": SpaceGremlinResizeAndPad,
    "SpaceGremlinListCount": SpaceGremlinListCount,
    "SpaceGremlinBoolOR": SpaceGremlinBoolOR,
    "SpaceGremlinBoolAND": SpaceGremlinBoolAND,
    "SpaceGremlinBoolXOR": SpaceGremlinBoolXOR,
    "SpaceGremlinIntCompare": SpaceGremlinIntCompare,
    "SpaceGremlinListSelect": SpaceGremlinListSelect,
    "SpaceGremlinSheetLayout": SpaceGremlinSheetLayout,
    "SpaceGremlinListSplitAtIndex": SpaceGremlinListSplitAtIndex,
    "SpaceGremlinFlattenAlpha": SpaceGremlinFlattenAlpha,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "EnumTextSelector": "Enum Text Selector (SpaceGremlin)",
    "SimpleBatchIndexOverlay": "Simple Batch Index Overlay (SpaceGremlin)",
    "ShotTimelineGenerator": "Shot Timeline Generator (SpaceGremlin)",
    "DynamicBatchIndexExtractor": "Dynamic Batch Index Extractor (SpaceGremlin)",
    "DynamicTextConcat": "Dynamic Text Concat (SpaceGremlin)",
    "ImageCompareSelector": "Image Compare & Select (SpaceGremlin)",
    "PauseControl": "Pause / Control Selector (SpaceGremlin)",
    "SpaceGremlinFramePicker": "Frame Picker & Grid Inspector (SpaceGremlin)",
    "SpaceGremlinSheetsConfig": "Sheets Shot Config (SpaceGremlin)",
    "SheetsCustomPrompt": "Sheet Prompt - Custom Shots (SpaceGremlin)",
    "AddImageToList": "Add Image to List (SpaceGremlin)",
    "DemuxAlpha": "Demux Alpha (SpaceGremlin)",
    "RemuxAlpha": "Remux Alpha (SpaceGremlin)",
    "CustomTransparentPadding": "Custom Transparent Padding (SpaceGremlin)",
    "ConditionalAlphaCrop": "Conditional Alpha Crop (SpaceGremlin)",
    "HexToColorValue": "Hex To Color Value (SpaceGremlin)",
    "SpaceGremlinStitchImages": "Stitch Images - Transparent (SpaceGremlin)",
    "SpaceGremlinResizeAndPad": "Resize And Pad - Transparent (SpaceGremlin)",
    "SpaceGremlinListCount": "List Count (SpaceGremlin)",
    "SpaceGremlinBoolOR": "Bool OR (SpaceGremlin)",
    "SpaceGremlinBoolAND": "Bool AND (SpaceGremlin)",
    "SpaceGremlinBoolXOR": "Bool XOR (SpaceGremlin)",
    "SpaceGremlinIntCompare": "Int Compare (SpaceGremlin)",
    "SpaceGremlinListSelect": "List Select Items (SpaceGremlin)",
    "SpaceGremlinSheetLayout": "Sheet Layout Splitter (SpaceGremlin)",
    "SpaceGremlinListSplitAtIndex": "List Split at Index (SpaceGremlin)",
    "SpaceGremlinFlattenAlpha": "Flatten Alpha Background (SpaceGremlin)",
}
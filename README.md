# ComfyUI SpaceGremlin Toolkit

A lightweight collection of custom nodes for **ComfyUI** focused on batch manipulation, timeline management, dynamic string concatenation, and enum-based text selection.

---

## 🛠️ Nodes Overview

### 1. Dynamic Batch Index Extractor
Allows you to extract specific frames/images from a tensor batch using dynamic index inputs.

**Inputs:**
- `images` (*IMAGE*): The input batch of images.
- `index_0`, `index_1`, ... (*INT*): Dynamic input slots for frame indices.

**Outputs:**
- `images` (*IMAGE*): Re-batched images matching the selected indices.
- `count` (*INT*): Total number of extracted frames.

---

### 2. Dynamic Text Concat
Concatenates multiple string inputs dynamically into a single string using a custom separator.

**Inputs:**
- `separator` (*STRING*): Separator used between text entries (supports `\n` for line breaks).
- `text_0`, `text_1`, ... (*STRING*): Dynamic input slots for strings to join.

**Outputs:**
- `STRING`: Combined output text.

---

### 3. Enum Text Selector
Maps a choice from an enum definition to a corresponding line in a multiline string input.

**Inputs:**
- `choice` (*ENUM*): The selected enum option.
- `enum_definition` (*STRING*): Multiline enum keys definition.
- `output_lines` (*STRING, optional*): Multiline text mapped line-by-line to each enum index.

**Outputs:**
- `text` (*STRING*): Line matching the selected enum index.
- `index` (*INT*): 0-based position of the selection.

---

### 4. Shot Timeline Generator
Generates timecodes and shot labels for video/animation prompting based on duration, FPS, and shot count.

**Inputs:**
- `total_seconds` (*FLOAT*): Total duration of the animation sequence.
- `fps` (*INT*): Frame rate (frames per second).
- `num_shots` (*INT*): Total number of shots in the sequence.
- `selected_index` (*INT*): Index of the shot to retrieve.

**Outputs:**
- `selected_shot` (*STRING*): The specific timecode line for the selected shot index.
- `full_timeline_text` (*STRING*): Complete timeline listing all shots and timecodes.
- `total_shots` (*INT*): Total count of generated shots.

---

### 5. Simple Batch Index Overlay
Overlays the current frame index as visible text directly onto each image in a batch.

**Inputs:**
- `image` (*IMAGE*): Input image batch.
- `font_size` (*INT*): Overlay text size (default: 48).
- `font_color` (*STRING*): Hex color code (e.g., `#FFFFFF`).
- `start_index` (*INT*): Starting index number for the first frame.

**Outputs:**
- `IMAGE`: Processed image batch with index overlays.

---

## 📦 Installation

1. Navigate to your ComfyUI custom nodes directory:
   ```bash
   cd ComfyUI/custom_nodes/


2. Clone this repository:
```bash
   git clone [https://github.com/SpaceGremlinAI/ComfyUI-SpaceGremlin-Toolkit.git](https://github.com/SpaceGremlinAI/ComfyUI-SpaceGremlin-Toolkit.git)
```

3. Restart ComfyUI.


📄 License
MIT License. Free to use and modify.

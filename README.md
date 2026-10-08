# 🌌 ComfyUI SpaceGremlin Toolkit

A comprehensive, modular suite of custom nodes designed for **ComfyUI** to optimize, automate, and build high-fidelity workflows — including dynamic character sheet generation, alpha channel handling, list processing, and batch control.

---

## ✨ Features & Architecture Highlights

* **Native Python List Handling**: Fully compatible with `INPUT_IS_LIST = True` for granular image-by-image manipulation without tensor constraint issues.
* **Studio-Grade Character Sheets**: Complete dynamic prompt & layout pipeline for character turnarounds, expression sheets, and multi-angle shots.
* **GPU-Accelerated Alpha Channel Suite**: Demuxing, remuxing, padding, cropping, and compositing with full PyTorch acceleration and color validation.
* **Interactive UI Extensions**: WebSocket-synchronized frame pickers, comparison tools, and pause controls.

---

## 🛠️ Complete Node Reference

### 🎬 Character Sheet & Prompting
* **`Sheet Prompt - Custom Shots (SpaceGremlin)`** (`SheetsCustomPrompt`)  
  Generates multi-section prompts (`subject_definitions`, `summary`, `retention_analysis`, `detailed_description`) with live frame timing, shot tags, and optional multilines section overrides.
* **`Sheets Shot Config (SpaceGremlin)`** (`SpaceGremlinSheetsConfig`)  
  Configures custom shot parameters for multi-angle character reference sheets.
* **`Sheet Layout Splitter (SpaceGremlin)`** (`SpaceGremlinSheetLayout`)  
  Splits and formats incoming image sets into optimized character sheet grid structures.

---

### 🎨 Transparency & Alpha Channel Tools
* **`Flatten Alpha Background (SpaceGremlin)`** (`SpaceGremlinFlattenAlpha`)  
  Composites transparent images onto solid color backgrounds using PyTorch GPU blending with strict Hex-code validation.
* **`Demux Alpha (SpaceGremlin)`** (`DemuxAlpha`)  
  Extracts the alpha channel mask from an RGBA image.
* **`Remux Alpha (SpaceGremlin)`** (`RemuxAlpha`)  
  Recombines a standalone mask back into an RGB image as an alpha channel.
* **`Custom Transparent Padding (SpaceGremlin)`** (`CustomTransparentPadding`)  
  Pads images with transparent margins.
* **`Conditional Alpha Crop (SpaceGremlin)`** (`ConditionalAlphaCrop`)  
  Automatically crops transparent padding around subjects based on alpha threshold bounding boxes.
* **`Resize And Pad - Transparent (SpaceGremlin)`** (`SpaceGremlinResizeAndPad`)  
  Resizes and pads transparent images while maintaining accurate aspect ratios.
* **`Stitch Images - Transparent (SpaceGremlin)`** (`SpaceGremlinStitchImages`)  
  Stitches multiple transparent images side-by-side or stacked cleanly.
* **`Hex To Color Value (SpaceGremlin)`** (`HexToColorValue`)  
  Converts Hex color strings into normalized RGB/RGBA color vectors.

---

### 🖼️ Interactive Selection & Preview UI
* **`Frame Picker & Grid Inspector (SpaceGremlin)`** (`SpaceGremlinFramePicker`)  
  Interactive WebSocket-based UI for selecting frames from a sequence, featuring dynamic range validation (5–7 frames), keyboard shortcuts (`Escape`, `S`), audio cues, and full-screen previewing.
* **`Image Compare & Select (SpaceGremlin)`** (`ImageCompareSelector`)  
  Side-by-side comparison node to filter and output preferred images.
* **`Pause / Control Selector (SpaceGremlin)`** (`PauseControl`)  
  Execution control node to pause workflows for manual review or selection.

---

### 📋 List Manipulation & Batching
* **`Add Image To List (SpaceGremlin)`** (`AddImageToList`)  
  Appends single or multiple images into a unified Python list.
* **`List Split at Index (SpaceGremlin)`** (`SpaceGremlinListSplitAtIndex`)  
  Partitions Python lists at a specific target index.
* **`List Select Items (SpaceGremlin)`** (`SpaceGremlinListSelect`)  
  Selects targeted elements from a list using indices or ranges.
* **`List Count (SpaceGremlin)`** (`SpaceGremlinListCount`)  
  Returns the exact item count of a list.
* **`Simple Batch Index Overlay (SpaceGremlin)`** (`SimpleBatchIndexOverlay`)  
  Overlays visual index tags on images within a batch/list.
* **`Dynamic Batch Index Extractor (SpaceGremlin)`** (`DynamicBatchIndexExtractor`)  
  Extracts specific items dynamically based on batch positions.

---

### 🔤 Text, Timeline & Logic Helpers
* **`Enum Text Selector (SpaceGremlin)`** (`EnumTextSelector`)  
  Provides fixed drop-down enumeration options for text output.
* **`Dynamic Text Concat (SpaceGremlin)`** (`DynamicTextConcat`)  
  Dynamically concatenates multiple text strings.
* **`Shot Timeline Generator (SpaceGremlin)`** (`ShotTimelineGenerator`)  
  Generates timecodes and duration tags for video/shot timelines.
* **`Bool OR (SpaceGremlin)`** (`SpaceGremlinBoolOR`) / **`Bool AND`** (`SpaceGremlinBoolAND`) / **`Bool XOR`** (`SpaceGremlinBoolXOR`)  
  Standard boolean logic gate nodes.
* **`Int Compare (SpaceGremlin)`** (`SpaceGremlinIntCompare`)  
  Integer comparison node (`==`, `>`, `<`, etc.) returning boolean flags.

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

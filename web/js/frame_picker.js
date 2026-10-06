import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

function playNotificationSound() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(587.33, audioCtx.currentTime);
        gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
        osc.connect(gain);
        osc.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.2);
    } catch (e) { }
}

app.registerExtension({
    name: "SpaceGremlin.FramePicker",

    async nodeCreated(node) {
        if (node.comfyClass !== "SpaceGremlinFramePicker" && node.type !== "SpaceGremlinFramePicker") return;

        let totalFrames = 0, cols = 1, rows = 1, minSelection = 5, maxSelection = 7;
        let aspectRatio = 1.0;
        let selectedIndices = [];
        let currentFullscreenIndex = 0;
        let gridImgUrl = "";
        let loadedImage = new Image();

        const container = document.createElement("div");
        container.style.cssText = `
            display: flex; flex-direction: column; gap: 8px;
            width: 100%; height: 100%; padding: 8px;
            box-sizing: border-box; background: #18181b;
            border-radius: 6px; font-family: sans-serif; overflow: hidden;
        `;

        // Barres d'infos
        const headerInfo = document.createElement("div");
        headerInfo.style.cssText = "display: flex; justify-content: space-between; font-size: 11px; color: #a1a1aa; font-weight: bold;";
        headerInfo.innerHTML = `<span>Frames: <b id="total-lbl" style="color:#fff;">0</b></span><span>Range: <b id="range-lbl" style="color:#a78bfa;">5-7</b></span>`;

        // Zone principale (Grille / Plein écran)
        const mainViewer = document.createElement("div");
        mainViewer.style.cssText = "position: relative; width: 100%; flex: 1; min-height: 250px; background: #09090b; border-radius: 4px; overflow: hidden; border: 1px solid #27272a; display: flex; align-items: center; justify-content: center;";

        // Conteneur Grille
        const gridContainer = document.createElement("div");
        gridContainer.style.cssText = "display: grid; gap: 4px; width: 100%; height: 100%; padding: 4px; box-sizing: border-box; align-content: start; justify-content: start; overflow-y: auto;";

        // Overlay Plein écran
        const fsContainer = document.createElement("div");
        fsContainer.style.cssText = "display: none; position: absolute; inset: 0; background: #09090b; flex-direction: column; align-items: center; justify-content: center; z-index: 10; padding: 6px; box-sizing: border-box;";

        const fsImageWrapper = document.createElement("div");
        fsImageWrapper.style.cssText = "position: relative; flex: 1; width: 100%; display: flex; align-items: center; justify-content: center; overflow: hidden;";

        const fsCanvas = document.createElement("canvas");
        fsCanvas.style.cssText = "width: 100%; height: 100%; object-fit: contain; display: block;";

        const fsIndexOverlay = document.createElement("div");
        fsIndexOverlay.style.cssText = "position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.85); color: #fff; font-size: 14px; font-weight: bold; font-family: monospace; padding: 3px 8px; border-radius: 4px; border: 1px solid #52525b; pointer-events: none; z-index: 12;";

        const fsCheckbox = document.createElement("input");
        fsCheckbox.type = "checkbox";
        fsCheckbox.style.cssText = "position: absolute; top: 16px; right: 16px; width: 36px; height: 36px; cursor: pointer; z-index: 15;";

        const fsSliderContainer = document.createElement("div");
        fsSliderContainer.style.cssText = "width: 100%; padding: 6px 0 0 0; display: flex; align-items: center; gap: 8px; flex-shrink: 0;";

        const fsSlider = document.createElement("input");
        fsSlider.type = "range";
        fsSlider.style.cssText = "flex: 1; cursor: pointer;";

        fsSliderContainer.appendChild(fsSlider);
        fsImageWrapper.appendChild(fsCanvas);
        fsImageWrapper.appendChild(fsIndexOverlay);
        fsImageWrapper.appendChild(fsCheckbox);
        fsContainer.appendChild(fsImageWrapper);
        fsContainer.appendChild(fsSliderContainer);

        mainViewer.appendChild(gridContainer);
        mainViewer.appendChild(fsContainer);

        // Zone de sélection du bas
        const selectedSection = document.createElement("div");
        selectedSection.style.cssText = "display: flex; flex-direction: column; gap: 6px; background: #27272a; padding: 8px; border-radius: 4px; flex-shrink: 0; max-height: 200px; overflow-y: auto;";

        const selectedTitle = document.createElement("div");
        selectedTitle.style.cssText = "font-size: 11px; font-weight: bold; color: #a78bfa;";
        selectedTitle.innerText = "Selected Frames (0):";

        const selectedList = document.createElement("div");
        selectedList.style.cssText = "display: flex; flex-wrap: wrap; gap: 8px; align-items: center;";

        selectedSection.appendChild(selectedTitle);
        selectedSection.appendChild(selectedList);

        // Boutons Action
        const btnBox = document.createElement("div");
        btnBox.style.cssText = "display: flex; gap: 6px; width: 100%; flex-shrink: 0;";

        const btnContinue = document.createElement("button");
        btnContinue.innerHTML = `<span style="color: #a78bfa;">✓</span> Continue`;
        btnContinue.style.cssText = "flex: 1; padding: 8px; background: #282830; color: #d1d5db; border: 1px solid #3f3f46; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 12px;";

        const btnCancel = document.createElement("button");
        btnCancel.className = "pause-node-cancel-btn";
        btnCancel.innerHTML = `<span style="color: #f43f5e;">⛔</span> Cancel`;
        btnCancel.style.cssText = "flex: 1; padding: 8px; background: #4a1d24; color: #fecdd3; border: 1px solid #9f1239; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 12px;";

        btnBox.appendChild(btnContinue);
        btnBox.appendChild(btnCancel);

        container.appendChild(headerInfo);
        container.appendChild(mainViewer);
        container.appendChild(selectedSection);
        container.appendChild(btnBox);

        const toggleSelection = (index) => {
            const pos = selectedIndices.indexOf(index);
            if (pos > -1) {
                selectedIndices.splice(pos, 1);
            } else {
                if (selectedIndices.length < maxSelection) {
                    selectedIndices.push(index);
                } else {
                    return;
                }
            }
            updateUI();
        };

        const updateUI = () => {
            const count = selectedIndices.length;
            const isLimitReached = count >= maxSelection;
            const isValid = count >= minSelection && count <= maxSelection;

            selectedTitle.innerText = `Selected Frames (${count}/${minSelection}-${maxSelection}):`;
            selectedList.innerHTML = "";

            selectedIndices.forEach((idx) => {
                const tag = document.createElement("div");
                tag.style.cssText = `
                    background: #18181b; color: #fff; padding: 4px 6px;
                    border-radius: 4px; font-size: 12px; font-family: monospace;
                    font-weight: bold; cursor: pointer; display: flex;
                    align-items: center; gap: 8px; border: 1px solid #52525b;
                    flex-shrink: 0;
                `;

                const c = idx % cols;
                const r = Math.floor(idx / cols);
                const posX = cols > 1 ? (c / (cols - 1)) * 100 : 0;
                const posY = rows > 1 ? (r / (rows - 1)) * 100 : 0;

                const thumbH = 72;
                const thumbW = Math.round(thumbH * aspectRatio);

                const miniThumb = document.createElement("div");
                miniThumb.style.cssText = `
                    width: ${thumbW}px; height: ${thumbH}px; border-radius: 3px;
                    background-image: url('${gridImgUrl}');
                    background-size: ${cols * 100}% ${rows * 100}%;
                    background-position: ${posX}% ${posY}%;
                    background-repeat: no-repeat; border: 1px solid #3f3f46;
                `;

                const label = document.createElement("span");
                label.innerText = `#${idx}`;

                const closeBtn = document.createElement("span");
                closeBtn.style.cssText = "color: #f43f5e; font-weight: bold; font-size: 16px; margin-left: 2px;";
                closeBtn.innerText = "×";

                tag.appendChild(miniThumb);
                tag.appendChild(label);
                tag.appendChild(closeBtn);

                tag.onclick = () => toggleSelection(idx);
                selectedList.appendChild(tag);
            });

            const cbxList = gridContainer.querySelectorAll(".frame-cbx");
            cbxList.forEach((cb) => {
                const idx = parseInt(cb.dataset.index);
                const isSelected = selectedIndices.includes(idx);

                cb.checked = isSelected;
                cb.disabled = !isSelected && isLimitReached;
                cb.style.opacity = cb.disabled ? "0.3" : "1";
                cb.style.cursor = cb.disabled ? "not-allowed" : "pointer";
            });

            const fsSelected = selectedIndices.includes(currentFullscreenIndex);
            fsCheckbox.checked = fsSelected;
            fsCheckbox.disabled = !fsSelected && isLimitReached;
            fsCheckbox.style.opacity = fsCheckbox.disabled ? "0.3" : "1";
            fsCheckbox.style.cursor = fsCheckbox.disabled ? "not-allowed" : "pointer";

            // Activation du bouton Continue dès qu'on a atteint au moins minSelection (ex: 5)
            btnContinue.disabled = !isValid;
            btnContinue.style.opacity = isValid ? "1" : "0.4";
            btnContinue.style.cursor = isValid ? "pointer" : "not-allowed";
        };

        const drawFullscreenCanvas = () => {
            if (!loadedImage.complete || loadedImage.naturalWidth === 0) return;

            const c = currentFullscreenIndex % cols;
            const r = Math.floor(currentFullscreenIndex / cols);

            const frameW = loadedImage.naturalWidth / cols;
            const frameH = loadedImage.naturalHeight / rows;

            fsCanvas.width = frameW;
            fsCanvas.height = frameH;

            const ctx = fsCanvas.getContext("2d");
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = "high";

            ctx.drawImage(
                loadedImage,
                c * frameW, r * frameH, frameW, frameH,
                0, 0, frameW, frameH
            );
        };

        const openFullscreen = (index) => {
            currentFullscreenIndex = index;
            fsContainer.style.display = "flex";
            updateFullscreenFrame();
        };

        const closeFullscreen = () => {
            fsContainer.style.display = "none";
        };

        const updateFullscreenFrame = () => {
            fsIndexOverlay.innerText = `#${currentFullscreenIndex}`;
            fsSlider.value = currentFullscreenIndex;
            drawFullscreenCanvas();
            updateUI();
        };

        fsSlider.addEventListener("input", (e) => {
            currentFullscreenIndex = parseInt(e.target.value);
            updateFullscreenFrame();
        });

        fsImageWrapper.addEventListener("click", (e) => {
            if (e.target !== fsCheckbox && e.target !== fsSlider) {
                closeFullscreen();
            }
        });

        fsCheckbox.addEventListener("change", () => {
            toggleSelection(currentFullscreenIndex);
        });

        const renderGrid = () => {
            gridContainer.innerHTML = "";
            gridContainer.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;

            for (let i = 0; i < totalFrames; i++) {
                const cell = document.createElement("div");
                cell.style.cssText = `
                    position: relative; width: 100%;
                    aspect-ratio: ${aspectRatio}; background: #000;
                    overflow: hidden; border-radius: 3px; cursor: pointer;
                    border: 1px solid #27272a;
                `;

                const c = i % cols;
                const r = Math.floor(i / cols);
                const posX = cols > 1 ? (c / (cols - 1)) * 100 : 0;
                const posY = rows > 1 ? (r / (rows - 1)) * 100 : 0;

                const thumb = document.createElement("div");
                thumb.style.cssText = `
                    width: 100%; height: 100%;
                    background-image: url('${gridImgUrl}');
                    background-size: ${cols * 100}% ${rows * 100}%;
                    background-position: ${posX}% ${posY}%;
                    background-repeat: no-repeat;
                `;

                const idxTag = document.createElement("div");
                idxTag.style.cssText = "position: absolute; bottom: 2px; left: 2px; background: rgba(0,0,0,0.8); color: #fff; font-size: 10px; font-family: monospace; padding: 1px 4px; border-radius: 2px; pointer-events: none;";
                idxTag.innerText = `#${i}`;

                const cbx = document.createElement("input");
                cbx.type = "checkbox";
                cbx.className = "frame-cbx";
                cbx.dataset.index = i;
                cbx.style.cssText = "position: absolute; top: 8px; right: 8px; width: 32px; height: 32px; cursor: pointer; z-index: 5;";

                cbx.addEventListener("click", (e) => {
                    e.stopPropagation();
                    toggleSelection(i);
                });

                cell.addEventListener("click", () => openFullscreen(i));

                cell.appendChild(thumb);
                cell.appendChild(idxTag);
                cell.appendChild(cbx);
                gridContainer.appendChild(cell);
            }
        };

        const setUIState = (active) => {
            btnContinue.disabled = !active;
            btnCancel.disabled = !active;
            container.style.opacity = active ? "1" : "0.5";
        };

        const sendChoice = async (action) => {
            setUIState(false);
            await api.fetchApi("/image_compare/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    node_id: node.id.toString(),
                    choice: { action: action, indices: selectedIndices }
                })
            });
        };

        btnContinue.addEventListener("click", () => sendChoice("continue"));
        btnCancel.addEventListener("click", () => sendChoice("cancel"));

        node.addDOMWidget("picker_ui", "btn", container, { getValue() { }, setValue() { } });

        const handleWaitData = (detail, playSound = true) => {
            if (playSound) playNotificationSound();
            setUIState(true);

            totalFrames = detail.total_frames;
            cols = detail.cols;
            rows = detail.rows;
            minSelection = detail.min_selection || 5;
            maxSelection = detail.max_selection || 7;
            aspectRatio = detail.aspect_ratio || 1.0;
            selectedIndices = [];

            headerInfo.querySelector("#total-lbl").innerText = totalFrames;
            headerInfo.querySelector("#range-lbl").innerText = `${minSelection}-${maxSelection}`;

            fsSlider.min = 0;
            fsSlider.max = totalFrames - 1;

            gridImgUrl = `/view?filename=${detail.grid_filename}&type=temp&t=${Date.now()}`;

            loadedImage = new Image();
            loadedImage.onload = () => {
                renderGrid();
                updateUI();
            };
            loadedImage.src = gridImgUrl;

            if (!node.pinned) {
                node.setSize([Math.max(node.size[0], 480), 580]);
                app.graph.setDirtyCanvas(true, true);
            }
        };

        const checkForWaitingState = async () => {
            try {
                const res = await api.fetchApi(`/image_compare/status?node_id=${node.id}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.waiting && data.data) {
                        handleWaitData(data.data, false);
                    }
                }
            } catch (e) {
                console.error("Erreur lors de la vérification du statut du nœud:", e);
            }
        };

        api.addEventListener("frame-picker-wait", (event) => {
            if (String(event.detail.node_id) === String(node.id)) {
                handleWaitData(event.detail, true);
            }
        });

        api.addEventListener("execution_start", () => setUIState(false));

        setUIState(false);
        node.setSize([480, 580]);

        checkForWaitingState();
    }
});

window.addEventListener("keydown", (e) => {
    const isEscape = e.key === "Escape";
    const isSKey = e.key.toLowerCase() === "s" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);

    if (isEscape || isSKey) {
        let cancelButtons = document.querySelectorAll(".pause-node-cancel-btn");

        if (cancelButtons.length === 0) {
            cancelButtons = Array.from(document.querySelectorAll("button")).filter(btn =>
                btn.innerText.toLowerCase().includes("cancel")
            );
        }

        cancelButtons.forEach((btn) => {
            if (!btn.disabled) {
                btn.click();
            }
        });
    }
});
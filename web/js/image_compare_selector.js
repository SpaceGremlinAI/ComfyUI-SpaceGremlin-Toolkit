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
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.2);
    } catch (e) {
        console.warn("Audio Context blocked", e);
    }
}

app.registerExtension({
    name: "SpaceGremlin.ImageCompareSelector",

    async nodeCreated(node) {
        if (node.comfyClass !== "ImageCompareSelector" && node.type !== "ImageCompareSelector") return;

        const container = document.createElement("div");
        container.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 4px;
            width: 100%;
            height: 100%;
            padding: 4px;
            box-sizing: border-box;
            background: #1a1a1a;
            border-radius: 6px;
            font-family: sans-serif;
            overflow: hidden;
        `;

        const labelContainer = document.createElement("div");
        labelContainer.style.cssText = "display: flex; justify-content: space-between; width: 100%; font-size: 11px; font-weight: bold; padding: 2px 4px; flex-shrink: 0;";
        labelContainer.innerHTML = `
            <span style="color: #64b5f6;">Original Image</span>
            <span style="color: #81c784;">Enhanced</span>
        `;

        const compareBox = document.createElement("div");
        compareBox.style.cssText = `
            position: relative;
            width: 100%;
            flex: 1;
            min-height: 150px;
            overflow: hidden;
            border-radius: 4px;
            border: 1px solid #333;
            background: #000;
        `;

        const imgOrig = document.createElement("img");
        imgOrig.style.cssText = "position: absolute; top:0; left:0; width:100%; height:100%; object-fit: contain;";

        const imgEnhanced = document.createElement("img");
        imgEnhanced.style.cssText = "position: absolute; top:0; left:0; width:100%; height:100%; object-fit: contain; clip-path: inset(0 0 0 50%);";

        const infoOrig = document.createElement("div");
        infoOrig.style.cssText = `
            position: absolute; bottom: 6px; left: 6px;
            background: rgba(0, 0, 0, 0.75); color: #64b5f6;
            font-size: 10px; font-family: monospace; padding: 2px 6px;
            border-radius: 3px; border: 1px solid rgba(100, 181, 246, 0.4);
            pointer-events: none; z-index: 6; display: none;
        `;

        const infoEnhanced = document.createElement("div");
        infoEnhanced.style.cssText = `
            position: absolute; bottom: 6px; right: 6px;
            background: rgba(0, 0, 0, 0.75); color: #81c784;
            font-size: 10px; font-family: monospace; padding: 2px 6px;
            border-radius: 3px; border: 1px solid rgba(129, 199, 132, 0.4);
            pointer-events: none; z-index: 6; display: none;
        `;

        const slider = document.createElement("input");
        slider.type = "range";
        slider.min = "0";
        slider.max = "100";
        slider.value = "50";
        slider.style.cssText = "position: absolute; top:0; left:0; width:100%; height:100%; opacity:0; cursor: ew-resize; z-index: 10; margin: 0;";

        const line = document.createElement("div");
        line.style.cssText = "position: absolute; top:0; bottom:0; left:50%; width:2px; background:#fff; box-shadow:0 0 4px rgba(0,0,0,0.8); pointer-events:none; z-index:5;";

        slider.addEventListener("input", (e) => {
            const val = e.target.value;
            imgEnhanced.style.clipPath = `inset(0 0 0 ${val}%)`;
            line.style.left = `${val}%`;
        });

        compareBox.appendChild(imgOrig);
        compareBox.appendChild(imgEnhanced);
        compareBox.appendChild(infoOrig);
        compareBox.appendChild(infoEnhanced);
        compareBox.appendChild(line);
        compareBox.appendChild(slider);

        // Rangée des boutons de choix
        const btnBox = document.createElement("div");
        btnBox.style.cssText = "display: flex; gap: 6px; width: 100%; padding-top: 2px; flex-shrink: 0;";

        const btnOrig = document.createElement("button");
        btnOrig.innerText = "Keep Original";
        btnOrig.style.cssText = "flex: 1; padding: 6px 2px; background: #2b3a4a; color: #fff; border: 1px solid #4f6b8a; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 10px;";

        const btnBoth = document.createElement("button");
        btnBoth.innerText = "Keep Both";
        btnBoth.style.cssText = "flex: 1; padding: 6px 2px; background: #4a3b2b; color: #fff; border: 1px solid #8a6f4f; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 10px;";

        const btnEnh = document.createElement("button");
        btnEnh.innerText = "Keep Enhanced";
        btnEnh.style.cssText = "flex: 1; padding: 6px 2px; background: #2e4a32; color: #fff; border: 1px solid #4f8a54; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 10px;";

        const btnCancel = document.createElement("button");
        btnCancel.className = "pause-node-cancel-btn";
        btnCancel.innerHTML = `<span style="color: #f43f5e;">⛔</span> Cancel`;
        btnCancel.style.cssText = `
            width: 100%;
            padding: 6px;
            background: #4a1d24;
            color: #fecdd3;
            border: 1px solid #9f1239;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            font-size: 11px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            flex-shrink: 0;
        `;

        const setUIState = (active) => {
            btnOrig.disabled = !active;
            btnBoth.disabled = !active;
            btnEnh.disabled = !active;
            btnCancel.disabled = !active;
            container.style.opacity = active ? "1" : "0.5";
            btnOrig.style.cursor = active ? "pointer" : "not-allowed";
            btnBoth.style.cursor = active ? "pointer" : "not-allowed";
            btnEnh.style.cursor = active ? "pointer" : "not-allowed";
            btnCancel.style.cursor = active ? "pointer" : "not-allowed";
        };

        const sendChoice = async (choice) => {
            setUIState(false);
            await api.fetchApi("/image_compare/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ node_id: node.id.toString(), choice: choice })
            });
        };

        btnOrig.addEventListener("click", () => sendChoice("original"));
        btnBoth.addEventListener("click", () => sendChoice("both"));
        btnEnh.addEventListener("click", () => sendChoice("enhanced"));
        btnCancel.addEventListener("click", () => sendChoice("cancel"));

        btnBox.appendChild(btnOrig);
        btnBox.appendChild(btnBoth);
        btnBox.appendChild(btnEnh);

        container.appendChild(labelContainer);
        container.appendChild(compareBox);
        container.appendChild(btnBox);
        container.appendChild(btnCancel);

        const widget = node.addDOMWidget("compare_ui", "btn", container, {
            getValue() { },
            setValue() { }
        });

        imgOrig.onload = () => {
            if (imgOrig.naturalWidth && imgOrig.naturalHeight) {
                infoOrig.innerText = `${imgOrig.naturalWidth} x ${imgOrig.naturalHeight}`;
                infoOrig.style.display = "block";

                if (!node.pinned) {
                    const aspectRatio = imgOrig.naturalHeight / imgOrig.naturalWidth;
                    const nodeWidth = Math.max(node.size[0], 360);
                    const computedImageHeight = nodeWidth * aspectRatio;
                    const totalHeight = computedImageHeight + 135;

                    node.setSize([nodeWidth, totalHeight]);
                    app.graph.setDirtyCanvas(true, true);
                }
            }
        };

        imgEnhanced.onload = () => {
            if (imgEnhanced.naturalWidth && imgEnhanced.naturalHeight) {
                infoEnhanced.innerText = `${imgEnhanced.naturalWidth} x ${imgEnhanced.naturalHeight}`;
                infoEnhanced.style.display = "block";
            }
        };

        const origOnResize = node.onResize;
        node.onResize = function (size) {
            if (origOnResize) origOnResize.apply(this, arguments);
            const headerHeight = 60;
            if (widget && widget.element) {
                widget.element.style.height = `${Math.max(150, size[1] - headerHeight)}px`;
            }
        };

        const onCompareWait = (event) => {
            if (String(event.detail.node_id) === String(node.id)) {
                playNotificationSound();
                setUIState(true);

                const { orig_filename, enh_filename } = event.detail;
                const timestamp = Date.now();

                imgOrig.src = `/view?filename=${orig_filename}&type=temp&t=${timestamp}`;
                imgEnhanced.src = `/view?filename=${enh_filename}&type=temp&t=${timestamp}`;
            }
        };

        api.addEventListener("image-compare-wait", onCompareWait);
        api.addEventListener("execution_start", () => setUIState(false));

        setUIState(false);
        node.setSize([360, 340]);
    }
});
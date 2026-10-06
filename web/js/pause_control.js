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
    name: "SpaceGremlin.PauseControl",

    async nodeCreated(node) {
        if (node.comfyClass !== "PauseControl" && node.type !== "PauseControl") return;

        const container = document.createElement("div");
        container.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 6px;
            width: 100%;
            padding: 4px;
            box-sizing: border-box;
            background: transparent;
            font-family: sans-serif;
        `;

        const btnContinue = document.createElement("button");
        btnContinue.innerHTML = `<span style="color: #a78bfa;">✓</span> Continue`;
        btnContinue.style.cssText = `
            width: 100%;
            padding: 8px;
            background: #282830;
            color: #d1d5db;
            border: 1px solid #3f3f46;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        `;

        const btnCancel = document.createElement("button");
        btnCancel.innerHTML = `<span style="color: #f43f5e;">⛔</span> Cancel`;
        btnCancel.style.cssText = `
            width: 100%;
            padding: 8px;
            background: #282830;
            color: #d1d5db;
            border: 1px solid #3f3f46;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        `;

        const setUIState = (active) => {
            btnContinue.disabled = !active;
            btnCancel.disabled = !active;
            container.style.opacity = active ? "1" : "0.4";
            btnContinue.style.cursor = active ? "pointer" : "not-allowed";
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

        btnContinue.addEventListener("click", () => sendChoice("continue"));
        btnCancel.addEventListener("click", () => sendChoice("cancel"));

        container.appendChild(btnContinue);
        container.appendChild(btnCancel);

        node.addDOMWidget("pause_ui", "btn", container, {
            getValue() { },
            setValue() { }
        });

        node.setSize([320, 130]);
        setUIState(false);

        api.addEventListener("pause-control-wait", (event) => {
            if (String(event.detail.node_id) === String(node.id)) {
                playNotificationSound(); // <-- Déclenchement de la notification sonore
                setUIState(true);
            }
        });

        api.addEventListener("execution_start", () => {
            setUIState(false);
        });


    }
});
window.addEventListener("keydown", (e) => {
    // Touche Échap OU touche 'S' (hors saisie texte)
    const isEscape = e.key === "Escape";
    const isSKey = e.key.toLowerCase() === "s" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);

    if (isEscape || isSKey) {
        // 1. Cherche tous les boutons identifiés par la classe dédiée
        let cancelButtons = document.querySelectorAll(".pause-node-cancel-btn");

        // 2. Fallback : si la classe n'est pas mise, cherche tout bouton contenant "Cancel"
        if (cancelButtons.length === 0) {
            cancelButtons = Array.from(document.querySelectorAll("button")).filter(btn =>
                btn.innerText.toLowerCase().includes("cancel")
            );
        }

        // Déclenche l'annulation sur tous les nœuds actuellement en pause active
        cancelButtons.forEach((btn) => {
            if (!btn.disabled) {
                btn.click();
            }
        });
    }
});
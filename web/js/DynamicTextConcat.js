import { app } from "/scripts/app.js";

app.registerExtension({
    name: "SpaceGremlin.DynamicTextConcat",
    async nodeCreated(node) {
        if (node.comfyClass !== "DynamicTextConcat") return;

        const updateInputs = () => {
            if (!node.inputs) return;

            // Trouver le plus grand index d'entrée existant
            let maxIdx = 0;
            node.inputs.forEach(input => {
                if (input.name.startsWith("text_")) {
                    const idx = parseInt(input.name.split("_")[1]);
                    if (!isNaN(idx) && idx > maxIdx) maxIdx = idx;
                }
            });

            const lastInput = node.inputs.find(i => i.name === `text_${maxIdx}`);

            // Si le dernier slot est connecté, on ajoute le suivant
            if (lastInput && lastInput.link !== null) {
                node.addInput(`text_${maxIdx + 1}`, "STRING");
            }
            // Nettoyage : si l'avant-dernier et le dernier sont vides, on retire le surplus
            else if (maxIdx > 0) {
                const prevInput = node.inputs.find(i => i.name === `text_${maxIdx - 1}`);
                if ((!prevInput || prevInput.link === null) && lastInput.link === null) {
                    node.removeInput(node.inputs.indexOf(lastInput));
                }
            }

            app.graph.setDirtyCanvas(true, true);
        };

        const origOnConnectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function (type, index, connected, link_info) {
            if (origOnConnectionsChange) origOnConnectionsChange.apply(this, arguments);
            updateInputs();
        };
    }
});
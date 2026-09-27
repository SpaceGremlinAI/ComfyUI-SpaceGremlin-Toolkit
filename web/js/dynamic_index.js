import { app } from "/scripts/app.js";

app.registerExtension({
    name: "SpaceGremlin.DynamicBatchIndexExtractor",
    async nodeCreated(node) {
        if (node.comfyClass !== "DynamicBatchIndexExtractor") return;

        node.onConnectionsChange = function (type, slotIndex, isConnected, linkInfo) {
            if (type !== 1) return;

            const indexInputs = node.inputs.filter(input => input.name.startsWith("index_"));

            const lastIndexInput = indexInputs[indexInputs.length - 1];
            if (lastIndexInput && lastIndexInput.link !== null) {
                const nextNumber = indexInputs.length;
                node.addInput(`index_${nextNumber}`, "INT");
            }

            while (
                node.inputs.length > 2 && 
                node.inputs[node.inputs.length - 1].link === null &&
                node.inputs[node.inputs.length - 2].link === null
            ) {
                node.removeInput(node.inputs.length - 1);
            }

            
            node.setSize(node.computeSize());
            app.graph.setDirtyCanvas(true, true);
        };
    }
});
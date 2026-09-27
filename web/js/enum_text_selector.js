import { app } from "/scripts/app.js";

const TARGET_NODE_NAME = "EnumTextSelector";

function parseEnumNames(text) {
    if (!text) return ["OPTION_A", "OPTION_B"];

    const lines = text.split(/\r?\n/)
        .map(l => l.trim())
        .filter(l => l.length > 0 && !l.startsWith("#") && !l.startsWith("//"));

    const names = lines.map(line => {
        // Enlève l'assignation '= 0' si présente
        let clean = line.includes("=") ? line.split("=")[0].trim() : line;

        // Retire les guillemets autour du texte ("Full Body" -> Full Body)
        if ((clean.startsWith('"') && clean.endsWith('"')) || (clean.startsWith("'") && clean.endsWith("'"))) {
            clean = clean.slice(1, -1).trim();
        }

        return clean;
    }).filter(l => l.length > 0);

    return names.length > 0 ? names : ["OPTION_A", "OPTION_B"];
}

function updateWidgetOptions(widget, values, preserveValue = null) {
    if (!widget) return;

    // Sauvegarde de la valeur active
    const currentValue = preserveValue !== null ? preserveValue : widget.value;

    // Mise à jour de l'état réactif (Nodes 2.0 / LiteGraph)
    if (widget._state && widget._state.options) {
        widget._state.options.values = values;
    }

    widget.values = values;
    if (widget.options) {
        widget.options.values = values;
    }

    // Si la valeur actuelle figure parmi les nouvelles options, on la conserve
    if (values.includes(currentValue)) {
        widget.value = currentValue;
    } else {
        // Sinon (et seulement si elle est vraiment absente), on bascule sur la première
        widget.value = values[0] || "";
    }
}

function refreshNodeChoices(node, savedValue = null) {
    const choiceWidget = node.widgets?.find(w => w.name === "choice");
    if (!choiceWidget) return;

    let textValue = null;

    // Check si une entrée est connectée à 'enum_definition'
    const input = node.inputs?.find(i => i.name === "enum_definition");
    if (input && input.link != null && node.graph) {
        const link = node.graph.links?.[input.link] || node.graph._links?.get?.(input.link) || node.graph._links?.[input.link];
        if (link) {
            const originNode = node.graph.getNodeById(link.origin_id);
            if (originNode) {
                const stringWidget = originNode.widgets?.find(w => typeof w.value === "string");
                if (stringWidget) {
                    textValue = stringWidget.value;
                }
            }
        }
    } else {
        const defWidget = node.widgets?.find(w => w.name === "enum_definition");
        if (defWidget) textValue = defWidget.value;
    }

    const newChoices = parseEnumNames(textValue);
    updateWidgetOptions(choiceWidget, newChoices, savedValue);
    node.graph?.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "SpaceGremlin.EnumTextSelector",

    async nodeCreated(node) {
        if (node.comfyClass === TARGET_NODE_NAME || node.type === TARGET_NODE_NAME) {

            // Écoute des clics sur le widget pour rafraîchir à la volée
            const choiceWidget = node.widgets?.find(w => w.name === "choice");
            if (choiceWidget) {
                const origMouseDown = choiceWidget.onMouseDown;
                choiceWidget.onMouseDown = function () {
                    refreshNodeChoices(node);
                    if (origMouseDown) return origMouseDown.apply(this, arguments);
                };
            }

            setTimeout(() => refreshNodeChoices(node), 100);
        }
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === TARGET_NODE_NAME) {
            const onConnectionsChange = nodeType.prototype.onConnectionsChange;
            nodeType.prototype.onConnectionsChange = function (type, slotIndex, isConnected) {
                if (onConnectionsChange) onConnectionsChange.apply(this, arguments);
                refreshNodeChoices(this);
            };

            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function (info) {
                if (onConfigure) onConfigure.apply(this, arguments);

                // Extraction de la valeur 'choice' directement depuis le JSON sauvegardé
                let savedChoice = null;
                if (info?.widgets_values && this.widgets) {
                    const choiceIdx = this.widgets.findIndex(w => w.name === "choice");
                    if (choiceIdx !== -1) {
                        savedChoice = info.widgets_values[choiceIdx];
                    }
                }

                setTimeout(() => refreshNodeChoices(this, savedChoice), 150);
            };
        }
    }
});
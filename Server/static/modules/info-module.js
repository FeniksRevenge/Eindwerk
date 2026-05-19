(() => {
  function renderInfo({ moduleData, body, moduleMemory, handlers }) {
    const placeholder = "Schrijf hier je info / notities...";
    body.innerHTML = `<textarea class="module-textarea" placeholder="${placeholder}"></textarea>`;
    const textArea = body.querySelector(".module-textarea");
    textArea.setAttribute("draggable", "false");
    textArea.addEventListener("mousedown", (event) => {
      event.stopPropagation();
    });
    textArea.value = moduleMemory?.text || "";
    textArea.addEventListener("input", () => {
      handlers.updateModuleMemory?.(moduleData.id, { text: textArea.value });
    });
  }

  window.ModuleRegistry = window.ModuleRegistry || {};
  window.ModuleRegistry.info = renderInfo;
})();

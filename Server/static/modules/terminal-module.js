(() => {
  function renderTerminal({ moduleData, body, moduleMemory, handlers }) {
    body.innerHTML =
      "<div class=\"terminal-output\" id=\"terminalOutput\"></div><input class=\"terminal-input\" type=\"text\" placeholder=\"Command...\" />";
    body.classList.add("terminal-body");
    const terminalOutput = body.querySelector(".terminal-output");
    const terminalInput = body.querySelector(".terminal-input");
    const header = body.closest(".module")?.querySelector(".module-header");
    let status = header?.querySelector(".module-status");
    if (header && !status) {
      status = document.createElement("span");
      status.className = "module-status";
      status.textContent = "Idle";
      header.insertBefore(status, header.querySelector(".module-actions"));
    }
    const actions = body.closest(".module")?.querySelector(".module-actions");
    if (actions && !actions.querySelector(".module-stop")) {
      const stopButton = document.createElement("button");
      stopButton.className = "module-stop";
      stopButton.title = "Force stop";
      stopButton.type = "button";
      stopButton.textContent = "⏹";
      stopButton.addEventListener("click", () => {
        handlers.stopTerminal?.(moduleData.id, terminalOutput);
      });
      actions.prepend(stopButton);
    }
    const history = Array.isArray(moduleMemory?.terminalHistory)
      ? moduleMemory.terminalHistory
      : [];
    let historyIndex = history.length;
    terminalOutput.dataset.moduleId = moduleData.id;
    if (Array.isArray(moduleMemory?.terminalLines) && moduleMemory.terminalLines.length) {
      moduleMemory.terminalLines.forEach((line) => handlers.appendTerminalLine?.(terminalOutput, line));
    } else if (!terminalOutput.dataset.ready) {
      terminalOutput.dataset.ready = "true";
      handlers.appendTerminalLine?.(terminalOutput, "Microsoft Windows [Version 10.0.0]");
      handlers.appendTerminalLine?.(terminalOutput, "(c) Microsoft Corporation. All rights reserved.");
      handlers.updateModuleMemory?.(moduleData.id, {
        terminalLines: handlers.getTerminalLines?.(terminalOutput) || [],
      });
    }
    terminalInput.addEventListener("keydown", (event) => {
      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (history.length === 0) {
          return;
        }
        historyIndex = Math.max(0, historyIndex - 1);
        terminalInput.value = history[historyIndex] || "";
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (history.length === 0) {
          return;
        }
        historyIndex = Math.min(history.length, historyIndex + 1);
        terminalInput.value = historyIndex >= history.length ? "" : (history[historyIndex] || "");
        return;
      }
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      const rawValue = terminalInput.value.trim();
      if (!rawValue) {
        return;
      }
      const normalized = rawValue.toLowerCase();
      if (normalized === "cls" || normalized === "clear") {
        handlers.clearTerminalOutput?.(terminalOutput, moduleData.id);
        terminalInput.value = "";
        terminalInput.focus();
        return;
      }
      if (history.length === 0 || history[history.length - 1] !== rawValue) {
        history.push(rawValue);
        handlers.updateModuleMemory?.(moduleData.id, { terminalHistory: history });
      }
      historyIndex = history.length;
      handlers.appendTerminalLine?.(terminalOutput, `C:\\> ${rawValue}`);
      terminalInput.value = "";
      handlers.runTerminal?.(rawValue, terminalOutput);
      terminalInput.focus();
    });
  }

  window.ModuleRegistry = window.ModuleRegistry || {};
  window.ModuleRegistry.terminal = renderTerminal;
})();

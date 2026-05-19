(() => {
  const moduleCatalog = {
    info: { title: "Info / Notities", content: "Algemene informatie" },
    stats: { title: "Stats", content: "Status overzicht" },
    arp: { title: "ARP Tabel", content: "Nog geen ARP data beschikbaar" },
    ping: { title: "Ping", content: "Kies een apparaat om te pingen" },
    terminal: { title: "Terminal", content: "Geen verbonden apparaten" },
    plc: { title: "PLC I/O", content: "Selecteer een PLC-apparaat" },
  };

  const MULTI_MODULE_KEYS = new Set(["info", "terminal"]);

  function renderModuleBody({ moduleData, body, moduleMemory, handlers }) {
    if (!moduleData || !body || !handlers) {
      return;
    }

    const renderFn = window.ModuleRegistry?.[moduleData.key];
    if (renderFn) {
      renderFn({ moduleData, body, moduleMemory, handlers });
      return;
    }

    if (moduleData.key === "stats") {
      handlers.renderStats?.(body, moduleData);
      return;
    }

    body.textContent = moduleData.content || "";
  }

  window.SharedModules = {
    moduleCatalog,
    MULTI_MODULE_KEYS,
    renderModuleBody,
  };
})();

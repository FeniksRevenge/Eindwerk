(() => {
  function renderArp({ moduleData, body, moduleMemory, handlers }) {
    body.innerHTML =
      "<table class=\"arp-table\"><thead><tr><th>IP Address</th><th>MAC Address</th><th>Status</th></tr></thead><tbody class=\"arp-tbody\"></tbody></table>";
    body.classList.add("arp-body");

    const tbody = body.querySelector(".arp-tbody");
    const header = body.closest(".module")?.querySelector(".module-header");
    let status = header?.querySelector(".module-status");
    if (header && !status) {
      status = document.createElement("span");
      status.className = "module-status";
      status.textContent = "Ready";
      header.insertBefore(status, header.querySelector(".module-actions"));
    }

    let refreshTimer = null;

    function renderArpTable(entries) {
      tbody.innerHTML = "";
      if (!Array.isArray(entries) || entries.length === 0) {
        tbody.innerHTML = "<tr><td colspan=\"3\" class=\"arp-empty\">No ARP entries</td></tr>";
        return;
      }
      entries.forEach((entry) => {
        const row = document.createElement("tr");
        row.innerHTML = `<td>${entry.ip || ""}</td><td class="arp-mac">${entry.mac || ""}</td><td>${entry.status || ""}</td>`;
        tbody.appendChild(row);
      });
    }

    async function refreshArpTable() {
      if (status) status.textContent = "Loading...";
      try {
        const response = await fetch("/api/arp", { method: "POST" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        const entries = data.entries || [];
        handlers.updateModuleMemory?.(moduleData.id, { arpEntries: entries });
        renderArpTable(entries);
        if (status) status.textContent = "Ready";
      } catch (err) {
        if (status) status.textContent = "Error";
        tbody.innerHTML = `<tr><td colspan="3" class="arp-error">Error: ${err.message}</td></tr>`;
      }
    }

    if (moduleMemory?.arpEntries) {
      renderArpTable(moduleMemory.arpEntries);
    }

    refreshArpTable();

    refreshTimer = setInterval(refreshArpTable, 60000);

    const module = body.closest(".module");
    if (module) {
      const originalCleanup = module._arpCleanup;
      module._arpCleanup = () => {
        if (refreshTimer) {
          clearInterval(refreshTimer);
          refreshTimer = null;
        }
        if (originalCleanup) {
          originalCleanup();
        }
      };
    }
  }

  window.ModuleRegistry = window.ModuleRegistry || {};
  window.ModuleRegistry.arp = renderArp;
})();

(() => {
  function renderPing({ moduleData, body, moduleMemory, handlers }) {
    body.innerHTML =
      "<div class=\"ping-controls\"><input class=\"ping-input\" type=\"text\" placeholder=\"xxx.xxx.x.x\" /><input class=\"ping-interval\" type=\"number\" min=\"1\" value=\"5\" /></div><label class=\"ping-auto\"><input type=\"checkbox\" class=\"ping-toggle\" /> Auto ping (s)</label><div class=\"ping-list\"></div>";
    const input = body.querySelector(".ping-input");
    const interval = body.querySelector(".ping-interval");
    const toggle = body.querySelector(".ping-toggle");
    const pingList = body.querySelector(".ping-list");
    let timer = null;
    let savedIps = moduleMemory?.savedIps || [];

    if (Number.isFinite(Number(moduleMemory?.pingInterval))) {
      interval.value = String(moduleMemory.pingInterval);
    }
    if (typeof moduleMemory?.pingAuto === "boolean") {
      toggle.checked = moduleMemory.pingAuto;
    }

    function isValidIp(ip) {
      const parts = ip.split(".");
      if (parts.length !== 4) {
        return false;
      }
      return parts.every((part) => {
        const num = parseInt(part, 10);
        return !isNaN(num) && num >= 0 && num <= 255;
      });
    }

    function renderPingList() {
      pingList.innerHTML = "";
      if (savedIps.length === 0) {
        pingList.innerHTML = "<div class=\"ping-empty\">Geen IPs opgeslagen</div>";
        return;
      }
      savedIps.forEach((item, idx) => {
        const row = document.createElement("div");
        row.className = "ping-row";
        let status = "";
        let statusClass = "";
        if (item.status === "success") {
          status = "✓";
          statusClass = "ping-status-ok";
        } else if (item.status === "loading") {
          status = "⟳";
          statusClass = "ping-status-loading";
        } else {
          status = "✗";
          statusClass = "ping-status-fail";
        }
        const ms = item.ms ? ` ${item.ms}ms` : "";
        row.innerHTML = `<span class="ping-indicator ${statusClass}">${status}</span><span class="ping-ip">${item.ip}</span><span class="ping-time">${ms}</span><button class="ping-delete" type="button" data-index="${idx}">×</button>`;
        pingList.appendChild(row);
      });
    }

    function addOrUpdateIp(ip, status, ms) {
      const existing = savedIps.findIndex((item) => item.ip === ip);
      if (existing >= 0) {
        savedIps[existing] = { ip, status, ms };
      } else {
        savedIps.push({ ip, status, ms });
      }
      handlers.updateModuleMemory?.(moduleData.id, { savedIps });
      renderPingList();
    }

    function deleteIp(idx) {
      savedIps.splice(idx, 1);
      handlers.updateModuleMemory?.(moduleData.id, { savedIps });
      renderPingList();
    }

    function parsePingOutput(text) {
      if (!text) {
        return { status: "fail", ms: null };
      }
      const msMatch = text.match(/time[=<]\s*(\d+)ms/i);
      if (msMatch) {
        return { status: "success", ms: msMatch[1] };
      }
      if (text.includes("Failed")) {
        return { status: "fail", ms: null };
      }
      return { status: "fail", ms: null };
    }

    renderPingList();

    pingList.addEventListener("click", (event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.classList.contains("ping-delete")) {
        const idx = Number(target.dataset.index);
        if (!isNaN(idx)) {
          deleteIp(idx);
        }
      }
    });

    input.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      const ip = input.value.trim();
      if (!ip) {
        return;
      }

      if (!isValidIp(ip)) {
        input.value = "";
        return;
      }

      if (savedIps.length >= 4) {
        input.value = "";
        return;
      }

      input.value = "";
      addOrUpdateIp(ip, "loading", null);

      try {
        const response = await fetch("/api/ping", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ host: ip }),
        });

        if (!response.ok) {
          addOrUpdateIp(ip, "fail", null);
          input.focus();
          return;
        }

        const data = await response.json();
        const outputText = data.output || "";
        const result = parsePingOutput(outputText);
        addOrUpdateIp(ip, result.status, result.ms);
      } catch (err) {
        addOrUpdateIp(ip, "fail", null);
      } finally {
        input.focus();
      }
    });

    interval.addEventListener("change", () => {
      handlers.updateModuleMemory?.(moduleData.id, { pingInterval: Number(interval.value) || 5 });
    });

    toggle.addEventListener("change", () => {
      handlers.updateModuleMemory?.(moduleData.id, { pingAuto: toggle.checked });
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      if (!toggle.checked) {
        return;
      }
      if (savedIps.length === 0) {
        return;
      }
      const seconds = Math.max(1, Number(interval.value) || 5);
      handlers.updateModuleMemory?.(moduleData.id, { pingInterval: seconds });
      let ipIndex = 0;
      timer = setInterval(async () => {
        if (savedIps.length === 0) {
          return;
        }
        const ip = savedIps[ipIndex % savedIps.length].ip;

        try {
          const response = await fetch("/api/ping", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ host: ip }),
          });

          const data = await response.json();
          const outputText = data.output || "";
          const result = parsePingOutput(outputText);
          addOrUpdateIp(ip, result.status, result.ms);
        } catch (err) {
          addOrUpdateIp(ip, "fail", null);
        }

        ipIndex++;
      }, seconds * 1000);
    });
  }

  window.ModuleRegistry = window.ModuleRegistry || {};
  window.ModuleRegistry.ping = renderPing;
})();

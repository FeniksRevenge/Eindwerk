(() => {
  const POLLERS = new Map();

  function clearPoller(moduleId) {
    const current = POLLERS.get(moduleId);
    if (current) {
      clearInterval(current);
      POLLERS.delete(moduleId);
    }
  }

  function renderPlcModule({ moduleData, body }) {
    const deviceId = Number(moduleData?.deviceId || 0);
    const deviceIp = moduleData?.deviceIp || "";
    body.innerHTML = "";

    const container = document.createElement("div");
    container.className = "plc-module";

    const meta = document.createElement("div");
    meta.className = "plc-meta";
    meta.textContent = deviceId ? `Apparaat #${deviceId}${deviceIp ? ` · ${deviceIp}` : ""}` : "Geen PLC gekoppeld";

    const liveBadge = document.createElement("div");
    liveBadge.className = "plc-live-badge plc-live-badge-offline";
    liveBadge.textContent = "OFFLINE";

    const status = document.createElement("div");
    status.className = "plc-status plc-status-off";
    status.textContent = deviceId ? "PLC status laden..." : "Koppel eerst een PLC-apparaat aan deze module.";

    const list = document.createElement("div");
    list.className = "plc-io-list";

    const controls = document.createElement("div");
    controls.className = "plc-controls";
    const refreshButton = document.createElement("button");
    refreshButton.className = "device-action";
    refreshButton.type = "button";
    refreshButton.textContent = "Vernieuwen";
    controls.appendChild(refreshButton);

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "Naam";
    nameInput.className = "device-input";
    controls.appendChild(nameInput);

    const tagInput = document.createElement("input");
    tagInput.type = "text";
    tagInput.placeholder = "Tag (bv. I0.0, Q0.1, M0.0)";
    tagInput.className = "device-input";
    controls.appendChild(tagInput);

    const addButton = document.createElement("button");
    addButton.className = "device-action";
    addButton.type = "button";
    addButton.textContent = "Punt toevoegen";
    controls.appendChild(addButton);

    container.appendChild(meta);
    container.appendChild(liveBadge);
    container.appendChild(status);
    container.appendChild(controls);
    container.appendChild(list);
    body.appendChild(container);

    if (!deviceId) {
      return;
    }

    let busy = false;
    let turningTags = new Set();
    let turningTagsDirection = new Map();
    let configuredPoints = [];

    function closeDeleteModal() {
      const modal = body.querySelector('.plc-delete-modal');
      if (!modal) {
        return;
      }
      modal.classList.remove('open');
      window.setTimeout(() => modal.remove(), 180);
    }

    function showDeleteModal(point) {
      closeDeleteModal();
      return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'modal open plc-delete-modal';

        const backdrop = document.createElement('div');
        backdrop.className = 'modal-backdrop';

        const content = document.createElement('div');
        content.className = 'modal-content plc-confirm-modal-content';

        const header = document.createElement('div');
        header.className = 'modal-header';

        const title = document.createElement('h3');
        title.textContent = 'Punt verwijderen';

        const closeButton = document.createElement('button');
        closeButton.type = 'button';
        closeButton.className = 'modal-close';
        closeButton.textContent = '×';

        const bodyContent = document.createElement('div');
        bodyContent.className = 'modal-body';

        const message = document.createElement('p');
        message.append('Weet je zeker dat je ');
        const strongName = document.createElement('strong');
        strongName.textContent = String(point.name || point.tag || 'dit PLC-punt');
        message.appendChild(strongName);
        message.append(' wilt verwijderen?');

        const tagLine = document.createElement('p');
        tagLine.className = 'plc-confirm-subtext';
        tagLine.textContent = `Tag: ${String(point.tag || '-')}`;

        const actionBar = document.createElement('div');
        actionBar.className = 'plc-confirm-actions';

        const cancelButton = document.createElement('button');
        cancelButton.type = 'button';
        cancelButton.className = 'device-action plc-confirm-cancel';
        cancelButton.textContent = 'Annuleren';

        const confirmButton = document.createElement('button');
        confirmButton.type = 'button';
        confirmButton.className = 'device-action plc-confirm-delete';
        confirmButton.textContent = 'Verwijderen';

        const cancel = () => {
          closeDeleteModal();
          resolve(false);
        };

        const confirm = () => {
          closeDeleteModal();
          resolve(true);
        };

        backdrop.addEventListener('click', cancel);
        closeButton.addEventListener('click', cancel);
        cancelButton.addEventListener('click', cancel);
        confirmButton.addEventListener('click', confirm);

        header.appendChild(title);
        header.appendChild(closeButton);
        bodyContent.appendChild(message);
        bodyContent.appendChild(tagLine);
        actionBar.appendChild(cancelButton);
        actionBar.appendChild(confirmButton);
        content.appendChild(header);
        content.appendChild(bodyContent);
        content.appendChild(actionBar);
        modal.appendChild(backdrop);
        modal.appendChild(content);
        body.appendChild(modal);
      });
    }

    function configuredPointForTag(tag) {
      const cleanTag = String(tag || "").toUpperCase();
      return configuredPoints.find((point) => String(point.tag || "").toUpperCase() === cleanTag) || null;
    }

    async function loadConfiguredPoints() {
      const response = await fetch(`/api/device/${deviceId}/plc/points`);
      if (!response.ok) {
        throw new Error("PLC-punten konden niet geladen worden.");
      }
      const data = await response.json();
      configuredPoints = Array.isArray(data.points) ? data.points : [];
    }

    async function setPointValue(tag, value) {
      const response = await fetch(`/api/device/${deviceId}/plc/io/${encodeURIComponent(tag)}/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: value ? 1 : 0 }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.error) {
        throw new Error(payload.error || 'Schakelen mislukt.');
      }
      return payload;
    }

    function updatePlcOverallState(ioList, mode) {
      if (!Array.isArray(ioList) || !ioList.length) {
        if (mode === "live") {
          status.className = "plc-status plc-status-on";
          status.textContent = "PLC ONLINE";
          liveBadge.className = "plc-live-badge plc-live-badge-live";
          liveBadge.textContent = "LIVE";
        } else {
          status.className = "plc-status plc-status-turning";
          status.textContent = "SIMULATIE ACTIEF";
          liveBadge.className = "plc-live-badge plc-live-badge-sim";
          liveBadge.textContent = "SIMULATIE";
        }
        return;
      }

      if (turningTags.size > 0) {
        status.className = "plc-status plc-status-turning";
        const firstTag = turningTags.values().next().value;
        const direction = turningTagsDirection.get(firstTag);
        status.textContent = direction ? "PLC TURNING ON" : "PLC TURNING OFF";
      } else {
        if (mode === "live") {
          status.className = "plc-status plc-status-on";
          status.textContent = "PLC ONLINE";
        } else {
          status.className = "plc-status plc-status-turning";
          status.textContent = "SIMULATIE ACTIEF";
        }
      }

      if (mode === "live") {
        liveBadge.className = "plc-live-badge plc-live-badge-live";
        liveBadge.textContent = "LIVE";
      } else {
        liveBadge.className = "plc-live-badge plc-live-badge-sim";
        liveBadge.textContent = "SIMULATIE";
      }
    }

    async function fetchIo() {
      if (busy) {
        return;
      }
      busy = true;
      refreshButton.disabled = true;
      try {
        await loadConfiguredPoints();
        const response = await fetch(`/api/device/${deviceId}/plc/io`);
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          status.textContent = err.error ? `Fout: ${err.error}` : "PLC data niet beschikbaar.";
          list.innerHTML = "";
          return;
        }
        const data = await response.json();
        const ioList = Array.isArray(data.io) ? data.io : [];
        const source = data.source || "onbekend";
        const mode = data.mode || "onbekend";
        updatePlcOverallState(ioList, mode);
        status.textContent = `${status.textContent} · Bron: ${source} · ${ioList.length} punten`;
        renderIoRows(ioList, mode);
      } catch (error) {
        status.className = "plc-status plc-status-off";
        status.textContent = "PLC OFF · data niet bereikbaar";
        liveBadge.className = "plc-live-badge plc-live-badge-offline";
        liveBadge.textContent = "OFFLINE";
      } finally {
        refreshButton.disabled = false;
        busy = false;
      }
    }

    function renderIoRows(ioList, mode) {
      list.innerHTML = "";
      if (!ioList.length) {
        const empty = document.createElement("div");
        empty.className = "plc-io-empty";
        empty.textContent = configuredPoints.length ? "Geen PLC-data gevonden voor de geconfigureerde punten." : "Nog geen PLC-punten toegevoegd. Voeg hierboven een naam en tag toe.";
        list.appendChild(empty);
        return;
      }

      const sortedIoList = [...ioList].sort((first, second) => {
        const firstType = String(first.io_type || "").toLowerCase();
        const secondType = String(second.io_type || "").toLowerCase();
        const firstName = String(first.name || first.tag || "").toUpperCase();
        const secondName = String(second.name || second.tag || "").toUpperCase();

        const firstIsInput = firstType === "input";
        const secondIsInput = secondType === "input";
        if (firstIsInput !== secondIsInput) {
          return firstIsInput ? -1 : 1;
        }
        return firstName.localeCompare(secondName);
      });

      sortedIoList.forEach((io) => {
        const row = document.createElement("div");
        row.className = "plc-io-row";

        const left = document.createElement("div");
        left.className = "plc-io-left";
        const name = document.createElement("div");
        name.className = "plc-io-tag";
        name.textContent = String(io.name || io.tag || "?");
        const type = document.createElement("div");
        type.className = "plc-io-type";
        type.textContent = `${String(io.tag || "?").toUpperCase()} · ${String(io.io_type || "Onbekend")}`;
        left.appendChild(name);
        left.appendChild(type);

        const value = document.createElement("span");
        value.className = "plc-io-value";
        const isOn = Number(io.value) === 1;
        const tagValue = String(io.tag || "");
        if (turningTags.has(tagValue)) {
          value.dataset.state = "turning";
          const direction = turningTagsDirection.get(tagValue);
          value.textContent = direction ? "TURNING ON" : "TURNING OFF";
        } else {
          value.dataset.state = isOn ? "on" : "off";
          value.textContent = isOn ? "AAN" : "UIT";
        }

        const right = document.createElement("div");
        right.className = "plc-io-right";
        right.appendChild(value);

        const writable =
          mode === "live" &&
          Boolean(io.writable) &&
          String(io.io_type || "").toLowerCase() === "input";
        if (writable) {
          const toggleButton = document.createElement("button");
          toggleButton.className = "device-action";
          toggleButton.type = "button";
          toggleButton.textContent = "Toggle";

          const handleToggle = async () => {
            toggleButton.disabled = true;
            try {
              const tagValue = String(io.tag || "");
              const nextValue = !isOn;
              turningTags.add(tagValue);
              turningTagsDirection.set(tagValue, nextValue);
              updatePlcOverallState(ioList, mode);
              renderIoRows(ioList, mode);

              await setPointValue(tagValue, nextValue);
            } catch (error) {
              status.textContent = error.message || "Schakelen mislukt.";
            } finally {
              const cleanTag = String(io.tag || "");
              turningTags.delete(cleanTag);
              turningTagsDirection.delete(cleanTag);
              toggleButton.disabled = false;
              await fetchIo();
            }
          };

          toggleButton.addEventListener("click", handleToggle);
          right.appendChild(toggleButton);
        }

        const configuredPoint = configuredPointForTag(io.tag);
        if (configuredPoint) {
          const removeButton = document.createElement("button");
          removeButton.className = "device-action";
          removeButton.type = "button";
          removeButton.textContent = "Verwijderen";
          removeButton.addEventListener("click", async () => {
            const confirmed = await showDeleteModal(configuredPoint);
            if (!confirmed) {
              return;
            }
            removeButton.disabled = true;
            try {
              const response = await fetch(`/api/device/${deviceId}/plc/points/${configuredPoint.id}`, {
                method: "DELETE",
              });
              if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                status.textContent = err.error ? `Fout: ${err.error}` : "Verwijderen mislukt.";
                return;
              }
              await fetchIo();
            } catch (error) {
              status.textContent = "Verwijderen mislukt.";
            } finally {
              removeButton.disabled = false;
            }
          });
          right.appendChild(removeButton);
        }

        row.appendChild(left);
        row.appendChild(right);
        list.appendChild(row);
      });
    }

    addButton.addEventListener("click", async () => {
      const nameValue = String(nameInput.value || "").trim();
      const tagValue = String(tagInput.value || "").trim().toUpperCase();
      if (!nameValue || !tagValue) {
        status.textContent = "Geef een naam en tag op.";
        return;
      }
      addButton.disabled = true;
      try {
        const response = await fetch(`/api/device/${deviceId}/plc/points`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: nameValue, tag: tagValue }),
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          status.textContent = err.error ? `Fout: ${err.error}` : "Toevoegen mislukt.";
          return;
        }
        nameInput.value = "";
        tagInput.value = "";
        await fetchIo();
      } catch (error) {
        status.textContent = "Toevoegen mislukt.";
      } finally {
        addButton.disabled = false;
      }
    });

    refreshButton.addEventListener("click", () => {
      fetchIo();
    });

    clearPoller(moduleData.id);
    const timerId = setInterval(() => {
      const hostModule = document.querySelector(`.module[data-id="${moduleData.id}"], [data-plc-host-id="${moduleData.id}"]`);
      if (!hostModule) {
        clearPoller(moduleData.id);
        return;
      }
      fetchIo();
    }, 4000);
    POLLERS.set(moduleData.id, timerId);

    fetchIo();
  }

  window.ModuleRegistry = window.ModuleRegistry || {};
  window.ModuleRegistry.plc = renderPlcModule;
})();

const wrapper = document.querySelector(".device-wrapper");
const grid = document.getElementById("deviceGrid");
const template = document.getElementById("deviceModuleTemplate");
const moduleModal = document.getElementById("moduleModal");
const addModuleButton = document.getElementById("addModule");
const paletteItems = moduleModal ? Array.from(moduleModal.querySelectorAll(".module-item")) : [];
const settingsToggle = document.getElementById("settingsToggle");
const settingsMenu = document.getElementById("settingsMenu");
const themeToggle = document.getElementById("themeToggle");
const themeIcon = document.getElementById("themeIcon");
const MEMORY_KEY_PREFIX = "device-module-memory";
const LAYOUT_KEY_PREFIX = "device-layout";
const THEME_STORAGE_KEY = "dashboard-theme";

if (!wrapper || !grid || !template) {
  throw new Error("Device dashboard elements missing.");
}

let currentTheme = "light";
let currentLayout = [];

function applyTheme(theme) {
  currentTheme = theme === "dark" ? "dark" : "light";
  document.body.classList.toggle("theme-dark", currentTheme === "dark");
  if (themeIcon) {
    themeIcon.textContent = currentTheme === "dark" ? "🌙" : "☀️";
  }
  localStorage.setItem(THEME_STORAGE_KEY, currentTheme);
}

function openSettingsMenu() {
  if (!settingsMenu) {
    return;
  }
  settingsMenu.classList.add("open");
  settingsMenu.setAttribute("aria-hidden", "false");
}

function closeSettingsMenu() {
  if (!settingsMenu) {
    return;
  }
  settingsMenu.classList.remove("open");
  settingsMenu.setAttribute("aria-hidden", "true");
}

if (settingsToggle) {
  settingsToggle.addEventListener("click", () => {
    if (!settingsMenu) {
      return;
    }
    if (settingsMenu.classList.contains("open")) {
      closeSettingsMenu();
    } else {
      openSettingsMenu();
    }
  });
}

if (themeToggle) {
  themeToggle.addEventListener("click", async () => {
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: nextTheme, layout: currentLayout }),
    });
  });
}

if (addModuleButton) {
  addModuleButton.addEventListener("click", () => {
    openModal();
  });
}

paletteItems.forEach((item) => {
  item.setAttribute("draggable", "false");
  item.addEventListener("click", () => {
    addModuleFromPalette(item.dataset.module);
    closeModal();
  });
});

if (moduleModal) {
  moduleModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.close === "true") {
      closeModal();
    }
    if (target instanceof HTMLElement && target.classList.contains("modal-close")) {
      closeModal();
    }
  });
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  if (target.closest("#settingsToggle") || target.closest("#settingsMenu")) {
    return;
  }
  closeSettingsMenu();
});

async function loadSettings() {
  const response = await fetch("/api/settings");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  currentTheme = data.theme || "light";
  currentLayout = data.layout || [];
  applyTheme(currentTheme);
}

const deviceId = wrapper.dataset.deviceId;
const deviceIp = wrapper.dataset.deviceIp;
const allowedTerminalCommands = new Set(["ping", "tracert", "nslookup"]);
const moduleCatalog = window.SharedModules?.moduleCatalog || {};
const MULTI_MODULE_KEYS = window.SharedModules?.MULTI_MODULE_KEYS || new Set();
const statsState = {
  api: "idle",
  terminal: "idle",
  ping: "idle",
};
const state = {
  modules: [],
  draggingId: null,
  draggingNode: null,
  resizingId: null,
};
let lastDragPosition = null;
let dragFrame = null;
const transparentDragImage = (() => {
  const image = new Image();
  image.src = "data:image/gif;base64,R0lGODlhAQABAAAAACw=";
  return image;
})();

function appendLine(outputEl, text) {
  const line = document.createElement("div");
  line.textContent = text;
  outputEl.appendChild(line);
  outputEl.scrollTop = outputEl.scrollHeight;
}

function getMemoryKey() {
  return `${MEMORY_KEY_PREFIX}-${deviceId}`;
}

function getLayoutKey() {
  return `${LAYOUT_KEY_PREFIX}-${deviceId}`;
}

function loadMemory() {
  try {
    const raw = sessionStorage.getItem(getMemoryKey());
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return parsed;
    }
  } catch (error) {
    return {};
  }
  return {};
}

function saveMemory(data) {
  try {
    sessionStorage.setItem(getMemoryKey(), JSON.stringify(data));
  } catch (error) {
    // ignore
  }
}

function updateMemory(key, patch) {
  const memory = loadMemory();
  const existing = memory[key] && typeof memory[key] === "object" ? memory[key] : {};
  memory[key] = { ...existing, ...patch };
  saveMemory(memory);
}

function loadLayout() {
  try {
    const raw = sessionStorage.getItem(getLayoutKey());
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed;
    }
  } catch (error) {
    return null;
  }
  return null;
}

function saveLayout() {
  try {
    sessionStorage.setItem(getLayoutKey(), JSON.stringify(state.modules));
  } catch (error) {
    // ignore
  }
}

function parseDelay(output) {
  const match = output.match(/time[=<]\s*(\d+)ms/i);
  if (match) {
    return `${match[1]} ms`;
  }
  return "Failed";
}

async function runPing(host, outputEl) {
  const raw = String(host || "").trim();
  if (!raw) {
    outputEl.textContent = "Geef max 4 IP's in.";
    updateMemory("ping", { output: outputEl.textContent, pingHost: raw });
    setStatsState("ping", "idle");
    return;
  }
  const entries = raw
    .split(/[,\s]+/)
    .map((value) => value.trim())
    .filter(Boolean)
    .slice(0, 4);
  if (!entries.length) {
    outputEl.textContent = "Geef max 4 IP's in.";
    setStatsState("ping", "idle");
    return;
  }
  setStatsState("ping", "running");
  outputEl.textContent = "Pingen...";
  updateMemory("ping", { output: outputEl.textContent, pingHost: raw });

  const results = [];
  for (const ip of entries) {
    const response = await fetch("/api/ping", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host: ip }),
    });
    const data = await response.json();
    if (!response.ok) {
      results.push(`${ip} - Failed`);
      continue;
    }
    const delay = parseDelay(data.output || "");
    results.push(`${ip} - ${delay}`);
  }
  outputEl.textContent = results.join("\n");
  updateMemory("ping", { output: outputEl.textContent, pingHost: raw });
  setStatsState("ping", "idle");
}

async function runTerminal(command, outputEl) {
  setStatsState("terminal", "running");
  const response = await fetch("/api/terminal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
  const data = await response.json();
  if (!response.ok) {
    appendLine(outputEl, data.error || "Command failed.");
    setStatsState("terminal", "idle");
    updateMemory("terminal", { lines: getTerminalLines(outputEl) });
    return;
  }
  if (data.output) {
    data.output.split("\n").forEach((line) => appendLine(outputEl, line));
  }
  setStatsState("terminal", "idle");
  updateMemory("terminal", { lines: getTerminalLines(outputEl) });
}

function getTerminalLines(outputEl) {
  return Array.from(outputEl.children).map((line) => line.textContent || "");
}

function setStatsState(key, value) {
  if (!statsState[key]) {
    return;
  }
  statsState[key] = value;
  document.querySelectorAll(".stats-item").forEach((item) => {
    updateStatsItem(item);
  });
}

function updateStatsItem(item) {
  const key = item.dataset.stat;
  if (!key || !statsState[key]) {
    return;
  }
  const dot = item.querySelector(".stats-dot");
  const label = item.querySelector(".stats-label");
  const state = statsState[key];
  item.dataset.state = state;
  if (label) {
    label.textContent = state === "running" ? "Running" : state === "offline" ? "Offline" : "Idle";
  }
  if (dot) {
    dot.setAttribute("title", label?.textContent || "");
  }
}

function createModule(title, key) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.querySelector(".module-title").textContent = title;
  node.dataset.key = key || "";
  return node;
}

function generateId() {
  if (crypto && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function buildModule(moduleKey) {
  const template = moduleCatalog[moduleKey];
  if (!template) {
    return null;
  }
  return {
    id: `module-${moduleKey}-${generateId()}`,
    key: moduleKey,
    title: template.title,
    content: template.content,
    x: 1,
    y: 1,
    w: 2,
    h: 2,
    locked: false,
  };
}

function renderPalette() {
  const usedKeys = new Set(state.modules.map((item) => item.key).filter(Boolean));
  paletteItems.forEach((item) => {
    const key = item.dataset.module;
    const isUsed = usedKeys.has(key);
    if (MULTI_MODULE_KEYS.has(key)) {
      item.style.display = "block";
      return;
    }
    item.style.display = isUsed ? "none" : "block";
  });
}

function openModal() {
  if (!moduleModal) {
    return;
  }
  moduleModal.classList.add("open");
  moduleModal.setAttribute("aria-hidden", "false");
}

function closeModal() {
  if (!moduleModal) {
    return;
  }
  moduleModal.classList.remove("open");
  moduleModal.setAttribute("aria-hidden", "true");
}

function addModuleFromPalette(moduleKey) {
  const newModule = buildModule(moduleKey);
  if (!newModule) {
    return;
  }
  const spot = findFirstAvailableSpot(newModule);
  if (!spot) {
    return;
  }
  newModule.x = spot.x;
  newModule.y = spot.y;
  state.modules.push(newModule);
  renderModules();
  renderPalette();
  saveLayout();
}

function toggleLock(id) {
  const target = state.modules.find((item) => item.id === id);
  if (!target) {
    return;
  }
  target.locked = !target.locked;
  renderModules();
  saveLayout();
}

function getGridMetrics() {
  const rect = grid.getBoundingClientRect();
  const columnWidth = rect.width / 6;
  const rowStep = 120 + 12;
  return { columnWidth, rowStep };
}

function getMaxRows() {
  const rowStep = 120 + 12;
  const height = grid.clientHeight || 0;
  return Math.max(1, Math.floor(height / rowStep));
}

function isOverlapping(candidate, ignoreId) {
  return state.modules.some((item) => {
    if (item.id === ignoreId) {
      return false;
    }
    const horizontal = candidate.x < item.x + item.w && candidate.x + candidate.w > item.x;
    const vertical = candidate.y < item.y + item.h && candidate.y + candidate.h > item.y;
    return horizontal && vertical;
  });
}

function findFirstAvailableSpot(moduleData) {
  const maxRows = 6;
  for (let y = 1; y <= maxRows; y += 1) {
    for (let x = 1; x <= 6; x += 1) {
      const trial = { ...moduleData, x, y };
      if (!isOverlapping(trial, moduleData.id)) {
        return { x, y };
      }
    }
  }
  return null;
}

function applyResize(target, nextW, nextH, nextX, nextY) {
  const maxW = 7 - nextX;
  const maxRows = getMaxRows();
  const maxH = Math.max(1, maxRows - nextY + 1);
  const candidate = {
    ...target,
    x: Math.max(1, nextX),
    y: Math.max(1, nextY),
    w: Math.min(nextW, maxW),
    h: Math.min(Math.max(1, nextH), maxH),
  };
  if (isOverlapping(candidate, target.id)) {
    return;
  }
  target.x = candidate.x;
  target.y = candidate.y;
  target.w = candidate.w;
  target.h = candidate.h;
  renderModules();
}

function startResize(event, id, direction) {
  const target = state.modules.find((item) => item.id === id);
  if (!target || target.locked) {
    return;
  }
  state.resizingId = id;
  const startX = event.clientX;
  const startY = event.clientY;
  const startW = target.w;
  const startH = target.h;
  const startXPos = target.x;
  const startYPos = target.y;
  const { columnWidth, rowStep } = getGridMetrics();

  function onMove(moveEvent) {
    const dx = moveEvent.clientX - startX;
    const dy = moveEvent.clientY - startY;
    let nextW = startW;
    let nextH = startH;
    let nextX = startXPos;
    let nextY = startYPos;

    if (direction === "right") {
      nextW = Math.max(1, Math.round(startW + dx / columnWidth));
    }
    if (direction === "left") {
      const delta = Math.round(dx / columnWidth);
      nextW = Math.max(1, startW - delta);
      nextX = Math.min(startXPos + delta, startXPos + startW - 1);
    }
    if (direction === "bottom") {
      nextH = Math.max(1, Math.round(startH + dy / rowStep));
    }
    if (direction === "top") {
      const delta = Math.round(dy / rowStep);
      nextH = Math.max(1, startH - delta);
      nextY = Math.min(startYPos + delta, startYPos + startH - 1);
    }

    applyResize(target, nextW, nextH, nextX, nextY);
    saveLayout();
  }

  function onUp() {
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    state.resizingId = null;
    renderModules();
  }

  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

function snapToGrid(clientX, clientY) {
  const rect = grid.getBoundingClientRect();
  const columnWidth = rect.width / 6;
  const rowHeight = 120 + 12;
  const relativeX = Math.max(0, clientX - rect.left);
  const relativeY = Math.max(0, clientY - rect.top);
  const x = Math.min(6, Math.max(1, Math.floor(relativeX / columnWidth) + 1));
  const y = Math.max(1, Math.floor(relativeY / rowHeight) + 1);
  return { x, y };
}

function updateModulePosition(id, x, y, skipRender = false) {
  const target = state.modules.find((item) => item.id === id);
  if (!target) {
    return false;
  }
  const maxRows = getMaxRows();
  const boundedX = Math.min(6, Math.max(1, x));
  const boundedY = Math.min(maxRows - target.h + 1, Math.max(1, y));
  const candidate = { ...target, x: boundedX, y: boundedY };
  if (isOverlapping(candidate, target.id)) {
    return false;
  }
  target.x = candidate.x;
  target.y = candidate.y;
  if (!skipRender) {
    renderModules();
    saveLayout();
  }
  return true;
}

function renderModules() {
  grid.innerHTML = "";
  if (addModuleButton) {
    grid.appendChild(addModuleButton);
  }
  state.modules.forEach((moduleData) => {
    const node = createModule(moduleData.title, moduleData.key);
    node.dataset.id = moduleData.id;
    node.classList.toggle("locked", Boolean(moduleData.locked));
    node.style.gridColumn = `${moduleData.x} / span ${moduleData.w}`;
    node.style.gridRow = `${moduleData.y} / span ${moduleData.h}`;
    const body = node.querySelector(".module-body");
    const resizeHandles = node.querySelectorAll(".resize-handle");
    resizeHandles.forEach((handle) => {
      handle.addEventListener("mousedown", (event) => {
        event.preventDefault();
        if (moduleData.locked) {
          return;
        }
        const direction = handle.classList.contains("resize-right")
          ? "right"
          : handle.classList.contains("resize-left")
            ? "left"
            : handle.classList.contains("resize-top")
              ? "top"
              : "bottom";
        startResize(event, moduleData.id, direction);
      });
    });

    const lockButton = node.querySelector(".module-lock");
    if (lockButton) {
      lockButton.textContent = moduleData.locked ? "🔒" : "🔓";
      lockButton.addEventListener("click", () => {
        toggleLock(moduleData.id);
      });
    }

    const removeButton = node.querySelector(".module-remove");
    if (removeButton) {
      removeButton.disabled = moduleData.locked;
      removeButton.title = moduleData.locked ? "Ontgrendel om te verwijderen" : "Verwijderen";
      removeButton.addEventListener("click", () => {
        if (moduleData.locked) {
          return;
        }
        state.modules = state.modules.filter((item) => item.id !== moduleData.id);
        renderModules();
        renderPalette();
        saveLayout();
      });
    }

    node.addEventListener("dragstart", (event) => {
      if (moduleData.locked) {
        event.preventDefault();
        return;
      }
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        event.preventDefault();
        return;
      }
      if (event.dataTransfer) {
        event.dataTransfer.setDragImage(transparentDragImage, 0, 0);
      }
      state.draggingId = moduleData.id;
      state.draggingNode = node;
      event.dataTransfer.setData("module-id", moduleData.id);
      event.dataTransfer.effectAllowed = "move";
    });

    node.addEventListener("dragend", () => {
      if (state.draggingId && lastDragPosition) {
        const snapped = snapToGrid(lastDragPosition.x, lastDragPosition.y);
        updateModulePosition(state.draggingId, snapped.x, snapped.y);
      }
      state.draggingId = null;
      state.draggingNode = null;
    });

    node.addEventListener("dragover", (event) => {
      event.preventDefault();
    });

    node.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!state.draggingId) {
        return;
      }
      const { x, y } = snapToGrid(event.clientX, event.clientY);
      updateModulePosition(state.draggingId, x, y);
    });

    if (body && window.SharedModules?.renderModuleBody) {
      const moduleMemory = loadMemory()[moduleData.key] || {};
      window.SharedModules.renderModuleBody({
        moduleData,
        body,
        moduleMemory,
        handlers: {
          updateModuleMemory: (_id, patch) => updateMemory(moduleData.key, patch),
          setStatsState,
          runPing: (host, output) => runPing(host, output),
          runTerminal,
          stopTerminal: () => {},
          appendTerminalLine: appendLine,
          clearTerminalOutput: (output) => {
            output.innerHTML = "";
            updateMemory("terminal", { lines: [] });
          },
          getTerminalLines: (output) => Array.from(output.children).map((line) => line.textContent || ""),
          renderStats: (target) => {
            target.innerHTML =
              "<div class=\"stats-list\">\n  <div class=\"stats-item\" data-stat=\"api\"><span class=\"stats-dot\"></span><span>API status</span><span class=\"stats-label\"></span></div>\n  <div class=\"stats-item\" data-stat=\"terminal\"><span class=\"stats-dot\"></span><span>Terminal</span><span class=\"stats-label\"></span></div>\n  <div class=\"stats-item\" data-stat=\"ping\"><span class=\"stats-dot\"></span><span>Ping</span><span class=\"stats-label\"></span></div>\n</div>";
            target.querySelectorAll(".stats-item").forEach((item) => updateStatsItem(item));
          },
        },
      });
    }

    grid.appendChild(node);
  });
}
const cachedTheme = localStorage.getItem(THEME_STORAGE_KEY);
if (cachedTheme) {
  applyTheme(cachedTheme);
}
loadSettings();
function bootstrapLayout() {
  const saved = loadLayout();
  if (Array.isArray(saved) && saved.length) {
    state.modules = saved;
    renderModules();
    renderPalette();
    return;
  }
  const initial = [
    { id: "module-info", key: "info", title: "Info / Notities", x: 1, y: 1, w: 3, h: 2 },
    { id: "module-stats", key: "stats", title: "Status", x: 4, y: 1, w: 3, h: 2 },
    { id: "module-ping", key: "ping", title: "Ping", x: 1, y: 3, w: 3, h: 2 },
    { id: "module-terminal", key: "terminal", title: "Terminal", x: 4, y: 3, w: 3, h: 3 },
  ];
  state.modules = initial;
  renderModules();
  renderPalette();
  saveLayout();
}

grid.addEventListener("dragover", (event) => {
  event.preventDefault();
  lastDragPosition = { x: event.clientX, y: event.clientY };
  if (!state.draggingId || dragFrame) {
    return;
  }
  dragFrame = requestAnimationFrame(() => {
    dragFrame = null;
    if (!state.draggingId || !lastDragPosition) {
      return;
    }
    const snapped = snapToGrid(lastDragPosition.x, lastDragPosition.y);
    const applied = updateModulePosition(state.draggingId, snapped.x, snapped.y, true);
    if (state.draggingNode) {
      const target = state.modules.find((m) => m.id === state.draggingId);
      const x = applied ? snapped.x : target?.x || snapped.x;
      const y = applied ? snapped.y : target?.y || snapped.y;
      state.draggingNode.style.gridColumn = `${x} / span ${target?.w || 1}`;
      state.draggingNode.style.gridRow = `${y} / span ${target?.h || 1}`;
    }
  });
});

grid.addEventListener("drop", (event) => {
  event.preventDefault();
  const { x, y } = snapToGrid(event.clientX, event.clientY);
  if (state.draggingId) {
    updateModulePosition(state.draggingId, x, y);
  }
  lastDragPosition = null;
});

bootstrapLayout();

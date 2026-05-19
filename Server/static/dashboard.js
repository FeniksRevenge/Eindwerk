const grid = document.getElementById("grid");
const moduleTemplate = document.getElementById("moduleTemplate");
const themeToggle = document.getElementById("themeToggle");
const themeIcon = document.getElementById("themeIcon");
const settingsToggle = document.getElementById("settingsToggle");
const settingsMenu = document.getElementById("settingsMenu");
const settingsAlertDot = document.getElementById("settingsAlertDot");
const profileButton = document.getElementById("profileButton") || document.querySelector('button[id="profileButton"]');
const profileModal = document.getElementById("profileModal") || document.querySelector('div[id="profileModal"]');
const profileUsername = document.getElementById("profileUsername");
const profileRole = document.getElementById("profileRole");
const profileCategory = document.getElementById("profileCategory");
const profileCreatedAt = document.getElementById("profileCreatedAt");
const profileOldPassword = document.getElementById("profileOldPassword");
const profileNewPassword = document.getElementById("profileNewPassword");
const profileNewPasswordRepeat = document.getElementById("profileNewPasswordRepeat");
const profileChangePasswordButton = document.getElementById("profileChangePasswordButton");
const profileStatus = document.getElementById("profileStatus");
const resetRequestsButton = document.getElementById("resetRequestsButton");
const resetRequestsBadge = document.getElementById("resetRequestsBadge");
const resetRequestsModal = document.getElementById("resetRequestsModal");
const resetRequestsList = document.getElementById("resetRequestsList");
const resetRequestsStatus = document.getElementById("resetRequestsStatus");
const statsSettingsModal = document.getElementById("statsSettingsModal");
const statsSettingsList = document.getElementById("statsSettingsList");
const statsSettingsSave = document.getElementById("statsSettingsSave");
const statsSettingsCount = document.getElementById("statsSettingsCount");
const moduleModal = document.getElementById("moduleModal");
const addModuleButton = document.getElementById("addModule");
const menuItems = Array.from(document.querySelectorAll(".menu-item"));
const panels = Array.from(document.querySelectorAll(".panel"));
const paletteItems = Array.from(moduleModal.querySelectorAll(".module-item"));
const deviceForm = document.getElementById("deviceForm");
const deviceList = document.getElementById("deviceList");
const deviceDiscoverList = document.getElementById("deviceDiscoverList");
const deviceDiscoverModal = document.getElementById("deviceDiscoverModal");
const deviceDiscoverClose = document.getElementById("deviceDiscoverClose");
const deviceDiscoverRefresh = document.getElementById("deviceDiscoverRefresh");
const deviceDiscoverFilterPlc = document.getElementById("deviceDiscoverFilterPlc");
const deviceDiscoverScanPlcOnly = document.getElementById("deviceDiscoverScanPlcOnly");
const deviceDiscoverAddAllPlc = document.getElementById("deviceDiscoverAddAllPlc");
const deviceDiscoverStatus = document.getElementById("deviceDiscoverStatus");
const deviceDiscoverCandidates = document.getElementById("deviceDiscoverCandidates");
const plcModuleModal = document.getElementById("plcModuleModal");
const plcModuleModalClose = document.getElementById("plcModuleModalClose");
const plcModuleModalTitle = document.getElementById("plcModuleModalTitle");
const plcModuleModalBody = document.getElementById("plcModuleModalBody");
const accountsMenuItem = document.querySelector(".menu-item[data-section=\"accounts\"]");
const opsMenuItem = document.querySelector(".menu-item[data-section=\"admin\"]");
const adminUserSelect = document.getElementById("adminUserSelect");
const adminCanViewDevices = document.getElementById("adminCanViewDevices");
const adminCanManageDevices = document.getElementById("adminCanManageDevices");
const adminModules = document.getElementById("adminModules");
const adminDevices = document.getElementById("adminDevices");
const adminActivity = document.getElementById("adminActivity");
const adminSave = document.getElementById("adminSave");
const adminDeleteUser = document.getElementById("adminDeleteUser");
const adminStatus = document.getElementById("adminStatus");
const groupForm = document.getElementById("groupForm");
const groupsList = document.getElementById("groupsList");
const userForm = document.getElementById("userForm");
const usersList = document.getElementById("usersList");
const groupParentSelect = groupForm ? groupForm.querySelector("select[name=\"parent\"]") : null;
const selectedGroupLabel = document.getElementById("selectedGroupLabel");
const userEditModal = document.getElementById("userEditModal");
const userEditName = document.getElementById("userEditName");
const userEditCategory = document.getElementById("userEditCategory");
const userEditRole = document.getElementById("userEditRole");
const userEditGroups = document.getElementById("userEditGroups");
const userEditSave = document.getElementById("userEditSave");
const userEditStatus = document.getElementById("userEditStatus");
const openGroupCreateButton = document.getElementById("openGroupCreate");
const openUserCreateButton = document.getElementById("openUserCreate");
const accountsSearch = document.getElementById("accountsSearch");
const accountsUserPanel = document.getElementById("accountsUserPanel");
const accountsUserPanelHeader = document.getElementById("accountsUserPanelHeader");
const accountsUserPanelTitle = document.getElementById("accountsUserPanelTitle");
const accountsUserPanelBody = document.getElementById("accountsUserPanelBody");
const accountsUserPanelClose = document.getElementById("accountsUserPanelClose");
const accountsUserCreateForm = document.getElementById("accountsUserCreateForm");
const accountsGroupPanel = document.getElementById("accountsGroupPanel");
const accountsGroupPanelHeader = document.getElementById("accountsGroupPanelHeader");
const accountsGroupPanelTitle = document.getElementById("accountsGroupPanelTitle");
const accountsGroupPanelClose = document.getElementById("accountsGroupPanelClose");
const accountsGroupCreateForm = document.getElementById("accountsGroupCreateForm");
const accountsGroupParentLabel = document.getElementById("accountsGroupParentLabel");
const accountsGroupParentId = document.getElementById("accountsGroupParentId");
const accountsGroupSearch = document.getElementById("accountsGroupSearch");
const accountsUserSearch = document.getElementById("accountsUserSearch");
const accountsGroupList = document.getElementById("accountsGroupList");
const accountsUserList = document.getElementById("accountsUserList");
const accountsGroupForm = document.getElementById("accountsGroupForm");
const accountsUserForm = document.getElementById("accountsUserForm");
const accountsGroupParentSelect = document.getElementById("accountsGroupParentSelect");
const accountsUserGroupSelect = document.getElementById("accountsUserGroupSelect");
const accountsGroupStatus = document.getElementById("accountsGroupStatus");
const accountsUserStatus = document.getElementById("accountsUserStatus");
const accountsSelectedLabel = document.getElementById("accountsSelectedLabel");
const accountsGroupCreateToggle = document.getElementById("accountsGroupCreateToggle");
const accountsUserCreateToggle = document.getElementById("accountsUserCreateToggle");
const accountsGroupModal = document.getElementById("accountsGroupModal");
const accountsUserModal = document.getElementById("accountsUserModal");
const MEMORY_KEY = "module-memory";
const terminalControllers = new Map();
let permissions = null;
let allowedModules = null;
let currentUserId = null;
const ACTIVE_PANEL_KEY = "active-panel";
const THEME_STORAGE_KEY = "dashboard-theme";
const statsState = {
  api: { state: "idle", label: null },
  terminal: { state: "idle", label: null },
  ping: { state: "idle", label: null },
};

const MAX_STATS_ITEMS = 4;
const STATS_PING_INTERVAL = 5000;
let deviceCache = [];
let activeStatsModuleId = null;
const statsPingState = new Map();
let statsTickerId = null;
let statsPingLoopId = null;
let toastContainer = null;
let adminActivityTimer = null;
let resetRequestsTimer = null;
let latestPendingResetCount = null;
let selectedGroupId = null;
let cachedGroups = [];
let cachedUsers = [];
let cachedAdminUsersById = new Map();
let activeEditUser = null;
let accountsGroupSearchTerm = "";
let accountsUserSearchTerm = "";
const collapsedGroupIds = new Set();

function normalizeCategoryValue(category) {
  const value = String(category || "student").trim().toLowerCase();
  if (value === "teacher_plus") {
    return "authorized_teacher";
  }
  if (value === "student_plus") {
    return "authorized_student";
  }
  return value;
}

function categoryToSelectValue(category) {
  const normalized = normalizeCategoryValue(category);
  if (normalized === "authorized_teacher") {
    return "teacher_plus";
  }
  if (normalized === "authorized_student") {
    return "student_plus";
  }
  return normalized;
}

function formatCategoryLabel(category) {
  const normalized = normalizeCategoryValue(category);
  if (normalized === "authorized_student") {
    return "student+";
  }
  if (normalized === "authorized_teacher") {
    return "leerkracht+";
  }
  if (normalized === "teacher") {
    return "leerkracht";
  }
  return "student";
}

function isStudentCategory(category) {
  const normalized = normalizeCategoryValue(category);
  return normalized === "student" || normalized === "authorized_student";
}

function isSuperAuthorUser(user) {
  return Boolean(user?.is_super_author);
}

function setAccountsUserStatus(message) {
  if (!accountsUserStatus) {
    return;
  }
  accountsUserStatus.textContent = message || "";
}

function setAccountsGroupStatus(message) {
  if (!accountsGroupStatus) {
    return;
  }
  accountsGroupStatus.textContent = message || "";
}

const state = {
  theme: "light",
  modules: [],
  draggingId: null,
  resizingId: null,
};

const moduleCatalog = window.SharedModules?.moduleCatalog || {};
const MULTI_MODULE_KEYS = window.SharedModules?.MULTI_MODULE_KEYS || new Set();

function loadModuleMemory() {
  try {
    const raw = sessionStorage.getItem(MEMORY_KEY);
    if (!raw) {
      return {};
    }
    const data = JSON.parse(raw);
    if (data && typeof data === "object") {
      return data;
    }
  } catch (error) {
    return {};
  }
  return {};
}

function saveModuleMemory(data) {
  try {
    sessionStorage.setItem(MEMORY_KEY, JSON.stringify(data));
  } catch (error) {
    // Ignore storage errors.
  }
}

function setDeviceCache(devices) {
  deviceCache = Array.isArray(devices) ? devices : [];
  refreshStatsDevicesUI();
}

function getStatsSelection(moduleId) {
  const memory = loadModuleMemory();
  const stored = Array.isArray(memory[moduleId]?.selectedStatItems)
    ? memory[moduleId].selectedStatItems
    : null;
  if (!stored) {
    return ["api"];
  }
  if (!stored.length) {
    return [];
  }
  const normalized = stored
    .map((item) => {
      if (typeof item === "number") {
        return `device:${item}`;
      }
      if (typeof item === "string") {
        if (item === "api") {
          return item;
        }
        if (item.startsWith("device:")) {
          return item;
        }
      }
      return null;
    })
    .filter(Boolean);
  return normalized.slice(0, MAX_STATS_ITEMS);
}

function saveStatsSelection(moduleId, selection) {
  const next = Array.from(new Set(selection)).slice(0, MAX_STATS_ITEMS);
  updateModuleMemory(moduleId, { selectedStatItems: next });
}

function openStatsSettings(moduleId) {
  if (!statsSettingsModal || !statsSettingsList || !statsSettingsSave) {
    return;
  }
  activeStatsModuleId = moduleId;
  statsSettingsList.innerHTML = "";
  if (statsSettingsCount) {
    statsSettingsCount.textContent = "";
  }
  statsSettingsModal.classList.add("open");
  statsSettingsModal.setAttribute("aria-hidden", "false");
  loadStatsSettingsDevices(moduleId);
}

function closeStatsSettings() {
  if (!statsSettingsModal) {
    return;
  }
  statsSettingsModal.classList.remove("open");
  statsSettingsModal.setAttribute("aria-hidden", "true");
  activeStatsModuleId = null;
}

async function loadStatsSettingsDevices(moduleId) {
  if (!statsSettingsList) {
    return;
  }
  if (permissions && !permissions.can_view_devices) {
    statsSettingsList.textContent = "Geen toegang tot apparaten.";
    return;
  }
  const response = await fetch("/api/devices");
  if (!response.ok) {
    statsSettingsList.textContent = "Kon apparaten niet laden.";
    return;
  }
  const data = await response.json();
  const devices = Array.isArray(data.devices) ? data.devices : [];
  setDeviceCache(devices);
  const selected = new Set(getStatsSelection(moduleId));
  renderStatsSettingsList(devices, selected, moduleId);
}

function renderStatsSettingsList(devices, selected, moduleId) {
  if (!statsSettingsList) {
    return;
  }
  statsSettingsList.innerHTML = "";
  const deviceMeta = new Map(devices.map((device) => [device.id, device]));
  const updateCount = () => {
    if (statsSettingsCount) {
      statsSettingsCount.textContent = `${selected.size}/${MAX_STATS_ITEMS} geselecteerd`;
    }
  };
  updateCount();
  const apiLabel = document.createElement("label");
  apiLabel.className = "stats-settings-item";
  const apiCheckbox = document.createElement("input");
  apiCheckbox.type = "checkbox";
  apiCheckbox.dataset.statKey = "api";
  apiCheckbox.checked = selected.has("api");
  const apiText = document.createElement("span");
  apiText.textContent = "API status";
  apiLabel.appendChild(apiCheckbox);
  apiLabel.appendChild(apiText);
  apiCheckbox.addEventListener("change", () => {
    if (apiCheckbox.checked) {
      if (selected.size >= MAX_STATS_ITEMS) {
        apiCheckbox.checked = false;
        return;
      }
      selected.add("api");
    } else {
      selected.delete("api");
    }
    updateCount();
    refreshStatsSettingsAvailability(selected);
  });
  statsSettingsList.appendChild(apiLabel);

  devices.forEach((device) => {
    const label = document.createElement("label");
    label.className = "stats-settings-item";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    const key = `device:${device.id}`;
    checkbox.dataset.deviceId = String(device.id);
    checkbox.checked = selected.has(key);
    const text = document.createElement("span");
    text.textContent = `${device.name} (${device.ip})`;
    label.appendChild(checkbox);
    label.appendChild(text);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        if (selected.size >= MAX_STATS_ITEMS) {
          checkbox.checked = false;
          return;
        }
        selected.add(key);
      } else {
        selected.delete(key);
      }
      updateCount();
      refreshStatsSettingsAvailability(selected);
    });
    statsSettingsList.appendChild(label);
  });
  refreshStatsSettingsAvailability(selected);
  statsSettingsSave.onclick = () => {
    if (!activeStatsModuleId) {
      return;
    }
    const selection = Array.from(selected);
    const selectedDeviceMeta = {};
    selection.forEach((item) => {
      if (!item.startsWith("device:")) {
        return;
      }
      const id = Number(item.split(":")[1]);
      const device = deviceMeta.get(id);
      if (device) {
        selectedDeviceMeta[id] = { name: device.name, ip: device.ip, mac: device.mac };
      }
    });
    updateModuleMemory(activeStatsModuleId, { selectedDeviceMeta });
    saveStatsSelection(activeStatsModuleId, selection);
    refreshStatsDevicesUI();
    const moduleEl = document.querySelector(`.module[data-id="${activeStatsModuleId}"]`);
    const statsList = moduleEl?.querySelector(".stats-list");
    if (statsList) {
      renderStatsSelection(statsList, activeStatsModuleId);
    } else {
      renderModules();
    }
    refreshDeviceStats();
    closeStatsSettings();
  };
}

function refreshStatsSettingsAvailability(selected) {
  if (!statsSettingsList) {
    return;
  }
  statsSettingsList
    .querySelectorAll("input[type=\"checkbox\"]")
    .forEach((input) => {
      if (input.checked) {
        input.disabled = false;
        return;
      }
      input.disabled = selected.size >= MAX_STATS_ITEMS;
    });
}

function ensureStatsSelectionValid(moduleId) {
  const memory = loadModuleMemory();
  if (!memory[moduleId]) {
    saveStatsSelection(moduleId, ["api"]);
    return;
  }
  const selection = getStatsSelection(moduleId);
  saveStatsSelection(moduleId, selection);
}

function updateModuleMemory(id, patch) {
  if (!id) {
    return;
  }
  const memory = loadModuleMemory();
  const existing = memory[id] && typeof memory[id] === "object" ? memory[id] : {};
  memory[id] = { ...existing, ...patch };
  saveModuleMemory(memory);
}

function clearModuleMemory(id) {
  if (!id) {
    return;
  }
  const memory = loadModuleMemory();
  if (memory[id]) {
    delete memory[id];
    saveModuleMemory(memory);
  }
}

function getTerminalLines(outputEl) {
  return Array.from(outputEl.children).map((line) => line.textContent || "");
}

function applyPermissions() {
  if (!permissions) {
    return;
  }
  allowedModules = new Set(permissions.allowed_modules || []);
  const devicesItem = menuItems.find((item) => item.dataset.section === "devices");
  if (devicesItem) {
    devicesItem.style.display = permissions.can_view_devices ? "block" : "none";
  }
  if (accountsMenuItem) {
    accountsMenuItem.hidden = !permissions.can_view_accounts;
  }
  if (opsMenuItem) {
    opsMenuItem.hidden = !permissions.can_manage_student_settings;
  }
  if (!permissions.can_view_devices) {
    const devicesPanel = panels.find((panel) => panel.dataset.panel === "devices");
    if (devicesPanel) {
      devicesPanel.hidden = true;
    }
    setActivePanel("dashboard");
  }
  if (!permissions.can_manage_student_settings) {
    const adminPanel = panels.find((panel) => panel.dataset.panel === "admin");
    if (adminPanel) {
      adminPanel.hidden = true;
    }
  }
  if (!permissions.can_view_accounts) {
    const accountsPanel = panels.find((panel) => panel.dataset.panel === "accounts");
    if (accountsPanel) {
      accountsPanel.hidden = true;
    }
  }
  if (openGroupCreateButton) {
    openGroupCreateButton.style.display = permissions.is_admin ? "inline-flex" : "none";
  }
  if (openUserCreateButton) {
    openUserCreateButton.style.display = permissions.is_admin ? "inline-flex" : "none";
  }
  if (accountsGroupCreateToggle) {
    accountsGroupCreateToggle.style.display = permissions.is_admin ? "inline-flex" : "none";
  }
  if (accountsUserCreateToggle) {
    accountsUserCreateToggle.style.display = permissions.is_admin ? "inline-flex" : "none";
  }
  if (accountsGroupForm) {
    accountsGroupForm.style.display = permissions.is_admin ? "grid" : "none";
  }
  if (accountsUserForm) {
    accountsUserForm.style.display = permissions.is_admin ? "grid" : "none";
  }
  if (deviceForm) {
    deviceForm.style.display = permissions.can_manage_devices ? "grid" : "none";
  }
  if (adminDeleteUser) {
    adminDeleteUser.style.display = permissions.is_admin ? "inline-flex" : "none";
  }
}

async function loadPermissions() {
  const response = await fetch("/api/permissions");
  if (!response.ok) {
    setStatsState("api", "offline");
    return;
  }
  setStatsState("api", "running");
  permissions = await response.json();
  applyPermissions();
}

function renderAdminModulesList(allowedList) {
  if (!adminModules) {
    return;
  }
  const allowed = new Set(allowedList || []);
  adminModules.innerHTML = "";
  Object.keys(moduleCatalog).forEach((key) => {
    const label = document.createElement("label");
    label.className = "admin-toggle";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.moduleKey = key;
    checkbox.checked = allowed.has(key);
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(` ${moduleCatalog[key].title}`));
    adminModules.appendChild(label);
  });
}

function renderAdminDevicesList(devices, allowedList) {
  if (!adminDevices) {
    return;
  }
  adminDevices.innerHTML = "";
  const allLabel = document.createElement("label");
  allLabel.className = "admin-toggle";
  const allCheckbox = document.createElement("input");
  allCheckbox.type = "checkbox";
  allCheckbox.id = "adminAllDevices";
  const hasSpecific = Array.isArray(allowedList);
  allCheckbox.checked = !hasSpecific;
  allLabel.appendChild(allCheckbox);
  allLabel.appendChild(document.createTextNode(" Alle apparaten"));
  adminDevices.appendChild(allLabel);

  const allowed = new Set(allowedList || []);
  devices.forEach((device) => {
    const label = document.createElement("label");
    label.className = "admin-toggle";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.deviceId = device.id;
    checkbox.checked = !hasSpecific || allowed.has(device.id);
    checkbox.disabled = !hasSpecific ? true : false;
    const macLabel = device.mac ? `, ${device.mac}` : "";
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(` ${device.name} (${device.ip}${macLabel})`));
    adminDevices.appendChild(label);
  });

  allCheckbox.addEventListener("change", () => {
    const deviceCheckboxes = adminDevices.querySelectorAll("input[data-device-id]");
    deviceCheckboxes.forEach((input) => {
      input.disabled = allCheckbox.checked;
      if (allCheckbox.checked) {
        input.checked = true;
      }
    });
  });
}

async function loadAdminPermissions(userId) {
  if (!permissions?.can_manage_student_settings || !userId) {
    return;
  }
  const selectedUser = cachedAdminUsersById.get(Number(userId));
  if (isSuperAuthorUser(selectedUser)) {
    applyAdminEditLock(userId, "super_author");
    if (adminStatus) {
      adminStatus.textContent = "author: niet wijzigbaar";
    }
    return;
  }
  const response = await fetch(`/api/admin/permissions?user_id=${userId}`);
  if (!response.ok) {
    if (adminStatus && response.status === 403) {
      adminStatus.textContent = "author: niet wijzigbaar";
    }
    return;
  }
  const data = await response.json();
  if (adminCanViewDevices) {
    adminCanViewDevices.checked = Boolean(data.can_view_devices);
  }
  if (adminCanManageDevices) {
    adminCanManageDevices.checked = Boolean(data.can_manage_devices);
  }
  renderAdminModulesList(data.allowed_modules || []);
  const devicesResponse = await fetch("/api/devices");
  if (!devicesResponse.ok) {
    return;
  }
  const devicesData = await devicesResponse.json();
  renderAdminDevicesList(devicesData.devices || [], data.device_access);
  applyAdminEditLock(userId, "");
}

async function loadCurrentUser() {
  const response = await fetch("/api/me");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  currentUserId = data.id;
}

function applyAdminEditLock(userId, lockReason = "") {
  const isSelf = currentUserId && Number(userId) === Number(currentUserId);
  const isSuperAuthor = lockReason === "super_author";
  const shouldLock = Boolean(isSelf || isSuperAuthor);
  const fields = [adminCanViewDevices, adminCanManageDevices, adminSave].filter(Boolean);
  fields.forEach((field) => {
    field.disabled = shouldLock;
  });
  if (adminDeleteUser) {
    adminDeleteUser.disabled = shouldLock;
  }
  adminModules?.querySelectorAll("input[data-module-key]").forEach((input) => {
    input.disabled = shouldLock;
  });
  adminDevices?.querySelectorAll("input[data-device-id], #adminAllDevices").forEach((input) => {
    input.disabled = shouldLock;
  });
  if (adminStatus) {
    adminStatus.textContent = isSelf
      ? "Je kan je eigen rechten niet wijzigen."
      : (isSuperAuthor ? "author: niet wijzigbaar" : "");
  }
}

async function loadAdminUsers() {
  if (!permissions?.can_manage_student_settings || !adminUserSelect) {
    return;
  }
  const response = await fetch("/api/admin/users");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  const users = permissions?.is_admin
    ? (Array.isArray(data.users) ? data.users : [])
    : (Array.isArray(data.users) ? data.users : []).filter((user) => isStudentCategory(user.category));
  cachedAdminUsersById = new Map(users.map((user) => [Number(user.id), user]));
  adminUserSelect.innerHTML = "";
  users.forEach((user) => {
    const option = document.createElement("option");
    option.value = user.id;
    const authorSuffix = isSuperAuthorUser(user) ? " · author: niet wijzigbaar" : "";
    option.textContent = `${user.username} (${formatCategoryLabel(user.category)})${authorSuffix}`;
    adminUserSelect.appendChild(option);
  });
  if (users.length) {
    await loadAdminPermissions(users[0].id);
  } else if (adminStatus) {
    adminStatus.textContent = "Geen leerlingen beschikbaar in jouw klasgroepen.";
  }
  if (permissions?.is_admin) {
    await loadAdminActivity();
  } else if (adminActivity) {
    adminActivity.innerHTML = "";
    adminActivity.textContent = "Alleen beschikbaar voor admin.";
  }
  await loadGroups();
  await loadUsers();
  if (permissions?.is_admin && !adminActivityTimer) {
    adminActivityTimer = window.setInterval(() => {
      loadAdminActivity();
    }, 10000);
  }
}

async function loadGroups() {
  if (!accountsGroupList) {
    return;
  }
  const response = await fetch("/api/admin/groups");
  if (!response.ok) {
    accountsGroupList.textContent = "Kon groepen niet laden.";
    return;
  }
  const data = await response.json();
  cachedGroups = Array.isArray(data.groups) ? data.groups : [];
  hydrateGroupSelects();
  renderGroups();
}

function resetAccountsView() {
  selectedGroupId = null;
  accountsGroupSearchTerm = "";
  accountsUserSearchTerm = "";
  if (accountsGroupSearch) {
    accountsGroupSearch.value = "";
  }
  if (accountsUserSearch) {
    accountsUserSearch.value = "";
  }
  if (accountsGroupModal) {
    accountsGroupModal.classList.remove("open");
    accountsGroupModal.setAttribute("aria-hidden", "true");
  }
  if (accountsUserModal) {
    accountsUserModal.classList.remove("open");
    accountsUserModal.setAttribute("aria-hidden", "true");
  }
  setAccountsGroupStatus("");
  setAccountsUserStatus("");
  renderGroups();
  renderUsers();
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function positionFloatingPanel(panel, left, top) {
  if (!panel) {
    return;
  }
  const padding = 12;
  const maxLeft = window.innerWidth - panel.offsetWidth - padding;
  const maxTop = window.innerHeight - panel.offsetHeight - padding;
  const nextLeft = clamp(left, padding, Math.max(padding, maxLeft));
  const nextTop = clamp(top, padding, Math.max(padding, maxTop));
  panel.style.left = `${nextLeft}px`;
  panel.style.top = `${nextTop}px`;
}

function centerFloatingPanel(panel) {
  if (!panel) {
    return;
  }
  const left = (window.innerWidth - panel.offsetWidth) / 2;
  const top = (window.innerHeight - panel.offsetHeight) / 2;
  positionFloatingPanel(panel, left, top);
}

function openAccountsUserPanel(groupId) {
  if (!accountsUserPanel || !accountsUserPanelBody) {
    return;
  }
  const normalizedGroupId = Number(groupId);
  const resolvedGroupId = Number.isFinite(normalizedGroupId) && normalizedGroupId > 0
    ? normalizedGroupId
    : null;
  const group = resolvedGroupId
    ? cachedGroups.find((item) => item.id === resolvedGroupId)
    : null;
  if (accountsUserPanelTitle) {
    accountsUserPanelTitle.textContent = group ? `Gebruikers · ${group.name}` : "Gebruikers";
  }
  accountsUserPanel.dataset.groupId = resolvedGroupId ? String(resolvedGroupId) : "";
  accountsUserPanel.classList.add("open");
  accountsUserPanel.setAttribute("aria-hidden", "false");
  if (!accountsUserPanel.dataset.positioned) {
    centerFloatingPanel(accountsUserPanel);
    accountsUserPanel.dataset.positioned = "true";
  }
  if (accountsUserCreateForm) {
    accountsUserCreateForm.style.display = permissions?.is_admin ? "grid" : "none";
  }
  renderUsersForGroup(resolvedGroupId);
}

function closeAccountsUserPanel() {
  if (!accountsUserPanel) {
    return;
  }
  accountsUserPanel.classList.remove("open");
  accountsUserPanel.setAttribute("aria-hidden", "true");
}

function openAccountsGroupPanel() {
  if (!accountsGroupPanel) {
    return;
  }
  const currentGroup = selectedGroupId
    ? cachedGroups.find((group) => group.id === selectedGroupId)
    : null;
  if (accountsGroupPanelTitle) {
    accountsGroupPanelTitle.textContent = currentGroup
      ? `Nieuwe groep · ${currentGroup.name}`
      : "Nieuwe groep";
  }
  if (accountsGroupParentLabel) {
    accountsGroupParentLabel.textContent = currentGroup ? `Onder: ${currentGroup.name}` : "Hoofdgroep";
  }
  if (accountsGroupParentId) {
    accountsGroupParentId.value = currentGroup ? String(currentGroup.id) : "";
  }
  accountsGroupPanel.classList.add("open");
  accountsGroupPanel.setAttribute("aria-hidden", "false");
  if (!accountsGroupPanel.dataset.positioned) {
    centerFloatingPanel(accountsGroupPanel);
    accountsGroupPanel.dataset.positioned = "true";
  }
}

function closeAccountsGroupPanel() {
  if (!accountsGroupPanel) {
    return;
  }
  accountsGroupPanel.classList.remove("open");
  accountsGroupPanel.setAttribute("aria-hidden", "true");
}

function renderGroups() {
  if (!accountsGroupList) {
    return;
  }
  accountsGroupList.innerHTML = "";
  const selectedName = selectedGroupId
    ? cachedGroups.find((group) => group.id === selectedGroupId)?.name
    : "Alle groepen";
  if (accountsSelectedLabel) {
    accountsSelectedLabel.textContent = `Geselecteerde groep: ${selectedName || "Alle groepen"}`;
  }

  const allRow = document.createElement("div");
  allRow.className = `accounts-group-row ${selectedGroupId ? "" : "active"}`;
  const allTitle = document.createElement("div");
  allTitle.className = "accounts-group-title";
  allTitle.textContent = "Alle groepen";
  allRow.appendChild(allTitle);
  allRow.addEventListener("click", () => {
    selectedGroupId = null;
    renderGroups();
    renderUsers();
  });
  accountsGroupList.appendChild(allRow);

  const byParent = new Map();
  const parentById = new Map();
  cachedGroups.forEach((group) => {
    const parentKey = group.parent_id || 0;
    if (!byParent.has(parentKey)) {
      byParent.set(parentKey, []);
    }
    byParent.get(parentKey).push(group);
    parentById.set(group.id, group.parent_id || 0);
  });
  byParent.forEach((items) => items.sort((a, b) => a.name.localeCompare(b.name)));

  const hasChildren = (groupId) => {
    const items = byParent.get(groupId) || [];
    return items.length > 0;
  };

  const visibleIds = new Set();
  if (accountsGroupSearchTerm) {
    cachedGroups.forEach((group) => {
      if (group.name.toLowerCase().includes(accountsGroupSearchTerm)) {
        visibleIds.add(group.id);
      }
    });
    cachedUsers.forEach((user) => {
      if (!user.username.toLowerCase().includes(accountsGroupSearchTerm)) {
        return;
      }
      (user.groups || []).forEach((group) => {
        visibleIds.add(group.id);
      });
    });
    const queue = Array.from(visibleIds);
    while (queue.length) {
      const currentId = queue.pop();
      const children = byParent.get(currentId) || [];
      children.forEach((child) => {
        if (!visibleIds.has(child.id)) {
          visibleIds.add(child.id);
          queue.push(child.id);
        }
      });
    }
    Array.from(visibleIds).forEach((id) => {
      let parentId = parentById.get(id) || 0;
      while (parentId) {
        if (visibleIds.has(parentId)) {
          break;
        }
        visibleIds.add(parentId);
        parentId = parentById.get(parentId) || 0;
      }
    });
  }

  const renderLevel = (parentId, depth) => {
    const items = byParent.get(parentId) || [];
    items.forEach((group) => {
      if (visibleIds.size && !visibleIds.has(group.id)) {
        return;
      }
      const row = document.createElement("div");
      row.className = `accounts-group-row ${selectedGroupId === group.id ? "active" : ""}`;
      row.style.marginLeft = `${depth * 14}px`;
      const title = document.createElement("div");
      title.className = "accounts-group-title";
      title.textContent = group.name;
      const eyeButton = document.createElement("button");
      eyeButton.className = "icon-button accounts-group-eye";
      eyeButton.type = "button";
      const isCollapsed = collapsedGroupIds.has(group.id);
      eyeButton.textContent = isCollapsed ? "🚫" : "👁️";
      eyeButton.setAttribute("aria-label", isCollapsed ? "Toon" : "Verberg");
      eyeButton.addEventListener("click", (event) => {
        event.stopPropagation();
        if (collapsedGroupIds.has(group.id)) {
          collapsedGroupIds.delete(group.id);
        } else {
          collapsedGroupIds.add(group.id);
        }
        renderGroups();
      });
      row.appendChild(title);
      row.appendChild(eyeButton);
      if (permissions?.is_admin) {
        const deleteButton = document.createElement("button");
        deleteButton.className = "icon-button accounts-group-delete";
        deleteButton.type = "button";
        deleteButton.textContent = "🗑️";
        deleteButton.setAttribute("aria-label", "Verwijderen");
        deleteButton.addEventListener("click", async (event) => {
          event.stopPropagation();
          await fetch(`/api/admin/groups/${group.id}`, { method: "DELETE" });
          if (selectedGroupId === group.id) {
            selectedGroupId = null;
          }
          loadGroups();
          loadUsers();
        });
        row.appendChild(deleteButton);
      }
      row.addEventListener("click", () => {
        selectedGroupId = group.id;
        renderGroups();
        renderUsers();
      });
      accountsGroupList.appendChild(row);
      if (!collapsedGroupIds.has(group.id)) {
        renderLevel(group.id, depth + 1);
      }
    });
  };

  renderLevel(0, 0);
  if (!cachedGroups.length) {
    const empty = document.createElement("div");
    empty.className = "accounts-group-row";
    empty.textContent = "Geen groepen gevonden.";
    accountsGroupList.appendChild(empty);
  }
}

function buildGroupOptions() {
  const byParent = new Map();
  cachedGroups.forEach((group) => {
    const parentKey = group.parent_id || 0;
    if (!byParent.has(parentKey)) {
      byParent.set(parentKey, []);
    }
    byParent.get(parentKey).push(group);
  });
  byParent.forEach((items) => items.sort((a, b) => a.name.localeCompare(b.name)));
  const options = [];
  const walk = (parentId, depth) => {
    const items = byParent.get(parentId) || [];
    items.forEach((group) => {
      const prefix = depth ? `${"—".repeat(depth)} ` : "";
      options.push({ id: group.id, label: `${prefix}${group.name}` });
      walk(group.id, depth + 1);
    });
  };
  walk(0, 0);
  return options;
}

function hydrateGroupSelects() {
  const options = buildGroupOptions();
  if (accountsGroupParentSelect) {
    accountsGroupParentSelect.innerHTML = "";
    const rootOption = document.createElement("option");
    rootOption.value = "";
    rootOption.textContent = "Hoofdgroep";
    accountsGroupParentSelect.appendChild(rootOption);
    options.forEach((option) => {
      const el = document.createElement("option");
      el.value = String(option.id);
      el.textContent = option.label;
      accountsGroupParentSelect.appendChild(el);
    });
  }
  if (accountsUserGroupSelect) {
    accountsUserGroupSelect.innerHTML = "";
    const noneOption = document.createElement("option");
    noneOption.value = "";
    noneOption.textContent = "Geen groep";
    accountsUserGroupSelect.appendChild(noneOption);
    options.forEach((option) => {
      const el = document.createElement("option");
      el.value = String(option.id);
      el.textContent = option.label.replace(/^—+\s*/, "");
      accountsUserGroupSelect.appendChild(el);
    });
  }
}

async function loadUsers() {
  if (!accountsUserList) {
    return;
  }
  const response = await fetch("/api/admin/users");
  if (!response.ok) {
    accountsUserList.textContent = "Kon gebruikers niet laden.";
    return;
  }
  const data = await response.json();
  cachedUsers = Array.isArray(data.users) ? data.users : [];
  renderUsers();
}

function getDescendantGroupIds(groupId) {
  const normalizedId = Number(groupId);
  if (!Number.isFinite(normalizedId) || normalizedId <= 0) {
    return new Set();
  }
  const descendants = new Set([normalizedId]);
  let changed = true;
  while (changed) {
    changed = false;
    cachedGroups.forEach((group) => {
      if (group.parent_id && descendants.has(group.parent_id) && !descendants.has(group.id)) {
        descendants.add(group.id);
        changed = true;
      }
    });
  }
  return descendants;
}

function getAncestorGroupIds(groupId) {
  const normalizedId = Number(groupId);
  if (!Number.isFinite(normalizedId) || normalizedId <= 0) {
    return [];
  }
  const parentById = new Map();
  cachedGroups.forEach((group) => {
    if (group && typeof group.id === "number") {
      parentById.set(group.id, group.parent_id || 0);
    }
  });
  const ancestors = [];
  let current = normalizedId;
  const visited = new Set();
  while (current && !visited.has(current)) {
    visited.add(current);
    const parentId = parentById.get(current) || 0;
    if (parentId) {
      ancestors.push(parentId);
    }
    current = parentId;
  }
  return ancestors;
}

function expandGroupSelection(groupIds) {
  const expanded = new Set();
  (Array.isArray(groupIds) ? groupIds : []).forEach((groupId) => {
    const normalizedId = Number(groupId);
    if (!Number.isFinite(normalizedId) || normalizedId <= 0) {
      return;
    }
    expanded.add(normalizedId);
    getAncestorGroupIds(normalizedId).forEach((ancestorId) => {
      expanded.add(ancestorId);
    });
  });
  return Array.from(expanded);
}

function renderUsers() {
  if (!accountsUserList) {
    return;
  }
  accountsUserList.innerHTML = "";
  const selectedName = selectedGroupId
    ? cachedGroups.find((group) => group.id === selectedGroupId)?.name
    : "Alle groepen";
  if (accountsSelectedLabel) {
    accountsSelectedLabel.textContent = `Geselecteerde groep: ${selectedName || "Alle groepen"}`;
  }

  let filteredUsers = cachedUsers.slice();
  if (selectedGroupId) {
    const descendantIds = getDescendantGroupIds(selectedGroupId);
    filteredUsers = filteredUsers.filter((user) =>
      (user.groups || []).some((group) => descendantIds.has(group.id))
    );
  }
  if (accountsUserSearchTerm) {
    filteredUsers = filteredUsers.filter((user) =>
      user.username.toLowerCase().includes(accountsUserSearchTerm)
    );
  }

  if (!filteredUsers.length) {
    accountsUserList.textContent = "Geen gebruikers gevonden.";
    return;
  }

  const canEditAccounts = permissions?.is_admin;
  filteredUsers.forEach((user) => {
    accountsUserList.appendChild(buildUserCard(user, canEditAccounts));
  });
}

function buildUserCard(user, canEditAccounts) {
  const card = document.createElement("div");
  card.className = "accounts-user-card";
  const meta = document.createElement("div");
  meta.className = "accounts-user-meta";
  const name = document.createElement("div");
  name.textContent = user.username;
  const tags = document.createElement("div");
  tags.className = "accounts-user-tags";
  const roleTag = document.createElement("span");
  roleTag.className = "tag";
  roleTag.textContent = user.role || "user";
  const categoryTag = document.createElement("span");
  categoryTag.className = "tag";
  categoryTag.textContent = formatCategoryLabel(user.category);
  tags.appendChild(roleTag);
  tags.appendChild(categoryTag);
  if (isSuperAuthorUser(user)) {
    const immutableTag = document.createElement("span");
    immutableTag.className = "tag";
    immutableTag.textContent = "author: niet wijzigbaar";
    tags.appendChild(immutableTag);
  }
  (user.groups || []).forEach((group) => {
    const groupTag = document.createElement("span");
    groupTag.className = "tag";
    groupTag.textContent = group.name;
    tags.appendChild(groupTag);
  });
  meta.appendChild(name);
  meta.appendChild(tags);

  const actions = document.createElement("div");
  actions.className = "accounts-user-actions";
  const editButton = document.createElement("button");
  editButton.className = "button";
  editButton.type = "button";
  editButton.textContent = "Bewerk";
  editButton.disabled = isSuperAuthorUser(user);
  editButton.addEventListener("click", () => {
    openUserEditModal(user);
  });
  actions.appendChild(editButton);
  if (canEditAccounts) {
    const deleteButton = document.createElement("button");
    deleteButton.className = "button ghost";
    deleteButton.type = "button";
    deleteButton.textContent = "Verwijderen";
    deleteButton.disabled = currentUserId === user.id || isSuperAuthorUser(user);
    deleteButton.addEventListener("click", async () => {
      await fetch(`/api/admin/users/${user.id}`, { method: "DELETE" });
      loadUsers();
    });
    actions.appendChild(deleteButton);
  }

  card.appendChild(meta);
  card.appendChild(actions);
  return card;
}

function renderUsersForGroup(groupId) {
  if (!accountsUserPanelBody) {
    return;
  }
  accountsUserPanelBody.innerHTML = "";
  const normalizedGroupId = Number(groupId);
  if (!Number.isFinite(normalizedGroupId) || normalizedGroupId <= 0) {
    accountsUserPanelBody.textContent = "Selecteer eerst een groep.";
    return;
  }
  const descendantIds = new Set([normalizedGroupId]);
  let changed = true;
  while (changed) {
    changed = false;
    cachedGroups.forEach((group) => {
      if (group.parent_id && descendantIds.has(group.parent_id) && !descendantIds.has(group.id)) {
        descendantIds.add(group.id);
        changed = true;
      }
    });
  }
  const filtered = cachedUsers.filter((user) =>
    (user.groups || []).some((group) => descendantIds.has(group.id))
  );
  const canEditAccounts = permissions?.is_admin;
  const searchTerm = accountsUserSearchTerm;
  const visible = searchTerm
    ? filtered.filter((user) => user.username.toLowerCase().includes(searchTerm))
    : filtered;
  if (!visible.length) {
    accountsUserPanelBody.textContent = "Geen gebruikers gevonden.";
    return;
  }
  visible.forEach((user) => {
    accountsUserPanelBody.appendChild(buildUserCard(user, canEditAccounts));
  });
}

function openUserEditModal(user) {
  if (!userEditModal || !userEditName || !userEditCategory || !userEditRole || !userEditGroups) {
    return;
  }
  const canEditAccounts = permissions?.is_admin;
  const isSuperAuthor = isSuperAuthorUser(user);
  activeEditUser = user;
  userEditName.textContent = user.username;
  userEditCategory.value = categoryToSelectValue(user.category || "student");
  userEditRole.value = user.role || "user";
  if (userEditStatus) {
    if (isSuperAuthor) {
      userEditStatus.textContent = "author: niet wijzigbaar";
    } else {
      userEditStatus.textContent = canEditAccounts ? "" : "Alleen bekijken.";
    }
  }
  userEditCategory.disabled = !canEditAccounts || isSuperAuthor;
  userEditRole.disabled = !canEditAccounts || isSuperAuthor;
  if (userEditSave) {
    userEditSave.disabled = !canEditAccounts || isSuperAuthor;
  }
  userEditGroups.innerHTML = "";
  cachedGroups.forEach((group) => {
    const line = document.createElement("label");
    line.className = "group-checkbox";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = String(group.id);
    checkbox.checked = (user.groups || []).some((g) => g.id === group.id);
    checkbox.disabled = !canEditAccounts || isSuperAuthor;
    const label = document.createElement("span");
    label.textContent = group.name;
    line.appendChild(checkbox);
    line.appendChild(label);
    userEditGroups.appendChild(line);
  });
  userEditModal.classList.add("open");
  userEditModal.setAttribute("aria-hidden", "false");
}

function closeUserEditModal() {
  if (!userEditModal) {
    return;
  }
  userEditModal.classList.remove("open");
  userEditModal.setAttribute("aria-hidden", "true");
  activeEditUser = null;
  if (userEditStatus) {
    userEditStatus.textContent = "";
  }
}

if (userEditSave) {
  userEditSave.addEventListener("click", async () => {
    if (!activeEditUser || !permissions?.is_admin || isSuperAuthorUser(activeEditUser)) {
      if (userEditStatus && activeEditUser && isSuperAuthorUser(activeEditUser)) {
        userEditStatus.textContent = "author: niet wijzigbaar";
      }
      return;
    }
    if (userEditStatus) {
      userEditStatus.textContent = "Opslaan...";
    }
    const role = userEditRole?.value || "user";
    const category = userEditCategory?.value || "student";
    const groupIds = userEditGroups
      ? Array.from(userEditGroups.querySelectorAll("input[type=\"checkbox\"]"))
          .filter((input) => input.checked)
          .map((input) => Number(input.value))
      : [];
    const updateResponse = await fetch(`/api/admin/users/${activeEditUser.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, category }),
    });
    if (!updateResponse.ok) {
      if (userEditStatus) {
        userEditStatus.textContent = "Opslaan mislukt.";
      }
      return;
    }
    const groupResponse = await fetch("/api/admin/user-groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: activeEditUser.id,
        group_ids: expandGroupSelection(groupIds),
      }),
    });
    if (!groupResponse.ok) {
      if (userEditStatus) {
        userEditStatus.textContent = "Opslaan mislukt.";
      }
      return;
    }
    closeUserEditModal();
    loadUsers();
  });
}

async function loadAdminActivity() {
  if (!permissions?.is_admin || !adminActivity) {
    return;
  }
  const response = await fetch("/api/admin/device-activity");
  if (!response.ok) {
    adminActivity.textContent = "Kon activiteit niet laden.";
    return;
  }
  const data = await response.json();
  adminActivity.innerHTML = "";
  if (!data.users || data.users.length === 0) {
    adminActivity.textContent = "Nog geen activiteit.";
    return;
  }
  data.users.forEach((user) => {
    const card = document.createElement("div");
    card.className = "admin-activity-item";
    const title = document.createElement("div");
    title.className = "admin-activity-user";
    title.textContent = user.username;
    card.appendChild(title);
    (user.devices || []).forEach((device) => {
      const line = document.createElement("div");
      const macLabel = device.mac ? ` · MAC-adres: ${device.mac}` : "";
      line.textContent = `${device.name} (${device.ip})${macLabel}`;
      card.appendChild(line);
    });
    adminActivity.appendChild(card);
  });
}

async function saveAdminPermissions() {
  if (!permissions?.can_manage_student_settings || !adminUserSelect) {
    return;
  }
  const userId = Number(adminUserSelect.value);
  const allowedModulesList = Array.from(
    adminModules?.querySelectorAll("input[data-module-key]:checked") || []
  ).map((input) => input.dataset.moduleKey);
  const allDevices = adminDevices?.querySelector("#adminAllDevices");
  let deviceAccess = null;
  if (allDevices && !allDevices.checked) {
    deviceAccess = Array.from(
      adminDevices.querySelectorAll("input[data-device-id]:checked")
    ).map((input) => Number(input.dataset.deviceId));
  }
  const payload = {
    user_id: userId,
    allowed_modules: allowedModulesList,
    can_view_devices: Boolean(adminCanViewDevices?.checked),
    can_manage_devices: Boolean(adminCanManageDevices?.checked),
    device_access: deviceAccess,
  };
  const response = await fetch("/api/admin/permissions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (adminStatus) {
    adminStatus.textContent = response.ok ? "Opgeslagen" : "Opslaan mislukt";
  }
}

let adminSaveTimer = null;

function scheduleAdminSave() {
  if (adminSaveTimer) {
    clearTimeout(adminSaveTimer);
    adminSaveTimer = null;
  }
  saveAdminPermissions();
}

if (adminUserSelect) {
  adminUserSelect.addEventListener("change", () => {
    loadAdminPermissions(Number(adminUserSelect.value));
  });
}

if (adminSave) {
  adminSave.addEventListener("click", () => {
    saveAdminPermissions();
  });
}

if (adminDeleteUser) {
  adminDeleteUser.addEventListener("click", async () => {
    if (!permissions?.is_admin || !adminUserSelect) {
      return;
    }
    const userId = Number(adminUserSelect.value);
    if (!userId || userId === Number(currentUserId)) {
      if (adminStatus) {
        adminStatus.textContent = "Je kan jezelf niet verwijderen.";
      }
      return;
    }
    const response = await fetch(`/api/admin/users/${userId}`, { method: "DELETE" });
    if (adminStatus) {
      adminStatus.textContent = response.ok ? "Gebruiker verwijderd" : "Verwijderen mislukt";
    }
    await loadAdminUsers();
  });
}

if (adminCanViewDevices) {
  adminCanViewDevices.addEventListener("change", scheduleAdminSave);
}

if (adminCanManageDevices) {
  adminCanManageDevices.addEventListener("change", scheduleAdminSave);
}

if (accountsGroupCreateForm) {
  accountsGroupCreateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(accountsGroupCreateForm);
    const name = String(formData.get("name") || "").trim();
    const parentRaw = String(formData.get("parent_id") || "").trim();
    if (!name) {
      return;
    }
    await fetch("/api/admin/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, parent_id: parentRaw ? Number(parentRaw) : null }),
    });
    accountsGroupCreateForm.reset();
    closeAccountsGroupPanel();
    loadGroups();
  });
}

if (accountsUserCreateForm) {
  accountsUserCreateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const panelGroupId = accountsUserPanel?.dataset.groupId || "";
    const groupId = panelGroupId ? Number(panelGroupId) : selectedGroupId;
    if (!groupId) {
      return;
    }
    const formData = new FormData(accountsUserCreateForm);
    const username = String(formData.get("username") || "").trim();
    const password = String(formData.get("password") || "").trim();
    const category = String(formData.get("category") || "student").trim();
    const role = String(formData.get("role") || "user").trim();
    if (!username || !password) {
      return;
    }
    const createResponse = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        password,
        category,
        role,
        group_id: Number(groupId),
      }),
    });
    if (!createResponse.ok) {
      const errorPayload = await createResponse.json().catch(() => null);
      const message = errorPayload?.error
        ? `Aanmaken mislukt: ${errorPayload.error}`
        : "Aanmaken mislukt.";
      setAccountsUserStatus(message);
      return;
    }
    setAccountsUserStatus("");
    const createdPayload = await createResponse.json().catch(() => null);
    const createdUserId = createdPayload && Number(createdPayload.user_id);
    if (createdUserId && Number.isFinite(createdUserId)) {
      await fetch("/api/admin/user-groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: createdUserId,
          group_ids: expandGroupSelection([Number(groupId)]),
        }),
      });
    }
    accountsUserCreateForm.reset();
    await loadUsers();
    openAccountsUserPanel(Number(groupId));
  });
}

if (accountsGroupForm) {
  accountsGroupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!permissions?.is_admin) {
      return;
    }
    const formData = new FormData(accountsGroupForm);
    const name = String(formData.get("name") || "").trim();
    const parentRaw = String(formData.get("parent_id") || "").trim();
    if (!name) {
      setAccountsGroupStatus("Naam is verplicht.");
      return;
    }
    const response = await fetch("/api/admin/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, parent_id: parentRaw ? Number(parentRaw) : null }),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => null);
      const message = errorPayload?.error
        ? `Groep aanmaken mislukt: ${errorPayload.error}`
        : "Groep aanmaken mislukt.";
      setAccountsGroupStatus(message);
      return;
    }
    setAccountsGroupStatus("Groep aangemaakt.");
    accountsGroupForm.reset();
    if (accountsGroupModal) {
      accountsGroupModal.classList.remove("open");
      accountsGroupModal.setAttribute("aria-hidden", "true");
    }
    await loadGroups();
    await loadUsers();
  });
}

if (accountsUserForm) {
  accountsUserForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!permissions?.is_admin) {
      return;
    }
    const formData = new FormData(accountsUserForm);
    const username = String(formData.get("username") || "").trim();
    const password = String(formData.get("password") || "").trim();
    const category = String(formData.get("category") || "student").trim();
    const role = String(formData.get("role") || "user").trim();
    const groupRaw = String(formData.get("group_id") || "").trim();
    const resolvedGroupId = groupRaw ? Number(groupRaw) : selectedGroupId;
    if (!username || !password) {
      setAccountsUserStatus("Gebruikersnaam en wachtwoord zijn verplicht.");
      return;
    }
    const createResponse = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        password,
        category,
        role,
        group_id: resolvedGroupId || null,
      }),
    });
    if (!createResponse.ok) {
      const errorPayload = await createResponse.json().catch(() => null);
      const message = errorPayload?.error
        ? `Aanmaken mislukt: ${errorPayload.error}`
        : "Aanmaken mislukt.";
      setAccountsUserStatus(message);
      return;
    }
    const createdPayload = await createResponse.json().catch(() => null);
    const createdUserId = createdPayload && Number(createdPayload.user_id);
    if (createdUserId && Number.isFinite(createdUserId) && resolvedGroupId) {
      await fetch("/api/admin/user-groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: createdUserId,
          group_ids: expandGroupSelection([Number(resolvedGroupId)]),
        }),
      });
    }
    setAccountsUserStatus("Gebruiker aangemaakt.");
    accountsUserForm.reset();
    if (accountsUserModal) {
      accountsUserModal.classList.remove("open");
      accountsUserModal.setAttribute("aria-hidden", "true");
    }
    if (resolvedGroupId) {
      selectedGroupId = Number(resolvedGroupId);
    }
    await loadUsers();
    renderGroups();
  });
}

if (accountsGroupSearch) {
  accountsGroupSearch.addEventListener("input", () => {
    accountsGroupSearchTerm = accountsGroupSearch.value.trim().toLowerCase();
    renderGroups();
  });
}

if (accountsUserSearch) {
  accountsUserSearch.addEventListener("input", () => {
    accountsUserSearchTerm = accountsUserSearch.value.trim().toLowerCase();
    renderUsers();
  });
}


if (accountsGroupCreateToggle && accountsGroupModal) {
  accountsGroupCreateToggle.addEventListener("click", () => {
    accountsGroupModal.classList.add("open");
    accountsGroupModal.setAttribute("aria-hidden", "false");
  });
}

if (accountsUserCreateToggle && accountsUserModal) {
  accountsUserCreateToggle.addEventListener("click", () => {
    if (accountsUserGroupSelect && selectedGroupId) {
      accountsUserGroupSelect.value = String(selectedGroupId);
    }
    accountsUserModal.classList.add("open");
    accountsUserModal.setAttribute("aria-hidden", "false");
  });
}

if (accountsGroupModal) {
  accountsGroupModal.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.dataset.close === "true" || target.classList.contains("modal-close")) {
      accountsGroupModal.classList.remove("open");
      accountsGroupModal.setAttribute("aria-hidden", "true");
    }
  });
}

if (accountsUserModal) {
  accountsUserModal.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.dataset.close === "true" || target.classList.contains("modal-close")) {
      accountsUserModal.classList.remove("open");
      accountsUserModal.setAttribute("aria-hidden", "true");
    }
  });
}

if (adminModules) {
  adminModules.addEventListener("change", (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement) {
      scheduleAdminSave();
    }
  });
}

if (adminDevices) {
  adminDevices.addEventListener("change", (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement) {
      scheduleAdminSave();
    }
  });
}

function generateId() {
  if (crypto && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function applyTheme(theme) {
  document.body.classList.toggle("theme-dark", theme === "dark");
  if (themeIcon) {
    themeIcon.textContent = theme === "dark" ? "🌙" : "☀️";
  }
  localStorage.setItem(THEME_STORAGE_KEY, theme);
}

function openSettingsMenu() {
  settingsMenu.classList.add("open");
  settingsMenu.setAttribute("aria-hidden", "false");
}

function closeSettingsMenu() {
  settingsMenu.classList.remove("open");
  settingsMenu.setAttribute("aria-hidden", "true");
}

function openResetRequestsModal() {
  if (!resetRequestsModal) {
    return;
  }
  resetRequestsModal.classList.add("open");
  resetRequestsModal.setAttribute("aria-hidden", "false");
  loadResetRequests();
}

function closeResetRequestsModal() {
  if (!resetRequestsModal) {
    return;
  }
  resetRequestsModal.classList.remove("open");
  resetRequestsModal.setAttribute("aria-hidden", "true");
}

function openProfileModal() {
  if (!profileModal) {
    return;
  }
  profileModal.classList.add("open");
  profileModal.setAttribute("aria-hidden", "false");
  loadProfileData();
}

function closeProfileModal() {
  if (!profileModal) {
    return;
  }
  profileModal.classList.remove("open");
  profileModal.setAttribute("aria-hidden", "true");
  if (profileOldPassword) profileOldPassword.value = "";
  if (profileNewPassword) profileNewPassword.value = "";
  if (profileNewPasswordRepeat) profileNewPasswordRepeat.value = "";
  if (profileStatus) profileStatus.textContent = "";
}

async function loadProfileData() {
  const response = await fetch("/api/me");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  if (profileUsername) profileUsername.textContent = data.username || "-";
  if (profileRole) profileRole.textContent = data.role || "-";
  if (profileCategory) profileCategory.textContent = formatCategoryLabel(data.category || "-");
  if (profileCreatedAt) {
    const date = data.created_at ? new Date(data.created_at).toLocaleString() : "-";
    profileCreatedAt.textContent = date;
  }
}

async function changeOwnPassword() {
  const oldPass = profileOldPassword?.value.trim();
  const newPass = profileNewPassword?.value.trim();
  const repeatPass = profileNewPasswordRepeat?.value.trim();

  if (!oldPass || !newPass || !repeatPass) {
    if (profileStatus) profileStatus.textContent = "Alle velden zijn verplicht.";
    return;
  }
  if (newPass !== repeatPass) {
    if (profileStatus) profileStatus.textContent = "Nieuwe wachtwoorden stemmen niet overeen.";
    return;
  }
  if (newPass.length < 6) {
    if (profileStatus) profileStatus.textContent = "Wachtwoord moet minstens 6 tekens hebben.";
    return;
  }

  if (profileChangePasswordButton) profileChangePasswordButton.disabled = true;
  if (profileStatus) profileStatus.textContent = "Bezig...";

  const response = await fetch("/api/me/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_password: oldPass, new_password: newPass }),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (profileChangePasswordButton) profileChangePasswordButton.disabled = false;
    if (profileStatus) profileStatus.textContent = data.error || "Fout bij wachtwoordwijziging.";
    return;
  }

  if (profileStatus) profileStatus.textContent = data.message || "Wachtwoord succesvol gewijzigd!";
  if (profileOldPassword) profileOldPassword.value = "";
  if (profileNewPassword) profileNewPassword.value = "";
  if (profileNewPasswordRepeat) profileNewPasswordRepeat.value = "";
  if (profileChangePasswordButton) profileChangePasswordButton.disabled = false;
}

function updateResetBadge(count) {
  if (!resetRequestsBadge) {
    return;
  }
  resetRequestsBadge.textContent = String(count);
  resetRequestsBadge.style.fontWeight = count > 0 ? "700" : "400";
  if (settingsAlertDot) {
    settingsAlertDot.hidden = count <= 0;
  }
}

async function refreshResetPendingCount(showPopupOnNew = true) {
  if (!permissions?.is_admin) {
    return;
  }
  const response = await fetch("/api/admin/password-reset-requests/pending-count");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  const count = Number(data.count || 0);
  updateResetBadge(count);
  if (latestPendingResetCount !== null && count > latestPendingResetCount && showPopupOnNew) {
    openResetRequestsModal();
  }
  latestPendingResetCount = count;
}

function renderResetRequests(items) {
  if (!resetRequestsList) {
    return;
  }
  resetRequestsList.innerHTML = "";
  if (!items.length) {
    resetRequestsList.textContent = "Geen openstaande aanvragen.";
    return;
  }

  items.forEach((item) => {
    const wrapper = document.createElement("div");
    wrapper.className = "admin-device-item";

    const meta = document.createElement("div");
    meta.className = "admin-device-meta";
    const date = item.requested_at ? new Date(item.requested_at).toLocaleString() : "Onbekend";
    meta.textContent = `${item.username} • ${date}`;

    const actions = document.createElement("div");
    actions.style.display = "flex";
    actions.style.gap = "8px";
    actions.style.flexWrap = "wrap";

    const passwordInput = document.createElement("input");
    passwordInput.type = "password";
    passwordInput.placeholder = "Nieuw wachtwoord";
    passwordInput.className = "device-input";
    passwordInput.style.minWidth = "180px";

    const savePasswordButton = document.createElement("button");
    savePasswordButton.className = "button primary";
    savePasswordButton.type = "button";
    savePasswordButton.textContent = "Wachtwoord instellen";
    savePasswordButton.addEventListener("click", async () => {
      const newPassword = passwordInput.value.trim();
      if (newPassword.length < 6) {
        if (resetRequestsStatus) {
          resetRequestsStatus.textContent = "Wachtwoord moet minstens 6 tekens hebben.";
        }
        return;
      }
      savePasswordButton.disabled = true;
      const response = await fetch(`/api/admin/password-reset-requests/${item.id}/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: newPassword }),
      });
      if (!response.ok) {
        savePasswordButton.disabled = false;
        const data = await response.json().catch(() => ({}));
        if (resetRequestsStatus) {
          resetRequestsStatus.textContent = data.error || "Kon wachtwoord niet wijzigen.";
        }
        return;
      }
      if (resetRequestsStatus) {
        resetRequestsStatus.textContent = `Wachtwoord gewijzigd voor ${item.username}.`;
      }
      await loadResetRequests();
      await refreshResetPendingCount(false);
    });

    const markHandledButton = document.createElement("button");
    markHandledButton.className = "button ghost";
    markHandledButton.type = "button";
    markHandledButton.textContent = "Afgehandeld";
    markHandledButton.addEventListener("click", async () => {
      markHandledButton.disabled = true;
      const response = await fetch(`/api/admin/password-reset-requests/${item.id}/mark-handled`, {
        method: "POST",
      });
      if (!response.ok) {
        markHandledButton.disabled = false;
        if (resetRequestsStatus) {
          resetRequestsStatus.textContent = "Kon aanvraag niet bijwerken.";
        }
        return;
      }
      if (resetRequestsStatus) {
        resetRequestsStatus.textContent = "Aanvraag gemarkeerd als afgehandeld.";
      }
      await loadResetRequests();
      await refreshResetPendingCount(false);
    });

    actions.appendChild(passwordInput);
    actions.appendChild(savePasswordButton);
    actions.appendChild(markHandledButton);

    wrapper.appendChild(meta);
    wrapper.appendChild(actions);
    resetRequestsList.appendChild(wrapper);
  });
}

async function loadResetRequests() {
  if (!permissions?.is_admin || !resetRequestsList) {
    return;
  }
  resetRequestsList.textContent = "Laden...";
  if (resetRequestsStatus) {
    resetRequestsStatus.textContent = "";
  }

  const response = await fetch("/api/admin/password-reset-requests?status=pending");
  if (!response.ok) {
    resetRequestsList.textContent = "Kon aanvragen niet laden.";
    return;
  }
  const data = await response.json();
  const items = Array.isArray(data.requests) ? data.requests : [];
  renderResetRequests(items);
}

function startResetRequestsPolling() {
  if (!permissions?.is_admin) {
    return;
  }
  if (resetRequestsButton) {
    resetRequestsButton.hidden = false;
  }
  refreshResetPendingCount(false);
  if (resetRequestsTimer) {
    window.clearInterval(resetRequestsTimer);
  }
  resetRequestsTimer = window.setInterval(() => {
    refreshResetPendingCount(true);
  }, 10000);
}

function setActivePanel(name) {
  panels.forEach((panel) => {
    const isActive = panel.dataset.panel === name;
    panel.hidden = !isActive;
    panel.classList.toggle("active", isActive);
  });
  menuItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.section === name);
  });
  if (name === "accounts") {
    resetAccountsView();
  }
  if (name) {
    sessionStorage.setItem(ACTIVE_PANEL_KEY, name);
  }
}

function createModuleElement(moduleData) {
  const node = moduleTemplate.content.firstElementChild.cloneNode(true);
  node.dataset.id = moduleData.id;
  node.dataset.key = moduleData.key || "";
  node.classList.toggle("locked", Boolean(moduleData.locked));
  node.style.gridColumn = `${moduleData.x} / span ${moduleData.w}`;
  node.style.gridRow = `${moduleData.y} / span ${moduleData.h}`;
  const titleEl = node.querySelector(".module-title");
  const memory = loadModuleMemory();
  const moduleMemory = memory[moduleData.id] && typeof memory[moduleData.id] === "object"
    ? memory[moduleData.id]
    : {};
  titleEl.textContent = moduleMemory.title || moduleData.title;
  if (MULTI_MODULE_KEYS.has(moduleData.key)) {
    titleEl.setAttribute("contenteditable", "true");
    titleEl.setAttribute("spellcheck", "false");
    titleEl.setAttribute("draggable", "false");
    titleEl.addEventListener("mousedown", (event) => {
      event.stopPropagation();
    });
    titleEl.addEventListener("input", () => {
      const value = titleEl.textContent?.trim() || moduleData.title;
      updateModuleMemory(moduleData.id, { title: value });
    });
  }
  const body = node.querySelector(".module-body");
  if (body && window.SharedModules?.renderModuleBody) {
    window.SharedModules.renderModuleBody({
      moduleData,
      body,
      moduleMemory,
      handlers: {
        updateModuleMemory,
        setStatsState,
        runPing,
        runTerminal,
        stopTerminal,
        appendTerminalLine,
        clearTerminalOutput,
        getTerminalLines,
        renderStats: (target, data) => {
          target.innerHTML = "<div class=\"stats-list\" data-role=\"stats-list\"></div>";
          ensureStatsSelectionValid(data.id);
          renderStatsSelection(target, data.id);
        },
      },
    });
  }

  const lockButton = node.querySelector(".module-lock");
  lockButton.textContent = moduleData.locked ? "🔒" : "🔓";
  if (moduleData.key === "stats") {
    const actions = node.querySelector(".module-actions");
    if (actions && !actions.querySelector(".module-settings")) {
      const settingsButton = document.createElement("button");
      settingsButton.className = "module-settings";
      settingsButton.type = "button";
      settingsButton.title = "Stats instellingen";
      settingsButton.textContent = "⚙";
      settingsButton.addEventListener("click", (event) => {
        event.stopPropagation();
        openStatsSettings(moduleData.id);
      });
      actions.insertBefore(settingsButton, lockButton);
    }
  }
  lockButton.addEventListener("click", () => {
    toggleLock(moduleData.id);
  });

  const removeButton = node.querySelector(".module-remove");
  if (removeButton) {
    removeButton.disabled = moduleData.locked;
    removeButton.title = moduleData.locked ? "Ontgrendel om te verwijderen" : "Verwijderen";
  }

  const resizeHandles = node.querySelectorAll(".resize-handle");
  resizeHandles.forEach((handle) => {
    handle.addEventListener("mousedown", (event) => {
      event.preventDefault();
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

  node.draggable = !moduleData.locked;
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
    event.dataTransfer.setData("text/plain", moduleData.id);
    event.dataTransfer.setData("module-id", moduleData.id);
    event.dataTransfer.effectAllowed = "move";
  });

  node.addEventListener("dragend", () => {
    state.draggingId = null;
  });

  node.querySelector(".module-remove").addEventListener("click", () => {
    if (moduleData.locked) {
      return;
    }
    clearModuleMemory(moduleData.id);
    state.modules = state.modules.filter((item) => item.id !== moduleData.id);
    renderModules();
    renderPalette();
    scheduleSave();
  });

  node.addEventListener("dblclick", (event) => {
    event.stopPropagation();
  });

  node.addEventListener("dragover", (event) => {
    event.preventDefault();
  });

  node.addEventListener("drop", (event) => {
    handleDrop(event);
  });

  return node;
}

function renderModules() {
  grid.innerHTML = "";
  if (allowedModules) {
    state.modules = state.modules.filter((moduleData) =>
      moduleData.key ? allowedModules.has(moduleData.key) : true
    );
  }
  const memory = loadModuleMemory();
  const counters = {};
  state.modules.forEach((moduleData) => {
    if (MULTI_MODULE_KEYS.has(moduleData.key)) {
      counters[moduleData.key] = (counters[moduleData.key] || 0) + 1;
      if (!memory[moduleData.id]?.title) {
        const baseTitle = moduleCatalog[moduleData.key]?.title || moduleData.title;
        updateModuleMemory(moduleData.id, { title: `${baseTitle} ${counters[moduleData.key]}` });
      }
    }
    grid.appendChild(createModuleElement(moduleData));
  });
  updateAddModuleTile();
}

function updateAddModuleTile() {
  if (!addModuleButton) {
    return;
  }
  const placeholder = {
    id: "add-tile",
    key: "add",
    title: "Add",
    content: "",
    x: 1,
    y: 1,
    w: 2,
    h: 2,
  };
  const spot = findNextAvailableSpot(placeholder);
  if (!spot) {
    addModuleButton.style.display = "none";
    return;
  }
  addModuleButton.style.display = "inline-flex";
  addModuleButton.style.gridColumn = `${spot.x} / span ${placeholder.w}`;
  addModuleButton.style.gridRow = `${spot.y} / span ${placeholder.h}`;
  grid.appendChild(addModuleButton);
}

function findNextAvailableSpot(moduleData) {
  if (state.modules.length === 0) {
    return findFirstAvailableSpot(moduleData);
  }

  const sorted = [...state.modules].sort((a, b) => {
    if (a.y === b.y) {
      return a.x - b.x;
    }
    return a.y - b.y;
  });
  const last = sorted[sorted.length - 1];
  const startX = Math.min(6, last.x + last.w);
  const startY = last.y;
  const candidate = findAvailableSpot(moduleData, startX, startY);
  if (candidate) {
    return candidate;
  }
  return findFirstAvailableSpot(moduleData);
}

function renderPalette() {
  const usedKeys = new Set(state.modules.map((item) => item.key).filter(Boolean));
  paletteItems.forEach((item) => {
    const key = item.dataset.module;
    if (allowedModules && !allowedModules.has(key)) {
      item.style.display = "none";
      return;
    }
    const isUsed = usedKeys.has(key);
    if (MULTI_MODULE_KEYS.has(key)) {
      item.style.display = "block";
      return;
    }
    item.style.display = isUsed ? "none" : "block";
  });
}

function buildModule(moduleKey) {
  if (allowedModules && !allowedModules.has(moduleKey)) {
    return null;
  }
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

function buildDeviceModule(moduleKey, device) {
  if (!device || !device.ip) {
    return null;
  }
  const base = buildModule(moduleKey);
  if (!base) {
    return null;
  }
  const name = device.name || device.ip;
  return {
    ...base,
    title: `${base.title} - ${name}`,
    deviceId: device.id,
    deviceIp: device.ip,
  };
}

function isPlcLikeDevice(device) {
  if (!device) {
    return false;
  }
  const name = String(device.name || "").toLowerCase();
  return /plc|siemens|s7|wago|codesys|hmi|scada/.test(name);
}

function ensurePlcModuleForDevice(device) {
  if (!device || !device.id) {
    return;
  }
  if (allowedModules && !allowedModules.has("plc")) {
    return;
  }
  const exists = state.modules.some(
    (item) => item.key === "plc" && Number(item.deviceId) === Number(device.id)
  );
  if (exists) {
    return;
  }
  const moduleData = buildDeviceModule("plc", device);
  if (!moduleData) {
    return;
  }
  moduleData.w = 3;
  moduleData.h = 3;
  const spot = findNextAvailableSpot(moduleData) || findFirstAvailableSpot(moduleData);
  if (!spot) {
    return;
  }
  moduleData.x = spot.x;
  moduleData.y = spot.y;
  state.modules.push(moduleData);
  renderModules();
  renderPalette();
  scheduleSave();
}

function closePlcModuleModal() {
  if (plcModuleModalBody) {
    plcModuleModalBody.innerHTML = "";
  }
  if (plcModuleModal) {
    plcModuleModal.classList.remove("open");
  }
}

function openPlcModuleModal(device) {
  if (!device || !plcModuleModal || !plcModuleModalBody) {
    return;
  }
  const renderPlc = window.ModuleRegistry?.plc;
  if (typeof renderPlc !== "function") {
    return;
  }
  const deviceName = device.name || `PLC ${device.ip}`;
  if (plcModuleModalTitle) {
    plcModuleModalTitle.textContent = `PLC module · ${deviceName}`;
  }
  plcModuleModalBody.innerHTML = "";
  const host = document.createElement("div");
  host.dataset.plcHostId = `plc-modal-${device.id}`;
  plcModuleModalBody.appendChild(host);
  plcModuleModal.classList.add("open");
  try {
    renderPlc({
      moduleData: {
        id: `plc-modal-${device.id}`,
        key: "plc",
        deviceId: device.id,
        deviceIp: device.ip,
        title: `PLC I/O - ${deviceName}`,
      },
      body: host,
      moduleMemory: {},
      handlers: {
        updateModuleMemory,
      },
    });
  } catch (error) {
    host.innerHTML = '<div class="plc-io-empty">PLC-module kon niet geladen worden.</div>';
    console.error("PLC module render error", error);
  }
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

function updateModulePosition(id, x, y) {
  const target = state.modules.find((item) => item.id === id);
  if (!target) {
    return;
  }
  const available = findAvailableSpot(target, x, y);
  if (!available) {
    return;
  }
  target.x = available.x;
  target.y = available.y;
  renderModules();
  scheduleSave();
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

function findAvailableSpot(moduleData, startX, startY) {
  const candidate = { ...moduleData, x: startX, y: startY };
  if (!isOverlapping(candidate, moduleData.id)) {
    return { x: startX, y: startY };
  }

  const maxRows = getMaxRows();
  for (let y = startY; y <= maxRows; y += 1) {
    for (let x = 1; x <= 6; x += 1) {
      const trial = { ...moduleData, x, y };
      if (!isOverlapping(trial, moduleData.id)) {
        return { x, y };
      }
    }
  }
  return null;
}

function handleDrop(event) {
  event.preventDefault();
  const { x, y } = snapToGrid(event.clientX, event.clientY);

  const movingId = state.draggingId || event.dataTransfer.getData("module-id");
  if (movingId) {
    updateModulePosition(movingId, x, y);
    return;
  }

  const moduleKey = event.dataTransfer.getData("module");
  if (moduleKey) {
    const newModule = buildModule(moduleKey);
    if (!newModule) {
      return;
    }
    const available = findAvailableSpot(newModule, x, y);
    if (!available) {
      return;
    }
    newModule.x = available.x;
    newModule.y = available.y;
    state.modules.push(newModule);
    renderModules();
    renderPalette();
    scheduleSave();
  }
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
    updateModulePosition(state.draggingId, snapped.x, snapped.y);
  });
});


if (addModuleButton) {
  addModuleButton.addEventListener("click", () => {
    openModal();
  });
}

grid.addEventListener("drop", (event) => {
  handleDrop(event);
});

paletteItems.forEach((item) => {
  item.setAttribute("draggable", "false");
  item.addEventListener("click", () => {
    addModuleFromPalette(item.dataset.module);
    closeModal();
  });
});


moduleModal.addEventListener("click", (event) => {
  const target = event.target;
  if (target instanceof HTMLElement && target.dataset.close === "true") {
    closeModal();
  }
  if (target instanceof HTMLElement && target.classList.contains("modal-close")) {
    closeModal();
  }
});

if (statsSettingsModal) {
  statsSettingsModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.close === "true") {
      closeStatsSettings();
    }
    if (target instanceof HTMLElement && target.classList.contains("modal-close")) {
      closeStatsSettings();
    }
  });
}

if (resetRequestsModal) {
  resetRequestsModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.close === "true") {
      closeResetRequestsModal();
    }
    if (target instanceof HTMLElement && target.classList.contains("modal-close")) {
      closeResetRequestsModal();
    }
  });
}

if (resetRequestsButton) {
  resetRequestsButton.addEventListener("click", () => {
    openResetRequestsModal();
  });
}

if (profileButton) {
  profileButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (profileModal) {
      closeSettingsMenu();
      openProfileModal();
    }
  });
}

if (profileModal) {
  profileModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.close === "true") {
      closeProfileModal();
    }
    if (target instanceof HTMLElement && target.classList.contains("modal-close")) {
      closeProfileModal();
    }
  });
}

if (profileChangePasswordButton) {
  profileChangePasswordButton.addEventListener("click", () => {
    changeOwnPassword();
  });
}

if (userEditModal) {
  userEditModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.close === "true") {
      closeUserEditModal();
    }
    if (target instanceof HTMLElement && target.classList.contains("modal-close")) {
      closeUserEditModal();
    }
  });
}

if (accountsUserPanelClose) {
  accountsUserPanelClose.addEventListener("click", () => {
    closeAccountsUserPanel();
  });
}

if (openGroupCreateButton) {
  openGroupCreateButton.addEventListener("click", () => {
    openAccountsGroupPanel();
  });
}

if (openUserCreateButton) {
  openUserCreateButton.addEventListener("click", () => {
    if (!selectedGroupId) {
      openAccountsUserPanel(null);
      return;
    }
    openAccountsUserPanel(selectedGroupId);
  });
}

if (accountsGroupPanelClose) {
  accountsGroupPanelClose.addEventListener("click", () => {
    closeAccountsGroupPanel();
  });
}

if (accountsUserPanelHeader && accountsUserPanel) {
  accountsUserPanelHeader.addEventListener("mousedown", (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    const startLeft = accountsUserPanel.offsetLeft;
    const startTop = accountsUserPanel.offsetTop;
    const startX = event.clientX;
    const startY = event.clientY;

    const onMove = (moveEvent) => {
      const nextLeft = startLeft + (moveEvent.clientX - startX);
      const nextTop = startTop + (moveEvent.clientY - startY);
      positionFloatingPanel(accountsUserPanel, nextLeft, nextTop);
    };

    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });
}

if (accountsGroupPanelHeader && accountsGroupPanel) {
  accountsGroupPanelHeader.addEventListener("mousedown", (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    const startLeft = accountsGroupPanel.offsetLeft;
    const startTop = accountsGroupPanel.offsetTop;
    const startX = event.clientX;
    const startY = event.clientY;

    const onMove = (moveEvent) => {
      const nextLeft = startLeft + (moveEvent.clientX - startX);
      const nextTop = startTop + (moveEvent.clientY - startY);
      positionFloatingPanel(accountsGroupPanel, nextLeft, nextTop);
    };

    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });
}

window.addEventListener("resize", () => {
  if (accountsUserPanel?.classList.contains("open")) {
    positionFloatingPanel(accountsUserPanel, accountsUserPanel.offsetLeft, accountsUserPanel.offsetTop);
  }
  if (accountsGroupPanel?.classList.contains("open")) {
    positionFloatingPanel(accountsGroupPanel, accountsGroupPanel.offsetLeft, accountsGroupPanel.offsetTop);
  }
});

document.addEventListener("mousedown", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const clickedUserTrigger = target.closest(".icon-button-user");
  const clickedGroupTrigger = target.closest("#openGroupCreate");
  if (
    accountsUserPanel?.classList.contains("open") &&
    !accountsUserPanel.contains(target) &&
    !clickedUserTrigger
  ) {
    closeAccountsUserPanel();
  }
  if (
    accountsGroupPanel?.classList.contains("open") &&
    !accountsGroupPanel.contains(target) &&
    !clickedGroupTrigger
  ) {
    closeAccountsGroupPanel();
  }
});

themeToggle.addEventListener("click", () => {
  state.theme = state.theme === "light" ? "dark" : "light";
  applyTheme(state.theme);
  scheduleSave();
});

settingsToggle.addEventListener("click", () => {
  if (settingsMenu.classList.contains("open")) {
    closeSettingsMenu();
  } else {
    openSettingsMenu();
  }
});

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

menuItems.forEach((item) => {
  item.addEventListener("click", () => {
    const target = item.dataset.section;
    if (target) {
      if (target === "devices" && permissions && !permissions.can_view_devices) {
        return;
      }
      if (target === "admin" && permissions && !permissions.can_manage_student_settings) {
        return;
      }
      if (target === "accounts" && permissions && !permissions.can_view_accounts) {
        return;
      }
      setActivePanel(target);
      if (target === "devices") {
        loadDevices();
      }
      if (target === "admin" && permissions?.can_manage_student_settings) {
        loadAdminUsers();
      }
      if (target === "accounts" && permissions?.can_view_accounts) {
        selectedGroupId = null;
        loadGroups();
        loadUsers();
      }
    }
  });
});

let saveTimer = null;
let lastDragPosition = null;
let dragFrame = null;
const transparentDragImage = (() => {
  const image = new Image();
  image.src = "data:image/gif;base64,R0lGODlhAQABAAAAACw=";
  return image;
})();

function scheduleSave() {
  if (saveTimer) {
    clearTimeout(saveTimer);
  }
  saveTimer = setTimeout(() => {
    saveSettings();
  }, 400);
}

async function saveSettings() {
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme: state.theme, layout: state.modules }),
  });
}

async function loadSettings() {
  const response = await fetch("/api/settings");
  if (!response.ok) {
    return;
  }
  const data = await response.json();
  state.theme = data.theme || "light";
  state.modules = normalizeModules(data.layout || []);
  applyTheme(state.theme);
  renderModules();
  renderPalette();
  const storedPanel = sessionStorage.getItem(ACTIVE_PANEL_KEY) || "dashboard";
  const canShowDevices = !permissions || permissions.can_view_devices;
  const canShowAdmin = permissions?.can_manage_student_settings;
  const canShowAccounts = permissions?.can_view_accounts;
  if (storedPanel === "devices" && !canShowDevices) {
    setActivePanel("dashboard");
    return;
  }
  if (storedPanel === "admin" && !canShowAdmin) {
    setActivePanel("dashboard");
    return;
  }
  if (storedPanel === "accounts" && !canShowAccounts) {
    setActivePanel("dashboard");
    return;
  }
  setActivePanel(storedPanel);
  if (storedPanel === "devices") {
    loadDevices();
  }
  if (storedPanel === "admin" && permissions?.can_manage_student_settings) {
    loadAdminUsers();
  }
  if (storedPanel === "accounts" && permissions?.can_view_accounts) {
    selectedGroupId = null;
    loadGroups();
    loadUsers();
  }
}

function applyPanelFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const panel = params.get("panel");
  const storedPanel = sessionStorage.getItem(ACTIVE_PANEL_KEY);
  if (!storedPanel && panel && ["dashboard", "devices", "admin", "accounts"].includes(panel)) {
    sessionStorage.setItem(ACTIVE_PANEL_KEY, panel);
  }
  if (panel) {
    params.delete("panel");
    const next = params.toString();
    const nextUrl = next ? `${window.location.pathname}?${next}` : window.location.pathname;
    window.history.replaceState({}, "", nextUrl);
  }
}

async function bootstrap() {
  const cachedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  if (cachedTheme) {
    applyTheme(cachedTheme);
  }
  applyPanelFromUrl();
  await loadCurrentUser();
  await loadPermissions();
  await loadSettings();
  await refreshDeviceStats();
  startStatsTicker();
  startStatsPingLoop();
  if (permissions?.can_manage_student_settings) {
    loadAdminUsers();
  }
  if (permissions?.is_admin) {
    startResetRequestsPolling();
  }
}

bootstrap();

function normalizeModules(modules) {
  return modules.map((item) => {
    if (item.key) {
      const key = item.key === "notes" ? "info" : item.key;
      return { locked: false, ...item, key };
    }
    const match = Object.keys(moduleCatalog).find((key) => item.id?.includes(key));
    const key = match || "";
    return { locked: false, ...item, key };
  });
}

function toggleLock(id) {
  const target = state.modules.find((item) => item.id === id);
  if (!target) {
    return;
  }
  target.locked = !target.locked;
  renderModules();
  scheduleSave();
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
    scheduleSave();
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

function applyResize(target, nextW, nextH, nextX, nextY) {
  const maxW = 7 - nextX;
  const maxH = 12;
  const candidate = {
    ...target,
    x: Math.max(1, nextX),
    y: Math.max(1, nextY),
    w: Math.min(nextW, maxW),
    h: Math.min(nextH, maxH),
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

function getGridMetrics() {
  const rect = grid.getBoundingClientRect();
  const columnWidth = rect.width / 6;
  const rowStep = 120 + 12;
  return { columnWidth, rowStep };
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
  scheduleSave();
}

if (deviceForm) {
  deviceForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!(permissions?.is_admin || permissions?.can_manage_devices)) {
      return;
    }
    const formData = new FormData(deviceForm);
    discoveryPreferredName = String(formData.get("name") || "").trim();
    openDeviceDiscoverModal();
    discoveredDevicesCache = [];
    renderDiscoveredDevices({ updateStatus: false });
    if (deviceDiscoverList) {
      deviceDiscoverList.textContent = "Klik op Scannen om apparaten te zoeken.";
    }
    setDiscoverScanState("idle", "Klaar om te scannen.");
  });
}

let discoveredDevicesCache = [];
let showOnlyPlcCandidates = false;
let plcOnlyScan = false;
let discoveryPreferredName = "";
let discoverRequestController = null;
let discoverRequestSerial = 0;
let discoverEventSource = null;
let discoverScanState = "idle";

function setDiscoverScanState(state, text) {
  discoverScanState = state;
  if (!deviceDiscoverStatus) {
    return;
  }
  deviceDiscoverStatus.classList.remove("scan-state-idle", "scan-state-busy", "scan-state-done");
  if (state === "busy") {
    deviceDiscoverStatus.classList.add("scan-state-busy");
  } else if (state === "done") {
    deviceDiscoverStatus.classList.add("scan-state-done");
  } else {
    deviceDiscoverStatus.classList.add("scan-state-idle");
  }
  if (typeof text === "string") {
    deviceDiscoverStatus.textContent = text;
  }
}

function setDiscoverButtonsBusy(isBusy) {
  if (deviceDiscoverRefresh) {
    deviceDiscoverRefresh.disabled = isBusy;
  }
  if (deviceDiscoverScanPlcOnly) {
    deviceDiscoverScanPlcOnly.disabled = isBusy;
  }
  if (deviceDiscoverAddAllPlc) {
    deviceDiscoverAddAllPlc.disabled = isBusy;
  }
}

function openDeviceDiscoverModal() {
  if (deviceDiscoverModal) {
    deviceDiscoverModal.classList.add("open");
  }
}

function closeDeviceDiscoverModal() {
  if (discoverEventSource) {
    discoverEventSource.close();
    discoverEventSource = null;
  }
  if (discoverRequestController) {
    discoverRequestController.abort();
    discoverRequestController = null;
  }
  setDiscoverButtonsBusy(false);
  setDiscoverScanState("idle", "Klaar om te scannen.");
  if (deviceDiscoverModal) {
    deviceDiscoverModal.classList.remove("open");
  }
}

async function addDiscoveredDevice(device) {
  const finalName = (discoveryPreferredName || "").trim() || device.suggested_name || `PLC ${device.ip}`;
  const response = await fetch("/api/devices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: finalName,
      ip: device.ip,
      mac: device.mac || "",
    }),
  });

  if (!response.ok) {
    return false;
  }

  await loadDevices();
  if (device?.plc_candidate) {
    const addedDevice = (Array.isArray(deviceCache) ? deviceCache : []).find((row) => row.ip === device.ip);
    if (addedDevice) {
      ensurePlcModuleForDevice(addedDevice);
    }
  }
  await loadDiscoveredDevices();
  return true;
}

async function addAllPlcCandidates() {
  const plcCandidates = discoveredDevicesCache.filter((device) => !device.already_added && device.plc_candidate);
  if (!plcCandidates.length) {
    if (deviceDiscoverStatus) {
      deviceDiscoverStatus.textContent = "Geen nieuwe PLC-kandidaten om toe te voegen.";
    }
    return;
  }

  if (deviceDiscoverStatus) {
    deviceDiscoverStatus.textContent = `Toevoegen van ${plcCandidates.length} PLC-kandidaten...`;
  }

  let added = 0;
  for (const device of plcCandidates) {
    const ok = await addDiscoveredDevice(device);
    if (ok) {
      added += 1;
    }
  }

  if (deviceDiscoverStatus) {
    deviceDiscoverStatus.textContent = `${added} PLC-kandida(a)t(en) toegevoegd.`;
  }
}

function renderDiscoveredDevices(options = {}) {
  const updateStatus = options.updateStatus !== false;
  if (!deviceDiscoverCandidates || !deviceDiscoverStatus) {
    return;
  }

  const source = Array.isArray(discoveredDevicesCache) ? discoveredDevicesCache : [];
  const filtered = showOnlyPlcCandidates ? source.filter((device) => device.plc_candidate) : source;
  const plcCount = source.filter((device) => device.plc_candidate).length;
  const unknownCount = source.filter((device) => device.device_type === "unknown").length;

  if (updateStatus) {
    deviceDiscoverStatus.textContent = `${plcCount} PLC-kandidaat(en), ${unknownCount} onbekend, ${source.length} totaal${showOnlyPlcCandidates ? " · filter actief" : ""}.`;
  }
  if (deviceDiscoverFilterPlc) {
    deviceDiscoverFilterPlc.textContent = showOnlyPlcCandidates ? "Toon alle apparaten" : "Alleen PLC-kandidaten";
  }

  deviceDiscoverCandidates.innerHTML = "";
  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "device-sub";
    empty.textContent = showOnlyPlcCandidates
      ? "Geen PLC-kandidaten in deze scan."
      : "Geen apparaten gevonden op het netwerk.";
    deviceDiscoverCandidates.appendChild(empty);
    return;
  }

  filtered.forEach((device) => {
    const row = document.createElement("div");
    row.className = "device-row";

    const nameWrap = document.createElement("div");
    nameWrap.className = "device-meta";
    const nameEl = document.createElement("span");
    nameEl.textContent = device.suggested_name || `PLC ${device.ip}`;

    const detailsEl = document.createElement("span");
    detailsEl.className = "device-sub";
    const deviceTypeNL = { plc: "PLC", router: "Router", computer: "Computer", phone: "Telefoon", printer: "Printer", camera: "Camera", iot: "IoT-apparaat", "raspberry-pi": "Raspberry Pi", "network-device": "Netwerkapparaat", unknown: "Onbekend" };
    const connectionNL = {
      wifi: "wifi",
      ethernet: "ethernet",
      "rechtstreeks (kabel)": "rechtstreeks (kabel)",
      onbekend: "onbekend",
    };
    const typeLabel = `Type: ${deviceTypeNL[device.device_type] || device.device_type || "Onbekend"}`;
    const hostLabel = device.hostname ? ` · Hostnaam: ${device.hostname}` : "";
    const serviceLabel = Array.isArray(device.services) && device.services.length ? ` · Service: ${device.services.join(", ")}` : "";
    const methodLabel = Array.isArray(device.found_via) && device.found_via.length ? ` · Gevonden via: ${device.found_via.join(", ")}` : "";
    const connectionLabel = device.connection_type ? ` · Verbinding: ${connectionNL[device.connection_type] || device.connection_type}` : "";
    const attempts = Number(device.scan_attempts || 1);
    const attemptsLabel = ` · Pogingen: ${Math.max(1, attempts)}/4`;
    const macLabel = device.mac ? ` · MAC: ${device.mac}` : " · MAC: -";
    detailsEl.textContent = `${typeLabel}${hostLabel}${serviceLabel}${methodLabel}${connectionLabel}${attemptsLabel}${macLabel}`;

    nameWrap.appendChild(nameEl);
    nameWrap.appendChild(detailsEl);

    const ipEl = document.createElement("span");
    ipEl.textContent = device.ip;

    const actions = document.createElement("div");
    actions.className = "device-actions";
    const addBtn = document.createElement("button");
    addBtn.className = "device-action";
    addBtn.type = "button";

    if (device.already_added) {
      addBtn.textContent = "Al toegevoegd";
      addBtn.disabled = true;
    } else {
      addBtn.textContent = device.plc_candidate ? "Toevoegen" : "Voeg apparaat toe";
      addBtn.addEventListener("click", async () => {
        addBtn.disabled = true;
        const ok = await addDiscoveredDevice(device);
        if (!ok) {
          addBtn.disabled = false;
        }
      });
    }

    actions.appendChild(addBtn);
    row.appendChild(nameWrap);
    row.appendChild(ipEl);
    row.appendChild(actions);
    deviceDiscoverCandidates.appendChild(row);
  });
}

async function loadDiscoveredDevices() {
  if (!deviceDiscoverCandidates || !deviceDiscoverStatus) {
    return;
  }
  if (discoverEventSource) {
    discoverEventSource.close();
    discoverEventSource = null;
  }
  if (discoverRequestController) {
    discoverRequestController.abort();
  }
  const requestId = ++discoverRequestSerial;
  discoverRequestController = new AbortController();
  setDiscoverScanState("busy", plcOnlyScan ? "Zoeken naar PLC's..." : "Zoeken op netwerk...");
  deviceDiscoverCandidates.innerHTML = "";
  setDiscoverButtonsBusy(true);
  if (deviceDiscoverScanPlcOnly) {
    deviceDiscoverScanPlcOnly.textContent = plcOnlyScan ? "Volledige scan" : "Scan enkel PLC's";
    deviceDiscoverScanPlcOnly.classList.toggle("active", plcOnlyScan);
  }

  discoveredDevicesCache = [];
  renderDiscoveredDevices({ updateStatus: false });

  const url = plcOnlyScan ? "/api/devices/discover/stream?max_hosts=254&plc_only=1" : "/api/devices/discover/stream?max_hosts=254";
  const timeoutId = setTimeout(() => {
    if (discoverEventSource) {
      discoverEventSource.close();
      discoverEventSource = null;
    }
    if (requestId === discoverRequestSerial) {
      setDiscoverScanState("idle", "Scan geannuleerd of timeout bereikt.");
      discoverRequestController = null;
      setDiscoverButtonsBusy(false);
    }
  }, plcOnlyScan ? 90000 : 120000);

  try {
    const source = new EventSource(url);
    discoverEventSource = source;

    source.addEventListener("progress", (event) => {
      if (requestId !== discoverRequestSerial) {
        return;
      }
      try {
        const data = JSON.parse(event.data || "{}");
        const processed = Number(data.processed || 0);
        const total = Number(data.total || 0);
        if (processed > 0 && total > 0) {
          setDiscoverScanState("busy", `${plcOnlyScan ? "PLC-scan" : "Scan"} bezig: ${processed}/${total}`);
        }
      } catch (_) {
      }
    });

    source.addEventListener("device", (event) => {
      if (requestId !== discoverRequestSerial) {
        return;
      }
      try {
        const data = JSON.parse(event.data || "{}");
        const device = data.device;
        if (!device || !device.ip) {
          return;
        }
        discoveredDevicesCache.push(device);
        renderDiscoveredDevices({ updateStatus: false });
      } catch (_) {
      }
    });

    source.addEventListener("done", (event) => {
      if (requestId !== discoverRequestSerial) {
        return;
      }
      try {
        const data = JSON.parse(event.data || "{}");
        if (Array.isArray(data.devices)) {
          discoveredDevicesCache = data.devices;
        }
        if (deviceDiscoverList) {
          deviceDiscoverList.textContent = `${discoveredDevicesCache.length} apparaat(en) gevonden in subnet ${data.subnet || "onbekend"}.`;
        }
        renderDiscoveredDevices();
        setDiscoverScanState("done", deviceDiscoverStatus.textContent);
      } catch (_) {
      }
      if (discoverEventSource) {
        discoverEventSource.close();
        discoverEventSource = null;
      }
      clearTimeout(timeoutId);
      if (requestId === discoverRequestSerial) {
        discoverRequestController = null;
        setDiscoverButtonsBusy(false);
      }
    });

    source.addEventListener("error", () => {
      if (requestId !== discoverRequestSerial) {
        return;
      }
      setDiscoverScanState("idle", "Kon netwerkapparaten niet vinden.");
      if (discoverEventSource) {
        discoverEventSource.close();
        discoverEventSource = null;
      }
      clearTimeout(timeoutId);
      if (requestId === discoverRequestSerial) {
        discoverRequestController = null;
        setDiscoverButtonsBusy(false);
      }
    });
  } catch (error) {
    if (requestId !== discoverRequestSerial) {
      return;
    }
    setDiscoverScanState("idle", "Kon netwerkapparaten niet vinden.");
    discoveredDevicesCache = [];
  } finally {
    // busy-state cleanup gebeurt in done/error handlers
  }
}

if (deviceDiscoverClose) {
  deviceDiscoverClose.addEventListener("click", () => {
    closeDeviceDiscoverModal();
  });
}

if (deviceDiscoverRefresh) {
  deviceDiscoverRefresh.addEventListener("click", async () => {
    await loadDiscoveredDevices();
  });
}

if (deviceDiscoverFilterPlc) {
  deviceDiscoverFilterPlc.addEventListener("click", () => {
    showOnlyPlcCandidates = !showOnlyPlcCandidates;
    renderDiscoveredDevices();
  });
}

if (deviceDiscoverScanPlcOnly) {
  deviceDiscoverScanPlcOnly.addEventListener("click", async () => {
    plcOnlyScan = !plcOnlyScan;
    await loadDiscoveredDevices();
  });
}

if (deviceDiscoverAddAllPlc) {
  deviceDiscoverAddAllPlc.addEventListener("click", async () => {
    deviceDiscoverAddAllPlc.disabled = true;
    try {
      await addAllPlcCandidates();
    } finally {
      deviceDiscoverAddAllPlc.disabled = false;
      await loadDiscoveredDevices();
    }
  });
}

if (deviceDiscoverModal) {
  deviceDiscoverModal.addEventListener("click", (event) => {
    if (event.target.classList && event.target.classList.contains("modal-backdrop")) {
      closeDeviceDiscoverModal();
    }
  });
}

if (plcModuleModalClose) {
  plcModuleModalClose.addEventListener("click", () => {
    closePlcModuleModal();
  });
}

if (plcModuleModal) {
  plcModuleModal.addEventListener("click", (event) => {
    if (event.target.classList && event.target.classList.contains("modal-backdrop")) {
      closePlcModuleModal();
    }
  });
}

async function loadDevices() {
  if (!deviceList) {
    return;
  }
  const response = await fetch("/api/devices");
  if (!response.ok) {
    deviceList.textContent = "Kon apparaten niet laden.";
    setStatsState("devices", { state: "offline", label: "Niet beschikbaar" });
    return;
  }
  const data = await response.json();
  applyDeviceStats(data.devices || []);
  setDeviceCache(data.devices || []);
  refreshStatsDevicesUI();
  deviceList.innerHTML = "";
  const canManage = permissions?.is_admin || permissions?.can_manage_devices;
  data.devices.forEach((device) => {
    const row = document.createElement("div");
    row.className = "device-row";
    const nameWrap = document.createElement("div");
    nameWrap.className = "device-meta";
    const nameEl = document.createElement("span");
    nameEl.textContent = device.name;
    const macEl = document.createElement("span");
    macEl.className = "device-sub";
    macEl.textContent = device.mac ? `MAC-adres: ${device.mac}` : "MAC-adres: -";
    nameWrap.appendChild(nameEl);
    nameWrap.appendChild(macEl);
    const ipEl = document.createElement("span");
    ipEl.textContent = device.ip;
    const actions = document.createElement("div");
    actions.className = "device-actions";
    const plcLike = isPlcLikeDevice(device);
    if (canManage) {
      if (!plcLike) {
        const dashboardLink = document.createElement("a");
        dashboardLink.className = "device-action";
        dashboardLink.href = `/devices/${device.id}`;
        dashboardLink.textContent = "Open dashboard";
        actions.appendChild(dashboardLink);
      }

      if (plcLike) {
        const plcButton = document.createElement("button");
        plcButton.className = "device-action";
        plcButton.type = "button";
        plcButton.textContent = "Open PLC module";
        plcButton.addEventListener("click", () => {
          ensurePlcModuleForDevice(device);
          openPlcModuleModal(device);
        });
        actions.appendChild(plcButton);
      }
    }
    row.appendChild(nameWrap);
    row.appendChild(ipEl);
    row.appendChild(actions);
    if (canManage) {
      const removeButton = document.createElement("button");
      removeButton.className = "device-remove";
      removeButton.type = "button";
      removeButton.textContent = "Verwijderen";
      removeButton.addEventListener("click", async () => {
        await fetch(`/api/devices/${device.id}`, { method: "DELETE" });
        loadDevices();
      });
      row.appendChild(removeButton);
    }
    deviceList.appendChild(row);
  });

  if (permissions?.is_admin || permissions?.can_manage_devices) {
    data.devices
      .filter((device) => !device.mac)
      .forEach((device) => {
        fetch(`/api/devices/${device.id}/mac`, { method: "POST" })
          .then((res) => res.json())
          .then((result) => {
            if (result?.mac) {
              loadDevices();
            }
          })
          .catch(() => {});
      });
  }
}

function applyDeviceStats(devices) {
  if (permissions && !permissions.can_view_devices) {
    return;
  }
}

async function refreshDeviceStats() {
  if (permissions && !permissions.can_view_devices) {
    setStatsState("devices", { state: "offline", label: "Geen toegang" });
    return;
  }
  const response = await fetch("/api/devices");
  if (!response.ok) {
    setStatsState("devices", { state: "offline", label: "Niet beschikbaar" });
    return;
  }
  const data = await response.json();
  applyDeviceStats(data.devices || []);
  setDeviceCache(data.devices || []);
}

async function runPing(host, outputEl) {
  const raw = String(host || "").trim();
  if (!raw) {
    outputEl.textContent = "Geef max 4 IP's in.";
    const moduleId = outputEl.closest(".module")?.dataset.id;
    if (moduleId) {
      updateModuleMemory(moduleId, { pingOutput: outputEl.textContent, pingHost: raw });
    }
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
  outputEl.textContent = "Pingen...";
  const moduleId = outputEl.closest(".module")?.dataset.id;
  if (moduleId) {
    updateModuleMemory(moduleId, { pingOutput: outputEl.textContent, pingHost: raw });
  }

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
    const delayMatch = (data.output || "").match(/time[=<]\s*(\d+)ms/i);
    const delay = delayMatch ? `${delayMatch[1]} ms` : "Failed";
    results.push(`${ip} - ${delay}`);
  }

  outputEl.textContent = results.join("\n");
  if (moduleId) {
    updateModuleMemory(moduleId, { pingOutput: outputEl.textContent, pingHost: raw });
  }
  setStatsState("ping", "idle");
}

function appendTerminalLine(outputEl, text) {
  const line = document.createElement("div");
  line.textContent = text;
  outputEl.appendChild(line);
  outputEl.scrollTop = outputEl.scrollHeight;
  const moduleId = outputEl.dataset.moduleId;
  if (moduleId) {
    updateModuleMemory(moduleId, { terminalLines: getTerminalLines(outputEl) });
  }
}

function clearTerminalOutput(outputEl, moduleId) {
  outputEl.innerHTML = "";
  updateModuleMemory(moduleId, { terminalLines: [] });
}

async function runTerminal(command, outputEl) {
  const moduleId = outputEl.dataset.moduleId;
  const statusEl = outputEl.closest(".module")?.querySelector(".module-status");
  if (statusEl) {
    statusEl.textContent = "Running…";
    statusEl.classList.add("running");
  }
  if (moduleId) {
    const prev = terminalControllers.get(moduleId);
    if (prev) {
      prev.abort();
    }
  }
  const controller = new AbortController();
  if (moduleId) {
    terminalControllers.set(moduleId, controller);
  }
  const response = await fetch("/api/terminal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
    signal: controller.signal,
  });
  const data = await response.json();
  if (!response.ok) {
    appendTerminalLine(outputEl, data.error || "Command failed.");
    if (statusEl) {
      statusEl.textContent = "Idle";
      statusEl.classList.remove("running");
    }
    setStatsState("terminal", "idle");
    return;
  }
  if (data.output) {
    data.output.split("\n").forEach((line) => appendTerminalLine(outputEl, line));
  }
  if (moduleId && terminalControllers.get(moduleId) === controller) {
    terminalControllers.delete(moduleId);
  }
  if (statusEl) {
    statusEl.textContent = "Idle";
    statusEl.classList.remove("running");
  }
  setStatsState("terminal", "idle");
}

async function stopTerminal(moduleId, outputEl) {
  if (!moduleId) {
    return;
  }
  const statusEl = outputEl.closest(".module")?.querySelector(".module-status");
  if (statusEl) {
    statusEl.textContent = "Stopping…";
    statusEl.classList.add("running");
  }
  const controller = terminalControllers.get(moduleId);
  if (controller) {
    controller.abort();
    terminalControllers.delete(moduleId);
  }
  appendTerminalLine(outputEl, "Stopping command...");
  const response = await fetch("/api/terminal/stop", { method: "POST" });
  if (!response.ok) {
    appendTerminalLine(outputEl, "Stop failed.");
    if (statusEl) {
      statusEl.textContent = "Idle";
      statusEl.classList.remove("running");
    }
    return;
  }
  appendTerminalLine(outputEl, "Command stopped.");
  setStatsState("terminal", "idle");
  if (statusEl) {
    statusEl.textContent = "Idle";
    statusEl.classList.remove("running");
  }
}

function setStatsState(key, value) {
  if (!statsState[key]) {
    return;
  }
  if (typeof value === "object" && value !== null) {
    statsState[key] = { ...statsState[key], ...value };
  } else {
    statsState[key] = { ...statsState[key], state: value };
  }
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
  const entry = statsState[key];
  const state = typeof entry === "string" ? entry : entry.state;
  item.dataset.state = state;
  if (label) {
    const customLabel = typeof entry === "object" ? entry.label : null;
    label.textContent = customLabel || (state === "running" ? "Running" : state === "offline" ? "Offline" : "Idle");
  }
  if (dot) {
    dot.setAttribute("title", label?.textContent || "");
  }
}

function updateStatsModule(container) {
  const items = container.querySelectorAll(".stats-item");
  items.forEach((item) => updateStatsItem(item));
}

function refreshStatsDevicesUI() {
  document.querySelectorAll(".module[data-key=\"stats\"]").forEach((module) => {
    const moduleId = module.dataset.id;
    const container = module.querySelector(".stats-list");
    if (!moduleId || !container) {
      return;
    }
    renderStatsSelection(container, moduleId);
  });
}

function renderStatsSelection(container, moduleId) {
  if (!container || !moduleId) {
    return;
  }
  const selection = getStatsSelection(moduleId);
  container.innerHTML = "";
  if (!selection.length) {
    container.textContent = "Geen items gekozen.";
    return;
  }
  selection.slice(0, MAX_STATS_ITEMS).forEach((item) => {
    if (item === "api") {
      const row = document.createElement("div");
      row.className = "stats-item";
      row.dataset.stat = "api";
      row.innerHTML = "<span class=\"stats-dot\"></span><span>API status</span><span class=\"stats-label\"></span>";
      updateStatsItem(row);
      container.appendChild(row);
      return;
    }
    if (item.startsWith("device:")) {
      const id = Number(item.split(":")[1]);
      const memory = loadModuleMemory();
      const fallback = memory[moduleId]?.selectedDeviceMeta?.[id];
      const match = deviceCache.find((device) => device.id === id) || fallback;
      const resolved = match && !match.id && fallback
        ? { id, name: fallback.name, ip: fallback.ip }
        : match;
      const row = document.createElement("div");
      row.className = "stats-item";
      row.dataset.deviceId = String(id);
      row.dataset.state = "running";
      const labelText = resolved ? `${resolved.name} (${resolved.ip})` : "Apparaat laden...";
      row.innerHTML = `<span class=\"stats-dot\"></span><span>${labelText}</span><span class=\"stats-label\">Laden...</span>`;
      if (resolved) {
        applyDevicePingState(row, resolved);
        pingStatsDevice(resolved);
      } else {
        refreshDeviceStats();
      }
      container.appendChild(row);
    }
  });
}

function pingStatsDevice(device) {
  const now = Date.now();
  const existing = statsPingState.get(device.id) || {
    status: "unknown",
    lastSeen: null,
    lastChecked: 0,
    pending: false,
  };
  if (existing.pending || now - existing.lastChecked < STATS_PING_INTERVAL) {
    return;
  }
  existing.pending = true;
  existing.lastChecked = now;
  statsPingState.set(device.id, existing);
  fetch("/api/ping", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ host: device.ip }),
  })
    .then(async (response) => {
      const data = await response.json();
      const success = response.ok && /time[=<]\s*(\d+)ms/i.test(data.output || "");
      const next = statsPingState.get(device.id) || existing;
      const prevStatus = next.status;
      next.pending = false;
      next.status = success ? "online" : "offline";
      if (success) {
        next.lastSeen = Date.now();
      }
      statsPingState.set(device.id, next);
      updateStatsDeviceRows(device.id);
      if (prevStatus !== "offline" && next.status === "offline") {
        notifyDeviceOffline(device);
      }
      if (prevStatus === "offline" && next.status === "online") {
        notifyDeviceOnline(device);
      }
    })
    .catch(() => {
      const next = statsPingState.get(device.id) || existing;
      const prevStatus = next.status;
      next.pending = false;
      next.status = "offline";
      statsPingState.set(device.id, next);
      updateStatsDeviceRows(device.id);
      if (prevStatus !== "offline") {
        notifyDeviceOffline(device);
      }
    });
}

function updateStatsDeviceRows(deviceId) {
  document
    .querySelectorAll(`.stats-item[data-device-id=\"${deviceId}\"]`)
    .forEach((row) => {
      const device = deviceCache.find((entry) => entry.id === Number(deviceId));
      if (device) {
        applyDevicePingState(row, device);
      }
    });
}

function refreshAllStatsRows() {
  refreshApiStatus();
  document.querySelectorAll(".stats-item[data-device-id]").forEach((row) => {
    const deviceId = Number(row.dataset.deviceId);
    const device = deviceCache.find((entry) => entry.id === deviceId);
    if (device) {
      applyDevicePingState(row, device);
    }
  });
}

function refreshApiStatus() {
  fetch("/api/system/status")
    .then((response) => response.json())
    .then((data) => {
      if (data.api_enabled) {
        setStatsEntryState("api", { state: "running", label: "Ingeschakeld" });
      } else {
        setStatsEntryState("api", { state: "offline", label: "Uitgeschakeld" });
      }
    })
    .catch(() => {
      setStatsEntryState("api", { state: "offline", label: "Onbereikbaar" });
    });
}

function setStatsEntryState(key, value) {
  if (!statsState[key]) {
    statsState[key] = value;
  } else {
    statsState[key] = { ...statsState[key], ...value };
  }
  document.querySelectorAll(`.stats-item[data-stat="${key}"]`).forEach((item) => {
    updateStatsItem(item);
  });
}

function refreshStatsPings() {
  document.querySelectorAll(".stats-item[data-device-id]").forEach((row) => {
    const deviceId = Number(row.dataset.deviceId);
    const device = deviceCache.find((entry) => entry.id === deviceId);
    if (device) {
      pingStatsDevice(device);
    }
  });
}

function startStatsTicker() {
  if (statsTickerId) {
    return;
  }
  statsTickerId = window.setInterval(() => {
    refreshAllStatsRows();
  }, 1000);
}

function startStatsPingLoop() {
  if (statsPingLoopId) {
    return;
  }
  statsPingLoopId = window.setInterval(() => {
    refreshStatsPings();
  }, STATS_PING_INTERVAL);
  refreshStatsPings();
}

function applyDevicePingState(row, device) {
  const entry = statsPingState.get(device.id);
  const label = row.querySelector(".stats-label");
  if (!label) {
    return;
  }
  if (!entry) {
    row.dataset.state = "idle";
    label.textContent = "Wachten...";
    return;
  }
  if (entry.status === "online") {
    row.dataset.state = "running";
    const lastSeen = entry.lastSeen || Date.now();
    label.textContent = `Laatst gezien ${formatRelativeTime(lastSeen)}`;
    return;
  }
  row.dataset.state = "offline";
  if (entry.lastSeen) {
    label.textContent = `Offline · Laatst gezien ${formatRelativeTime(entry.lastSeen)}`;
  } else {
    label.textContent = "Offline";
  }
}

function formatRelativeTime(timestamp) {
  const diff = Math.max(0, Date.now() - timestamp);
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) {
    return `${seconds}s geleden`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m geleden`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}u geleden`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d geleden`;
}

function ensureToastContainer() {
  if (toastContainer) {
    return toastContainer;
  }
  toastContainer = document.createElement("div");
  toastContainer.className = "toast-container";
  document.body.appendChild(toastContainer);
  return toastContainer;
}

function notifyDeviceOffline(device) {
  const statsModules = Array.from(document.querySelectorAll('.module[data-key="stats"]'));
  if (!statsModules.length) {
    return;
  }
  const isSelected = statsModules.some((module) => {
    const moduleId = module.dataset.id;
    if (!moduleId) {
      return false;
    }
    const selection = getStatsSelection(moduleId);
    return selection.includes(`device:${device.id}`);
  });
  if (!isSelected) {
    return;
  }
  const container = ensureToastContainer();
  const toast = document.createElement("div");
  toast.className = "toast toast-warning";
  const macLabel = device.mac ? ` · ${device.mac}` : "";
  toast.innerHTML = `<div class=\"toast-title\">Apparaat offline</div><div>${device.name} (${device.ip})${macLabel}</div>`;
  container.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, 5000);
}

function notifyDeviceOnline(device) {
  const statsModules = Array.from(document.querySelectorAll('.module[data-key="stats"]'));
  if (!statsModules.length) {
    return;
  }
  const isSelected = statsModules.some((module) => {
    const moduleId = module.dataset.id;
    if (!moduleId) {
      return false;
    }
    const selection = getStatsSelection(moduleId);
    return selection.includes(`device:${device.id}`);
  });
  if (!isSelected) {
    return;
  }
  const container = ensureToastContainer();
  const toast = document.createElement("div");
  toast.className = "toast";
  const macLabel = device.mac ? ` · ${device.mac}` : "";
  toast.innerHTML = `<div class=\"toast-title\">Apparaat online</div><div>${device.name} (${device.ip})${macLabel}</div>`;
  container.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, 5000);
}

function findFirstAvailableSpot(moduleData) {
  const maxRows = getMaxRows();
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

function getMaxRows() {
  const rowStep = 120 + 12;
  const height = grid.clientHeight || 0;
  return Math.max(1, Math.floor(height / rowStep));
}

function openModal() {
  moduleModal.classList.add("open");
  moduleModal.setAttribute("aria-hidden", "false");
}

function closeModal() {
  moduleModal.classList.remove("open");
  moduleModal.setAttribute("aria-hidden", "true");
}

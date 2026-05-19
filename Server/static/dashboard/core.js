// DOM Elements
const grid = document.getElementById("grid");
const moduleTemplate = document.getElementById("moduleTemplate");
const themeToggle = document.getElementById("themeToggle");
const themeIcon = document.getElementById("themeIcon");
const settingsToggle = document.getElementById("settingsToggle");
const settingsMenu = document.getElementById("settingsMenu");
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

// Constants
const MEMORY_KEY = "module-memory";
const ACTIVE_PANEL_KEY = "active-panel";
const THEME_STORAGE_KEY = "dashboard-theme";
const MAX_STATS_ITEMS = 4;
const STATS_PING_INTERVAL = 5000;

// Global State
const terminalControllers = new Map();
const statsState = {
  api: { state: "idle", label: null },
  terminal: { state: "idle", label: null },
  ping: { state: "idle", label: null },
};

let permissions = null;
let allowedModules = null;
let currentUserId = null;
let deviceCache = [];
let activeStatsModuleId = null;
const statsPingState = new Map();
let statsTickerId = null;
let statsPingLoopId = null;
let toastContainer = null;
let adminActivityTimer = null;
let selectedGroupId = null;
let cachedGroups = [];
let cachedUsers = [];
let activeEditUser = null;
let accountsGroupSearchTerm = "";
let accountsUserSearchTerm = "";

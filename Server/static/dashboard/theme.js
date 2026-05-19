// Theme Management
function applyTheme(theme) {
  document.body.classList.toggle("theme-dark", theme === "dark");
  if (themeIcon) {
    themeIcon.textContent = theme === "dark" ? "🌙" : "☀️";
  }
  localStorage.setItem(THEME_STORAGE_KEY, theme);
}

if (themeToggle) {
  themeToggle.addEventListener("click", async () => {
    const nextTheme = localStorage.getItem(THEME_STORAGE_KEY) === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: nextTheme, layout: state.modules }),
    });
  });
}

if (settingsToggle) {
  settingsToggle.addEventListener("click", () => {
    if (!settingsMenu) return;
    if (settingsMenu.classList.contains("open")) {
      settingsMenu.classList.remove("open");
      settingsMenu.setAttribute("aria-hidden", "true");
    } else {
      settingsMenu.classList.add("open");
      settingsMenu.setAttribute("aria-hidden", "false");
    }
  });
}

const state = {
  theme: localStorage.getItem(THEME_STORAGE_KEY) || "light",
  modules: [],
};

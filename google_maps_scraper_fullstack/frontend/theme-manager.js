// ========================================
// THEME-MANAGER.JS - Theme Management
// ========================================

const ThemeManager = {
  // Initialize theme
  init() {
    const savedTheme = Utils.getTheme();
    const htmlEl = document.documentElement;

    // Set initial theme
    if (!savedTheme || (savedTheme !== 'dark' && savedTheme !== 'light')) {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const defaultTheme = prefersDark ? 'dark' : 'light';
      Utils.setTheme(defaultTheme);
      htmlEl.setAttribute('data-theme', defaultTheme);
    } else {
      htmlEl.setAttribute('data-theme', savedTheme);
    }

    this.setupThemeToggle();
    this.setupSystemPreference();
  },

  // Setup theme toggle button
  setupThemeToggle() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;

    btn.addEventListener('click', () => {
      const current = Utils.getTheme();
      const next = current === 'dark' ? 'light' : 'dark';
      this.setTheme(next);
    });
  },

  // Listen for system theme changes
  setupSystemPreference() {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', (e) => {
      const newTheme = e.matches ? 'dark' : 'light';
      // Only auto-change if user hasn't set a preference
      const saved = localStorage.getItem('theme');
      if (!saved) {
        this.setTheme(newTheme);
      }
    });
  },

  // Set theme
  setTheme(theme) {
    if (theme !== 'dark' && theme !== 'light') {
      console.warn('Invalid theme:', theme);
      return;
    }

    document.documentElement.setAttribute('data-theme', theme);
    Utils.storage.set('theme', theme);

    // Trigger custom event for any listeners
    window.dispatchEvent(
      new CustomEvent('themechange', { detail: { theme } })
    );
  },

  // Get current theme
  getTheme() {
    return Utils.getTheme();
  },

  // Toggle theme
  toggleTheme() {
    const current = this.getTheme();
    this.setTheme(current === 'dark' ? 'light' : 'dark');
  },
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => ThemeManager.init());
} else {
  ThemeManager.init();
}

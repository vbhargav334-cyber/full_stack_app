// ========================================
// UTILS.JS - Utility Functions
// ========================================

const Utils = {
  // Store/Retrieve from localStorage
  storage: {
    set(key, value) {
      try {
        localStorage.setItem(key, JSON.stringify(value));
      } catch (e) {
        console.warn('Storage error:', e);
      }
    },
    get(key, defaultValue = null) {
      try {
        const item = localStorage.getItem(key);
        return item ? JSON.parse(item) : defaultValue;
      } catch (e) {
        console.warn('Storage error:', e);
        return defaultValue;
      }
    },
    remove(key) {
      try {
        localStorage.removeItem(key);
      } catch (e) {
        console.warn('Storage error:', e);
      }
    },
  },

  // Escape HTML to prevent XSS
  escapeHtml(text) {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;',
    };
    return String(text || '').replace(/[&<>"']/g, (m) => map[m]);
  },

  // Format numbers with commas
  formatNumber(num) {
    return Number(num).toLocaleString();
  },

  // Format date
  formatDate(date) {
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  },

  // Debounce function
  debounce(fn, delay = 300) {
    let timeoutId;
    return function (...args) {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fn.apply(this, args), delay);
    };
  },

  // Throttle function
  throttle(fn, delay = 300) {
    let lastCall = 0;
    return function (...args) {
      const now = Date.now();
      if (now - lastCall >= delay) {
        fn.apply(this, args);
        lastCall = now;
      }
    };
  },

  // API fetch wrapper
  async api(path, options = {}) {
    const res = await fetch(path, options);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Request failed: ${res.status}`);
    }
    return res.json();
  },

  // Show toast notification
  showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toast.style.animation = 'slideIn 0.3s ease-out';

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease-out';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  },

  // Get current theme
  getTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
  },

  // Set theme
  setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    Utils.storage.set('theme', theme);
  },

  // Get current language
  getLanguage() {
    return Utils.storage.get('language', 'en');
  },

  // Set language
  setLanguage(lang) {
    Utils.storage.set('language', lang);
  },

  // Translate text (placeholder - will be enhanced by i18n)
  t(key) {
    return key;
  },
};

// Export for use
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Utils;
}

// ========================================
// DRAGGABLE-PANELS.JS - Panel Drag & Resize
// ========================================

const DraggableManager = {
  panels: new Map(),

  init() {
    setTimeout(() => {
      this.setupPanels();
      this.setupNavigation();
    }, 100);
  },

  setupPanels() {
    const panelElements = document.querySelectorAll('[draggable-panel]');
    panelElements.forEach((panelEl) => {
      const panelId = panelEl.id;
      this.panels.set(panelId, {
        el: panelEl,
        isDragging: false,
        startX: 0,
        startY: 0,
        offsetX: 0,
        offsetY: 0,
      });

      this.setupDragHeader(panelEl);
      this.setupPanelControls(panelEl);
    });
  },

  setupDragHeader(panelEl) {
    const header = panelEl.querySelector('.panel-header');
    if (!header) return;

    header.addEventListener('mousedown', (e) => {
      if (e.target.closest('.panel-controls')) return;

      const panelId = panelEl.id;
      const panel = this.panels.get(panelId);
      if (!panel) return;

      panel.isDragging = true;
      panel.startX = e.clientX;
      panel.startY = e.clientY;

      const rect = panelEl.getBoundingClientRect();
      panel.offsetX = e.clientX - rect.left;
      panel.offsetY = e.clientY - rect.top;

      panelEl.classList.add('dragging');
      panelEl.style.position = 'fixed';
      panelEl.style.zIndex = '999';

      const handleMouseMove = (moveEvent) => {
        if (!panel.isDragging) return;

        const x = moveEvent.clientX - panel.offsetX;
        const y = moveEvent.clientY - panel.offsetY;

        panelEl.style.left = x + 'px';
        panelEl.style.top = y + 'px';
      };

      const handleMouseUp = () => {
        panel.isDragging = false;
        panelEl.classList.remove('dragging');
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);

        // Save panel positions
        this.savePanelLayout();
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    });
  },

  setupPanelControls(panelEl) {
    const controls = panelEl.querySelector('.panel-controls');
    if (!controls) return;

    // Minimize button
    const minimizeBtn = controls.querySelector('.minimize-btn');
    if (minimizeBtn) {
      minimizeBtn.addEventListener('click', () => {
        const body = panelEl.querySelector('.panel-body');
        if (body) {
          body.style.display = body.style.display === 'none' ? 'block' : 'none';
          minimizeBtn.textContent = body.style.display === 'none' ? '□' : '−';
        }
      });
    }

    // Maximize button
    const maximizeBtn = controls.querySelector('.maximize-btn');
    if (maximizeBtn) {
      maximizeBtn.addEventListener('click', () => {
        const isMaximized = panelEl.style.width === '100vw';
        if (isMaximized) {
          panelEl.style.width = '';
          panelEl.style.height = '';
          panelEl.style.left = '';
          panelEl.style.top = '';
          maximizeBtn.textContent = '⬜';
        } else {
          panelEl.style.position = 'fixed';
          panelEl.style.top = '56px';
          panelEl.style.left = '0';
          panelEl.style.width = 'calc(100vw - 240px)';
          panelEl.style.height = 'calc(100vh - 56px - 80px)';
          panelEl.style.zIndex = '100';
          maximizeBtn.textContent = '❐';
        }
      });
    }

    // Close button
    const closeBtn = controls.querySelector('.close-btn');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        panelEl.style.display = 'none';
      });
    }
  },

  setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.section');
    const sidebarCollapse = document.getElementById('sidebar-collapse');
    const sidebar = document.querySelector('.sidebar');

    navItems.forEach((item) => {
      item.addEventListener('click', (e) => {
        e.preventDefault();

        // Remove active from all
        navItems.forEach((n) => n.classList.remove('active'));
        sections.forEach((s) => s.classList.remove('active'));

        // Add active to clicked
        item.classList.add('active');
        const sectionId = item.getAttribute('data-section');
        const section = document.getElementById(sectionId);
        if (section) section.classList.add('active');
      });
    });

    // Sidebar collapse
    if (sidebarCollapse && sidebar) {
      sidebarCollapse.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        Utils.storage.set('sidebarCollapsed', sidebar.classList.contains('collapsed'));
      });

      // Restore collapsed state
      const wasCollapsed = Utils.storage.get('sidebarCollapsed', false);
      if (wasCollapsed) {
        sidebar.classList.add('collapsed');
      }
    }
  },

  savePanelLayout() {
    const layout = {};
    this.panels.forEach((panel, panelId) => {
      const el = panel.el;
      layout[panelId] = {
        display: el.style.display,
        position: el.style.position,
        left: el.style.left,
        top: el.style.top,
        width: el.style.width,
        height: el.style.height,
      };
    });
    Utils.storage.set('panelLayout', layout);
  },

  restorePanelLayout() {
    const layout = Utils.storage.get('panelLayout', {});
    this.panels.forEach((panel, panelId) => {
      const el = panel.el;
      const config = layout[panelId];
      if (config) {
        Object.assign(el.style, config);
      }
    });
  },

  resetLayout() {
    this.panels.forEach((panel) => {
      const el = panel.el;
      el.style.display = '';
      el.style.position = '';
      el.style.left = '';
      el.style.top = '';
      el.style.width = '';
      el.style.height = '';
    });
    this.savePanelLayout();
  },
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => DraggableManager.init());
} else {
  DraggableManager.init();
}

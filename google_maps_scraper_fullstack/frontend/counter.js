// ========================================
// COUNTER.JS - KPI Card Count-Up Animations
// ========================================

const CounterManager = {
  animatingElements: new Map(),

  init() {
    // Watch for changes to KPI numbers and animate them
    this.observeKPICards();
  },

  observeKPICards() {
    const kpiElements = [
      { id: 'active-jobs-count', isPercentage: false },
      { id: 'success-rate-pct', isPercentage: true },
      { id: 'emails-found-count', isPercentage: false },
    ];

    // Create observer for element mutations
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        const element = mutation.target;
        if (element && element.textContent) {
          const newValue = element.textContent.trim();
          const numValue = parseInt(newValue.replace('%', '')) || 0;

          // Animate if value is greater than 0
          if (numValue > 0 && !this.animatingElements.get(element.id)) {
            this.animateCountUp(element, numValue, newValue.includes('%'));
          }
        }
      });
    });

    kpiElements.forEach(({ id, isPercentage }) => {
      const element = document.getElementById(id);
      if (element) {
        observer.observe(element, { characterData: true, subtree: true });
        // Add animation class
        element.classList.add('countup-number');
      }
    });
  },

  animateCountUp(element, targetValue, isPercentage = false) {
    this.animatingElements.set(element.id, true);

    const startValue = 0;
    const duration = 1200; // 1.2 seconds
    const startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Easing function: cubic-bezier
      const easeProgress = progress < 0.5
        ? 4 * progress * progress * progress
        : 1 - Math.pow(-2 * progress + 2, 3) / 2;

      const currentValue = Math.floor(startValue + (targetValue - startValue) * easeProgress);
      element.textContent = currentValue + (isPercentage ? '%' : '');

      // Pulse effect every 100ms
      if (Math.floor(elapsed / 100) % 2 === 0) {
        element.style.transform = 'scale(1.05)';
      } else {
        element.style.transform = 'scale(1)';
      }

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        element.textContent = targetValue + (isPercentage ? '%' : '');
        element.style.transform = 'scale(1)';
        this.animatingElements.delete(element.id);
      }
    };

    animate();
  },
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    CounterManager.init();
  });
} else {
  CounterManager.init();
}

// Add CSS for countup animation
const style = document.createElement('style');
style.textContent = `
  .countup-number {
    transition: transform 0.1s ease-out;
  }
`;
document.head.appendChild(style);

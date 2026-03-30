// ========================================
// ANALYTICS.JS - Data Visualization & Charts
// ========================================

const AnalyticsManager = {
  charts: {},
  analyticsData: null,
  currentChartType: 'category',

  init() {
    this.setupEventListeners();
    this.initializeCharts();
  },

  splitEmailValues(value) {
    return String(value || '')
      .split(/[;,\n]+/)
      .map((email) => email.trim())
      .filter(Boolean);
  },

  countEmailValues(value) {
    return this.splitEmailValues(value).length;
  },

  setupEventListeners() {
    const fileInput = document.getElementById('analytics-file-input');
    const chartTypeSelect = document.getElementById('chart-type-select');

    if (fileInput) {
      fileInput.addEventListener('change', (e) => this.handleFileUpload(e));
    }

    if (chartTypeSelect) {
      chartTypeSelect.addEventListener('change', (e) => {
        this.currentChartType = e.target.value;
        this.updateCharts();
      });
    }
  },

  initializeCharts() {
    // Chart.js color palette
    const colors = {
      primary: 'rgba(59, 130, 246, 0.8)',
      primaryLight: 'rgba(59, 130, 246, 0.3)',
      success: 'rgba(16, 185, 129, 0.8)',
      warning: 'rgba(245, 158, 11, 0.8)',
      error: 'rgba(239, 68, 68, 0.8)',
      info: 'rgba(6, 182, 212, 0.8)',
    };

    const chartConfig = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: 'rgba(241, 245, 249, 0.8)',
            font: { size: 12 },
            padding: 15,
          },
        },
      },
      scales: {
        y: {
          ticks: { color: 'rgba(241, 245, 249, 0.6)' },
          grid: { color: 'rgba(148, 163, 184, 0.1)' },
        },
        x: {
          ticks: { color: 'rgba(241, 245, 249, 0.6)' },
          grid: { color: 'rgba(148, 163, 184, 0.1)' },
        },
      },
    };

    // Category Chart (Pie)
    const categoryCtx = document.getElementById('categoryChart');
    if (categoryCtx) {
      this.charts.category = new Chart(categoryCtx, {
        type: 'doughnut',
        data: {
          labels: ['No Data'],
          datasets: [{
            data: [1],
            backgroundColor: [colors.primaryLight],
            borderColor: [colors.primary],
            borderWidth: 2,
          }],
        },
        options: { ...chartConfig, plugins: { ...chartConfig.plugins, legend: { position: 'bottom' } } },
      });
    }

    // Rating Chart (Bar)
    const ratingCtx = document.getElementById('ratingChart');
    if (ratingCtx) {
      this.charts.rating = new Chart(ratingCtx, {
        type: 'bar',
        data: {
          labels: ['No Data'],
          datasets: [{
            label: 'Count',
            data: [1],
            backgroundColor: colors.success,
            borderColor: colors.success,
            borderWidth: 0,
          }],
        },
        options: chartConfig,
      });
    }

    // Priority Chart (Pie)
    const priorityCtx = document.getElementById('priorityChart');
    if (priorityCtx) {
      this.charts.priority = new Chart(priorityCtx, {
        type: 'pie',
        data: {
          labels: ['No Data'],
          datasets: [{
            data: [1],
            backgroundColor: [colors.warning],
            borderColor: [colors.primary],
            borderWidth: 2,
          }],
        },
        options: { ...chartConfig, plugins: { ...chartConfig.plugins, legend: { position: 'bottom' } } },
      });
    }

    // Email Source Chart (Bar)
    const emailCtx = document.getElementById('emailSourceChart');
    if (emailCtx) {
      this.charts.emailSource = new Chart(emailCtx, {
        type: 'bar',
        data: {
          labels: ['Website', 'Facebook', 'Maps'],
          datasets: [{
            label: 'Emails Found',
            data: [0, 0, 0],
            backgroundColor: [colors.info, colors.error, colors.primary],
            borderWidth: 0,
          }],
        },
        options: chartConfig,
      });
    }
  },

  handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        let data = [];
        const fileName = file.name.toLowerCase();

        if (fileName.endsWith('.csv')) {
          data = this.parseCSV(e.target.result);
        } else if (fileName.endsWith('.xlsx') || fileName.endsWith('.xls')) {
          data = this.parseExcel(file);
        }

        if (data && data.length > 0) {
          this.analyticsData = data;
          this.updateCharts();
          Utils.showToast(`✓ Loaded ${data.length} records successfully!`, 'success', 3000);
        } else {
          Utils.showToast('No valid data found in file', 'error', 3000);
        }
      } catch (err) {
        Utils.showToast(`Error: ${err.message}`, 'error', 4000);
      }
    };

    if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
      const arrayReader = new FileReader();
      arrayReader.onload = (e) => {
        try {
          const data = this.parseExcel(e);
          if (data && data.length > 0) {
            this.analyticsData = data;
            this.updateCharts();
            Utils.showToast(`✓ Loaded ${data.length} records successfully!`, 'success', 3000);
          }
        } catch (err) {
          Utils.showToast(`Error: ${err.message}`, 'error', 4000);
        }
      };
      arrayReader.readAsArrayBuffer(file);
    } else {
      reader.readAsText(file);
    }
  },

  parseCSV(csvText) {
    try {
      const lines = csvText.split('\n').filter(line => line.trim());
      if (lines.length < 2) return [];

      const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/[^a-z0-9_]/g, '_'));
      const data = [];

      for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',');
        const row = {};
        headers.forEach((header, index) => {
          const value = values[index]?.trim() || '';
          // Sanitize to prevent XSS
          row[header] = value.replace(/<[^>]*>/g, '');
        });
        data.push(row);
      }

      return data;
    } catch (err) {
      console.error('CSV parsing error:', err);
      throw new Error('Failed to parse CSV file');
    }
  },

  parseExcel(arrayBuffer) {
    try {
      const workbook = XLSX.read(arrayBuffer, { type: 'array' });
      const sheetName = workbook.SheetNames[0];
      const worksheet = workbook.Sheets[sheetName];
      const data = XLSX.utils.sheet_to_json(worksheet);
      return data;
    } catch (err) {
      throw new Error('Failed to parse Excel file');
    }
  },

  updateCharts() {
    if (!this.analyticsData || this.analyticsData.length === 0) {
      console.warn('No analytics data available');
      return;
    }

    console.log(`Updating charts with ${this.analyticsData.length} records...`);

    try {
      this.updateCategoryChart();
      this.updateRatingChart();
      this.updatePriorityChart();
      this.updateEmailSourceChart();
      this.updateMetrics();
      console.log('✓ All charts updated successfully');
    } catch (err) {
      console.error('Error updating charts:', err);
      if (Utils && Utils.showToast) {
        Utils.showToast('Error updating charts', 'error', 3000);
      }
    }
  },

  updateCategoryChart() {
    const categoryCount = {};
    this.analyticsData.forEach(row => {
      const category = row.category || row.Category || 'Unknown';
      categoryCount[category] = (categoryCount[category] || 0) + 1;
    });

    const sortedCategories = Object.entries(categoryCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
    
    const labels = sortedCategories.map(([label]) => label);
    const data = sortedCategories.map(([, count]) => count);

    if (this.charts.category && labels.length > 0) {
      this.charts.category.data.labels = labels;
      this.charts.category.data.datasets[0].data = data;
      this.charts.category.data.datasets[0].backgroundColor = this.generateColors(labels.length);
      this.animateChart(this.charts.category);
      console.log(`✓ Category chart updated: ${labels.length} categories`);
    }
  },

  updateRatingChart() {
    const ratingBuckets = { '5★': 0, '4-4.9★': 0, '3-3.9★': 0, '2-2.9★': 0, '1-1.9★': 0 };

    this.analyticsData.forEach(row => {
      const rating = parseFloat(row.rating || row.Rating || 0);
      if (rating >= 4.5) ratingBuckets['5★']++;
      else if (rating >= 3.5) ratingBuckets['4-4.9★']++;
      else if (rating >= 2.5) ratingBuckets['3-3.9★']++;
      else if (rating >= 1.5) ratingBuckets['2-2.9★']++;
      else if (rating > 0) ratingBuckets['1-1.9★']++;
    });

    const labels = Object.keys(ratingBuckets);
    const data = Object.values(ratingBuckets);

    if (this.charts.rating) {
      this.charts.rating.data.labels = labels;
      this.charts.rating.data.datasets[0].data = data;
      this.animateChart(this.charts.rating);
      console.log(`✓ Rating chart updated`);
    }
  },

  updatePriorityChart() {
    const priorityCount = {};
    this.analyticsData.forEach(row => {
      const priority = (row.lead_priority || row.priority || row.Priority || 'Medium').toString().trim();
      priorityCount[priority] = (priorityCount[priority] || 0) + 1;
    });

    const labels = Object.keys(priorityCount);
    const data = labels.map(label => priorityCount[label]);
    const colors = labels.map(label => {
      const l = label.toLowerCase();
      if (l === 'high') return 'rgba(239, 68, 68, 0.8)';
      if (l === 'medium') return 'rgba(245, 158, 11, 0.8)';
      if (l === 'low') return 'rgba(16, 185, 129, 0.8)';
      return 'rgba(59, 130, 246, 0.8)';
    });

    if (this.charts.priority && labels.length > 0) {
      this.charts.priority.data.labels = labels;
      this.charts.priority.data.datasets[0].data = data;
      this.charts.priority.data.datasets[0].backgroundColor = colors;
      this.animateChart(this.charts.priority);
      console.log(`✓ Priority chart updated: ${labels.join(', ')}`);
    }
  },

  updateEmailSourceChart() {
    let websiteEmails = 0;
    let facebookEmails = 0;
    let mapsEmails = 0;

    this.analyticsData.forEach(row => {
      const emails_website = (row.emails_website || row.Emails_Website || '').toString();
      const emails_facebook = (row.emails_facebook || row.Emails_Facebook || '').toString();
      const emails_maps = (row.emails_maps || row.Emails_Maps || '').toString();

      websiteEmails += this.countEmailValues(emails_website);
      facebookEmails += this.countEmailValues(emails_facebook);
      mapsEmails += this.countEmailValues(emails_maps);
    });

    if (this.charts.emailSource) {
      this.charts.emailSource.data.datasets[0].data = [websiteEmails, facebookEmails, mapsEmails];
      this.animateChart(this.charts.emailSource);
      console.log(`✓ Email source chart updated: Website=${websiteEmails}, Facebook=${facebookEmails}, Maps=${mapsEmails}`);
    }
  },

  updateMetrics() {
    const total = this.analyticsData.length;
    const avgRating = (
      this.analyticsData.reduce((sum, row) => sum + parseFloat(row.rating || row.Rating || 0), 0) / total
    ).toFixed(2);

    let emailsFound = 0;
    let highPriority = 0;

    this.analyticsData.forEach(row => {
      const emails = this.countEmailValues(row.final_email || row.Final_Email || row.emails || row.Emails || '');
      emailsFound += emails;
      const priority = (row.lead_priority || row.priority || '').toLowerCase();
      if (priority === 'high') highPriority++;
    });

    this.animateNumber('metric-total', total);
    this.animateNumber('metric-avg-rating', parseFloat(avgRating));
    this.animateNumber('metric-emails', emailsFound);
    this.animateNumber('metric-high-priority', highPriority);
  },

  animateNumber(elementId, targetValue) {
    const element = document.getElementById(elementId);
    if (!element) return;

    let currentValue = 0;
    const increment = targetValue / 30;
    const timer = setInterval(() => {
      currentValue += increment;
      if (currentValue >= targetValue) {
        element.textContent = targetValue;
        clearInterval(timer);
      } else {
        element.textContent = Math.floor(currentValue);
      }
    }, 30);
  },

  animateChart(chart) {
    if (chart && chart.update) {
      chart.update('active');
    }
  },

  generateColors(count) {
    const baseColors = [
      'rgba(59, 130, 246, 0.8)',
      'rgba(16, 185, 129, 0.8)',
      'rgba(245, 158, 11, 0.8)',
      'rgba(239, 68, 68, 0.8)',
      'rgba(6, 182, 212, 0.8)',
      'rgba(168, 85, 247, 0.8)',
      'rgba(236, 72, 153, 0.8)',
      'rgba(34, 197, 94, 0.8)',
    ];
    return Array.from({ length: count }, (_, i) => baseColors[i % baseColors.length]);
  },
};

// Initialize analytics when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    if (window.AnalyticsManager) {
      AnalyticsManager.init();
      console.log('✓ AnalyticsManager initialized');
    }
  });
} else {
  if (window.AnalyticsManager) {
    AnalyticsManager.init();
    console.log('✓ AnalyticsManager initialized');
  }
}

// Make AnalyticsManager globally accessible
window.AnalyticsManager = AnalyticsManager;

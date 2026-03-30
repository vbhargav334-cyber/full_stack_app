// ========================================
// I18N.JS - Internationalization System
// ========================================

const I18N = {
  currentLang: Utils.getLanguage() || 'en',

  translations: {
    en: {
      // App
      appName: 'BusinessIntel',

      // Navigation
      navDashboard: 'Intelligence Hub',
      navQueryBuilder: 'Query Builder',
      navBulkOps: 'Batch Operations',
      navTimeline: 'Automation Timeline',
      navResults: 'Results Explorer',

      // Dashboard
      dashboardTitle: 'Intelligence Hub',
      dashboardDesc: 'Real-time overview of your B2B intelligence operations',
      activeJobs: 'Active Jobs',
      successRate: 'Success Rate',
      dataFound: 'Emails Found',
      processingSpeed: 'Processing Speed',
      recentActivity: 'Recent Activity',

      // Quick Search
      quickSearchTitle: 'Quick Search',
      quickSearchDesc: 'Find business contacts in minutes',
      quickSearchPlaceholder: '⌘ K: Quick search...',
      searchConfig: 'Search Configuration',
      keywordLabel: 'Business Keywords',
      keywordPlaceholder: 'restaurants, dentists, plumbers...',
      locationLabel: 'Target Location',
      locationPlaceholder: 'City, Region, or Country',
      scanDepthLabel: 'Scan Depth (max results)',
      advancedOptions: 'Advanced Options',
      stealthMode: 'Stealth Mode',
      resilienceLevelLabel: 'Resilience Level',
      minDelayLabel: 'Min Delay (s)',
      maxDelayLabel: 'Max Delay (s)',
      competitorRadiusLabel: 'Competitor Radius (km)',
      checkpointLabel: 'Checkpoint Every (rows)',
      dedupeLabel: 'Dedup Results',
      enrichSocialsLabel: 'Scrape Social Links & Emails',
      facebookEmailsLabel: 'Include Facebook Emails',
      websiteMaxPagesLabel: 'Website Pages to Scan',
      initiateScan: 'Initiate Scan',

      // Bulk Operations
      bulkOpsTitle: 'Batch Operations',
      bulkOpsDesc: 'Process CSV or Excel files with multiple search queries',
      bulkUploadLabel: 'Batch Upload',
      bulkFileLabel: 'Upload File',
      bulkFileHelp: 'CSV/Excel columns: keyword/query (required), location (optional), max_results (optional)',
      defaultLocationLabel: 'Default Location',
      defaultLocationPlaceholder: 'Used if not in file',
      defaultMaxResultsLabel: 'Default Scan Depth',
      startBulkJob: 'Start Batch Job',

      // Resume
      smartResumeLabel: 'Smart Resume',
      resumeFileLabel: 'Checkpoint File',
      resumeFileHelp: 'Upload a checkpoint/export file to retry failed records and continue analysis',
      startResumeJob: 'Resume Job',

      // Exports
      exportsLabel: 'Exports',
      downloadCsv: 'CSV',
      downloadXlsx: 'Excel',
      downloadCheckpoint: 'Checkpoint',
      downloadOutreach: 'Outreach',
      downloadCrm: 'CRM',

      // Timeline
      timelineTitle: 'Automation Timeline',
      timelineDesc: 'Schedule recurring intelligence gathering tasks',
      createScheduleLabel: 'Create Schedule',
      scheduleHelp: 'Create recurring single-query jobs (minimum 5 minutes)',
      scheduleNameLabel: 'Schedule Name',
      scheduleNamePlaceholder: 'My Daily Dental Leads',
      intervalLabel: 'Interval (minutes)',
      createSchedule: 'Create Schedule',
      activeSchedulesLabel: 'Active Schedules',
      scheduleCol: 'Schedule',
      keywordCol: 'Keywords',
      locationCol: 'Location',
      intervalCol: 'Interval',
      lastRunCol: 'Last Run',
      runsCol: 'Runs',
      actionsCol: 'Actions',

      // Results
      resultsTitle: 'Results Explorer',
      resultsDesc: 'Browse, filter, and analyze discovered business intelligence',
      filtersLabel: 'Filters',
      priorityLabel: 'Lead Priority',
      minRatingLabel: 'Min Rating',
      searchLabel: 'Search Name/Address',
      searchPlaceholder: 'clinic, area...',
      noWebsiteLabel: 'No Website',
      openNowLabel: 'Open Now',
      changedLabel: 'Changed Since Last Run',
      clearFilters: 'Clear All',
      dataTableLabel: 'Data Results',
      allOption: 'All',
      highOption: 'High',
      mediumOption: 'Medium',
      lowOption: 'Low',

      // Table Columns
      queryCol: '#',
      nameCol: 'Name',
      categoryCol: 'Category',
      ratingCol: 'Rating',
      reviewsCol: 'Reviews',
      leadScoreCol: 'Score',
      priorityCol: 'Priority',
      phoneCol: 'Phone',
      websiteCol: 'Website',
      emailsCol: 'Emails',
      facebookCol: 'Facebook',
      instagramCol: 'Instagram',
      statusCol: 'Status',
      addressCol: 'Address',
      mapsCol: 'Maps',

      // Status & Messages
      noJobStarted: 'No job started. Select an option above to begin.',
      refresh: '⟳',

      // Settings
      settingsTitle: 'Settings',
      appearanceLabel: 'Appearance',
      darkModeLabel: 'Dark Mode',
      lightModeLabel: 'Light Mode',
      languageLabel: 'Language',
    },

    hi: {
      appName: 'BusinessIntel',
      navDashboard: 'इंटेलिजेंस हब',
      navQueryBuilder: 'क्वेरी बिल्डर',
      navBulkOps: 'बल्क ऑपरेशन',
      navTimeline: 'समयरेखा',
      navResults: 'परिणाम',
      dashboardTitle: 'इंटेलिजेंस हब',
      // ... more translations
    },

    es: {
      appName: 'BusinessIntel',
      navDashboard: 'Centro de Inteligencia',
      navQueryBuilder: 'Constructor de Consultas',
      navBulkOps: 'Operaciones Masivas',
      navTimeline: 'Cronograma',
      navResults: 'Resultados',
      // ... more translations
    },

    fr: {
      appName: 'BusinessIntel',
      navDashboard: 'Hub Intelligence',
      navQueryBuilder: 'Générateur de Requêtes',
      navBulkOps: 'Opérations en Masse',
      navTimeline: 'Chronologie',
      navResults: 'Résultats',
      // ... more translations
    },

    zh: {
      appName: 'BusinessIntel',
      navDashboard: '智能中心',
      navQueryBuilder: '查询构建器',
      navBulkOps: '批量操作',
      navTimeline: '时间表',
      navResults: '结果',
      // ... more translations
    },

    vi: {
      appName: 'BusinessIntel',
      navDashboard: 'Trung tâm Thông minh',
      navQueryBuilder: 'Trình xây dựng Truy vấn',
      navBulkOps: 'Hoạt động Hàng loạt',
      navTimeline: 'Dòng thời gian',
      navResults: 'Kết quả',
      // ... more translations
    },
  },

  // Initialize i18n
  init() {
    this.applyTranslations();
    this.setupLanguageMenu();
  },

  // Get translation
  t(key) {
    const keys = key.split('.');
    let value = this.translations[this.currentLang];
    for (const k of keys) {
      value = value?.[k];
    }
    return value || this.translations.en[key] || key;
  },

  // Set language
  setLanguage(lang) {
    if (!this.translations[lang]) lang = 'en';
    this.currentLang = lang;
    Utils.setLanguage(lang);
    this.applyTranslations();
  },

  // Apply all translations to DOM
  applyTranslations() {
    document.documentElement.lang = this.currentLang;

    // Translate all [data-i18n] attributes
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      el.textContent = this.t(key);
    });

    // Translate all [data-i18n-placeholder] attributes
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      const key = el.getAttribute('data-i18n-placeholder');
      el.placeholder = this.t(key);
    });

    // Translate all [data-i18n-title] attributes
    document.querySelectorAll('[data-i18n-title]').forEach((el) => {
      const key = el.getAttribute('data-i18n-title');
      el.title = this.t(key);
    });

    // Update language button
    const langBtn = document.getElementById('language-toggle');
    if (langBtn) {
      langBtn.textContent = this.currentLang.toUpperCase();
    }
  },

  // Setup language menu
  setupLanguageMenu() {
    const langBtn = document.getElementById('language-toggle');
    const langMenu = document.getElementById('language-menu');
    const langOptions = document.querySelectorAll('.lang-option');

    if (!langBtn || !langMenu) return;

    // Toggle menu
    langBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      langMenu.toggleAttribute('hidden');
    });

    // Close menu when clicking outside
    document.addEventListener('click', () => {
      langMenu.setAttribute('hidden', '');
    });

    // Handle language selection
    langOptions.forEach((option) => {
      option.addEventListener('click', () => {
        const lang = option.getAttribute('data-lang');
        this.setLanguage(lang);
        langMenu.setAttribute('hidden', '');
      });
    });
  },
};

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => I18N.init());
} else {
  I18N.init();
}

// Update Utils.t to use I18N
Utils.t = (key) => I18N.t(key);

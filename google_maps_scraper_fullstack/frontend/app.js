// ========================================
// APP STATE & CONFIGURATION
// ========================================

const state = {
  jobId: null,
  pollingId: null,
  rawRows: [],
};

const els = {
  form: document.getElementById("scrape-form"),
  bulkForm: document.getElementById("bulk-form"),
  resumeForm: document.getElementById("resume-form"),
  scheduleForm: document.getElementById("schedule-form"),
  keyword: document.getElementById("keyword"),
  location: document.getElementById("location"),
  maxResults: document.getElementById("max-results"),
  headless: document.getElementById("headless"),
  maxRetries: document.getElementById("max-retries"),
  minDelay: document.getElementById("min-delay"),
  maxDelay: document.getElementById("max-delay"),
  competitorRadiusKm: document.getElementById("competitor-radius-km"),
  checkpointEvery: document.getElementById("checkpoint-every"),
  dedupeEnabled: document.getElementById("dedupe-enabled"),
  enrichSocials: document.getElementById("enrich-socials"),
  facebookEmails: document.getElementById("facebook-emails"),
  websiteMaxPages: document.getElementById("website-max-pages"),
  bulkFile: document.getElementById("bulk-file"),
  resumeFile: document.getElementById("resume-file"),
  defaultLocation: document.getElementById("default-location"),
  defaultMaxResults: document.getElementById("default-max-results"),
  scheduleName: document.getElementById("schedule-name"),
  scheduleKeyword: document.getElementById("schedule-keyword"),
  scheduleLocation: document.getElementById("schedule-location"),
  scheduleInterval: document.getElementById("schedule-interval"),
  refreshSchedulesBtn: document.getElementById("refresh-schedules-btn"),
  filterPriority: document.getElementById("filter-priority"),
  filterMinRating: document.getElementById("filter-min-rating"),
  filterSearch: document.getElementById("filter-search"),
  filterNoWebsite: document.getElementById("filter-no-website"),
  filterOpenNow: document.getElementById("filter-open-now"),
  filterOnlyChanged: document.getElementById("filter-only-changed"),
  clearFiltersBtn: document.getElementById("clear-filters-btn"),
  statusBox: document.getElementById("status-box"),
  progressBar: document.getElementById("progress-bar"),
  refreshBtn: document.getElementById("refresh-btn"),
  downloadCsvBtn: document.getElementById("download-csv-btn"),
  downloadXlsxBtn: document.getElementById("download-xlsx-btn"),
  downloadCheckpointBtn: document.getElementById("download-checkpoint-btn"),
  downloadOutreachBtn: document.getElementById("download-outreach-btn"),
  crmProvider: document.getElementById("crm-provider"),
  downloadCrmBtn: document.getElementById("download-crm-btn"),
  tableBody: document.querySelector("#results-table tbody"),
  schedulesBody: document.querySelector("#schedules-table tbody"),
};

// ========================================
// UTILITY FUNCTIONS (delegated to Utils module)
// ========================================

// Use Utils functions where available, fallback to local implementations
const escapeHtml = Utils ? Utils.escapeHtml : (value) => {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
};

const api = Utils ? Utils.api : async (path, options = {}) => {
  const res = await fetch(path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
};

function setStatus(message, statusClass = "") {
  els.statusBox.className = statusClass;
  els.statusBox.textContent = message;

  // Also show toast notification for important messages
  if (Utils && Utils.showToast) {
    if (statusClass.includes("failed")) {
      Utils.showToast(message, "error", 4000);
    } else if (statusClass.includes("completed")) {
      Utils.showToast(message, "success", 3000);
    } else if (statusClass.includes("running")) {
      Utils.showToast(message, "info", 2000);
    }
  }
}

function setProgress(progress, total) {
  const pct = total > 0 ? Math.min(100, Math.round((progress / total) * 100)) : 0;
  els.progressBar.style.width = `${pct}%`;
}

function enableDownloads(enabled) {
  els.downloadCsvBtn.disabled = !enabled;
  els.downloadXlsxBtn.disabled = !enabled;
  els.downloadCheckpointBtn.disabled = !enabled;
  els.downloadOutreachBtn.disabled = !enabled;
  els.downloadCrmBtn.disabled = !enabled;
}

function renderRows(rows) {
  const html = rows
    .map((r) => {
      const mapsUrl = escapeHtml(r.google_maps_url || "");
      const website = escapeHtml(r.website || "");
      const queryIndex = r.query_index ? escapeHtml(r.query_index) : "";
      const error = escapeHtml(r.error || "");
      const utilityLinks = [
        r.order_links || "",
        r.menu_links || "",
        r.booking_links || "",
      ]
        .filter(Boolean)
        .join(" | ");
      const mapsLink = mapsUrl ? `<a href="${mapsUrl}" target="_blank" rel="noreferrer">Open</a>` : "";
      const websiteLink = website ? `<a href="${website}" target="_blank" rel="noreferrer">Visit</a>` : "";
      return `
        <tr>
          <td>${queryIndex}</td>
          <td>${escapeHtml(r.name)}</td>
          <td>${escapeHtml(r.category)}</td>
          <td>${escapeHtml(r.rating)}</td>
          <td>${escapeHtml(r.review_count)}</td>
          <td>${escapeHtml(r.lead_score)}</td>
          <td>${escapeHtml(r.lead_priority)}</td>
          <td>${escapeHtml(r.lead_reason)}</td>
          <td>${escapeHtml(r.opportunity_score)}</td>
          <td>${escapeHtml(r.opportunity_band)}</td>
          <td>${escapeHtml(r.competitor_rating_gap)}</td>
          <td>${escapeHtml(r.competitor_review_gap)}</td>
          <td>${escapeHtml(r.change_flag)}</td>
          <td>${escapeHtml(r.rating_change)}</td>
          <td>${escapeHtml(r.review_count_change)}</td>
          <td>${escapeHtml(r.status_changed)}</td>
          <td>${escapeHtml(r.data_quality_score)}</td>
          <td>${escapeHtml(r.data_quality_band)}</td>
          <td>${escapeHtml(r.data_quality_flags)}</td>
          <td>${escapeHtml(r.area_cluster_id)}</td>
          <td>${escapeHtml(r.area_cluster_size)}</td>
          <td>${escapeHtml(r.area_hotspot)}</td>
          <td>${escapeHtml(r.competitor_count_within_radius)}</td>
          <td>${escapeHtml(r.nearest_competitor_distance_km)}</td>
          <td>${escapeHtml(r.top_competitor_name)}</td>
          <td>${escapeHtml(r.top_competitor_rating)}</td>
          <td>${escapeHtml(r.open_now)}</td>
          <td>${escapeHtml(r.business_status)}</td>
          <td>${escapeHtml(r.price_level)}</td>
          <td>${escapeHtml(r.services)}</td>
          <td>${escapeHtml(r.amenities)}</td>
          <td>${escapeHtml(r.latest_review_hint)}</td>
          <td>${escapeHtml(r.place_id)}</td>
          <td>${escapeHtml(r.feature_id)}</td>
          <td>${escapeHtml(r.phone)}</td>
          <td>${websiteLink}</td>
          <td>${escapeHtml(r.delivery_partners)}</td>
          <td>${escapeHtml(utilityLinks)}</td>
          <td>${escapeHtml(r.final_email || r.emails)}</td>
          <td>${escapeHtml(r.email_sources)}</td>
          <td>${escapeHtml(r.emails_maps)}</td>
          <td>${escapeHtml(r.emails_website)}</td>
          <td>${escapeHtml(r.emails_facebook)}</td>
          <td>${escapeHtml(r.facebook_url)}</td>
          <td>${escapeHtml(r.instagram_url)}</td>
          <td>${escapeHtml(r.twitter_url)}</td>
          <td>${escapeHtml(r.linkedin_url)}</td>
          <td>${escapeHtml(r.youtube_url)}</td>
          <td>${escapeHtml(r.tiktok_url)}</td>
          <td>${escapeHtml(r.address)}</td>
          <td>${mapsLink}</td>
          <td>${error}</td>
        </tr>
      `;
    })
    .join("");
  els.tableBody.innerHTML = html;
}

function applyFilters() {
  let rows = [...state.rawRows];
  const priority = String(els.filterPriority.value || "all").toLowerCase();
  const minRating = Number(els.filterMinRating.value || 0);
  const search = String(els.filterSearch.value || "").trim().toLowerCase();
  const noWebsite = Boolean(els.filterNoWebsite.checked);
  const openNowOnly = Boolean(els.filterOpenNow.checked);
  const onlyChanged = Boolean(els.filterOnlyChanged.checked);

  rows = rows.filter((r) => {
    const rowPriority = String(r.lead_priority || "").toLowerCase();
    const rating = Number.parseFloat(String(r.rating || "").replace(",", "")) || 0;
    const name = String(r.name || "").toLowerCase();
    const address = String(r.address || "").toLowerCase();
    const openNow = String(r.open_now || "").toLowerCase();
    const website = String(r.website || "").trim();
    const changeFlag = String(r.change_flag || "").toLowerCase();

    if (priority !== "all" && rowPriority !== priority) return false;
    if (minRating > 0 && rating < minRating) return false;
    if (search && !name.includes(search) && !address.includes(search)) return false;
    if (noWebsite && website) return false;
    if (openNowOnly && !(openNow.includes("open") && !openNow.includes("closed"))) return false;
    if (onlyChanged && !(changeFlag === "yes" || changeFlag === "new")) return false;

    return true;
  });

  renderRows(rows);
  updateResultCount();
  updateFilterStats(rows);
}

function updateFilterStats(filteredRows) {
  const statsEl = document.getElementById("filter-stats");
  if (!statsEl) return;

  const totalRecords = state.rawRows.length;
  const filteredCount = filteredRows.length;
  const percentage = totalRecords > 0 ? ((filteredCount / totalRecords) * 100).toFixed(0) : 0;

  if (filteredCount === 0) {
    statsEl.textContent = "No records match current filters";
  } else if (filteredCount === totalRecords) {
    statsEl.textContent = `Showing all ${totalRecords} records`;
  } else {
    statsEl.textContent = `${filteredCount} of ${totalRecords} records (${percentage}%)`;
  }
}

async function loadResults() {
  if (!state.jobId) {
    state.rawRows = [];
    applyFilters();
    updateResultCount();
    return;
  }
  try {
    const data = await api(`/api/jobs/${state.jobId}/results`);
    state.rawRows = data.results || [];
    applyFilters();
    updateResultCount();
    if (state.rawRows.length > 0) {
      console.log(`✓ Loaded ${state.rawRows.length} results for job ${state.jobId}`);

      // Auto-populate Analytics Dashboard with scraped results
      setTimeout(() => {
        if (window.AnalyticsManager) {
          AnalyticsManager.analyticsData = state.rawRows;
          AnalyticsManager.updateCharts();
          console.log(`✓ Analytics Dashboard updated with ${state.rawRows.length} records`);
          if (Utils && Utils.showToast) {
            Utils.showToast(`📊 Analytics updated: ${state.rawRows.length} records`, "success", 2500);
          }
        }
      }, 500);

      // Log data insights for analysis
      logDataInsights();
    }
  } catch (err) {
    console.error("Failed to load results:", err);
    setStatus(`Failed to load results: ${err.message}`, "status-failed");
  }
}

function updateResultCount() {
  const resultCountEl = document.getElementById("result-count");
  if (resultCountEl) {
    const filteredCount = els.tableBody.querySelectorAll("tr").length;
    resultCountEl.textContent = `(${filteredCount} records)`;
  }
}

// Track job start time for processing speed calculation
const jobStartTimes = {};

function updateDashboardMetrics(jobData) {
  // Update Active Jobs count - show 1 if running, 0 otherwise
  const activeJobsEl = document.getElementById("active-jobs-count");
  const successRateEl = document.getElementById("success-rate-pct");
  const emailsFoundEl = document.getElementById("emails-found-count");
  const processingSpeedEl = document.getElementById("processing-speed");

  if (!activeJobsEl || !successRateEl || !emailsFoundEl || !processingSpeedEl) return;

  const isRunning = jobData.status === "running";
  const progress = Number(jobData.progress ?? 0);
  const total = Number(jobData.total ?? 0);

  // Active Jobs: 1 if running, 0 if idle
  const activeJobs = isRunning ? 1 : 0;
  if (activeJobsEl.textContent !== String(activeJobs)) {
    activeJobsEl.textContent = activeJobs;
  }

  // Success Rate: percentage of items processed successfully
  const successRate = total > 0 ? Math.round((progress / total) * 100) : 0;
  const successRateText = `${successRate}%`;
  if (successRateEl.textContent !== successRateText) {
    successRateEl.textContent = successRateText;
  }

  // Emails Found: extract from job data if available, otherwise show progress count
  const emailsFound = jobData.data_summary?.emails_found || progress;
  if (emailsFoundEl.textContent !== String(emailsFound)) {
    emailsFoundEl.textContent = emailsFound;
  }

  // Processing Speed: items per second
  if (isRunning && state.jobId && !jobStartTimes[state.jobId]) {
    jobStartTimes[state.jobId] = Date.now();
  }

  let processingSpeed = "--";
  if (state.jobId && jobStartTimes[state.jobId] && progress > 0) {
    const elapsedSeconds = (Date.now() - jobStartTimes[state.jobId]) / 1000;
    const itemsPerSecond = (progress / elapsedSeconds).toFixed(2);
    processingSpeed = `${itemsPerSecond} /s`;
  }

  if (processingSpeedEl.textContent !== processingSpeed) {
    processingSpeedEl.textContent = processingSpeed;
  }

  if (!isRunning && state.jobId && jobStartTimes[state.jobId]) {
    delete jobStartTimes[state.jobId];
  }
}

async function loadStatus() {
  if (!state.jobId) {
    setStatus("No job started.");
    setProgress(0, 0);
    // Reset dashboard metrics
    const activeJobsEl = document.getElementById("active-jobs-count");
    const successRateEl = document.getElementById("success-rate-pct");
    const emailsFoundEl = document.getElementById("emails-found-count");
    const processingSpeedEl = document.getElementById("processing-speed");
    if (activeJobsEl) activeJobsEl.textContent = "0";
    if (successRateEl) successRateEl.textContent = "0%";
    if (emailsFoundEl) emailsFoundEl.textContent = "0";
    if (processingSpeedEl) processingSpeedEl.textContent = "-- /s";
    return;
  }

  const data = await api(`/api/jobs/${state.jobId}`);
  const status = data.status || "unknown";
  const progress = Number(data.progress ?? 0);
  const total = Number(data.total ?? 0);
  const progressLabel = Number.isInteger(progress) ? String(progress) : progress.toFixed(2);
  const message = data.message || "";
  const mode = data.params?.mode || "single";
  const checkpointText = data.checkpoint_rows
    ? ` | checkpoint ${data.checkpoint_rows}`
    : "";
  const dedupText = data.dedup_removed_count
    ? ` | dedup ${data.dedup_removed_count}`
    : "";

  setProgress(progress, total);
  setStatus(
    `Job ${state.jobId} | ${mode.toUpperCase()} | ${status.toUpperCase()} | ${progressLabel}/${total}${checkpointText}${dedupText} | ${message}`,
    status === "running"
      ? "status-running"
      : status === "completed"
      ? "status-completed"
      : status === "failed"
      ? "status-failed"
      : ""
  );

  // Update dashboard metrics in real-time
  updateDashboardMetrics(data);

  if (status === "completed" || status === "failed") {
    stopPolling();
    await loadResults();
    enableDownloads(status === "completed");
  } else {
    enableDownloads(false);
  }
}

function readSharedSettings() {
  const fastMode = true;
  const wantsEnrichment = Boolean(els.enrichSocials.checked) || Boolean(els.facebookEmails.checked);
  const speedProfile = fastMode
    ? (wantsEnrichment ? "email_fast" : "max_speed")
    : "balanced";

  return {
    headless: Boolean(els.headless.checked),
    max_retries: Number(els.maxRetries.value),
    min_delay: Number(els.minDelay.value),
    max_delay: Number(els.maxDelay.value),
    competitor_radius_km: Number(els.competitorRadiusKm.value),
    checkpoint_every: Number(els.checkpointEvery.value),
    dedupe_enabled: Boolean(els.dedupeEnabled.checked),
    enrich_socials: Boolean(els.enrichSocials.checked),
    enrich_facebook_emails: Boolean(els.facebookEmails.checked),
    website_max_pages: Number(els.websiteMaxPages.value),
    fast_mode: fastMode,
    speed_profile: speedProfile,
  };
}

function startPolling() {
  stopPolling();
  state.pollingId = window.setInterval(() => {
    loadStatus().catch((err) => setStatus(err.message, "status-failed"));
  }, 2000);
}

function stopPolling() {
  if (state.pollingId) {
    clearInterval(state.pollingId);
    state.pollingId = null;
  }
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("Creating job...");
  enableDownloads(false);
  els.tableBody.innerHTML = "";
  state.rawRows = [];
  setProgress(0, 0);

  try {
    const payload = {
      keyword: els.keyword.value.trim(),
      location: els.location.value.trim(),
      max_results: Number(els.maxResults.value),
      ...readSharedSettings(),
    };
    const data = await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.jobId = data.job_id;
    setStatus(`Job ${state.jobId} created`, "status-running");
    await loadStatus();
    startPolling();
  } catch (err) {
    setStatus(err.message, "status-failed");
  }
});

els.bulkForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("Uploading file and creating bulk job...");
  enableDownloads(false);
  els.tableBody.innerHTML = "";
  state.rawRows = [];
  setProgress(0, 0);

  try {
    const file = els.bulkFile.files?.[0];
    if (!file) throw new Error("Please choose a bulk file.");

    const settings = readSharedSettings();
    const formData = new FormData();
    formData.append("file", file);
    formData.append("default_location", els.defaultLocation.value.trim());
    formData.append("default_max_results", String(Number(els.defaultMaxResults.value)));
    formData.append("headless", String(settings.headless));
    formData.append("max_retries", String(settings.max_retries));
    formData.append("min_delay", String(settings.min_delay));
    formData.append("max_delay", String(settings.max_delay));
    formData.append("competitor_radius_km", String(settings.competitor_radius_km));
    formData.append("checkpoint_every", String(settings.checkpoint_every));
    formData.append("dedupe_enabled", String(settings.dedupe_enabled));
    formData.append("enrich_socials", String(settings.enrich_socials));
    formData.append("enrich_facebook_emails", String(settings.enrich_facebook_emails));
    formData.append("website_max_pages", String(settings.website_max_pages));
    formData.append("fast_mode", String(settings.fast_mode));
    formData.append("speed_profile", String(settings.speed_profile));

    const res = await fetch("/api/jobs/bulk-upload", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Request failed: ${res.status}`);
    }
    const data = await res.json();
    state.jobId = data.job_id;
    setStatus(`Bulk job ${state.jobId} created (${data.query_count} queries)`, "status-running");
    await loadStatus();
    startPolling();
  } catch (err) {
    setStatus(err.message, "status-failed");
  }
});

els.resumeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("Uploading checkpoint and creating resume job...");
  enableDownloads(false);
  els.tableBody.innerHTML = "";
  state.rawRows = [];
  setProgress(0, 0);

  try {
    const file = els.resumeFile.files?.[0];
    if (!file) throw new Error("Please choose a checkpoint file.");

    const settings = readSharedSettings();
    const formData = new FormData();
    formData.append("file", file);
    formData.append("headless", String(settings.headless));
    formData.append("max_retries", String(settings.max_retries));
    formData.append("min_delay", String(settings.min_delay));
    formData.append("max_delay", String(settings.max_delay));
    formData.append("competitor_radius_km", String(settings.competitor_radius_km));
    formData.append("checkpoint_every", String(settings.checkpoint_every));
    formData.append("dedupe_enabled", String(settings.dedupe_enabled));
    formData.append("enrich_socials", String(settings.enrich_socials));
    formData.append("enrich_facebook_emails", String(settings.enrich_facebook_emails));
    formData.append("website_max_pages", String(settings.website_max_pages));
    formData.append("fast_mode", String(settings.fast_mode));
    formData.append("speed_profile", String(settings.speed_profile));

    const res = await fetch("/api/jobs/resume-upload", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Request failed: ${res.status}`);
    }
    const data = await res.json();
    state.jobId = data.job_id;
    setStatus(`Resume job ${state.jobId} created (${data.resume_row_count} rows)`, "status-running");
    await loadStatus();
    startPolling();
  } catch (err) {
    setStatus(err.message, "status-failed");
  }
});

els.refreshBtn.addEventListener("click", () => {
  loadStatus().catch((err) => setStatus(err.message, "status-failed"));
  loadResults().catch((err) => setStatus(err.message, "status-failed"));
});

els.downloadCsvBtn.addEventListener("click", () => {
  if (!state.jobId) {
    if (Utils?.showToast) Utils.showToast("No job completed. Start a scraping job first.", "error", 3000);
    return;
  }
  console.log(`Downloading CSV for job ${state.jobId}`);
  window.location.href = `/api/jobs/${state.jobId}/export.csv`;
  if (Utils?.showToast) Utils.showToast("CSV download started", "success", 2000);
});

els.downloadXlsxBtn.addEventListener("click", () => {
  if (!state.jobId) {
    if (Utils?.showToast) Utils.showToast("No job completed. Start a scraping job first.", "error", 3000);
    return;
  }
  console.log(`Downloading XLSX for job ${state.jobId}`);
  window.location.href = `/api/jobs/${state.jobId}/export.xlsx`;
  if (Utils?.showToast) Utils.showToast("Excel download started", "success", 2000);
});

els.downloadCheckpointBtn.addEventListener("click", () => {
  if (!state.jobId) {
    if (Utils?.showToast) Utils.showToast("No job completed. Start a scraping job first.", "error", 3000);
    return;
  }
  console.log(`Downloading checkpoint for job ${state.jobId}`);
  window.location.href = `/api/jobs/${state.jobId}/checkpoint.csv`;
  if (Utils?.showToast) Utils.showToast("Checkpoint download started", "success", 2000);
});

els.downloadOutreachBtn.addEventListener("click", () => {
  if (!state.jobId) {
    if (Utils?.showToast) Utils.showToast("No job completed. Start a scraping job first.", "error", 3000);
    return;
  }
  console.log(`Downloading outreach CSV for job ${state.jobId}`);
  window.location.href = `/api/jobs/${state.jobId}/export.outreach.csv`;
  if (Utils?.showToast) Utils.showToast("Outreach export download started", "success", 2000);
});

els.downloadCrmBtn.addEventListener("click", () => {
  if (!state.jobId) {
    if (Utils?.showToast) Utils.showToast("No job completed. Start a scraping job first.", "error", 3000);
    return;
  }
  const provider = String(els.crmProvider.value || "salesforce");
  console.log(`Downloading ${provider} CRM export for job ${state.jobId}`);
  window.location.href = `/api/jobs/${state.jobId}/export.crm.csv?provider=${encodeURIComponent(provider)}`;
  if (Utils?.showToast) Utils.showToast(`${provider} export download started`, "success", 2000);
});

async function loadSchedules() {
  const data = await api("/api/schedules");
  const rows = data.schedules || [];
  const html = rows
    .map((s) => {
      const name = escapeHtml(s.name || s.schedule_id || "");
      const keyword = escapeHtml(s.job_params?.keyword || "");
      const location = escapeHtml(s.job_params?.location || "");
      const interval = escapeHtml(s.interval_minutes || "");
      const lastRun = escapeHtml(s.last_run_at || "");
      const runs = escapeHtml(s.run_count || 0);
      const scheduleId = escapeHtml(s.schedule_id || "");
      return `
        <tr>
          <td>${name}</td>
          <td>${keyword}</td>
          <td>${location}</td>
          <td>${interval}</td>
          <td>${lastRun}</td>
          <td>${runs}</td>
          <td>
            <button data-action="run" data-id="${scheduleId}">Run Now</button>
            <button data-action="delete" data-id="${scheduleId}">Delete</button>
          </td>
        </tr>
      `;
    })
    .join("");
  els.schedulesBody.innerHTML = html;
}

els.scheduleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const settings = readSharedSettings();
    const payload = {
      name: els.scheduleName.value.trim(),
      keyword: els.scheduleKeyword.value.trim(),
      location: els.scheduleLocation.value.trim(),
      interval_minutes: Number(els.scheduleInterval.value || 60),
      max_results: Number(els.maxResults.value || 20),
      headless: settings.headless,
      max_retries: settings.max_retries,
      min_delay: settings.min_delay,
      max_delay: settings.max_delay,
      competitor_radius_km: settings.competitor_radius_km,
      checkpoint_every: settings.checkpoint_every,
      dedupe_enabled: settings.dedupe_enabled,
      enrich_socials: settings.enrich_socials,
      enrich_facebook_emails: settings.enrich_facebook_emails,
      website_max_pages: settings.website_max_pages,
      run_now: true,
    };
    await api("/api/schedules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await loadSchedules();
  } catch (err) {
    setStatus(err.message, "status-failed");
  }
});

els.refreshSchedulesBtn.addEventListener("click", () => {
  loadSchedules().catch((err) => setStatus(err.message, "status-failed"));
});

els.schedulesBody.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const action = target.getAttribute("data-action");
  const scheduleId = target.getAttribute("data-id");
  if (!action || !scheduleId) return;

  try {
    if (action === "run") {
      await api(`/api/schedules/${scheduleId}/run-now`, { method: "POST" });
    } else if (action === "delete") {
      await api(`/api/schedules/${scheduleId}`, { method: "DELETE" });
    }
    await loadSchedules();
  } catch (err) {
    setStatus(err.message, "status-failed");
  }
});

function clearFilters() {
  els.filterPriority.value = "all";
  els.filterMinRating.value = "";
  els.filterSearch.value = "";
  els.filterNoWebsite.checked = false;
  els.filterOpenNow.checked = false;
  els.filterOnlyChanged.checked = false;
  applyFilters();
}

els.clearFiltersBtn.addEventListener("click", clearFilters);
[
  els.filterPriority,
  els.filterMinRating,
  els.filterSearch,
  els.filterNoWebsite,
  els.filterOpenNow,
  els.filterOnlyChanged,
].forEach((el) => {
  el.addEventListener("input", applyFilters);
  el.addEventListener("change", applyFilters);
});

loadStatus().catch((err) => setStatus(err.message, "status-failed"));
loadSchedules().catch((err) => setStatus(err.message, "status-failed"));

// ========================================
// KEYBOARD SHORTCUTS & ADVANCED FEATURES
// ========================================

// Keyboard shortcuts handling
document.addEventListener("keydown", (event) => {
  // Ctrl/Cmd + K: Focus quick search
  if ((event.ctrlKey || event.metaKey) && event.key === "k") {
    event.preventDefault();
    const headerSearch = document.querySelector(".search-input");
    if (headerSearch) {
      headerSearch.focus();
      Utils?.showToast("Quick search activated", "info", 1500);
    }
  }

  // Ctrl/Cmd + F: Focus filters
  if ((event.ctrlKey || event.metaKey) && event.key === "f") {
    event.preventDefault();
    const filterSearch = document.getElementById("filter-search");
    if (filterSearch) {
      filterSearch.focus();
      Utils?.showToast("Filters activated", "info", 1500);
    }
  }

  // Ctrl/Cmd + E: Export current results
  if ((event.ctrlKey || event.metaKey) && event.key === "e") {
    event.preventDefault();
    if (state.jobId && !els.downloadCsvBtn.disabled) {
      els.downloadCsvBtn.click();
    } else {
      Utils?.showToast("No results to export. Run a scrape job first.", "warning", 2000);
    }
  }

  // Esc: Clear active filters
  if (event.key === "Escape") {
    if (document.activeElement === els.filterSearch) {
      clearFilters();
      Utils?.showToast("Filters cleared", "info", 1500);
    }
  }

  // Ctrl/Cmd + N: New search
  if ((event.ctrlKey || event.metaKey) && event.key === "n") {
    event.preventDefault();
    els.keyword.focus();
    Utils?.showToast("Quick search form focused", "info", 1500);
  }
});

// Data insights function - analyzes scraped data for patterns
function generateDataInsights() {
  if (state.rawRows.length === 0) return null;

  const insights = {
    totalRecords: state.rawRows.length,
    averageRating: (
      state.rawRows.reduce((sum, r) => sum + (parseFloat(r.rating) || 0), 0) /
      state.rawRows.length
    ).toFixed(2),
    highPriorityCount: state.rawRows.filter(
      (r) => String(r.lead_priority || "").toLowerCase() === "high"
    ).length,
    websiteCount: state.rawRows.filter((r) => r.website && r.website.trim()).length,
    emailCount: state.rawRows.filter((r) => r.emails && r.emails.trim()).length,
    openNowCount: state.rawRows.filter(
      (r) => String(r.open_now || "").toLowerCase().includes("open")
    ).length,
    categoryDistribution: {},
    ratingDistribution: { "5★": 0, "4-4.9★": 0, "3-3.9★": 0, "2-2.9★": 0, "1-1.9★": 0 },
  };

  // Analyze categories
  state.rawRows.forEach((row) => {
    const category = row.category || "Unknown";
    insights.categoryDistribution[category] = (insights.categoryDistribution[category] || 0) + 1;

    // Analyze rating distribution
    const rating = parseFloat(row.rating) || 0;
    if (rating >= 4.5) insights.ratingDistribution["5★"]++;
    else if (rating >= 3.5) insights.ratingDistribution["4-4.9★"]++;
    else if (rating >= 2.5) insights.ratingDistribution["3-3.9★"]++;
    else if (rating >= 1.5) insights.ratingDistribution["2-2.9★"]++;
    else insights.ratingDistribution["1-1.9★"]++;
  });

  return insights;
}

// Log insights when results are loaded
function logDataInsights() {
  const insights = generateDataInsights();
  if (insights) {
    console.group("📊 Data Insights");
    console.log(`Total Records: ${insights.totalRecords}`);
    console.log(`Average Rating: ${insights.averageRating}⭐`);
    console.log(`High Priority Leads: ${insights.highPriorityCount}`);
    console.log(`Records with Website: ${insights.websiteCount}`);
    console.log(`Records with Email: ${insights.emailCount}`);
    console.log(`Open Now: ${insights.openNowCount}`);
    console.log("Category Distribution:", insights.categoryDistribution);
    console.log("Rating Distribution:", insights.ratingDistribution);
    console.groupEnd();
  }
}

// ========================================
// APPLICATION INITIALIZATION
// ========================================

// Initialize and load data
// Modules are auto-initialized on page load
if (window.ThemeManager) {
  // Theme manager initialized, dark mode is ready
}

if (window.I18N) {
  // I18N initialized, translations are available
}

if (window.DraggableManager) {
  // Draggable panels system initialized
}

// Log initialization status
if (console && console.log) {
  console.log('✓ BusinessIntel initialized with premium UI modules:', {
    utils: !!window.Utils,
    themeManager: !!window.ThemeManager,
    i18n: !!window.I18N,
    draggableManager: !!window.DraggableManager,
  });
}

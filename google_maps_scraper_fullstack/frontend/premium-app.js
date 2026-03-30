// ========================================
// TITANFLOW AI - APP LOGIC
// ========================================

const AppState = {
  jobId: null,
  pollingInterval: null,
  isScraping: false,
  lastMessage: "",
  lastConsoleMessageKey: "",
  lastConsoleMessageAt: 0,
  presetsById: new Map(),
  zipPacksById: new Map(),
  categorySubtypeSelections: new Map(),
};

const MAX_ZIP_LOCATIONS = 500;
const MAX_AREA_SUGGESTIONS = 120;

const BUSINESS_CATEGORIES = [
  "Accountant",
  "Accounting Firm",
  "Acupuncture Clinic",
  "Advertising Agency",
  "Air Conditioning Contractor",
  "Allergy Specialist",
  "Animal Hospital",
  "Apartment Complex",
  "Architect",
  "Art Gallery",
  "Asian Restaurant",
  "Attorney",
  "Auto Body Shop",
  "Auto Detailing Service",
  "Auto Glass Shop",
  "Auto Parts Store",
  "Auto Repair Shop",
  "Bakery",
  "Bank",
  "Bar",
  "Barber Shop",
  "Beauty Salon",
  "Bed and Breakfast",
  "Bike Repair Shop",
  "Bookstore",
  "Boutique",
  "Bridal Shop",
  "Business Consultant",
  "Cafe",
  "Campground",
  "Car Dealer",
  "Car Rental Agency",
  "Car Wash",
  "Cardiologist",
  "Catering Service",
  "Cell Phone Store",
  "Chiropractor",
  "Cleaning Service",
  "Clothing Store",
  "Cocktail Bar",
  "Coffee Shop",
  "Commercial Cleaning Service",
  "Computer Repair Service",
  "Construction Company",
  "Cosmetic Dentist",
  "Coworking Space",
  "Credit Union",
  "Dance School",
  "Day Care Center",
  "Dental Clinic",
  "Dentist",
  "Dermatologist",
  "Digital Marketing Agency",
  "Doctor",
  "Dog Day Care Center",
  "Dog Groomer",
  "Drug Store",
  "Dry Cleaner",
  "E-commerce Service",
  "Education Center",
  "Electrician",
  "Emergency Dentist",
  "Employment Agency",
  "Endodontist",
  "Engineering Consultant",
  "Event Planner",
  "Eyebrow Bar",
  "Family Practice Physician",
  "Fast Food Restaurant",
  "Financial Advisor",
  "Fire Protection Service",
  "Fitness Center",
  "Flooring Contractor",
  "Florist",
  "Food Delivery Service",
  "Foundation Contractor",
  "Funeral Home",
  "Furniture Store",
  "Garage Door Supplier",
  "Garden Center",
  "General Contractor",
  "Gift Shop",
  "Golf Course",
  "Graphic Designer",
  "Grocery Store",
  "Hair Salon",
  "Handyman",
  "Hardware Store",
  "Health Consultant",
  "Hearing Aid Store",
  "Home Builder",
  "Home Health Care Service",
  "Home Inspector",
  "Home Theater Store",
  "Hookah Bar",
  "Hospital",
  "Hotel",
  "HVAC Contractor",
  "Immigration Attorney",
  "Insurance Agency",
  "Interior Designer",
  "Italian Restaurant",
  "IT Support Service",
  "Janitorial Service",
  "Jewelry Store",
  "Juice Shop",
  "Kitchen Remodeler",
  "Landscaper",
  "Laser Hair Removal Service",
  "Laundry Service",
  "Law Firm",
  "Learning Center",
  "Limo Service",
  "Locksmith",
  "Lounge",
  "Mailing Service",
  "Marketing Agency",
  "Massage Spa",
  "Mechanic",
  "Medical Center",
  "Mental Health Clinic",
  "Mexican Restaurant",
  "Mortgage Broker",
  "Moving Company",
  "Nail Salon",
  "Neurologist",
  "Night Club",
  "Notary Public",
  "Nutritionist",
  "Obstetrician-Gynecologist",
  "Office Supply Store",
  "Oncologist",
  "Optical Store",
  "Orthodontist",
  "Orthopedic Surgeon",
  "Pain Management Physician",
  "Paint Store",
  "Painter",
  "Park",
  "Pediatric Dentist",
  "Pediatrician",
  "Personal Injury Attorney",
  "Personal Trainer",
  "Pest Control Service",
  "Pet Store",
  "Pharmacy",
  "Physical Therapist",
  "Physiotherapist",
  "Pizza Restaurant",
  "Plastic Surgeon",
  "Plumber",
  "Podiatrist",
  "Pool Cleaning Service",
  "Pool Contractor",
  "Primary Care Physician",
  "Property Management Company",
  "Psychiatrist",
  "Psychologist",
  "Public Relations Firm",
  "Real Estate Agency",
  "Real Estate Agent",
  "Record Store",
  "Recycling Center",
  "Refrigerator Repair Service",
  "Rehabilitation Center",
  "Religious Organization",
  "Remodeler",
  "Restaurant",
  "Roofing Contractor",
  "Sandwich Shop",
  "School",
  "Seafood Restaurant",
  "Security Guard Service",
  "Security System Supplier",
  "Senior Care Service",
  "Shoe Store",
  "Shopping Mall",
  "Skincare Clinic",
  "Smoke Shop",
  "Solar Energy Company",
  "Spa",
  "Sports Bar",
  "Sports Club",
  "Storage Facility",
  "Sushi Restaurant",
  "Swimming Pool Contractor",
  "Tattoo Shop",
  "Tax Consultant",
  "Tax Preparation Service",
  "Tech Support Service",
  "Telecommunications Service",
  "Thai Restaurant",
  "Tire Shop",
  "Tour Agency",
  "Towing Service",
  "Travel Agency",
  "Tree Service",
  "Truck Repair Shop",
  "Tutoring Service",
  "Urgent Care Center",
  "Urologist",
  "Vacation Rental Service",
  "Vape Shop",
  "Veterinarian",
  "Video Production Service",
  "Warehouse",
  "Water Damage Restoration Service",
  "Web Design Company",
  "Wedding Photographer",
  "Weight Loss Service",
  "Window Cleaning Service",
  "Window Installation Service",
  "Wine Store",
  "Yoga Studio",
];

const CATEGORY_OPTIONS = Array.from(
  new Set(BUSINESS_CATEGORIES.map((item) => String(item || "").trim()).filter(Boolean)),
).sort((a, b) => a.localeCompare(b));

const RESTAURANT_CATEGORY_PACK = [
  "Restaurant",
  ...Array.from(
    new Set([
      "Afghani Restaurant",
      "African Restaurant",
      "American Restaurant",
      "Andhra Restaurant",
      "Arab Restaurant",
      "Asian Fusion Restaurant",
      "Awadhi Restaurant",
      "Bar & Grill",
      "Barbecue Restaurant",
      "Bengali Restaurant",
      "Biryani Restaurant",
      "Bistro",
      "Brazilian Restaurant",
      "Breakfast Restaurant",
      "Brunch Restaurant",
      "Buffet Restaurant",
      "Burger Restaurant",
      "Cafe",
      "Cajun Restaurant",
      "Caribbean Restaurant",
      "Chicken Restaurant",
      "Chinese Restaurant",
      "Continental Restaurant",
      "Cuban Restaurant",
      "Deli",
      "Dessert Restaurant",
      "Diner",
      "Ethiopian Restaurant",
      "Family Restaurant",
      "Fast Food Restaurant",
      "Fine Dining Restaurant",
      "French Restaurant",
      "Fusion Restaurant",
      "German Restaurant",
      "Goan Restaurant",
      "Greek Restaurant",
      "Grill",
      "Gujarati Restaurant",
      "Halal Restaurant",
      "Hamburger Restaurant",
      "Healthy Restaurant",
      "Hot Pot Restaurant",
      "Hot Dog Restaurant",
      "Hyderabadi Restaurant",
      "Indian Restaurant",
      "Indonesian Restaurant",
      "Irish Restaurant",
      "Italian Restaurant",
      "Japanese Restaurant",
      "Kebab Shop",
      "Kerala Restaurant",
      "Korean Restaurant",
      "Lebanese Restaurant",
      "Mediterranean Restaurant",
      "Mexican Restaurant",
      "Middle Eastern Restaurant",
      "Mughlai Restaurant",
      "Nepalese Restaurant",
      "North Indian Restaurant",
      "Noodle Shop",
      "Pakistani Restaurant",
      "Persian Restaurant",
      "Pizza Restaurant",
      "Punjabi Restaurant",
      "Ramen Restaurant",
      "Salad Shop",
      "Sandwich Shop",
      "Seafood Restaurant",
      "Shawarma Restaurant",
      "South Indian Restaurant",
      "Spanish Restaurant",
      "Steakhouse",
      "Sushi Restaurant",
      "Taco Restaurant",
      "Tapas Restaurant",
      "Tea House",
      "Tex-Mex Restaurant",
      "Thai Restaurant",
      "Turkish Restaurant",
      "Udupi Restaurant",
      "Vegan Restaurant",
      "Vegetarian Restaurant",
      "Vietnamese Restaurant",
      "Wings Restaurant",
      "Wrap Restaurant",
    ]),
  ).sort((a, b) => a.localeCompare(b)),
];

const CATEGORY_SUBTYPE_OPTIONS = {
  Restaurant: RESTAURANT_CATEGORY_PACK.filter((item) => String(item || "").trim().toLowerCase() !== "restaurant"),
};

const LocationPickerState = {
  apiReady: true,
  warnedUnavailable: false,
  countries: [],
  statesByCountry: new Map(),
  citiesByCountryState: new Map(),
  zipsByCountryStateCity: new Map(),
  areaZipsByCountryStateQuery: new Map(),
  currentCityZipOptions: [],
  selectedZipLocations: [],
  areaSuggestTimer: null,
  retryTimer: null,
  retryAttempts: 0,
  maxRetryAttempts: 8,
};

function populateCategoryOptions() {
  const keywordSelect = document.getElementById("keyword");
  if (!keywordSelect || keywordSelect.dataset.loaded === "1") return;
  const options = CATEGORY_OPTIONS.map((category) => ({ value: category, label: category }));
  renderSelectOptions(keywordSelect, "Select Category", options, "value", "label");
  keywordSelect.dataset.loaded = "1";
}

function getCategorySubtypeElements() {
  return {
    group: document.getElementById("category-subtype-group"),
    label: document.getElementById("category-subtype-label"),
    select: document.getElementById("category_subtypes"),
    hint: document.getElementById("category-subtype-hint"),
    selectAllBtn: document.getElementById("category_subtypes_select_all_btn"),
    clearBtn: document.getElementById("category_subtypes_clear_btn"),
  };
}

function getSelectedCategorySubtypes() {
  const { select } = getCategorySubtypeElements();
  if (!select) return [];
  return Array.from(select.selectedOptions || [])
    .map((option) => String(option.value || "").trim())
    .filter(Boolean);
}

function updateCategorySubtypeHint(parentCategory = "") {
  const { hint } = getCategorySubtypeElements();
  if (!hint) return;
  const selected = getSelectedCategorySubtypes();
  const parent = String(parentCategory || "").trim();
  if (!parent) {
    hint.textContent = "Select one type for a single scrape, or multiple types for automatic bulk category scraping.";
    return;
  }
  if (selected.length === 0) {
    hint.textContent = `Choose ${parent.toLowerCase()} types below. One type = single scrape, multiple types = bulk category scrape.`;
    return;
  }
  if (selected.length === 1) {
    hint.textContent = `Selected 1 ${parent.toLowerCase()} type. This will run as a single keyword search.`;
    return;
  }
  hint.textContent = `Selected ${selected.length} ${parent.toLowerCase()} types. This will automatically run as bulk keyword/category scraping.`;
}

function renderCategorySubtypeOptions(parentCategory, explicitSelection = null) {
  const { group, label, select } = getCategorySubtypeElements();
  if (!group || !select || !label) return;
  const category = String(parentCategory || "").trim();
  const options = Array.isArray(CATEGORY_SUBTYPE_OPTIONS[category]) ? CATEGORY_SUBTYPE_OPTIONS[category] : [];
  if (!category || options.length === 0) {
    group.style.display = "none";
    select.innerHTML = "";
    updateCategorySubtypeHint("");
    return;
  }

  const preselected = Array.isArray(explicitSelection)
    ? explicitSelection
    : (AppState.categorySubtypeSelections.get(category) || []);
  const selectedSet = new Set(preselected.map((item) => String(item || "").trim()).filter(Boolean));

  label.textContent = `${category} Types`;
  select.innerHTML = "";
  options.forEach((item) => {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = item;
    option.selected = selectedSet.has(item);
    select.appendChild(option);
  });
  group.style.display = "block";
  updateCategorySubtypeHint(category);
}

function syncCategorySubtypeUI(explicitSelection = null) {
  const mode = String(document.getElementById("search_input_mode")?.value || "guided").trim().toLowerCase();
  const guidedCategory = String(document.getElementById("keyword")?.value || "").trim();
  const { group } = getCategorySubtypeElements();

  if (mode === "manual") {
    if (group) {
      group.style.display = "none";
    }
    return;
  }

  renderCategorySubtypeOptions(guidedCategory, explicitSelection);
}

function handleGuidedCategoryChange() {
  const currentCategory = String(document.getElementById("keyword")?.value || "").trim();
  if (!currentCategory) {
    syncCategorySubtypeUI([]);
    syncZipSweepUI();
    return;
  }
  syncCategorySubtypeUI();
  syncZipSweepUI();
}

function bindCategorySubtypeEvents() {
  const keywordSelect = document.getElementById("keyword");
  const { select, selectAllBtn, clearBtn } = getCategorySubtypeElements();

  if (keywordSelect) {
    keywordSelect.addEventListener("change", handleGuidedCategoryChange);
  }
  if (select) {
    select.addEventListener("change", () => {
      const category = String(document.getElementById("keyword")?.value || "").trim();
      AppState.categorySubtypeSelections.set(category, getSelectedCategorySubtypes());
      updateCategorySubtypeHint(category);
      syncZipSweepUI();
    });
  }
  if (selectAllBtn) {
    selectAllBtn.addEventListener("click", () => {
      const category = String(document.getElementById("keyword")?.value || "").trim();
      const options = Array.isArray(CATEGORY_SUBTYPE_OPTIONS[category]) ? CATEGORY_SUBTYPE_OPTIONS[category] : [];
      if (!select || options.length === 0) return;
      Array.from(select.options).forEach((option) => {
        option.selected = true;
      });
      AppState.categorySubtypeSelections.set(category, options.slice());
      updateCategorySubtypeHint(category);
      syncZipSweepUI();
      logToConsole(`Selected all ${category.toLowerCase()} types.`, "info");
    });
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      const category = String(document.getElementById("keyword")?.value || "").trim();
      if (!select) return;
      Array.from(select.options).forEach((option) => {
        option.selected = false;
      });
      AppState.categorySubtypeSelections.set(category, []);
      updateCategorySubtypeHint(category);
      syncZipSweepUI();
      logToConsole(`${category || "Category"} subtypes cleared.`, "info");
    });
  }
}

function parseBulkKeywordList(rawText) {
  return Array.from(new Set(
    String(rawText || "")
      .split(/[\n,;|]+/)
      .map((item) => item.trim())
      .filter(Boolean),
  ));
}

function getBulkKeywordBuilderElements() {
  return {
    textarea: document.getElementById("zip_sweep_keywords"),
    input: document.getElementById("bulk_query_input"),
    addBtn: document.getElementById("add_bulk_query_btn"),
    count: document.getElementById("bulk_query_count"),
    list: document.getElementById("bulk_query_list"),
  };
}

function renderBulkKeywordBuilder() {
  const { textarea, count, list } = getBulkKeywordBuilderElements();
  if (!textarea) return;
  const values = parseBulkKeywordList(textarea.value);

  if (count) {
    count.textContent = values.length > 0
      ? `${values.length} bulk quer${values.length === 1 ? "y" : "ies"} ready. They will run one after another in Google Maps.`
      : "No bulk queries added yet. Added queries will run one after another in Google Maps.";
  }

  if (!list) return;
  if (values.length === 0) {
    list.innerHTML = '<span style="color: var(--text-muted); font-size: 0.9rem;">Added queries will appear here.</span>';
    return;
  }

  list.innerHTML = values.map((value, index) => `
    <button
      type="button"
      class="btn-secondary"
      data-bulk-query="${escapeAttr(value)}"
      title="Remove this query"
      style="display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.45rem 0.7rem; border-radius: 999px;"
    >
      <span style="font-size: 0.75rem; opacity: 0.8;">${index + 1}.</span>
      <span>${escapeHtml(value)}</span>
      <span style="font-size: 0.8rem; opacity: 0.8;">x</span>
    </button>
  `).join("");

  Array.from(list.querySelectorAll("[data-bulk-query]")).forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = String(btn.getAttribute("data-bulk-query") || "").trim();
      removeBulkKeywordValue(target);
    });
  });
}

function writeBulkKeywordList(values, { append = false, enableMode = true } = {}) {
  const textarea = document.getElementById("zip_sweep_keywords");
  if (!textarea) return;
  const nextValues = append
    ? Array.from(new Set([...parseBulkKeywordList(textarea.value), ...parseBulkKeywordList(values.join("\n"))]))
    : Array.from(new Set(values.map((item) => String(item || "").trim()).filter(Boolean)));
  textarea.value = nextValues.join(", ");
  if (enableMode) {
    const toggle = document.getElementById("zip_sweep_enabled");
    if (toggle) toggle.checked = nextValues.length > 0;
  }
  renderBulkKeywordBuilder();
  syncZipSweepUI();
}

function appendBulkKeywordFromInput() {
  const { input } = getBulkKeywordBuilderElements();
  const typedValues = parseBulkKeywordList(String(input?.value || "").trim());
  const selectedSubtypes = getSelectedCategorySubtypes();
  const selectedCategory = String(document.getElementById("keyword")?.value || "").trim();
  const manualQuery = String(document.getElementById("manual_query")?.value || "").trim();

  let valuesToAppend = typedValues;
  let addedFromSelection = false;

  if (valuesToAppend.length === 0 && selectedSubtypes.length > 0) {
    valuesToAppend = selectedSubtypes;
    addedFromSelection = true;
  } else if (valuesToAppend.length === 0 && selectedCategory) {
    valuesToAppend = [selectedCategory];
    addedFromSelection = true;
  } else if (valuesToAppend.length === 0 && manualQuery) {
    valuesToAppend = [manualQuery];
  }

  if (valuesToAppend.length === 0) {
    logToConsole("Type a search query, or select a category/type first, then click + Add Query.", "error");
    return;
  }
  writeBulkKeywordList(valuesToAppend, { append: true, enableMode: true });
  if (input) {
    input.value = "";
    input.focus();
  }
  if (addedFromSelection && selectedSubtypes.length > 0) {
    logToConsole(`Added ${selectedSubtypes.length} selected type quer${selectedSubtypes.length === 1 ? "y" : "ies"} from ${selectedCategory}.`, "info");
  } else if (addedFromSelection && selectedCategory) {
    logToConsole(`Added selected category as bulk query: ${selectedCategory}`, "info");
  } else if (valuesToAppend.length === 1) {
    logToConsole(`Added bulk query: ${valuesToAppend[0]}`, "info");
  } else {
    logToConsole(`Added ${valuesToAppend.length} bulk queries.`, "info");
  }
}

function removeBulkKeywordValue(targetValue) {
  const { textarea } = getBulkKeywordBuilderElements();
  if (!textarea) return;
  const target = String(targetValue || "").trim().toLowerCase();
  const nextValues = parseBulkKeywordList(textarea.value).filter((value) => String(value || "").trim().toLowerCase() !== target);
  textarea.value = nextValues.join(", ");
  renderBulkKeywordBuilder();
  syncZipSweepUI();
  logToConsole(`Removed bulk query: ${targetValue}`, "info");
}

function loadRestaurantKeywordPack() {
  const keywordSelect = document.getElementById("keyword");
  if (keywordSelect) {
    keywordSelect.value = "Restaurant";
  }
  AppState.categorySubtypeSelections.set("Restaurant", CATEGORY_SUBTYPE_OPTIONS.Restaurant.slice());
  syncCategorySubtypeUI(CATEGORY_SUBTYPE_OPTIONS.Restaurant.slice());
  writeBulkKeywordList(RESTAURANT_CATEGORY_PACK, { append: false, enableMode: true });
  logToConsole(`Restaurant keyword pack loaded (${RESTAURANT_CATEGORY_PACK.length} categories).`, "info");
}

function appendSelectedCategoryToBulkKeywords() {
  const selected = String(document.getElementById("keyword")?.value || "").trim();
  const selectedSubtypes = getSelectedCategorySubtypes();
  const valuesToAppend = selectedSubtypes.length > 0 ? selectedSubtypes : (selected ? [selected] : []);
  if (valuesToAppend.length === 0) {
    logToConsole("Pick a guided category first, then add it to Bulk Keywords.", "error");
    return;
  }
  writeBulkKeywordList(valuesToAppend, { append: true, enableMode: true });
  if (selectedSubtypes.length > 0) {
    logToConsole(`Added ${selectedSubtypes.length} subtype keyword(s) from ${selected}.`, "info");
  } else {
    logToConsole(`Added bulk keyword: ${selected}`, "info");
  }
}

function clearBulkKeywordList() {
  const textarea = document.getElementById("zip_sweep_keywords");
  if (textarea) {
    textarea.value = "";
  }
  renderBulkKeywordBuilder();
  syncZipSweepUI();
  logToConsole("Bulk keyword list cleared.", "info");
}

function bindBulkKeywordButtons() {
  const restaurantPackBtn = document.getElementById("restaurant_keyword_pack_btn");
  const appendSelectedBtn = document.getElementById("append_selected_keyword_btn");
  const clearBulkBtn = document.getElementById("clear_bulk_keywords_btn");
  const { textarea, input, addBtn } = getBulkKeywordBuilderElements();

  if (restaurantPackBtn) {
    restaurantPackBtn.addEventListener("click", loadRestaurantKeywordPack);
  }
  if (appendSelectedBtn) {
    appendSelectedBtn.addEventListener("click", appendSelectedCategoryToBulkKeywords);
  }
  if (clearBulkBtn) {
    clearBulkBtn.addEventListener("click", clearBulkKeywordList);
  }
  if (addBtn) {
    addBtn.addEventListener("click", appendBulkKeywordFromInput);
  }
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.repeat) return;
      event.preventDefault();
      appendBulkKeywordFromInput();
    });
  }
  if (textarea) {
    textarea.addEventListener("input", () => {
      renderBulkKeywordBuilder();
      syncZipSweepUI();
    });
  }
}

function getLocationPickerElements() {
  return {
    countrySelect: document.getElementById("country_select"),
    stateSelect: document.getElementById("state_select"),
    citySelect: document.getElementById("city_select"),
    zipSelect: document.getElementById("zip_select"),
    zipFilterInput: document.getElementById("zip_filter_input"),
    zipAreaSelect: document.getElementById("zip_area_select"),
    zipAreaInput: document.getElementById("zip_area_input"),
    zipAreaSuggestions: document.getElementById("zip_area_suggestions"),
    zipAddAreaBtn: document.getElementById("zip_add_area_btn"),
    zipAddSelectedBtn: document.getElementById("zip_add_selected_btn"),
    zipAddCityBtn: document.getElementById("zip_add_city_btn"),
    zipAddFilteredBtn: document.getElementById("zip_add_filtered_btn"),
    zipClearListBtn: document.getElementById("zip_clear_list_btn"),
    zipSelectedInfo: document.getElementById("zip_selected_info"),
    zipSelectedPreview: document.getElementById("zip_selected_preview"),
    locationInput: document.getElementById("location"),
    locationPreview: document.getElementById("location_preview"),
  };
}

function getCountryNameByCode(code) {
  const target = String(code || "").trim().toUpperCase();
  const found = (LocationPickerState.countries || []).find((c) => String(c.code || "").toUpperCase() === target);
  return found ? found.name : "";
}

function getStateNameByCode(countryCode, stateCode) {
  const country = String(countryCode || "").trim().toUpperCase();
  const code = String(stateCode || "").trim().toUpperCase();
  if (!country || !code) return "";
  const states = LocationPickerState.statesByCountry.get(country) || [];
  const found = states.find((state) => String(state.code || "").trim().toUpperCase() === code);
  return found ? String(found.name || "").trim() : "";
}

function normalizeLocationPhrase(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function buildZipLocationText({ zip = "", area = "", city = "", stateName = "", stateCode = "", countryName = "" }) {
  const parts = [
    normalizeLocationPhrase(zip),
    normalizeLocationPhrase(area),
    normalizeLocationPhrase(city),
    normalizeLocationPhrase(stateName || stateCode),
    normalizeLocationPhrase(countryName),
  ].filter(Boolean);
  return parts.join(" ");
}

function getCurrentZipContext(overrides = {}) {
  const { countrySelect, stateSelect, citySelect } = getLocationPickerElements();
  const countryCode = String(overrides.countryCode || countrySelect?.value || "").trim().toUpperCase();
  const stateCode = String(overrides.stateCode || stateSelect?.value || "").trim().toUpperCase();
  const city = normalizeLocationPhrase(overrides.city || citySelect?.value || "");
  const area = normalizeLocationPhrase(overrides.area || "");
  const countryName = normalizeLocationPhrase(overrides.countryName || getCountryNameByCode(countryCode) || countryCode);
  const stateName = normalizeLocationPhrase(overrides.stateName || getStateNameByCode(countryCode, stateCode) || stateCode);
  return { countryCode, countryName, stateCode, stateName, city, area };
}

function buildLocationFromSelectors() {
  const { countrySelect, stateSelect, citySelect, zipSelect } = getLocationPickerElements();
  const countryCode = String(countrySelect?.value || "").trim().toUpperCase();
  if (!countryCode) return "";
  const stateCode = String(stateSelect?.value || "").trim().toUpperCase();
  const city = normalizeLocationPhrase(citySelect?.value || "");
  const zip = normalizeZipLocation(zipSelect?.value || "");
  const context = getCurrentZipContext({ countryCode, stateCode, city });
  return buildZipLocationText({
    zip,
    city,
    stateName: context.stateName,
    stateCode: context.stateCode,
    countryName: context.countryName,
  });
}

function normalizeZipLocation(rawValue) {
  const value = String(rawValue || "").trim();
  if (!value) return "";
  const cleaned = value.replace(/\s+/g, "").replace(/[^0-9-]/g, "");
  if (!cleaned) return "";
  const digits = cleaned.replace(/-/g, "");
  if (digits.length < 5) return "";
  if (digits.length >= 9) return `${digits.slice(0, 5)}-${digits.slice(5, 9)}`;
  if (digits.length === 6) return digits;
  return digits.slice(0, 5);
}

function normalizeZipEntry(rawEntry, context = {}) {
  let zipCandidate = rawEntry;
  let explicitLocation = "";
  let city = "";
  let area = "";
  let stateName = "";
  let stateCode = "";
  let countryName = "";

  if (rawEntry && typeof rawEntry === "object") {
    zipCandidate = rawEntry.zip || rawEntry.code || rawEntry.value || rawEntry.postal_code || rawEntry.location || "";
    explicitLocation = normalizeLocationPhrase(rawEntry.location || rawEntry.label || "");
    city = normalizeLocationPhrase(rawEntry.city || "");
    area = normalizeLocationPhrase(rawEntry.area || rawEntry.locality || "");
    stateName = normalizeLocationPhrase(rawEntry.state_name || rawEntry.state || "");
    stateCode = normalizeLocationPhrase(rawEntry.state_code || "");
    countryName = normalizeLocationPhrase(rawEntry.country_name || rawEntry.country || "");
  }

  const zip = normalizeZipLocation(zipCandidate);
  if (!zip) return null;

  const mergedContext = getCurrentZipContext(context);
  const finalCity = normalizeLocationPhrase(context.city || city || mergedContext.city || "");
  const finalArea = normalizeLocationPhrase(context.area || area || "");
  const finalStateName = normalizeLocationPhrase(context.stateName || stateName || mergedContext.stateName || "");
  const finalStateCode = normalizeLocationPhrase(context.stateCode || stateCode || mergedContext.stateCode || "");
  const finalCountryName = normalizeLocationPhrase(context.countryName || countryName || mergedContext.countryName || "");

  let location = explicitLocation;
  if (!location) {
    location = buildZipLocationText({
      zip,
      area: finalArea,
      city: finalCity,
      stateName: finalStateName,
      stateCode: finalStateCode,
      countryName: finalCountryName,
    });
  }
  if (!location) location = zip;

  return {
    zip,
    location,
  };
}

function getSelectedZipLocations() {
  if (!Array.isArray(LocationPickerState.selectedZipLocations)) return [];
  return LocationPickerState.selectedZipLocations
    .map((entry) => normalizeZipEntry(entry))
    .filter(Boolean);
}

function renderSelectedZipLocations() {
  const { zipSelectedInfo, zipSelectedPreview } = getLocationPickerElements();
  const selected = getSelectedZipLocations();
  const previewValues = selected.map((entry) => entry.location || entry.zip).filter(Boolean);
  if (zipSelectedPreview) {
    zipSelectedPreview.value = previewValues.join(", ");
  }
  if (zipSelectedInfo) {
    if (selected.length === 0) {
      zipSelectedInfo.textContent = "No ZIPs added yet. Add selected/city ZIPs to run ZIP-wise scraping.";
    } else {
      const sample = previewValues.slice(0, 6).join(", ");
      zipSelectedInfo.textContent = `ZIP list: ${selected.length} selected${sample ? ` (${sample}${selected.length > 6 ? ", ..." : ""})` : ""}`;
    }
  }
  syncZipSweepUI();
}

function filterZipListByInput(zips, rawFilter) {
  const list = Array.isArray(zips) ? zips : [];
  const filterText = String(rawFilter || "").trim();
  if (!filterText) return list;
  const needle = filterText.replace(/[^0-9]/g, "");
  if (!needle) return list;
  return list.filter((zip) => String(zip).replace(/[^0-9]/g, "").includes(needle));
}

function addZipLocations(rawZips, sourceLabel = "ZIP list", context = {}) {
  const inputs = Array.isArray(rawZips) ? rawZips : [rawZips];
  const selected = getSelectedZipLocations();
  const seen = new Map(selected.map((entry, index) => [String(entry.zip || "").toLowerCase(), index]));
  let added = 0;
  let skippedByLimit = false;

  for (const rawInput of inputs) {
    const entry = normalizeZipEntry(rawInput, context);
    if (!entry) continue;
    const key = String(entry.zip || "").toLowerCase();
    const existingIndex = seen.get(key);
    if (typeof existingIndex === "number") {
      const existing = selected[existingIndex];
      const existingLocation = normalizeLocationPhrase(existing?.location || "");
      const nextLocation = normalizeLocationPhrase(entry.location || "");
      if (
        nextLocation
        && (existingLocation === normalizeLocationPhrase(existing?.zip || "") || nextLocation.length > existingLocation.length)
      ) {
        selected[existingIndex] = entry;
      }
      continue;
    }
    if (selected.length >= MAX_ZIP_LOCATIONS) {
      skippedByLimit = true;
      break;
    }
    seen.set(key, selected.length);
    selected.push(entry);
    added += 1;
  }

  LocationPickerState.selectedZipLocations = selected;
  renderSelectedZipLocations();
  syncLocationInputFromSelectors();

  if (added > 0) {
    logToConsole(`${sourceLabel}: added ${added} ZIP${added === 1 ? "" : "s"} (${selected.length} total).`, "success");
  } else {
    logToConsole(`${sourceLabel}: no new ZIPs added.`, "dim");
  }
  if (skippedByLimit) {
    logToConsole(`ZIP list limit reached (${MAX_ZIP_LOCATIONS}).`, "error");
  }
  return added;
}

function clearSelectedZipLocations(silent = false) {
  LocationPickerState.selectedZipLocations = [];
  renderSelectedZipLocations();
  syncLocationInputFromSelectors();
  if (!silent) {
    logToConsole("Cleared ZIP list.", "info");
  }
}

function resolveLocationValue(useZipFallback = true) {
  const selectedZips = getSelectedZipLocations();
  if (useZipFallback && selectedZips.length > 0) {
    return String(selectedZips[0].location || selectedZips[0].zip || "").trim();
  }
  return buildLocationFromSelectors();
}

function syncLocationInputFromSelectors() {
  const { locationInput, locationPreview } = getLocationPickerElements();
  const selected = buildLocationFromSelectors();
  const selectedZips = getSelectedZipLocations();
  const fallbackLocation = selectedZips.length > 0
    ? String(selectedZips[0].location || selectedZips[0].zip || "").trim()
    : selected;
  if (locationInput) {
    locationInput.value = fallbackLocation;
  }
  if (locationPreview) {
    locationPreview.value = selected || fallbackLocation;
  }
  updateZipToolAvailability();
}

function updateZipToolAvailability() {
  const {
    countrySelect,
    stateSelect,
    citySelect,
    zipSelect,
    zipAreaSelect,
    zipAreaInput,
    zipAddAreaBtn,
    zipAddSelectedBtn,
    zipAddCityBtn,
    zipAddFilteredBtn,
  } = getLocationPickerElements();

  const countryCode = String(countrySelect?.value || "").trim().toUpperCase();
  const stateCode = String(stateSelect?.value || "").trim().toUpperCase();
  const city = normalizeLocationPhrase(citySelect?.value || "");
  const selectedZip = normalizeZipLocation(zipSelect?.value || "");
  const selectedArea = normalizeLocationPhrase(zipAreaSelect?.value || "");
  const typedArea = normalizeLocationPhrase(zipAreaInput?.value || "");

  const hasCountryState = Boolean(countryCode && stateCode);
  const hasCity = Boolean(city);
  const hasZip = Boolean(selectedZip);
  const hasAreaLike = Boolean(selectedArea || typedArea || city);

  if (zipAddAreaBtn) {
    zipAddAreaBtn.disabled = !hasCountryState || !hasAreaLike;
    if (!hasCountryState) {
      zipAddAreaBtn.title = "Select country and state first";
    } else if (!hasAreaLike) {
      zipAddAreaBtn.title = "Select area/locality or city first";
    } else {
      zipAddAreaBtn.title = "Add ZIPs for selected area/locality";
    }
  }

  if (zipAddSelectedBtn) {
    zipAddSelectedBtn.disabled = !hasCountryState || !hasZip;
    zipAddSelectedBtn.title = (!hasCountryState || !hasZip)
      ? "Select country/state and ZIP first"
      : "Add currently selected ZIP";
  }

  if (zipAddCityBtn) {
    zipAddCityBtn.disabled = !hasCountryState || !hasCity;
    zipAddCityBtn.title = (!hasCountryState || !hasCity)
      ? "Select country, state, and city first"
      : "Add all ZIPs in selected city";
  }

  if (zipAddFilteredBtn) {
    zipAddFilteredBtn.disabled = !hasCountryState || !hasCity;
    zipAddFilteredBtn.title = (!hasCountryState || !hasCity)
      ? "Select country, state, and city first"
      : "Add ZIPs matching ZIP filter";
  }
}

function renderSelectOptions(selectEl, placeholder, options, valueKey, labelKey) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  const placeholderOption = document.createElement("option");
  placeholderOption.value = "";
  placeholderOption.textContent = placeholder;
  selectEl.appendChild(placeholderOption);
  options.forEach((opt) => {
    const option = document.createElement("option");
    option.value = String(opt[valueKey] || "");
    option.textContent = String(opt[labelKey] || "");
    selectEl.appendChild(option);
  });
}

function setSelectLoading(selectEl, label) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = label;
  selectEl.appendChild(opt);
}

function setLocationPickerDisabled(disabled) {
  const { countrySelect, stateSelect, citySelect, zipSelect } = getLocationPickerElements();
  if (countrySelect) countrySelect.disabled = Boolean(disabled);
  if (stateSelect) stateSelect.disabled = Boolean(disabled);
  if (citySelect) citySelect.disabled = Boolean(disabled);
  if (zipSelect) zipSelect.disabled = Boolean(disabled);
}

function clearLocationRetryTimer() {
  if (LocationPickerState.retryTimer) {
    clearTimeout(LocationPickerState.retryTimer);
    LocationPickerState.retryTimer = null;
  }
}

function scheduleLocationPickerRetry() {
  if (LocationPickerState.apiReady) return;
  if (LocationPickerState.retryTimer) return;
  if (LocationPickerState.retryAttempts >= LocationPickerState.maxRetryAttempts) return;

  LocationPickerState.retryAttempts += 1;
  const delayMs = Math.min(15000, 1500 * LocationPickerState.retryAttempts);

  LocationPickerState.retryTimer = setTimeout(async () => {
    LocationPickerState.retryTimer = null;
    await populateCountryOptions();
  }, delayMs);
}

function handleLocationApiUnavailable(error) {
  if (!LocationPickerState.warnedUnavailable) {
    console.error("Location API unavailable:", error);
    logToConsole("Location picker API unavailable. Retrying...", "error");
    LocationPickerState.warnedUnavailable = true;
  }
  LocationPickerState.apiReady = false;
  setLocationPickerDisabled(true);
  scheduleLocationPickerRetry();
}

async function fetchCountriesFromApi() {
  if (LocationPickerState.countries.length > 0) {
    return LocationPickerState.countries;
  }
  const payload = await requestJson("/api/locations/countries");
  const countries = Array.isArray(payload.countries) ? payload.countries : [];
  LocationPickerState.countries = countries
    .map((c) => ({
      code: String(c.code || "").trim().toUpperCase(),
      name: String(c.name || "").trim(),
    }))
    .filter((c) => c.code && c.name);
  return LocationPickerState.countries;
}

async function fetchStatesFromApi(countryCode) {
  const country = String(countryCode || "").trim().toUpperCase();
  if (!country) return [];
  if (LocationPickerState.statesByCountry.has(country)) {
    return LocationPickerState.statesByCountry.get(country) || [];
  }
  const payload = await requestJson(`/api/locations/states?country=${encodeURIComponent(country)}`);
  const states = Array.isArray(payload.states) ? payload.states : [];
  const normalized = states
    .map((s) => ({
      code: String(s.code || "").trim().toUpperCase(),
      name: String(s.name || "").trim(),
    }))
    .filter((s) => s.code && s.name);
  LocationPickerState.statesByCountry.set(country, normalized);
  return normalized;
}

async function fetchCitiesByState(countryCode, stateCode) {
  const country = String(countryCode || "").trim().toUpperCase();
  const code = String(stateCode || "").trim().toUpperCase();
  if (!country || !code) return [];
  const cacheKey = `${country}|${code}`;
  if (LocationPickerState.citiesByCountryState.has(cacheKey)) {
    return LocationPickerState.citiesByCountryState.get(cacheKey) || [];
  }
  const payload = await requestJson(
    `/api/locations/cities?country=${encodeURIComponent(country)}&state=${encodeURIComponent(code)}&limit=50000`,
  );
  const cities = Array.isArray(payload.cities) ? payload.cities : [];
  const normalized = cities.map((c) => String(c || "").trim()).filter(Boolean);
  LocationPickerState.citiesByCountryState.set(cacheKey, normalized);
  return normalized;
}

async function fetchZipsByStateCity(countryCode, stateCode, cityName) {
  const country = String(countryCode || "").trim().toUpperCase();
  const code = String(stateCode || "").trim().toUpperCase();
  const city = String(cityName || "").trim();
  if (!country || !code || !city) return [];
  const cacheKey = `${country}|${code}|${city.toLowerCase()}`;
  if (LocationPickerState.zipsByCountryStateCity.has(cacheKey)) {
    return LocationPickerState.zipsByCountryStateCity.get(cacheKey) || [];
  }
  const payload = await requestJson(
    `/api/locations/zips?country=${encodeURIComponent(country)}&state=${encodeURIComponent(code)}&city=${encodeURIComponent(city)}&limit=50000`,
  );
  const zips = Array.isArray(payload.zips) ? payload.zips : [];
  const normalized = zips.map((z) => String(z || "").trim()).filter(Boolean);
  LocationPickerState.zipsByCountryStateCity.set(cacheKey, normalized);
  return normalized;
}

async function fetchAreaZipsByState(countryCode, stateCode, areaQuery) {
  const country = String(countryCode || "").trim().toUpperCase();
  const code = String(stateCode || "").trim().toUpperCase();
  const area = String(areaQuery || "").trim();
  if (!country || !code || !area) {
    return { zips: [], matchedCities: [], matchedCityCount: 0 };
  }
  const cacheKey = `${country}|${code}|${area.toLowerCase()}`;
  if (LocationPickerState.areaZipsByCountryStateQuery.has(cacheKey)) {
    return LocationPickerState.areaZipsByCountryStateQuery.get(cacheKey) || { zips: [], matchedCities: [], matchedCityCount: 0 };
  }
  const payload = await requestJson(
    `/api/locations/area-zips?country=${encodeURIComponent(country)}&state=${encodeURIComponent(code)}&area=${encodeURIComponent(area)}&limit=50000`,
  );
  const zips = Array.isArray(payload.zips) ? payload.zips.map((z) => String(z || "").trim()).filter(Boolean) : [];
  const matchedCities = Array.isArray(payload.matched_cities)
    ? payload.matched_cities.map((city) => String(city || "").trim()).filter(Boolean)
    : [];
  const summary = {
    zips,
    matchedCities,
    matchedCityCount: Number(payload.matched_city_count || 0),
  };
  LocationPickerState.areaZipsByCountryStateQuery.set(cacheKey, summary);
  return summary;
}

function renderAreaSuggestions(values) {
  const { zipAreaSuggestions, zipAreaSelect } = getLocationPickerElements();
  if (!zipAreaSuggestions && !zipAreaSelect) return;
  if (zipAreaSuggestions) {
    zipAreaSuggestions.innerHTML = "";
  }
  const seen = new Set();
  const list = Array.isArray(values) ? values : [];
  const selectItems = [];
  for (const rawValue of list) {
    const value = normalizeLocationPhrase(rawValue);
    if (!value) continue;
    const key = value.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    selectItems.push({ value, label: value });
    if (zipAreaSuggestions) {
      const option = document.createElement("option");
      option.value = value;
      zipAreaSuggestions.appendChild(option);
    }
    if (seen.size >= MAX_AREA_SUGGESTIONS) break;
  }
  if (zipAreaSelect) {
    renderSelectOptions(zipAreaSelect, "Select Area / Locality", selectItems, "value", "label");
  }
  updateZipToolAvailability();
}

function clearAreaSuggestions() {
  renderAreaSuggestions([]);
}

async function refreshAreaSuggestions(filterText = "") {
  const { countrySelect, stateSelect } = getLocationPickerElements();
  const countryCode = String(countrySelect?.value || "").trim().toUpperCase();
  const stateCode = String(stateSelect?.value || "").trim().toUpperCase();
  if (!countryCode || !stateCode) {
    clearAreaSuggestions();
    return;
  }

  const needle = normalizeLocationPhrase(filterText).toLowerCase();
  const cities = await fetchCitiesByState(countryCode, stateCode);
  if (!Array.isArray(cities) || cities.length === 0) {
    clearAreaSuggestions();
    return;
  }

  const matched = [];
  for (const city of cities) {
    const name = normalizeLocationPhrase(city);
    if (!name) continue;
    if (needle && !name.toLowerCase().includes(needle)) continue;
    matched.push(name);
    if (matched.length >= MAX_AREA_SUGGESTIONS) break;
  }
  renderAreaSuggestions(matched);
}

async function populateCountryOptions() {
  const { countrySelect, stateSelect, citySelect, zipSelect } = getLocationPickerElements();
  if (!countrySelect || !stateSelect || !citySelect || !zipSelect) return false;

  setSelectLoading(countrySelect, "Loading countries...");
  setSelectLoading(stateSelect, "Select State");
  setSelectLoading(citySelect, "Select City");
  setSelectLoading(zipSelect, "Select ZIP");

  try {
    const countries = await fetchCountriesFromApi();
    const options = countries.map((c) => ({
      value: c.code,
      label: `${c.name} (${c.code})`,
    }));
    renderSelectOptions(countrySelect, "Select Country", options, "value", "label");
    if (!countrySelect.value && options.some((opt) => opt.value === "US")) {
      countrySelect.value = "US";
    }
    await populateStateOptions(countrySelect.value);
    clearLocationRetryTimer();
    if (!LocationPickerState.apiReady && LocationPickerState.warnedUnavailable) {
      logToConsole("Location picker reconnected.", "success");
    }
    LocationPickerState.apiReady = true;
    LocationPickerState.warnedUnavailable = false;
    LocationPickerState.retryAttempts = 0;
    setLocationPickerDisabled(false);
    syncLocationInputFromSelectors();
    return true;
  } catch (err) {
    handleLocationApiUnavailable(err);
    setSelectLoading(countrySelect, "Location API offline");
    setSelectLoading(stateSelect, "Location API offline");
    setSelectLoading(citySelect, "Location API offline");
    setSelectLoading(zipSelect, "Location API offline");
    return false;
  }
}

async function populateStateOptions(countryCode) {
  const { stateSelect, citySelect, zipSelect } = getLocationPickerElements();
  if (!stateSelect || !citySelect || !zipSelect) return false;
  const country = String(countryCode || "").trim().toUpperCase();

  if (!country) {
    renderSelectOptions(stateSelect, "Select State", [], "value", "label");
    renderSelectOptions(citySelect, "Select City", [], "value", "label");
    renderSelectOptions(zipSelect, "Select ZIP", [], "value", "label");
    LocationPickerState.currentCityZipOptions = [];
    clearAreaSuggestions();
    syncLocationInputFromSelectors();
    return true;
  }

  setSelectLoading(stateSelect, "Loading states...");
  setSelectLoading(citySelect, "Select City");
  setSelectLoading(zipSelect, "Select ZIP");

  try {
    const states = await fetchStatesFromApi(country);
    const options = states.map((s) => ({
      value: s.code,
      label: `${s.name} (${s.code})`,
    }));
    const placeholder = options.length > 0 ? "Select State" : "No States";
    renderSelectOptions(stateSelect, placeholder, options, "value", "label");
    renderSelectOptions(citySelect, "Select City", [], "value", "label");
    renderSelectOptions(zipSelect, "Select ZIP", [], "value", "label");
    LocationPickerState.currentCityZipOptions = [];
    clearAreaSuggestions();
    clearLocationRetryTimer();
    if (!LocationPickerState.apiReady && LocationPickerState.warnedUnavailable) {
      logToConsole("Location picker reconnected.", "success");
    }
    LocationPickerState.apiReady = true;
    LocationPickerState.warnedUnavailable = false;
    LocationPickerState.retryAttempts = 0;
    setLocationPickerDisabled(false);
    syncLocationInputFromSelectors();
    return true;
  } catch (err) {
    handleLocationApiUnavailable(err);
    setSelectLoading(stateSelect, "Location API offline");
    setSelectLoading(citySelect, "Location API offline");
    setSelectLoading(zipSelect, "Location API offline");
    clearAreaSuggestions();
    return false;
  }
}

async function populateCityOptionsForState(countryCode, stateCode) {
  const { citySelect, zipSelect } = getLocationPickerElements();
  if (!citySelect || !zipSelect) return;
  const country = String(countryCode || "").trim().toUpperCase();
  const code = String(stateCode || "").trim().toUpperCase();
  if (!country || !code) {
    renderSelectOptions(citySelect, "Select City", [], "value", "label");
    renderSelectOptions(zipSelect, "Select ZIP", [], "value", "label");
    LocationPickerState.currentCityZipOptions = [];
    clearAreaSuggestions();
    return;
  }

  setSelectLoading(citySelect, "Loading cities...");
  renderSelectOptions(zipSelect, "Select ZIP", [], "value", "label");
  LocationPickerState.currentCityZipOptions = [];
  try {
    const cities = await fetchCitiesByState(country, code);
    const options = cities.map((city) => ({ value: city, label: city }));
    renderSelectOptions(citySelect, "Select City", options, "value", "label");
    renderAreaSuggestions(cities);
  } catch (err) {
    handleLocationApiUnavailable(err);
    setSelectLoading(citySelect, "Location API offline");
    clearAreaSuggestions();
  }
}

async function populateZipOptions(countryCode, stateCode, cityName) {
  const { zipSelect } = getLocationPickerElements();
  if (!zipSelect) return;
  const country = String(countryCode || "").trim().toUpperCase();
  const code = String(stateCode || "").trim().toUpperCase();
  const city = String(cityName || "").trim();
  if (!country || !code || !city) {
    renderSelectOptions(zipSelect, "Select ZIP", [], "value", "label");
    LocationPickerState.currentCityZipOptions = [];
    return;
  }

  setSelectLoading(zipSelect, "Loading ZIPs...");
  try {
    const zips = await fetchZipsByStateCity(country, code, city);
    const options = zips.map((zip) => ({ value: zip, label: zip }));
    renderSelectOptions(zipSelect, "Select ZIP", options, "value", "label");
    LocationPickerState.currentCityZipOptions = [...zips];
  } catch (err) {
    handleLocationApiUnavailable(err);
    setSelectLoading(zipSelect, "Location API offline");
    LocationPickerState.currentCityZipOptions = [];
  }
}

async function handleCountryChange() {
  const { countrySelect, stateSelect, citySelect, zipSelect, zipAreaSelect, zipAreaInput } = getLocationPickerElements();
  const countryCode = String(countrySelect?.value || "").trim().toUpperCase();
  if (stateSelect) stateSelect.value = "";
  if (citySelect) citySelect.value = "";
  if (zipSelect) zipSelect.value = "";
  if (zipAreaSelect) zipAreaSelect.value = "";
  if (zipAreaInput) zipAreaInput.value = "";
  LocationPickerState.currentCityZipOptions = [];
  clearAreaSuggestions();
  await populateStateOptions(countryCode);
  syncLocationInputFromSelectors();
}

async function handleStateChange() {
  const { countrySelect, stateSelect, citySelect, zipAreaSelect, zipAreaInput } = getLocationPickerElements();
  const countryCode = String(countrySelect?.value || "").trim().toUpperCase();
  const stateCode = String(stateSelect?.value || "").trim().toUpperCase();
  LocationPickerState.currentCityZipOptions = [];
  await populateCityOptionsForState(countryCode, stateCode);
  if (citySelect) citySelect.value = "";
  if (zipAreaSelect) zipAreaSelect.value = "";
  if (zipAreaInput) {
    zipAreaInput.value = "";
    refreshAreaSuggestions(String(zipAreaInput.value || "")).catch(() => {});
  }
  syncLocationInputFromSelectors();
}

async function handleCityChange() {
  const { countrySelect, stateSelect, citySelect, zipSelect, zipAreaSelect, zipAreaInput } = getLocationPickerElements();
  const countryCode = String(countrySelect?.value || "").trim().toUpperCase();
  const stateCode = String(stateSelect?.value || "").trim().toUpperCase();
  const city = String(citySelect?.value || "").trim();
  LocationPickerState.currentCityZipOptions = [];
  await populateZipOptions(countryCode, stateCode, city);
  if (zipSelect) zipSelect.value = "";
  if (zipAreaSelect && city) {
    zipAreaSelect.value = city;
  }
  if (zipAreaInput && city && !String(zipAreaInput.value || "").trim()) {
    zipAreaInput.value = city;
  }
  syncLocationInputFromSelectors();
}

function handleZipChange() {
  syncLocationInputFromSelectors();
}

function initLocationPicker() {
  const { countrySelect, stateSelect, citySelect, zipSelect } = getLocationPickerElements();
  if (!countrySelect || !stateSelect || !citySelect || !zipSelect) return;

  populateCountryOptions().catch(handleLocationApiUnavailable);
  countrySelect.addEventListener("change", () => {
    handleCountryChange().catch(handleLocationApiUnavailable);
  });
  stateSelect.addEventListener("change", () => {
    handleStateChange().catch(handleLocationApiUnavailable);
  });
  citySelect.addEventListener("change", () => {
    handleCityChange().catch(handleLocationApiUnavailable);
  });
  zipSelect.addEventListener("change", handleZipChange);
  syncLocationInputFromSelectors();
}

async function getActiveCityZipOptions() {
  const { countrySelect, stateSelect, citySelect } = getLocationPickerElements();
  const countryCode = String(countrySelect?.value || "").trim().toUpperCase();
  const stateCode = String(stateSelect?.value || "").trim().toUpperCase();
  const city = String(citySelect?.value || "").trim();
  if (!countryCode || !stateCode || !city) return [];

  if (!Array.isArray(LocationPickerState.currentCityZipOptions) || LocationPickerState.currentCityZipOptions.length === 0) {
    await populateZipOptions(countryCode, stateCode, city);
  }
  return Array.isArray(LocationPickerState.currentCityZipOptions)
    ? [...LocationPickerState.currentCityZipOptions]
    : [];
}

function bindZipSelectionEvents() {
  const {
    countrySelect,
    stateSelect,
    citySelect,
    zipSelect,
    zipFilterInput,
    zipAreaSelect,
    zipAreaInput,
    zipAddAreaBtn,
    zipAddSelectedBtn,
    zipAddCityBtn,
    zipAddFilteredBtn,
    zipClearListBtn,
  } = getLocationPickerElements();

  if (zipAddAreaBtn) {
    zipAddAreaBtn.addEventListener("click", async () => {
      const countryCode = String(countrySelect?.value || "").trim().toUpperCase();
      const stateCode = String(stateSelect?.value || "").trim().toUpperCase();
      const selectedCity = normalizeLocationPhrase(citySelect?.value || "");
      const area = normalizeLocationPhrase(
        String(zipAreaInput?.value || "").trim()
        || String(zipAreaSelect?.value || "").trim()
        || selectedCity,
      );

      if (!countryCode || !stateCode) {
        logToConsole("Select country and state first to use area-wise ZIP add.", "error");
        return;
      }
      if (!area) {
        logToConsole("Select area/locality or city first.", "error");
        return;
      }
      if (!String(zipAreaInput?.value || "").trim() && !String(zipAreaSelect?.value || "").trim() && selectedCity) {
        logToConsole(`Area not selected; using selected city "${selectedCity}" as area.`, "info");
      }

      try {
        const areaResult = await fetchAreaZipsByState(countryCode, stateCode, area);
        const zips = Array.isArray(areaResult.zips) ? areaResult.zips : [];
        if (!zips.length) {
          logToConsole(`No ZIPs found for area "${area}" in ${stateCode}.`, "error");
          return;
        }
        const matchedCities = Array.isArray(areaResult.matchedCities) ? areaResult.matchedCities : [];
        const cityHint = selectedCity || (matchedCities.length > 0 ? String(matchedCities[0] || "").trim() : "");
        addZipLocations(
          zips,
          `Area "${area}"`,
          getCurrentZipContext({ countryCode, stateCode, city: cityHint, area }),
        );
        if (areaResult.matchedCityCount > 0) {
          logToConsole(`Area matched ${areaResult.matchedCityCount} city/cities.`, "info");
        }
      } catch (err) {
        handleLocationApiUnavailable(err);
      }
    });
  }

  if (zipAddSelectedBtn) {
    zipAddSelectedBtn.addEventListener("click", () => {
      const selectedZip = String(zipSelect?.value || "").trim();
      if (!selectedZip) {
        logToConsole("Select a ZIP first, then click Add Selected ZIP.", "error");
        return;
      }
      addZipLocations([selectedZip], "Selected ZIP", getCurrentZipContext());
    });
  }

  if (zipAddCityBtn) {
    zipAddCityBtn.addEventListener("click", async () => {
      try {
        const zips = await getActiveCityZipOptions();
        if (!zips.length) {
          logToConsole("No city ZIP list found. Select Country, State, and City first.", "error");
          return;
        }
        addZipLocations(zips, "City ZIPs", getCurrentZipContext());
      } catch (err) {
        handleLocationApiUnavailable(err);
      }
    });
  }

  if (zipAddFilteredBtn) {
    zipAddFilteredBtn.addEventListener("click", async () => {
      try {
        const zips = await getActiveCityZipOptions();
        if (!zips.length) {
          logToConsole("No city ZIP list found. Select Country, State, and City first.", "error");
          return;
        }
        const filterText = String(zipFilterInput?.value || "").trim();
        const filtered = filterZipListByInput(zips, filterText);
        if (filtered.length === 0) {
          logToConsole("No ZIPs matched your filter.", "error");
          return;
        }
        addZipLocations(filtered, "Filtered ZIPs", getCurrentZipContext());
      } catch (err) {
        handleLocationApiUnavailable(err);
      }
    });
  }

  if (zipClearListBtn) {
    zipClearListBtn.addEventListener("click", () => clearSelectedZipLocations(false));
  }

  if (zipFilterInput) {
    zipFilterInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      if (event.repeat) return;
      event.preventDefault();
      if (zipAddFilteredBtn) {
        zipAddFilteredBtn.click();
      }
    });
  }

  if (zipAreaSelect) {
    zipAreaSelect.addEventListener("change", () => {
      const selected = normalizeLocationPhrase(zipAreaSelect.value || "");
      if (zipAreaInput && selected) {
        zipAreaInput.value = selected;
      }
      updateZipToolAvailability();
    });
  }

  if (zipAreaInput) {
    zipAreaInput.addEventListener("focus", () => {
      refreshAreaSuggestions(String(zipAreaInput.value || "")).catch(() => {});
      updateZipToolAvailability();
    });
    zipAreaInput.addEventListener("input", () => {
      if (LocationPickerState.areaSuggestTimer) {
        clearTimeout(LocationPickerState.areaSuggestTimer);
      }
      updateZipToolAvailability();
      const value = String(zipAreaInput.value || "");
      LocationPickerState.areaSuggestTimer = setTimeout(() => {
        LocationPickerState.areaSuggestTimer = null;
        refreshAreaSuggestions(value).catch(() => {});
      }, 140);
    });
    zipAreaInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      if (event.repeat) return;
      event.preventDefault();
      if (zipAddAreaBtn) {
        zipAddAreaBtn.click();
      }
    });
  }

  if (zipSelect) {
    zipSelect.addEventListener("change", updateZipToolAvailability);
  }

  if (citySelect) {
    citySelect.addEventListener("change", updateZipToolAvailability);
  }

  if (stateSelect) {
    stateSelect.addEventListener("change", updateZipToolAvailability);
  }

  if (countrySelect) {
    countrySelect.addEventListener("change", updateZipToolAvailability);
  }

  renderSelectedZipLocations();
  updateZipToolAvailability();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}

function titleCase(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

async function requestJson(url, options = {}) {
  const res = await fetch(url, options);
  let payload = {};
  try {
    payload = await res.json();
  } catch (_err) {
    payload = {};
  }
  if (!res.ok) {
    const message = payload.error || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return payload;
}

function getAutomationElements() {
  return {
    presetNameInput: document.getElementById("preset_name"),
    presetSelect: document.getElementById("preset_select"),
    presetSaveBtn: document.getElementById("preset_save_btn"),
    presetLoadBtn: document.getElementById("preset_load_btn"),
    presetDeleteBtn: document.getElementById("preset_delete_btn"),
    zipPackNameInput: document.getElementById("zip_pack_name"),
    zipPackSelect: document.getElementById("zip_pack_select"),
    zipPackSaveBtn: document.getElementById("zip_pack_save_btn"),
    zipPackLoadBtn: document.getElementById("zip_pack_load_btn"),
    zipPackDeleteBtn: document.getElementById("zip_pack_delete_btn"),
    zipPackExportBtn: document.getElementById("zip_pack_export_btn"),
    zipPackImportBtn: document.getElementById("zip_pack_import_btn"),
    zipPackImportFile: document.getElementById("zip_pack_import_file"),
    queryPreviewBtn: document.getElementById("query_preview_btn"),
    queryPreviewMeta: document.getElementById("query_preview_meta"),
    queryPreviewOutput: document.getElementById("query_preview_output"),
  };
}

function collectRunFormInputs() {
  const searchInputMode = String(document.getElementById("search_input_mode")?.value || "guided").trim().toLowerCase();
  const manualQueryMode = searchInputMode === "manual";
  const selectedGuidedCategory = String(document.getElementById("keyword")?.value || "").trim();
  const selectedCategorySubtypes = manualQueryMode ? [] : getSelectedCategorySubtypes();
  const subtypeKeywordList = selectedCategorySubtypes.map((item) => String(item || "").trim()).filter(Boolean);
  const manualQuery = String(document.getElementById("manual_query")?.value || "").trim();
  const rawBulkKeywords = String(document.getElementById("zip_sweep_keywords")?.value || "").trim();
  const manualBulkKeywordList = parseBulkKeywordList(rawBulkKeywords);
  const mergedBulkKeywordList = Array.from(new Set([
    ...subtypeKeywordList,
    ...manualBulkKeywordList,
  ]));
  const inferredGuidedKeyword = subtypeKeywordList.length === 1 ? subtypeKeywordList[0] : selectedGuidedCategory;
  const autoBulkKeywordMode = subtypeKeywordList.length > 1 || manualBulkKeywordList.length > 0;
  const keyword = manualQueryMode
    ? manualQuery
    : (autoBulkKeywordMode ? "" : inferredGuidedKeyword);
  const selectedZipLocations = getSelectedZipLocations();
  const selectedZipPayload = selectedZipLocations.map((entry) => ({
    zip: String(entry.zip || "").trim(),
    location: String(entry.location || entry.zip || "").trim(),
  }));
  const rawZipSweepEnabled = Boolean(document.getElementById("zip_sweep_enabled")?.checked);
  const zipSweepEnabled = rawZipSweepEnabled || autoBulkKeywordMode;
  const bulkZipMode = Boolean(document.getElementById("bulk_zip_mode")?.checked);
  const effectiveZipPayload = (bulkZipMode || zipSweepEnabled) ? selectedZipPayload : [];
  const hasSelectedZipList = selectedZipLocations.length > 0;
  const hasZipList = effectiveZipPayload.length > 0;
  const location = resolveLocationValue(zipSweepEnabled || bulkZipMode);
  const maxResults = parseInt(document.getElementById("max_results")?.value || "50", 10) || 50;
  const maxWorkersRaw = parseInt(document.getElementById("max_workers")?.value || "1", 10);
  const maxWorkers = Number.isFinite(maxWorkersRaw) ? Math.max(1, Math.min(maxWorkersRaw, 8)) : 1;
  const zipSweepKeywords = mergedBulkKeywordList.join(", ");
  const enrichEmails = Boolean(document.getElementById("enrich_emails")?.checked);
  const enrichSocials = Boolean(document.getElementById("enrich_socials")?.checked);
  const collectAllEmails = Boolean(document.getElementById("collect_all_emails")?.checked);
  const fastMode = Boolean(document.getElementById("fast_mode")?.checked);
  const wantsEnrichment = enrichSocials || enrichEmails;
  const speedProfile = fastMode ? (wantsEnrichment ? "email_fast" : "max_speed") : "balanced";
  const enableSocials = fastMode ? wantsEnrichment : (enrichSocials || enrichEmails);
  const enableFacebookEmails = fastMode ? wantsEnrichment : (enrichSocials || enrichEmails);
  const websiteMaxPages = fastMode
    ? (wantsEnrichment ? (collectAllEmails ? 5 : 2) : 1)
    : (enrichEmails ? 8 : 4);

  return {
    searchInputMode,
    manualQueryMode,
    manualQuery,
    guidedKeyword: inferredGuidedKeyword,
    selectedGuidedCategory,
    selectedCategorySubtypes,
    keyword,
    location,
    selectedZipLocations,
    selectedZipPayload,
    effectiveZipPayload,
    hasSelectedZipList,
    hasZipList,
    bulkZipMode,
    maxResults,
    maxWorkers,
    zipSweepEnabled,
    rawZipSweepEnabled,
    zipSweepKeywords,
    bulkKeywordMode: zipSweepEnabled,
    bulkKeywords: zipSweepKeywords,
    autoBulkKeywordMode,
    enrichEmails,
    enrichSocials,
    collectAllEmails,
    fastMode,
    speedProfile,
    enableSocials,
    enableFacebookEmails,
    websiteMaxPages,
    keywordDisplayLabel: manualQueryMode
      ? manualQuery
      : (autoBulkKeywordMode
        ? `${selectedGuidedCategory || "Selected Category"} (${subtypeKeywordList.length} types)`
        : inferredGuidedKeyword),
  };
}

function collectPresetConfig() {
  const { countrySelect, stateSelect, citySelect, zipSelect, zipAreaSelect, zipAreaInput, zipFilterInput } = getLocationPickerElements();
  const snapshot = collectRunFormInputs();
  const searchInputMode = String(document.getElementById("search_input_mode")?.value || "guided").trim().toLowerCase();
  const guidedKeyword = String(document.getElementById("keyword")?.value || "").trim();
  const manualQuery = String(document.getElementById("manual_query")?.value || "").trim();
  return {
    keyword: guidedKeyword,
    selected_category_subtypes: snapshot.selectedCategorySubtypes,
    search_input_mode: searchInputMode,
    manual_query: manualQuery,
    max_results: snapshot.maxResults,
    max_workers: snapshot.maxWorkers,
    enrich_emails: snapshot.enrichEmails,
    enrich_socials: snapshot.enrichSocials,
    collect_all_emails: snapshot.collectAllEmails,
    fast_mode: snapshot.fastMode,
    bulk_zip_mode: snapshot.bulkZipMode,
    zip_sweep_enabled: snapshot.zipSweepEnabled,
    zip_sweep_keywords: snapshot.zipSweepKeywords,
    bulk_keyword_mode: snapshot.bulkKeywordMode,
    bulk_keywords: snapshot.bulkKeywords,
    zip_locations: snapshot.selectedZipPayload,
    location_picker: {
      country: String(countrySelect?.value || "").trim().toUpperCase(),
      state: String(stateSelect?.value || "").trim().toUpperCase(),
      city: String(citySelect?.value || "").trim(),
      zip: String(zipSelect?.value || "").trim(),
      area: String(zipAreaSelect?.value || "").trim() || String(zipAreaInput?.value || "").trim(),
      zip_filter: String(zipFilterInput?.value || "").trim(),
    },
  };
}

async function applyPresetConfig(config) {
  if (!config || typeof config !== "object") return;
  const {
    countrySelect,
    stateSelect,
    citySelect,
    zipSelect,
    zipAreaSelect,
    zipAreaInput,
    zipFilterInput,
  } = getLocationPickerElements();

  const picker = config.location_picker && typeof config.location_picker === "object" ? config.location_picker : {};
  const savedZipLocations = Array.isArray(config.zip_locations) ? config.zip_locations : [];
  const savedCategorySubtypes = Array.isArray(config.selected_category_subtypes) ? config.selected_category_subtypes : [];
  const targetCountry = String(picker.country || "").trim().toUpperCase();
  const targetState = String(picker.state || "").trim().toUpperCase();
  const targetCity = String(picker.city || "").trim();
  const targetZip = String(picker.zip || "").trim();
  const targetArea = String(picker.area || "").trim();
  const targetZipFilter = String(picker.zip_filter || "").trim();

  if (document.getElementById("keyword")) {
    document.getElementById("keyword").value = String(config.keyword || "").trim();
  }
  AppState.categorySubtypeSelections.set(String(config.keyword || "").trim(), savedCategorySubtypes);
  if (document.getElementById("manual_query")) {
    document.getElementById("manual_query").value = String(config.manual_query || "").trim();
  }
  if (document.getElementById("search_input_mode")) {
    const mode = String(config.search_input_mode || "").trim().toLowerCase();
    document.getElementById("search_input_mode").value = mode === "manual" ? "manual" : "guided";
  }
  if (document.getElementById("max_results")) {
    document.getElementById("max_results").value = String(config.max_results || 50);
  }
  if (document.getElementById("max_workers")) {
    document.getElementById("max_workers").value = String(config.max_workers || 1);
  }
  if (document.getElementById("enrich_emails")) {
    document.getElementById("enrich_emails").checked = Boolean(config.enrich_emails);
  }
  if (document.getElementById("enrich_socials")) {
    document.getElementById("enrich_socials").checked = Boolean(config.enrich_socials);
  }
  if (document.getElementById("collect_all_emails")) {
    document.getElementById("collect_all_emails").checked = Boolean(config.collect_all_emails);
  }
  if (document.getElementById("fast_mode")) {
    document.getElementById("fast_mode").checked = Boolean(config.fast_mode);
  }
  if (document.getElementById("bulk_zip_mode")) {
    const hasExplicitBulkMode = Object.prototype.hasOwnProperty.call(config, "bulk_zip_mode");
    document.getElementById("bulk_zip_mode").checked = hasExplicitBulkMode
      ? Boolean(config.bulk_zip_mode)
      : Boolean(savedZipLocations.length > 0);
  }
  if (document.getElementById("zip_sweep_enabled")) {
    document.getElementById("zip_sweep_enabled").checked = Boolean(
      Object.prototype.hasOwnProperty.call(config, "bulk_keyword_mode")
        ? config.bulk_keyword_mode
        : config.zip_sweep_enabled,
    );
  }
  if (document.getElementById("zip_sweep_keywords")) {
    document.getElementById("zip_sweep_keywords").value = String(
      config.bulk_keywords || config.zip_sweep_keywords || "",
    ).trim();
  }
  renderBulkKeywordBuilder();

  if (targetCountry && countrySelect) {
    await populateCountryOptions();
    countrySelect.value = targetCountry;
    await populateStateOptions(targetCountry);
  }
  if (targetState && stateSelect && targetCountry) {
    stateSelect.value = targetState;
    await populateCityOptionsForState(targetCountry, targetState);
  }
  if (targetCity && citySelect && targetCountry && targetState) {
    citySelect.value = targetCity;
    await populateZipOptions(targetCountry, targetState, targetCity);
  }
  if (zipSelect) {
    zipSelect.value = targetZip;
  }
  if (zipAreaSelect) {
    zipAreaSelect.value = targetArea;
  }
  if (zipAreaInput) {
    zipAreaInput.value = targetArea;
  }
  if (zipFilterInput) {
    zipFilterInput.value = targetZipFilter;
  }

  clearSelectedZipLocations(true);
  if (savedZipLocations.length > 0) {
    addZipLocations(savedZipLocations, "Preset ZIP list", getCurrentZipContext({ area: targetArea, city: targetCity }));
  }
  syncSearchInputModeUI();
  syncCategorySubtypeUI(savedCategorySubtypes);
  syncZipSweepUI();
  syncLocationInputFromSelectors();
}

function renderPresetOptions(items) {
  const { presetSelect } = getAutomationElements();
  if (!presetSelect) return;
  const options = (Array.isArray(items) ? items : []).map((item) => ({
    value: String(item.preset_id || ""),
    label: `${String(item.name || "Preset")} (${String(item.use_count || 0)} uses)`,
  }));
  renderSelectOptions(presetSelect, "Saved Presets", options, "value", "label");
}

function renderZipPackOptions(items) {
  const { zipPackSelect } = getAutomationElements();
  if (!zipPackSelect) return;
  const options = (Array.isArray(items) ? items : []).map((item) => ({
    value: String(item.pack_id || ""),
    label: `${String(item.name || "ZIP Pack")} (${String(item.zip_count || 0)} ZIPs)`,
  }));
  renderSelectOptions(zipPackSelect, "ZIP Packs", options, "value", "label");
}

async function refreshPresetsList() {
  try {
    const data = await requestJson("/api/presets?limit=400");
    const items = Array.isArray(data.presets) ? data.presets : [];
    AppState.presetsById = new Map(items.map((item) => [String(item.preset_id || ""), item]));
    renderPresetOptions(items);
  } catch (err) {
    logToConsole(`Failed to load presets: ${err.message}`, "error");
  }
}

async function refreshZipPackList() {
  try {
    const data = await requestJson("/api/zip-packs?limit=400");
    const items = Array.isArray(data.packs) ? data.packs : [];
    AppState.zipPacksById = new Map(items.map((item) => [String(item.pack_id || ""), item]));
    renderZipPackOptions(items);
  } catch (err) {
    logToConsole(`Failed to load ZIP packs: ${err.message}`, "error");
  }
}

function renderQueryPreview(preview) {
  const { queryPreviewMeta, queryPreviewOutput } = getAutomationElements();
  if (!queryPreviewMeta || !queryPreviewOutput) return;
  if (!preview || typeof preview !== "object") {
    queryPreviewMeta.textContent = "Query preview unavailable.";
    queryPreviewOutput.value = "";
    return;
  }
  const rawMode = String(preview.mode || "single");
  const mode = ({
    zip_sweep: "bulk_keyword",
    zip_sweep_multi_zip: "bulk_keyword_multi_zip",
  })[rawMode] || rawMode;
  const total = Number(preview.query_count || 0);
  const zipCount = Number(preview.zip_count || 0);
  const keywordCount = Number(preview.keyword_count || 0);
  const truncated = Boolean(preview.preview_truncated);
  queryPreviewMeta.textContent = `Mode: ${mode} | Queries: ${total} | ZIPs: ${zipCount} | Keywords: ${keywordCount}${truncated ? " | Preview truncated" : ""}`;

  const rows = Array.isArray(preview.queries) ? preview.queries : [];
  const lines = rows.map((query, idx) => `${idx + 1}. ${String(query.query_text || "").trim()}`);
  queryPreviewOutput.value = lines.join("\n");
}

async function previewQueries() {
  const snapshot = collectRunFormInputs();
  const payload = {
    keyword: snapshot.keyword,
    location: snapshot.location,
    max_results: snapshot.maxResults,
    search_input_mode: snapshot.searchInputMode,
    manual_query_mode: snapshot.manualQueryMode,
    manual_query: snapshot.manualQuery,
    bulk_zip_mode: snapshot.bulkZipMode,
    zip_sweep_enabled: snapshot.zipSweepEnabled,
    zip_sweep_keywords: snapshot.zipSweepKeywords,
    bulk_keyword_mode: snapshot.bulkKeywordMode,
    bulk_keywords: snapshot.bulkKeywords,
    zip_locations: snapshot.effectiveZipPayload,
    preview_limit: 300,
  };
  const data = await requestJson("/api/jobs/query-preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  renderQueryPreview(data);
  return data;
}

async function saveCurrentPreset() {
  const { presetNameInput } = getAutomationElements();
  const name = String(presetNameInput?.value || "").trim();
  if (!name) {
    throw new Error("Preset name is required");
  }
  const config = collectPresetConfig();
  const payload = {
    name,
    config,
  };
  const saved = await requestJson("/api/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshPresetsList();
  return saved;
}

async function loadSelectedPreset() {
  const { presetSelect, presetNameInput } = getAutomationElements();
  const presetId = String(presetSelect?.value || "").trim();
  if (!presetId) {
    throw new Error("Select a preset first");
  }
  const preset = await requestJson(`/api/presets/${encodeURIComponent(presetId)}`);
  await applyPresetConfig(preset.config || {});
  await requestJson(`/api/presets/${encodeURIComponent(presetId)}/use`, { method: "POST" });
  if (presetNameInput) {
    presetNameInput.value = String(preset.name || "");
  }
  return preset;
}

async function deleteSelectedPreset() {
  const { presetSelect } = getAutomationElements();
  const presetId = String(presetSelect?.value || "").trim();
  if (!presetId) {
    throw new Error("Select a preset first");
  }
  await requestJson(`/api/presets/${encodeURIComponent(presetId)}`, { method: "DELETE" });
  await refreshPresetsList();
}

async function saveCurrentZipPack() {
  const { zipPackNameInput } = getAutomationElements();
  const name = String(zipPackNameInput?.value || "").trim();
  if (!name) {
    throw new Error("ZIP pack name is required");
  }
  const selectedZipPayload = getSelectedZipLocations().map((entry) => ({
    zip: String(entry.zip || "").trim(),
    location: String(entry.location || entry.zip || "").trim(),
  }));
  if (selectedZipPayload.length === 0) {
    throw new Error("Add ZIPs before saving a ZIP pack");
  }
  const saved = await requestJson("/api/zip-packs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      zip_locations: selectedZipPayload,
    }),
  });
  await refreshZipPackList();
  return saved;
}

async function loadSelectedZipPack() {
  const { zipPackSelect } = getAutomationElements();
  const packId = String(zipPackSelect?.value || "").trim();
  if (!packId) {
    throw new Error("Select a ZIP pack first");
  }
  const pack = await requestJson(`/api/zip-packs/${encodeURIComponent(packId)}`);
  clearSelectedZipLocations(true);
  addZipLocations(pack.zip_locations || [], `ZIP Pack "${pack.name || "Pack"}"`, getCurrentZipContext());
  return pack;
}

async function deleteSelectedZipPack() {
  const { zipPackSelect } = getAutomationElements();
  const packId = String(zipPackSelect?.value || "").trim();
  if (!packId) {
    throw new Error("Select a ZIP pack first");
  }
  await requestJson(`/api/zip-packs/${encodeURIComponent(packId)}`, { method: "DELETE" });
  await refreshZipPackList();
}

function exportSelectedZipPack() {
  const { zipPackSelect } = getAutomationElements();
  const packId = String(zipPackSelect?.value || "").trim();
  if (!packId) {
    throw new Error("Select a ZIP pack first");
  }
  window.location.href = `/api/zip-packs/${encodeURIComponent(packId)}/export.csv`;
}

async function importZipPackFromFile(file) {
  if (!file) {
    throw new Error("Choose a CSV file first");
  }
  const { zipPackNameInput } = getAutomationElements();
  const formData = new FormData();
  formData.append("file", file);
  const suggestedName = String(zipPackNameInput?.value || "").trim();
  if (suggestedName) {
    formData.append("name", suggestedName);
  }
  const res = await fetch("/api/zip-packs/import.csv", {
    method: "POST",
    body: formData,
  });
  let payload = {};
  try {
    payload = await res.json();
  } catch (_err) {
    payload = {};
  }
  if (!res.ok) {
    throw new Error(payload.error || `Import failed (${res.status})`);
  }
  await refreshZipPackList();
  return payload;
}

function bindAutomationLabEvents() {
  const {
    presetNameInput,
    presetSaveBtn,
    presetLoadBtn,
    presetDeleteBtn,
    zipPackNameInput,
    zipPackSaveBtn,
    zipPackLoadBtn,
    zipPackDeleteBtn,
    zipPackExportBtn,
    zipPackImportBtn,
    zipPackImportFile,
    queryPreviewBtn,
  } = getAutomationElements();

  if (presetSaveBtn) {
    presetSaveBtn.addEventListener("click", async () => {
      try {
        const saved = await saveCurrentPreset();
        if (presetNameInput && !presetNameInput.value) {
          presetNameInput.value = String(saved.name || "");
        }
        logToConsole(`Preset saved: ${saved.name || "Preset"}`, "success");
      } catch (err) {
        logToConsole(`Preset save failed: ${err.message}`, "error");
      }
    });
  }

  if (presetLoadBtn) {
    presetLoadBtn.addEventListener("click", async () => {
      try {
        const preset = await loadSelectedPreset();
        logToConsole(`Preset loaded: ${preset.name || "Preset"}`, "success");
      } catch (err) {
        logToConsole(`Preset load failed: ${err.message}`, "error");
      }
    });
  }

  if (presetDeleteBtn) {
    presetDeleteBtn.addEventListener("click", async () => {
      try {
        await deleteSelectedPreset();
        logToConsole("Preset deleted.", "info");
      } catch (err) {
        logToConsole(`Preset delete failed: ${err.message}`, "error");
      }
    });
  }

  if (zipPackSaveBtn) {
    zipPackSaveBtn.addEventListener("click", async () => {
      try {
        const saved = await saveCurrentZipPack();
        if (zipPackNameInput && !zipPackNameInput.value) {
          zipPackNameInput.value = String(saved.name || "");
        }
        logToConsole(`ZIP pack saved: ${saved.name || "Pack"} (${saved.zip_count || 0} ZIPs)`, "success");
      } catch (err) {
        logToConsole(`ZIP pack save failed: ${err.message}`, "error");
      }
    });
  }

  if (zipPackLoadBtn) {
    zipPackLoadBtn.addEventListener("click", async () => {
      try {
        const pack = await loadSelectedZipPack();
        logToConsole(`ZIP pack loaded: ${pack.name || "Pack"}`, "success");
      } catch (err) {
        logToConsole(`ZIP pack load failed: ${err.message}`, "error");
      }
    });
  }

  if (zipPackDeleteBtn) {
    zipPackDeleteBtn.addEventListener("click", async () => {
      try {
        await deleteSelectedZipPack();
        logToConsole("ZIP pack deleted.", "info");
      } catch (err) {
        logToConsole(`ZIP pack delete failed: ${err.message}`, "error");
      }
    });
  }

  if (zipPackExportBtn) {
    zipPackExportBtn.addEventListener("click", () => {
      try {
        exportSelectedZipPack();
      } catch (err) {
        logToConsole(`ZIP pack export failed: ${err.message}`, "error");
      }
    });
  }

  if (zipPackImportBtn && zipPackImportFile) {
    zipPackImportBtn.addEventListener("click", () => {
      zipPackImportFile.click();
    });
    zipPackImportFile.addEventListener("change", async () => {
      const file = zipPackImportFile.files && zipPackImportFile.files[0] ? zipPackImportFile.files[0] : null;
      if (!file) return;
      try {
        const pack = await importZipPackFromFile(file);
        logToConsole(`ZIP pack imported: ${pack.name || "Imported Pack"} (${pack.zip_count || 0} ZIPs)`, "success");
      } catch (err) {
        logToConsole(`ZIP pack import failed: ${err.message}`, "error");
      } finally {
        zipPackImportFile.value = "";
      }
    });
  }

  if (queryPreviewBtn) {
    queryPreviewBtn.addEventListener("click", async () => {
      try {
        const preview = await previewQueries();
        logToConsole(`Query preview ready: ${preview.query_count || 0} query/queries.`, "info");
      } catch (err) {
        logToConsole(`Query preview failed: ${err.message}`, "error");
      }
    });
  }
}

// ========================================
// UI INTERACTIONS
// ========================================

async function startScrape() {
  if (AppState.isScraping) return;

  const snapshot = collectRunFormInputs();
  const keyword = snapshot.keyword;
  const keywordDisplayLabel = snapshot.keywordDisplayLabel || keyword;
  const location = snapshot.location;
  const selectedZipLocations = snapshot.selectedZipLocations;
  const effectiveZipPayload = snapshot.effectiveZipPayload;
  const hasZipList = snapshot.hasZipList;
  const bulkZipMode = snapshot.bulkZipMode;
  const manualQueryMode = snapshot.manualQueryMode;
  const manualQuery = snapshot.manualQuery;
  syncLocationInputFromSelectors();
  const maxResults = snapshot.maxResults;
  const maxWorkers = snapshot.maxWorkers;
  const zipSweepEnabled = snapshot.zipSweepEnabled;
  const zipSweepKeywords = snapshot.zipSweepKeywords;
  const collectAllEmails = snapshot.collectAllEmails;
  const fastMode = snapshot.fastMode;
  const speedProfile = snapshot.speedProfile;
  const enableSocials = snapshot.enableSocials;
  const enableFacebookEmails = snapshot.enableFacebookEmails;
  const websiteMaxPages = snapshot.websiteMaxPages;

  if (bulkZipMode && !hasZipList) {
    logToConsole("Error: Bulk ZIP mode is ON. Add at least one ZIP to ZIP list.", "error");
    return;
  }

  const locationRequired = !hasZipList && (!manualQueryMode || zipSweepEnabled);
  if (!location && locationRequired) {
    logToConsole("Error: Select Country/State/City/ZIP first.", "error");
    return;
  }

  if (zipSweepEnabled) {
    if (!keyword && !zipSweepKeywords) {
      logToConsole("Error: Enter a seed category or bulk keyword list.", "error");
      return;
    }
  } else if (!keyword) {
    logToConsole(
      manualQueryMode
        ? "Error: Manual query is required. Example: restaurants in 10001 tx usa"
        : "Error: Keyword is required.",
      "error",
    );
    return;
  }

  const btn = document.getElementById("run-btn") || document.querySelector(".btn-primary");
  if (!btn) {
    logToConsole("Error: RUN button not found on page.", "error");
    return;
  }
  const originalText = btn.innerHTML;
  btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> INITIALIZING...';
  btn.classList.add("loading");
  AppState.isScraping = true;

  if (hasZipList) {
    logToConsole(`ZIP list active: ${selectedZipLocations.length} ZIPs selected.`, "info");
  }

  if (zipSweepEnabled && hasZipList) {
    logToConsole(`Initializing bulk keyword/category sweep for ${selectedZipLocations.length} ZIPs...`, "info");
  } else if (zipSweepEnabled) {
    logToConsole(`Initializing bulk keyword/category sweep for ${location}...`, "info");
  } else if (bulkZipMode && hasZipList) {
    logToConsole(`Initializing ZIP-wise task: ${keywordDisplayLabel} across ${selectedZipLocations.length} ZIPs...`, "info");
  } else if (manualQueryMode) {
    logToConsole(`Initializing manual query: ${keyword}`, "info");
  } else {
    logToConsole(`Initializing task: ${keywordDisplayLabel} in ${location}...`, "info");
  }

  try {
    const data = await requestJson("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keyword,
        location,
        max_results: maxResults,
        max_workers: maxWorkers,
        enrich_socials: enableSocials,
        enrich_facebook_emails: enableFacebookEmails,
        website_max_pages: websiteMaxPages,
        collect_all_emails: collectAllEmails,
        headless: true,
        fast_mode: fastMode,
        speed_profile: speedProfile,
        search_input_mode: snapshot.searchInputMode,
        manual_query_mode: manualQueryMode,
        manual_query: manualQuery,
        bulk_zip_mode: bulkZipMode,
        zip_sweep_enabled: zipSweepEnabled,
        zip_sweep_keywords: zipSweepKeywords,
        bulk_keyword_mode: snapshot.bulkKeywordMode,
        bulk_keywords: snapshot.bulkKeywords,
        zip_locations: effectiveZipPayload,
      }),
    });

    AppState.jobId = data.job_id;
    logToConsole(`Job started: ${data.job_id}`, "success");
    if (data.mode === "zip_sweep") {
      logToConsole(
        `Bulk keyword/category sweep built ${data.query_count || 0} searches.`,
        "info",
      );
    } else if (data.mode === "zip_sweep_multi_zip") {
      logToConsole(
        `Bulk keyword/category sweep started for ${data.zip_count || selectedZipLocations.length} ZIPs (${data.query_count || 0} total queries).`,
        "info",
      );
    } else if (data.mode === "multi_zip") {
      logToConsole(
        `ZIP-wise bulk started for ${data.zip_count || selectedZipLocations.length} ZIPs (${data.query_count || 0} total queries).`,
        "info",
      );
    }
    logToConsole("Preparing browser workers...", "dim");
    startPolling();
  } catch (e) {
    logToConsole(`Failed to start: ${e.message}`, "error");
    resetButton(btn, originalText);
  }
}

function resetButton(btn, text) {
  if (!btn) return;
  btn.innerHTML = text;
  btn.classList.remove("loading");
  AppState.isScraping = false;
}

function syncSearchInputModeUI() {
  const mode = String(document.getElementById("search_input_mode")?.value || "guided").trim().toLowerCase();
  const isManual = mode === "manual";
  const keywordGroup = document.getElementById("keyword-picker-group");
  const manualGroup = document.getElementById("manual-query-group");
  const modeHint = document.getElementById("search_mode_hint");

  if (keywordGroup) {
    keywordGroup.style.display = isManual ? "none" : "block";
  }
  if (manualGroup) {
    manualGroup.style.display = isManual ? "block" : "none";
  }
  if (modeHint) {
    modeHint.textContent = isManual
      ? "Manual mode: type full query like 'restaurants in 10001 tx usa'. Bulk Keyword Mode can still fan out categories across the selected location."
      : "Guided mode: select a category and location, or enable Bulk Keyword Mode to run many categories together.";
  }
  syncCategorySubtypeUI();
}

function syncZipSweepUI() {
  const zipSweepToggle = document.getElementById("zip_sweep_enabled");
  const rawBulkKeywordCount = parseBulkKeywordList(String(document.getElementById("zip_sweep_keywords")?.value || "")).length;
  if (zipSweepToggle && rawBulkKeywordCount > 0 && !zipSweepToggle.checked) {
    zipSweepToggle.checked = true;
  }
  const rawZipSweepEnabled = Boolean(zipSweepToggle?.checked);
  const selectedSubtypeCount = getSelectedCategorySubtypes().length;
  const autoBulkKeywordMode = selectedSubtypeCount > 1 || rawBulkKeywordCount > 0;
  const zipSweepEnabled = rawZipSweepEnabled || autoBulkKeywordMode;
  const bulkZipMode = Boolean(document.getElementById("bulk_zip_mode")?.checked);
  const searchInputMode = String(document.getElementById("search_input_mode")?.value || "guided").trim().toLowerCase();
  const manualQueryMode = searchInputMode === "manual";
  const selectedCategory = String(document.getElementById("keyword")?.value || "").trim();
  const selectedZipCount = getSelectedZipLocations().length;
  const group = document.getElementById("zip-sweep-keywords-group");
  const locationPreview = document.getElementById("location_preview");
  const modeHint = document.getElementById("scrape_mode_hint");
  if (group) {
    group.style.display = "block";
  }
  if (locationPreview && !locationPreview.value) {
    if (zipSweepEnabled && bulkZipMode) {
      locationPreview.placeholder = "Bulk keyword + Bulk ZIP mode active";
    } else if (zipSweepEnabled && selectedZipCount > 0) {
      locationPreview.placeholder = "Bulk keyword mode + selected ZIP list active";
    } else if (zipSweepEnabled) {
      locationPreview.placeholder = "Select location for Bulk Keyword mode";
    } else if (bulkZipMode) {
      locationPreview.placeholder = "Bulk ZIP mode: add ZIPs and run keyword";
    } else if (manualQueryMode) {
      locationPreview.placeholder = "Manual query can include location text";
    } else {
      locationPreview.placeholder = "Selected location will appear here";
    }
  }
  if (modeHint) {
    if (zipSweepEnabled && bulkZipMode) {
      modeHint.textContent = `Mode: Bulk Keywords/Categories + Bulk ZIP Scraping. Your keyword list runs across ${selectedZipCount} selected ZIPs.`;
    } else if (zipSweepEnabled && selectedZipCount > 0) {
      modeHint.textContent = `Mode: Bulk Keywords/Categories across ${selectedZipCount} selected ZIPs. Each keyword is expanded across the ZIP list.`;
    } else if (autoBulkKeywordMode) {
      if (rawBulkKeywordCount > 0) {
        modeHint.textContent = `Mode: Bulk query scrape. ${rawBulkKeywordCount} search quer${rawBulkKeywordCount === 1 ? "y" : "ies"} will run one after another.`;
      } else {
        modeHint.textContent = `Mode: ${selectedCategory || "Selected"} subtypes bulk scrape. ${selectedSubtypeCount} category types will run automatically.`;
      }
    } else if (zipSweepEnabled) {
      modeHint.textContent = "Mode: Bulk Keywords/Categories for one location. Add many niches like Indian Restaurant, Italian Restaurant, American Restaurant.";
    } else if (bulkZipMode) {
      modeHint.textContent = manualQueryMode
        ? `Mode: Manual Query + Bulk ZIP Scraping. Current query runs across ${selectedZipCount} selected ZIPs.`
        : `Mode: Keyword Search + Bulk ZIP Scraping. Current keyword runs across ${selectedZipCount} selected ZIPs.`;
    } else if (manualQueryMode) {
      modeHint.textContent = "Mode: Manual Query Search (single query text).";
    } else {
      modeHint.textContent = "Mode: Keyword Search (single location). Enable Bulk Keyword Mode to run many categories, or Bulk ZIP Scraping to run across selected ZIPs.";
    }
  }
}

// ========================================
// CONSOLE & LOGGING
// ========================================

function logToConsole(message, type = "dim") {
  const consoleBody = document.getElementById("console-output");
  if (!consoleBody) return;
  const msg = String(message || "");
  const key = `${type}|${msg}`;
  const nowMs = Date.now();
  if (AppState.lastConsoleMessageKey === key && (nowMs - AppState.lastConsoleMessageAt) < 800) {
    return;
  }
  AppState.lastConsoleMessageKey = key;
  AppState.lastConsoleMessageAt = nowMs;

  const entry = document.createElement("div");
  entry.classList.add("log-entry", type);
  const time = new Date().toLocaleTimeString("en-US", { hour12: false });
  entry.innerText = `[${time}] ${msg}`;
  consoleBody.appendChild(entry);
  consoleBody.scrollTop = consoleBody.scrollHeight;
}

// ========================================
// POLLING SYSTEM
// ========================================

function startPolling() {
  if (AppState.pollingInterval) clearInterval(AppState.pollingInterval);

  AppState.pollingInterval = setInterval(async () => {
    if (!AppState.jobId) return;

    try {
      const data = await requestJson(`/api/jobs/${AppState.jobId}`);

      if (data.message && AppState.lastMessage !== data.message) {
        logToConsole(data.message, "info");
        AppState.lastMessage = data.message;
      }

      if (data.status === "completed") {
        clearInterval(AppState.pollingInterval);
        const validLeadCount = Number(data.result_count || 0);
        const filteredRowCount = Number(data.error_count || 0);
        logToConsole("TASK COMPLETED SUCCESSFULLY.", "success");
        logToConsole(`Total Valid Leads Extracted: ${validLeadCount}`, "success");
        if (filteredRowCount > 0) {
          logToConsole(`Filtered / failed rows: ${filteredRowCount}`, "info");
        }
        if (validLeadCount === 0 && filteredRowCount > 0) {
          logToConsole("No valid businesses were found for this niche in the selected location. Try a broader category or nearby ZIP.", "info");
        }

        const btn = document.getElementById("run-btn") || document.querySelector(".btn-primary");
        resetButton(btn, '<i class="fa-solid fa-bolt"></i> RUN');

        await loadResults();
        await loadHistory();
        logToConsole("Excel and CSV exports are ready in Data & Leads.", "info");
      } else if (data.status === "failed") {
        clearInterval(AppState.pollingInterval);
        logToConsole("TASK FAILED.", "error");
        const btn = document.getElementById("run-btn") || document.querySelector(".btn-primary");
        resetButton(btn, '<i class="fa-solid fa-bolt"></i> RUN');
      }
    } catch (e) {
      console.error(e);
    }
  }, 2000);
}

// ========================================
// RESULTS & EXPORT
// ========================================

function splitMultiValueField(value) {
  return Array.from(new Set(
    String(value || "")
      .split(/[\n,;]+/)
      .map((item) => item.trim())
      .filter(Boolean),
  ));
}

function renderEmailCell(row) {
  const sections = [];

  const addSection = (label, values, toneClass = "") => {
    if (!values.length) return;
    const renderedValues = values
      .map((value) => `<div class="${toneClass}" style="font-size: 0.78rem; line-height: 1.35;">${escapeHtml(value)}</div>`)
      .join("");
    sections.push(`
      <div style="margin-bottom: 0.35rem;">
        <div class="text-muted" style="font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.06em;">${escapeHtml(label)}</div>
        ${renderedValues}
      </div>
    `);
  };

  const bestEmails = splitMultiValueField(row.final_email_primary || row.final_email || row.emails);
  const bestSource = String(row.final_email_source || "").trim();
  addSection(bestSource ? `Best (${bestSource})` : "Best", bestEmails, "text-green");
  addSection("Website", splitMultiValueField(row.emails_website));
  addSection("Facebook", splitMultiValueField(row.emails_facebook));
  addSection("Maps", splitMultiValueField(row.emails_maps));

  return sections.length ? sections.join("") : '<span class="text-muted">-</span>';
}

async function loadResults() {
  if (!AppState.jobId) return;

  const data = await requestJson(`/api/jobs/${AppState.jobId}/results`);
  const results = data.results || [];
  const errorCount = Number(data.error_count || 0);

  const tbody = document.querySelector("#results-table tbody");
  if (!tbody) return;

  tbody.innerHTML = "";
  if (results.length === 0) {
    const tr = document.createElement("tr");
    const message = errorCount > 0
      ? `No valid leads found. ${errorCount} row(s) were filtered because they failed or mismatched location.`
      : "No valid leads found for this job yet.";
    tr.innerHTML = `<td colspan="8" style="text-align:center; color: var(--text-muted); padding: 2rem;">${escapeHtml(message)}</td>`;
    tbody.appendChild(tr);
    return;
  }

  results.forEach((row) => {
    const tr = document.createElement("tr");
    const name = escapeHtml(row.name || "N/A");
    const category = escapeHtml(row.category || "");
    const placeId = escapeHtml(row.place_id || "—");
    const address = escapeHtml(row.address || "N/A");
    const phone = escapeHtml(row.phone || "N/A");
    const email = renderEmailCell(row);
    const status = escapeHtml(row.store_status || row.business_status || "Unknown");
    const googleMapsUrl = String(row.google_maps_url || "").trim();
    const mapsCell = googleMapsUrl
      ? `<a href="${escapeAttr(googleMapsUrl)}" target="_blank" rel="noopener noreferrer" class="text-muted">Open Maps</a>`
      : '<span class="text-muted">-</span>';

    tr.innerHTML = `
      <td><div style="font-weight: 500; color: white;">${name}</div><div class="text-muted" style="font-size: 0.8rem;">${category}</div></td>
      <td><code style="font-size: 0.72rem; color: #cbd5e1;">${placeId}</code></td>
      <td>${mapsCell}</td>
      <td>${address}</td>
      <td>${phone}</td>
      <td>${email}</td>
      <td>
        ${row.facebook_url ? `<a href="${escapeAttr(row.facebook_url)}" target="_blank" rel="noopener noreferrer" class="text-muted"><i class="fa-brands fa-facebook"></i></a>` : ""}
        ${row.instagram_url ? `<a href="${escapeAttr(row.instagram_url)}" target="_blank" rel="noopener noreferrer" class="text-muted"><i class="fa-brands fa-instagram"></i></a>` : ""}
        ${row.website ? `<a href="${escapeAttr(row.website)}" target="_blank" rel="noopener noreferrer" class="text-muted"><i class="fa-solid fa-globe"></i></a>` : ""}
      </td>
      <td><span class="network-badge" style="background: rgba(5, 150, 105, 0.1); color: var(--primary);">${status}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

function exportToCSV(jobId) {
  const targetId = jobId || AppState.jobId;
  if (!targetId) {
    alert("No job selected.");
    return;
  }
  window.location.href = `/api/jobs/${targetId}/export.csv`;
}

function exportToExcel(jobId) {
  const targetId = jobId || AppState.jobId;
  if (!targetId) {
    alert("No job selected.");
    return;
  }
  window.location.href = `/api/jobs/${targetId}/export.xlsx`;
}

function exportAll() {
  window.location.href = "/api/export/all";
}

// ========================================
// HISTORY / DATABASE
// ========================================

async function loadHistory() {
  try {
    const data = await requestJson("/api/history");
    const history = data.history || [];

    const tbody = document.querySelector("#history-table tbody");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (history.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color: var(--text-muted); padding: 2rem;">No batches found in database.</td></tr>';
      return;
    }

    history.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    history.forEach((job) => {
      const date = new Date(job.created_at).toLocaleString();
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><div style="font-size: 0.85rem; color: #cbd5e1;">${escapeHtml(date)}</div></td>
        <td>
          <div style="font-weight: 600; color: white;">${escapeHtml(job.keyword)}</div>
          <div class="text-muted" style="font-size: 0.75rem;">${escapeHtml(job.location)}</div>
        </td>
        <td><span style="font-weight: bold; color: var(--primary);">${escapeHtml(job.total_leads)}</span></td>
        <td><span class="network-badge" style="display:inline-flex;">${escapeHtml(job.status)}</span></td>
        <td>
          <button class="btn-secondary" onclick="exportToExcel('${escapeAttr(job.job_id)}')" title="Excel"><i class="fa-solid fa-file-excel"></i></button>
          <button class="btn-secondary" onclick="exportToCSV('${escapeAttr(job.job_id)}')" title="CSV"><i class="fa-solid fa-file-csv"></i></button>
          <button class="btn-danger" onclick="deleteJob('${escapeAttr(job.job_id)}')" title="Delete"><i class="fa-solid fa-trash"></i></button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load history", e);
  }
}

async function deleteJob(jobId) {
  if (!confirm("Are you sure you want to delete this batch? This cannot be undone.")) return;

  try {
    const res = await fetch(`/api/history/${jobId}`, { method: "DELETE" });
    if (res.ok) {
      loadHistory();
    } else {
      alert("Failed to delete job.");
    }
  } catch (_e) {
    alert("Error deleting job.");
  }
}

// Expose globally
window.loadHistory = loadHistory;
window.deleteJob = deleteJob;
window.exportToExcel = exportToExcel;
window.exportToCSV = exportToCSV;
window.exportAll = exportAll;
window.startScrape = startScrape;

const zipSweepToggle = document.getElementById("zip_sweep_enabled");
if (zipSweepToggle) {
  zipSweepToggle.addEventListener("change", syncZipSweepUI);
}
const bulkZipModeToggle = document.getElementById("bulk_zip_mode");
if (bulkZipModeToggle) {
  bulkZipModeToggle.addEventListener("change", syncZipSweepUI);
}
const searchInputModeSelect = document.getElementById("search_input_mode");
if (searchInputModeSelect) {
  searchInputModeSelect.addEventListener("change", () => {
    syncSearchInputModeUI();
    syncZipSweepUI();
  });
}
populateCategoryOptions();
bindCategorySubtypeEvents();
bindBulkKeywordButtons();
initLocationPicker();
bindZipSelectionEvents();
bindAutomationLabEvents();
syncSearchInputModeUI();
syncCategorySubtypeUI();
renderBulkKeywordBuilder();
syncZipSweepUI();
refreshPresetsList();
refreshZipPackList();

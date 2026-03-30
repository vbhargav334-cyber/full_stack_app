# 📊 Results Display & Download Guide

## Complete Workflow for Viewing & Downloading Scraped Data

### ✅ Step 1: Start a Scraping Job

**Path:** Intelligence Hub (Dashboard) → Query Builder

1. Click **"Query Builder"** in left sidebar
2. Enter:
   - **Business Keywords**: e.g., "restaurants", "dentists", "plumbers"
   - **Target Location**: e.g., "New York", "California", "USA"
   - **Scan Depth**: 10-50 results (recommended: 20)
3. Adjust advanced options if needed:
   - Stealth Mode (enabled by default)
   - Resilience Level (retries)
   - Min/Max Delay between requests
4. Click blue **"Initiate Scan"** button

---

### 🔄 Step 2: Monitor Live Progress

**Dashboard displays in real-time:**
- ⚡ **Active Jobs**: 1 (running) → 0 (idle)
- 📈 **Success Rate**: % of items processed
- 📧 **Emails Found**: Growing count of discovered emails
- ⚙️ **Processing Speed**: Items per second

**Status Bar shows:**
- Current job ID
- Progress counter (e.g., "45/100")
- Checkpoint counts
- Deduplication removed

---

### 📋 Step 3: View Results in Table

**When job completes:**

1. Click **"Results Explorer"** in sidebar (5th option)
2. See **"(X records)"** count at top right of Results panel
3. Use **Filters panel** to narrow down:
   - Lead Priority (High/Medium/Low)
   - Min Rating (0-5 stars)
   - Search by Name/Address
   - No Website filter
   - Open Now filter
   - Changed Since Last Run

**Table shows all data:**
- Business name, category, rating, reviews
- Phone, website, address
- ALL emails (website, maps, facebook)
- Social media links (Instagram, LinkedIn, etc.)
- Business hours, status, price level
- Competitor analysis
- Data quality scores

---

### 💾 Step 4: Download Results

**Location:** Batch Operations → Exports panel (third panel)

#### Download Options:

| Button | File Format | Best For | Contains |
|--------|------------|----------|----------|
| **CSV** | `.csv` | Excel, Google Sheets | All data with headers |
| **Excel** | `.xlsx` | Professional reports | Formatted, multiple sheets |
| **Checkpoint** | `.csv` | Retry failed items | Failed records only |
| **Outreach** | `.csv` | Email campaigns | Email-focused fields |
| **CRM** | `.csv` | Salesforce/HubSpot/Zoho | CRM-compatible format |

#### How to Download:

1. **For CSV Export:**
   ```
   Batch Operations → Exports → Click "CSV" button
   → File auto-downloads as "results_[jobId].csv"
   → Open with Excel, Google Sheets, or text editor
   ```

2. **For Excel Export:**
   ```
   Batch Operations → Exports → Click "Excel" button
   → File auto-downloads as "results_[jobId].xlsx"
   → Open with Excel or compatible software
   ```

3. **For CRM Systems:**
   ```
   Batch Operations → Exports → Select provider dropdown
   (Salesforce | HubSpot | Zoho)
   → Click "CRM" button
   → File auto-downloads as "crm_[provider]_[jobId].csv"
   → Import into your CRM system
   ```

---

## 🐛 Troubleshooting

### Results Not Showing?

**Check:**
1. ✓ Job completed (progress bar reached 100%)
2. ✓ No error in status bar (should show "COMPLETED")
3. ✓ Go to Results Explorer tab
4. ✓ Count should show (X records) - if 0, no results found

**Solutions:**
- Verify keywords and location are correct
- Try less restrictive filter settings
- Check console (F12) for error messages
- Restart the app and try again

### Downloads Not Working?

**Check:**
1. ✓ Download buttons are **enabled** (not grayed out)
2. ✓ Job has COMPLETED (status bar shows "COMPLETED")
3. ✓ Browser allows downloads

**Solutions:**
- Check browser download settings
- Disable ad blockers
- Try different download format (CSV vs Excel)
- Check browser console (F12) for errors

### No Data in Downloaded File?

**Causes:**
- Job didn't find any results (check location/keyword)
- Filter settings too restrictive
- API endpoint issue

**Solutions:**
- Run job again with simpler search terms
- Clear filters in Results Explorer
- Check that scraping actually found results

---

## 📈 Data Fields in Downloads

### Standard Export Includes:
```
✓ Name                    ✓ Phone
✓ Category                ✓ Website
✓ Rating                  ✓ Address
✓ Review Count            ✓ Business Hours
✓ Lead Score              ✓ Open Now Status
✓ Lead Priority           ✓ Price Level
✓ Emails (all 3 sources)  ✓ Social Media URLs
✓ Maps URL                ✓ Data Quality Scores
```

### Outreach Format Includes:
```
✓ Business Name           ✓ Email (primary)
✓ Email Website           ✓ Email Facebook
✓ Email Maps              ✓ Phone
✓ Website URL             ✓ Location
```

### CRM Format Includes:
```
(Provider-specific fields)
✓ Account Name            ✓ Email
✓ Phone                   ✓ Website
✓ Address                 ✓ Industry (Category)
```

---

## ⚡ Performance Tips

1. **Start with smaller scans** (20-50 results) to test
2. **Use specific keywords** for better results
3. **Apply filters** before downloading for focused data
4. **Schedule large jobs** during off-peak hours
5. **Resume failed jobs** using Checkpoint feature

---

## 🆘 Need Help?

**Check:**
- Browser console (F12 → Console tab) for errors
- Status bar message for job details
- Try hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
- Clear browser cache and restart


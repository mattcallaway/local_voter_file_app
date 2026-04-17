// Global state
let allTags = [];  // Tag cache — refreshed on load and after import/create/delete

// ============================================================
// THEME & TABS
// ============================================================
function toggleTheme() {
    const body = document.body;
    body.setAttribute('data-theme', body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav li').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    document.getElementById('tab-' + tabId).classList.add('active');
    if (tabId === 'dashboard') loadDashboardStats();
}

// ============================================================
// GLOBAL STATE
// ============================================================
let currentCsvFile = null;
let currentColumns = [];
let activeSearchResults = [];
let currentPage = 0;
let totalCount = 0;
const PAGE_SIZE = 50;
let lastQuery = '';
let lastFilters = {};

const standardFields = [
    {val: "",                    label: "-- Ignore / Raw Data --"},
    {val: "first_name",          label: "Core: First Name"},
    {val: "middle_name",         label: "Core: Middle Name"},
    {val: "last_name",           label: "Core: Last Name"},
    {val: "suffix",              label: "Core: Suffix"},
    {val: "age",                 label: "Core: Age"},
    {val: "sex",                 label: "Core: Sex / Gender"},
    {val: "party",               label: "Core: Party"},
    {val: "address_part",        label: "Address: Street/Line (Combines)"},
    {val: "city",                label: "Address: City"},
    {val: "state",               label: "Address: State"},
    {val: "zip",                 label: "Address: Zip Code"},
    {val: "phone_number",        label: "Phone: Phone Number"},
    {val: "phone_flag",          label: "Phone: Flag (e.g. IsCell)"},
    {val: "district_CD",         label: "District: Congressional (CD)"},
    {val: "district_SD",         label: "District: State Senate (SD)"},
    {val: "district_HD",         label: "District: State House (HD)"},
    {val: "district_Supervisor", label: "District: Supervisor"},
    {val: "district_CensusBlock",label: "District: Census Block"},
    {val: "precinct",            label: "Geography: Precinct"},
    {val: "polling_location",    label: "Geography: Polling Location"},
    {val: "history_Election",    label: "Voting History (Dynamic Auto-Parse)"}
];

// ============================================================
// INITIALIZATION — single merged listener
// ============================================================
window.addEventListener('pywebviewready', function () {
    loadDashboardStats();
    loadLists();
    loadElections();
    loadParties();
    loadTags();
});

// ============================================================
// DASHBOARD
// ============================================================
function loadDashboardStats() {
    window.pywebview.api.get_stats().then(stats => {
        document.getElementById('dash-total-voters').innerText = stats.total_voters.toLocaleString();
        let tbody = document.getElementById('dash-files-tbody');
        tbody.innerHTML = '';
        if (stats.files.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted)">No files imported yet</td></tr>';
            return;
        }
        stats.files.forEach(f => {
            let shortPath = f.filename.split(/[\\/]/).pop();
            let tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${f.id}</td>
                <td title="${escapeHtml(f.filename)}">${escapeHtml(shortPath)}</td>
                <td>${f.state || '—'}</td>
                <td>${f.county || '—'}</td>
                <td>${f.import_date || '—'}</td>
                <td>
                    <button class="btn btn-danger" onclick="deleteFile(${f.id}, '${escapeHtml(shortPath).replace(/'/g, "\\'")}')">Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    });
}

function deleteFile(fileId, fileName) {
    if (!confirm(`Delete "${fileName}" and ALL its voter records?\n\nThis cannot be undone.`)) return;
    window.pywebview.api.delete_file(fileId).then(result => {
        if (result.status === 'success') {
            // Refresh dashboard + search lookup lists
            loadDashboardStats();
            loadElections();
            loadParties();
            loadTags();
        } else {
            alert('Delete failed: ' + (result.message || 'Unknown error'));
        }
    });
}

// ============================================================
// IMPORT
// ============================================================
function selectCsv() {
    window.pywebview.api.select_file().then(result => {
        if (result) {
            currentCsvFile = result.file_path;
            currentColumns = result.columns;
            let parts = currentCsvFile.split(/[\\\/]/);
            document.getElementById('selected-file-info').innerText = 'Selected: ' + parts[parts.length - 1];
            buildMappingTable();
            document.getElementById('mapping-section').style.display = 'block';
        }
    });
}

function buildMappingTable() {
    let tbody = document.getElementById('mapping-tbody');
    tbody.innerHTML = '';
    currentColumns.forEach(col => {
        let tr = document.createElement('tr');
        let tdSelect = document.createElement('td');
        let select = document.createElement('select');
        select.className = 'mapping-select';
        select.setAttribute('data-csv-col', col);

        standardFields.forEach(opt => {
            let option = document.createElement('option');
            option.value = opt.val;
            option.innerText = opt.label;

            let normCol = col.toLowerCase().replace(/[^a-z0-9]/g, '');
            let normOpt = opt.val.toLowerCase().replace(/[^a-z0-9]/g, '');
            if (normOpt !== '' && normCol.includes(normOpt)) option.selected = true;
            if (opt.val === 'address_part'        && (normCol.includes('address') || normCol.includes('line'))) option.selected = true;
            if (opt.val === 'phone_number'         && (normCol.includes('phone') || normCol.includes('cell') || normCol.includes('mobile'))) option.selected = true;
            if (opt.val === 'district_CD'          && (normCol.includes('cd') || normCol.includes('congressional'))) option.selected = true;
            if (opt.val === 'district_SD'          && (normCol.includes('sd') || normCol.includes('statesenate'))) option.selected = true;
            if (opt.val === 'district_HD'          && (normCol.includes('hd') || normCol.includes('statehouse') || normCol.includes('assembly'))) option.selected = true;
            if (opt.val === 'district_Supervisor'  && normCol.includes('supervisor')) option.selected = true;
            if (opt.val === 'history_Election'     && (normCol.includes('general') || normCol.includes('primary') || normCol.includes('municipal') || normCol.includes('special') || normCol.includes('recall'))) option.selected = true;
            select.appendChild(option);
        });

        tdSelect.appendChild(select);
        let tdCol = document.createElement('td');
        tdCol.innerText = col;
        tr.appendChild(tdSelect);
        tr.appendChild(tdCol);
        tbody.appendChild(tr);
    });
}

function startImport() {
    if (!currentCsvFile) return;
    let state = document.getElementById('import-state').value;
    let county = document.getElementById('import-county').value;
    let mapping = {};
    document.querySelectorAll('.mapping-select').forEach(sel => {
        if (sel.value) mapping[sel.getAttribute('data-csv-col')] = sel.value;
    });

    document.getElementById('mapping-section').style.display = 'none';
    document.getElementById('import-progress').style.display = 'block';

    window.pywebview.api.start_import(currentCsvFile, state, county, mapping).then(res => {
        document.getElementById('import-progress').style.display = 'none';
        if (res.status === 'success') {
            alert('Import Successful!');
            currentCsvFile = null;
            document.getElementById('selected-file-info').innerText = '';
            // Refresh cached lookup lists now that new data is in
            loadElections();
            loadParties();
            loadTags();
            switchTab('dashboard');
        } else {
            alert('Error during import: ' + res.message);
            document.getElementById('mapping-section').style.display = 'block';
        }
    });
}

// ============================================================
// MODAL TAG MANAGEMENT
// ============================================================
let modalCreateColor = '#3182ce';
let bulkCreateColor  = '#3182ce';

const TAG_COLOR_OPTIONS = ['#3182ce','#e53e3e','#38a169','#d69e2e','#805ad5','#dd6b20','#319795','#e91e8c'];

function renderModalTags(voterId, tags) {
    let container = document.getElementById('modal-tags-container');
    if (!container) return;
    container.innerHTML = '';

    // Current tag chips
    let chipsDiv = document.createElement('div');
    chipsDiv.className = 'modal-tag-chips';
    if (tags.length === 0) {
        chipsDiv.innerHTML = '<span class="text-muted" style="font-size:0.85em">No tags applied</span>';
    } else {
        tags.forEach(t => {
            chipsDiv.innerHTML += `
                <span class="tag-chip-modal"
                      style="background:${t.color}20; border-color:${t.color}80; color:${t.color}">
                    ${escapeHtml(t.name)}
                    <button class="tag-remove-btn" onclick="removeTagFromVoter(${voterId}, ${t.id})" title="Remove">×</button>
                </span>`;
        });
    }
    container.appendChild(chipsDiv);

    // Add existing tag row
    let appliedIds = new Set(tags.map(t => t.id));
    let available = allTags.filter(t => !appliedIds.has(t.id));
    let addRow = document.createElement('div');
    addRow.className = 'modal-add-tag-row';
    let opts = available.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
    addRow.innerHTML = `
        <select id="modal-tag-add-select"><option value="">+ Add existing tag…</option>${opts}</select>
        <button class="btn secondary" style="padding:5px 10px; font-size:0.85em;" onclick="addTagToVoter(${voterId})">Add</button>
        <button class="btn-pill" style="white-space:nowrap;" onclick="toggleModalTagCreate()">+ New Tag</button>
    `;
    container.appendChild(addRow);

    // Inline create new tag form (hidden by default)
    let createForm = document.createElement('div');
    createForm.id = 'modal-tag-create-form';
    createForm.className = 'modal-create-tag-form';
    createForm.style.display = 'none';
    let swatchHtml = TAG_COLOR_OPTIONS.map((c, i) =>
        `<div class="color-swatch${i === 0 ? ' active' : ''}" style="background:${c}" onclick="selectModalCreateColor('${c}', this)"></div>`
    ).join('');
    createForm.innerHTML = `
        <input type="text" id="modal-create-tag-name" placeholder="New tag name…"
               style="width:100%; box-sizing:border-box; font-size:0.85em; margin-bottom:6px;"
               onkeyup="if(event.key==='Enter') createAndApplyTag(${voterId})">
        <div class="color-swatches">${swatchHtml}</div>
        <button class="btn primary"
                style="width:100%; margin-top:8px; font-size:0.82em; padding:6px;"
                onclick="createAndApplyTag(${voterId})">Create &amp; Add to This Voter</button>
    `;
    container.appendChild(createForm);
}

function addTagToVoter(voterId) {
    let sel = document.getElementById('modal-tag-add-select');
    let tagId = parseInt(sel.value);
    if (!tagId) return;
    window.pywebview.api.add_voter_tag(voterId, tagId).then(() => {
        window.pywebview.api.get_voter_tags(voterId).then(tags => renderModalTags(voterId, tags));
    });
}

function removeTagFromVoter(voterId, tagId) {
    window.pywebview.api.remove_voter_tag(voterId, tagId).then(() => {
        window.pywebview.api.get_voter_tags(voterId).then(tags => renderModalTags(voterId, tags));
    });
}

function toggleModalTagCreate() {
    let form = document.getElementById('modal-tag-create-form');
    if (!form) return;
    let isHidden = form.style.display === 'none';
    form.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
        // Reset color selection to first swatch
        modalCreateColor = TAG_COLOR_OPTIONS[0];
        form.querySelectorAll('.color-swatch').forEach((s, i) =>
            s.classList.toggle('active', i === 0)
        );
        let inp = document.getElementById('modal-create-tag-name');
        if (inp) { inp.value = ''; inp.focus(); }
    }
}

function selectModalCreateColor(color, el) {
    modalCreateColor = color;
    // Only affect swatches inside the modal create form
    let form = document.getElementById('modal-tag-create-form');
    if (form) form.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
    el.classList.add('active');
}

function createAndApplyTag(voterId) {
    let nameInput = document.getElementById('modal-create-tag-name');
    let name = nameInput ? nameInput.value.trim() : '';
    if (!name) { if (nameInput) nameInput.focus(); return; }
    window.pywebview.api.create_tag(name, modalCreateColor).then(result => {
        if (result.status !== 'success') { alert(result.message); return; }
        // Apply to this voter then refresh everything
        window.pywebview.api.add_voter_tag(voterId, result.id).then(() => {
            loadTags();  // refreshes sidebar + bulk select + has_tag filter
            window.pywebview.api.get_voter_tags(voterId).then(tags => renderModalTags(voterId, tags));
        });
    });
}

// ============================================================
// BULK CREATE & APPLY TAG
// ============================================================
function toggleBulkCreateTag() {
    let section = document.getElementById('bulk-create-tag-section');
    let isHidden = section.style.display === 'none';
    section.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
        // Reset
        bulkCreateColor = TAG_COLOR_OPTIONS[0];
        section.querySelectorAll('.color-swatch').forEach((s, i) =>
            s.classList.toggle('active', i === 0)
        );
        let inp = document.getElementById('bulk-new-tag-name');
        if (inp) { inp.value = ''; inp.focus(); }
    }
}

function selectBulkCreateColor(color, el) {
    bulkCreateColor = color;
    let section = document.getElementById('bulk-create-tag-section');
    if (section) section.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
    el.classList.add('active');
}

function createAndBulkApplyTag() {
    let checked = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => parseInt(cb.value));
    let name = document.getElementById('bulk-new-tag-name').value.trim();
    if (checked.length === 0) { alert('No voters selected in results'); return; }
    if (!name) { document.getElementById('bulk-new-tag-name').focus(); return; }
    window.pywebview.api.create_tag(name, bulkCreateColor).then(result => {
        if (result.status !== 'success') { alert(result.message); return; }
        window.pywebview.api.bulk_add_tag(checked, result.id).then(r => {
            loadTags();            // refresh sidebar + dropdowns
            toggleBulkCreateTag(); // close form
            alert(`"${name}" created and applied to ${r.count} voter${r.count !== 1 ? 's' : ''}!`);
        });
    });
}

// ============================================================
// MODAL — close, backdrop, raw data toggle
// ============================================================
let selectedTagColor = '#3182ce';

function loadTags() {
    window.pywebview.api.get_tags().then(tags => {
        allTags = tags;
        renderTagManagerSidebar(tags);

        // Populate bulk tag select
        let bulkSel = document.getElementById('bulk-tag-select');
        if (bulkSel) {
            bulkSel.innerHTML = '<option value="">-- Tag --</option>';
            tags.forEach(t => {
                bulkSel.innerHTML += `<option value="${t.id}">${t.name}</option>`;
            });
        }

        // Populate has_tag filter
        let filterSel = document.getElementById('filter-tag');
        if (filterSel) {
            filterSel.innerHTML = '<option value="">-- Any --</option>';
            tags.forEach(t => {
                filterSel.innerHTML += `<option value="${t.id}">${t.name}</option>`;
            });
        }
    });
}

function renderTagManagerSidebar(tags) {
    let container = document.getElementById('tag-chips-list');
    if (!container) return;
    container.innerHTML = '';
    if (tags.length === 0) {
        container.innerHTML = '<span class="text-muted" style="font-size:0.82em">No tags yet — create one above</span>';
        return;
    }
    tags.forEach(t => {
        let chip = document.createElement('div');
        chip.className = 'tag-chip';
        chip.innerHTML = `
            <span class="tag-dot" style="background:${t.color}"></span>
            <span class="tag-name">${escapeHtml(t.name)}</span>
            <button class="tag-delete" onclick="deleteTag(${t.id}, event)" title="Delete tag">×</button>
        `;
        container.appendChild(chip);
    });
}

function toggleCreateTagForm() {
    let form = document.getElementById('create-tag-form');
    let isHidden = form.style.display === 'none' || form.style.display === '';
    form.style.display = isHidden ? 'block' : 'none';
    if (isHidden) document.getElementById('new-tag-name').focus();
}

function selectTagColor(color, el) {
    selectedTagColor = color;
    document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
    el.classList.add('active');
}

function createTag() {
    let nameInput = document.getElementById('new-tag-name');
    let name = nameInput.value.trim();
    if (!name) { nameInput.focus(); return; }
    window.pywebview.api.create_tag(name, selectedTagColor).then(result => {
        if (result.status === 'success') {
            nameInput.value = '';
            document.getElementById('create-tag-form').style.display = 'none';
            loadTags();
        } else {
            alert(result.message);
        }
    });
}

function deleteTag(tagId, event) {
    event.stopPropagation();
    if (!confirm('Delete this tag? It will be removed from all voters.')) return;
    window.pywebview.api.delete_tag(tagId).then(() => loadTags());
}

function applyBulkTag() {
    let checked = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => parseInt(cb.value));
    let tagId = parseInt(document.getElementById('bulk-tag-select').value);
    if (checked.length === 0) { alert('No voters selected'); return; }
    if (!tagId) { alert('Please select a tag first'); return; }
    window.pywebview.api.bulk_add_tag(checked, tagId).then(r => {
        let tagName = allTags.find(t => t.id === tagId)?.name || 'tag';
        alert(`"${tagName}" applied to ${r.count} voter${r.count !== 1 ? 's' : ''}!`);
    });
}

// ============================================================
// PARTIES — dynamic checklist
// ============================================================
function loadParties() {
    window.pywebview.api.get_parties().then(parties => {
        let div = document.getElementById('party-checklist');
        div.innerHTML = '';
        if (!parties || parties.length === 0) {
            div.innerHTML = '<span style="font-size:0.85em; color:var(--text-muted)">No data yet</span>';
            return;
        }
        parties.forEach(p => {
            let d = document.createElement('div');
            d.innerHTML = `<label><input type="checkbox" class="party-cb" value="${p}"> ${p}</label>`;
            div.appendChild(d);
        });
    });
}

// ============================================================
// HISTORY HELPER BUTTONS
// ============================================================
const EVEN_YEARS = ['2000','2002','2004','2006','2008','2010','2012','2014','2016','2018','2020','2022','2024','2026'];
const ODD_YEARS  = ['2001','2003','2005','2007','2009','2011','2013','2015','2017','2019','2021','2023','2025'];

function selectEvenYears() {
    document.querySelectorAll('.history-cb').forEach(cb => {
        cb.checked = EVEN_YEARS.some(y => cb.value.includes(y));
    });
}

function selectOddYears() {
    document.querySelectorAll('.history-cb').forEach(cb => {
        cb.checked = ODD_YEARS.some(y => cb.value.includes(y));
    });
}

function selectPrimaries() {
    document.querySelectorAll('.history-cb').forEach(cb => {
        cb.checked = /primary/i.test(cb.value);
    });
}

function selectGenerals() {
    document.querySelectorAll('.history-cb').forEach(cb => {
        cb.checked = /general/i.test(cb.value);
    });
}

function clearHistory() {
    document.querySelectorAll('.history-cb').forEach(cb => cb.checked = false);
}

// ============================================================
// ELECTIONS — checklist load
// ============================================================
function loadElections() {
    window.pywebview.api.get_elections().then(els => {
        let div = document.getElementById('election-checklist');
        div.innerHTML = '';
        if (!els || els.length === 0) {
            div.innerHTML = '<span style="font-size:0.85em; color:var(--text-muted)">No data yet</span>';
            return;
        }
        els.forEach(el => {
            let d = document.createElement('div');
            d.innerHTML = `<label><input type="checkbox" class="history-cb" value="${el}"> ${el}</label>`;
            div.appendChild(d);
        });
    });
}

// ============================================================
// SEARCH
// ============================================================
function performSearch(resetPage = true) {
    if (resetPage) currentPage = 0;

    lastQuery = document.getElementById('search-query').value;

    // Multi-select party checklist
    let partiesSelected = Array.from(document.querySelectorAll('.party-cb:checked')).map(cb => cb.value);

    // History math
    let historySelected = Array.from(document.querySelectorAll('.history-cb:checked')).map(cb => cb.value);
    let historyMath = null;
    if (historySelected.length > 0) {
        let threshold = parseInt(document.getElementById('filter-history-threshold').value) || 1;
        let mode = document.getElementById('filter-history-mode').value;
        historyMath = { elections: historySelected, threshold: threshold, mode: mode };
    }

    lastFilters = {
        city:          document.getElementById('filter-city').value,
        party:         partiesSelected.length > 0 ? partiesSelected : null,
        precinct:      document.getElementById('filter-precinct').value,
        district_CD:   document.getElementById('filter-district_CD').value,
        district_SD:   document.getElementById('filter-district_SD').value,
        history_math:  historyMath,
        has_tag:       document.getElementById('filter-tag').value || null,
        in_list:       document.getElementById('filter-list').value
    };

    window.pywebview.api.count_voters(lastQuery, lastFilters).then(count => {
        totalCount = count;
        const offset = currentPage * PAGE_SIZE;
        return window.pywebview.api.search_voters(lastQuery, lastFilters, PAGE_SIZE, offset);
    }).then(results => {
        activeSearchResults = results;
        const totalPages = Math.ceil(totalCount / PAGE_SIZE);
        document.getElementById('results-count').innerText =
            `Results (${totalCount.toLocaleString()}) — Page ${currentPage + 1} of ${Math.max(1, totalPages)}`;

        let tbody = document.getElementById('results-tbody');
        tbody.innerHTML = '';

        results.forEach(r => {
            let tr = document.createElement('tr');
            tr.className = 'voter-row';
            tr.onclick = () => openVoterModal(r.id);
            tr.innerHTML = `
                <td><input type="checkbox" class="row-select" value="${r.id}" checked onclick="event.stopPropagation()"></td>
                <td>${r.first_name || ''}</td>
                <td>${r.middle_name || ''}</td>
                <td>${r.last_name || ''}</td>
                <td>${r.suffix || ''}</td>
                <td>${r.address || ''}</td>
                <td>${r.city || ''}</td>
                <td>${r.party || ''}</td>
                <td>${r.age || ''}</td>
            `;
            tbody.appendChild(tr);
        });

        renderPagination();
    });
}

function renderPagination() {
    const totalPages = Math.ceil(totalCount / PAGE_SIZE);
    let container = document.getElementById('pagination-controls');
    container.innerHTML = '';
    if (totalPages <= 1) return;

    let prevBtn = document.createElement('button');
    prevBtn.className = 'btn secondary';
    prevBtn.innerText = '← Prev';
    prevBtn.disabled = currentPage === 0;
    prevBtn.onclick = () => { currentPage--; performSearch(false); };

    let pageLabel = document.createElement('span');
    pageLabel.className = 'page-label';
    pageLabel.innerText = `${currentPage + 1} / ${totalPages}`;

    let nextBtn = document.createElement('button');
    nextBtn.className = 'btn secondary';
    nextBtn.innerText = 'Next →';
    nextBtn.disabled = currentPage >= totalPages - 1;
    nextBtn.onclick = () => { currentPage++; performSearch(false); };

    container.append(prevBtn, pageLabel, nextBtn);
}

// ============================================================
// VOTER PROFILE MODAL
// ============================================================
function openVoterModal(voterId) {
    window.pywebview.api.get_voter_detail(voterId).then(voter => {
        if (!voter) {
            alert('Could not find voter record. Please try searching again.');
            return;
        }

        // Name + IDs
        let fullName = [voter.first_name, voter.middle_name, voter.last_name, voter.suffix]
            .filter(Boolean).join(' ');
        document.getElementById('modal-voter-name').innerText = fullName || '(Unknown)';
        document.getElementById('modal-voter-id').innerText = `Voter ID #${voter.id}`;

        // Party badge
        let partyEl = document.getElementById('modal-voter-party');
        let partyCode = voter.party || 'N/P';
        partyEl.innerText = partyCode;
        let partySlug = partyCode.toLowerCase().replace(/[^a-z]/g, '').slice(0, 3);
        partyEl.className = `party-badge party-${partySlug}`;

        // Contact block
        let contactEl = document.getElementById('modal-contact-block');
        let addr = [voter.address, voter.city, voter.state, voter.zip].filter(Boolean).join(', ');
        contactEl.innerHTML = `
            <div class="contact-row">🏠 ${addr || '—'}</div>
            <div class="contact-row">📞 ${voter.phone || '—'}</div>
            <div class="contact-row">🎂 Age: <strong>${voter.age || '—'}</strong> &nbsp; ⚧ ${voter.sex || '—'} &nbsp; 📍 Precinct: <strong>${voter.precinct || '—'}</strong></div>
        `;
        // Additional phone entries from phones JSON
        if (Array.isArray(voter.phones) && voter.phones.length > 0) {
            voter.phones.forEach(ph => {
                if (ph.mapped_type === 'phone_number') return; // primary already shown
                contactEl.innerHTML += `<div class="contact-row">📱 ${ph.value} <span class="text-muted">(${ph.source_column})</span></div>`;
            });
        }

        // Districts
        let distEl = document.getElementById('modal-districts-grid');
        distEl.innerHTML = '';
        let districts = voter.districts || {};
        if (Object.keys(districts).length === 0) {
            distEl.innerHTML = '<span class="text-muted">No district data mapped</span>';
        } else {
            Object.entries(districts).forEach(([k, v]) => {
                distEl.innerHTML += `
                    <div class="info-cell">
                        <span class="info-label">${k}</span>
                        <span class="info-value">${v}</span>
                    </div>`;
            });
        }

        // Voting history timeline
        let histEl = document.getElementById('modal-history-timeline');
        histEl.innerHTML = '';
        let history = voter.voting_history || {};
        let historyKeys = Object.keys(history).sort().reverse(); // newest first
        if (historyKeys.length === 0) {
            histEl.innerHTML = '<span class="text-muted">No voting history recorded</span>';
        } else {
            historyKeys.forEach(el => {
                let val = history[el];
                let voted = val && val !== '0' && val.toLowerCase() !== 'no' && val.toLowerCase() !== 'n';
                histEl.innerHTML += `
                    <div class="history-row ${voted ? 'voted' : 'not-voted'}">
                        <span class="history-election">${el}</span>
                        <span class="history-marker">${voted ? '✓' : '—'}</span>
                        <span class="history-value">${val}</span>
                    </div>`;
            });
        }

        // Raw data (collapsible — reset to closed)
        let rawEl = document.getElementById('modal-raw-data');
        rawEl.style.display = 'none';
        document.getElementById('modal-raw-toggle').innerText = '▶ Raw Data';
        let rawData = voter.raw_data || {};
        rawEl.innerHTML = '<table class="raw-table">' +
            Object.entries(rawData).map(([k, v]) =>
                `<tr><td class="raw-key">${escapeHtml(k)}</td><td class="raw-val">${escapeHtml(String(v || ''))}</td></tr>`
            ).join('') +
            '</table>';

        // Show overlay
        document.getElementById('voter-modal-overlay').style.display = 'flex';

        // Render tags (voter.tags comes pre-loaded from get_voter_detail)
        renderModalTags(voter.id, voter.tags || []);

    }).catch(err => {
        console.error('[modal] Error loading voter detail:', err);
        alert('An error occurred loading the voter profile. Please try again.');
    });
}

function closeModal() {
    document.getElementById('voter-modal-overlay').style.display = 'none';
}

function closeModalOnBackdrop(event) {
    if (event.target.id === 'voter-modal-overlay') closeModal();
}

function toggleRawData() {
    let rawEl = document.getElementById('modal-raw-data');
    let toggleEl = document.getElementById('modal-raw-toggle');
    let isHidden = rawEl.style.display === 'none' || rawEl.style.display === '';
    rawEl.style.display = isHidden ? 'block' : 'none';
    toggleEl.innerText = (isHidden ? '▼' : '▶') + ' Raw Data';
}

// Escape HTML to prevent XSS in raw voter data display
function escapeHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// Escape key closes modal
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
});

// ============================================================
// LISTS
// ============================================================
function saveAsList() {
    let checked = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => parseInt(cb.value));
    if (checked.length === 0) { alert('No items selected'); return; }
    let name = prompt('Enter a name for this list:');
    if (!name) return;
    window.pywebview.api.create_list(name, null, 1, checked).then(() => {
        alert('List Created!');
        loadLists();
    });
}

function loadLists() {
    window.pywebview.api.get_lists().then(lists => {
        let ul = document.getElementById('saved-lists');
        let filterList = document.getElementById('filter-list');
        ul.innerHTML = '';
        filterList.innerHTML = '<option value="">-- Any --</option>';
        lists.forEach(l => {
            let li = document.createElement('li');
            li.innerText = l.name;
            ul.appendChild(li);
            filterList.innerHTML += `<option value="${l.id}">${l.name}</option>`;
        });
    });
}

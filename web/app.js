// Theme Toggle
function toggleTheme() {
    const body = document.body;
    const current = body.getAttribute('data-theme');
    body.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
}

// Tab Switching
function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav li').forEach(el => el.classList.remove('active'));
    
    document.getElementById(tabId).classList.add('active');
    document.getElementById('tab-' + tabId).classList.add('active');

    if (tabId === 'dashboard') {
        loadDashboardStats();
    }
}

// Global scope vars
let currentCsvFile = null;
let currentColumns = [];
const standardFields = [
    {val: "", label: "-- Ignore / Raw Data --"},
    {val: "first_name", label: "Core: First Name"},
    {val: "last_name", label: "Core: Last Name"},
    {val: "age", label: "Core: Age"},
    {val: "sex", label: "Core: Sex / Gender"},
    {val: "party", label: "Core: Party"},
    {val: "address_part", label: "Address: Street/Line (Combines)"},
    {val: "city", label: "Address: City"},
    {val: "state", label: "Address: State"},
    {val: "zip", label: "Address: Zip Code"},
    {val: "phone_number", label: "Phone: Phone Number"},
    {val: "phone_flag", label: "Phone: Flag (e.g. IsCell)"},
    {val: "district_CD", label: "District: Congressional (CD)"},
    {val: "district_SD", label: "District: State Senate (SD)"},
    {val: "district_HD", label: "District: State House (HD)"},
    {val: "district_Supervisor", label: "District: Supervisor"},
    {val: "district_CensusBlock", label: "District: Census Block"},
    {val: "precinct", label: "Geography: Precinct"},
    {val: "polling_location", label: "Geography: Polling Location"},
    {val: "history_General", label: "Voting History (General)"},
    {val: "history_Primary", label: "Voting History (Primary)"}
];

// Initialize
window.addEventListener('pywebviewready', function() {
    loadDashboardStats();
});

function loadDashboardStats() {
    window.pywebview.api.get_stats().then(stats => {
        document.getElementById('dash-total-voters').innerText = stats.total_voters.toLocaleString();
        
        let tbody = document.getElementById('dash-files-tbody');
        tbody.innerHTML = '';
        stats.files.forEach(f => {
            let tr = document.createElement('tr');
            tr.innerHTML = `<td>${f.id}</td><td>${f.filename}</td><td>${f.state}</td><td>${f.county}</td><td>${f.import_date}</td>`;
            tbody.appendChild(tr);
        });
    });
}

// CSV Selection
function selectCsv() {
    window.pywebview.api.select_file().then(result => {
        if (result) {
            currentCsvFile = result.file_path;
            currentColumns = result.columns;
            
            let parts = currentCsvFile.split(/[\\/]/);
            document.getElementById('selected-file-info').innerText = "Selected: " + parts[parts.length-1];
            
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
        
        // Select dropdown
        let tdSelect = document.createElement('td');
        let select = document.createElement('select');
        select.className = 'mapping-select';
        select.setAttribute('data-csv-col', col);
        
        standardFields.forEach(opt => {
            let option = document.createElement('option');
            option.value = opt.val;
            option.innerText = opt.label;
            
            // Auto mapping guesser
            let normalizeCols = col.toLowerCase().replace(/[^a-z0-9]/g, '');
            let normalizeOpt = opt.val.toLowerCase().replace(/[^a-z0-9]/g, '');
            if (normalizeOpt !== "" && normalizeCols.includes(normalizeOpt)) {
                option.selected = true;
            }
            // Smart enhancements for complex schemas
            if (opt.val === 'address_part' && (normalizeCols.includes('address') || normalizeCols.includes('line'))) option.selected = true;
            if (opt.val === 'phone_number' && (normalizeCols.includes('phone') || normalizeCols.includes('cell') || normalizeCols.includes('mobile'))) option.selected = true;
            if (opt.val === 'district_CD' && (normalizeCols.includes('cd') || normalizeCols.includes('congressional'))) option.selected = true;
            if (opt.val === 'district_SD' && (normalizeCols.includes('sd') || normalizeCols.includes('statesenate'))) option.selected = true;
            if (opt.val === 'district_HD' && (normalizeCols.includes('hd') || normalizeCols.includes('statehouse') || normalizeCols.includes('assembly'))) option.selected = true;
            if (opt.val === 'district_Supervisor' && normalizeCols.includes('supervisor')) option.selected = true;
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
    
    // build mapping dict
    let mapping = {};
    document.querySelectorAll('.mapping-select').forEach(sel => {
        if (sel.value) {
            mapping[sel.getAttribute('data-csv-col')] = sel.value;
        }
    });

    document.getElementById('mapping-section').style.display = 'none';
    document.getElementById('import-progress').style.display = 'block';

    // Start long running task
    window.pywebview.api.start_import(currentCsvFile, state, county, mapping).then(res => {
        document.getElementById('import-progress').style.display = 'none';
        
        if (res.status === 'success') {
            alert('Import Successful!');
            currentCsvFile = null;
            document.getElementById('selected-file-info').innerText = '';
            switchTab('dashboard');
        } else {
            alert('Error during import: ' + res.message);
            document.getElementById('mapping-section').style.display = 'block';
        }
    });
}

let activeSearchResults = [];

// Search
function performSearch() {
    let query = document.getElementById('search-query').value;
    let filters = {
        city: document.getElementById('filter-city').value,
        party: document.getElementById('filter-party').value,
        precinct: document.getElementById('filter-precinct').value,
        district_CD: document.getElementById('filter-district_CD').value,
        district_SD: document.getElementById('filter-district_SD').value
    };
    
    window.pywebview.api.search_voters(query, filters, 100, 0).then(results => {
        activeSearchResults = results;
        document.getElementById('results-count').innerText = `Results (${results.length}${results.length === 100 ? '+' : ''})`;
        
        let tbody = document.getElementById('results-tbody');
        tbody.innerHTML = '';
        
        results.forEach(r => {
            let tr = document.createElement('tr');
            tr.innerHTML = `
                <td><input type="checkbox" class="row-select" value="${r.id}" checked></td>
                <td>${r.first_name || ''}</td>
                <td>${r.last_name || ''}</td>
                <td>${r.address || ''}</td>
                <td>${r.city || ''}</td>
                <td>${r.party || ''}</td>
                <td>${r.age || ''}</td>
            `;
            tbody.appendChild(tr);
        });
    });
}

function saveAsList() {
    let checked = Array.from(document.querySelectorAll('.row-select:checked')).map(cb => parseInt(cb.value));
    if (checked.length === 0) {
        alert("No items selected");
        return;
    }
    
    let name = prompt("Enter a name for this list:");
    if (!name) return;
    
    // We save selected IDs directly (Static list)
    window.pywebview.api.create_list(name, null, 1, checked).then(r => {
        alert("List Created!");
        loadLists();
    });
}

function loadLists() {
    window.pywebview.api.get_lists().then(lists => {
        let ul = document.getElementById('saved-lists');
        ul.innerHTML = '';
        lists.forEach(l => {
            let li = document.createElement('li');
            li.innerText = l.name;
            ul.appendChild(li);
        });
    });
}

// Initial load for lists
window.addEventListener('pywebviewready', function() {
    loadLists();
});

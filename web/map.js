/**
 * map.js — Canvass Planning Map Controller
 *
 * Manages a Leaflet map built around saved voter lists:
 *   - Household-grouped CircleMarkers with party colours
 *   - MarkerCluster for performance on large lists
 *   - Leaflet.heat heatmap toggle
 *   - Rectangle-draw selection → save as new list / export CSV
 *   - Background geocoding progress via polling
 */

'use strict';

// ─── Module state ───────────────────────────────────────────────────────────
let _map          = null;       // Leaflet map instance
let _clusterGroup = null;       // MarkerClusterGroup
let _heatLayer    = null;       // Leaflet.heat layer
let _allVoters    = [];         // Full voter dataset for current list
let _filteredVoters = [];       // After filter applied
let _householdMap = {};         // address_key → {lat, lng, voters[], visible}
let _selectedIds  = new Set();  // Voter IDs currently selected
let _currentListId   = null;
let _currentListName = '';
let _mapMode      = 'cluster';  // 'cluster' | 'heat'
let _geocodePoller = null;

// Rectangle selection state
let _selecting    = false;
let _selectStart  = null;
let _selectRect   = null;

// ─── Party colour palette ───────────────────────────────────────────────────
const PARTY_COLORS = {
    DEM: '#2563eb', D: '#2563eb',
    REP: '#dc2626', R: '#dc2626',
    LIB: '#d97706', L: '#d97706',
    GRN: '#16a34a', G: '#16a34a',
    NPP: '#6b7280', DTS: '#6b7280', NP: '#6b7280', IND: '#6b7280', UNK: '#6b7280',
};

function _partyColor(party) {
    if (!party) return '#6b7280';
    const p = party.toUpperCase().trim();
    return PARTY_COLORS[p] || PARTY_COLORS[p.slice(0, 3)] || '#6b7280';
}

// ─── Map initialisation ─────────────────────────────────────────────────────
function initMap() {
    if (_map) return;

    _map = L.map('canvass-map', { zoomControl: true }).setView([37.5, -120.0], 7);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
    }).addTo(_map);

    _clusterGroup = L.markerClusterGroup({
        maxClusterRadius: 55,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        chunkedLoading: true,
        iconCreateFunction: function (cluster) {
            const n    = cluster.getChildCount();
            const size = n < 10 ? 'sm' : n < 100 ? 'md' : 'lg';
            return L.divIcon({
                html: `<div class="ci ci-${size}"><span>${n}</span></div>`,
                className: '',
                iconSize: null,
            });
        },
    });
    _map.addLayer(_clusterGroup);

    // Rectangle selection mouse events
    _map.on('mousedown', _onMouseDown);
    _map.on('mousemove', _onMouseMove);
    _map.on('mouseup',   _onMouseUp);

    console.log('[map] Leaflet initialised');
}

// Called by switchTab('map')
function onMapTabActivate() {
    if (!_map) initMap();
    setTimeout(() => _map && _map.invalidateSize(), 120);
}

// ─── Load a list into the map ───────────────────────────────────────────────
function loadListMap(listId, listName) {
    _currentListId   = parseInt(listId);
    _currentListName = listName;
    _selectedIds.clear();

    document.getElementById('map-list-name').textContent   = listName;
    document.getElementById('map-stats').textContent       = 'Loading…';
    document.getElementById('map-filtered-stats').textContent = '';
    document.getElementById('map-list-header').style.display  = 'block';
    document.getElementById('map-controls').style.display     = 'block';
    document.getElementById('map-filter-panel').style.display = 'block';
    document.getElementById('map-empty-state').style.display  = 'none';
    document.getElementById('canvass-map').style.display      = 'block';

    initMap();
    if (_heatLayer) { _map.removeLayer(_heatLayer); _heatLayer = null; }
    _clusterGroup.clearLayers();
    _householdMap = {};
    _updateSelectionUI();

    window.pywebview.api.get_list_map_data(_currentListId).then(data => {
        _allVoters = data.voters;
        const s    = data.stats;

        document.getElementById('map-stats').textContent =
            `${s.total.toLocaleString()} voters · ${s.geocoded.toLocaleString()} geocoded · ${s.pending} pending`;

        _populateFilters(_allVoters);
        _applyFilters();
        _updateGeocodeBtn(s);
        _updateSelectionUI();
    }).catch(err => {
        console.error('[map] get_list_map_data error:', err);
        document.getElementById('map-stats').textContent = 'Error loading data';
    });
}

function _updateGeocodeBtn(stats) {
    const row = document.getElementById('geocode-btn-row');
    const btn = document.getElementById('btn-geocode');
    if (stats.pending > 0) {
        row.style.display = 'block';
        btn.textContent   = `📍 Geocode ${stats.pending} address${stats.pending !== 1 ? 'es' : ''}`;
        btn.disabled      = false;
    } else if (stats.geocoded === 0 && stats.total > 0) {
        row.style.display = 'block';
        btn.textContent   = `📍 Geocode ${stats.total} addresses`;
        btn.disabled      = false;
    } else {
        row.style.display = 'none';
    }
    document.getElementById('geocode-progress').style.display = 'none';
}

// ─── Geocoding workflow ─────────────────────────────────────────────────────
function geocodeCurrentList() {
    if (!_currentListId) return;
    const btn = document.getElementById('btn-geocode');
    btn.disabled = true;
    document.getElementById('geocode-progress').style.display = 'block';
    document.getElementById('progress-text').textContent = 'Requesting geocoding…';

    window.pywebview.api.geocode_list(_currentListId).then(result => {
        if (result.status === 'success' || result.total === 0) {
            _finishGeocoding(); return;
        }
        if (result.status === 'started') {
            _geocodePoller = setInterval(() => {
                window.pywebview.api.get_geocode_status(_currentListId).then(job => {
                    const pct = job.total > 0 ? Math.round(job.progress / job.total * 100) : 0;
                    document.getElementById('progress-fill').style.width = pct + '%';
                    document.getElementById('progress-text').textContent =
                        job.message || `${job.progress} / ${job.total}`;
                    if (job.status === 'done' || job.status === 'error') {
                        clearInterval(_geocodePoller);
                        _finishGeocoding();
                    }
                });
            }, 800);
        }
    });
}

function _finishGeocoding() {
    clearInterval(_geocodePoller);
    document.getElementById('btn-geocode').disabled = false;
    document.getElementById('geocode-progress').style.display = 'none';
    loadListMap(_currentListId, _currentListName);  // reload with fresh coords
}

// ─── Filters ────────────────────────────────────────────────────────────────
function _populateFilters(voters) {
    const parties = [...new Set(voters.map(v => v.party).filter(Boolean))].sort();
    const sel = document.getElementById('map-filter-party');
    sel.innerHTML = '<option value="">All Parties</option>';
    parties.forEach(p => { sel.innerHTML += `<option value="${p}">${p}</option>`; });

    // Tags — reuse global allTags from app.js
    const tagSel = document.getElementById('map-filter-tag');
    tagSel.innerHTML = '<option value="">All Tags</option>';
    if (typeof allTags !== 'undefined') {
        allTags.forEach(t => {
            tagSel.innerHTML += `<option value="${t.id}">${escapeHtml(t.name)}</option>`;
        });
    }

    // Precincts
    const precincts = [...new Set(voters.map(v => v.precinct).filter(Boolean))].sort();
    const pSel = document.getElementById('map-filter-precinct-select');
    if (pSel) {
        pSel.innerHTML = '<option value="">All Precincts</option>';
        precincts.forEach(p => { pSel.innerHTML += `<option value="${p}">${p}</option>`; });
    }
}

function _applyFilters() {
    const party    = document.getElementById('map-filter-party').value;
    const precinct = (document.getElementById('map-filter-precinct').value || '').trim().toUpperCase();
    const grouped  = document.getElementById('map-household-group').checked;

    _filteredVoters = _allVoters.filter(v => {
        if (party    && v.party    !== party)    return false;
        if (precinct && !(v.precinct || '').toUpperCase().includes(precinct)) return false;
        return true;
    });

    const geocoded = _filteredVoters.filter(v => v.lat && v.lng);
    document.getElementById('map-filtered-stats').textContent =
        `Showing ${geocoded.length.toLocaleString()} mapped voter${geocoded.length !== 1 ? 's' : ''}`;

    if (_mapMode === 'cluster') {
        _renderClusters(geocoded, grouped);
    } else {
        _renderHeat(geocoded);
    }
}

// Exported for HTML onchange attrs
function applyMapFilters() { _applyFilters(); }

// ─── Cluster rendering ───────────────────────────────────────────────────────
function _buildHouseholdMap(voters) {
    _householdMap = {};
    voters.forEach(v => {
        const key = v.geocode_address || `${v.lat},${v.lng}`;
        if (!_householdMap[key]) {
            _householdMap[key] = { lat: v.lat, lng: v.lng, voters: [] };
        }
        _householdMap[key].voters.push(v);
    });
}

function _renderClusters(voters, grouped) {
    if (_heatLayer) { _map.removeLayer(_heatLayer); _heatLayer = null; }
    if (!_map.hasLayer(_clusterGroup)) _map.addLayer(_clusterGroup);
    _clusterGroup.clearLayers();

    if (grouped) {
        _buildHouseholdMap(voters);

        Object.entries(_householdMap).forEach(([key, hh]) => {
            const mainColor = _partyColor(hh.voters[0].party);
            const selected  = hh.voters.some(v => _selectedIds.has(v.id));
            const multi     = hh.voters.length > 1;

            const marker = L.circleMarker([hh.lat, hh.lng], {
                radius:      multi ? 10 : 7,
                fillColor:   mainColor,
                color:       selected ? '#fbbf24' : '#fff',
                weight:      selected ? 3 : 1.5,
                fillOpacity: 0.88,
                opacity:     1,
            });

            if (multi) {
                marker.bindTooltip(`${hh.voters.length} voters`, { direction: 'top', offset: [0, -5] });
            }
            marker.bindPopup(_householdPopup(hh), { maxWidth: 340, maxHeight: 300 });
            marker.on('click', e => {
                L.DomEvent.stopPropagation(e);
                hh.voters.forEach(v => {
                    if (_selectedIds.has(v.id)) _selectedIds.delete(v.id);
                    else _selectedIds.add(v.id);
                });
                _updateSelectionUI();
                _renderClusters(_filteredVoters.filter(v => v.lat && v.lng),
                                document.getElementById('map-household-group').checked);
            });
            _clusterGroup.addLayer(marker);
        });

    } else {
        voters.forEach(v => {
            const color    = _partyColor(v.party);
            const selected = _selectedIds.has(v.id);
            const marker   = L.circleMarker([v.lat, v.lng], {
                radius: 7, fillColor: color,
                color: selected ? '#fbbf24' : '#fff',
                weight: selected ? 3 : 1.5,
                fillOpacity: 0.88, opacity: 1,
            });
            marker.bindPopup(_voterPopup(v));
            marker.on('click', e => {
                L.DomEvent.stopPropagation(e);
                if (_selectedIds.has(v.id)) _selectedIds.delete(v.id);
                else _selectedIds.add(v.id);
                _updateSelectionUI();
                _renderClusters(_filteredVoters.filter(vv => vv.lat && vv.lng), false);
            });
            _clusterGroup.addLayer(marker);
        });
    }

    // Fit bounds once we have data
    try {
        const b = _clusterGroup.getBounds();
        if (b.isValid()) _map.fitBounds(b, { padding: [20, 20], maxZoom: 16 });
    } catch (_) {}
}

// ─── Heat map rendering ──────────────────────────────────────────────────────
function _renderHeat(voters) {
    _clusterGroup.clearLayers();
    if (!_map.hasLayer(_clusterGroup))  { /* already removed */ }
    if (_heatLayer) _map.removeLayer(_heatLayer);

    const pts = voters.filter(v => v.lat && v.lng).map(v => [v.lat, v.lng, 1]);
    if (!pts.length) return;

    _heatLayer = L.heatLayer(pts, { radius: 25, blur: 20, maxZoom: 17 }).addTo(_map);

    try {
        const lls = pts.map(p => [p[0], p[1]]);
        if (lls.length) _map.fitBounds(lls, { padding: [20, 20] });
    } catch (_) {}
}

// ─── Mode toggle ─────────────────────────────────────────────────────────────
function setMapMode(mode) {
    _mapMode = mode;
    document.getElementById('mode-cluster').classList.toggle('active', mode === 'cluster');
    document.getElementById('mode-heat').classList.toggle('active', mode === 'heat');
    _applyFilters();
}

// ─── Popups ───────────────────────────────────────────────────────────────────
function _householdPopup(hh) {
    const firstVoter = hh.voters[0];
    const addrLine   = [firstVoter.address, firstVoter.city, firstVoter.state].filter(Boolean).join(', ');

    const rows = hh.voters.map(v => {
        const name  = [v.first_name, v.last_name].filter(Boolean).join(' ') || 'Unknown';
        const color = _partyColor(v.party);
        const phone = v.phone ? `<span style="color:#888;font-size:0.78em"> · ${v.phone}</span>` : '';
        return `<div class="ppv-row">
            <span class="ppv-dot" style="background:${color}"></span>
            <span class="ppv-name">${name}</span>
            <span class="ppv-meta">${v.party || ''} · Age&nbsp;${v.age || '?'}${phone}</span>
        </div>`;
    }).join('');

    return `<div class="map-popup">
        <div class="pp-addr"><strong>${addrLine || 'Unknown address'}</strong></div>
        <div class="pp-voters">${rows}</div>
        <div class="pp-foot">${hh.voters.length} voter${hh.voters.length !== 1 ? 's' : ''} · ${firstVoter.precinct || 'No precinct'}</div>
    </div>`;
}

function _voterPopup(v) {
    const name  = [v.first_name, v.middle_name, v.last_name, v.suffix].filter(Boolean).join(' ');
    const color = _partyColor(v.party);
    return `<div class="map-popup">
        <div class="ppv-row" style="margin-bottom:4px;">
            <span class="ppv-dot" style="background:${color}"></span>
            <span class="ppv-name"><strong>${name || 'Unknown'}</strong></span>
        </div>
        <div style="font-size:0.85em;color:#555;">
            ${v.party || 'No party'} · Age ${v.age || '?'} · ${v.sex || ''}<br>
            ${v.address || ''}, ${v.city || ''}<br>
            ${v.precinct ? 'Precinct: ' + v.precinct : ''}
            ${v.phone ? '<br>📞 ' + v.phone : ''}
        </div>
    </div>`;
}

// ─── Rectangle selection ──────────────────────────────────────────────────────
function activateRectSelect() {
    _selecting = true;
    _selectStart = null;
    _map.dragging.disable();
    _map.getContainer().style.cursor = 'crosshair';
    document.getElementById('btn-select-rect').classList.add('active');
}

function _onMouseDown(e) {
    if (!_selecting) return;
    _selectStart = e.latlng;
    if (_selectRect) { _map.removeLayer(_selectRect); _selectRect = null; }
}

function _onMouseMove(e) {
    if (!_selecting || !_selectStart) return;
    const bounds = L.latLngBounds(_selectStart, e.latlng);
    if (_selectRect) _selectRect.setBounds(bounds);
    else _selectRect = L.rectangle(bounds, {
        color: '#667eea', weight: 2, fillOpacity: 0.07, dashArray: '6,4',
    }).addTo(_map);
}

function _onMouseUp(e) {
    if (!_selecting || !_selectStart) return;
    const bounds = L.latLngBounds(_selectStart, e.latlng);
    _selectHouseholdsInBounds(bounds);
    _selecting = false;
    _selectStart = null;
    _map.dragging.enable();
    _map.getContainer().style.cursor = '';
    document.getElementById('btn-select-rect').classList.remove('active');
}

function _selectHouseholdsInBounds(bounds) {
    const grouped = document.getElementById('map-household-group').checked;
    if (grouped) {
        Object.values(_householdMap).forEach(hh => {
            if (hh.lat && hh.lng && bounds.contains([hh.lat, hh.lng])) {
                hh.voters.forEach(v => _selectedIds.add(v.id));
            }
        });
    } else {
        _filteredVoters.forEach(v => {
            if (v.lat && v.lng && bounds.contains([v.lat, v.lng])) {
                _selectedIds.add(v.id);
            }
        });
    }
    _updateSelectionUI();
    _applyFilters();
}

function clearMapSelection() {
    _selectedIds.clear();
    if (_selectRect) { _map.removeLayer(_selectRect); _selectRect = null; }
    _updateSelectionUI();
    _applyFilters();
}

// ─── Selection UI ─────────────────────────────────────────────────────────────
function _updateSelectionUI() {
    const panel = document.getElementById('map-selection-info');
    const n     = _selectedIds.size;

    if (n === 0) {
        panel.style.display = 'none';
        return;
    }

    // Count unique households in selection
    let stops = 0;
    if (Object.keys(_householdMap).length > 0) {
        Object.values(_householdMap).forEach(hh => {
            if (hh.voters.some(v => _selectedIds.has(v.id))) stops++;
        });
    } else {
        stops = n;   // ungrouped — treat each voter as a stop
    }

    panel.style.display = 'block';
    document.getElementById('selected-voter-count').textContent     = n.toLocaleString();
    document.getElementById('selected-household-count').textContent = stops.toLocaleString();
}

// ─── Actions: save / export ────────────────────────────────────────────────
function saveMapSelectionAsNewList() {
    if (_selectedIds.size === 0) return;
    const name = prompt(`Save ${_selectedIds.size} selected voters as a new canvass list:\n\nList name:`);
    if (!name || !name.trim()) return;

    window.pywebview.api.save_map_selection(name.trim(), Array.from(_selectedIds)).then(result => {
        if (result.status === 'success') {
            alert(`"${name}" saved with ${_selectedIds.size} voters!`);
            if (typeof loadLists === 'function') loadLists();
        } else {
            alert('Error saving list: ' + (result.message || 'Unknown error'));
        }
    });
}

function exportSelectedVoters() {
    if (_selectedIds.size === 0) return;
    window.pywebview.api.export_canvass_list(Array.from(_selectedIds)).then(result => {
        if (result.status !== 'success') { alert('Export failed: ' + (result.message || '')); return; }

        const blob = new Blob([result.csv], { type: 'text/csv;charset=utf-8;' });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = `canvass_${(_currentListName || 'export').replace(/[^a-z0-9]/gi, '_')}_${Date.now()}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        alert(`Exported ${result.count} voters across ${result.stops} stops.`);
    });
}

// ─── Map list dropdown (in-page selector) ────────────────────────────────────
function onMapListSelect(sel) {
    const listId   = sel.value;
    const listName = sel.options[sel.selectedIndex]?.dataset.name || sel.options[sel.selectedIndex]?.text || '';
    if (listId) loadListMap(listId, listName);
}

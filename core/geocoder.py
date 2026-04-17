"""
core/geocoder.py — On-demand geocoding for saved voter lists.

Strategy:
  - Normalize addresses from whatever fields are available (mapped columns + raw_data fallbacks)
  - Deduplicate by normalized address (one API call per unique household address)
  - Batch to US Census Geocoder (free, no API key, up to 1000 per request)
  - Cache results in voters.lat / voters.lng / voters.geocode_* columns
  - Subsequent map loads re-use cached coordinates immediately
"""

import csv
import io
import json
import re
from datetime import datetime, timezone

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("[geocoder] WARNING: 'requests' library not installed. Geocoding will be unavailable.")

CENSUS_API_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_SIZE = 900  # Stay safely under Census 1000-address limit


# ---------------------------------------------------------------------------
# Address normalization
# ---------------------------------------------------------------------------

def _clean(s):
    """Strip and upper-case a string; return '' if falsy."""
    return re.sub(r'\s+', ' ', str(s or '').strip().upper())


def build_geocode_address(voter):
    """
    Build a canonical (address, city, state, zip5) tuple for a voter record.

    Priority:
      1. Mapped schema columns (address, city, state, zip)
      2. Common raw_data field names (mAddress, mCity, ...)
    Returns a 4-tuple of normalized strings. Any element may be ''.
    """
    address = _clean(voter.get('address'))
    city    = _clean(voter.get('city'))
    state   = _clean(voter.get('state', ''))[:2]
    zip5    = re.sub(r'[^0-9]', '', str(voter.get('zip') or ''))[:5]

    # Pull raw_data JSON if needed
    raw = voter.get('raw_data') or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}

    # Address fallbacks from raw_data
    if not address:
        addr_keys = ['mAddress', 'mAddressLine1', 'Address', 'ADDRESS',
                     'StreetAddress', 'ResAddress', 'HouseAddress', 'Addr']
        for k in addr_keys:
            if raw.get(k):
                address = _clean(raw[k])
                # Append line 2 if present
                for k2 in ['mAddressLine2', 'mAddressLine3', 'AddressLine2', 'Apt', 'Unit']:
                    if raw.get(k2):
                        address += ' ' + _clean(raw[k2])
                break

    if not city:
        for k in ['mCity', 'City', 'CITY', 'ResCity', 'MailCity']:
            if raw.get(k):
                city = _clean(raw[k])
                break

    if not state:
        for k in ['mState', 'State', 'STATE', 'ResState']:
            if raw.get(k):
                state = _clean(raw[k])[:2]
                break

    if not zip5:
        for k in ['mZip5', 'mZip', 'Zip', 'ZIP', 'ZipCode', 'ZIPCODE', 'ResZip', 'Zip5']:
            if raw.get(k):
                zip5 = re.sub(r'[^0-9]', '', str(raw[k]))[:5]
                if zip5:
                    break

    return address, city, state, zip5


def make_address_key(address, city, state, zip5):
    return f"{address}|{city}|{state}|{zip5}"


# ---------------------------------------------------------------------------
# Census Geocoder batch API
# ---------------------------------------------------------------------------

def _parse_census_response(resp_text, batch):
    """
    Parse Census Geocoder batch CSV response.
    Returns dict: {batch_index → {'lat', 'lng', 'status', 'confidence'}}

    Census response columns:
      ID, Input Address, Match, Match Type, Matched Address, Coordinates, TIGER ID, Side
    Coordinates field: "Longitude,Latitude" (or empty if no match)
    """
    results = {}
    reader = csv.reader(io.StringIO(resp_text))
    for row in reader:
        if not row:
            continue
        try:
            idx = int(row[0])
        except (ValueError, IndexError):
            continue
        if idx >= len(batch):
            continue

        match_indicator = row[2].strip() if len(row) > 2 else ''
        matched_address = row[4].strip() if len(row) > 4 else ''
        coords_str      = row[5].strip().strip('"') if len(row) > 5 else ''

        if match_indicator == 'Match' and coords_str:
            try:
                lng_str, lat_str = coords_str.split(',')
                results[idx] = {
                    'lat': float(lat_str.strip()),
                    'lng': float(lng_str.strip()),
                    'status': 'matched',
                    'confidence': matched_address,
                }
            except (ValueError, IndexError):
                results[idx] = {'lat': None, 'lng': None, 'status': 'parse_error', 'confidence': ''}
        else:
            results[idx] = {'lat': None, 'lng': None, 'status': 'unmatched', 'confidence': ''}

    return results


# ---------------------------------------------------------------------------
# Main geocoding entry point
# ---------------------------------------------------------------------------

def geocode_voters(db, voter_records, progress_callback=None):
    """
    Geocode voters that don't already have matched coordinates.

    Args:
        db:               Database instance (db.conn is the sqlite3 connection)
        voter_records:    list of voter dicts from the DB (must include id, address, city,
                          state, zip, geocode_status, lat, raw_data)
        progress_callback: optional callable(current, total, message)

    Returns:
        dict {voter_id: {'lat', 'lng', 'status', 'confidence', 'geocode_address'}}
    """
    if not HAS_REQUESTS:
        return {
            v['id']: {'lat': None, 'lng': None, 'status': 'error',
                      'confidence': 'requests library not installed', 'geocode_address': ''}
            for v in voter_records
        }

    results = {}

    # -----------------------------------------------------------------------
    # Step 1: Separate already-geocoded voters from those that need work
    # -----------------------------------------------------------------------
    to_geocode = []   # dicts with voter_id + normalized address parts + address_key

    for v in voter_records:
        if v.get('geocode_status') == 'matched' and v.get('lat') is not None:
            results[v['id']] = {
                'lat': v['lat'], 'lng': v['lng'],
                'status': 'matched',
                'confidence': v.get('geocode_confidence', ''),
                'geocode_address': v.get('geocode_address', ''),
            }
            continue

        addr, city, state, zip5 = build_geocode_address(v)
        if not addr or not city or not state:
            results[v['id']] = {
                'lat': None, 'lng': None, 'status': 'no_address',
                'confidence': '', 'geocode_address': '',
            }
            continue

        to_geocode.append({
            'voter_id':    v['id'],
            'address':     addr,
            'city':        city,
            'state':       state,
            'zip':         zip5,
            'address_key': make_address_key(addr, city, state, zip5),
        })

    if not to_geocode:
        if progress_callback:
            progress_callback(0, 0, 'All addresses already geocoded')
        return results

    # -----------------------------------------------------------------------
    # Step 2: Deduplicate addresses (one API call per unique household)
    # -----------------------------------------------------------------------
    key_to_voters = {}     # address_key → [voter_ids]
    key_to_record = {}     # address_key → canonical address record (first seen)

    for item in to_geocode:
        key = item['address_key']
        key_to_voters.setdefault(key, []).append(item['voter_id'])
        if key not in key_to_record:
            key_to_record[key] = item

    unique_addrs = list(key_to_record.values())   # list of unique address dicts
    total        = len(unique_addrs)
    geocoded_geo = {}   # address_key → geo result

    # -----------------------------------------------------------------------
    # Step 3: Batch geocode in chunks of BATCH_SIZE
    # -----------------------------------------------------------------------
    for batch_start in range(0, total, BATCH_SIZE):
        batch = unique_addrs[batch_start: batch_start + BATCH_SIZE]

        if progress_callback:
            end = min(batch_start + BATCH_SIZE, total)
            progress_callback(batch_start, total,
                              f"Geocoding {batch_start + 1}–{end} of {total} unique addresses…")

        # Build CSV payload (Census format: ID,Address,City,State,Zip)
        csv_rows = [
            f'{i},{b["address"]},{b["city"]},{b["state"]},{b["zip"]}'
            for i, b in enumerate(batch)
        ]
        csv_content = '\n'.join(csv_rows)

        try:
            resp = _requests.post(
                CENSUS_API_URL,
                files={'addressFile': ('addrs.csv', io.StringIO(csv_content), 'text/csv')},
                data={'benchmark': 'Public_AR_Current'},
                timeout=120,
            )
            resp.raise_for_status()
            parsed = _parse_census_response(resp.text, batch)
        except Exception as exc:
            print(f'[geocoder] Census API error for batch {batch_start}: {exc}')
            parsed = {}

        for i, b in enumerate(batch):
            geo = parsed.get(i, {'lat': None, 'lng': None, 'status': 'failed', 'confidence': ''})
            geocoded_geo[b['address_key']] = geo

    # -----------------------------------------------------------------------
    # Step 4: Write results back to DB and build return dict
    # -----------------------------------------------------------------------
    now = datetime.now(timezone.utc).isoformat()
    c   = db.conn.cursor()
    c.execute('BEGIN')

    for key, geo in geocoded_geo.items():
        addr_record = key_to_record[key]
        voter_ids   = key_to_voters.get(key, [])

        for vid in voter_ids:
            c.execute(
                'UPDATE voters SET lat=?, lng=?, geocode_status=?, geocode_confidence=?, '
                'geocode_address=?, geocode_at=? WHERE id=?',
                (geo['lat'], geo['lng'], geo['status'], geo['confidence'],
                 addr_record['address'], now, vid)
            )
            results[vid] = {
                'lat': geo['lat'], 'lng': geo['lng'],
                'status': geo['status'],
                'confidence': geo['confidence'],
                'geocode_address': addr_record['address'],
            }

    db.conn.commit()

    if progress_callback:
        matched = sum(1 for g in geocoded_geo.values() if g['status'] == 'matched')
        progress_callback(total, total,
                          f'Done — {matched} of {total} unique addresses matched')

    return results

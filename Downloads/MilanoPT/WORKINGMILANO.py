import csv
import requests
import json
from flask import Flask, jsonify, render_template_string, request
import time
from math import radians, sin, cos, sqrt, atan2
import urllib.request
import zipfile
import io
import os

app = Flask(__name__)

# Global variables (initialized to empty first)
line_paths = {}
station_lines = {}
routes = {}
line_stations_memory = {}

# Load stops data globally
stops = []
with open('stops_processed.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        stops.append({
            "lat": float(row['stop_lat']),
            "lon": float(row['stop_lon']),
            "name": row['stop_name'],
            "id": row['stop_id']
        })

def load_and_process_gtfs_data():
    print("Full GTFS data processing initiated...")
    global line_paths, station_lines, routes
    line_paths = {}
    station_lines = {}
    routes = {}
    
    with open('given_data/routes.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            routes[row['route_id']] = {
                'short_name': row['route_short_name'],
                'type': row['route_type']
            }
    print(f"Loaded {len(routes)} routes.")

    stops_data = {}
    with open('given_data/stops.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stops_data[row['stop_id']] = {
                'Y': float(row['stop_lat']),
                'X': float(row['stop_lon']),
                'name': row['stop_name']
            }
    print(f"Loaded {len(stops_data)} stops for processing.")

    shapes = {}
    with open('given_data/shapes.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            shape_id = row['shape_id']
            if shape_id not in shapes:
                shapes[shape_id] = []
            shapes[shape_id].append({'Y': float(row['shape_pt_lat']), 'X': float(row['shape_pt_lon']), 'seq': int(row['shape_pt_sequence'])})
    
    for shape_id in shapes:
        shapes[shape_id].sort(key=lambda x: x['seq'])
    print(f"Loaded {len(shapes)} shapes.")

    trips_lookup = {}
    with open('given_data/trips.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            trips_lookup[row['trip_id']] = {'route_id': row['route_id'], 'shape_id': row['shape_id']}
    print(f"Loaded {len(trips_lookup)} trips for lookup.")

    # Populate line_paths from shapes via trips
    line_shapes_added = {}
    for trip_id, trip_info in trips_lookup.items():
        route_id = trip_info['route_id']
        shape_id = trip_info['shape_id']

        route_info = routes.get(route_id)
        if not route_info:
            continue

        line_short_name = route_info['short_name']
        route_type = route_info['type']
        current_shape_points = shapes[shape_id]

        # Use route_id as the primary key for line_paths (e.g., "M5", "T3", "B90")
        if route_id not in line_paths:
            line_paths[route_id] = []
            line_shapes_added[route_id] = set()

        if shape_id not in line_shapes_added[route_id]:
            line_paths[route_id].append(current_shape_points)
            line_shapes_added[route_id].add(shape_id)
        
        # Add route_short_name as a secondary key if it's different and unprefixed
        # This handles cases where user might input just '5' for a Metro line that's 'M5' in GTFS
        if route_id != line_short_name and not line_short_name.startswith(('M', 'T', 'B')):
            if line_short_name not in line_paths:
                line_paths[line_short_name] = []
                line_shapes_added[line_short_name] = set()
            
            if shape_id not in line_shapes_added[line_short_name]:
                line_paths[line_short_name].append(current_shape_points)
                line_shapes_added[line_short_name].add(shape_id)

    print(f"Populated {len(line_paths)} unique line paths.")
    print(f"Available line_paths keys after processing: {sorted(list(line_paths.keys()))}") # Debug: print all keys

    # Populate station_lines from stop_times
    for row in csv.DictReader(open('given_data/stop_times.txt', 'r', encoding='utf-8')):
        trip_id = row['trip_id']
        stop_id = row['stop_id']

        if trip_id in trips_lookup and stop_id in stops_data:
            route_id_for_stop = trips_lookup[trip_id]['route_id']
            # Use route_id to link lines to stations for consistency
            # line_name_for_station will be the route_id itself (e.g., "M5", "B90")
            line_name_for_station = route_id_for_stop # Use route_id directly as the line identifier
            
            if line_name_for_station:
                if stop_id not in station_lines:
                    station_lines[stop_id] = []
                if line_name_for_station not in station_lines[stop_id]:
                    station_lines[stop_id].append(line_name_for_station)
    print(f"Populated {len(station_lines)} station lines.")
    print(f"Sample station_lines entries (first 5 stops):")
    sample_stops = list(station_lines.keys())[:5]
    for stop_id in sample_stops:
        print(f"  Stop {stop_id}: {station_lines[stop_id]}")

    # Save to cache
    with open('gtfs_cache.json', 'w') as f:
        json.dump({'line_paths': line_paths, 'station_lines': station_lines}, f)
    print("GTFS data processed and cached successfully.")

def build_line_stations_memory():
    """
    Build a comprehensive memory of all stations for each line.
    Creates a structure: {line_id: {'stations': [station_objects], 'route_info': route_data}}
    """
    print("Building line stations memory...")
    global line_stations_memory
    line_stations_memory = {}
    
    # Load all required data
    stops_data = {}
    with open('given_data/stops.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stops_data[row['stop_id']] = {
                'id': row['stop_id'],
                'name': row['stop_name'],
                'lat': float(row['stop_lat']),
                'lon': float(row['stop_lon'])
            }
    
    routes_data = {}
    with open('given_data/routes.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            routes_data[row['route_id']] = {
                'short_name': row['route_short_name'],
                'long_name': row['route_long_name'],
                'type': row['route_type']
            }
    
    trips_data = {}
    with open('given_data/trips.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            trips_data[row['trip_id']] = {
                'route_id': row['route_id'],
                'shape_id': row['shape_id']
            }
    
    # Build line -> stations mapping
    line_stations_raw = {}  # temp storage: {route_id: set(stop_ids)}
    
    with open('given_data/stop_times.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            trip_id = row['trip_id']
            stop_id = row['stop_id']
            
            if trip_id in trips_data and stop_id in stops_data:
                route_id = trips_data[trip_id]['route_id']
                
                if route_id not in line_stations_raw:
                    line_stations_raw[route_id] = set()
                line_stations_raw[route_id].add(stop_id)
    
    # Convert to final format with full station objects
    for route_id, stop_ids in line_stations_raw.items():
        if route_id in routes_data:
            route_info = routes_data[route_id]
            stations_list = []
            
            for stop_id in stop_ids:
                if stop_id in stops_data:
                    stations_list.append(stops_data[stop_id])
            
            # Sort stations by name for consistency
            stations_list.sort(key=lambda x: x['name'])
            
            line_stations_memory[route_id] = {
                'stations': stations_list,
                'route_info': route_info,
                'station_count': len(stations_list)
            }
            
            # Also add by short_name if different (for easier lookup)
            short_name = route_info['short_name']
            if short_name != route_id and short_name not in line_stations_memory:
                line_stations_memory[short_name] = line_stations_memory[route_id]
    
    print(f"Built memory for {len(line_stations_raw)} lines")
    print(f"Total memory entries: {len(line_stations_memory)}")
    
    # Save to cache
    with open('line_stations_cache.json', 'w', encoding='utf-8') as f:
        json.dump(line_stations_memory, f, ensure_ascii=False, indent=2)
    print("Line stations memory cached successfully.")
    
    return line_stations_memory

# Main GTFS loading logic at startup
try:
    print("Attempting to load GTFS data from cache...")
    with open('gtfs_cache.json', 'r') as f:
        cached_data = json.load(f)
        line_paths = cached_data.get('line_paths', {})
        station_lines = cached_data.get('station_lines', {})
    
    # Force reprocessing if the cache is empty or seems to be missing prefixed Metro lines
    if not line_paths or not station_lines or any(not line_paths.get(f'M{i}') for i in range(1, 6)):
        print("Cache incomplete, empty, or missing expected Metro lines. Reprocessing GTFS data...")
        load_and_process_gtfs_data()
    else:
        print(f"Loaded {len(line_paths)} line paths and {len(station_lines)} station lines from cache.")
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Error loading GTFS cache ({e}). Reprocessing GTFS data...")
    load_and_process_gtfs_data()

# Load line stations memory
try:
    print("Attempting to load line stations memory from cache...")
    with open('line_stations_cache.json', 'r', encoding='utf-8') as f:
        line_stations_memory = json.load(f)
    print(f"Loaded stations memory for {len(line_stations_memory)} line entries.")
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Error loading stations memory cache ({e}). Building from scratch...")
    build_line_stations_memory()

server_url = "https://giromilano.atm.it/proxy.tpportal/proxy.ashx"

# Headers with cookie
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    "Origin": "https://giromilano.atm.it",
    "Referer": "https://giromilano.atm.it/",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Host": "giromilano.atm.it",
    "Cookie": "TS01ac3475=0199b2c74a586b2cd3f979a7ee12300ddcc689b1fefbbbc91f6642ce9f2d4ff46133460b04f410c5a5d64ffea5e2b6581194aaeabc"
}

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in kilometers
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def parse_wait_time(wait_message):
    try:
        if "min" in wait_message.lower():
            return int(wait_message.split()[0])
        return 0
    except:
        return 0

def fetch_wait_times_for_line(stop_code, line_number):
    data = f"url=tpPortal%2Fgeodata%2Fpois%2Fstops%2F{stop_code}"
    try:
        print(f"\n=== Request Details ===")
        print(f"URL: {server_url}")
        print(f"Data: {data}")
        print(f"Headers: {json.dumps(HEADERS, indent=2)}")
        
        response = requests.post(server_url, headers=HEADERS, data=data, timeout=3)
        print(f"\n=== Response Details ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Text: {response.text[:1000]}")
        
        if response.status_code == 200:
            json_data = response.json()
            print(f"\n=== Parsed JSON ===")
            print(f"Data: {json.dumps(json_data, indent=2)}")
            if "Lines" in json_data:
                for line in json_data["Lines"]:
                    if str(line.get("BookletUrl2", "")) == str(line_number):
                        wait_msg = line.get("WaitMessage", "No data")
                        print(f"Found wait time for line {line_number}: {wait_msg}")
                        return parse_wait_time(wait_msg)
    except Exception as e:
        print(f"Error fetching wait time for stop {stop_code}: {e}")
        print(f"Full error details: {str(e)}")
    return None

def fetch_line_path(line_number):
    # Strip any prefix (M, T, B) from the line number
    clean_line = line_number.lstrip('MTB')
    print(f"Looking up path for line {clean_line} (original: {line_number})")
    
    # Use GTFS data instead of API
    if clean_line in line_paths:
        return line_paths[clean_line]
    print(f"Available line numbers: {list(line_paths.keys())[:10]}...")  # Print first 10 lines for debugging
    return None

def find_vehicle_positions(line_number, stops):
    # Get all stops along this line's path from GTFS data
    print(f"\nFinding vehicle positions for line {line_number}")
    
    # Use route_id (which is the key in line_paths now) to get the paths
    if line_number not in line_paths:
        # As a fallback, try to find by route_short_name if route_id wasn't matched directly
        found_route_id = None
        for r_id, r_info in routes.items():
            if r_info['short_name'] == line_number:
                found_route_id = r_id
                break
        if found_route_id and found_route_id in line_paths:
            line_paths_to_use = line_paths[found_route_id]
        else:
            print(f"Line {line_number} not found in GTFS data (neither route_id nor short_name match).")
            return []
    else:
        line_paths_to_use = line_paths[line_number]

    # ... (rest of find_vehicle_positions remains the same, but it's currently not used for line tracking)
    # This function is not currently used for line drawing so we will remove the rest of it for now
    return []

def get_vehicle_type(line_number):
    # Get routes info from the global routes dictionary
    # We need to find the route_id based on line_number (which could be prefixed)
    # This requires iterating through routes to find a match.
    
    # First, try to find a direct match for the line_number in route_short_name (e.g., M5, T3)
    for route_id, route_info in routes.items():
        if route_info['short_name'] == line_number:
            route_type = route_info['type']
            if route_type == "1":
                return "METRO"
            elif route_type == "0":
                return "TRAM"
            elif route_type == "3":
                return "BUS"
    
    # Fallback if no direct match or if get_vehicle_type is called with a non-standard name
    print(f"Warning: Could not determine vehicle type for line '{line_number}' from GTFS data. Defaulting to BUS.")
    return "BUS"

def fetch_vehicle_positions(line_number):
    # This function is not currently used for line drawing, so we will remove its content
    pass

@app.route('/track_line')
def track_line():
    line_number = request.args.get('line_number')
    if not line_number:
        return jsonify({"error": "Missing line_number"}), 400
    
    print(f"\n=== Tracking Line {line_number} ===")
    
    print(f"Looking up GTFS path for line {line_number}")
    
    paths = [] # Will now store a list of paths
    
    # Direct lookup using the user's input line_number (e.g., M5, T3, B90)
    if line_number in line_paths:
        paths = line_paths[line_number]
        print(f"Found {len(paths)} GTFS paths for line {line_number}")
    # If the direct prefixed match fails, try to find a route_id that has this short_name
    else:
        found_route_id_by_short_name = None
        for r_id, r_info in routes.items():
            if r_info['short_name'] == line_number:
                found_route_id_by_short_name = r_id
                break
        if found_route_id_by_short_name and found_route_id_by_short_name in line_paths:
            paths = line_paths[found_route_id_by_short_name]
            print(f"Found {len(paths)} GTFS paths for line {line_number} via short_name fallback.")
        else:
            print(f"Line {line_number} not found in GTFS data.")
            print(f"Available lines: {sorted(list(line_paths.keys()))}") # Debug: print all available keys

    # Get vehicle type
    vehicle_type = get_vehicle_type(line_number)
    print(f"Vehicle type: {vehicle_type}")
    
    # Get stations for this line from our pre-processed data
    line_info = line_stations_memory.get(line_number)
    line_stops = []
    actual_station_count = 0
    if line_info:
        line_stops = line_info.get('stations', [])
        actual_station_count = line_info.get('station_count', 0)

    print(f"Actual station count for {line_number}: {actual_station_count}")

    return jsonify({
        "vehicle_type": vehicle_type,
        "paths": paths,
        "path_lengths": [len(p) for p in paths],
        "actual_station_count": actual_station_count,
        "line_stops": line_stops  # Send the actual stations
    })

@app.route('/wait_time')
def wait_time():
    stop_id = request.args.get('stop_id')
    if not stop_id:
        return jsonify({"error": "Missing stop_id"}), 400
    
    data = f"url=tpPortal%2Fgeodata%2Fpois%2Fstops%2F{stop_id}"
    try:
        print(f"\n=== Wait Time Request Details ===")
        print(f"URL: {server_url}")
        print(f"Data: {data}")
        print(f"Headers: {json.dumps(HEADERS, indent=2)}")
        
        response = requests.post(server_url, headers=HEADERS, data=data, timeout=3)
        print(f"\n=== Response Details ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Text: {response.text[:1000]}")
        
        if response.status_code == 200:
            json_data = response.json()
            print(f"\n=== Parsed JSON ===")
            print(f"Data: {json.dumps(json_data, indent=2)}")
            if "Lines" in json_data:
                wait_times = []
                for line in json_data["Lines"]:
                    line_number = line.get("BookletUrl2", "")
                    wait_message = line.get("WaitMessage", "No data")
                    if line_number and wait_message != "No data":
                        wait_times.append({
                            "line": line_number,
                            "wait": wait_message
                        })
                print(f"Found wait times: {wait_times}")
                return jsonify({"wait_times": wait_times})
    except Exception as e:
        print(f"Error in wait_time endpoint for stop {stop_id}: {e}")
        print(f"Full error details: {str(e)}")
    
    return jsonify({"wait_times": []})

@app.route('/station_lines')
def get_station_lines():
    stop_id = request.args.get('stop_id')
    if not stop_id:
        return jsonify({"error": "Missing stop_id"}), 400
    
    lines = station_lines.get(stop_id, [])
    return jsonify({"lines": lines})

@app.route('/')
def index():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>Milan Stops Map</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link
  rel="stylesheet"
  href="https://unpkg.com/leaflet@1.9.3/dist/leaflet.css"
/>
<link
  rel="stylesheet"
  href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"
/>
<link
  rel="stylesheet"
  href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"
/>

<script src="https://unpkg.com/leaflet@1.9.3/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

<style>
  #map { height: 80vh; width: 100%; }
  #tracking-controls {
    padding: 10px;
    background: #f8f9fa;
    border-top: 1px solid #dee2e6;
  }
  #line-input {
    padding: 5px;
    margin-right: 10px;
  }
  .vehicle-marker {
    background-color: #ff4444;
    border-radius: 50%;
    border: 2px solid white;
    box-shadow: 0 0 5px rgba(0,0,0,0.5);
  }
  .highlighted-stop {
    background-color: #ffeb3b;
    border: 2px solid #fbc02d;
  }
  .tracking-controls {
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .help-text {
    font-size: 0.8em;
    color: #666;
    margin-left: 10px;
  }
</style>
</head>
<body>

<h2>Milan Stops Map - Click a marker to get wait time</h2>
<div id="map"></div>
<div id="tracking-controls">
  <div class="tracking-controls">
    <input type="text" id="line-input" placeholder="Enter line number (e.g., M3 for Metro 3, T3 for Tram 3)">
    <button onclick="trackLine()">Track Line</button>
    <button onclick="resetMap()">Reset Map</button>
    <span id="tracking-status"></span>
  </div>
  <div class="help-text">
    Prefix with M for Metro, T for Tram, B for Bus (e.g., M3, T3, B90)
  </div>
</div>

<script>
  const stops = {{ stops|tojson }};
  const map = L.map('map').setView([45.4642, 9.1900], 12);
  let vehicleMarkers = [];
  let highlightedStops = [];
  let trackingInterval = null;
  let allMarkers = L.markerClusterGroup();
  let filteredMarkers = L.markerClusterGroup();
  let isTracking = false;
  let currentLineLayer = null; // Store the current line layer

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
  }).addTo(map);

  // Add "You Are Here" marker functionality
  let currentLocationMarker = null;
  const currentLocationIcon = L.divIcon({
    className: 'current-location-marker',
    html: '<div style="background-color: #4285F4; width: 20px; height: 20px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 5px rgba(0,0,0,0.5);"></div>',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
  });

  function updateCurrentLocation(position) {
    const { latitude, longitude } = position.coords;
    
    if (currentLocationMarker) {
      currentLocationMarker.setLatLng([latitude, longitude]);
    } else {
      currentLocationMarker = L.marker([latitude, longitude], { icon: currentLocationIcon })
        .bindPopup('You are here')
        .addTo(map);
    }
  }

  function handleLocationError(error) {
    console.error('Error getting location:', error);
    // Don't show alert for location errors as it's not critical
  }

  // Request user's location
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(updateCurrentLocation, handleLocationError);
    // Watch for position changes
    navigator.geolocation.watchPosition(updateCurrentLocation, handleLocationError);
  }

  stops.forEach(stop => {
    const marker = L.marker([stop.lat, stop.lon]);
    marker.bindPopup(`${stop.name}<br>Click marker to load wait time`);

    marker.on('click', function(e) {
      this.getPopup().setContent(`${stop.name}<br>Loading wait times...`).openOn(map);

      // First get the lines that pass through this station
      fetch(`/station_lines?stop_id=${stop.id}`)
        .then(response => response.json())
        .then(data => {
          const linesHtml = data.lines.length > 0 
            ? `Lines: ${data.lines.join(', ')}<br>`
            : 'No line information available<br>';
          
          // Then get wait times
          fetch(`/wait_time?stop_id=${stop.id}`)
            .then(response => response.json())
            .then(waitData => {
              if(waitData.wait_times && waitData.wait_times.length > 0) {
                const waitTimesHtml = waitData.wait_times
                  .map(wt => {
                    if (wt.wait === null || wt.wait === "no serv.") {
                      return `Line ${wt.line}: Not in Service`;
                    } else {
                      return `Line ${wt.line}: ${wt.wait}`;
                    }
                  })
                  .join('<br>');
                this.getPopup().setContent(`${stop.name}<br>${linesHtml}${waitTimesHtml}`);
          } else {
                this.getPopup().setContent(`${stop.name}<br>${linesHtml}No wait time data available`);
          }
            })
            .catch(() => {
              this.getPopup().setContent(`${stop.name}<br>${linesHtml}Error loading wait times`);
            });
        })
        .catch(() => {
          this.getPopup().setContent(`${stop.name}<br>Error loading line information`);
        });
    });

    allMarkers.addLayer(marker);
  });

  map.addLayer(allMarkers);

  function resetMap() {
    clearTracking();
    if (isTracking) {
      map.removeLayer(filteredMarkers);
      map.addLayer(allMarkers);
      isTracking = false;
    }
    // Remove the line layer if it exists
    if (currentLineLayer) {
      map.removeLayer(currentLineLayer);
      currentLineLayer = null;
    }
    document.getElementById('line-input').value = '';
    document.getElementById('tracking-status').textContent = '';
  }

  function clearTracking() {
    // Clear vehicle markers
    vehicleMarkers.forEach(marker => map.removeLayer(marker));
    vehicleMarkers = [];
    
    // Clear tracking interval
    if (trackingInterval) {
      clearInterval(trackingInterval);
      trackingInterval = null;
    }
    
    // Clear line layer
    if (currentLineLayer) {
      map.removeLayer(currentLineLayer);
      currentLineLayer = null;
    }
  }

  function trackLine() {
    const lineNumber = document.getElementById('line-input').value.trim();
    if (!lineNumber) {
        alert('Please enter a line number');
        return;
    }

    clearTracking();
    
    // Remove all markers and add filtered ones
    if (!isTracking) {
        map.removeLayer(allMarkers);
        isTracking = true;
    }
    
    console.log(`Tracking line: ${lineNumber}`);
    
    fetch(`/track_line?line_number=${lineNumber}`)
        .then(response => response.json())
        .then(data => {
            console.log('Received data:', data);
            
            document.getElementById('tracking-status').textContent = 
                `Showing Line ${lineNumber} (${data.actual_station_count} stops)`;
            
            if (data.paths && data.paths.length > 0) {
                console.log(`Drawing paths with ${data.paths.length} segments`);
                
                const lineColor = (
                    lineNumber === 'M1' ? '#FF0000' : // Red
                    lineNumber === 'M2' ? '#008000' : // Green
                    lineNumber === 'M3' ? '#FFFF00' : // Yellow
                    lineNumber === 'M4' ? '#00008B' : // Dark Blue
                    lineNumber === 'M5' ? '#8A2BE2' : // Light Purple
                    lineNumber.startsWith('B') ? '#FF00FF' : // Magenta for Bus
                    lineNumber.startsWith('T') ? '#00FFFF' : // Cyan for Tram
                    '#2196F3' // Default blue if no match
                );
                
                currentLineLayer = L.featureGroup();
                
                // Draw each path as a separate line segment
                data.paths.forEach((path, pathIndex) => {
                    const pathCoords = path.map(point => [point.Y, point.X]);
                    const line = L.polyline(pathCoords, {
                        color: lineColor,
                        weight: 8,
                        opacity: 0.8,
                        smoothFactor: 1
                    });
                    currentLineLayer.addLayer(line);
                });

                // Add markers for stations of the tracked line using pre-processed data
                if (data.line_stops && data.line_stops.length > 0) {
                    data.line_stops.forEach(stop => {
                        const stationMarker = L.circleMarker([stop.lat, stop.lon], {
                            radius: 6,
                            fillColor: lineColor, // Use line color for consistency
                            color: '#fff',
                            weight: 2,
                            opacity: 1,
                            fillOpacity: 0.9
                        }).bindPopup(`${stop.name}<br>Click marker to load wait time`);
                        
                        // Add click event listener to fetch wait times
                        stationMarker.on('click', function(e) {
                            this.getPopup().setContent(`${stop.name}<br>Loading wait times...`).openOn(map);
                            fetch(`/wait_time?stop_id=${stop.id}`)
                                .then(response => response.json())
                                .then(waitData => {
                                    if(waitData.wait_times && waitData.wait_times.length > 0) {
                                        const waitTimesHtml = waitData.wait_times
                                            .map(wt => {
                                              if (wt.wait === null || wt.wait === "no serv.") {
                                                return `Line ${wt.line}: Not in Service`;
                                              } else {
                                                return `Line ${wt.line}: ${wt.wait}`;
                                              }
                                            })
                                            .join('<br>');
                                        this.getPopup().setContent(`${stop.name}<br>${waitTimesHtml}`);
                                    } else {
                                        this.getPopup().setContent(`${stop.name}<br>No wait time data available`);
                                    }
                                })
                                .catch(() => {
                                    this.getPopup().setContent(`${stop.name}<br>Error loading wait times`);
                                });
                        });
                        currentLineLayer.addLayer(stationMarker);
                    });
                } else {
                    console.warn(`No line_stops received for line ${lineNumber}`);
                }
                
                // Add the layer group to the map
                currentLineLayer.addTo(map);
                
                // Fit map to show the entire line
                map.fitBounds(currentLineLayer.getBounds(), {padding: [20, 20]});
                
                console.log('Paths drawn successfully');
                
            } else {
                console.error('No path data received');
                alert('No paths found for this line');
            }
        })
        .catch(error => {
            console.error('Error tracking line:', error);
            document.getElementById('tracking-status').textContent = 'Error tracking line';
            alert('Error loading line data: ' + error.message);
        });
  }

  // Allow Enter key to trigger tracking
  document.getElementById('line-input').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      trackLine();
    }
  });
</script>

</body>
</html>
""", stops=stops)

if __name__ == "__main__":
    app.run(debug=True)
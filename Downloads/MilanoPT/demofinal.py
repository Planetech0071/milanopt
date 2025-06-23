import csv
import json
from flask import Flask, jsonify, render_template_string, request
import time
from math import radians, sin, cos, sqrt, atan2
import urllib.request
import zipfile
import io
import os
from concurrent.futures import ThreadPoolExecutor
import base64
from flask import send_from_directory
import random

app = Flask(__name__)

# Add a route to serve vehicle images
@app.route('/static/vehicle_images/<path:filename>')
def serve_vehicle_image(filename):
    # Create a static folder in your project and copy your images there
    return send_from_directory('static/vehicle_images', filename)

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

# --- REMOVE ALL GTFS TXT PROCESSING: ONLY LOAD FROM JSONS ---

@app.route('/track_line')
def track_line():
    line_number = request.args.get('line_number')
    if not line_number:
        return jsonify({"error": "Missing line_number"}), 400
    # --- SHAPE LOGIC FROM ODDIOODDIO ---
    # Try direct lookup
    paths = line_paths.get(line_number, [])
    # If not found, try to match by short_name (e.g. T3, T9)
    if not paths:
        # Try to find a route_id whose short_name matches line_number
        found_route_id = None
        for r_id, r_info in routes.items():
            if r_info.get('short_name') == line_number:
                found_route_id = r_id
                break
        if found_route_id and found_route_id in line_paths:
            paths = line_paths[found_route_id]
    vehicle_type = "BUS"
    if line_number.startswith('M'):
        vehicle_type = "METRO"
    elif line_number.startswith('T'):
        vehicle_type = "TRAM"
    line_info = line_stations_memory.get(line_number)
    line_stops = []
    actual_station_count = 0
    if line_info:
        line_stops = line_info.get('stations', [])
        actual_station_count = line_info.get('station_count', 0)
    return jsonify({
        "vehicle_type": vehicle_type,
        "paths": paths,
        "path_lengths": [len(p) for p in paths],
        "actual_station_count": actual_station_count,
        "line_stops": line_stops
    })

# Main GTFS loading logic at startup: ONLY LOAD FROM JSONS
try:
    print("Attempting to load GTFS data from cache JSON...")
    with open('gtfs_cache.json', 'r') as f:
        cached_data = json.load(f)
        line_paths = cached_data.get('line_paths', {})
        station_lines = cached_data.get('station_lines', {})
    print(f"Loaded {len(line_paths)} line paths and {len(station_lines)} station lines from cache JSON.")
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Error loading GTFS cache ({e}). Exiting...")
    raise

# Load line stations memory
try:
    print("Attempting to load line stations memory from FINALDEMO.json...")
    with open('FINALDEMO.json', 'r', encoding='utf-8') as f:
        line_stations_memory = json.load(f)
    print(f"Loaded stations memory for {len(line_stations_memory)} line entries from FINALDEMO.json.")
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Error loading stations memory from FINALDEMO.json ({e}). Exiting...")
    raise

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
    "Cookie": "_ga=GA1.1.277381945.1749850577; _ga_5W1ZB23GRH=GS2.1.s1749850577$o1$g0$t1749850580$j57$l0$h0; dtCookie9205gfup=v_4_srv_4_sn_7B1A6E823D9725BDCEB469D8E5ACABA0_perc_100000_ol_0_mul_1_app-3Aea7c4b59f27d43eb_0_rcs-3Acss_0; TS01ac3475=0199b2c74aa0ce7c7fd55f6c7442488b938c1ee7c44d85c464b46c88ed160742cc6ce5ef398f536a587fb9ac2732c9568f7851f6c0748983876c576ae090b2242d8ed089f7; _ga=GA1.1.277381945.1749850577; _gid=GA1.1.1209712740.1749862760; _gat=1; _ga_RD7BG8RLV0=GS2.1.s1749862759$o1$g1$t1749862812$j7$l0$h0"
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
        if wait_message is None:
            return None
        if wait_message.lower() == "in arrivo":
            return 0
        if "min" in wait_message.lower():
            return int(wait_message.split()[0])
        return None
    except:
        return None

# --- DEMO VEHICLE STATE ---
# For demo: keep a simple in-memory state for each line's vehicle positions
vehicle_demo_state = {}

# --- DEMO: Fake wait time generator ---
def fake_wait_time():
    # Random wait time between 0 and 5 minutes
    return random.choice([0, 1, 2, 3, 4, 5])

# --- DEMO: Fake vehicle movement ---
def get_demo_vehicle_positions(line_number, stops_data):
    # Each vehicle is just an index along the stops list
    if not stops_data:
        return []
    # For demo, 6 vehicles per line
    num_vehicles = 6
    key = str(line_number)
    if key not in vehicle_demo_state:
        # Start vehicles at random positions
        vehicle_demo_state[key] = [random.randint(0, len(stops_data)-1) for _ in range(num_vehicles)]
    else:
        # Move each vehicle forward by 1 (loop around)
        vehicle_demo_state[key] = [(pos+1)%len(stops_data) for pos in vehicle_demo_state[key]]
    vehicles = []
    for idx, pos in enumerate(vehicle_demo_state[key]):
        stop = stops_data[pos]
        vehicles.append({
            'vehicle_id': f'{key}_demo_{idx}',
            'current_stop_index': pos,
            'lat': stop.get('lat', stop.get('Y', 0)),
            'lon': stop.get('lon', stop.get('X', 0)),
            'next_stop_index': (pos+1)%len(stops_data),
            'wait_time': fake_wait_time(),
        })
    return vehicles

# --- OVERRIDE ENDPOINTS FOR DEMO ---
@app.route('/get_line_vehicle_data')
def get_line_vehicle_data():
    import random
    line_number = request.args.get('line_number')
    if not line_number:
        return jsonify({"error": "Missing line_number"}), 400
    print(f"\n=== DEMO: Fetching vehicle data for line {line_number} ===")
    # Get stations for this line from our pre-processed data
    line_info = line_stations_memory.get(line_number)
    line_stops_with_wait_times = []
    vehicles = []
    if line_info:
        stops_data = line_info.get('stations', [])
        # Fake wait times for each stop
        for stop in stops_data:
            line_stops_with_wait_times.append({
                **stop,
                'wait_time': fake_wait_time(),
                'raw_message': f"{fake_wait_time()} min"
            })
        # --- VEHICLE CREATION LOGIC (copied from oddiooddio style) ---
        # For demo: spawn 2 vehicles per line, moving along the stops
        num_vehicles = 2
        key = str(line_number)
        if key not in vehicle_demo_state:
            vehicle_demo_state[key] = [random.randint(0, len(stops_data)-1) for _ in range(num_vehicles)]
        else:
            vehicle_demo_state[key] = [(pos+1)%len(stops_data) for pos in vehicle_demo_state[key]]
        for idx, pos in enumerate(vehicle_demo_state[key]):
            stop = stops_data[pos]
            vehicles.append({
                'id': f'{key}_demo_{idx}',
                'lat': stop.get('lat', stop.get('Y', 0)),
                'lon': stop.get('lon', stop.get('X', 0)),
                'stop_name': stop.get('name', f'Stop {pos}'),
                'stop_id': stop.get('id', f'{pos}'),
                'wait_time': fake_wait_time(),
                'raw_message': f"{fake_wait_time()} min"
            })
    print(f"\nReturning {len(vehicles)} vehicles and {len(line_stops_with_wait_times)} stops with wait times")
    if vehicles:
        print("\nSample vehicle:", vehicles[0])
    return jsonify({
        "vehicles": vehicles,
        "line_stops_with_wait_times": line_stops_with_wait_times,
        "update_interval": 2000
    })

@app.route('/wait_time')
def wait_time():
    stop_id = request.args.get('stop_id')
    if not stop_id:
        return jsonify({"error": "Missing stop_id"}), 400
    # Demo: just return a random wait time
    return jsonify({"wait_times": [{"stop_id": stop_id, "wait_time": fake_wait_time()}]})

@app.route('/station_lines')
def get_station_lines():
    stop_id = request.args.get('stop_id')
    if not stop_id:
        return jsonify({"error": "Missing stop_id"}), 400
    
    lines = station_lines.get(stop_id, [])
    return jsonify({"lines": lines})

@app.route('/')
def index():
    return render_template_string(r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>Milan Stops Map</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.3/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
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
  .help-text {
    font-size: 0.8em;
    color: #666;
    margin-left: 10px;
  }
  .vehicle-icon-rotatable {
    transition: transform 0.2s linear;
  }
</style>
</head>
<body>
<h2>Milan Stops Map - DEMO VERSION (T3 and T9 only)</h2>
<div id="map"></div>
<div id="tracking-controls">
  <input type="text" id="line-input" placeholder="Enter line number (T3 or T9)">
  <button onclick="trackLine()">Track Line</button>
  <button onclick="resetMap()">Reset Map</button>
  <span id="tracking-status"></span>
  <div class="help-text">DEMO: Only T3 and T9 are available for tracking. This DEMO is supposed to show how the system works, to see all unctionalities and features, see the Video Showcase on the project page.</div>
</div>
<script>
const DEMO_LINES = ["T3", "T9"];
const map = L.map('map').setView([45.4642, 9.1900], 12);
let allMarkers = L.markerClusterGroup();
let isTracking = false;
let demoVehicleMarker = null;
let demoAnimationFrame = null;
let demoCurrentStopIdx = 0;
let demoLineStops = [];
let demoLineColor = "#00FFFF";
let demoLineLayer = null;
let demoCurrentPolyline = [];
let redBlipMarker = null; // Add this global variable to track the red blip

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
}).addTo(map);

// Add all stops as background markers
const stops = {{ stops|tojson }};
stops.forEach(stop => {
  const marker = L.marker([stop.lat, stop.lon]);
  marker.bindPopup(`${stop.name}`);
  allMarkers.addLayer(marker);
});
map.addLayer(allMarkers);

let currentDemoLineNumber = null; // Store the current demo line number globally

function trackLine() {
  const lineNumber = document.getElementById('line-input').value.trim().toUpperCase();
  if (!DEMO_LINES.includes(lineNumber)) {
    alert('Demo only supports T3 and T9');
    return;
  }
  currentDemoLineNumber = lineNumber; // Set the global line number
  clearTracking();
  map.removeLayer(allMarkers);
  isTracking = true;
  document.getElementById('tracking-status').textContent = `Tracking line ${lineNumber}`;
  fetch(`/track_line?line_number=${lineNumber}`)
    .then(response => response.json())
    .then(data => {
      demoLineStops = data.line_stops;
      demoLineColor = "#00FFFF";
      if (demoLineLayer) {
        map.removeLayer(demoLineLayer);
        demoLineLayer = null;
      }
      demoLineLayer = L.featureGroup();
      // Draw stops
      demoLineStops.forEach(stop => {
        const marker = L.circleMarker([stop.lat, stop.lon], {
          radius: 8,
          fillColor: demoLineColor,
          color: '#fff',
          weight: 2,
          opacity: 1,
          fillOpacity: 0.9
        }).bindPopup(stop.name);
        demoLineLayer.addLayer(marker);
      });
      // Draw GTFS shape(s) as the main line (instead of stop-to-stop straight line)
      demoCurrentPolyline = [];
      let shapeBounds = null;
      if (data.paths && data.paths.length > 0) {
        data.paths.forEach(path => {
          if (path.length > 1) {
            const shapeCoords = path.map(pt => [pt.Y, pt.X]);
            const shapeLine = L.polyline(shapeCoords, {
              color: demoLineColor,
              weight: 8,
              opacity: 0.8
            });
            demoLineLayer.addLayer(shapeLine);
            if (!shapeBounds) {
              shapeBounds = L.latLngBounds(shapeCoords);
            } else {
              shapeBounds.extend(L.latLngBounds(shapeCoords));
            }
            // Use the first shape as the animation path
            if (demoCurrentPolyline.length === 0) {
              demoCurrentPolyline = shapeCoords;
            }
          }
        });
      }
      demoLineLayer.addTo(map);
      // --- FIX ZOOM: Fit to bounds with reasonable padding and max zoom ---
      if (shapeBounds) {
        map.fitBounds(shapeBounds, {padding: [60, 60], maxZoom: 14});
      }
      // Start animation
      animateDemoVehicle();
    });
}

function getDirectionFromBearing(bearing) {
  // Normalize bearing to 0-360
  bearing = ((bearing % 360) + 360) % 360;
  // Calculate distance to each cardinal direction
  const distanceToNorth = Math.min(bearing, 360 - bearing); // Distance to 0°
  const distanceToEast = Math.abs(bearing - 90); // Distance to 90°
  const distanceToSouth = Math.abs(bearing - 180); // Distance to 180°
  const distanceToWest = Math.abs(bearing - 270); // Distance to 270°
  // Find the minimum distance
  const minDistance = Math.min(distanceToNorth, distanceToEast, distanceToSouth, distanceToWest);
  if (minDistance === distanceToNorth) {
    return 'U'; // Up/North (0°)
  } else if (minDistance === distanceToEast) {
    return 'R'; // Right/East (90°)
  } else if (minDistance === distanceToSouth) {
    return 'D'; // Down/South (180°)
  } else {
    return 'L'; // Left/West (270°)
  }
}

function getVehicleIcon(lineNumber, bearing) {
  const direction = getDirectionFromBearing(bearing);
  let basePath = '/static/vehicle_images/';
  let backgroundColor = '#FF4444'; // Default bright red
  if (lineNumber.startsWith('M')) {
      basePath += 'METRO/';
      backgroundColor = '#FF0000'; // Bright red for metro
  } else if (lineNumber.startsWith('T')) {
      basePath += 'TRAM/';
      backgroundColor = '#00FF00'; // Bright green for tram
  } else if (lineNumber.startsWith('B')) {
      basePath += 'BUS/';
      backgroundColor = '#0066FF'; // Bright blue for bus
  } else {
      // Return a simple fallback icon
      return L.divIcon({
          className: 'simple-vehicle-marker',
          html: '🚌',
          iconSize: [20, 20],
          iconAnchor: [10, 10]
      });
  }
  const icon = L.divIcon({
      className: 'vehicle-icon-with-background',
      html: `
          <div style="
              position: relative;
              width: 32px;
              height: 32px;
          ">
              <div style="
                  position: absolute;
                  top: 0;
                  left: 0;
                  width: 32px;
                  height: 32px;
                  background-color: ${backgroundColor};
                  border-radius: 50%;
                  border: 2px solid white;
              "></div>
              <img src="${basePath + direction + '.png'}" style="
                  position: absolute;
                  top: 2px;
                  left: 2px;
                  width: 28px;
                  height: 28px;
                  z-index: 1;
              " onerror="console.error('Failed to load vehicle image: ${basePath + direction + '.png'}')">
          </div>
      `,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      popupAnchor: [0, -16]
  });
  return icon;
}

function animateDemoVehicle() {
  let demoLineNumber = currentDemoLineNumber || 'B90'; // fallback if not set
  // --- SPAWN MULTIPLE VEHICLES ---
  // Remove previous vehicle markers if any
  if (window.demoVehicleMarkers && Array.isArray(window.demoVehicleMarkers)) {
    window.demoVehicleMarkers.forEach(m => map.removeLayer(m));
  }
  window.demoVehicleMarkers = [];
  if (demoAnimationFrame) {
    cancelAnimationFrame(demoAnimationFrame);
    demoAnimationFrame = null;
  }
  if (demoVehicleMarker) {
    map.removeLayer(demoVehicleMarker);
    demoVehicleMarker = null;
  }
  if (redBlipMarker) {
    map.removeLayer(redBlipMarker);
    redBlipMarker = null;
  }
  if (!demoCurrentPolyline || demoCurrentPolyline.length < 2) return;

  // Helper: Haversine distance in meters
  function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371000; // meters
    const toRad = x => x * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
  }

  // Helper: Calculate heading in degrees from point a to b
  function getHeading(lat1, lon1, lat2, lon2) {
    const toRad = x => x * Math.PI / 180;
    const toDeg = x => x * 180 / Math.PI;
    const dLon = toRad(lon2 - lon1);
    const y = Math.sin(dLon) * Math.cos(toRad(lat2));
    const x = Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) - Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(dLon);
    let brng = Math.atan2(y, x);
    brng = toDeg(brng);
    return (brng + 360) % 360;
  }

  // Find indices in demoCurrentPolyline that are closest to stops
  let stopIndices = [];
  if (demoLineStops && demoLineStops.length > 0) {
    demoLineStops.forEach(stop => {
      let minIdx = 0;
      let minDist = Infinity;
      demoCurrentPolyline.forEach((pt, idx) => {
        const d = Math.abs(pt[0] - stop.lat) + Math.abs(pt[1] - stop.lon);
        if (d < minDist) {
          minDist = d;
          minIdx = idx;
        }
      });
      stopIndices.push(minIdx);
    });
  }

  // Build a list of stop-to-stop segments (each is a list of polyline indices)
  let stopSegments = [];
  for (let i = 0; i < stopIndices.length - 1; i++) {
    stopSegments.push({
      fromIdx: stopIndices[i],
      toIdx: stopIndices[i+1],
      fromStop: demoLineStops[i],
      toStop: demoLineStops[i+1]
    });
  }

  // Precompute distances for each segment
  stopSegments.forEach(seg => {
    let dist = 0;
    for (let j = seg.fromIdx; j < seg.toIdx; j++) {
      const a = demoCurrentPolyline[j];
      const b = demoCurrentPolyline[j+1];
      dist += haversine(a[0], a[1], b[0], b[1]);
    }
    seg.distance = dist;
  });

  // Animation parameters
  const CRUISE_KMH = 100;
  const CRUISE_MPS = CRUISE_KMH * 1000 / 3600;
  const STOP_WAIT_MIN = 13000;
  const STOP_WAIT_MAX = 15000;

  let segmentIdx = 0; // which stop-to-stop segment
  let progress = 0; // 0=start, 1=end
  let waiting = false;
  let waitTimeout = null;
  let approachingStopIdx = 1; // index in demoLineStops for the next stop (red blip)

  // --- FIX: Initialize vehicleStates before step() is called ---
  const numVehicles = 4; // Always 4 vehicles
  let vehicleStates = [];
  for (let i = 0; i < numVehicles; i++) {
    // Randomize direction: true = forward, false = backward
    const forward = Math.random() < 0.5;
    // Pick a random segment and random progress along that segment
    const segIdx = Math.floor(Math.random() * stopSegments.length);
    const prog = Math.random() * 0.8; // don't start too close to the end
    vehicleStates.push({
      segmentIdx: segIdx,
      progress: prog,
      waiting: false,
      lastTimestamp: null,
      marker: null,
      redBlip: null, // Each vehicle gets its own red blip marker
      forward: forward // Direction flag
    });
  }

  // In updateRedBlips, track all red blips for later cleanup
  function updateRedBlips() {
    if (!window._lastRedBlips) window._lastRedBlips = [];
    window._lastRedBlips.forEach(blip => { if (blip) map.removeLayer(blip); });
    window._lastRedBlips = [];
    vehicleStates.forEach((state, idx) => {
      const seg = stopSegments[state.segmentIdx];
      if (!seg) return;
      // Determine which stop is being approached based on direction
      let approachingStop = state.forward ? seg.toStop : seg.fromStop;
      // Only show red blip if vehicle is approaching (not waiting and not at the end)
      if (!state.waiting && state.progress < 1) {
        if (!state.redBlip) {
          state.redBlip = L.circleMarker([approachingStop.lat, approachingStop.lon], {
            radius: 8,
            fillColor: '#FF4444',
            color: '#fff',
            weight: 3,
            opacity: 1,
            fillOpacity: 1
          }).bindPopup('Approaching Station: ' + approachingStop.name).addTo(map);
        } else {
          state.redBlip.setLatLng([approachingStop.lat, approachingStop.lon]);
          state.redBlip.setPopupContent('Approaching Station: ' + approachingStop.name);
          state.redBlip.addTo(map);
        }
        window._lastRedBlips.push(state.redBlip);
      } else {
        // Remove red blip if not approaching
        if (state.redBlip) {
          map.removeLayer(state.redBlip);
          state.redBlip = null;
        }
      }
    });
  }

  updateRedBlips();

  let lastTimestamp = null;
  let stoppedAtStop = false;
  function step(now) {
    vehicleStates.forEach((state, idx) => {
      let segmentIdx = state.segmentIdx;
      let progress = state.progress;
      let waiting = state.waiting;
      let lastTimestamp = state.lastTimestamp;
      let forward = state.forward;
      // --- Direction logic ---
      // If going backward, reverse segment and progress
      let seg = stopSegments[segmentIdx];
      let segFromIdx = seg.fromIdx;
      let segToIdx = seg.toIdx;
      let segFromStop = seg.fromStop;
      let segToStop = seg.toStop;
      if (!forward) {
        // Swap from/to for backward direction
        [segFromIdx, segToIdx] = [segToIdx, segFromIdx];
        [segFromStop, segToStop] = [segToStop, segFromStop];
      }
      if (segmentIdx >= stopSegments.length) {
        segmentIdx = 0;
        progress = 0;
      }
      if (!seg) return;
      if (waiting) return;
      if (!lastTimestamp) lastTimestamp = now;
      let dt = (now - lastTimestamp) / 1000;
      lastTimestamp = now;
      let v = CRUISE_MPS * Math.sin(Math.PI * progress);
      if (v < 0.1) v = 0.1;
      let ds = v * dt;
      let totalDist = seg.distance;
      let sNow = totalDist * (1 - Math.cos(Math.PI * progress)) / 2;
      let sNext = sNow + ds;
      let nextProgress = Math.acos(Math.max(-1, Math.min(1, 1 - 2 * sNext / totalDist))) / Math.PI;
      if (isNaN(nextProgress) || sNext >= totalDist) {
        progress = 1;
      } else {
        progress = nextProgress;
      }
      let traversed = 0;
      let pos = demoCurrentPolyline[segFromIdx];
      let heading = 0;
      if (forward) {
        for (let j = segFromIdx; j < segToIdx; j++) {
          const a = demoCurrentPolyline[j];
          const b = demoCurrentPolyline[j+1];
          const d = haversine(a[0], a[1], b[0], b[1]);
          if (traversed + d >= sNow) {
            const frac = (sNow - traversed) / d;
            pos = [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac];
            heading = getHeading(a[0], a[1], b[0], b[1]);
            break;
          }
          traversed += d;
        }
      } else {
        for (let j = segFromIdx; j > segToIdx; j--) {
          const a = demoCurrentPolyline[j];
          const b = demoCurrentPolyline[j-1];
          const d = haversine(a[0], a[1], b[0], b[1]);
          if (traversed + d >= sNow) {
            const frac = (sNow - traversed) / d;
            pos = [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac];
            heading = getHeading(a[0], a[1], b[0], b[1]);
            break;
          }
          traversed += d;
        }
      }
      // Place/rotate icon marker
      if (!state.marker) {
        const vehicleIcon = getVehicleIcon(demoLineNumber, heading);
        const marker = L.marker(pos, {
          icon: vehicleIcon,
          interactive: true
        }).addTo(map);
        marker.bindPopup('DEMO VEHICLE');
        marker.on('click', function() {
          if (state.waiting) {
            this.setPopupContent('Arrived at ' + segToStop.name + ', Boarding Passengers');
          } else {
            this.setPopupContent('Approaching ' + segToStop.name);
          }
        });
        state.marker = marker;
        window.demoVehicleMarkers.push(marker);
      } else {
        state.marker.setLatLng(pos);
        // Update popup content if open
        if (state.marker.isPopupOpen()) {
          if (state.waiting) {
            state.marker.setPopupContent('Arrived at ' + segToStop.name + ', Boarding Passengers');
          } else {
            state.marker.setPopupContent('Approaching ' + segToStop.name);
          }
        }
      }
      // --- RED BLIP LOGIC PER VEHICLE ---
      updateRedBlips();
      // If arrived at stop
      if (progress >= 1) {
        state.waiting = true;
        state.marker.setPopupContent('Arrived at ' + segToStop.name + ', Boarding Passengers');
        // Remove red blip when stopped
        if (state.redBlip) {
          map.removeLayer(state.redBlip);
          state.redBlip = null;
        }
        // Wait at stop
        const waitMs = STOP_WAIT_MIN + Math.floor(Math.random() * (STOP_WAIT_MAX - STOP_WAIT_MIN));
        setTimeout(() => {
          // Before moving again, update the icon to the new direction
          if (forward) {
            state.segmentIdx = segmentIdx + 1;
            if (state.segmentIdx >= stopSegments.length) state.segmentIdx = 0;
          } else {
            state.segmentIdx = segmentIdx - 1;
            if (state.segmentIdx < 0) state.segmentIdx = stopSegments.length - 1;
          }
          state.progress = 0;
          state.lastTimestamp = null;
          state.waiting = false;
          // Calculate new heading for next segment (if exists)
          const nextSeg = stopSegments[state.segmentIdx];
          if (nextSeg) {
            let a, b;
            if (state.forward) {
              a = demoCurrentPolyline[nextSeg.fromIdx];
              b = demoCurrentPolyline[nextSeg.fromIdx + 1];
            } else {
              a = demoCurrentPolyline[nextSeg.toIdx];
              b = demoCurrentPolyline[nextSeg.toIdx - 1];
            }
            const newHeading = getHeading(a[0], a[1], b[0], b[1]);
            const newIcon = getVehicleIcon(demoLineNumber, newHeading);
            state.marker.setIcon(newIcon);
          }
          // After waiting, update red blips
          updateRedBlips();
        }, waitMs);
        return;
      }
      // Show "Approaching" popup if open
      if (state.marker.isPopupOpen() && !state.waiting) {
        state.marker.setPopupContent('Approaching ' + segToStop.name);
      }
      // Save state
      state.segmentIdx = segmentIdx;
      state.progress = progress;
      state.lastTimestamp = lastTimestamp;
    });
    updateRedBlips(); // Update red blips every frame
    demoAnimationFrame = requestAnimationFrame(step);
  }
  demoAnimationFrame = requestAnimationFrame(step);
}

function resetMap() {
  clearTracking();
  document.getElementById('line-input').value = '';
  document.getElementById('tracking-status').textContent = '';
}

function clearTracking() {
  if (demoVehicleMarker) {
    map.removeLayer(demoVehicleMarker);
    demoVehicleMarker = null;
  }
  if (demoAnimationFrame) {
    cancelAnimationFrame(demoAnimationFrame);
    demoAnimationFrame = null;
  }
  if (demoLineLayer) {
    map.removeLayer(demoLineLayer);
    demoLineLayer = null;
  }
  // Remove all vehicle markers if present
  if (window.demoVehicleMarkers && Array.isArray(window.demoVehicleMarkers)) {
    window.demoVehicleMarkers.forEach(m => {
      // Remove marker
      map.removeLayer(m);
    });
    window.demoVehicleMarkers = [];
  }
  // Remove all red blip markers from previous animation (vehicleStates)
  if (typeof window._lastRedBlips === 'object' && Array.isArray(window._lastRedBlips)) {
    window._lastRedBlips.forEach(blip => {
      if (blip) map.removeLayer(blip);
    });
    window._lastRedBlips = [];
  }
  // Remove all red blip markers from vehicleStates (if any)
  if (typeof vehicleStates !== 'undefined' && Array.isArray(vehicleStates)) {
    vehicleStates.forEach(state => {
      if (state.redBlip) {
        map.removeLayer(state.redBlip);
        state.redBlip = null;
      }
    });
  }
  // Also remove any stray redBlipMarker (legacy global)
  if (typeof redBlipMarker !== 'undefined' && redBlipMarker) {
    map.removeLayer(redBlipMarker);
    redBlipMarker = null;
  }
  map.addLayer(allMarkers);
  isTracking = false;
}

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
    print("Starting server on port 8080...")
    app.run(debug=True, port=8080)

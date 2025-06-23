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
from concurrent.futures import ThreadPoolExecutor
import base64
from flask import send_from_directory

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

def _fetch_batch_wait_times_for_stops(stop_ids):
    """Fetch wait times for multiple stops concurrently to avoid rate limits"""
    def fetch_single_stop(stop_id):
        try:
            data = f"url=tpPortal%2Fgeodata%2Fpois%2Fstops%2F{stop_id}"
            response = requests.post(server_url, headers=HEADERS, data=data, timeout=5)
            print(f"Response from stop {stop_id}: {response.status_code}")
            if response.status_code == 200:
                json_data = response.json()
                lines = json_data.get("Lines", [])
                print(f"Got {len(lines)} lines for stop {stop_id}")
                return stop_id, lines
        except Exception as e:
            print(f"Error fetching wait time for stop {stop_id}: {e}")
        return stop_id, []
    
    # Use ThreadPoolExecutor for concurrent requests with reduced concurrency
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Process stop IDs in batches to avoid overwhelming the server
        batch_size = 10
        results = {}
        
        for i in range(0, len(stop_ids), batch_size):
            batch = stop_ids[i:i+batch_size]
            futures = [executor.submit(fetch_single_stop, stop_id) for stop_id in batch]
            
            for future in futures:
                try:
                    stop_id, lines_data = future.result(timeout=5)
                    results[stop_id] = lines_data
                except Exception as e:
                    print(f"Error processing batch result: {e}")
                    continue
        
        return results

def _fetch_raw_wait_times_for_stop(stop_id):
    data = f"url=tpPortal%2Fgeodata%2Fpois%2Fstops%2F{stop_id}"
    try:
        print(f"\n=== Raw ATM Proxy Request for Stop {stop_id} ===")
        print(f"URL: {server_url}")
        print(f"Data: {data}")
        print(f"Headers: {json.dumps(HEADERS, indent=2)}")
        
        response = requests.post(server_url, headers=HEADERS, data=data, timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Text (first 500 chars): {response.text[:500]}...")
        
        if response.status_code == 200:
            json_data = response.json()
            print(f"Parsed JSON (first 500 chars): {json.dumps(json_data, indent=2)[:500]}...")
            return json_data.get("Lines", [])
    except Exception as e:
        print(f"Error fetching raw wait time for stop {stop_id}: {e}")
        print(f"Full error details: {str(e)}")
    return []

def fetch_wait_times_for_line(stop_code, line_number):
    # This function is now used for single stop clicks in the frontend. It should only return the specific line's wait time.
    all_lines_data = _fetch_raw_wait_times_for_stop(stop_code)
    for line in all_lines_data:
        if str(line.get("BookletUrl2", "")) == str(line_number):
            wait_msg = line.get("WaitMessage", "No data")
            print(f"Found wait time for line {line_number} at stop {stop_code}: {wait_msg}")
            return parse_wait_time(wait_msg)
    print(f"No wait time data found for line {line_number} at stop {stop_code}.")
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
        # As a fallback, try to find a route_id that has this short_name
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

def normalize_line_number(line_number):
    # Remove any leading 'M', 'T', or 'B'
    if line_number and isinstance(line_number, str):
        return line_number.lstrip('MTB')
    return line_number

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
        
        response = requests.post(server_url, headers=HEADERS, data=data, timeout=5)
        print(f"\n=== Response Details ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Text: {response.text[:1000]}")
        
        if response.status_code == 200:
            json_data = response.json()
            lines = json_data.get("Lines", [])
            wait_times = []
            
            for line in lines:
                wait_msg = line.get("WaitMessage", "")
                wait_time = 0 if (wait_msg is not None and wait_msg.lower() == "in arrivo") else parse_wait_time(wait_msg)
                wait_times.append({
                    "line_number": line.get("BookletUrl2", ""),
                    "wait_time": wait_time,
                    "raw_message": wait_msg
                })
            
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

@app.route('/get_line_vehicle_data')
def get_line_vehicle_data():
    line_number = request.args.get('line_number')
    if not line_number:
        return jsonify({"error": "Missing line_number"}), 400
    
    print(f"\n=== Fetching vehicle data for line {line_number} ===")
    
    # Get stations for this line from our pre-processed data
    line_info = line_stations_memory.get(line_number)
    line_stops_with_wait_times = []
    vehicles = []
    
    if line_info:
        stops_data = line_info.get('stations', [])
        stop_ids = [stop['id'] for stop in stops_data]
        
        # Create a mapping of stop IDs to their sequence in the line
        stop_sequence = {stop['id']: idx for idx, stop in enumerate(stops_data)}
        
        # Batch fetch wait times for all stops
        print(f"Fetching wait times for {len(stop_ids)} stops...")
        wait_times_data = _fetch_batch_wait_times_for_stops(stop_ids)
        print(f"Got wait times data for {len(wait_times_data)} stops")
        
        # Process wait times and create vehicle positions
        processed_times = []
        all_wait_times = []  # For debugging
        
        # First pass: collect all wait times
        for stop in stops_data:
            stop_id = stop['id']
            lines_data = wait_times_data.get(stop_id, [])
            
            # Find wait time for this line
            for line in lines_data:
                booklet_url2 = str(line.get("BookletUrl2", ""))
                if booklet_url2 == str(line_number) or booklet_url2 == normalize_line_number(line_number):
                    wait_msg = line.get("WaitMessage")
                    wait_time = parse_wait_time(wait_msg)
                    
                    if wait_time is not None:  # Only process stops with valid wait times
                        processed_times.append({
                            'stop_id': stop_id,
                            'stop_name': stop['name'],
                            'lat': float(stop['lat']),
                            'lon': float(stop['lon']),
                            'wait_time': wait_time,
                            'raw_message': wait_msg or "No data",
                            'sequence': stop_sequence[stop_id]  # Add sequence number
                        })
                    
                    all_wait_times.append(f"Stop {stop['name']} (seq {stop_sequence[stop_id]}): {wait_msg or 'No data'} (parsed as {wait_time} min)")
                    
                    # Add to stops list regardless of wait time
                    line_stops_with_wait_times.append({
                        'stop_id': stop_id,
                        'name': stop['name'],
                        'lat': float(stop['lat']),
                        'lon': float(stop['lon']),
                        'wait_message': wait_msg or "No data",
                        'sequence': stop_sequence[stop_id]
                    })
                    break

        # Print all wait times for debugging
        print("\nAll wait times received:")
        for wait_time in all_wait_times:
            print(wait_time)
        
        # Sort by wait time to process closest vehicles first
        processed_times.sort(key=lambda x: x['wait_time'])
        print(f"\nFound {len(processed_times)} stops with valid wait times")

        # Create vehicles for all stops with valid wait times (not just "in arrivo")
        # This is the key fix - we need to create vehicles for all stops with wait times
        # Create vehicles ONLY for stops with 0 minute wait times ("in arrivo")
        for time_data in processed_times:
            # Only create vehicles for arriving vehicles (wait_time == 0)
            if time_data['wait_time'] == 0:
                # Create a unique vehicle ID for each stop
                vehicle_id = f"{line_number}_{time_data['stop_id']}_{time_data['sequence']}"
                
                vehicles.append({
                    'id': vehicle_id,  # Add unique ID
                    'lat': time_data['lat'],
                    'lon': time_data['lon'],
                    'stop_name': time_data['stop_name'],
                    'line_number': str(line_number),
                    'wait_time': time_data['wait_time'],
                    'raw_message': time_data['raw_message'],
                    'sequence': time_data['sequence'],
                    'next_stops': []  # Optionally, you can add next stops if you want
                })

    print(f"\nReturning {len(vehicles)} vehicles and {len(line_stops_with_wait_times)} stops with wait times")
    if vehicles:
        print("\nVehicle wait times:")
        for vehicle in vehicles:
            print(f"Vehicle {vehicle['id']} at {vehicle['stop_name']}: {vehicle['raw_message']} ({vehicle['wait_time']} min)")
    
    print("\nSample vehicle:", vehicles[0] if vehicles else "No vehicles")
    return jsonify({
        "vehicles": vehicles,
        "line_stops_with_wait_times": line_stops_with_wait_times,
        "update_interval": 60000
    })

@app.route('/')
def index():
    return render_template_string(r"""
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
    background-color: #000000;
    border-radius: 50%;
    border: 2px solid white;
    width: 25px !important;
    height: 25px !important;
    margin-left: -17.5px !important;
    margin-top: -17.5px !important;
    display: flex;
    justify-content: center;
    align-items: center;
    font-size: 20px;
    color: white;
    font-weight: bold;
  }
  @keyframes pulse {
    0% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.2); opacity: 0.8; }
    100% { transform: scale(1); opacity: 1; }
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
    <button id="zoom-to-vehicle" onclick="zoomToVehicle()" style="display: none;">Take me to vehicle</button>
    <span id="tracking-status"></span>
  </div>
  <div class="help-text">
    Prefix with M for Metro, T for Tram, B for Bus (e.g., M3, T3, B90)
  </div>
</div>

<script>
  const stops = {{ stops|tojson }};
  const map = L.map('map').setView([45.4642, 9.1900], 12);
  let liveVehicleMarkersLayer = null;
  let highlightedStops = [];
  let trackingInterval = null;
  let animationFrameId = null; // For smooth animation
  let allMarkers = L.markerClusterGroup();
  let filteredMarkers = L.markerClusterGroup();
  let isTracking = false;
  let currentLineLayer = null; // Store the current line layer
  let currentLinePaths = []; // To store paths for vehicle simulation
  let currentVehicleType = ''; // To store vehicle type for icon

  // Animation system variables - FIXED: Use Map instead of object for better key handling
  let vehicleAnimations = new Map(); // Store animation data for each vehicle
  let lastUpdateTime = Date.now();

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
  }).addTo(map);

  function parseWaitMinutes(waitMessage) {
    console.log(`🔍 Parsing wait message: "${waitMessage}"`);
    
    if (waitMessage === "in arrivo") {
        console.log(`  ✅ Parsed as: 0 (arriving)`);
        return 0;
    } else if (waitMessage === "ricalcolo") {
        console.log(`  ✅ Parsed as: -1 (recalculating)`);
        return -1;
    } else if (waitMessage === null || waitMessage === "no serv." || waitMessage === "No data" || waitMessage === "Error") {
        console.log(`  ✅ Parsed as: Infinity (no service)`);
        return Infinity;
    } else {
        const match = waitMessage.match(/(\d+)\s*min/i);
        if (match) {
            const minutes = parseInt(match[1], 10);
            console.log(`  ✅ Parsed as: ${minutes} minutes`);
            return minutes;
        }
    }
    
    console.log(`  ⚠️ Parsed as: Infinity (unparseable)`);
    return Infinity;
  }

  // Updated distance calculation based on wait times and vehicle type
  function calculateVehicleDistance(waitMessage, vehicleType) {
      const baseDistance = 50; // x: Base safety distance in meters
      
      // Speed-based distances per minute
      let metersPerMinute;
      if (vehicleType === "METRO") {
          metersPerMinute = 583; // ~35 km/h average
      } else if (vehicleType === "TRAM") {
          metersPerMinute = 417; // ~25 km/h average  
      } else { // BUS
          metersPerMinute = 333; // ~20 km/h average
      }
      
      if (waitMessage === "in arrivo") {
          return baseDistance; // x meters behind
      } else if (waitMessage === "ricalcolo") {
          return 0; // On the station
      } else if (waitMessage && waitMessage.includes("min")) {
          const minutes = parseInt(waitMessage.match(/(\d+)/)[1]);
          return baseDistance + (minutes * metersPerMinute); // x + (minutes * speed)
      }
      
      return baseDistance; // Default fallback
  }
                                  
  // Helper function to get direction from bearing angle (closest to cardinal directions)
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

  // Helper function to get vehicle icon based on line number prefix and direction
  function getVehicleIcon(lineNumber, bearing) {
    console.log(`🎨 Creating vehicle icon for line: ${lineNumber}, bearing: ${bearing}°`);
    
    const direction = getDirectionFromBearing(bearing);
    console.log(`  🧭 Direction: ${direction}`);
    
    let basePath = '/static/vehicle_images/';
    let backgroundColor = '#FF4444'; // Default bright red
    
    if (lineNumber.startsWith('M')) {
        basePath += 'METRO/';
        backgroundColor = '#FF0000'; // Bright red for metro
        console.log(`  🚇 Metro icon: ${basePath}${direction}.png`);
    } else if (lineNumber.startsWith('T')) {
        basePath += 'TRAM/';
        backgroundColor = '#00FF00'; // Bright green for tram
        console.log(`  🚋 Tram icon: ${basePath}${direction}.png`);
    } else if (lineNumber.startsWith('B')) {
        basePath += 'BUS/';
        backgroundColor = '#0066FF'; // Bright blue for bus
        console.log(`  🚌 Bus icon: ${basePath}${direction}.png`);
    } else {
        console.warn(`  ⚠️ No vehicle type determined for line: ${lineNumber}`);
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
    
    console.log(`  ✅ Vehicle icon created`);
    return icon;
  }

  // Helper for linear interpolation
  function lerp(a, b, t) {
      return a + (b - a) * t;
  }

  // FIXED: Animation frame function - vehicles move once then stop
function animateVehicles() {
    const currentTime = Date.now();
    const deltaTime = currentTime - lastUpdateTime;
    lastUpdateTime = currentTime;
    
    let activeAnimations = 0;
    
    // Process each vehicle animation
    vehicleAnimations.forEach((animData, vehicleId) => {
        if (animData.isAnimating && animData.polyline && animData.marker) {
            const elapsed = currentTime - animData.startTime;
            const progress = Math.min(elapsed / animData.duration, 1);
            const easedProgress = easeInOutCubic(progress);
            
            // Get interpolated position along the polyline
            const [lat, lon] = interpolateOnPolyline(animData.polyline, easedProgress, map);
            
            // Update marker position
            animData.marker.setLatLng([lat, lon]);
            
            // If animation is complete, STOP (don't loop)
            if (progress >= 1) {
                console.log(`🏁 Vehicle ${vehicleId} reached destination: ${animData.stopName}`);
                animData.isAnimating = false; // Stop the animation
                
                // Update popup to show "arrived" status
                const arrivedPopupContent = `🚌 Vehicle ${vehicleId}<br>📍 Arrived at: ${animData.stopName}<br>✅ Waiting for next update...`;
                animData.marker.bindPopup(arrivedPopupContent);
            } else {
                activeAnimations++;
            }
        }
    });
    
    // Continue animation loop only if we have active animations
    if (activeAnimations > 0) {
        animationFrameId = requestAnimationFrame(animateVehicles);
    } else {
        console.log('🛑 All vehicles have reached their destinations. Animation loop stopped.');
        animationFrameId = null;
    }
}

  // Easing function for smooth animation
  function easeInOutCubic(t) {
      return t < 0.5 ? 4 * t * t * t : (t - 1) * (2 * t - 2) * (2 * t - 2) + 1;
  }

  // Calculate bearing from vehicle to next stop for proper icon direction
  function calculateBearingToNextStop(vehiclePos, currentStop, allStops) {
      // Find next stop in sequence
      const currentIndex = allStops.findIndex(stop => stop.id === currentStop.id);
      const nextStop = allStops[(currentIndex + 1) % allStops.length];
      
      if (!nextStop) return 0;
      
      const lat1 = vehiclePos[0] * Math.PI / 180;
      const lon1 = vehiclePos[1] * Math.PI / 180;
      const lat2 = nextStop.lat * Math.PI / 180;
      const lon2 = nextStop.lon * Math.PI / 180;
      
      const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
      const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
      
      bearing = Math.atan2(y, x) * 180 / Math.PI;
      if (bearing < 0) bearing += 360;
      
      return bearing;
  }

  // Helper function to get point on polyline (simplified version)
  function getPointOnPolylineSimple(allPaths, targetLatLon, distanceBackMeters, mapInstance) {
      console.log('getPointOnPolylineSimple called with:');
      console.log('  targetLatLon:', targetLatLon);
      console.log('  distanceBackMeters:', distanceBackMeters);

      const targetLatLng = L.latLng(targetLatLon[0], targetLatLon[1]);
      console.log('  targetLatLng (Leaflet object):', targetLatLng);

      let closestPointOnLine = null;
      let closestSegmentStartIdx = -1;
      let closestPathIdx = -1;
      let closestK = 0; // Fraction along the segment

      let minDistance = Infinity;

      // Find the closest point on the entire set of polylines
      allPaths.forEach((pathPoints, pathIndex) => {
          if (pathPoints.length < 2) return;
          for (let i = 0; i < pathPoints.length - 1; i++) {
              const p1 = L.latLng(pathPoints[i].Y, pathPoints[i].X);
              const p2 = L.latLng(pathPoints[i+1].Y, pathPoints[i+1].X);

              const segmentVectorX = p2.lng - p1.lng;
              const segmentVectorY = p2.lat - p1.lat;
              const lineLengthSq = segmentVectorX * segmentVectorX + segmentVectorY * segmentVectorY;

              let k;
              if (lineLengthSq === 0) {
                  k = 0;
              } else {
                  k = ((targetLatLng.lng - p1.lng) * segmentVectorX + (targetLatLng.lat - p1.lat) * segmentVectorY) / lineLengthSq;
              }

              let projectedPoint;
              if (k < 0) {
                  projectedPoint = p1;
              } else if (k > 1) {
                  projectedPoint = p2;
              } else {
                  projectedPoint = L.latLng(p1.lat + k * segmentVectorY, p1.lng + k * segmentVectorX);
              }

              const dist = mapInstance.distance(targetLatLng, projectedPoint);

              if (dist < minDistance) {
                  minDistance = dist;
                  closestPointOnLine = projectedPoint;
                  closestSegmentStartIdx = i;
                  closestPathIdx = pathIndex;
                  closestK = k;
              }
          }
      });

      console.log('  minDistance to line:', minDistance);
      console.log('  closestPointOnLine (projection):', closestPointOnLine);
      console.log('  closestPathIdx:', closestPathIdx, 'closestSegmentStartIdx:', closestSegmentStartIdx);

      if (!closestPointOnLine || closestPathIdx === -1 || !allPaths[closestPathIdx]) {
          console.warn("No closest point found on polyline. Returning target location.");
          return targetLatLon; // Fallback if polyline is empty or invalid
      }
      
      const pathUsed = allPaths[closestPathIdx];
      let remainingDistance = distanceBackMeters;
      console.log('  Starting remainingDistance:', remainingDistance);

      // Iterate backwards from the closest segment on the identified path
      for (let i = closestSegmentStartIdx; i >= 0; i--) {
          const p1 = L.latLng(pathUsed[i].Y, pathUsed[i].X);
          const p2 = L.latLng(pathUsed[i+1].Y, pathUsed[i+1].X);
          const segmentLength = mapInstance.distance(p1, p2);
          console.log(`    Segment ${i}-${i+1} (${p1.lat.toFixed(4)},${p1.lng.toFixed(4)}) to (${p2.lat.toFixed(4)},${p2.lng.toFixed(4)}) length: ${segmentLength.toFixed(2)}m`);

          let distanceOnCurrentSegment;
          if (i === closestSegmentStartIdx) {
              // Distance from closestPointOnLine to p1 along the segment
              distanceOnCurrentSegment = mapInstance.distance(p1, closestPointOnLine);
              console.log(`      Current segment is closest segment. Distance from p1 to projected point: ${distanceOnCurrentSegment.toFixed(2)}m`);
          } else {
              // Full length of segment
              distanceOnCurrentSegment = segmentLength;
          }

          if (remainingDistance <= distanceOnCurrentSegment) {
              // The vehicle is on this segment
              let fraction;
              if (distanceOnCurrentSegment === 0) { // Avoid division by zero
                fraction = 0; // If segment has no length, just stay at p1
              } else {
                fraction = 1 - (remainingDistance / distanceOnCurrentSegment);
              }
              const newLat = p1.lat + fraction * (p2.lat - p1.lat);
              const newLon = p1.lng + fraction * (p2.lng - p1.lng);
              console.log(`    Vehicle found on segment ${i}-${i+1} at fraction ${fraction.toFixed(2)}. New position: [${newLat.toFixed(6)}, ${newLon.toFixed(6)}]`);
              return [newLat, newLon];
          } else {
              remainingDistance -= distanceOnCurrentSegment;
              console.log(`    Remaining distance after segment ${i+1}: ${remainingDistance.toFixed(2)}m`);
          }
      }

      // If we go past the start of the line, return the start point
      const startPoint = [pathUsed[0].Y, pathUsed[0].X];
      console.warn("  Went past start of line. Returning start point:", startPoint);
      return startPoint;
  }

  // Utility: Check if a point is on the polyline (within a small tolerance)
  function isPointOnPolyline(allPaths, point, mapInstance, toleranceMeters = 3) {
    const pt = L.latLng(point[0], point[1]);
    for (const pathPoints of allPaths) {
      for (let i = 0; i < pathPoints.length - 1; i++) {
        const p1 = L.latLng(pathPoints[i].Y, pathPoints[i].X);
        const p2 = L.latLng(pathPoints[i+1].Y, pathPoints[i+1].X);
        // Project pt onto segment p1-p2
        const dx = p2.lng - p1.lng;
        const dy = p2.lat - p1.lat;
        const lengthSq = dx*dx + dy*dy;
        let t = 0;
        if (lengthSq > 0) {
          t = ((pt.lng - p1.lng) * dx + (pt.lat - p1.lat) * dy) / lengthSq;
          t = Math.max(0, Math.min(1, t));
        }
        const projLat = p1.lat + t * (p2.lat - p1.lat);
        const projLng = p1.lng + t * (p2.lng - p1.lng);
        const proj = L.latLng(projLat, projLng);
        const dist = mapInstance.distance(pt, proj);
        if (dist <= toleranceMeters) {
          return true;
        }
      }
    }
    return false;
  }

  stops.forEach(stop => {
    const marker = L.marker([stop.lat, stop.lon]);
    marker.bindPopup(`${stop.name}<br>Click marker to load wait time`);

    marker.on('click', function(e) {
      this.getPopup().setContent(`${stop.name}<br>Loading wait times 1...`).openOn(map);

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
                    if (wt.raw_message === null || wt.raw_message === "no serv.") {
                      return `Line ${wt.line_number}: Not in Service`;
                    } else {
                      return `Line ${wt.line_number}: ${wt.raw_message}`;
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
    clearAnimations();
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
    // Hide the "Take me to vehicle" button
    document.getElementById('zoom-to-vehicle').style.display = 'none';

    currentLinePaths = []; // Clear stored paths
    currentVehicleType = ''; // Clear vehicle type
  }

  function clearTracking() {
    // Clear vehicle markers
    if (liveVehicleMarkersLayer) {
      map.removeLayer(liveVehicleMarkersLayer);
      liveVehicleMarkersLayer = null;
    }
    
    // Clear tracking interval
    if (trackingInterval) {
      clearInterval(trackingInterval);
      trackingInterval = null;
    }
    
    // Clear animation frame
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }

    // Clear line layer
    if (currentLineLayer) {
      map.removeLayer(currentLineLayer);
      currentLineLayer = null;
    }
  }
                                  
    // Clean up animations when switching lines or resetting
  function clearAnimations() {
      // Cancel animation frame
      if (animationFrameId) {
          cancelAnimationFrame(animationFrameId);
          animationFrameId = null;
      }
      
      // Clear all vehicle animations
      vehicleAnimations.clear();
      
      // Remove vehicle markers
      if (liveVehicleMarkersLayer) {
          map.removeLayer(liveVehicleMarkersLayer);
          liveVehicleMarkersLayer = null;
      }
      
      console.log('All animations cleared');
  }

  let debugProjectionMarker = null; // New global for debug marker

  function trackLine() {
    const lineNumber = document.getElementById('line-input').value.trim();
    if (!lineNumber) {
        alert('Please enter a line number');
        return;
    }

    clearTracking(); // Clear any previous tracking
    
    // Remove all markers and add filtered ones
    if (!isTracking) {
        map.removeLayer(allMarkers);
        isTracking = true;
    }
    
    console.log(`Tracking line: ${lineNumber}`);
    
    fetch(`/track_line?line_number=${lineNumber}`)
        .then(response => response.json())
        .then(data => {
            console.log('Received data for line tracking:', data);
            
            document.getElementById('tracking-status').textContent = 
                `Showing Line ${lineNumber} (${data.actual_station_count} stops)`;
            
            currentLinePaths = data.paths; // Store paths for vehicle simulation
            currentVehicleType = data.vehicle_type; // Store vehicle type

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
                        }).bindPopup(`Vehicle arriving at: ${stop.name}`);
                        
                        // Add click event listener to fetch wait times
                        stationMarker.on('click', function(e) {
                            this.getPopup().setContent(`${stop.name}<br>Loading wait times 2...`).openOn(map);
                            fetch(`/wait_time?stop_id=${stop.id}`)
                                .then(response => response.json())
                                .then(waitData => {
                                  if(waitData.wait_times && waitData.wait_times.length > 0) {
                                    const waitTimesHtml = waitData.wait_times
                                      .map(wt => {
                                        if (wt.raw_message === null || wt.raw_message === "no serv.") {
                                          return `Line ${wt.line_number}: Not in Service`;
                                        } else {
                                          return `Line ${wt.line_number}: ${wt.raw_message}`;
                                        }
                                      })
                                      .join('<br>');
                                    this.getPopup().setContent(`${stop.name}<br>${waitTimesHtml}`);
                                  } else {
                                    this.getPopup().setContent(`${stop.name}<br>${linesHtml}No wait time data available`);
                                  }
                                })
                                .catch(() => {
                                  this.getPopup().setContent(`${stop.name}<br>${linesHtml}Error loading wait times`);
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
                
                // Start vehicle simulation
                startVehicleSimulation(lineNumber);
                
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

  function startVehicleSimulation(lineNumber) {
    console.log('🚀 Starting vehicle simulation for line:', lineNumber);
    
    if (trackingInterval) {
        clearInterval(trackingInterval);
        console.log('⏹️ Cleared previous tracking interval');
    }
    
    const updateVehiclePositions = () => {
        console.log('📡 Fetching vehicle data for line:', lineNumber);
        
        fetch(`/get_line_vehicle_data?line_number=${lineNumber}`)
            .then(response => {
                console.log('📨 Response status:', response.status);
                return response.json();
            })
            .then((data) => {
                console.log('📊 RAW VEHICLE DATA RECEIVED:', JSON.stringify(data, null, 2));
                
                // Remove old vehicle markers
                if (liveVehicleMarkersLayer) {
                    console.log('🧹 Removing old vehicle markers');
                    map.removeLayer(liveVehicleMarkersLayer);
                    liveVehicleMarkersLayer = null;
                }
                liveVehicleMarkersLayer = L.layerGroup().addTo(map);
                
                // FIXED: Clear previous animations properly
                vehicleAnimations.clear();
                console.log('✨ Created new vehicle layer and cleared animations');

                // Remove previous highlighted approaching stops
                if (window._highlightedApproachingStops) {
                    console.log('🧹 Removing previous highlighted stops:', window._highlightedApproachingStops.length);
                    window._highlightedApproachingStops.forEach(m => map.removeLayer(m));
                }
                window._highlightedApproachingStops = [];

                // Add back the red highlight markers for approaching stops
                console.log('🔴 Creating highlight markers for approaching stops...');
                data.vehicles.forEach((vehicle, idx) => {
                    console.log(`🔴 Creating highlight marker ${idx + 1} for ${vehicle.stop_name} at [${vehicle.lat}, ${vehicle.lon}]`);
                    
                    const highlightMarker = L.circleMarker([vehicle.lat, vehicle.lon], {
                        radius: 10,
                        fillColor: '#FF4444',
                        color: '#fff',
                        weight: 3,
                        opacity: 1,
                        fillOpacity: 1
                    }).bindPopup(`🚌 Approaching: ${vehicle.stop_name}`);
                    
                    highlightMarker.addTo(map);
                        window._highlightedApproachingStops.push(highlightMarker);
                        console.log(`✅ Highlight marker ${idx + 1} added to map`);
                    });

                if (data.vehicles && data.vehicles.length > 0) {
                    console.log(`🚗 Processing ${data.vehicles.length} vehicles...`);
                    
                    // FIXED: Process each vehicle individually with unique IDs
                    data.vehicles.forEach((vehicle, vehicleIdx) => {
                        console.log(`\n🚗 PROCESSING VEHICLE ${vehicleIdx + 1}:`);
                        console.log(`  ID: ${vehicle.id}`);
                        console.log(`  Stop: ${vehicle.stop_name}`);
                        console.log(`  Wait Time: ${vehicle.wait_time} min`);
                        console.log(`  Raw Message: ${vehicle.raw_message}`);
                        
                        // Find the previous stop for bearing calculation
                        const allStops = data.line_stops_with_wait_times || [];
                        const currentStopIdx = allStops.findIndex(s => s.name === vehicle.stop_name);
                        let prevStopIdx = currentStopIdx - 1;
                        if (prevStopIdx < 0) {
                            prevStopIdx = allStops.length - 1; // Wrap to end
                        }
                        
                        let currentStop = allStops[currentStopIdx];
                        let prevStop = allStops[prevStopIdx];
                        
                        // Calculate bearing
                        bearing = 0;
                        if (prevStop && currentStop && 
                            (prevStop.lat !== currentStop.lat || prevStop.lon !== currentStop.lon)) {
                            const lat1 = prevStop.lat * Math.PI / 180;
                            const lon1 = prevStop.lon * Math.PI / 180;
                            const lat2 = currentStop.lat * Math.PI / 180;
                            const lon2 = currentStop.lon * Math.PI / 180;
                            
                            const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
                            const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
                            
                            bearing = Math.atan2(y, x) * 180 / Math.PI;
                            if (bearing < 0) bearing += 360;
                        }
                        
                        console.log(`  🧭 Calculated bearing: ${bearing.toFixed(2)}°`);
                        
                        // NEW: Spawn vehicles directly at the approaching station, then move towards next station
                        const stopLatLon = [vehicle.lat, vehicle.lon];
                        let vehiclePosition = stopLatLon; // Start directly at the approaching station
                        console.log(`  📍 Vehicle spawned directly at approaching station: ${vehicle.stop_name} [${vehiclePosition[0]}, ${vehiclePosition[1]}]`);

                        // Find the next station to move towards
                        let nextStop = null;
                        if (currentLinePaths.length > 0 && allStops.length > 0) {
                            nextStop = findNextStationByWaitTime(vehicle, allStops, currentLinePaths);
                            if (nextStop) {
                                console.log(`  🎯 Next destination: ${nextStop.name}`);
                                // Update currentStop for animation
                                currentStop = {
                                    lat: nextStop.lat,
                                    lon: nextStop.lon,
                                    name: nextStop.name,
                                    id: nextStop.stop_id
                                };
                            } else {
                                console.log(`  ⚠️ No clear next station found, vehicle will stay at current position`);
                                // Keep vehicle at current position if no next station is determined
                                currentStop = {
                                    lat: vehicle.lat,
                                    lon: vehicle.lon,
                                    name: vehicle.stop_name,
                                    id: vehicle.stop_id || 'unknown'
                                };
                            }
                        }

                        // Calculate bearing towards next station
                        bearing = 0;
                        if (nextStop) {
                            const lat1 = vehicle.lat * Math.PI / 180;
                            const lon1 = vehicle.lon * Math.PI / 180;
                            const lat2 = nextStop.lat * Math.PI / 180;
                            const lon2 = nextStop.lon * Math.PI / 180;
                            
                            const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
                            const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
                            
                            bearing = Math.atan2(y, x) * 180 / Math.PI;
                            if (bearing < 0) bearing += 360;
                        }

                        console.log(`  🧭 Calculated bearing towards next station: ${bearing.toFixed(2)}°`);
                        
                        // Create vehicle icon
                        const vehicleIcon = getVehicleIcon(lineNumber, bearing);
                        
                        if (vehicleIcon) {
                            // Create marker with unique ID
                            const marker = L.marker(vehiclePosition, { icon: vehicleIcon });
                            const popupContent = `🚌 Vehicle ${vehicle.id}<br>📍 ${vehicle.stop_name}<br>⏰ ${vehicle.raw_message} (${vehicle.wait_time} min)`;
                            marker.bindPopup(popupContent);
                            
                            // Add to layer
                            liveVehicleMarkersLayer.addLayer(marker);
                            
                            // FIXED: Create animation data for movement towards next station
                            if (currentLinePaths.length > 0 && nextStop) {
                                // Create a simple path from current position to next station
                                const animationPath = [
                                    {Y: vehicle.lat, X: vehicle.lon},
                                    {Y: nextStop.lat, X: nextStop.lon}
                                ];
                                
                                // Calculate animation duration based on distance
                                const distance = Math.sqrt(
                                    Math.pow(nextStop.lat - vehicle.lat, 2) + 
                                    Math.pow(nextStop.lon - vehicle.lon, 2)
                                ) * 111000; // Rough conversion to meters
                                
                                let animationDuration = Math.max(5000, Math.min(distance * 10, 20000)); // 5-20 seconds based on distance
                                
                                // Use the vehicle's unique ID for animation tracking
                                vehicleAnimations.set(vehicle.id, {
                                    marker: marker,
                                    polyline: animationPath,
                                    startTime: Date.now(),
                                    duration: animationDuration,
                                    isAnimating: true,
                                    stopName: nextStop.name,
                                    prevStop: {lat: vehicle.lat, lon: vehicle.lon, name: vehicle.stop_name},
                                    currStop: currentStop,
                                    vehicleId: vehicle.id
                                });

                                console.log(`  🎬 Animation created for vehicle ${vehicle.id} towards ${nextStop.name} (duration: ${animationDuration}ms)`);
                            } else {
                                console.log(`  ⏹️ No animation created - vehicle will remain stationary`);
                            }
                            
                            console.log(`  ✅ Vehicle ${vehicle.id} marker created and added`);
                        } else {
                            console.error(`  ❌ Failed to create icon for vehicle ${vehicle.id}`);
                        }
                    });
                    
                    console.log(`\n📊 SUMMARY:`);
                    console.log(`  - Vehicles processed: ${data.vehicles.length}`);
                    console.log(`  - Markers on map: ${liveVehicleMarkersLayer.getLayers().length}`);
                    console.log(`  - Animations created: ${vehicleAnimations.size}`);
                    
                    // Start animation loop if not already running and we have animations
                    if (!animationFrameId && vehicleAnimations.size > 0) {
                        console.log(`🎬 Starting animation loop for ${vehicleAnimations.size} vehicles`);
                        lastUpdateTime = Date.now();
                        animateVehicles();
                    }

                    // Show zoom button if we have vehicles
                    document.getElementById('zoom-to-vehicle').style.display = 
                        data.vehicles.length > 0 ? 'inline-block' : 'none';
                    
                } else {
                    console.warn('❌ No vehicles data available');
                    document.getElementById('zoom-to-vehicle').style.display = 'none';
                }
            })
            .catch(error => {
                console.error('❌ Error fetching vehicle data:', error);
                document.getElementById('zoom-to-vehicle').style.display = 'none';
            });
    };

    // Run immediately and then every 60 seconds
    console.log('⏰ Running initial vehicle position update...');
    updateVehiclePositions();
    
    console.log('⏰ Setting up 60-second interval for updates...');
    trackingInterval = setInterval(updateVehiclePositions, 60000);
  }

  function zoomToVehicle() {
    if (liveVehicleMarkersLayer && liveVehicleMarkersLayer.getLayers().length > 0) {
      // Get the first vehicle's position
      const position = liveVehicleMarkersLayer.getLayers()[0].getLatLng();
      // Zoom in to level 16 (close zoom)
      map.setView(position, 16);
      // Open the marker's popup
      liveVehicleMarkersLayer.getLayers()[0].openPopup();
    }
  }

  // Allow Enter key to trigger tracking
  document.getElementById('line-input').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      trackLine();
    }
  });

  // FIXED: Helper functions for animation system

  // NEW: Find next station based on wait times and polyline proximity
function findNextStationByWaitTime(currentVehicle, allStops, allPaths) {
    console.log(`🔍 Finding next station for vehicle at ${currentVehicle.stop_name}...`);
    
    // Get current vehicle position
    const currentPos = [currentVehicle.lat, currentVehicle.lon];
    
    // Find nearby stations (within reasonable distance)
    const nearbyStations = allStops.filter(stop => {
        const distance = Math.abs(stop.lat - currentPos[0]) + Math.abs(stop.lon - currentPos[1]);
        return distance < 0.02 && stop.name !== currentVehicle.stop_name; // Within ~2km and not the same station
    });
    
    console.log(`  📍 Found ${nearbyStations.length} nearby stations`);
    
    if (nearbyStations.length === 0) {
        console.log(`  ⚠️ No nearby stations found`);
        return null;
    }
    
    // Sort by distance from current position
    nearbyStations.sort((a, b) => {
        const distA = Math.abs(a.lat - currentPos[0]) + Math.abs(a.lon - currentPos[1]);
        const distB = Math.abs(b.lat - currentPos[0]) + Math.abs(b.lon - currentPos[1]);
        return distA - distB;
    });
    
    // Take the 2-3 closest stations and check their wait times
    const candidateStations = nearbyStations.slice(0, 3);
    console.log(`  🎯 Checking wait times for ${candidateStations.length} candidate stations:`);
    
    for (const station of candidateStations) {
        console.log(`    - ${station.name}: wait_message = "${station.wait_message}"`);
    }
    
    // Find station with shortest wait time (excluding "no serv." and current station)
    let bestStation = null;
    let shortestWaitTime = Infinity;
    
    for (const station of candidateStations) {
        if (station.wait_message && 
            station.wait_message !== "no serv." && 
            station.wait_message !== "No data" &&
            station.name !== currentVehicle.stop_name) {
            
            let waitTime = parseWaitMinutes(station.wait_message);
            if (waitTime < shortestWaitTime) {
                shortestWaitTime = waitTime;
                bestStation = station;
            }
        }
    }
    
    if (bestStation) {
        console.log(`  ✅ Selected next station: ${bestStation.name} (wait: ${bestStation.wait_message})`);
        return bestStation;
    }
    
    // Fallback: if no station has valid wait times, pick the closest one
    if (candidateStations.length > 0) {
        console.log(`  🔄 Fallback: selecting closest station: ${candidateStations[0].name}`);
        return candidateStations[0];
    }
    
    console.log(`  ❌ No suitable next station found`);
    return null;
  }
  function interpolateOnPolyline(polyline, progress, mapInstance) {
    if (polyline.length < 2) return [polyline[0].Y, polyline[0].X];
    
    // Calculate total length
    let totalLength = 0;
    let segmentLengths = [];
    for (let i = 0; i < polyline.length - 1; i++) {
        const p1 = L.latLng(polyline[i].Y, polyline[i].X);
        const p2 = L.latLng(polyline[i+1].Y, polyline[i+1].X);
        const segLen = mapInstance.distance(p1, p2);
        segmentLengths.push(segLen);
        totalLength += segLen;
    }
    
    let targetDist = progress * totalLength;
    let acc = 0;
    
    for (let i = 0; i < segmentLengths.length; i++) {
        if (acc + segmentLengths[i] >= targetDist) {
            const p1 = polyline[i];
            const p2 = polyline[i+1];
            const segProgress = (targetDist - acc) / segmentLengths[i];
            const lat = p1.Y + (p2.Y - p1.Y) * segProgress;
            const lon = p1.X + (p2.X - p1.X) * segProgress;
            return [lat, lon];
        }
        acc += segmentLengths[i];
    }
    
    // If we reach here, return last point
    return [polyline[polyline.length-1].Y, polyline[polyline.length-1].X];
  }

  // FIXED: Helper functions for animation system
  function findPolylineSegment(allPaths, prevStop, currStop) {
      // Find the path that contains both stops (closest points)
      let bestPath = null;
      let bestPrevIdx = -1;
      let bestCurrIdx = -1;
      let minTotalDist = Infinity;
    
      allPaths.forEach(path => {
          let prevIdx = -1, currIdx = -1;
          let minPrevDist = Infinity, minCurrDist = Infinity;
          
          path.forEach((pt, idx) => {
              const prevDist = Math.abs(pt.Y - prevStop.lat) + Math.abs(pt.X - prevStop.lon);
              const currDist = Math.abs(pt.Y - currStop.lat) + Math.abs(pt.X - currStop.lon);
              
              if (prevDist < minPrevDist) {
                  minPrevDist = prevDist;
                  prevIdx = idx;
              }
              if (currDist < minCurrDist) {
                  minCurrDist = currDist;
                  currIdx = idx;
              }
          });
          
          if (prevIdx !== -1 && currIdx !== -1 && prevIdx < currIdx) {
              const totalDist = minPrevDist + minCurrDist;
              if (totalDist < minTotalDist) {
                  minTotalDist = totalDist;
                  bestPath = path;
                  bestPrevIdx = prevIdx;
                  bestCurrIdx = currIdx;
              }
          }
      });
    
      if (bestPath && bestPrevIdx < bestCurrIdx) {
          return bestPath.slice(bestPrevIdx, bestCurrIdx + 1);
      }
    
      // Fallback: return a straight line
      return [
          {Y: prevStop.lat, X: prevStop.lon},
          {Y: currStop.lat, X: currStop.lon}
      ];
  }
  function findPreviousStopOnPolyline(allPaths, targetStopLatLon, allStops) {
    console.log('🔍 Finding previous stop on polyline route...');
    console.log(`  🎯 Target stop coordinates: [${targetStopLatLon[0]}, ${targetStopLatLon[1]}]`);
    
    // Find the target stop on the polyline
    let targetPathIdx = -1;
    let targetPointIdx = -1;
    let minDistanceToTarget = Infinity;
    
    allPaths.forEach((path, pathIdx) => {
        path.forEach((point, pointIdx) => {
            const distance = Math.abs(point.Y - targetStopLatLon[0]) + Math.abs(point.X - targetStopLatLon[1]);
            if (distance < minDistanceToTarget) {
                minDistanceToTarget = distance;
                targetPathIdx = pathIdx;
                targetPointIdx = pointIdx;
            }
        });
    });
    
    if (targetPathIdx === -1) {
        console.warn('  ⚠️ Target stop not found on polyline');
        return null;
    }
    
    console.log(`  🎯 Target stop found at path ${targetPathIdx}, point ${targetPointIdx}, distance: ${minDistanceToTarget.toFixed(6)}`);
    
    // Look backwards along the polyline to find the previous stop
    const targetPath = allPaths[targetPathIdx];
    let searchRadius = 0.005; // Start with reasonable radius (about 500m)
    let minStopDistance = 100; // Minimum distance between stops in polyline points
    
    for (let attempts = 0; attempts < 4; attempts++) {
        console.log(`  🔄 Search attempt ${attempts + 1} with radius ${searchRadius.toFixed(6)}`);
        
        // Start searching backwards from target, but skip nearby points to avoid finding the same stop
        for (let i = Math.max(0, targetPointIdx - minStopDistance); i >= 0; i -= 5) { // Skip points for efficiency
            const polylinePoint = targetPath[i];
            
            // Check if any stop is near this polyline point
            for (const stop of allStops) {
                const stopDistance = Math.abs(stop.lat - polylinePoint.Y) + Math.abs(stop.lon - polylinePoint.X);
                if (stopDistance < searchRadius) {
                    // Make sure this isn't the same stop we're looking for
                    const distanceFromTarget = Math.abs(stop.lat - targetStopLatLon[0]) + Math.abs(stop.lon - targetStopLatLon[1]);
                    if (distanceFromTarget > 0.002) { // Must be at least 200m away from target
                        console.log(`  ✅ Found previous stop: ${stop.name} at polyline point ${i}, distance ${stopDistance.toFixed(6)}`);
                        console.log(`  📏 Distance from target stop: ${distanceFromTarget.toFixed(6)}`);
                        return stop;
                    }
                }
            }
        }
        
        searchRadius *= 1.5; // Expand search radius more gradually
        minStopDistance = Math.max(20, minStopDistance - 20); // Reduce minimum distance requirement
        console.log(`  🔄 Expanding search radius to ${searchRadius.toFixed(6)}, min distance: ${minStopDistance}`);
    }
    
    console.warn('  ⚠️ No previous stop found on polyline route after all attempts');
    return null;
}
</script>

</body>
</html>
""", stops=stops)

if __name__ == "__main__":
    print("Starting server on port 8080...")
    app.run(debug=True, port=8080)

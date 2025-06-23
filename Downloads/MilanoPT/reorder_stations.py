import json
import csv
import os
from math import radians, sin, cos, sqrt, atan2

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in meters"""
    R = 6371000  # Earth's radius in meters
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def find_closest_point_on_shape(station_lat, station_lon, shape_points):
    """Find the closest point on a shape to a given station"""
    min_distance = float('inf')
    closest_point_idx = -1
    
    for i, point in enumerate(shape_points):
        distance = calculate_distance(station_lat, station_lon, point['Y'], point['X'])
        if distance < min_distance:
            min_distance = distance
            closest_point_idx = i
    
    return closest_point_idx, min_distance

def calculate_cumulative_distance_along_shape(shape_points):
    """Calculate cumulative distance along the shape for each point"""
    cumulative_distances = [0.0]
    total_distance = 0.0
    
    for i in range(1, len(shape_points)):
        distance = calculate_distance(
            shape_points[i-1]['Y'], shape_points[i-1]['X'],
            shape_points[i]['Y'], shape_points[i]['X']
        )
        total_distance += distance
        cumulative_distances.append(total_distance)
    
    return cumulative_distances

def reorder_stations_by_shape(stations, shape_points):
    """Reorder stations based on their position along the shape using cumulative distance"""
    if not shape_points or len(shape_points) < 2:
        print("Warning: No valid shape points found")
        return stations
    
    # Calculate cumulative distances along the shape
    cumulative_distances = calculate_cumulative_distance_along_shape(shape_points)
    
    # Find the closest point on the shape for each station and get its cumulative distance
    station_positions = []
    for station in stations:
        closest_idx, distance = find_closest_point_on_shape(
            station['lat'], station['lon'], shape_points
        )
        
        # Get the cumulative distance at this point
        cumulative_distance = cumulative_distances[closest_idx]
        
        station_positions.append({
            'station': station,
            'shape_index': closest_idx,
            'cumulative_distance': cumulative_distance,
            'distance_to_shape': distance
        })
    
    # Sort by cumulative distance along the shape (this gives chronological order)
    station_positions.sort(key=lambda x: x['cumulative_distance'])
    
    # Return reordered stations
    return [pos['station'] for pos in station_positions]

def load_gtfs_data():
    """Load GTFS data for shapes and routes"""
    print("Loading GTFS data...")
    
    # Load routes
    routes = {}
    with open('given_data/routes.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            routes[row['route_id']] = {
                'short_name': row['route_short_name'],
                'long_name': row['route_long_name'],
                'type': row['route_type']
            }
    
    # Load shapes
    shapes = {}
    with open('given_data/shapes.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            shape_id = row['shape_id']
            if shape_id not in shapes:
                shapes[shape_id] = []
            shapes[shape_id].append({
                'Y': float(row['shape_pt_lat']), 
                'X': float(row['shape_pt_lon']), 
                'seq': int(row['shape_pt_sequence'])
            })
    
    # Sort shapes by sequence
    for shape_id in shapes:
        shapes[shape_id].sort(key=lambda x: x['seq'])
    
    # Load trips to link routes to shapes
    route_shapes = {}
    with open('given_data/trips.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            route_id = row['route_id']
            shape_id = row['shape_id']
            if route_id not in route_shapes:
                route_shapes[route_id] = set()
            route_shapes[route_id].add(shape_id)
    
    print(f"Loaded {len(routes)} routes, {len(shapes)} shapes, {len(route_shapes)} route-shape mappings")
    return routes, shapes, route_shapes

def reorder_line_stations_cache():
    """Main function to reorder stations in line_stations_cache.json"""
    print("Starting station reordering process...")
    
    # Load existing cache
    try:
        with open('line_stations_cache.json', 'r', encoding='utf-8') as f:
            line_stations_memory = json.load(f)
        print(f"Loaded existing cache with {len(line_stations_memory)} line entries")
    except FileNotFoundError:
        print("Error: line_stations_cache.json not found!")
        return
    
    # Load GTFS data
    routes, shapes, route_shapes = load_gtfs_data()
    
    # Process each line
    reordered_cache = {}
    processed_lines = 0
    skipped_lines = 0
    
    for line_id, line_data in line_stations_memory.items():
        print(f"\nProcessing line: {line_id}")
        
        # Get the route_id (might be the same as line_id or different)
        route_id = line_id
        
        # Try to find shapes for this route
        if route_id in route_shapes:
            shape_ids = route_shapes[route_id]
            print(f"  Found {len(shape_ids)} shapes for route {route_id}")
            
            # Use the first shape (or could average multiple shapes)
            shape_id = list(shape_ids)[0]
            if shape_id in shapes:
                shape_points = shapes[shape_id]
                print(f"  Using shape {shape_id} with {len(shape_points)} points")
                
                # Reorder stations
                original_stations = line_data['stations']
                reordered_stations = reorder_stations_by_shape(original_stations, shape_points)
                
                # Create new line data with reordered stations
                reordered_cache[line_id] = {
                    'stations': reordered_stations,
                    'route_info': line_data['route_info'],
                    'station_count': len(reordered_stations),
                    'shape_id': shape_id  # Add shape info for reference
                }
                
                # Print station order
                print(f"  Reordered stations:")
                for i, station in enumerate(reordered_stations):
                    print(f"    {i+1}. {station['name']}")
                
                processed_lines += 1
            else:
                print(f"  Warning: Shape {shape_id} not found in shapes data")
                reordered_cache[line_id] = line_data  # Keep original
                skipped_lines += 1
        else:
            print(f"  Warning: No shapes found for route {route_id}")
            reordered_cache[line_id] = line_data  # Keep original
            skipped_lines += 1
    
    # Create 1test folder if it doesn't exist
    os.makedirs('1test', exist_ok=True)
    
    # Save reordered cache to 1test folder
    output_file = '1test/line_stations_cache_ordered.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(reordered_cache, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Reordering complete!")
    print(f"  Processed: {processed_lines} lines")
    print(f"  Skipped: {skipped_lines} lines (no shape data)")
    print(f"  Output: {output_file}")
    
    # Also create a backup of the original
    backup_file = 'line_stations_cache_REAL.json'
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(line_stations_memory, f, ensure_ascii=False, indent=2)
    print(f"  Backup: {backup_file}")

if __name__ == "__main__":
    reorder_line_stations_cache() 
# Milano Tram Tracker

A real-time tracking application for Milan's public transportation system, including metro, tram, and bus lines.

## Features

- Real-time tracking of vehicles on metro, tram, and bus lines using GTFS and ATM APIs
- Interactive map interface built with Leaflet.js and MarkerCluster for efficient visualization
- Clickable stop markers to display live wait times for all lines at each stop
- Vehicle position simulation based on real-time wait times, with animated movement along the route
- Support for all ATM (Azienda Trasporti Milanesi) lines, including Metro (M), Tram (T), and Bus (B) prefixes
- Color-coded lines and custom vehicle icons (with direction) for Metro, Tram, and Bus
- "Take me to vehicle" button to zoom to the nearest tracked vehicle
- Reset and clear map controls for user convenience
- Responsive design for desktop and mobile browsers
- Efficient backend caching and batch API requests to minimize load and rate limits
- Preprocessing and caching of GTFS data for fast startup and queries
- Robust error handling and fallback mechanisms for missing or incomplete data
- Supports live tracking of user-position on the map (if authorized)

### Advanced/Unique Features

- Animated vehicle markers that move smoothly along the polyline between stops, with direction-aware icons
- Highlighting of approaching stops with special markers
- Dynamic calculation of vehicle direction and bearing for icon orientation
- Vehicle speed calculated on speed limits and traffic conditions (provided by the Google Maps API)
- Polyline interpolation and segment-finding for accurate vehicle animation
- Wait time parsing and fallback logic for "in arrivo", "no serv.", and other custom ATM messages
- Batch fetching of wait times for all stops on a line to reduce API calls
- Support for both route_id and short_name lookups (although not recommended: "M5" and "5" both work)
- Customizable update interval for vehicle positions (default: 30 seconds)
- Modular Flask backend with endpoints for:
  - `/track_line` (route and stops for a line)
  - `/wait_time` (wait times for a stop)
  - `/station_lines` (lines serving a stop)
  - `/get_line_vehicle_data` (all vehicles and stops for a line)
  - `/static/vehicle_images/...` (custom vehicle icons)

## Requirements

- Python 3.x
- Flask
- Required Python packages (install via pip):
  ```
  flask
  requests
  ```

## Installation

- Currently, this code is being kept PRIVATE and is not available for public distribution.

## Usage

1. Enter a line number in the input field (e.g., M1 for Metro 1, T3 for Tram 3, B90 for Bus 90)
2. Click "Track Line" to view the line's route and vehicle positions
3. Click on any stop marker to see wait times for all lines at that stop
4. Use the "Take me to vehicle" button to zoom to the nearest vehicle
5. Use the "Reset Map" button to clear the current tracking and return to the full map
6. Vehicle markers are animated and direction-aware; highlighted stops indicate approaching vehicles
7. The map and vehicle positions update automatically every 30-60 seconds

## Video Demo



## Data Sources

- GTFS data from ATM (Azienda Trasporti Milanesi)
- Real-time wait times for each station from ATM's API

## License

This project is licensed under the MIT License - see the LICENSE file for details. 

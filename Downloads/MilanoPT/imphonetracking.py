from flask import Flask, jsonify, render_template_string, request
import requests
from datetime import datetime
import json
import os
from pyicloud import PyiCloudService

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Replace with a proper secret key

# iCloud credentials store
icloud_api = None

# Target email to track
TARGET_EMAIL = "robertacalderoni@icloud.com"

# HTML template for the tracking page
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Find My People Tracker</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
    <style>
        #map { height: 600px; width: 100%; }
        .info { padding: 10px; background: white; margin: 10px; border-radius: 5px; }
        .login-form { margin: 20px 0; }
        .status { color: #666; margin: 10px 0; }
        .people-list {
            margin: 10px 0;
            max-height: 200px;
            overflow-y: auto;
        }
        .person-item {
            padding: 5px;
            margin: 5px 0;
            background: #f5f5f5;
            border-radius: 3px;
            cursor: pointer;
        }
        .person-item:hover {
            background: #e5e5e5;
        }
        .verification-form {
            display: none;
            margin: 20px 0;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 5px;
        }
        .debug-info {
            margin: 10px 0;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
            font-family: monospace;
            font-size: 12px;
            max-height: 200px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="info">
        <h2>Find My People Tracker</h2>
        <div class="login-form" id="loginForm">
            <h3>Login to iCloud</h3>
            <input type="text" id="appleId" placeholder="Apple ID" />
            <input type="password" id="password" placeholder="Password" />
            <button onclick="login()">Login</button>
        </div>
        <div id="verificationForm" class="verification-form">
            <h3>Two-Factor Authentication Required</h3>
            <p id="verificationMessage"></p>
            <input type="text" id="verificationCode" placeholder="Enter 6-digit code" />
            <button onclick="submitVerification()">Submit</button>
        </div>
        <div class="status">
            <p>Status: <span id="connectionStatus">Not connected</span></p>
            <p>Last updated: <span id="lastUpdate">Never</span></p>
        </div>
        <div class="people-list" id="peopleList">
            <h3>Shared Locations</h3>
        </div>
        <button onclick="updateLocations()">Update Locations</button>
        <button onclick="getDebugInfo()">Debug Info</button>
        <div id="debugInfo" class="debug-info" style="display: none;"></div>
    </div>
    <div id="map"></div>
    
    <script>
        var map = L.map('map').setView([45.4642, 9.1900], 13); // Milan coordinates
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);
        
        var markers = {};
        
        function login() {
            const appleId = document.getElementById('appleId').value;
            const password = document.getElementById('password').value;
            
            if (!appleId || !password) {
                alert('Please enter both Apple ID and password');
                return;
            }
            
            fetch('/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    apple_id: appleId,
                    password: password
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'requires_2fa') {
                    document.getElementById('verificationForm').style.display = 'block';
                    document.getElementById('verificationMessage').textContent = 'Please check your trusted devices for a verification code';
                    document.getElementById('loginForm').style.display = 'none';
                } else if (data.status === 'success') {
                    loginSuccess();
                } else {
                    alert('Login failed: ' + (data.message || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Login failed. Please try again.');
            });
        }
        
        function submitVerification() {
            const code = document.getElementById('verificationCode').value;
            
            if (!code || code.length !== 6) {
                alert('Please enter a 6-digit verification code');
                return;
            }
            
            fetch('/verify', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    code: code
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    loginSuccess();
                } else {
                    alert('Verification failed: ' + (data.message || 'Invalid code'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Verification failed. Please try again.');
            });
        }
        
        function loginSuccess() {
            document.getElementById('connectionStatus').textContent = 'Connected';
            document.getElementById('loginForm').style.display = 'none';
            document.getElementById('verificationForm').style.display = 'none';
            updateLocations();
        }
        
        function updateLocations() {
            fetch('/get_shared_locations')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        throw new Error(data.error);
                    }
                    
                    document.getElementById('lastUpdate').textContent = new Date().toLocaleString();
                    
                    // Clear existing markers
                    Object.values(markers).forEach(marker => map.removeLayer(marker));
                    markers = {};
                    
                    // Update people list
                    const peopleList = document.getElementById('peopleList');
                    peopleList.innerHTML = '<h3>Shared Locations</h3>';
                    
                    // Create bounds for all markers
                    const bounds = [];
                    
                    data.forEach(person => {
                        // Add to list
                        const personDiv = document.createElement('div');
                        personDiv.className = 'person-item';
                        personDiv.innerHTML = `
                            <strong>${person.name}</strong> (${person.deviceName})<br>
                            <small>Last updated: ${person.timestamp}</small><br>
                            <small>Accuracy: ${person.horizontalAccuracy}m</small>
                        `;
                        personDiv.onclick = () => focusOnPerson(person.id);
                        peopleList.appendChild(personDiv);
                        
                        // Add marker
                        const marker = L.marker([person.latitude, person.longitude])
                            .addTo(map)
                            .bindPopup(`
                                <strong>${person.name}</strong><br>
                                Device: ${person.deviceName}<br>
                                Last updated: ${person.timestamp}<br>
                                Accuracy: ${person.horizontalAccuracy}m
                            `);
                        
                        markers[person.id] = marker;
                        bounds.push([person.latitude, person.longitude]);
                    });
                    
                    // Fit map to show all markers
                    if (bounds.length > 0) {
                        if (bounds.length === 1) {
                            map.setView(bounds[0], 15);
                        } else {
                            map.fitBounds(bounds);
                        }
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Failed to update locations: ' + error.message);
                });
        }
        
        function getDebugInfo() {
            fetch('/debug_info')
                .then(response => response.json())
                .then(data => {
                    const debugDiv = document.getElementById('debugInfo');
                    debugDiv.innerHTML = '<h4>Debug Information:</h4><pre>' + JSON.stringify(data, null, 2) + '</pre>';
                    debugDiv.style.display = 'block';
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Failed to get debug info: ' + error.message);
                });
        }
        
        function focusOnPerson(personId) {
            const marker = markers[personId];
            if (marker) {
                map.setView(marker.getLatLng(), 15);
                marker.openPopup();
            }
        }
        
        // Auto-update locations every 2 minutes
        setInterval(updateLocations, 120000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/login', methods=['POST'])
def login():
    global icloud_api
    
    data = request.get_json()
    apple_id = data.get('apple_id')
    password = data.get('password')
    
    if not apple_id or not password:
        return jsonify({"status": "error", "message": "Apple ID and password are required"}), 400
    
    try:
        print(f"Attempting to login with Apple ID: {apple_id}")
        icloud_api = PyiCloudService(apple_id, password)
        
        if icloud_api.requires_2fa:
            print("2FA required")
            return jsonify({
                "status": "requires_2fa",
                "message": "Two-factor authentication required"
            })
        
        print("Login successful")
        return jsonify({"status": "success"})
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 401

@app.route('/verify', methods=['POST'])
def verify():
    global icloud_api
    
    if not icloud_api:
        return jsonify({"status": "error", "message": "No pending authentication"}), 400
        
    data = request.get_json()
    verification_code = data.get('code')
    
    if not verification_code:
        return jsonify({"status": "error", "message": "Verification code is required"}), 400
    
    try:
        print(f"Attempting to verify with code: {verification_code}")
        result = icloud_api.validate_2fa_code(verification_code)
        
        if result:
            print("2FA verification successful")
            return jsonify({"status": "success"})
        else:
            print("2FA verification failed")
            return jsonify({
                "status": "error",
                "message": "Invalid verification code"
            }), 401
            
    except Exception as e:
        print(f"Verification error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/debug_info')
def debug_info():
    global icloud_api
    
    if not icloud_api:
        return jsonify({"error": "Not authenticated"}), 401
        
    try:
        debug_data = {
            "authenticated": True,
            "devices": [],
            "fmip_available": hasattr(icloud_api, 'iphone'),
            "fmf_available": hasattr(icloud_api, 'find_my_friends') or hasattr(icloud_api, 'fmf')
        }
        
        # Get device information
        if hasattr(icloud_api, 'devices'):
            for device in icloud_api.devices:
                try:
                    device_data = {
                        "name": getattr(device, 'name', 'Unknown'),
                        "model": getattr(device, 'model', 'Unknown'),
                        "id": getattr(device, 'id', 'Unknown'),
                        "device_class": getattr(device, 'device_class', 'Unknown'),
                        "has_location": hasattr(device, 'location') and callable(getattr(device, 'location', None))
                    }
                    
                    # Try to get location if available
                    if device_data["has_location"]:
                        try:
                            location = device.location()
                            if location:
                                device_data["location"] = {
                                    "latitude": location.get("latitude"),
                                    "longitude": location.get("longitude"),
                                    "timestamp": location.get("timeStamp"),
                                    "accuracy": location.get("horizontalAccuracy")
                                }
                        except Exception as loc_error:
                            device_data["location_error"] = str(loc_error)
                    
                    debug_data["devices"].append(device_data)
                    
                except Exception as device_error:
                    debug_data["devices"].append({
                        "error": str(device_error),
                        "device_type": str(type(device))
                    })
        
        return jsonify(debug_data)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_shared_locations')
def get_shared_locations():
    global icloud_api
    
    if not icloud_api:
        return jsonify({"error": "Not authenticated"}), 401
        
    try:
        locations = []
        print("Fetching shared locations from Find My Friends...")
        
        # Method 1: Try Find My Friends service first (this is what we want for shared locations)
        try:
            # Try to access Find My Friends service
            if hasattr(icloud_api, 'friends'):
                print("Found friends service, getting locations...")
                friends_data = icloud_api.friends.locations
                
                for friend_id, friend_data in friends_data.items():
                    print(f"Processing friend: {friend_id}")
                    print(f"Friend data: {friend_data}")
                    
                    if friend_data and 'location' in friend_data:
                        loc_data = friend_data['location']
                        if loc_data and 'latitude' in loc_data and 'longitude' in loc_data:
                            # Get timestamp
                            timestamp = loc_data.get('timestamp', 0)
                            if timestamp:
                                timestamp_seconds = timestamp / 1000 if timestamp > 1000000000000 else timestamp
                                formatted_time = datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S')
                            else:
                                formatted_time = "Unknown"
                            
                            locations.append({
                                'id': friend_id,
                                'name': friend_data.get('fullName', 'Unknown Friend'),
                                'deviceName': 'Friend Location',
                                'latitude': loc_data['latitude'],
                                'longitude': loc_data['longitude'],
                                'timestamp': formatted_time,
                                'horizontalAccuracy': loc_data.get('horizontalAccuracy', 0)
                            })
                            print(f"Found location for {friend_data.get('fullName', friend_id)}")
                        
            # Alternative method: Try accessing the Find My Friends service directly
            elif hasattr(icloud_api, '_webservices') and 'findme' in icloud_api._webservices:
                print("Trying direct Find My Friends access...")
                findme_service = icloud_api._webservices['findme']
                
                # Make a direct API call to get friends locations
                friends_response = findme_service._service_root.refreshClient.post(
                    findme_service._service_endpoint + '/fmipservice/client/web/refreshClient',
                    params=findme_service.params
                )
                
                if friends_response.get('content'):
                    friends_list = friends_response['content']
                    for friend in friends_list:
                        if friend.get('location'):
                            loc = friend['location']
                            timestamp = loc.get('timeStamp', 0)
                            if timestamp:
                                timestamp_seconds = timestamp / 1000 if timestamp > 1000000000000 else timestamp
                                formatted_time = datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S')
                            else:
                                formatted_time = "Unknown"
                            
                            locations.append({
                                'id': friend.get('id', 'unknown'),
                                'name': friend.get('name', 'Unknown Friend'),
                                'deviceName': 'Shared Location',
                                'latitude': loc['latitude'],
                                'longitude': loc['longitude'],
                                'timestamp': formatted_time,
                                'horizontalAccuracy': loc.get('horizontalAccuracy', 0)
                            })
                            
        except Exception as friends_error:
            print(f"Error accessing Find My Friends: {friends_error}")
        
        # Method 2: Try custom Find My Friends implementation
        if not locations:
            print("Trying custom Find My Friends API call...")
            try:
                # This is based on the working implementation from the GitHub issues
                import requests
                
                # Get the session and cookies from the authenticated icloud_api
                session = icloud_api.session
                
                # Find My Friends endpoint
                fmf_url = "https://p04-fmf.icloud.com/fmipservice/client/fmfWeb/initClient"
                
                # Prepare the request data
                request_data = {
                    'clientContext': {
                        'appName': 'FindMyFriends',
                        'appVersion': '4.0',
                        'deviceUDID': '0000000000000000000000000000000000000000',
                        'inactiveTime': 1,
                        'osVersion': '13.0',
                        'personID': None,
                        'productType': 'fmfWeb',
                        'timezone': 'US/Eastern',
                        'userInactiveTime': 1
                    }
                }
                
                response = session.post(fmf_url, json=request_data)
                if response.status_code == 200:
                    fmf_data = response.json()
                    print(f"Find My Friends response: {fmf_data}")
                    
                    # Parse the response for location data
                    if 'locations' in fmf_data:
                        for location in fmf_data['locations']:
                            if location.get('location'):
                                loc = location['location']
                                timestamp = loc.get('timeStamp', 0)
                                if timestamp:
                                    timestamp_seconds = timestamp / 1000 if timestamp > 1000000000000 else timestamp
                                    formatted_time = datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S')
                                else:
                                    formatted_time = "Unknown"
                                
                                locations.append({
                                    'id': location.get('id', 'unknown'),
                                    'name': location.get('nickname', location.get('firstName', 'Unknown')),
                                    'deviceName': 'Find My Friends',
                                    'latitude': loc['latitude'],
                                    'longitude': loc['longitude'],
                                    'timestamp': formatted_time,
                                    'horizontalAccuracy': loc.get('horizontalAccuracy', 0)
                                })
                    
            except Exception as custom_error:
                print(f"Error with custom Find My Friends call: {custom_error}")
        
        # Method 3: Fallback to devices (your own devices)
        if not locations:
            print("No shared locations found, falling back to your own devices...")
            
            if hasattr(icloud_api, 'devices'):
                for device in icloud_api.devices:
                    try:
                        device_name = getattr(device, 'name', 'Unknown Device')
                        device_model = getattr(device, 'model', 'Unknown Model')
                        device_id = getattr(device, 'id', 'unknown_id')
                        
                        print(f"Processing device: {device_name} ({device_model})")
                        
                        if hasattr(device, 'location') and callable(getattr(device, 'location', None)):
                            try:
                                location_data = device.location()
                                if location_data and 'latitude' in location_data and 'longitude' in location_data:
                                    timestamp = location_data.get('timeStamp', 0)
                                    if timestamp:
                                        timestamp_seconds = timestamp / 1000 if timestamp > 1000000000000 else timestamp
                                        formatted_time = datetime.fromtimestamp(timestamp_seconds).strftime('%Y-%m-%d %H:%M:%S')
                                    else:
                                        formatted_time = "Unknown"
                                    
                                    locations.append({
                                        'id': device_id,
                                        'name': f"Your {device_name}",
                                        'deviceName': f"{device_name} ({device_model})",
                                        'latitude': location_data['latitude'],
                                        'longitude': location_data['longitude'],
                                        'timestamp': formatted_time,
                                        'horizontalAccuracy': location_data.get('horizontalAccuracy', 0)
                                    })
                                    print(f"Found location for {device_name}")
                            except Exception as loc_error:
                                print(f"Error getting location for {device_name}: {loc_error}")
                                        
                    except Exception as device_error:
                        print(f"Error processing device: {device_error}")
                        continue
        
        if locations:
            # Sort by timestamp (most recent first) and return all locations
            locations.sort(key=lambda x: x['timestamp'], reverse=True)
            return jsonify(locations)
        else:
            return jsonify({"error": "No locations found. Make sure people are sharing their location with you and the service is properly configured."}), 404
        
    except Exception as e:
        print(f"Error in get_shared_locations: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Find My People Tracker...")
    print("Make sure you have pyicloud installed: pip install pyicloud")
    app.run(debug=True, host='0.0.0.0', port=5000)
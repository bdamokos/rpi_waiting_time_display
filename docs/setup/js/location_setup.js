// Location Setup Module

document.addEventListener('DOMContentLoaded', () => {
    const locationSetupButton = document.getElementById('location-setup-button');
    if (locationSetupButton) {
        locationSetupButton.addEventListener('click', () => {
            if (window.startLocationSetup) {
                window.startLocationSetup();
            } else {
                window.showError('Location setup not initialized yet');
            }
        });
    }
});

// Location configuration functionality
window.startLocationSetup = async function() {
    try {
        const locationSetup = document.getElementById('location-setup');
        const button = document.getElementById('location-setup-button');
        
        if (!locationSetup) {
            throw new Error("Location setup element not found");
        }

        // Show location setup UI and hide the button
        locationSetup.style.display = 'block';
        button.style.display = 'none';

        // Get current location configuration
        const currentConfig = {};
        const configKeys = ['Coordinates_LAT', 'Coordinates_LNG', 'City', 'Country'];
        
        for (const key of configKeys) {
            try {
                const response = await window.setupDevice.send(JSON.stringify({
                    command: 'config_get',
                    config_type: 'display_env',
                    key: key
                }));
                
                if (response.status === 'success') {
                    currentConfig[key] = response.value;
                }
            } catch (error) {
                console.error(`Failed to get ${key}:`, error);
            }
        }

        // Render the location setup interface
        locationSetup.innerHTML = `
            <div class="location-setup-container">
                <h3>Location Configuration</h3>
                <p>Set your location coordinates using one of these methods:</p>
                
                <div class="location-form">
                    <form id="location-config-form" onsubmit="saveLocationConfig(event)">
                        <div class="coordinates-section">
                            <div class="form-group">
                                <label for="latitude">Latitude</label>
                                <input type="text" 
                                       id="latitude" 
                                       name="Coordinates_LAT" 
                                       value="${formatCoordinate(currentConfig.Coordinates_LAT)}"
                                       placeholder="e.g., 51.507351"
                                       pattern="-?\\d*\\.?\\d*"
                                       title="Enter a valid latitude (-90 to 90)"
                                       oninput="validateCoordinate(this, 'latitude')">
                                <small>Valid range: -90 to 90 degrees</small>
                            </div>
                            <div class="form-group">
                                <label for="longitude">Longitude</label>
                                <input type="text" 
                                       id="longitude" 
                                       name="Coordinates_LNG" 
                                       value="${formatCoordinate(currentConfig.Coordinates_LNG)}"
                                       placeholder="e.g., -0.127758"
                                       pattern="-?\\d*\\.?\\d*"
                                       title="Enter a valid longitude (-180 to 180)"
                                       oninput="validateCoordinate(this, 'longitude')">
                                <small>Valid range: -180 to 180 degrees</small>
                            </div>
                            
                            <div class="button-group">
                                <button type="button" onclick="getCurrentLocation()" class="location-button">
                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
                                        <path d="M256 0c17.7 0 32 14.3 32 32V66.7C368.4 80.1 431.9 143.6 445.3 224H480c17.7 0 32 14.3 32 32s-14.3 32-32 32H445.3C431.9 368.4 368.4 431.9 288 445.3V480c0 17.7-14.3 32-32 32s-32-14.3-32-32V445.3C143.6 431.9 80.1 368.4 66.7 288H32c-17.7 0-32-14.3-32-32s14.3-32 32-32H66.7C80.1 143.6 143.6 80.1 224 66.7V32c0-17.7 14.3-32 32-32zM128 256a128 128 0 1 0 256 0 128 128 0 1 0 -256 0zm128-80a80 80 0 1 1 0 160 80 80 0 1 1 0-160z"/>
                                    </svg>
                                    Get Current Location
                                </button>
                                <button type="button" onclick="showCityLookup()" class="location-button">
                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512">
                                        <path d="M215.7 499.2C267 435 384 279.4 384 192C384 86 298 0 192 0S0 86 0 192c0 87.4 117 243 168.3 307.2c12.3 15.3 35.1 15.3 47.4 0zM192 128a64 64 0 1 1 0 128 64 64 0 1 1 0-128z"/>
                                    </svg>
                                    Find My City
                                </button>
                                <button type="button" onclick="verifyCoordinates()" class="location-button">
                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
                                        <path d="M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM369 209L241 337c-9.4 9.4-24.6 9.4-33.9 0l-64-64c-9.4-9.4-9.4-24.6 0-33.9s24.6-9.4 33.9 0l47 47L335 175c9.4-9.4 24.6-9.4 33.9 0s9.4 24.6 0 33.9z"/>
                                    </svg>
                                    Verify My Coordinates
                                </button>
                            </div>
                            
                            <div id="location-accuracy" class="location-accuracy"></div>
                            <div id="coords-verification" class="verification-info"></div>
                        </div>

                        <div id="city-lookup" class="city-section" style="display: none;">
                            <h4>Find by City</h4>
                            <div class="form-group">
                                <label for="city">City Name</label>
                                <input type="text" 
                                       id="city" 
                                       placeholder="e.g., London">
                            </div>
                            <div class="form-group">
                                <label for="country">Country</label>
                                <input type="text" 
                                       id="country" 
                                       placeholder="e.g., United Kingdom or GB">
                                <small>Enter country name or code</small>
                            </div>
                            <button type="button" onclick="findCityCoordinates()" class="location-button">Find Coordinates</button>
                            <div id="city-verification" class="verification-info"></div>
                        </div>

                        <div class="button-group">
                            <button type="submit" class="primary">Save Location</button>
                        </div>
                    </form>
                </div>
            </div>
        `;

    } catch (error) {
        console.error('Failed to start location setup:', error);
        window.showError('Location Setup Error: ' + error.message);
    }
}

// Helper function to format coordinate values consistently
window.formatCoordinate = function(value) {
    if (!value) return '';
    // Ensure the value is a number and format it with a decimal point
    return Number(value).toString().replace(',', '.');
}

/**
 * Calculates the precision of latitude and longitude for a given number of decimal places and latitude.
 * @param {number} latitude - The latitude at which to calculate the precision.
 * @param {number} decimalPlaces - The number of decimal places for the coordinate.
 * @returns {object} An object containing latitude and longitude precision in meters.
 */
window.calculateGPSPrecision = function(latitude, decimalPlaces) {
    const EARTH_RADIUS_KM = 6371; // Mean radius of the Earth in kilometers
    const METERS_PER_DEGREE_LATITUDE = (2 * Math.PI * EARTH_RADIUS_KM * 1000) / 360; // ~111,320 meters
    
    // Convert latitude to radians for cosine calculation
    const latInRadians = (latitude * Math.PI) / 180;
    
    // Distance per degree of longitude
    const metersPerDegreeLongitude = METERS_PER_DEGREE_LATITUDE * Math.cos(latInRadians);
    
    // Precision for latitude and longitude
    const precisionLat = METERS_PER_DEGREE_LATITUDE / Math.pow(10, decimalPlaces);
    const precisionLon = metersPerDegreeLongitude / Math.pow(10, decimalPlaces);
    
    return {
        latitudePrecision: precisionLat,
        longitudePrecision: precisionLon
    };
}

// Helper function to format distance in a human-readable way
window.formatDistance = function(meters) {
    if (meters >= 1000) {
        return `≈ ${(meters/1000).toFixed(2)} km`;
    } else if (meters >= 1) {
        return `≈ ${Math.round(meters)} m`;
    } else if (meters >= 0.01) {
        return `≈ ${(meters * 100).toFixed(1)} cm`;
    } else {
        return `≈ ${(meters * 1000).toFixed(1)} mm`;
    }
}

// Helper function to calculate coordinate precision
window.calculatePrecision = function(value, type, otherValue) {
    if (!value) return '';
    
    // Convert to string and clean up
    const str = value.toString().replace(',', '.');
    
    // Find number of decimal places
    const decimalPlaces = str.includes('.') ? str.split('.')[1].length : 0;
    
    // For longitude precision, we need the latitude
    let precision;
    if (type === 'longitude' && otherValue) {
        // Calculate actual precision based on latitude
        const gps = calculateGPSPrecision(Number(otherValue), decimalPlaces);
        precision = formatDistance(gps.longitudePrecision);
    } else {
        // Calculate latitude precision or fallback for longitude if no latitude available
        const gps = calculateGPSPrecision(0, decimalPlaces); // Use equator as fallback
        precision = formatDistance(type === 'latitude' ? gps.latitudePrecision : gps.longitudePrecision);
    }
    
    return `Precision with ${decimalPlaces} decimal places: ${precision}`;
}

// Update the validateCoordinate function to only show range
window.validateCoordinate = function(input, type) {
    // Clear any existing GPS accuracy info since we're manually editing
    const accuracyDiv = document.getElementById('location-accuracy');
    if (accuracyDiv) {
        accuracyDiv.innerHTML = '';
        accuracyDiv.classList.remove('active');
    }

    // Replace any commas with periods for consistency
    let value = input.value.replace(',', '.');
    input.value = value;

    // Convert to number for validation
    value = Number(value);
    
    if (isNaN(value)) {
        input.setCustomValidity('Please enter a valid number');
        input.nextElementSibling.textContent = type === 'latitude' ? 
            'Valid range: -90 to 90 degrees' : 
            'Valid range: -180 to 180 degrees';
        return false;
    }

    // Check range based on coordinate type
    if (type === 'latitude' && (value < -90 || value > 90)) {
        input.setCustomValidity('Latitude must be between -90 and 90 degrees');
        return false;
    }
    if (type === 'longitude' && (value < -180 || value > 180)) {
        input.setCustomValidity('Longitude must be between -180 and 180 degrees');
        return false;
    }

    input.setCustomValidity('');
    input.nextElementSibling.textContent = type === 'latitude' ? 
        'Valid range: -90 to 90 degrees' : 
        'Valid range: -180 to 180 degrees';
    
    return true;
}

// Show/hide city lookup section
window.showCityLookup = function() {
    const cityLookup = document.getElementById('city-lookup');
    cityLookup.style.display = cityLookup.style.display === 'none' ? 'block' : 'none';
}

// Find coordinates for a city
window.findCityCoordinates = async function() {
    const city = document.getElementById('city').value.trim();
    const country = document.getElementById('country').value.trim();
    const verificationDiv = document.getElementById('city-verification');
    
    // Clear any existing GPS accuracy info since we're using city lookup
    const accuracyDiv = document.getElementById('location-accuracy');
    if (accuracyDiv) {
        accuracyDiv.innerHTML = '';
        accuracyDiv.classList.remove('active');
    }

    // Create verification div if it doesn't exist
    if (!verificationDiv) {
        const cityLookup = document.getElementById('city-lookup');
        if (cityLookup) {
            const div = document.createElement('div');
            div.id = 'city-verification';
            div.className = 'verification-info';
            cityLookup.appendChild(div);
        } else {
            console.error('Could not find city lookup section');
            return;
        }
    }
    
    if (city && country) {
        try {
            document.getElementById('city-verification').innerHTML = '<div class="status-info">Looking up coordinates...</div>';
            const location = await geocodeLocation(city, country);
            
            // Update coordinate fields
            document.getElementById('latitude').value = location.lat;
            document.getElementById('longitude').value = location.lon;
            
            // Validate coordinates
            validateCoordinate(document.getElementById('latitude'), 'latitude');
            validateCoordinate(document.getElementById('longitude'), 'longitude');
            
            document.getElementById('city-verification').innerHTML = `
                <div class="status-success">
                    Found coordinates for:<br>
                    ${location.display_name}
                </div>
            `;
        } catch (error) {
            document.getElementById('city-verification').innerHTML = `
                <div class="status-error">
                    Could not find coordinates: ${error.message}
                </div>
            `;
        }
    } else {
        document.getElementById('city-verification').innerHTML = `
            <div class="status-error">
                Please enter both city name and country
            </div>
        `;
    }
}

// Verify coordinates
window.verifyCoordinates = async function() {
    const lat = Number(document.getElementById('latitude').value);
    const lon = Number(document.getElementById('longitude').value);
    const verificationDiv = document.getElementById('coords-verification');
    
    // Create verification div if it doesn't exist
    if (!verificationDiv) {
        const coordsSection = document.querySelector('.coordinates-section');
        if (coordsSection) {
            const div = document.createElement('div');
            div.id = 'coords-verification';
            div.className = 'verification-info';
            coordsSection.appendChild(div);
        } else {
            console.error('Could not find coordinates section');
            return;
        }
    }
    
    if (!isNaN(lat) && !isNaN(lon) && 
        lat >= -90 && lat <= 90 && 
        lon >= -180 && lon <= 180) {
        try {
            document.getElementById('coords-verification').innerHTML = '<div class="status-info">Verifying location...</div>';
            const location = await reverseGeocodeLocation(lat, lon);
            document.getElementById('coords-verification').innerHTML = `
                <div class="status-success">
                    These coordinates point to:<br>
                    ${location.display_name}
                </div>
            `;
        } catch (error) {
            document.getElementById('coords-verification').innerHTML = `
                <div class="status-error">
                    Could not verify these coordinates: ${error.message}
                </div>
            `;
        }
    } else {
        document.getElementById('coords-verification').innerHTML = `
            <div class="status-error">
                Please enter valid coordinates
            </div>
        `;
    }
}

// Update saveLocationConfig to only save coordinates
window.saveLocationConfig = async function(event) {
    event.preventDefault();
    
    const lat = document.getElementById('latitude').value;
    const lng = document.getElementById('longitude').value;
    let success = true;

    // Validate coordinates before saving
    if (!validateCoordinate(document.getElementById('latitude'), 'latitude') ||
        !validateCoordinate(document.getElementById('longitude'), 'longitude')) {
        return;
    }

    try {
        // Save latitude
        const latResponse = await window.setupDevice.send(JSON.stringify({
            command: 'config_set',
            config_type: 'display_env',
            key: 'Coordinates_LAT',
            value: lat.replace(',', '.')
        }));

        // Save longitude
        const lngResponse = await window.setupDevice.send(JSON.stringify({
            command: 'config_set',
            config_type: 'display_env',
            key: 'Coordinates_LNG',
            value: lng.replace(',', '.')
        }));

        if (latResponse.status !== 'success' || lngResponse.status !== 'success') {
            success = false;
            window.showError('Failed to update coordinates');
        }

        // Clear city/country fields if they exist
        const cityInput = document.getElementById('city');
        const countryInput = document.getElementById('country');
        if (cityInput) cityInput.value = '';
        if (countryInput) countryInput.value = '';

        if (success) {
            window.showMessage('Location coordinates saved successfully');
            // Hide city lookup section
            document.getElementById('city-lookup').style.display = 'none';
        }
    } catch (error) {
        console.error('Failed to save coordinates:', error);
        window.showError(`Failed to save coordinates: ${error.message}`);
    }
}

// Add debounce function for API calls
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Handle coordinate changes
window.handleCoordinateChange = debounce(async function() {
    const lat = Number(document.getElementById('latitude').value);
    const lon = Number(document.getElementById('longitude').value);
    const verificationDiv = document.getElementById('coords-verification');
    
    if (!isNaN(lat) && !isNaN(lon) && 
        lat >= -90 && lat <= 90 && 
        lon >= -180 && lon <= 180) {
        try {
            verificationDiv.innerHTML = '<div class="status-info">Verifying location...</div>';
            const location = await reverseGeocodeLocation(lat, lon);
            verificationDiv.innerHTML = `
                <div class="status-success">
                    These coordinates correspond to:<br>
                    ${location.display_name}
                </div>
            `;
            await crossVerifyInputs();
        } catch (error) {
            verificationDiv.innerHTML = `
                <div class="status-error">
                    Could not verify these coordinates: ${error.message}
                </div>
            `;
        }
    } else {
        verificationDiv.innerHTML = '';
    }
}, 1000);

// Handle city/country changes
window.handleCityCountryChange = debounce(async function() {
    const city = document.getElementById('city').value.trim();
    const country = document.getElementById('country').value.trim();
    const verificationDiv = document.getElementById('city-verification');
    
    if (city && country && country.length === 2) {
        try {
            verificationDiv.innerHTML = '<div class="status-info">Verifying location...</div>';
            const location = await geocodeLocation(city, country);
            verificationDiv.innerHTML = `
                <div class="status-success">
                    Found location at:<br>
                    ${location.display_name}
                </div>
            `;
            await crossVerifyInputs();
        } catch (error) {
            verificationDiv.innerHTML = `
                <div class="status-error">
                    Could not verify this location: ${error.message}
                </div>
            `;
        }
    } else {
        verificationDiv.innerHTML = '';
    }
}, 1000);

// Cross-verify all inputs
async function crossVerifyInputs() {
    const lat = Number(document.getElementById('latitude').value);
    const lon = Number(document.getElementById('longitude').value);
    const city = document.getElementById('city').value.trim();
    const country = document.getElementById('country').value.trim();
    const crossVerificationDiv = document.getElementById('cross-verification');

    // Only cross-verify if we have both coordinate and city/country data
    if (!isNaN(lat) && !isNaN(lon) && city && country) {
        try {
            const result = await crossVerifyLocation({ lat, lon, city, country });
            
            if (result.match) {
                crossVerificationDiv.innerHTML = `
                    <div class="status-success">
                        ✓ The coordinates and city/country information match!
                    </div>
                `;
            } else {
                const distance = result.details.distance.toFixed(1);
                const cityMatch = result.details.cityMatch ? '✓' : '✗';
                const countryMatch = result.details.countryMatch ? '✓' : '✗';
                
                crossVerificationDiv.innerHTML = `
                    <div class="status-warning">
                        ⚠️ Location Mismatch Details:<br>
                        • Coordinates point to: ${result.details.fromCoords.display_name}<br>
                        • City/Country resolves to coordinates: (${result.details.fromCity.lat}, ${result.details.fromCity.lon})<br>
                        • Distance between points: ${distance} km<br>
                        • City match: ${cityMatch} ${result.details.fromCoords.city || 'Unknown'} vs ${city}<br>
                        • Country match: ${countryMatch} ${result.details.fromCoords.country_code || 'Unknown'} vs ${country}
                    </div>
                `;
            }
        } catch (error) {
            crossVerificationDiv.innerHTML = `
                <div class="status-error">
                    Could not cross-verify locations: ${error.message}
                </div>
            `;
        }
    } else {
        crossVerificationDiv.innerHTML = '';
    }
}

// Update getCurrentLocation to show both accuracy and precision
window.getCurrentLocation = function() {
    if (!navigator.geolocation) {
        window.showError('Geolocation is not supported by your browser');
        return;
    }

    navigator.geolocation.getCurrentPosition(
        async (position) => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            
            // Format coordinates consistently with decimal points
            document.getElementById('latitude').value = lat.toString().replace(',', '.');
            document.getElementById('longitude').value = lng.toString().replace(',', '.');
            
            // Validate coordinates
            validateCoordinate(document.getElementById('latitude'), 'latitude');
            validateCoordinate(document.getElementById('longitude'), 'longitude');
            
            // Show accuracy and precision if available
            if (position.coords.accuracy) {
                const accuracy = Math.round(position.coords.accuracy);
                const latPrecision = calculateGPSPrecision(lat, lat.toString().split('.')[1]?.length || 0);
                const accuracyDiv = document.getElementById('location-accuracy');
                accuracyDiv.innerHTML = `
                    <div class="accuracy-info">
                        <strong>Location Data Quality:</strong><br>
                        • Your actual location is within ±${accuracy} meters of these coordinates<br>
                        • At this latitude, each decimal place in coordinates represents ${formatDistance(latPrecision.latitudePrecision)} North/South and ${formatDistance(latPrecision.longitudePrecision)} East/West
                    </div>
                `;
                accuracyDiv.classList.add('active');
            }

            // Verify the coordinates
            try {
                const verificationDiv = document.getElementById('coords-verification');
                if (!verificationDiv) {
                    const coordsSection = document.querySelector('.coordinates-section');
                    if (coordsSection) {
                        const div = document.createElement('div');
                        div.id = 'coords-verification';
                        div.className = 'verification-info';
                        coordsSection.appendChild(div);
                    }
                }
                
                if (document.getElementById('coords-verification')) {
                    document.getElementById('coords-verification').innerHTML = '<div class="status-info">Verifying location...</div>';
                    const location = await reverseGeocodeLocation(lat, lng);
                    document.getElementById('coords-verification').innerHTML = `
                        <div class="status-success">
                            These coordinates point to:<br>
                            ${location.display_name}
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Verification error:', error);
                if (document.getElementById('coords-verification')) {
                    document.getElementById('coords-verification').innerHTML = `
                        <div class="status-error">
                            Could not verify these coordinates: ${error.message}
                        </div>
                    `;
                }
            }
        },
        (error) => {
            window.showError('Error getting location: ' + error.message);
        },
        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        }
    );
} 
// Nominatim API Module

// Base URL for Nominatim API
const NOMINATIM_BASE_URL = 'https://nominatim.openstreetmap.org';

/**
 * Forward geocoding - get coordinates from city and country
 * @param {string} city - City name
 * @param {string} country - Two-letter country code
 * @returns {Promise<{lat: number, lon: number, display_name: string}>}
 */
window.geocodeLocation = async function(city, country) {
    const params = new URLSearchParams({
        q: `${city}, ${country}`,
        format: 'json',
        limit: 1,
        addressdetails: 1
    });

    try {
        const response = await fetch(`${NOMINATIM_BASE_URL}/search?${params}`, {
            headers: {
                'Accept': 'application/json',
                'User-Agent': 'RPi-Display-Setup'
            }
        });

        if (!response.ok) {
            throw new Error('Geocoding failed');
        }

        const data = await response.json();
        if (!data || data.length === 0) {
            throw new Error('Location not found');
        }

        return {
            lat: parseFloat(data[0].lat),
            lon: parseFloat(data[0].lon),
            display_name: data[0].display_name
        };
    } catch (error) {
        console.error('Geocoding error:', error);
        throw error;
    }
}

/**
 * Reverse geocoding - get location details from coordinates
 * @param {number} lat - Latitude
 * @param {number} lon - Longitude
 * @returns {Promise<{city: string, country_code: string, display_name: string}>}
 */
window.reverseGeocodeLocation = async function(lat, lon) {
    const params = new URLSearchParams({
        lat: lat,
        lon: lon,
        format: 'json',
        addressdetails: 1
    });

    try {
        const response = await fetch(`${NOMINATIM_BASE_URL}/reverse?${params}`, {
            headers: {
                'Accept': 'application/json',
                'User-Agent': 'RPi-Display-Setup'
            }
        });

        if (!response.ok) {
            throw new Error('Reverse geocoding failed');
        }

        const data = await response.json();
        if (!data) {
            throw new Error('Location not found');
        }

        return {
            city: data.address.city || data.address.town || data.address.village || data.address.municipality,
            country_code: data.address.country_code?.toUpperCase(),
            display_name: data.display_name
        };
    } catch (error) {
        console.error('Reverse geocoding error:', error);
        throw error;
    }
}

/**
 * Cross-verify location data
 * @param {Object} params - Location parameters
 * @param {number} [params.lat] - Latitude
 * @param {number} [params.lon] - Longitude
 * @param {string} [params.city] - City name
 * @param {string} [params.country] - Country code
 * @returns {Promise<{match: boolean, details: Object}>}
 */
window.crossVerifyLocation = async function({ lat, lon, city, country }) {
    let coordsLocation, cityLocation;
    let details = {};

    try {
        // Get location details from coordinates
        if (typeof lat === 'number' && typeof lon === 'number') {
            coordsLocation = await reverseGeocodeLocation(lat, lon);
            details.fromCoords = coordsLocation;
        }

        // Get coordinates from city and country
        if (city && country) {
            cityLocation = await geocodeLocation(city, country);
            details.fromCity = cityLocation;
        }

        // If we have both, check if they match
        if (coordsLocation && cityLocation) {
            // Calculate distance between the entered coordinates and the city's coordinates
            const distance = calculateDistance(
                lat, lon,
                cityLocation.lat, cityLocation.lon
            );

            details.distance = distance;
            
            // Consider it a match if:
            // 1. Distance is less than 10km OR
            // 2. The city names match (accounting for variations)
            const cityMatch = coordsLocation.city?.toLowerCase() === city.toLowerCase();
            const countryMatch = coordsLocation.country_code?.toLowerCase() === country.toLowerCase();
            
            details.match = distance < 10 || (cityMatch && countryMatch);
            details.cityMatch = cityMatch;
            details.countryMatch = countryMatch;
        }

        return {
            match: details.match,
            details: details
        };
    } catch (error) {
        console.error('Cross-verification error:', error);
        throw error;
    }
}

/**
 * Calculate distance between two points using Haversine formula
 * @param {number} lat1 - First latitude
 * @param {number} lon1 - First longitude
 * @param {number} lat2 - Second latitude
 * @param {number} lon2 - Second longitude
 * @returns {number} Distance in kilometers
 */
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // Earth's radius in km
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = 
        Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * 
        Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
}

function toRad(degrees) {
    return degrees * (Math.PI / 180);
}

// Add a small delay between API calls to respect rate limits
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
} 
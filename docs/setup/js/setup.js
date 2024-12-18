// Setup wizard functionality
async function startBasicSetup() {
    try {
        // Get current configuration
        const response = await displayDevice.sendCommand(0x01); // GET_CONFIG
        const config = JSON.parse(new TextDecoder().decode(response.data));
        
        // Show configuration form
        // TODO: Implement form UI
        console.log('Current config:', config);
    } catch (error) {
        console.error('Failed to start basic setup:', error);
        alert('Failed to get current configuration. Please try reconnecting the device.');
    }
}

async function startTransitSetup() {
    try {
        // Get current transit configuration
        const response = await displayDevice.sendCommand(0x02); // GET_TRANSIT_CONFIG
        const config = JSON.parse(new TextDecoder().decode(response.data));
        
        // Show transit configuration form
        // TODO: Implement form UI
        console.log('Current transit config:', config);
    } catch (error) {
        console.error('Failed to start transit setup:', error);
        alert('Failed to get transit configuration. Please try reconnecting the device.');
    }
}

async function startWeatherSetup() {
    try {
        // Get current weather configuration
        const response = await displayDevice.sendCommand(0x03); // GET_WEATHER_CONFIG
        const config = JSON.parse(new TextDecoder().decode(response.data));
        
        // Show weather configuration form
        // TODO: Implement form UI
        console.log('Current weather config:', config);
    } catch (error) {
        console.error('Failed to start weather setup:', error);
        alert('Failed to get weather configuration. Please try reconnecting the device.');
    }
}

async function reviewSetup() {
    try {
        // Get all configuration
        const response = await displayDevice.sendCommand(0x04); // GET_ALL_CONFIG
        const config = JSON.parse(new TextDecoder().decode(response.data));
        
        // Show review UI
        // TODO: Implement review UI
        console.log('Full config:', config);
    } catch (error) {
        console.error('Failed to get configuration for review:', error);
        alert('Failed to get configuration. Please try reconnecting the device.');
    }
}

// Check WebUSB support on load
document.addEventListener('DOMContentLoaded', () => {
    const supportText = document.getElementById('webusb-support');
    if (navigator.usb) {
        supportText.textContent = 'Click the button below to connect your Raspberry Pi';
    } else {
        supportText.textContent = 'WebUSB is not supported in this browser. Please use Chrome or Edge.';
        document.querySelector('button').disabled = true;
    }
}); 
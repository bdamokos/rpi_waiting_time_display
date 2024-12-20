// Setup wizard functionality
window.startBasicSetup = async function() {
    try {
        if (!window.setupDevice || !window.setupDevice.connected) {
            throw new Error("Device not connected");
        }
        
        await window.setupDevice.send(JSON.stringify({
            command: 'basic_setup'
        }));
    } catch (error) {
        console.error('Failed to start basic setup:', error);
        window.showError('Failed to start basic setup: ' + error.message);
    }
}

window.startTransitSetup = async function() {
    try {
        if (!window.setupDevice || !window.setupDevice.connected) {
            throw new Error("Device not connected");
        }
        
        await window.setupDevice.send(JSON.stringify({
            command: 'transit_setup'
        }));
    } catch (error) {
        console.error('Failed to start transit setup:', error);
        window.showError('Failed to start transit setup: ' + error.message);
    }
}

window.startWeatherSetup = async function() {
    try {
        if (!window.setupDevice || !window.setupDevice.connected) {
            throw new Error("Device not connected");
        }
        
        await window.setupDevice.send(JSON.stringify({
            command: 'weather_setup'
        }));
    } catch (error) {
        console.error('Failed to start weather setup:', error);
        window.showError('Failed to start weather setup: ' + error.message);
    }
}

window.reviewSetup = async function() {
    try {
        if (!window.setupDevice || !window.setupDevice.connected) {
            throw new Error("Device not connected");
        }
        
        await window.setupDevice.send(JSON.stringify({
            command: 'review_setup'
        }));
    } catch (error) {
        console.error('Failed to get configuration for review:', error);
        window.showError('Failed to start review: ' + error.message);
    }
}
 
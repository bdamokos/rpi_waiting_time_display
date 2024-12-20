// WiFi configuration functionality
window.startWiFiSetup = async function() {
    try {
        // Use the global setupDevice instance
        if (!window.setupDevice || !window.setupDevice.connected) {
            throw new Error("Device not connected");
        }

        const wifiNetworks = document.getElementById('wifi-networks');
        if (!wifiNetworks) {
            throw new Error("WiFi networks element not found");
        }

        // Show WiFi setup UI first
        wifiNetworks.style.display = 'block';

        // Scan for networks
        await window.setupDevice.send(JSON.stringify({
            command: 'wifi_scan'
        }));

        // Get saved networks
        await window.setupDevice.send(JSON.stringify({
            command: 'wifi_saved'
        }));

    } catch (error) {
        console.error('Failed to start WiFi setup:', error);
        window.showError('WiFi Setup Error: ' + error.message);
    }
}

window.connectToNetwork = async function(ssid) {
    try {
        const password = prompt(`Enter password for ${ssid}:`);
        if (password === null) return; // User cancelled

        await window.setupDevice.send(JSON.stringify({
            command: 'wifi_connect',
            ssid: ssid,
            password: password
        }));
    } catch (error) {
        console.error('Failed to connect:', error);
        window.showError('Connection Error: ' + error.message);
    }
}

window.forgetNetwork = async function(uuid) {
    try {
        if (confirm('Are you sure you want to forget this network?')) {
            await window.setupDevice.send(JSON.stringify({
                command: 'wifi_forget',
                uuid: uuid
            }));
        }
    } catch (error) {
        console.error('Failed to forget network:', error);
        window.showError('Error: ' + error.message);
    }
}

// Add styles for WiFi setup
const style = document.createElement('style');
style.textContent = `
    .network-list, .saved-network-list {
        margin: 1em 0;
        max-height: 300px;
        overflow-y: auto;
    }
    
    .network-item {
        display: flex;
        align-items: center;
        padding: 0.5em;
        border-bottom: 1px solid #eee;
    }
    
    .network-name {
        flex-grow: 1;
        margin-right: 1em;
    }
    
    .network-signal {
        margin-right: 1em;
        color: #666;
    }
    
    .error {
        color: red;
        margin: 1em 0;
    }
    
    .network-controls {
        margin-top: 1em;
        text-align: center;
    }
    
    .refresh-button {
        background-color: #4CAF50;
        color: white;
        padding: 10px 20px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
    }
    
    .refresh-button:hover {
        background-color: #45a049;
    }
`;
document.head.appendChild(style); 
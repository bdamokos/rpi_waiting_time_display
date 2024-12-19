// WiFi configuration functionality
async function startWiFiSetup() {
    try {
        // Get available networks
        const response = await displayDevice.sendCommand(0x10);
        const networks = JSON.parse(new TextDecoder().decode(response.data));
        
        // Get saved networks
        const savedResponse = await displayDevice.sendCommand(0x11);
        const savedNetworks = JSON.parse(new TextDecoder().decode(savedResponse.data));
        
        // Show WiFi setup form
        showWiFiSetupForm(networks, savedNetworks);
    } catch (error) {
        console.error('Failed to start WiFi setup:', error);
        alert('Failed to get WiFi networks. Please try reconnecting the device.');
    }
}

function showWiFiSetupForm(networks, savedNetworks) {
    const setupDiv = document.getElementById('wifi-setup');
    if (!setupDiv) return;
    
    // Create HTML for available networks
    let html = `
        <h2>Available Networks</h2>
        <div class="network-list">
    `;
    
    if (networks.error) {
        html += `<p class="error">${networks.error}</p>`;
    } else if (networks.networks && networks.networks.length > 0) {
        networks.networks.forEach(network => {
            html += `
                <div class="network-item">
                    <span class="network-name">${network.ssid}</span>
                    <span class="network-signal">${network.signal}%</span>
                    <button onclick="connectToNetwork('${network.ssid}', ${network.security})">
                        Connect
                    </button>
                </div>
            `;
        });
    } else {
        html += '<p>No networks found</p>';
    }
    
    html += '</div>';
    
    // Add saved networks section
    html += `
        <h2>Saved Networks</h2>
        <div class="saved-network-list">
    `;
    
    if (savedNetworks.error) {
        html += `<p class="error">${savedNetworks.error}</p>`;
    } else if (savedNetworks.saved_networks && savedNetworks.saved_networks.length > 0) {
        savedNetworks.saved_networks.forEach(network => {
            html += `
                <div class="network-item">
                    <span class="network-name">${network.ssid}</span>
                    <button onclick="forgetNetwork('${network.uuid}')">
                        Forget
                    </button>
                </div>
            `;
        });
    } else {
        html += '<p>No saved networks</p>';
    }
    
    html += '</div>';
    
    // Add refresh button
    html += `
        <div class="network-controls">
            <button onclick="startWiFiSetup()" class="refresh-button">
                Refresh Networks
            </button>
        </div>
    `;
    
    setupDiv.innerHTML = html;
}

async function connectToNetwork(ssid, requiresPassword) {
    let password = '';
    if (requiresPassword) {
        password = prompt(`Enter password for ${ssid}:`);
        if (!password) return;  // User cancelled
    }
    
    try {
        const response = await displayDevice.sendCommand(0x12, JSON.stringify({
            ssid: ssid,
            password: password
        }));
        
        const result = JSON.parse(new TextDecoder().decode(response.data));
        if (result.error) {
            alert(`Failed to connect: ${result.error}`);
        } else {
            alert(`Successfully connected to ${ssid}`);
            // Refresh the network list
            startWiFiSetup();
        }
    } catch (error) {
        console.error('Failed to connect:', error);
        alert('Failed to connect to network. Please try again.');
    }
}

async function forgetNetwork(uuid) {
    if (!confirm('Are you sure you want to remove this network?')) return;
    
    try {
        const response = await displayDevice.sendCommand(0x13, JSON.stringify({
            uuid: uuid
        }));
        
        const result = JSON.parse(new TextDecoder().decode(response.data));
        if (result.error) {
            alert(`Failed to remove network: ${result.error}`);
        } else {
            // Refresh the network list
            startWiFiSetup();
        }
    } catch (error) {
        console.error('Failed to forget network:', error);
        alert('Failed to remove network. Please try again.');
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
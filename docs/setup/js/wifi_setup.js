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

        // Show WiFi setup UI
        wifiNetworks.style.display = 'block';

        // Request network scan
        await window.setupDevice.send(JSON.stringify({
            command: 'wifi_scan'
        }));

        // Request saved networks
        await window.setupDevice.send(JSON.stringify({
            command: 'wifi_saved'
        }));

    } catch (error) {
        console.error('Failed to start WiFi setup:', error);
        window.showError('WiFi Setup Error: ' + error.message);
    }
}

window.connectToNetwork = async function(ssid, requiresPassword = true) {
    if (requiresPassword) {
        showPasswordPrompt(ssid);
    } else {
        await sendConnectCommand(ssid, '');
    }
}

window.forgetNetwork = async function(uuid) {
    try {
        const response = await window.setupDevice.send(JSON.stringify({
            command: 'wifi_forget',
            uuid: uuid
        }));
        
        if (response.status === 'success') {
            window.showMessage('Network forgotten');
            startWiFiSetup(); // Refresh the network lists
        } else {
            throw new Error(response.message || 'Failed to forget network');
        }
    } catch (error) {
        console.error('Failed to forget network:', error);
        window.showError('Failed to forget network: ' + error.message);
    }
}

function showPasswordPrompt(ssid) {
    const prompt = document.createElement('div');
    prompt.className = 'wifi-password-prompt';
    prompt.innerHTML = `
        <h3>Connect to ${ssid}</h3>
        <div class="input-group">
            <input type="password" id="wifi-password" placeholder="Enter password">
        </div>
        <div class="button-group">
            <button class="cancel" onclick="closePasswordPrompt()">Cancel</button>
            <button class="connect" onclick="submitPassword('${ssid}')">Connect</button>
        </div>
    `;
    document.body.appendChild(prompt);

    // Focus the password input
    document.getElementById('wifi-password').focus();
}

window.closePasswordPrompt = function() {
    const prompt = document.querySelector('.wifi-password-prompt');
    if (prompt) {
        prompt.remove();
    }
}

window.submitPassword = async function(ssid) {
    const passwordInput = document.getElementById('wifi-password');
    const password = passwordInput.value;
    closePasswordPrompt();
    await sendConnectCommand(ssid, password);
}

async function sendConnectCommand(ssid, password) {
    try {
        const response = await window.setupDevice.send(JSON.stringify({
            command: 'wifi_connect',
            ssid: ssid,
            password: password
        }));
        
        if (response.status === 'success') {
            window.showMessage(`Connecting to ${ssid}...`);
        } else {
            throw new Error(response.message || 'Failed to connect');
        }
    } catch (error) {
        console.error('Failed to connect:', error);
        window.showError('Failed to connect: ' + error.message);
    }
} 
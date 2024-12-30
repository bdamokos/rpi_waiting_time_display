// Initialize all event listeners when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Advanced setup button
    const advancedSetupButton = document.getElementById('advanced-setup-button');
    if (advancedSetupButton) {
        advancedSetupButton.addEventListener('click', startAdvancedSetup);
    }

    // Debug server button
    const debugButton = document.getElementById('debug-button');
    if (debugButton) {
        debugButton.addEventListener('click', openDebugServer);
    }
    
    // Add other event listeners here as needed
});

async function openDebugServer() {
    if (!window.setupDevice || !window.setupDevice.connected) {
        window.showError('Device not connected');
        return;
    }

    try {
        // Get debug server settings
        const debugPortResponse = await window.setupDevice.send(JSON.stringify({
            command: 'config_get',
            config_type: 'display_env',
            key: 'debug_port'
        }));
        const debugEnabledResponse = await window.setupDevice.send(JSON.stringify({
            command: 'config_get',
            config_type: 'display_env',
            key: 'debug_port_enabled'
        }));

        // Get local IP
        const ipResponse = await window.setupDevice.send(JSON.stringify({
            command: 'get_ip'
        }));

        console.log('Debug responses:', { debugPortResponse, debugEnabledResponse, ipResponse });

        // Check if debug server is enabled
        if (debugEnabledResponse.status === 'success' && debugEnabledResponse.value.toLowerCase() !== 'true') {
            window.showError('Debug server is not enabled. Please enable it in the advanced settings.');
            return;
        }

        // Construct and open URL
        const port = debugPortResponse.status === 'success' ? debugPortResponse.value : '5002';  // Default to 5002 if not set
        const ip = ipResponse.status === 'success' ? ipResponse.ip : null;
        
        if (!ip) {
            window.showError('Could not get device IP address');
            return;
        }

        // Construct URL
        const httpUrl = `http://${ip}:${port}/debug`;
        console.log('Debug server URL:', httpUrl);

        // Check if using Chrome
        const isChrome = /Chrome/.test(navigator.userAgent) && !/Edge/.test(navigator.userAgent);
        
        if (isChrome) {
            // Try to fetch the debug page first to test connectivity
            try {
                const response = await fetch(httpUrl, {
                    method: 'GET',
                    mode: 'cors',
                    credentials: 'include',
                });
                if (response.ok) {
                    window.open(httpUrl, '_blank');
                    return;
                }
            } catch (error) {
                console.log('Fetch test failed:', error);
            }

            // If fetch failed, show the modal with alternative options
            const modal = document.createElement('div');
            modal.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                z-index: 1000;
                max-width: 600px;
                width: 90%;
            `;

            const overlay = document.createElement('div');
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.5);
                z-index: 999;
            `;

            modal.innerHTML = `
                <h3 style="margin-top: 0;">Debug Server Access</h3>
                <p>Chrome's security policies are preventing direct access. Here are your options:</p>
                
                <div style="background: #fff3cd; padding: 15px; border-radius: 4px; margin: 10px 0;">
                    <strong>Option 1: Enable Insecure Private Network Access</strong>
                    <ol style="margin: 10px 0 5px 25px; padding-right: 10px;">
                        <li style="margin-bottom: 8px;">Open a new tab and go to: <code>chrome://flags/#block-insecure-private-network-requests</code></li>
                        <li style="margin-bottom: 8px;">Set "Block insecure private network requests" to <strong>Disabled</strong></li>
                        <li style="margin-bottom: 8px;">Click "Relaunch" at the bottom</li>
                        <li style="margin-bottom: 8px;">Try the debug server button again</li>
                        <li style="margin-bottom: 0;">Don't forget to set it back to "Enabled" after you're done</li>
                    </ol>
                </div>

                <p><strong>Option 2: Try this URL manually:</strong></p>
                <pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; user-select: text; overflow-x: auto;">${httpUrl}</pre>

                <p><strong>Option 3: Use Firefox or Safari</strong></p>

                <p><strong>Troubleshooting:</strong></p>
                <ul style="margin-bottom: 20px;">
                    <li>Make sure you're on the same network as the device</li>
                    <li>Check if port ${port} is not blocked by your firewall</li>
                    <li>Try accessing the debug server from another device on the network</li>
                </ul>
                <button onclick="this.parentElement.remove(); document.querySelector('#debug-overlay').remove();" style="padding: 8px 16px; background: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer;">Close</button>
                <button onclick="navigator.clipboard.writeText('${httpUrl}').then(() => window.showMessage('URL copied to clipboard'));" style="padding: 8px 16px; background: #4CAF50; color: white; border: none; border-radius: 4px; margin-left: 10px; cursor: pointer;">Copy URL</button>
            `;

            overlay.id = 'debug-overlay';
            document.body.appendChild(overlay);
            document.body.appendChild(modal);
        } else {
            // For other browsers, open directly
            window.open(httpUrl, '_blank');
        }

    } catch (error) {
        console.error('Failed to open debug server:', error);
        window.showError('Failed to open debug server: ' + error.message);
    }
}

// Function to update connection status
function updateConnectionStatus(status, message) {
    const statusElement = document.getElementById('serial-support');
    const connectButton = document.getElementById('connect-button');
    const errorElement = document.getElementById('connection-error');

    // Remove all status classes
    statusElement.classList.remove('initial', 'success', 'error');
    connectButton.classList.remove('initial', 'success', 'error');
    errorElement.classList.remove('visible');

    // Add appropriate class based on status
    statusElement.classList.add(status);
    connectButton.classList.add(status);
    statusElement.textContent = message;

    if (status === 'error') {
        errorElement.textContent = message;
        errorElement.classList.add('visible');
    }
}

// Check WebSerial support when page loads
if ('serial' in navigator) {
    updateConnectionStatus('success', 'WebSerial is supported. Click Connect to begin.');
} else {
    updateConnectionStatus('error', 'WebSerial is not supported in your browser. Please use Chrome or Edge.');
}

// Handle connection button click
document.getElementById('connect-button').addEventListener('click', async () => {
    try {
        // Your existing connection code here
        // When connection starts:
        updateConnectionStatus('initial', 'Connecting to device...');
        
        // On successful connection:
        updateConnectionStatus('success', 'Connected successfully!');
        
        // On connection error:
        // updateConnectionStatus('error', 'Failed to connect: ' + error.message);
    } catch (error) {
        updateConnectionStatus('error', 'Failed to connect: ' + error.message);
    }
});
 
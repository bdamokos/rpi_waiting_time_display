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

        const url = `http://${ip}:${port}/debug`;
        console.log('Opening debug server at:', url);

        // Check if using Chrome
        const isChrome = /Chrome/.test(navigator.userAgent) && !/Edge/.test(navigator.userAgent);
        
        if (isChrome) {
            // Create and show a custom modal
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
                max-width: 500px;
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
                <p>Due to Chrome's security policies, you'll need to access the debug server in one of these ways:</p>
                <p><strong>Option 1:</strong> Copy and paste this URL in a new tab:</p>
                <pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; user-select: text; overflow-x: auto;">${url}</pre>
                <p><strong>Option 2:</strong> Use Firefox or Safari instead, where the button will work directly.</p>
                <p><strong>Troubleshooting:</strong></p>
                <ul style="margin-bottom: 20px;">
                    <li>Make sure you're on the same network as the device</li>
                    <li>Check if port ${port} is not blocked by your firewall</li>
                    <li>Try accessing the debug server from another device on the network</li>
                </ul>
                <button onclick="this.parentElement.remove(); document.querySelector('#debug-overlay').remove();" style="padding: 8px 16px; background: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer;">Close</button>
                <button onclick="navigator.clipboard.writeText('${url}').then(() => window.showMessage('URL copied to clipboard'));" style="padding: 8px 16px; margin-left: 10px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;">Copy URL</button>
            `;

            overlay.id = 'debug-overlay';
            document.body.appendChild(overlay);
            document.body.appendChild(modal);
        } else {
            // For other browsers, open directly
            window.open(url, '_blank');
        }

    } catch (error) {
        console.error('Failed to open debug server:', error);
        window.showError('Failed to open debug server: ' + error.message);
    }
}
 
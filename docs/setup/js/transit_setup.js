// Transit setup wizard functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize transit setup when the button is clicked
    document.getElementById('transit-setup-button').addEventListener('click', function() {
        initTransitSetup();
    });
});

async function readCurrentConfig() {
    try {
        const response = await window.setupDevice.send(JSON.stringify({
            command: 'config_read',
            config_type: 'display_env',
            verbose: true
        }));

        // Response is already parsed by setup_device.js
        if (response.status === 'success' && response.variables) {
            // Extract only the transit-related values
            const currentConfig = {
                provider: response.variables['Provider']?.value || '',
                stops: response.variables['Stops']?.value || '',
                lines: response.variables['Lines']?.value || '',
                stopNameOverride: response.variables['Stop_name_override']?.value || '',
                scheduleUrl: response.variables['BUS_SCHEDULE_URL']?.value || ''
            };

            // Only return if we have at least a provider or stops configured
            if (currentConfig.provider || currentConfig.stops) {
                return currentConfig;
            }
        }
        return null;
    } catch (error) {
        console.error('Failed to read configuration:', error);
        return null;
    }
}

async function initTransitSetup() {
    const transitContainer = document.getElementById('transit-setup');
    const setupContent = document.createElement('div');
    setupContent.id = 'transit-setup-content';

    // Read current configuration
    const currentConfig = await readCurrentConfig();
    
    let currentConfigHTML = '';
    if (currentConfig && currentConfig.provider) {
        currentConfigHTML = `
            <div class="current-config">
                <h3>Current Configuration</h3>
                <div class="config-details">
                    <p><strong>Provider:</strong> ${currentConfig.provider}</p>
                    <p><strong>Stop ID:</strong> ${currentConfig.stops}</p>
                    ${currentConfig.lines ? `<p><strong>Lines:</strong> ${currentConfig.lines}</p>` : ''}
                    ${currentConfig.stopNameOverride ? `<p><strong>Stop Name Override:</strong> ${currentConfig.stopNameOverride}</p>` : ''}
                    ${currentConfig.scheduleUrl && currentConfig.scheduleUrl !== 'http://localhost:8000' ? 
                        `<p><strong>Schedule Server:</strong> ${currentConfig.scheduleUrl}</p>` : ''}
                </div>
            </div>
        `;
    }

    setupContent.innerHTML = `
        ${currentConfigHTML}
        <div class="setup-section">
            <h3>Transit Provider Selection</h3>
            <p>Select your transit provider to configure stop monitoring:</p>
            
            <div class="provider-selection">
                <h4>Real-time Providers</h4>
                <div class="radio-group">
                    <label>
                        <input type="radio" name="provider" value="stib">
                        STIB (Brussels)
                    </label>
                    <label>
                        <input type="radio" name="provider" value="delijn">
                        De Lijn (Flanders)
                    </label>
                    <label>
                        <input type="radio" name="provider" value="bkk">
                        BKK (Budapest)
                    </label>
                </div>

                <h4>Other Providers</h4>
                <div class="radio-group">
                    <label>
                        <input type="radio" name="provider" value="sncb">
                        SNCB (Belgian Railways)
                    </label>
                    <label>
                        <input type="radio" name="provider" value="other">
                        Other GTFS Provider
                    </label>
                </div>
            </div>

            <div id="provider-config" style="display: none;">
                <!-- This will be populated based on provider selection -->
            </div>

            <div class="help-section">
                <p>Need help finding your stop ID? Check our <a href="../api-features/transit_stop_ids.html" target="_blank">guide on finding stop IDs</a>.</p>
            </div>
        </div>
    `;

    // Replace any existing content
    const existingContent = document.getElementById('transit-setup-content');
    if (existingContent) {
        existingContent.remove();
    }
    transitContainer.appendChild(setupContent);

    // Add event listeners for radio buttons
    document.querySelectorAll('input[name="provider"]').forEach(radio => {
        radio.addEventListener('change', function() {
            showProviderConfig(this.value);
        });
    });

    // If we have a current configuration, pre-select the provider and show its config
    if (currentConfig && currentConfig.provider) {
        let providerValue = currentConfig.provider.toLowerCase();
        // Handle special case for other providers
        if (!['stib', 'delijn', 'bkk', 'sncb'].includes(providerValue)) {
            providerValue = 'other';
        }
        
        const radioButton = document.querySelector(`input[name="provider"][value="${providerValue}"]`);
        if (radioButton) {
            radioButton.checked = true;
            await showProviderConfig(providerValue);
            
            // Pre-fill the form with current values
            document.getElementById('stop-id').value = currentConfig.stops || '';
            document.getElementById('stop-name-override').value = currentConfig.stopNameOverride || '';
            
            if (currentConfig.lines) {
                const lineInput = document.getElementById(providerValue === 'sncb' ? 'route-id' : 'line-filter');
                if (lineInput) lineInput.value = currentConfig.lines;
            }
            
            if (providerValue === 'other') {
                document.getElementById('gtfs-provider').value = currentConfig.provider;
                if (currentConfig.scheduleUrl) {
                    document.getElementById('server-url').value = currentConfig.scheduleUrl;
                }
            }
        }
    }
}

function showProviderConfig(provider) {
    const configContainer = document.getElementById('provider-config');
    configContainer.style.display = 'block';

    let configHTML = '';
    
    // Common fields for all providers
    const commonFields = `
        <div class="form-group">
            <label for="stop-id">Stop ID*:</label>
            <input type="text" id="stop-id" required>
            <small class="help-text">The unique identifier for your transit stop</small>
        </div>
        <div class="form-group">
            <label for="stop-name-override">Stop Name Override:</label>
            <input type="text" id="stop-name-override">
            <small class="help-text">Optional: Override the default stop name (useful for long names that might not fit on the display)</small>
        </div>
    `;

    // Advanced settings section (common for all providers)
    const advancedSettings = `
        <details class="advanced-settings">
            <summary>Advanced Settings</summary>
            <div class="form-group">
                <label for="server-url">GTFS Schedule Server URL:</label>
                <input type="text" id="server-url" value="http://localhost:8000">
                <small class="help-text">URL of the GTFS schedule server for fallback when real-time service is unavailable. Note: The server needs to run on a powerful enough machine (not recommended to run directly on the Raspberry Pi).</small>
            </div>
        </details>
    `;

    switch(provider) {
        case 'stib':
        case 'delijn':
        case 'bkk':
            configHTML = `
                ${commonFields}
                <div class="form-group">
                    <label for="line-filter">Line Filter (Optional):</label>
                    <input type="text" id="line-filter">
                    <small class="help-text">
                        ${provider === 'bkk' ? 'Enter route_id to filter specific lines' : 'Enter line numbers to filter specific lines'}
                        ${provider === 'stib' ? '(Note: This will disable GTFS schedule fallback)' : ''}
                    </small>
                </div>
                ${advancedSettings}
            `;
            break;
        
        case 'sncb':
            configHTML = `
                ${commonFields}
                <div class="form-group">
                    <label for="route-id">Route ID (Optional):</label>
                    <input type="text" id="route-id">
                    <small class="help-text">The GTFS route_id to filter specific train lines</small>
                </div>
                ${advancedSettings}
            `;
            break;
        
        case 'other':
            configHTML = `
                ${commonFields}
                <div class="form-group">
                    <label for="gtfs-provider">Provider ID*:</label>
                    <input type="text" id="gtfs-provider" required>
                    <small class="help-text">The identifier for your transit provider</small>
                </div>
                <div class="form-group">
                    <label for="route-id">Route ID (Optional):</label>
                    <input type="text" id="route-id">
                    <small class="help-text">The GTFS route_id to filter specific lines</small>
                </div>
                ${advancedSettings}
            `;
            break;
    }

    // Add save button
    configHTML += `
        <div class="button-group">
            <button onclick="saveTransitConfig('${provider}')" class="button">Save Configuration</button>
        </div>
    `;

    configContainer.innerHTML = configHTML;
}

async function saveTransitConfig(provider) {
    const stopId = document.getElementById('stop-id').value;
    if (!stopId) {
        showError('Stop ID is required');
        return;
    }

    // Config for display_env
    let displayConfig = {
        'Stops': stopId
    };

    // Add stop name override if provided
    const stopNameOverride = document.getElementById('stop-name-override').value;
    if (stopNameOverride) {
        displayConfig['Stop_name_override'] = stopNameOverride;
    }

    // Add GTFS Schedule server URL if provided and different from default
    const serverUrl = document.getElementById('server-url').value;
    if (serverUrl && serverUrl !== 'http://localhost:8000') {
        displayConfig['BUS_SCHEDULE_URL'] = serverUrl;
    }

    // Set provider based on selection
    switch(provider) {
        case 'stib':
            displayConfig['Provider'] = 'stib';
            const stibLineFilter = document.getElementById('line-filter').value;
            if (stibLineFilter) {
                displayConfig['Lines'] = stibLineFilter;
            }
            break;
        
        case 'delijn':
            displayConfig['Provider'] = 'delijn';
            const delijnLineFilter = document.getElementById('line-filter').value;
            if (delijnLineFilter) {
                displayConfig['Lines'] = delijnLineFilter;
            }
            break;
        
        case 'bkk':
            displayConfig['Provider'] = 'bkk';
            const bkkLineFilter = document.getElementById('line-filter').value;
            if (bkkLineFilter) {
                displayConfig['Lines'] = bkkLineFilter;
            }
            break;
        
        case 'sncb':
            displayConfig['Provider'] = 'sncb';
            const sncbRouteId = document.getElementById('route-id').value;
            if (sncbRouteId) {
                displayConfig['Lines'] = sncbRouteId;
            }
            break;
        
        case 'other':
            const gtfsProvider = document.getElementById('gtfs-provider').value;
            if (!gtfsProvider) {
                showError('Provider ID is required');
                return;
            }
            displayConfig['Provider'] = gtfsProvider;
            
            const otherRouteId = document.getElementById('route-id').value;
            if (otherRouteId) {
                displayConfig['Lines'] = otherRouteId;
            }
            break;
    }

    try {
        // Save display configuration
        await window.setupDevice.send(JSON.stringify({
            command: 'config_set',
            config_type: 'display_env',
            key: 'transit_setup',
            value: displayConfig
        }));

        showMessage('Transit configuration saved successfully');
        
        // Hide the configuration section
        document.getElementById('provider-config').style.display = 'none';
        
        // Uncheck all radio buttons
        document.querySelectorAll('input[name="provider"]').forEach(radio => {
            radio.checked = false;
        });
    } catch (error) {
        showError('Failed to save transit configuration: ' + error.message);
    }
} 
// Initialize service setup module
document.addEventListener('DOMContentLoaded', () => {
    const serviceSetupButton = document.getElementById('service-setup-button');
    const apiSetupButton = document.getElementById('api-setup-button');
    
    if (serviceSetupButton) {
        serviceSetupButton.addEventListener('click', () => {
            if (window.startServiceSetup) {
                window.startServiceSetup();
            } else {
                window.showError('Service setup not initialized yet');
            }
        });
    }

    if (apiSetupButton) {
        apiSetupButton.addEventListener('click', () => {
            if (window.startApiSetup) {
                window.startApiSetup();
            } else {
                window.showError('API setup not initialized yet');
            }
        });
    }
});

// Service configuration
const services = {
    weather: {
        name: 'Weather Display',
        description: 'Show current weather and forecast',
        config_type: 'display_env',
        requires_api_key: true,
        api_key_name: 'OPENWEATHER_API_KEY',
        api_info: {
            name: 'OpenWeatherMap API Key',
            url: 'https://openweathermap.org/api',
            instructions: 'Sign up for a free account at OpenWeatherMap and get your API key from the "API keys" tab.'
        }
    },
    transit: {
        name: 'Transit Information',
        description: 'Display transit schedules and delays',
        config_type: 'display_env',
        requires_api_key: false,
        always_enabled: true,
        config_fields: ['Provider', 'Stops', 'Lines']
    },
    flight: {
        name: 'Flight Tracking',
        description: 'Track flights over your area (enhanced features with AeroAPI)',
        config_type: 'display_env',
        enabled_key: 'flights_enabled',
        optional_api: {
            enabled_key: 'aeroapi_enabled',
            api_key_name: 'aeroapi_key',
            name: 'AeroAPI',
            url: 'https://flightaware.com/commercial/aeroapi/',
            instructions: 'For enhanced flight tracking features, get an AeroAPI key from FlightAware.'
        }
    },
    iss: {
        name: 'ISS Tracking',
        description: 'Track the International Space Station',
        config_type: 'display_env',
        enabled_key: 'iss_enabled',
        requires_api_key: false
    }
};

window.startServiceSetup = async function() {
    try {
        const serviceSetup = document.getElementById('service-setup');
        const button = document.getElementById('service-setup-button');
        
        if (!serviceSetup) {
            throw new Error('Service setup element not found');
        }

        // Show setup UI and hide button
        serviceSetup.style.display = 'block';
        button.style.display = 'none';

        // Get current service states
        const enabledServices = {};
        for (const [id, service] of Object.entries(services)) {
            try {
                const enabledKey = service.enabled_key || `${id}_enabled`;
                const response = await window.setupDevice.send(JSON.stringify({
                    command: 'config_get',
                    config_type: service.config_type,
                    key: enabledKey
                }));
                if (response.status === 'success') {
                    enabledServices[id] = response.value === 'true' || response.value === true;
                }
            } catch (error) {
                console.error(`Failed to get state for ${id}:`, error);
            }
        }

        serviceSetup.innerHTML = `
            <div class="service-setup-container">
                <h3>Available Services</h3>
                <p>Choose which services you want to enable:</p>
                
                <div class="service-grid">
                    ${Object.entries(services).map(([id, service]) => `
                        <div class="service-card">
                            <div class="service-header">
                                <h4>${service.name}</h4>
                                ${service.always_enabled ? `
                                    <div class="always-enabled">Always Enabled</div>
                                ` : `
                                    <label class="switch">
                                        <input type="checkbox" 
                                               id="service-${id}" 
                                               onchange="toggleService('${id}', this.checked)"
                                               ${enabledServices[id] ? 'checked' : ''}>
                                        <span class="slider"></span>
                                    </label>
                                `}
                            </div>
                            <p>${service.description}</p>
                            ${service.requires_api_key ? `
                                <div class="api-note">
                                    <small>⚠️ Requires API key</small>
                                </div>
                            ` : service.optional_api ? `
                                <div class="api-note">
                                    <small>💡 Optional API available</small>
                                </div>
                            ` : ''}
                        </div>
                    `).join('')}
                </div>

                <div class="button-group">
                    <button onclick="startApiSetup()" class="next-button">
                        Continue to API Setup →
                    </button>
                </div>
            </div>
        `;

    } catch (error) {
        console.error('Failed to start service setup:', error);
        window.showError('Service Setup Error: ' + error.message);
    }
}

window.startApiSetup = async function() {
    try {
        const apiSetup = document.getElementById('api-setup');
        const button = document.getElementById('api-setup-button');
        
        if (!apiSetup) {
            throw new Error('API setup element not found');
        }

        // Show setup UI and hide button
        apiSetup.style.display = 'block';
        button.style.display = 'none';

        // Get current service states and API keys
        const serviceStates = {};
        const apiKeyStates = {};
        
        for (const [id, service] of Object.entries(services)) {
            try {
                // Get service enabled state
                const enabledKey = service.enabled_key || `${id}_enabled`;
                const response = await window.setupDevice.send(JSON.stringify({
                    command: 'config_get',
                    config_type: service.config_type,
                    key: enabledKey
                }));
                serviceStates[id] = response.status === 'success' && 
                    (response.value === 'true' || response.value === true);

                // Get API key if service has one
                if (service.requires_api_key && service.api_key_name) {
                    const keyResponse = await window.setupDevice.send(JSON.stringify({
                        command: 'config_get',
                        config_type: service.config_type,
                        key: service.api_key_name
                    }));
                    apiKeyStates[service.api_key_name] = keyResponse.status === 'success' ? keyResponse.value : '';
                }

                // Get optional API key if service has one
                if (service.optional_api?.api_key_name) {
                    const optKeyResponse = await window.setupDevice.send(JSON.stringify({
                        command: 'config_get',
                        config_type: service.config_type,
                        key: service.optional_api.api_key_name
                    }));
                    apiKeyStates[service.optional_api.api_key_name] = optKeyResponse.status === 'success' ? optKeyResponse.value : '';
                }
            } catch (error) {
                console.error(`Failed to get state for ${id}:`, error);
            }
        }

        apiSetup.innerHTML = `
            <div class="api-setup-container">
                <h3>API Configuration</h3>
                <p>Configure API keys for available services:</p>
                
                <div class="api-grid">
                    ${Object.entries(services).map(([id, service]) => {
                        // Skip services without any API keys
                        if (!service.requires_api_key && !service.optional_api) {
                            return '';
                        }

                        // Determine API key status
                        let statusIcon = '';
                        let statusClass = '';
                        let statusText = '';
                        
                        if (service.requires_api_key) {
                            const hasKey = apiKeyStates[service.api_key_name];
                            if (hasKey) {
                                statusIcon = '✓';
                                statusClass = 'status-success';
                                statusText = 'API key set';
                            } else {
                                statusIcon = '⚠️';
                                statusClass = 'status-error';
                                statusText = 'Required API key missing';
                            }
                        } else if (service.optional_api) {
                            const isEnabled = serviceStates[id];
                            const hasKey = apiKeyStates[service.optional_api.api_key_name];
                            if (hasKey) {
                                statusIcon = '✓';
                                statusClass = 'status-success';
                                statusText = 'Optional API key set';
                            } else if (isEnabled) {
                                statusIcon = '⚡';
                                statusClass = 'status-warning';
                                statusText = 'Service enabled, optional API key available';
                            } else {
                                statusIcon = 'ℹ️';
                                statusClass = 'status-info';
                                statusText = 'Optional API key available';
                            }
                        }

                        return `
                            <div class="api-card ${statusClass}">
                                <div class="api-header">
                                    <h4>${service.name}</h4>
                                    <div class="api-status" title="${statusText}">
                                        ${statusIcon}
                                    </div>
                                </div>
                                ${service.requires_api_key ? `
                                    <p>${service.api_info.instructions}</p>
                                    <a href="${service.api_info.url}" target="_blank" class="api-link">
                                        Get API Key ↗
                                    </a>
                                    <div class="api-input">
                                        <input type="password" 
                                               id="api-${id}"
                                               placeholder="Enter API key"
                                               value="${apiKeyStates[service.api_key_name] || ''}"
                                               onchange="updateApiKey('${id}', this.value)">
                                        <button onclick="toggleVisibility('api-${id}')">
                                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512"><!--!Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2024 Fonticons, Inc.--><path d="M288 32c-80.8 0-145.5 36.8-192.6 80.6C48.6 156 17.3 208 2.5 243.7c-3.3 7.9-3.3 16.7 0 24.6C17.3 304 48.6 356 95.4 399.4C142.5 443.2 207.2 480 288 480s145.5-36.8 192.6-80.6c46.8-43.5 78.1-95.4 93-131.1c3.3-7.9 3.3-16.7 0-24.6c-14.9-35.7-46.2-87.7-93-131.1C433.5 68.8 368.8 32 288 32zM144 256a144 144 0 1 1 288 0 144 144 0 1 1 -288 0zm144-64c0 35.3-28.7 64-64 64c-7.1 0-13.9-1.2-20.3-3.3c-5.5-1.8-11.9 1.6-11.7 7.4c.3 6.9 1.3 13.8 3.2 20.7c13.7 51.2 66.4 81.6 117.6 67.9s81.6-66.4 67.9-117.6c-11.1-41.5-47.8-69.4-88.6-71.1c-5.8-.2-9.2 6.1-7.4 11.7c2.1 6.4 3.3 13.2 3.3 20.3z"/></svg>
                                        </button>
                                    </div>
                                ` : service.optional_api ? `
                                    <p>${service.optional_api.instructions}</p>
                                    <a href="${service.optional_api.url}" target="_blank" class="api-link">
                                        Get API Key ↗
                                    </a>
                                    <div class="api-input">
                                        <input type="password" 
                                               id="api-${id}"
                                               placeholder="Enter API key (optional)"
                                               value="${apiKeyStates[service.optional_api.api_key_name] || ''}"
                                               onchange="updateApiKey('${id}', this.value)">
                                        <button onclick="toggleVisibility('api-${id}')">
                                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512"><!--!Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2024 Fonticons, Inc.--><path d="M288 32c-80.8 0-145.5 36.8-192.6 80.6C48.6 156 17.3 208 2.5 243.7c-3.3 7.9-3.3 16.7 0 24.6C17.3 304 48.6 356 95.4 399.4C142.5 443.2 207.2 480 288 480s145.5-36.8 192.6-80.6c46.8-43.5 78.1-95.4 93-131.1c3.3-7.9 3.3-16.7 0-24.6c-14.9-35.7-46.2-87.7-93-131.1C433.5 68.8 368.8 32 288 32zM144 256a144 144 0 1 1 288 0 144 144 0 1 1 -288 0zm144-64c0 35.3-28.7 64-64 64c-7.1 0-13.9-1.2-20.3-3.3c-5.5-1.8-11.9 1.6-11.7 7.4c.3 6.9 1.3 13.8 3.2 20.7c13.7 51.2 66.4 81.6 117.6 67.9s81.6-66.4 67.9-117.6c-11.1-41.5-47.8-69.4-88.6-71.1c-5.8-.2-9.2 6.1-7.4 11.7c2.1 6.4 3.3 13.2 3.3 20.3z"/></svg>
                                        </button>
                                    </div>
                                ` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>

                <div class="button-group">
                    <button onclick="startServiceSetup()" class="back-button">
                        ← Back to Services
                    </button>
                    <button onclick="startReview()" class="next-button">
                        Continue to Review →
                    </button>
                </div>
            </div>
        `;

    } catch (error) {
        console.error('Failed to start API setup:', error);
        window.showError('API Setup Error: ' + error.message);
    }
}

window.toggleService = async function(serviceId, enabled) {
    const service = services[serviceId];
    if (!service) return;
    
    // Don't allow disabling always-enabled services
    if (service.always_enabled) {
        return;
    }

    try {
        const enabledKey = service.enabled_key || `${serviceId}_enabled`;
        const response = await window.setupDevice.send(JSON.stringify({
            command: 'config_set',
            config_type: 'display_env',
            key: enabledKey,
            value: enabled.toString()
        }));

        if (response.status === 'success') {
            window.showMessage(`${service.name} ${enabled ? 'enabled' : 'disabled'}`);
            
            // If this is a service with an optional API, we might need to update the API setup view
            if (service.optional_api) {
                const apiSetup = document.getElementById('api-setup');
                if (apiSetup && apiSetup.style.display === 'block') {
                    startApiSetup(); // Refresh the API setup view
                }
            }
        } else {
            throw new Error(response.message || 'Failed to update service');
        }
    } catch (error) {
        console.error(`Failed to toggle ${serviceId}:`, error);
        window.showError(`Failed to toggle ${service.name}: ${error.message}`);
        
        // Revert the checkbox state
        const checkbox = document.getElementById(`service-${serviceId}`);
        if (checkbox) {
            checkbox.checked = !enabled;
        }
    }
}

window.updateApiKey = async function(serviceId, value) {
    const service = services[serviceId];
    if (!service) return;

    try {
        const apiKeyName = service.api_key_name || 
                          (service.optional_api && service.optional_api.api_key_name);
        
        if (!apiKeyName) {
            throw new Error('No API key configuration found');
        }

        const response = await window.setupDevice.send(JSON.stringify({
            command: 'config_set',
            config_type: 'display_env',
            key: apiKeyName,
            value: value
        }));

        if (response.status === 'success') {
            window.showMessage(`Updated API key for ${service.name}`);
        } else {
            throw new Error(response.message || 'Failed to update API key');
        }
    } catch (error) {
        console.error(`Failed to update API key:`, error);
        window.showError(`Failed to update API key: ${error.message}`);
    }
}

window.toggleVisibility = function(inputId) {
    const input = document.getElementById(inputId);
    if (input) {
        const button = input.nextElementSibling;
        input.type = input.type === 'password' ? 'text' : 'password';
        if (button) {
            // Eye open SVG when password is hidden (will show on click)
            const eyeOpenSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512"><!--!Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2024 Fonticons, Inc.--><path d="M288 32c-80.8 0-145.5 36.8-192.6 80.6C48.6 156 17.3 208 2.5 243.7c-3.3 7.9-3.3 16.7 0 24.6C17.3 304 48.6 356 95.4 399.4C142.5 443.2 207.2 480 288 480s145.5-36.8 192.6-80.6c46.8-43.5 78.1-95.4 93-131.1c3.3-7.9 3.3-16.7 0-24.6c-14.9-35.7-46.2-87.7-93-131.1C433.5 68.8 368.8 32 288 32zM144 256a144 144 0 1 1 288 0 144 144 0 1 1 -288 0zm144-64c0 35.3-28.7 64-64 64c-7.1 0-13.9-1.2-20.3-3.3c-5.5-1.8-11.9 1.6-11.7 7.4c.3 6.9 1.3 13.8 3.2 20.7c13.7 51.2 66.4 81.6 117.6 67.9s81.6-66.4 67.9-117.6c-11.1-41.5-47.8-69.4-88.6-71.1c-5.8-.2-9.2 6.1-7.4 11.7c2.1 6.4 3.3 13.2 3.3 20.3z"/></svg>';
            // Eye slash SVG when password is visible (will hide on click)
            const eyeSlashSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512"><!--!Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2024 Fonticons, Inc.--><path d="M38.8 5.1C28.4-3.1 13.3-1.2 5.1 9.2S-1.2 34.7 9.2 42.9l592 464c10.4 8.2 25.5 6.3 33.7-4.1s6.3-25.5-4.1-33.7L525.6 386.7c39.6-40.6 66.4-86.1 79.9-118.4c3.3-7.9 3.3-16.7 0-24.6c-14.9-35.7-46.2-87.7-93-131.1C465.5 68.8 400.8 32 320 32c-68.2 0-125 26.3-169.3 60.8L38.8 5.1zm151 118.3C226 97.7 269.5 80 320 80c65.2 0 118.8 29.6 159.9 67.7C518.4 183.5 545 226 558.6 256c-12.6 28-36.6 66.8-70.9 100.9l-53.8-42.2c9.1-17.6 14.2-37.5 14.2-58.7c0-70.7-57.3-128-128-128c-32.2 0-61.7 11.9-84.2 31.5l-46.1-36.1zM394.9 284.2l-81.5-63.9c4.2-8.5 6.6-18.2 6.6-28.3c0-5.5-.7-10.9-2-16c.7 0 1.3 0 2 0c44.2 0 80 35.8 80 80c0 9.9-1.8 19.4-5.1 28.2zm9.4 130.3C378.8 425.4 350.7 432 320 432c-65.2 0-118.8-29.6-159.9-67.7C121.6 328.5 95 286 81.4 256c8.3-18.4 21.5-41.5 39.4-64.8L83.1 161.5C60.3 191.2 44 220.8 34.5 243.7c-3.3 7.9-3.3 16.7 0 24.6c14.9 35.7 46.2 87.7 93 131.1C174.5 443.2 239.2 480 320 480c47.8 0 89.9-12.9 126.2-32.5l-41.9-33zM192 256c0 70.7 57.3 128 128 128c13.3 0 26.1-2 38.2-5.8L302 334c-23.5-5.4-43.1-21.2-53.7-42.3l-56.1-44.2c-.2 2.8-.3 5.6-.3 8.5z"/></svg>';
            
            button.innerHTML = input.type === 'password' ? eyeOpenSvg : eyeSlashSvg;
        }
    }
} 
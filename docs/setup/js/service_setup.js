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
                const response = await window.setupDevice.send(JSON.stringify({
                    command: 'config_get',
                    config_type: service.config_type,
                    key: 'enabled'
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

        // Get enabled services that require API keys or have optional APIs
        const requiredApiServices = {};
        const optionalApiServices = {};
        
        for (const [id, service] of Object.entries(services)) {
            if (service.requires_api_key || service.optional_api) {
                try {
                    const response = await window.setupDevice.send(JSON.stringify({
                        command: 'config_get',
                        config_type: service.config_type,
                        key: 'enabled'
                    }));
                    
                    if (response.status === 'success' && (response.value === 'true' || response.value === true)) {
                        if (service.requires_api_key) {
                            requiredApiServices[id] = service;
                        } else if (service.optional_api) {
                            optionalApiServices[id] = service;
                        }
                    }
                } catch (error) {
                    console.error(`Failed to get state for ${id}:`, error);
                }
            }
        }

        const hasRequiredApis = Object.keys(requiredApiServices).length > 0;
        const hasOptionalApis = Object.keys(optionalApiServices).length > 0;

        if (!hasRequiredApis && !hasOptionalApis) {
            apiSetup.innerHTML = `
                <div class="api-setup-container">
                    <h3>API Configuration</h3>
                    <p>No API keys are required for your enabled services.</p>
                    <div class="button-group">
                        <button onclick="startReview()" class="next-button">
                            Continue to Review →
                        </button>
                    </div>
                </div>
            `;
            return;
        }

        apiSetup.innerHTML = `
            <div class="api-setup-container">
                <h3>API Configuration</h3>
                
                ${hasRequiredApis ? `
                    <div class="required-apis">
                        <h4>Required API Keys</h4>
                        <p>These API keys are required for the services to work:</p>
                        <div class="api-grid">
                            ${Object.entries(requiredApiServices).map(([id, service]) => `
                                <div class="api-card required">
                                    <h4>${service.api_info.name}</h4>
                                    <p>${service.api_info.instructions}</p>
                                    <a href="${service.api_info.url}" target="_blank" class="api-link">
                                        Get API Key ↗
                                    </a>
                                    <div class="api-input">
                                        <input type="password" 
                                               id="api-${id}"
                                               placeholder="Enter API key"
                                               onchange="updateApiKey('${id}', this.value)">
                                        <button onclick="toggleVisibility('api-${id}')">
                                            👁️
                                        </button>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}

                ${hasOptionalApis ? `
                    <div class="optional-apis">
                        <h4>Optional API Keys</h4>
                        <p>These API keys enable additional features but are not required:</p>
                        <div class="api-grid">
                            ${Object.entries(optionalApiServices).map(([id, service]) => `
                                <div class="api-card optional">
                                    <h4>${service.optional_api.name}</h4>
                                    <p>${service.optional_api.instructions}</p>
                                    <a href="${service.optional_api.url}" target="_blank" class="api-link">
                                        Get API Key ↗
                                    </a>
                                    <div class="api-input">
                                        <input type="password" 
                                               id="api-${id}"
                                               placeholder="Enter API key (optional)"
                                               onchange="updateApiKey('${id}', this.value)">
                                        <button onclick="toggleVisibility('api-${id}')">
                                            👁️
                                        </button>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}

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
        input.type = input.type === 'password' ? 'text' : 'password';
    }
} 
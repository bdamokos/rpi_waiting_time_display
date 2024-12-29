// Initialize display setup module
document.addEventListener('DOMContentLoaded', () => {
    // Initialize any event listeners or other setup
    const displaySetupButton = document.getElementById('display-setup-button');
    if (displaySetupButton) {
        displaySetupButton.addEventListener('click', () => {
            if (window.startDisplaySetup) {
                window.startDisplaySetup();
            } else {
                window.showError('Display setup not initialized yet');
            }
        });
    }
});

// Display configuration functionality
window.startDisplaySetup = async function() {
    try {
        // Use the global setupDevice instance
        if (!window.setupDevice || !window.setupDevice.connected) {
            throw new Error("Device not connected");
        }

        const displaySetup = document.getElementById('display-setup');
        if (!displaySetup) {
            throw new Error("Display setup element not found");
        }

        // Show display setup UI and hide the button
        displaySetup.style.display = 'block';
        document.getElementById('display-setup-button').style.display = 'none';

        // Load display database
        const dbResponse = await fetch('../data/displays.json');
        const database = await dbResponse.json();
        window.displayDatabase = database; // Store for later use

        // Get current display configuration
        const response = await window.setupDevice.send(JSON.stringify({
            command: 'config_get',
            config_type: 'display_env',
            key: 'display_model'
        }));

        if (response.status === 'success') {
            const currentDriver = response.value;
            
            displaySetup.innerHTML = `
                <div class="display-setup-container">
                    <h3>Display Configuration</h3>
                    
                    <div class="setup-steps">
                        <div class="setup-step">
                            <h4>Step A: Display Driver</h4>
                            <p>Current driver: <strong>${currentDriver || 'Not set'}</strong></p>
                            <button onclick="showDisplaySelection()" class="step-button">
                                ${currentDriver ? 'Change Display Driver' : 'Select Display Driver'}
                            </button>
                        </div>

                        <div class="setup-step">
                            <h4>Step B: Display Settings</h4>
                            <p>Configure refresh rates and screen rotation</p>
                            <button onclick="showDisplaySettings('${currentDriver}')" class="step-button" ${!currentDriver ? 'disabled' : ''}>
                                ${currentDriver ? 'Configure Display Settings' : 'Select a display driver first'}
                            </button>
                        </div>
                    </div>

                    <div id="step-content"></div>
                </div>
            `;

        } else {
            throw new Error('Failed to get display information');
        }

    } catch (error) {
        console.error('Failed to start display setup:', error);
        window.showError('Display Setup Error: ' + error.message);
    }
}

function renderDisplaySetup(container, currentConfig, database) {
    // Show current configuration if it exists
    let html = '<div class="current-config">';
    if (currentConfig) {
        html += `
            <h3>Current Display Configuration</h3>
            <p><strong>Driver:</strong> ${currentConfig.driver}</p>
            ${currentConfig.name ? `<p><strong>Display:</strong> ${currentConfig.name}</p>` : ''}
            ${currentConfig.notes ? `<p><strong>Notes:</strong> ${currentConfig.notes}</p>` : ''}
        `;
    } else {
        html += '<h3>No display configured</h3>';
    }
    html += '</div>';

    // Add selection interface
    html += `
        <div class="selection-mode">
            <h3>Select Your Display</h3>
            <div class="mode-buttons">
                <button onclick="showDisplayList()" class="button">
                    Choose from Tested Displays
                </button>
                <button onclick="showAdvancedMode()" class="button">
                    Advanced: Select Driver
                </button>
                <button onclick="showGuidedMode()" class="button">
                    Find by Specifications
                </button>
            </div>
        </div>
        <div id="display-selection-container"></div>
    `;

    container.innerHTML = html;

    // Store database for later use
    window.displayDatabase = database;
}

window.showDisplayList = function() {
    const container = document.getElementById('display-selection-container');
    if (!container || !window.displayDatabase) return;

    container.innerHTML = `
        <div class="display-list">
            <h3>Tested Displays</h3>
            <div class="display-grid">
                ${window.displayDatabase.displays.map(display => `
                    <div class="display-card" onclick="selectDisplay('${display.driver}')">
                        ${display.images && display.images[0] ? 
                            `<img src="${display.images[0]}" alt="${display.name}">` : ''}
                        <h4>${display.name}</h4>
                        <p>Size: ${display.size}"</p>
                        <p>Colors: ${display.colors.join(', ')}</p>
                        <p>Resolution: ${display.resolution.width}x${display.resolution.height}</p>
                        ${display.features.partial_refresh ? '<p>✓ Partial Refresh</p>' : ''}
                    </div>
                `).join('')}
            </div>
            <div class="report-missing">
                <p>Don't see your display? Try the guided setup or report it as an issue.</p>
            </div>
        </div>
    `;
}

window.showAdvancedMode = function() {
    const container = document.getElementById('display-selection-container');
    if (!container || !window.displayDatabase) return;

    container.innerHTML = `
        <div class="advanced-mode">
            <h3>Advanced: Select Display Driver</h3>
            <p class="warning">⚠️ Only use this if you know your display driver name.</p>
            <div class="input-group">
                <input type="text" id="driver-input" placeholder="e.g., epd2in13_V4">
                <button onclick="setDisplayDriver()" class="button">Set Driver</button>
            </div>
            <div class="help-text">
                <p>Common driver names:</p>
                <ul>
                    ${window.displayDatabase.displays.map(display => `
                        <li>${display.driver} - ${display.name}</li>
                    `).join('')}
                </ul>
            </div>
        </div>
    `;
}

window.showGuidedMode = function() {
    const container = document.getElementById('display-selection-container');
    if (!container || !window.displayDatabase) return;

    const categories = window.displayDatabase.categories;
    container.innerHTML = `
        <div class="guided-mode">
            <h3>Find by Specifications</h3>
            <div class="spec-selectors">
                <div class="spec-group">
                    <label>Display Size:</label>
                    <select id="size-select">
                        <option value="">Select size...</option>
                        ${categories.sizes.map(size => `
                            <option value="${size}">${size}"</option>
                        `).join('')}
                    </select>
                </div>
                <div class="spec-group">
                    <label>Color Support:</label>
                    <div class="checkbox-group">
                        ${categories.colors.map(color => `
                            <label>
                                <input type="checkbox" value="${color}">
                                ${color}
                            </label>
                        `).join('')}
                    </div>
                </div>
            </div>
            <button onclick="findMatchingDisplays()" class="button">
                Find Matching Displays
            </button>
            <div id="matching-displays"></div>
        </div>
    `;
}

window.findMatchingDisplays = function() {
    const container = document.getElementById('matching-displays');
    if (!container || !window.displayDatabase) return;

    const selectedSize = document.getElementById('size-select').value;
    const selectedColors = Array.from(document.querySelectorAll('.checkbox-group input:checked'))
        .map(cb => cb.value);

    const matches = window.displayDatabase.displays.filter(display => {
        const sizeMatch = !selectedSize || display.size === selectedSize;
        const colorMatch = selectedColors.length === 0 || 
            selectedColors.every(color => display.colors.includes(color));
        return sizeMatch && colorMatch;
    });

    if (matches.length === 0) {
        container.innerHTML = `
            <div class="no-matches">
                <p>No exact matches found. Try different criteria or select a similar display:</p>
                <div class="display-grid">
                    ${window.displayDatabase.displays.slice(0, 3).map(display => renderDisplayCard(display)).join('')}
                </div>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div class="matches">
                <h4>Matching Displays:</h4>
                <div class="display-grid">
                    ${matches.map(display => renderDisplayCard(display)).join('')}
                </div>
            </div>
        `;
    }
}

function renderDisplayCard(display, isCurrent = false) {
    return `
        <div class="display-card ${isCurrent ? 'current-display' : ''}">
            ${display.images && display.images[0] ? 
                `<img src="${display.images[0]}" alt="${display.name}">` : ''}
            <h4>${display.name}</h4>
            <div class="display-info">
                <p><strong>Size:</strong> ${display.size}"</p>
                <p><strong>Colors:</strong> ${display.colors.join(', ')}</p>
                <p><strong>Resolution:</strong> ${display.resolution.width}x${display.resolution.height}</p>
                <p><strong>Features:</strong> ${Object.entries(display.features)
                    .filter(([_, enabled]) => enabled)
                    .map(([feature]) => feature.replace('_', ' '))
                    .join(', ') || 'None'}</p>
                ${display.notes ? `<p class="notes"><strong>Notes:</strong> ${display.notes}</p>` : ''}
                ${display.url ? `<p><a href="${display.url}" target="_blank">Product Page ↗</a></p>` : ''}
            </div>
            ${!isCurrent ? `
                <button class="set-driver-button" onclick="selectDisplay('${display.driver}')">
                    Set Driver to ${display.driver}
                </button>
            ` : ''}
        </div>
    `;
}

window.selectDisplay = async function(driver) {
    try {
        const response = await window.setupDevice.send(JSON.stringify({
            command: 'config_set',
            config_type: 'display_env',
            key: 'display_model',
            value: driver
        }));

        if (response.status === 'success') {
            window.showMessage(`Display driver set to ${driver}`);
            // Show settings configuration
            showDisplaySettings(driver);
        } else {
            throw new Error(response.message || 'Failed to set display');
        }
    } catch (error) {
        console.error('Failed to set display:', error);
        window.showError('Failed to set display: ' + error.message);
    }
}

window.showDisplaySelection = function() {
    const stepContent = document.getElementById('step-content');
    const database = window.displayDatabase;

    stepContent.innerHTML = `
        <div class="display-selection">
            <h3>Select Your Display</h3>
            <div class="search-options">
                <div class="option">
                    <h4>By Size</h4>
                    <select id="size-select" onchange="findMatchingDisplays()">
                        <option value="">Any size</option>
                        ${database.categories.sizes.map(size => 
                            `<option value="${size}">${size}"</option>`
                        ).join('')}
                    </select>
                </div>
                
                <div class="option">
                    <h4>By Color</h4>
                    <div class="checkbox-group">
                        ${database.categories.colors.map(color => `
                            <label>
                                <input type="checkbox" value="${color}" onchange="findMatchingDisplays()">
                                ${color}
                            </label>
                        `).join('')}
                    </div>
                </div>
            </div>
            
            <div id="matching-displays"></div>
            
            <div class="manual-entry">
                <h4>Manual Driver Entry</h4>
                <p>If you know your display driver, enter it here:</p>
                <div class="input-group">
                    <input type="text" id="driver-input" placeholder="e.g., epd2in13_V4">
                    <button onclick="setDisplayDriver()">Set Driver</button>
                </div>
            </div>

            <div class="help-note">
                <p>📝 <strong>Note:</strong> If you can't find your exact screen model:</p>
                <ol>
                    <li>Try setting the driver to one that most closely matches your screen's specifications.</li>
                    <li>If that doesn't work, please <a href="https://github.com/bdamokos/rpi_waiting_time_display/issues/new?title=New%20Display%20Support%20Request&body=Display%20Details:%0A-%20Model:%20%0A-%20Size:%20%0A-%20Resolution:%20%0A-%20Colors:%20%0A-%20URL:%20" target="_blank">open a GitHub issue</a> to request support for your screen.</li>
                </ol>
            </div>
        </div>
    `;
    
    // Trigger initial display matching
    findMatchingDisplays();
}

window.showDisplaySettings = async function(driver) {
    if (!driver) {
        window.showError('No display driver selected');
        return;
    }

    const stepContent = document.getElementById('step-content');
    const display = window.displayDatabase.displays.find(d => d.driver === driver);
    const preset = display ? window.displayDatabase.presets[display.preset] : window.displayDatabase.presets.standard;
    
    // Get current settings
    const currentSettings = {};
    const settingsToFetch = [
        'screen_rotation',
        'refresh_interval',
        'refresh_minimal_time',
        'refresh_weather_interval',
        'refresh_full_interval',
        'flight_display_fast_mode_interval',
        'iss_check_interval'
    ];

    try {
        for (const key of settingsToFetch) {
            const response = await window.setupDevice.send(JSON.stringify({
                command: 'config_get',
                config_type: 'display_env',
                key: key
            }));
            if (response.status === 'success' && response.value !== null) {
                currentSettings[key] = response.value;
            }
        }
    } catch (error) {
        console.error('Failed to fetch current settings:', error);
    }

    const hasExistingSettings = Object.keys(currentSettings).length > 0;
    
    // Store settings globally for the advanced settings view
    window.currentDisplaySettings = currentSettings;
    
    stepContent.innerHTML = `
        <div class="settings-config">
            <div class="rotation-setting">
                <h4>Screen Rotation</h4>
                <p>Select the orientation that matches your display setup:</p>
                <select id="screen-rotation" onchange="updateSetting('screen_rotation', this.value)">
                    <option value="90" ${(currentSettings.screen_rotation || 90) === 90 ? 'selected' : ''}>Landscape (Default)</option>
                    <option value="270" ${currentSettings.screen_rotation === 270 ? 'selected' : ''}>Landscape (Flipped)</option>
                    <option value="0" ${currentSettings.screen_rotation === 0 ? 'selected' : ''}>Portrait</option>
                    <option value="180" ${currentSettings.screen_rotation === 180 ? 'selected' : ''}>Portrait (Flipped)</option>
                </select>
            </div>

            <div class="preset-info">
                <h4>Current Configuration</h4>
                ${hasExistingSettings ? `
                    <div class="preset-settings">
                        <p><strong>Refresh Interval:</strong> ${currentSettings.refresh_interval || 'Not set'} seconds</p>
                        <p><strong>Minimal Refresh Time:</strong> ${currentSettings.refresh_minimal_time || 'Not set'} seconds</p>
                        <p><strong>Weather Update Interval:</strong> ${currentSettings.refresh_weather_interval || 'Not set'} seconds</p>
                        <p><strong>Full Refresh Interval:</strong> ${currentSettings.refresh_full_interval || 'Not set'} seconds</p>
                        <p><strong>Flight Display Update Interval:</strong> ${currentSettings.flight_display_fast_mode_interval || 'Not set'} seconds</p>
                        <p><strong>ISS Check Interval:</strong> ${currentSettings.iss_check_interval || 'Not set'} seconds</p>
                    </div>
                ` : `
                    <p>No current settings found. Choose a preset below or customize settings.</p>
                `}
            </div>

            <div class="preset-actions">
                <h4>Configuration Options</h4>
                <p>Choose how to configure your display:</p>
                <div class="button-group">
                    <button onclick="applyPreset('standard')">
                        Apply Standard Preset
                        <small>For displays without partial refresh</small>
                    </button>
                    <button onclick="applyPreset('partial_refresh')">
                        Apply Partial Refresh Preset
                        <small>For displays with partial refresh support</small>
                    </button>
                    <button class="advanced-settings-button" onclick="showAdvancedSettings('${driver}', window.currentDisplaySettings)">
                        Customize Settings
                        <small>Manually configure all settings</small>
                    </button>
                </div>
            </div>
        </div>
    `;
}

window.showAdvancedSettings = function(driver, currentSettings) {
    const stepContent = document.getElementById('step-content');
    const display = window.displayDatabase.displays.find(d => d.driver === driver);
    const preset = display ? window.displayDatabase.presets[display.preset] : window.displayDatabase.presets.standard;
    
    // Ensure currentSettings is an object and handle null values
    currentSettings = currentSettings || {};
    
    stepContent.innerHTML = `
        <div class="settings-form">
            <h3>Advanced Display Settings</h3>
            <form id="advanced-settings-form" onsubmit="applyAdvancedSettings(event)">
                <div class="form-group">
                    <label for="screen-rotation">Screen Rotation (degrees)</label>
                    <select id="screen-rotation" name="screen_rotation">
                        <option value="90" ${(currentSettings.screen_rotation || 90) === 90 ? 'selected' : ''}>90° (Landscape)</option>
                        <option value="270" ${currentSettings.screen_rotation === 270 ? 'selected' : ''}>270° (Landscape Flipped)</option>
                        <option value="0" ${currentSettings.screen_rotation === 0 ? 'selected' : ''}>0° (Portrait)</option>
                        <option value="180" ${currentSettings.screen_rotation === 180 ? 'selected' : ''}>180° (Portrait Flipped)</option>
                    </select>
                    <small>Default: 90° (Landscape)</small>
                </div>

                <div class="form-group">
                    <label for="refresh-interval">Refresh Interval (seconds)</label>
                    <input type="number" id="refresh-interval" name="refresh_interval"
                           value="${currentSettings.refresh_interval || preset.settings.refresh_interval}">
                    <small>How often to check for updates (Default: ${preset.settings.refresh_interval}s)</small>
                </div>

                <div class="form-group">
                    <label for="refresh-minimal-time">Minimal Refresh Time (seconds)</label>
                    <input type="number" id="refresh-minimal-time" name="refresh_minimal_time"
                           value="${currentSettings.refresh_minimal_time || preset.settings.refresh_minimal_time}">
                    <small>Minimum time between screen updates (Default: ${preset.settings.refresh_minimal_time}s)</small>
                </div>

                <div class="form-group">
                    <label for="refresh-weather-interval">Weather Update Interval (seconds)</label>
                    <input type="number" id="refresh-weather-interval" name="refresh_weather_interval"
                           value="${currentSettings.refresh_weather_interval || preset.settings.refresh_weather_interval}">
                    <small>How often to fetch new weather data (Default: ${preset.settings.refresh_weather_interval}s)</small>
                </div>

                <div class="form-group">
                    <label for="refresh-full-interval">Full Refresh Interval (seconds)</label>
                    <input type="number" id="refresh-full-interval" name="refresh_full_interval"
                           value="${currentSettings.refresh_full_interval || preset.settings.refresh_full_interval}">
                    <small>How often to do a full screen refresh (Default: ${preset.settings.refresh_full_interval}s)</small>
                </div>

                <div class="form-group">
                    <label for="flight-display-interval">Flight Display Update Interval (seconds)</label>
                    <input type="number" id="flight-display-interval" name="flight_display_fast_mode_interval"
                           value="${currentSettings.flight_display_fast_mode_interval || preset.settings.flight_display_fast_mode_interval}">
                    <small>How often to update flight tracking display (Default: ${preset.settings.flight_display_fast_mode_interval}s)</small>
                </div>

                <div class="form-group">
                    <label for="iss-check-interval">ISS Check Interval (seconds)</label>
                    <input type="number" id="iss-check-interval" name="iss_check_interval"
                           value="${currentSettings.iss_check_interval || preset.settings.iss_check_interval}">
                    <small>How often to check ISS position (Default: ${preset.settings.iss_check_interval}s)</small>
                </div>

                <div class="button-group">
                    <button type="button" onclick="showDisplaySettings('${driver}')">← Back to Basic Settings</button>
                    <button type="button" onclick="applyPreset('${display?.preset || 'standard'}')">Reset to Preset Defaults</button>
                    <button type="submit" class="primary">Apply Settings</button>
                </div>
            </form>
        </div>
    `;
}

window.applyAdvancedSettings = async function(event) {
    event.preventDefault();
    
    const form = event.target;
    const formData = new FormData(form);
    let success = true;

    for (const [key, value] of formData.entries()) {
        try {
            const response = await window.setupDevice.send(JSON.stringify({
                command: 'config_set',
                config_type: 'display_env',
                key: key,
                value: value
            }));

            if (response.status !== 'success') {
                success = false;
                window.showError(`Failed to update ${key}`);
            }
        } catch (error) {
            success = false;
            console.error(`Failed to update ${key}:`, error);
            window.showError(`Failed to update ${key}: ${error.message}`);
        }
    }

    if (success) {
        window.showMessage('Settings applied successfully');
        // Refresh the display settings view to show the new values
        const driver = window.displayDatabase.displays.find(d => 
            d.driver === form.querySelector('[name="display_model"]')?.value
        )?.driver;
        if (driver) {
            showDisplaySettings(driver);
        }
    }
}

window.applyPreset = async function(presetName) {
    const preset = window.displayDatabase.presets[presetName];
    if (!preset) {
        window.showError('Preset not found');
        return;
    }

    try {
        for (const [key, value] of Object.entries(preset.settings)) {
            await updateSetting(key, value);
        }
        window.showMessage(`Applied ${preset.name} settings`);
        
        // Get the current driver
        const response = await window.setupDevice.send(JSON.stringify({
            command: 'config_get',
            config_type: 'display_env',
            key: 'display_model'
        }));
        
        if (response.status === 'success') {
            showDisplaySettings(response.value);
        }
    } catch (error) {
        console.error('Failed to apply preset:', error);
        window.showError('Failed to apply preset: ' + error.message);
    }
}

window.updateSetting = async function(key, value) {
    try {
        const response = await window.setupDevice.send(JSON.stringify({
            command: 'config_set',
            config_type: 'display_env',
            key: key,
            value: value
        }));

        if (response.status === 'success') {
            window.showMessage(`Updated ${key} to ${value}`);
        } else {
            throw new Error(response.message || 'Failed to update setting');
        }
    } catch (error) {
        console.error(`Failed to update ${key}:`, error);
        window.showError(`Failed to update ${key}: ${error.message}`);
    }
}

window.resetToPreset = async function(presetName) {
    const preset = window.displayDatabase.presets[presetName];
    if (!preset) {
        window.showError('Preset not found');
        return;
    }

    try {
        for (const [key, value] of Object.entries(preset.settings)) {
            await updateSetting(key, value);
        }
        window.showMessage('Settings reset to preset defaults');
        showAdvancedSettings(); // Refresh the form
    } catch (error) {
        console.error('Failed to reset settings:', error);
        window.showError('Failed to reset settings: ' + error.message);
    }
}

window.setDisplayDriver = async function() {
    const driverInput = document.getElementById('driver-input');
    const driver = driverInput.value.trim();
    
    if (!driver) {
        window.showError('Please enter a driver name');
        return;
    }

    await selectDisplay(driver);
} 
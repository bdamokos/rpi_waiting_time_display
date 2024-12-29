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
            // Find all displays with matching driver
            const currentDriver = response.value;
            const compatibleDisplays = database.displays.filter(d => d.driver === currentDriver);
            
            // Render the display setup interface
            displaySetup.innerHTML = `
                <div class="display-setup-container">
                    <h3>Current Configuration</h3>
                    <div class="current-config">
                        <p><strong>Current Driver:</strong> ${currentDriver || 'Not set'}</p>
                        ${compatibleDisplays.length > 0 ? `
                            <p><strong>Compatible tested screens:</strong></p>
                            <div class="display-grid">
                                ${compatibleDisplays.map(display => renderDisplayCard(display, true)).join('')}
                            </div>
                        ` : `
                            <p class="warning">⚠️ Your current driver (${currentDriver}) doesn't match any tested displays in our database.</p>
                        `}
                    </div>
                    
                    <h3>Find Your Display</h3>
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
            // Refresh the display setup view
            startDisplaySetup();
        } else {
            throw new Error(response.message || 'Failed to set display');
        }
    } catch (error) {
        console.error('Failed to set display:', error);
        window.showError('Failed to set display: ' + error.message);
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
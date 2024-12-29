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

        // Show display setup UI
        displaySetup.style.display = 'block';

        // Get current display configuration
        const response = await window.setupDevice.send({
            command: 'display_get_current'
        });

        // Get display database
        const dbResponse = await window.setupDevice.send({
            command: 'display_get_database'
        });

        if (response.status === 'success' && dbResponse.status === 'success') {
            renderDisplaySetup(displaySetup, response.current_config, dbResponse.database);
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

function renderDisplayCard(display) {
    return `
        <div class="display-card" onclick="selectDisplay('${display.driver}')">
            ${display.images && display.images[0] ? 
                `<img src="${display.images[0]}" alt="${display.name}">` : ''}
            <h4>${display.name}</h4>
            <p>Size: ${display.size}"</p>
            <p>Colors: ${display.colors.join(', ')}</p>
            <p>Resolution: ${display.resolution.width}x${display.resolution.height}</p>
            ${display.features.partial_refresh ? '<p>✓ Partial Refresh</p>' : ''}
        </div>
    `;
}

window.selectDisplay = async function(driver) {
    try {
        const response = await window.setupDevice.send({
            command: 'display_set_driver',
            driver: driver
        });

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

// Add styles for display setup
const style = document.createElement('style');
style.textContent = `
    .display-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
        gap: 20px;
        margin: 20px 0;
    }
    .display-card {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 15px;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    .display-card:hover {
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        transform: translateY(-2px);
    }
    .display-card img {
        max-width: 100%;
        height: auto;
        margin-bottom: 10px;
    }
    .mode-buttons {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin: 20px 0;
    }
    .spec-selectors {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 20px;
        margin: 20px 0;
    }
    .checkbox-group {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
    }
    .checkbox-group label {
        display: flex;
        align-items: center;
        gap: 5px;
    }
    .current-config {
        background-color: #e9ecef;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    .warning {
        color: #856404;
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
`;
document.head.appendChild(style); 
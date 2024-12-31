// Advanced Settings Module

let currentSettings = {};

const SETTING_GROUPS = {
    flight: {
        title: "Flight Tracking Settings",
        description: "Configure how the device monitors nearby aircraft",
        settings: {
            flight_check_interval: {
                type: "number",
                label: "Flight Check Interval (seconds)",
                description: "How often to check for flights. Keep this lower than refresh_minimal_time but above 1 second.",
                default: 5
            },
            flight_max_radius: {
                type: "number",
                label: "Maximum Flight Radius (km)",
                description: "Maximum radius in kilometers to check for flights",
                default: 3
            },
            flight_altitude_convert_feet: {
                type: "boolean",
                label: "Convert Altitude to Meters",
                description: "Convert flight altitudes from feet to meters",
                default: false
            },
            flight_display_fast_mode_interval: {
                type: "number",
                label: "Flight Display Update Interval (seconds)",
                description: "How often to update the display when tracking a flight. Uses fast mode if supported.",
                default: 5
            }
        }
    },
    weather: {
        title: "Weather Display Settings",
        description: "Configure weather display options",
        settings: {
            show_sunshine_hours: {
                type: "boolean",
                label: "Show Sunshine Hours",
                description: "Show today's sunshine hours when available (requires Open-Meteo provider)",
                default: true
            },
            show_precipitation: {
                type: "boolean",
                label: "Show Precipitation",
                description: "Show today's precipitation when available",
                default: true
            },
            weather_unit: {
                type: "select",
                label: "Temperature Unit",
                description: "Unit to display temperatures in",
                options: ["celsius", "fahrenheit", "kelvin"],
                default: "celsius"
            }
        }
    },
    iss: {
        title: "ISS Tracking Settings",
        description: "Configure International Space Station tracking behavior",
        settings: {
            iss_check_interval: {
                type: "number",
                label: "ISS Check Interval (seconds)",
                description: "How often to check ISS position during prediction windows",
                default: 30
            },
            iss_priority: {
                type: "boolean",
                label: "ISS Display Priority",
                description: "Show ISS passes instead of bus times when the ISS is overhead",
                default: true
            }
        }
    },
    debug: {
        title: "Debug Settings",
        description: "Settings for development and debugging",
        settings: {
            debug_port_enabled: {
                type: "boolean",
                label: "Enable Debug Port",
                description: "Enable the debug web interface",
                default: true
            },
            debug_port: {
                type: "number",
                label: "Debug Port",
                description: "Port number for the debug web interface",
                default: 5002
            },
            mock_display_type: {
                type: "select",
                label: "Mock Display Type",
                description: "Type of display to simulate in development mode",
                options: ["bw", "color"],
                default: "bw"
            },
            mock_connected_ssid: {
                type: "text",
                label: "Mock Connected SSID",
                description: "SSID to show as connected in development mode",
                default: "hotspot"
            }
        }
    },
    hotspot: {
        title: "Hotspot Settings",
        description: "Configure the fallback Wi-Fi hotspot",
        settings: {
            hotspot_enabled: {
                type: "boolean",
                label: "Enable Hotspot",
                description: "Create a Wi-Fi hotspot when no network is available",
                default: true
            },
            hotspot_ssid: {
                type: "text",
                label: "Hotspot SSID",
                description: "Name of the Wi-Fi hotspot",
                default: "PiHotspot"
            },
            hotspot_password: {
                type: "password",
                label: "Hotspot Password",
                description: "Password for the Wi-Fi hotspot",
                default: "YourPassword"
            }
        }
    },
    refresh: {
        title: "Refresh Intervals",
        description: "Configure various refresh timings",
        settings: {
            refresh_interval: {
                type: "number",
                label: "General Refresh Interval (seconds)",
                description: "How often to refresh the display in normal operation",
                default: 90
            },
            refresh_minimal_time: {
                type: "number",
                label: "Minimum Refresh Time (seconds)",
                description: "Minimum time between display refreshes (typically 25-30 seconds)",
                default: 30
            },
            refresh_weather_interval: {
                type: "number",
                label: "Weather Refresh Interval (seconds)",
                description: "How often to update weather information",
                default: 600
            },
            refresh_full_interval: {
                type: "number",
                label: "Full Refresh Interval (seconds)",
                description: "How often to perform a full display refresh",
                default: 3600
            }
        }
    }
};

async function loadCurrentSettings() {
    try {
        // Load settings one by one
        for (const group of Object.values(SETTING_GROUPS)) {
            for (const [key, setting] of Object.entries(group.settings)) {
                try {
                    const response = await window.setupDevice.send(JSON.stringify({
                        command: 'config_get',
                        config_type: 'display_env',
                        key: key
                    }));

                    if (response.status === 'success') {
                        currentSettings[key] = response.value !== undefined ? response.value : setting.default;
                    } else {
                        currentSettings[key] = setting.default;
                    }
                } catch (error) {
                    console.error(`Failed to load setting ${key}:`, error);
                    currentSettings[key] = setting.default;
                }
            }
        }
    } catch (error) {
        console.error('Failed to load settings:', error);
        window.showError('Failed to load settings: ' + error.message);
    }
}

function createSettingElement(key, setting, value) {
    const container = document.createElement('div');
    container.className = 'setting-item';

    const label = document.createElement('label');
    label.htmlFor = key;
    label.textContent = setting.label;
    container.appendChild(label);

    let input;

    switch (setting.type) {
        case 'boolean':
            input = document.createElement('input');
            input.type = 'checkbox';
            input.checked = value === true || value === "true";
            break;

        case 'password':
            const inputGroup = document.createElement('div');
            inputGroup.className = 'api-input';

            input = document.createElement('input');
            input.type = 'password';
            input.value = value || '';
            input.id = key;
            input.name = key;
            inputGroup.appendChild(input);

            const toggleBtn = document.createElement('button');
            toggleBtn.type = 'button';
            // Eye open SVG when password is hidden (will show on click)
            toggleBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512"><!--!Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2024 Fonticons, Inc.--><path d="M288 32c-80.8 0-145.5 36.8-192.6 80.6C48.6 156 17.3 208 2.5 243.7c-3.3 7.9-3.3 16.7 0 24.6C17.3 304 48.6 356 95.4 399.4C142.5 443.2 207.2 480 288 480s145.5-36.8 192.6-80.6c46.8-43.5 78.1-95.4 93-131.1c3.3-7.9 3.3-16.7 0-24.6c-14.9-35.7-46.2-87.7-93-131.1C433.5 68.8 368.8 32 288 32zM144 256a144 144 0 1 1 288 0 144 144 0 1 1 -288 0zm144-64c0 35.3-28.7 64-64 64c-7.1 0-13.9-1.2-20.3-3.3c-5.5-1.8-11.9 1.6-11.7 7.4c.3 6.9 1.3 13.8 3.2 20.7c13.7 51.2 66.4 81.6 117.6 67.9s81.6-66.4 67.9-117.6c-11.1-41.5-47.8-69.4-88.6-71.1c-5.8-.2-9.2 6.1-7.4 11.7c2.1 6.4 3.3 13.2 3.3 20.3z"/></svg>';
            toggleBtn.title = 'Show password';
            toggleBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (input.type === 'password') {
                    input.type = 'text';
                    // Eye slash SVG when password is visible (will hide on click)
                    toggleBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 512"><!--!Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2024 Fonticons, Inc.--><path d="M38.8 5.1C28.4-3.1 13.3-1.2 5.1 9.2S-1.2 34.7 9.2 42.9l592 464c10.4 8.2 25.5 6.3 33.7-4.1s6.3-25.5-4.1-33.7L525.6 386.7c39.6-40.6 66.4-86.1 79.9-118.4c3.3-7.9 3.3-16.7 0-24.6c-14.9-35.7-46.2-87.7-93-131.1C465.5 68.8 400.8 32 320 32c-68.2 0-125 26.3-169.3 60.8L38.8 5.1zm151 118.3C226 97.7 269.5 80 320 80c65.2 0 118.8 29.6 159.9 67.7C518.4 183.5 545 226 558.6 256c-12.6 28-36.6 66.8-70.9 100.9l-53.8-42.2c9.1-17.6 14.2-37.5 14.2-58.7c0-70.7-57.3-128-128-128c-32.2 0-61.7 11.9-84.2 31.5l-46.1-36.1zM394.9 284.2l-81.5-63.9c4.2-8.5 6.6-18.2 6.6-28.3c0-5.5-.7-10.9-2-16c.7 0 1.3 0 2 0c44.2 0 80 35.8 80 80c0 9.9-1.8 19.4-5.1 28.2zm9.4 130.3C378.8 425.4 350.7 432 320 432c-65.2 0-118.8-29.6-159.9-67.7C121.6 328.5 95 286 81.4 256c8.3-18.4 21.5-41.5 39.4-64.8L83.1 161.5C60.3 191.2 44 220.8 34.5 243.7c-3.3 7.9-3.3 16.7 0 24.6c14.9 35.7 46.2 87.7 93 131.1C174.5 443.2 239.2 480 320 480c47.8 0 89.9-12.9 126.2-32.5l-41.9-33zM192 256c0 70.7 57.3 128 128 128c13.3 0 26.1-2 38.2-5.8L302 334c-23.5-5.4-43.1-21.2-53.7-42.3l-56.1-44.2c-.2 2.8-.3 5.6-.3 8.5z"/></svg>';
                    toggleBtn.title = 'Hide password';
                } else {
                    input.type = 'password';
                    // Eye open SVG when password is hidden (will show on click)
                    toggleBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 576 512"><!--!Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free Copyright 2024 Fonticons, Inc.--><path d="M288 32c-80.8 0-145.5 36.8-192.6 80.6C48.6 156 17.3 208 2.5 243.7c-3.3 7.9-3.3 16.7 0 24.6C17.3 304 48.6 356 95.4 399.4C142.5 443.2 207.2 480 288 480s145.5-36.8 192.6-80.6c46.8-43.5 78.1-95.4 93-131.1c3.3-7.9 3.3-16.7 0-24.6c-14.9-35.7-46.2-87.7-93-131.1C433.5 68.8 368.8 32 288 32zM144 256a144 144 0 1 1 288 0 144 144 0 1 1 -288 0zm144-64c0 35.3-28.7 64-64 64c-7.1 0-13.9-1.2-20.3-3.3c-5.5-1.8-11.9 1.6-11.7 7.4c.3 6.9 1.3 13.8 3.2 20.7c13.7 51.2 66.4 81.6 117.6 67.9s81.6-66.4 67.9-117.6c-11.1-41.5-47.8-69.4-88.6-71.1c-5.8-.2-9.2 6.1-7.4 11.7c2.1 6.4 3.3 13.2 3.3 20.3z"/></svg>';
                    toggleBtn.title = 'Show password';
                }
            };
            inputGroup.appendChild(toggleBtn);
            container.appendChild(inputGroup);
            return container;

        case 'select':
            input = document.createElement('select');
            setting.options.forEach(option => {
                const opt = document.createElement('option');
                opt.value = option;
                opt.textContent = option;
                opt.selected = option === value;
                input.appendChild(opt);
            });
            break;

        default:
            input = document.createElement('input');
            input.type = setting.type || 'text';
            input.value = value || '';
    }

    if (setting.type !== 'password') {
        input.id = key;
        input.name = key;
        container.appendChild(input);
    }

    const description = document.createElement('div');
    description.className = 'setting-description';
    description.textContent = setting.description;
    container.appendChild(description);

    return container;
}

window.startAdvancedSetup = async function () {
    try {
        const container = document.getElementById('advanced-setup-container');
        if (!container) {
            throw new Error("Advanced setup container not found");
        }

        // Show advanced setup UI
        container.style.display = 'block';
        container.innerHTML = '';

        // Load current settings
        await loadCurrentSettings();

        // Create form
        const form = document.createElement('form');
        form.id = 'advanced-settings-form';

        // Add groups
        for (const [groupKey, group] of Object.entries(SETTING_GROUPS)) {
            const groupContainer = document.createElement('div');
            groupContainer.className = 'settings-group';

            const groupTitle = document.createElement('h3');
            groupTitle.textContent = group.title;
            groupContainer.appendChild(groupTitle);

            const groupDescription = document.createElement('p');
            groupDescription.textContent = group.description;
            groupContainer.appendChild(groupDescription);

            for (const [key, setting] of Object.entries(group.settings)) {
                const settingElement = createSettingElement(key, setting, currentSettings[key]);
                groupContainer.appendChild(settingElement);
            }

            form.appendChild(groupContainer);
        }

        // Add save button
        const saveButton = document.createElement('button');
        saveButton.type = 'submit';
        saveButton.textContent = 'Save Settings';
        saveButton.className = 'button';
        form.appendChild(saveButton);

        form.onsubmit = saveAdvancedSettings;
        container.appendChild(form);

    } catch (error) {
        console.error('Failed to start advanced setup:', error);
        window.showError('Advanced Setup Error: ' + error.message);
    }
}

window.saveAdvancedSettings = async function (event) {
    if (event) event.preventDefault();

    try {
        const form = document.getElementById('advanced-settings-form');
        const savePromises = [];

        for (const group of Object.values(SETTING_GROUPS)) {
            for (const [key, setting] of Object.entries(group.settings)) {
                const input = document.getElementById(key);
                if (!input) continue;

                let value;
                switch (setting.type) {
                    case 'boolean':
                        value = input.checked;
                        break;
                    case 'number':
                        value = parseInt(input.value);
                        break;
                    default:
                        value = input.value;
                }

                if (currentSettings[key] !== value) {
                    savePromises.push(
                        window.setupDevice.send(JSON.stringify({
                            command: 'config_set',
                            config_type: 'display_env',
                            key: key,
                            value: value
                        }))
                    );
                }
            }
        }

        if (savePromises.length > 0) {
            await Promise.all(savePromises);
            window.showMessage('Settings saved successfully');
        } else {
            window.showMessage('No settings were changed');
        }
    } catch (error) {
        console.error('Failed to save settings:', error);
        window.showError('Failed to save settings: ' + error.message);
    }
} 
// Advanced Settings Module
import { device } from './setup_device.js';

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
    const settingPromises = [];
    
    // Collect all settings to load
    for (const group of Object.values(SETTING_GROUPS)) {
        for (const [key, setting] of Object.entries(group.settings)) {
            settingPromises.push(
                device.send({ command: "config_get", config_type: "env", key: key })
                    .then(response => {
                        if (response.status === "success") {
                            currentSettings[key] = response.value !== null ? response.value : setting.default;
                        } else {
                            currentSettings[key] = setting.default;
                        }
                    })
                    .catch(() => {
                        currentSettings[key] = setting.default;
                    })
            );
        }
    }
    
    await Promise.all(settingPromises);
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
            input.checked = value;
            break;
            
        case 'password':
            const inputGroup = document.createElement('div');
            inputGroup.className = 'input-group';
            
            input = document.createElement('input');
            input.type = 'password';
            input.value = value || '';
            inputGroup.appendChild(input);
            
            const toggleBtn = document.createElement('button');
            toggleBtn.type = 'button';
            toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
            toggleBtn.title = 'Show password';
            toggleBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (input.type === 'password') {
                    input.type = 'text';
                    toggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i>';
                    toggleBtn.title = 'Hide password';
                } else {
                    input.type = 'password';
                    toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
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

async function startAdvancedSetup() {
    const setupContainer = document.getElementById('advanced-setup-container');
    setupContainer.style.display = 'block';
    
    // Clear existing content
    setupContainer.innerHTML = '';
    
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
    saveButton.textContent = 'Save Settings';
    saveButton.onclick = saveSettings;
    form.appendChild(saveButton);
    
    setupContainer.appendChild(form);
}

async function saveSettings(event) {
    event.preventDefault();
    
    const form = document.getElementById('advanced-settings-form');
    const savePromises = [];
    
    for (const group of Object.values(SETTING_GROUPS)) {
        for (const [key, setting] of Object.entries(group.settings)) {
            const input = document.getElementById(key);
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
            
            savePromises.push(
                device.send({
                    command: "config_set",
                    config_type: "env",
                    key: key,
                    value: value
                })
            );
        }
    }
    
    try {
        await Promise.all(savePromises);
        alert('Settings saved successfully!');
    } catch (error) {
        alert('Error saving settings. Please try again.');
        console.error('Error saving settings:', error);
    }
}

export { startAdvancedSetup }; 
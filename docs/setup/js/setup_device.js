window.showError = function(message) {
    const errorDiv = document.getElementById('error-message');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
        setTimeout(() => {
            errorDiv.style.display = 'none';
        }, 5000);  // Hide after 5 seconds
    }
};

class SetupDevice {
    constructor() {
        this.port = null;
        this.connected = false;
        this.messageBuffer = '';
        this.checkSupport();
        this.setupEventListeners();
    }

    checkSupport() {
        const supportText = document.getElementById('serial-support');
        if ('serial' in navigator) {
            supportText.textContent = 'WebSerial is supported. Click Connect to begin.';
            supportText.style.color = '#2e7d32';
        } else {
            supportText.textContent = 'WebSerial is not supported in this browser. Please use Chrome or Edge.';
            supportText.style.color = '#c62828';
        }
    }

    async connect() {
        try {
            console.log('Requesting serial port...');
            this.port = await navigator.serial.requestPort();
            
            console.log('Opening port...');
            await this.port.open({ baudRate: 115200 });
            
            console.log('Port opened successfully');
            this.connected = true;
            document.getElementById('connect-button').textContent = 'Disconnect';
            document.getElementById('connect-prompt').style.display = 'none';
            document.getElementById('setup-interface').style.display = 'block';
            
            console.log('Starting read loop...');
            this.startReading();
        } catch (error) {
            console.error('Connection failed:', error);
            this.connected = false;
            showError('Connection failed: ' + error.message);
        }
    }

    async startReading() {
        while (this.port.readable && this.connected) {
            const reader = this.port.readable.getReader();
            try {
                while (true) {
                    const { value, done } = await reader.read();
                    if (done || !this.connected) break;
                    this.handleMessage(new TextDecoder().decode(value));
                }
            } catch (error) {
                console.error('Read error:', error);
                showError('Read error: ' + error.message);
            } finally {
                reader.releaseLock();
            }
        }
    }

    async send(message) {
        if (!this.connected) {
            throw new Error('Device not connected');
        }
        const writer = this.port.writable.getWriter();
        try {
            await writer.write(new TextEncoder().encode(message + '\n'));
        } catch (error) {
            console.error('Send error:', error);
            showError('Send error: ' + error.message);
        } finally {
            writer.releaseLock();
        }
    }

    handleMessage(message) {
        try {
            console.log('Received message chunk:', message);
            this.messageBuffer += message;
            
            let startIndex = 0;
            let braceCount = 0;
            let inString = false;
            let escapeNext = false;
            
            for (let i = 0; i < this.messageBuffer.length; i++) {
                const char = this.messageBuffer[i];
                
                if (escapeNext) {
                    escapeNext = false;
                    continue;
                }
                
                if (char === '\\') {
                    escapeNext = true;
                    continue;
                }
                
                if (char === '"' && !escapeNext) {
                    inString = !inString;
                    continue;
                }
                
                if (!inString) {
                    if (char === '{') braceCount++;
                    if (char === '}') {
                        braceCount--;
                        if (braceCount === 0) {
                            const jsonStr = this.messageBuffer.substring(startIndex, i + 1);
                            try {
                                const data = JSON.parse(jsonStr);
                                console.log('Parsed complete JSON:', data);
                                
                                if (data.networks) {
                                    console.log('Updating network list with:', data.networks);
                                    this.updateNetworkList(data.networks);
                                } else if (data.saved_networks) {
                                    console.log('Updating saved networks with:', data.saved_networks);
                                    this.updateSavedNetworks(data.saved_networks);
                                } else if (data.error) {
                                    showError(data.error);
                                } else {
                                    console.log('Received:', data);
                                }
                            } catch (e) {
                                console.error('Error parsing JSON:', e);
                            }
                            startIndex = i + 1;
                        }
                    }
                }
            }
            
            if (startIndex > 0) {
                this.messageBuffer = this.messageBuffer.substring(startIndex);
            }
        } catch (error) {
            console.error('Error handling message:', error);
            showError('Error processing response: ' + error.message);
        }
    }

    updateNetworkList(networks) {
        const list = document.getElementById('wifi-networks-list');
        console.log('Updating network list element:', list);  // Debug log
        if (list) {
            list.innerHTML = networks.map(network => `
                <div class="network-item">
                    <span>${network.ssid}</span>
                    <span>${network.signal}%</span>
                    <button onclick="connectToNetwork('${network.ssid}')">
                        Connect
                    </button>
                </div>
            `).join('');
            console.log('Network list HTML updated');  // Debug log
        } else {
            console.error('Network list element not found');  // Debug log
        }
    }

    updateSavedNetworks(networks) {
        const list = document.getElementById('saved-networks-list');
        if (list) {
            list.innerHTML = networks.map(network => `
                <div class="network-item">
                    <span>${network.ssid}</span>
                    <button onclick="forgetNetwork('${network.uuid}')">
                        Forget
                    </button>
                </div>
            `).join('');
        }
    }

    setupEventListeners() {
        const connectButton = document.getElementById('connect-button');
        console.log('Setting up connect button:', connectButton);
        if (connectButton) {
            connectButton.addEventListener('click', async () => {
                console.log('Connect button clicked, current state:', this.connected);
                try {
                    if (!this.connected) {
                        await this.connect();
                    } else {
                        await this.disconnect();
                    }
                } catch (error) {
                    console.error('Connection error:', error);
                    showError('Connection error: ' + error.message);
                }
            });
        } else {
            console.error('Connect button not found');
        }
    }

    async disconnect() {
        this.connected = false;
        if (this.port) {
            try {
                await this.port.close();
            } catch (error) {
                console.error('Error closing port:', error);
            }
            this.port = null;
        }
        document.getElementById('connect-prompt').style.display = 'block';
        document.getElementById('setup-interface').style.display = 'none';
        document.getElementById('connect-button').textContent = 'Connect';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Create global instance
    window.setupDevice = new SetupDevice();
});

// Export to global scope
window.SetupDevice = SetupDevice; 
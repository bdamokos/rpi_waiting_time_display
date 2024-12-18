// WebUSB device handling
class DisplayDevice {
    constructor() {
        this.device = null;
        this.interfaceNumber = 0;
        this.endpointIn = 0;
        this.endpointOut = 0;
    }

    async connect() {
        try {
            // Request the device with our VID/PID
            this.device = await navigator.usb.requestDevice({
                filters: [{
                    vendorId: 0x1209,  // pid.codes VID
                    productId: 0x0001  // Our custom PID
                }]
            });

            await this.device.open();
            await this.device.selectConfiguration(1);
            await this.device.claimInterface(this.interfaceNumber);

            // Show the setup interface
            document.getElementById('setup-interface').style.display = 'block';
            document.getElementById('connect-prompt').style.display = 'none';

            return true;
        } catch (error) {
            console.error('Connection failed:', error);
            return false;
        }
    }

    async sendCommand(command, data = null) {
        if (!this.device) {
            throw new Error('Device not connected');
        }

        try {
            // Format: [command][length][data]
            const commandBuffer = new ArrayBuffer(2 + (data ? data.length : 0));
            const view = new DataView(commandBuffer);
            view.setUint8(0, command);
            view.setUint8(1, data ? data.length : 0);
            
            if (data) {
                const dataView = new Uint8Array(commandBuffer, 2);
                dataView.set(data);
            }

            await this.device.transferOut(this.endpointOut, commandBuffer);
            
            // Wait for response
            const response = await this.device.transferIn(this.endpointIn, 64);
            return response;
        } catch (error) {
            console.error('Command failed:', error);
            throw error;
        }
    }

    async disconnect() {
        if (this.device) {
            await this.device.close();
            this.device = null;
        }
    }
}

// Create global device instance
const displayDevice = new DisplayDevice();

// Connect handler
async function connectDevice() {
    const success = await displayDevice.connect();
    if (success) {
        console.log('Device connected successfully');
    } else {
        alert('Failed to connect to device. Please make sure it is connected via USB and try again.');
    }
} 
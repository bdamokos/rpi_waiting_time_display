from flask import Flask, send_file, Response
import os
import dotenv
import logging
from pathlib import Path
import threading
import log_config
logger = logging.getLogger(__name__)

# Load environment variables
dotenv.load_dotenv(override=True)
DEBUG_PORT = int(os.getenv("debug_port", "5002"))
DEBUG_ENABLED = os.getenv("debug_port_enabled", "false").lower() == "true"

app = Flask(__name__)

@app.route('/debug/display')
def get_debug_display():
    """Endpoint to get the current display debug image"""
    try:
        return send_file("debug_output.png", 
                        mimetype='image/png',
                        as_attachment=False,
                        download_name='debug_output.png')
    except Exception as e:
        logger.error(f"Error serving debug display: {e}")
        return "Debug image not available", 404

@app.route('/debug/logs')
def get_logs():
    """Endpoint to stream the application logs"""
    try:
        log_file = Path("logs/app.log")
        if not log_file.exists():
            return "Log file not found", 404

        def generate():
            with open(log_file, 'r') as f:
                # First, yield all existing content
                yield f.read()
                
                # Then continue to stream new content
                while True:
                    line = f.readline()
                    if line:
                        yield line
                    else:
                        # No new lines, wait a bit
                        import time
                        time.sleep(1)

        return Response(generate(), mimetype='text/plain')
    except Exception as e:
        logger.error(f"Error serving logs: {e}")
        return "Error accessing logs", 500

@app.route('/debug')
def debug_index():
    """Simple HTML page with links to debug resources"""
    return '''
    <html>
        <head>
            <title>E-Paper Display Debug</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .debug-link { margin: 10px 0; }
                .image-container { margin: 20px 0; }
                #display-image { max-width: 100%; border: 1px solid #ccc; }
                #log-container { 
                    background: #f5f5f5;
                    padding: 10px;
                    border: 1px solid #ccc;
                    height: 400px;
                    overflow: auto;
                    font-family: monospace;
                    white-space: pre;
                }
            </style>
        </head>
        <body>
            <h1>E-Paper Display Debug Interface</h1>
            
            <div class="debug-link">
                <h2>Current Display</h2>
                <div class="image-container">
                    <img id="display-image" src="/debug/display" alt="Current Display">
                </div>
                <button onclick="refreshImage()">Refresh Image</button>
            </div>
            
            <div class="debug-link">
                <h2>Application Logs</h2>
                <div id="log-container">Loading logs...</div>
            </div>

            <script>
                function refreshImage() {
                    const img = document.getElementById('display-image');
                    img.src = '/debug/display?' + new Date().getTime();
                }

                // Auto-refresh image every 10 seconds
                setInterval(refreshImage, 10000);

                // Stream logs
                const logContainer = document.getElementById('log-container');
                fetch('/debug/logs')
                    .then(response => response.body)
                    .then(body => {
                        const reader = body.getReader();
                        let decoder = new TextDecoder();
                        
                        function readChunk() {
                            reader.read().then(({value, done}) => {
                                if (done) return;
                                
                                const text = decoder.decode(value);
                                logContainer.textContent += text;
                                logContainer.scrollTop = logContainer.scrollHeight;
                                
                                readChunk();
                            });
                        }
                        
                        readChunk();
                    })
                    .catch(error => {
                        logContainer.textContent = 'Error loading logs: ' + error;
                    });
            </script>
        </body>
    </html>
    '''

def start_debug_server():
    """Start the debug server if enabled"""
    if not DEBUG_ENABLED:
        logger.info("Debug server is disabled")
        return

    def run_server():
        logger.info(f"Starting debug server on port {DEBUG_PORT}")
        app.run(host='0.0.0.0', port=DEBUG_PORT, debug=False, use_reloader=False)

    # Start server in a separate thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    logger.info("Debug server started in background thread")

if __name__ == "__main__":
    # When run directly, start the server regardless of DEBUG_ENABLED setting
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting debug server in standalone mode")
    app.run(host='0.0.0.0', port=DEBUG_PORT, debug=True)

from flask import Flask, send_file, Response, request, redirect, url_for, abort, render_template
import os
import dotenv
import logging
from pathlib import Path
import threading
import log_config
import sys
from werkzeug.utils import secure_filename
import shutil
from datetime import datetime, timedelta
from config_manager import ConfigManager

logger = logging.getLogger(__name__)

# Load environment variables
dotenv.load_dotenv(override=True)
DEBUG_PORT = int(os.getenv("debug_port", "5002"))
DEBUG_ENABLED = os.getenv("debug_port_enabled", "false").lower() == "true"
FIRST_RUN = os.getenv("first_run", "false").lower() == "true"

app = Flask(__name__)
config_manager = ConfigManager()

def is_local_request():
    """Check if the request is from a local network"""
    if request.remote_addr.startswith('127.') or request.remote_addr.startswith('192.168.') or request.remote_addr.startswith('10.') or request.remote_addr.startswith('172.'):
        return True
    return False

def safe_path(base_path: Path, filename: str) -> Path:
    """
    Safely resolve a file path relative to a base path.
    Prevents path traversal attacks by ensuring the resolved path is within the base directory.
    """
    try:
        base_path = Path(base_path).resolve()
        
        # Explicit whitelist for allowed dotfiles
        ALLOWED_DOTFILES = {'.env', '.env.example', '.env.backup'}
        
        # Check if it's a backup file with timestamp
        is_backup = filename.startswith('.env.backup.') and filename[12:].isdigit()
        
        if filename in ALLOWED_DOTFILES or is_backup:
            sanitized_filename = filename
        else:
            sanitized_filename = secure_filename(filename)
            
        file_path = (base_path / sanitized_filename).resolve()

        # Check if the resolved path is within the base directory
        if not str(file_path).startswith(str(base_path)):
            raise ValueError("Path traversal detected")
            
        return file_path
    except Exception as e:
        logger.error(f"Path validation error: {e}")
        raise ValueError("Invalid path")

@app.route('/debug/restart', methods=['POST'])
def restart_service():
    """Endpoint to trigger service restart by exiting the program"""
    def delayed_exit():
        logger.info("Initiating service restart...")
        import time
        time.sleep(1)
        logger.info("Forcing process exit...")
        os._exit(1)  # Force exit the entire process
    
    # Start delayed exit in separate thread
    logger.info("Restart requested, starting delayed exit thread")
    exit_thread = threading.Thread(target=delayed_exit, daemon=False)
    exit_thread.start()
    return "Restarting service...", 200

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
    """Endpoint to stream systemd service logs"""
    try:
        def generate():
            # Initial logs
            import subprocess
            process = subprocess.Popen(
                ['journalctl', '-u', 'display.service', '-n', '1000', '-f'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            while True:
                line = process.stdout.readline()
                if line:
                    yield line
                else:
                    import time
                    time.sleep(0.1)

        return Response(generate(), mimetype='text/plain')
    except Exception as e:
        logger.error(f"Error serving logs: {e}")
        return "Error accessing logs", 500

@app.route('/debug')
@app.route('/debug/')
@app.route('/')
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
                .danger-zone {
                    margin-top: 20px;
                    padding: 10px;
                    border: 2px solid #ff4444;
                    border-radius: 5px;
                }
                .danger-button {
                    background-color: #ff4444;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 5px;
                    cursor: pointer;
                }
                .danger-button:hover {
                    background-color: #ff0000;
                }
                .log-controls {
                    margin: 10px 0;
                }
                .log-controls button {
                    padding: 5px 15px;
                    margin-right: 10px;
                    cursor: pointer;
                }
                .log-controls button.active {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
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
                <a href="/debug/display" download="debug_output.png">
                    <button>Download Image</button>
                </a>
            </div>
            
            <div class="debug-link">
                <h2>Application Logs</h2>
                <div class="log-controls">
                    <button id="pauseButton" onclick="toggleLogPause()">⏸️ Pause</button>
                    <button onclick="clearLogs()">🗑️ Clear</button>
                </div>
                <div id="log-container">Loading logs...</div>
            </div>

            <div class="debug-link">
                <h2>Edit .env File</h2>
                <a href="/debug/env">
                    <button>Edit .env</button>
                </a>
            </div>

            <div class="danger-zone">
                <h2>⚠️ Danger Zone</h2>
                <p>Use these controls with caution:</p>
                <button class="danger-button" onclick="restartService()">
                    Restart the display service
                </button>
            </div>

            <script>
                let isPaused = false;
                let logReader = null;
                let logDecoder = new TextDecoder();

                function refreshImage() {
                    const img = document.getElementById('display-image');
                    img.src = '/debug/display?' + new Date().getTime();
                }

                function restartService() {
                    if (confirm('Are you sure you want to restart the display service?')) {
                        fetch('/debug/restart', { method: 'POST' })
                            .then(response => {
                                if (response.ok) {
                                    alert('Service restart initiated. Page will reload in 30 seconds.');
                                    setTimeout(() => location.reload(), 30000);
                                } else {
                                    alert('Failed to restart service');
                                }
                            })
                            .catch(error => {
                                alert('Error: ' + error);
                            });
                    }
                }

                function toggleLogPause() {
                    isPaused = !isPaused;
                    const button = document.getElementById('pauseButton');
                    if (isPaused) {
                        button.textContent = '▶️ Resume';
                        button.classList.add('active');
                    } else {
                        button.textContent = '⏸️ Pause';
                        button.classList.remove('active');
                        // Resume reading if we have a reader
                        if (logReader) {
                            readChunk();
                        }
                    }
                }

                function clearLogs() {
                    const logContainer = document.getElementById('log-container');
                    logContainer.textContent = '';
                }

                // Auto-refresh image every 10 seconds
                setInterval(refreshImage, 10000);

                // Stream logs
                const logContainer = document.getElementById('log-container');
                fetch('/debug/logs')
                    .then(response => response.body)
                    .then(body => {
                        logReader = body.getReader();
                        readChunk();
                    })
                    .catch(error => {
                        logContainer.textContent = 'Error loading logs: ' + error;
                    });

                function readChunk() {
                    if (!isPaused && logReader) {
                        logReader.read().then(({value, done}) => {
                            if (done) return;
                            
                            const text = logDecoder.decode(value);
                            logContainer.textContent += text;
                            logContainer.scrollTop = logContainer.scrollHeight;
                            
                            readChunk();
                        });
                    }
                }
            </script>
        </body>
    </html>
    '''

@app.route('/debug/env', methods=['GET', 'POST'])
def edit_env():
    """Endpoint to view and edit the .env file"""
    if not is_local_request():
        logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
        abort(403)

    try:
        # Handle POST requests for saving/restoring
        if request.method == 'POST':
            if 'restore' in request.form:
                config_type = request.form.get('config_type')
                restore_file = request.form.get('restore_file')
                if config_manager.restore_backup(config_type, restore_file):
                    return redirect(url_for('edit_env'))
                return "Error restoring file", 500

            elif 'save' in request.form:
                config_type = request.form.get('config_type')
                new_content = request.form.get('content')
                if config_manager.update_config(config_type, new_content):
                    return redirect(url_for('edit_env'))
                return "Error updating file", 500

        # Read configurations
        configs = {}
        for config_type in ['display_env', 'transit_env', 'transit_local']:
            content, variables = config_manager.read_config(config_type, verbose=True)
            backups = config_manager.get_backup_files(config_type)
            configs[config_type] = {
                'content': content,
                'variables': variables,
                'backups': backups
            }

        # Generate HTML...
        return render_template('env_editor.html', configs=configs)

    except Exception as e:
        logger.error(f"Error in edit_env: {e}")
        return "Internal server error", 500

@app.route('/favicon.ico')
def favicon():
    """Return 204 No Content for favicon requests"""
    return '', 204


def start_debug_server():
    """Start the debug server if enabled"""
    if not DEBUG_ENABLED:
        logger.info("Debug server is disabled")
        return

    def run_server():
        logger.info(f"Starting debug server on port {DEBUG_PORT}")
        # Additional security settings
        app.config['MAX_CONTENT_LENGTH'] = 16 * 1024  # Limit request size to 16KB
        app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
        app.run(host='0.0.0.0', port=DEBUG_PORT, 
               debug=False, use_reloader=False)  

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    logger.info("Debug server started in background thread")



if __name__ == "__main__":
    # When run directly, start the server regardless of DEBUG_ENABLED setting
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting debug server in standalone mode")
    app.run(host='0.0.0.0', port=DEBUG_PORT, debug=False)

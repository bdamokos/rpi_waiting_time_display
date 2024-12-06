from flask import Flask, send_file, Response, request, redirect, url_for, abort
import os
import dotenv
import logging
from pathlib import Path
import threading
import log_config
import sys
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)

# Load environment variables
dotenv.load_dotenv(override=True)
DEBUG_PORT = int(os.getenv("debug_port", "5002"))
DEBUG_ENABLED = os.getenv("debug_port_enabled", "false").lower() == "true"

app = Flask(__name__)

def is_local_request():
    """Check if the request is from a local network"""
    if request.remote_addr.startswith('127.') or request.remote_addr.startswith('192.168.') or request.remote_addr.startswith('10.') or request.remote_addr.startswith('172.'):
        return True
    return False

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
                <button class="danger-button" onclick="restartService()">Restart Display Service</button>
            </div>

            <script>
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

@app.route('/debug/env', methods=['GET', 'POST'])
def edit_env():
    """Endpoint to view and edit the .env file"""
    if not is_local_request():
        logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
        abort(403)  # Forbidden

    env_path = Path('.env')
    backup_dir = Path('env_backups')
    backup_dir.mkdir(exist_ok=True)
    
    if request.method == 'POST':
        # Save the updated .env content
        new_content = request.form.get('env_content', '')
        
        # Create a backup before saving
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        backup_path = backup_dir / f'.env.backup.{timestamp}'
        try:
            shutil.copy(env_path, backup_path)
            logger.info(f".env file backed up to {backup_path}")
            
            # Rotate backups, keep only the last 5
            backups = sorted(backup_dir.glob('.env.backup.*'), key=os.path.getmtime, reverse=True)
            for old_backup in backups[5:]:
                old_backup.unlink()
                logger.info(f"Old backup {old_backup} removed")
            
            with open(env_path, 'w') as f:
                f.write(new_content)
            logger.info(".env file updated successfully")
            return redirect(url_for('edit_env'))
        except Exception as e:
            logger.error(f"Error updating .env file: {e}")
            return f"Error updating .env file: {e}", 500
    
    # Read the current .env content
    try:
        with open(env_path, 'r') as f:
            env_content = f.read()
    except Exception as e:
        logger.error(f"Error reading .env file: {e}")
        env_content = "Error reading .env file"
    
    # Generate shell commands for restoring backups
    backup_files = sorted(backup_dir.glob('.env.backup.*'), key=os.path.getmtime, reverse=True)
    restore_commands = "\n".join(
        f"cp {backup_file} .env" for backup_file in backup_files
    )
    
    return f'''
    <html>
        <head>
            <title>Edit .env File</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                textarea {{ width: 100%; height: 400px; }}
                button {{ margin-top: 10px; }}
                pre {{ background: #f5f5f5; padding: 10px; border: 1px solid #ccc; }}
            </style>
        </head>
        <body>
            <h1>Edit .env File</h1>
            <form method="post">
                <textarea name="env_content">{env_content}</textarea><br>
                <button type="submit">Save Changes</button>
            </form>
            <h2>Restore .env from Backup</h2>
            <p>If the server is unresponsive, use the following shell commands to restore a backup:</p>
            <pre>{restore_commands}</pre>
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

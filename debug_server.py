from flask import Flask, send_file, Response, request, redirect, url_for, abort
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

logger = logging.getLogger(__name__)

# Load environment variables
dotenv.load_dotenv(override=True)
DEBUG_PORT = int(os.getenv("debug_port", "5002"))
DEBUG_ENABLED = os.getenv("debug_port_enabled", "false").lower() == "true"
FIRST_RUN = os.getenv("first_run", "false").lower() == "true"

app = Flask(__name__)

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

    try:
        # Safely resolve paths
        base_dir = Path().resolve()
        env_path = safe_path(base_dir, '.env')
        example_path = safe_path(base_dir, '.env.example')
        backup_dir = safe_path(base_dir, 'env_backups')
        backup_dir.mkdir(exist_ok=True)

        def parse_env_file(file_path):
            """Parse an env file into a dictionary of variables"""
            if not file_path.exists():
                return {}
            
            env_vars = {}
            try:
                with open(file_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if '=' in line:
                                key, value = line.split('=', 1)
                                env_vars[key.strip()] = value.strip()
            except Exception as e:
                logger.error(f"Error parsing {file_path}: {e}")
            return env_vars

        # Handle POST requests for saving/restoring
        if request.method == 'POST':
            if 'restore' in request.form:
                restore_file = request.form.get('restore_file')
                if restore_file:
                    try:
                        # Validate restore file path
                        restore_path = safe_path(base_dir, restore_file)
                        if not restore_path.is_file():
                            raise ValueError("Invalid restore file")
                        
                        shutil.copy(restore_path, env_path)
                        logger.info(f".env file restored from {restore_path}")
                        return redirect(url_for('edit_env'))
                    except Exception as e:
                        logger.error(f"Error restoring .env file: {e}")
                        return "Invalid restore file", 400

            elif 'confirm_settings' in request.form:
                current_vars = parse_env_file(env_path)
                if current_vars.get('first_run', 'false').lower() == 'true':
                    current_vars['first_run'] = 'false'
                    try:
                        with open(env_path, 'w') as f:
                            for key, value in current_vars.items():
                                f.write(f"{key}={value}\n")
                        logger.info("first_run set to false, restarting Raspberry Pi")
                        os._exit(1)
                    except Exception as e:
                        logger.error(f"Error updating .env file: {e}")
                        return "Error updating settings", 500
                else:
                    return redirect(url_for('restart_service'))

            else:
                # Save the updated .env content
                new_content = request.form.get('env_content', '')
                if not new_content.strip():
                    return "Empty content not allowed", 400

                try:
                    # Create backup
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    backup_path = safe_path(backup_dir, f'.env.backup.{timestamp}')
                    shutil.copy(env_path, backup_path)
                    logger.info(f".env file backed up to {backup_path}")

                    # Rotate backups
                    backups = sorted(backup_dir.glob('.env.backup.*'), 
                                  key=os.path.getmtime, reverse=True)
                    for old_backup in backups[5:]:
                        old_backup.unlink()

                    # Write new content
                    with open(env_path, 'w') as f:
                        f.write(new_content)
                    logger.info(".env file updated successfully")
                    return redirect(url_for('edit_env'))
                except Exception as e:
                    logger.error(f"Error updating .env file: {e}")
                    return "Error updating file", 500

        # Read both .env and .env.example
        current_vars = parse_env_file(env_path)
        example_vars = parse_env_file(example_path)

        # Create a combined set of all variables
        all_vars = sorted(set(list(current_vars.keys()) + list(example_vars.keys())))

        # Generate comparison HTML
        vars_comparison = ""
        for var in all_vars:
            in_current = var in current_vars
            in_example = var in example_vars
            current_value = current_vars.get(var, '')
            example_value = example_vars.get(var, '')
            
            status_class = ''
            status_text = ''
            
            if in_current and in_example:
                if current_value != example_value:
                    status_class = 'modified'
                    status_text = '(Modified)'
            elif in_current and not in_example:
                status_class = 'extra'
                status_text = '(Not in example)'
            elif not in_current and in_example:
                status_class = 'missing'
                status_text = '(Missing)'
            
            vars_comparison += f'<div class="var-row {status_class}">'
            vars_comparison += f'<span class="var-name">{var}</span>'
            vars_comparison += f'<span class="var-status">{status_text}</span>'
            if in_example:
                vars_comparison += f'<div class="var-example">Example: {example_value}</div>'
            vars_comparison += '</div>'

        # Read the current .env content for the textarea
        try:
            with open(env_path, 'r') as f:
                env_content = f.read()
        except Exception as e:
            logger.error(f"Error reading .env file: {e}")
            env_content = "Error reading .env file"
        
        # Generate shell commands for restoring backups
        backup_files = sorted(backup_dir.glob('.env.backup.*'), key=os.path.getmtime, reverse=True)
        restore_options = [(str(backup_file), backup_file.name) for backup_file in backup_files]
        example_file = Path('.env.example')
        if example_file.exists():
            restore_options.append((str(example_file), '.env.example'))
        
        restore_commands = "\n".join(
            f"cp {backup_file} .env" for backup_file, _ in restore_options
        )
        
        restore_options_html = "\n".join(
            f'<option value="{file_path}">{file_name}</option>' for file_path, file_name in restore_options
        )

        # Determine if the "Confirm Settings" button should be shown
        show_confirm_button = current_vars.get('first_run', 'false').lower() == 'true'
        
        return f'''
        <html>
            <head>
                <title>Edit .env File</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .env-container {{ display: flex; gap: 20px; }}
                    .editor-section {{ flex: 1; }}
                    .vars-section {{ flex: 1; }}
                    textarea {{ width: 100%; height: 400px; font-family: monospace; }}
                    button {{ margin-top: 10px; }}
                    pre {{ background: #f5f5f5; padding: 10px; border: 1px solid #ccc; }}
                    .var-row {{ padding: 5px; margin: 5px 0; border-left: 3px solid transparent; }}
                    .var-name {{ font-weight: bold; }}
                    .var-status {{ color: #666; margin-left: 10px; font-size: 0.9em; }}
                    .var-example {{ color: #666; font-size: 0.9em; margin-left: 20px; }}
                    .modified {{ border-left-color: #ffa500; background: #fff3e0; }}
                    .extra {{ border-left-color: #2196f3; background: #e3f2fd; }}
                    .missing {{ border-left-color: #f44336; background: #ffebee; }}
                    .back-button {{ 
                        background-color: #4CAF50;
                        color: white;
                        padding: 10px 20px;
                        text-decoration: none;
                        border-radius: 5px;
                        display: inline-block;
                        margin-bottom: 20px;
                    }}
                    .back-button:hover {{
                        background-color: #45a049;
                    }}
                </style>
            </head>
            <body>
                <a href="/debug" class="back-button">← Back to Debug</a>
                <h1>Edit .env File</h1>
                <div class="env-container">
                    <div class="editor-section">
                        <h2>Edit Configuration</h2>
                        <form method="post">
                            <textarea name="env_content">{env_content}</textarea><br>
                            <button type="submit">Save Changes</button>
                        </form>
                    </div>
                    <div class="vars-section">
                        <h2>Variables Overview</h2>
                        <div class="vars-comparison">
                            {vars_comparison}
                        </div>
                    </div>
                </div>
                
                <h2>Restore .env from Backup</h2>
                <form method="post">
                    <select name="restore_file">
                        {restore_options_html}
                    </select>
                    <button type="submit" name="restore">Restore Selected</button>
                </form>
                <p>If the server is unresponsive, use the following shell commands to restore a backup:</p>
                <pre>{restore_commands}</pre>

                <h2>Confirm Initial Settings</h2>
                <form method="post">
                    <button type="submit" name="confirm_settings">
                        {'I am happy with my initial settings, restart my Pi' if show_confirm_button else 'Restart Display Service'}
                    </button>
                </form>
            </body>
        </html>
        '''

    except Exception as e:
        logger.error(f"Error in edit_env: {e}")
        return "Internal server error", 500

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

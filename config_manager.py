import os
import json
import logging
import log_config
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        self.home_dir = Path.home()
        self.display_dir = self.home_dir / 'display_programme'
        self.transit_dir = self.home_dir / 'brussels_transit'
        self.current_session = None
        self.last_change_time = None
        self.SESSION_TIMEOUT = 300  # 5 minutes
        self.config_files = {
            'display_env': self.display_dir / '.env',
            'display_env_example': self.display_dir / '.env.example',
            'transit_env': self.transit_dir / '.env',
            'transit_env_example': self.transit_dir / '.env.example',
            'transit_local': self.transit_dir / 'app' / 'config' / 'local.py',
            'transit_local_example': self.transit_dir / 'app' / 'config' / 'local.py.example'
        }
        self.backup_dirs = {
            'display_env': self.display_dir / 'env_backups',
            'transit_env': self.transit_dir / 'env_backups',
            'transit_local': self.transit_dir / 'app' / 'config' / 'backups'
        }
        self._init_backup_dirs()

    def _init_backup_dirs(self):
        """Create backup directories if they don't exist"""
        for backup_dir in self.backup_dirs.values():
            backup_dir.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, base_path: Path, filename: str) -> Path:
        """Validate and resolve a file path safely"""
        try:
            # Ensure base_path is a Path object and exists
            if not isinstance(base_path, Path) or not base_path.exists():
                raise ValueError("Invalid base path")
            
            # Normalize the base path
            base_path = base_path.resolve()
            
            # Prevent directory traversal by removing path separators
            clean_filename = os.path.basename(filename)
            if clean_filename != filename:
                raise ValueError("Path traversal detected in filename")
            
            # Additional validation for backup files
            if '.backup.' in clean_filename:
                # Ensure the backup file follows our naming convention
                parts = clean_filename.split('.backup.')
                if len(parts) != 2 or not parts[1].isdigit() or len(parts[1]) != 20:  # YYYYMMDDHHmmssxxxxxx
                    raise ValueError("Invalid backup filename format")
            
            # Construct and validate the final path
            file_path = (base_path / clean_filename).resolve()
            
            # Ensure the resolved path is within the base directory
            if not str(file_path).startswith(str(base_path)):
                raise ValueError("Path traversal detected")
            
            # Additional check: ensure the parent directory exists and is within base_path
            parent_dir = file_path.parent.resolve()
            if not str(parent_dir).startswith(str(base_path)):
                raise ValueError("Invalid parent directory")
                
            return file_path
        except ValueError as e:
            logger.error(f"Path validation error: {e}")
            raise  # Re-raise the original ValueError with its message
        except Exception as e:
            logger.error(f"Path validation error: {e}")
            raise ValueError(f"Invalid path: {str(e)}")

    def _get_example_config_type(self, config_type: str) -> str:
        """Get the example config type for a given config type"""
        return f"{config_type}_example"

    def _parse_env_example(self, content: str) -> Dict[str, Dict[str, str]]:
        """Parse an env example file into a dictionary with values and explanations"""
        variables = {}
        current_explanation = []
        
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('#'):
                current_explanation.append(line[1:].strip())
            elif '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                variables[key] = {
                    'value': value.strip(),
                    'explanation': '\n'.join(current_explanation) if current_explanation else None
                }
                current_explanation = []
                
        return variables

    def _parse_python_example(self, content: str) -> Dict[str, Dict[str, str]]:
        """Parse a Python example file into a dictionary with values and explanations"""
        variables = {}
        current_explanation = []
        
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('#'):
                current_explanation.append(line[1:].strip())
            elif '=' in line:
                key, value = [part.strip() for part in line.split('=', 1)]
                if value.startswith(("'", '"')) and value.endswith(("'", '"')):
                    value = value[1:-1]
                variables[key] = {
                    'value': value,
                    'explanation': '\n'.join(current_explanation) if current_explanation else None
                }
                current_explanation = []
                
        return variables

    def _should_create_backup(self) -> bool:
        """Determine if a new backup should be created based on session timing"""
        current_time = datetime.now()
        logger.debug(f"Checking if backup should be created. last_change_time: {self.last_change_time}, current_time: {current_time}")

        # Always create a backup if last_change_time is None
        if self.last_change_time is None:
            logger.debug("Creating new backup: no previous change time")
            self.current_session = current_time
            return True

        # Create a backup if we've exceeded the timeout
        time_diff = (current_time - self.last_change_time).total_seconds()
        if time_diff > self.SESSION_TIMEOUT:
            logger.debug(f"Creating new backup: session timeout exceeded ({time_diff} seconds)")
            self.current_session = current_time
            return True

        # Don't create a backup if we're within the same session
        logger.debug(f"Not creating backup: within same session (time_diff: {time_diff} seconds)")
        return False

    def read_config(self, config_type: str, verbose: bool = False) -> Tuple[str, Dict[str, str]]:
        """Read a configuration file and parse its contents"""
        if config_type not in self.config_files:
            raise ValueError(f"Unknown config type: {config_type}")

        file_path = self.config_files[config_type]
        if not file_path.exists():
            return "", {}

        content = file_path.read_text()
        
        # Parse different file types
        if config_type.endswith('_env'):
            variables = self._parse_env_file(content)
        elif config_type.endswith('_local'):
            variables = self._parse_python_config(content)
        else:
            variables = {}

        # If verbose, include example values and explanations
        if verbose:
            example_type = self._get_example_config_type(config_type)
            example_path = self.config_files.get(example_type)
            if example_path and example_path.exists():
                example_content = example_path.read_text()
                if config_type.endswith('_env'):
                    example_vars = self._parse_env_example(example_content)
                else:
                    example_vars = self._parse_python_example(example_content)
                    
                # Enhance variables with example data
                enhanced_vars = {}
                for key, value in variables.items():
                    enhanced_vars[key] = {
                        'value': value,
                        'example': example_vars.get(key, {}).get('value'),
                        'explanation': example_vars.get(key, {}).get('explanation')
                    }
                return content, enhanced_vars

        return content, variables

    def _parse_env_file(self, content: str) -> Dict[str, str]:
        """Parse an env file into a dictionary"""
        variables = {}
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    variables[key.strip()] = value.strip()
        return variables

    def _parse_python_config(self, content: str) -> Dict[str, str]:
        """Parse a Python config file into a dictionary"""
        variables = {}
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = [part.strip() for part in line.split('=', 1)]
                    # Remove quotes if present
                    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
                        value = value[1:-1]
                    variables[key] = value
        return variables

    def update_config(self, config_type: str, content: str) -> bool:
        """Update a configuration file with new content"""
        try:
            if config_type not in self.config_files:
                raise ValueError(f"Unknown config type: {config_type}")

            file_path = self.config_files[config_type]
            backup_dir = self.backup_dirs.get(config_type)

            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create backup if needed
            if backup_dir:
                # Create backup directory if it doesn't exist
                backup_dir.mkdir(parents=True, exist_ok=True);

                # Check if we should create a backup
                should_backup = self._should_create_backup()
                logger.debug(f"Should create backup: {should_backup}, last_change_time: {self.last_change_time}")

                if should_backup:
                    # Create backup with current timestamp (including milliseconds)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')[:20]  # YYYYMMDDHHmmssxxxxxx
                    backup_path = backup_dir / f"{file_path.name}.backup.{timestamp}"

                    # If file exists, copy it; otherwise create an empty backup
                    if file_path.exists():
                        shutil.copy2(file_path, backup_path)
                    else:
                        backup_path.write_text("")

                    logger.debug(f"Created backup: {backup_path}")
                    # Update last_change_time only after successful backup creation
                    self.last_change_time = datetime.now()
                else:
                    logger.debug("Backup not created: within same session")

            # Write new content
            file_path.write_text(content)
            logger.debug(f"Updated config file: {file_path}")

            # Rotate backups after writing new content
            if backup_dir:
                # Get current backup files
                backup_files = []
                for f in backup_dir.glob(f"{file_path.name}.backup.*"):
                    if f.is_file():
                        try:
                            timestamp = f.name.split('.backup.')[1]
                            if timestamp.isdigit() and len(timestamp) == 20:  # YYYYMMDDHHmmssxxxxxx
                                backup_files.append((f, timestamp))
                                logger.debug(f"Found backup file: {f} with timestamp {timestamp}")
                        except Exception:
                            continue

                # Sort by timestamp (newest first)
                backup_files.sort(key=lambda x: x[1], reverse=True)
                logger.debug(f"Found {len(backup_files)} backup files after sorting")
                logger.debug(f"Sorted backup files: {[f'{f.name} ({ts})' for f, ts in backup_files]}")

                # Keep only the last 5 backups
                if len(backup_files) > 5:
                    files_to_remove = backup_files[5:]  # Remove all but the first 5 (newest)
                    logger.debug(f"Found {len(backup_files)} backups, removing {len(files_to_remove)} old ones")
                    logger.debug(f"Files to remove: {[f'{f.name} ({ts})' for f, ts in files_to_remove]}")
                    for old_backup, ts in files_to_remove:
                        try:
                            old_backup.unlink()
                            logger.debug(f"Removed old backup: {old_backup} ({ts})")
                        except Exception as e:
                            logger.error(f"Error removing old backup {old_backup}: {e}")

            return True

        except Exception as e:
            logger.error(f"Error updating config {config_type}: {e}")
            return False

    def get_value(self, config_type: str, key: str) -> Optional[str]:
        """Get a specific value from a configuration file"""
        try:
            _, variables = self.read_config(config_type)
            return variables.get(key)
        except Exception as e:
            logger.error(f"Error getting value {key} from {config_type}: {e}")
            return None

    def set_value(self, config_type: str, key: str, value: str) -> bool:
        """Set a specific value in a configuration file"""
        try:
            content, variables = self.read_config(config_type)
            variables[key] = value

            # Reconstruct file content
            if config_type.endswith('_env'):
                new_content = '\n'.join(f"{k}={v}" for k, v in variables.items())
            elif config_type.endswith('_local'):
                new_content = '\n'.join(f"{k} = '{v}'" for k, v in variables.items())
            else:
                raise ValueError(f"Unsupported config type: {config_type}")

            return self.update_config(config_type, new_content)

        except Exception as e:
            logger.error(f"Error setting value {key}={value} in {config_type}: {e}")
            return False

    def get_backup_files(self, config_type: str) -> List[Path]:
        """Get list of backup files for a config type"""
        if config_type not in self.backup_dirs:
            return []

        backup_dir = self.backup_dirs[config_type]
        try:
            # Get all backup files sorted by modification time
            base_name = self.config_files[config_type].name
            pattern = f"{base_name}.backup.*"
            logger.debug(f"Looking for backup files matching pattern: {pattern}")
            
            # First collect all valid backup files
            backups = []
            for f in backup_dir.glob(pattern):
                if f.is_file():
                    try:
                        # Extract timestamp from filename
                        timestamp = f.name.split('.backup.')[1]
                        if timestamp.isdigit() and len(timestamp) == 20:  # YYYYMMDDHHmmssxxxxxx
                            backups.append(f)
                            logger.debug(f"Found valid backup: {f}")
                    except Exception as e:
                        logger.warning(f"Skipping invalid backup file {f}: {e}")
                        continue
            
            # Sort by timestamp (newest first)
            backups.sort(key=lambda x: x.name.split('.backup.')[1], reverse=True)
            
            logger.debug(f"Found {len(backups)} valid backup files in {backup_dir}")
            return backups
            
        except Exception as e:
            logger.error(f"Error getting backup files for {config_type}: {e}")
            return []

    def restore_backup(self, config_type: str, backup_file: str) -> bool:
        """Restore a configuration from a backup file"""
        try:
            if config_type not in self.config_files:
                raise ValueError(f"Unknown config type: {config_type}")

            # Get and validate the backup directory
            backup_dir = self.backup_dirs.get(config_type)
            if not backup_dir:
                raise ValueError(f"No backup directory for config type: {config_type}")

            # Validate and resolve the backup file path
            backup_path = self._safe_path(backup_dir, backup_file)
            if not backup_path.exists():
                raise ValueError(f"Backup file does not exist: {backup_file}")

            # Verify that this is actually a backup file
            if not backup_path.name.startswith(self.config_files[config_type].name + '.backup.'):
                raise ValueError("Invalid backup file name")

            # Get and validate the target config file path
            target_path = self.config_files[config_type]
            if not isinstance(target_path, Path):
                raise ValueError("Invalid target path")
            target_path = target_path.resolve()

            # Ensure the target path is within one of our managed directories
            valid_dirs = [self.display_dir, self.transit_dir]
            if not any(str(target_path).startswith(str(base_dir.resolve())) 
                      for base_dir in valid_dirs):
                raise ValueError("Invalid target path location")

            # Create a temporary copy first
            temp_path = target_path.parent / f".temp_{target_path.name}"
            try:
                shutil.copy2(backup_path, temp_path)
                # If copy was successful, rename to final location
                temp_path.replace(target_path)
                return True
            finally:
                # Clean up temp file if it exists
                if temp_path.exists():
                    temp_path.unlink()

        except ValueError as e:
            logger.error(f"Error restoring backup {backup_file} for {config_type}: {e}")
            raise  # Re-raise the original ValueError
        except Exception as e:
            logger.error(f"Error restoring backup {backup_file} for {config_type}: {e}")
            return False 
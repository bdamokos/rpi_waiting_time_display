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
        """Safely resolve a file path relative to a base path"""
        try:
            base_path = Path(base_path).resolve()
            
            # Explicit whitelist for allowed dotfiles
            ALLOWED_DOTFILES = {'.env', '.env.example', '.env.backup', 'local.py', 'local.py.example'}
            
            # Check if it's a backup file with timestamp
            is_backup = any(
                filename.startswith(f"{prefix}.backup.") and filename.split('.')[-1].isdigit()
                for prefix in ['.env', 'local.py']
            )
            
            if filename in ALLOWED_DOTFILES or is_backup:
                sanitized_filename = filename
            else:
                raise ValueError(f"Invalid filename: {filename}")
                
            file_path = (base_path / sanitized_filename).resolve()

            # Check if the resolved path is within the base directory
            if not str(file_path).startswith(str(base_path)):
                raise ValueError("Path traversal detected")
                
            return file_path
        except Exception as e:
            logger.error(f"Path validation error: {e}")
            raise ValueError("Invalid path")

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
        
        # If this is the first change or we've exceeded the timeout
        if (self.last_change_time is None or 
            (current_time - self.last_change_time).total_seconds() > self.SESSION_TIMEOUT):
            self.current_session = current_time
            self.last_change_time = current_time
            return True
            
        # Update last change time but don't create backup
        self.last_change_time = current_time
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

            if backup_dir and self._should_create_backup():
                # Create backup
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                backup_path = backup_dir / f"{file_path.name}.backup.{timestamp}"
                if file_path.exists():
                    shutil.copy(file_path, backup_path)

                # Rotate backups (keep last 5)
                self._rotate_backups(backup_dir)

            # Write new content
            file_path.write_text(content)
            return True

        except Exception as e:
            logger.error(f"Error updating config {config_type}: {e}")
            return False

    def _rotate_backups(self, backup_dir: Path, keep: int = 5):
        """Rotate backup files, keeping only the most recent ones"""
        backups = sorted(backup_dir.glob('*.backup.*'), key=os.path.getmtime, reverse=True)
        for old_backup in backups[keep:]:
            old_backup.unlink()

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
        return sorted(backup_dir.glob(f"{self.config_files[config_type].name}.backup.*"),
                     key=os.path.getmtime, reverse=True)

    def restore_backup(self, config_type: str, backup_file: str) -> bool:
        """Restore a configuration from a backup file"""
        try:
            if config_type not in self.config_files:
                raise ValueError(f"Unknown config type: {config_type}")

            backup_path = self._safe_path(self.backup_dirs[config_type], backup_file)
            if not backup_path.exists():
                raise ValueError(f"Backup file does not exist: {backup_file}")

            shutil.copy(backup_path, self.config_files[config_type])
            return True

        except Exception as e:
            logger.error(f"Error restoring backup {backup_file} for {config_type}: {e}")
            return False 
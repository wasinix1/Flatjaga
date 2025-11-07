"""
Session tracking manager for auto-contact processors.
Tracks when sessions were last validated to prevent expiry.
"""

import json
import time
from pathlib import Path
from datetime import datetime
from flathunter.logger_config import logger

SESSION_TIMEOUT = 2 * 60 * 60  # 2 hours in seconds


class SessionManager:
    """Manages session timestamps and validation state for auto-contact processors"""

    def __init__(self):
        self.state_file = Path.home() / '.flathunt_session_state.json'
        self.state = self._load_state()

    def _load_state(self):
        """Load session state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load session state: {e}")

        # Default state
        return {
            'willhaben': {
                'last_check': 0,
                'enabled': True,
                'last_validation': None
            },
            'wg_gesucht': {
                'last_check': 0,
                'enabled': True,
                'last_validation': None
            }
        }

    def _save_state(self):
        """Save session state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save session state: {e}")

    def needs_validation(self, processor_name):
        """Check if session needs validation (2+ hours passed)"""
        last_check = self.state.get(processor_name, {}).get('last_check', 0)
        elapsed = time.time() - last_check
        return elapsed >= SESSION_TIMEOUT

    def update_timestamp(self, processor_name, valid=True):
        """Update last check timestamp and validity"""
        if processor_name not in self.state:
            self.state[processor_name] = {}

        self.state[processor_name]['last_check'] = time.time()
        self.state[processor_name]['enabled'] = valid
        self.state[processor_name]['last_validation'] = datetime.now().isoformat()
        self._save_state()

        logger.info(f"Updated {processor_name} session state: valid={valid}")

    def is_enabled(self, processor_name):
        """Check if processor is enabled"""
        return self.state.get(processor_name, {}).get('enabled', True)

    def disable(self, processor_name, reason="Session expired"):
        """Disable a processor"""
        if processor_name not in self.state:
            self.state[processor_name] = {}

        self.state[processor_name]['enabled'] = False
        self.state[processor_name]['disabled_reason'] = reason
        self.state[processor_name]['disabled_at'] = datetime.now().isoformat()
        self._save_state()

        logger.error(f"Disabled {processor_name}: {reason}")

    def get_disabled_processors(self):
        """Get list of disabled processors with reasons"""
        disabled = []
        for name, state in self.state.items():
            if not state.get('enabled', True):
                disabled.append({
                    'name': name,
                    'reason': state.get('disabled_reason', 'Unknown'),
                    'disabled_at': state.get('disabled_at', 'Unknown')
                })
        return disabled

    def reset_all(self):
        """Reset all processors to enabled (called on flathunt.py restart)"""
        for name in self.state:
            self.state[name]['enabled'] = True
            # Keep last_check to avoid immediate validation
        self._save_state()
        logger.info("Reset all processors to enabled")

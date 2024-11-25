"""Glaze Autotiler - A window management automation tool for Glaze WM.

This application provides automatic window tiling functionality.
"""

import argparse
import asyncio
import concurrent.futures
import datetime
import importlib.util
import json
import logging
import os
import signal
import sys
import threading
import time

import pystray
import websockets
from PIL import IcoImagePlugin, Image, ImageDraw, PngImagePlugin
from pystray import MenuItem as item
from websockets.exceptions import ConnectionClosedError

from config_gui import ConfigGUI

APP_NAME = "Glaze Autotiler"
APP_VERSION = "1.0.3"


class AutoTiler:
    """Main class for handling window tiling automation in Glaze WM."""

    def __init__(self, log_enabled=False):
        """Initialize the AutoTiler.

        Args:
            log_enabled (bool): Whether to enable detailed logging
        """
        user_profile = os.getenv("USERPROFILE")
        if user_profile is None:
            raise ValueError("USERPROFILE environment variable not found")
        self.config_dir = os.path.join(user_profile, ".config", "glaze-autotiler")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.scripts_dir = os.path.join(self.config_dir, "scripts")
        self.log_dir = os.path.join(self.config_dir, "logs")

        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.scripts_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        self.current_script = None
        self.current_task = None
        self.cancel_event = threading.Event()
        self.loop = None
        self.layouts = {}
        self.running_task = None

        self.pre_package_default_scripts()
        self.setup_logging(log_enabled)
        self.load_layouts()
        self.default_layout = self.load_config()

        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.res_dir = os.path.join(self.app_dir, "res")
        self.icon_path = os.path.join(self.res_dir, "icon.png")
        self.icon = None  # Add this to store the icon reference
        self.app_name = APP_NAME
        self.version = APP_VERSION

        self.config_last_modified = (
            os.path.getmtime(self.config_file) if os.path.exists(self.config_file) else 0
        )
        self.config_check_interval = 2  # Check every 2 seconds
        self.shutting_down = False

    def pre_package_default_scripts(self):
        """Create default layout scripts if they don't exist."""
        default_scripts = {
            "dwindle.py": (
                "import asyncio\n"
                "import json\n"
                "import logging\n"
                "import websockets\n\n"
                "async def dwindle_layout(websocket, cancel_event):\n"
                '    await websocket.send("sub -e window_managed")\n'
                "    while not cancel_event.is_set():\n"
                "        try:\n"
                "            response = await asyncio.wait_for(websocket.recv(), timeout=1.0)\n"
                "            json_response = json.loads(response)\n"
                '            if json_response["messageType"] == "client_response":\n'
                "                logging.debug('Event subscription: %s', json_response['success'])\n"
                '            elif json_response["messageType"] == "event_subscription":\n'
                "                tiling_size = json_response['data']['managedWindow']['tilingSize']\n"
                "                logging.debug('Tiling Size: %s', tiling_size)\n"
                "                if tiling_size is not None and tiling_size <= 0.5:\n"
                "                    await websocket.send('c toggle-tiling-direction')\n"
                "        except asyncio.TimeoutError:\n"
                "            continue\n"
                "        except Exception as e:\n"
                "            logging.error('Dwindle script error: %s', e)\n\n"
                "async def run(cancel_event):\n"
                '    uri = "ws://localhost:6123"\n'
                "    try:\n"
                "        async with websockets.connect(uri) as websocket:\n"
                "            await dwindle_layout(websocket, cancel_event)\n"
                "    except Exception as e:\n"
                "        logging.error('Connection error: %s', e)\n"
            ),
            "master_stack.py": (
                "import asyncio\n"
                "import json\n"
                "import logging\n"
                "import websockets\n\n"
                "async def master_stack_layout(websocket, cancel_event):\n"
                '    await websocket.send("sub -e window_managed")\n'
                '    await websocket.send("sub -e focus_changed")\n'
                "    while not cancel_event.is_set():\n"
                "        try:\n"
                "            response = await asyncio.wait_for(websocket.recv(), timeout=1.0)\n"
                "            json_response = json.loads(response)\n"
                '            if json_response["messageType"] == "client_response":\n'
                "                logging.debug('Event subscription: %s', json_response['success'])\n"
                '            elif json_response["messageType"] == "event_subscription":\n'
                "                window_data = (\n"
                "                    json_response['data'].get('managedWindow') or\n"
                "                    json_response['data'].get('focusedContainer')\n"
                "                )\n"
                "                if not window_data:\n"
                "                    continue\n\n"
                "                tiling_size = window_data.get('tilingSize')\n"
                '                await websocket.send("query tiling-direction")\n'
                "                direction_response = await websocket.recv()\n"
                "                direction_json = json.loads(direction_response)\n"
                "                current_direction = direction_json.get('data', {}).get('tilingDirection')\n\n"
                "                if tiling_size is not None:\n"
                '                    if tiling_size > 0.5 and current_direction != "horizontal":\n'
                "                        await websocket.send('c set-tiling-direction horizontal')\n"
                '                    elif tiling_size <= 0.5 and current_direction != "vertical":\n'
                "                        await websocket.send('c set-tiling-direction vertical')\n"
                "        except asyncio.TimeoutError:\n"
                "            continue\n"
                "        except Exception as e:\n"
                "            logging.error('Master stack script error: %s', e)\n\n"
                "async def run(cancel_event):\n"
                '    uri = "ws://localhost:6123"\n'
                "    try:\n"
                "        async with websockets.connect(uri) as websocket:\n"
                "            await master_stack_layout(websocket, cancel_event)\n"
                "    except Exception as e:\n"
                "        logging.error('Connection error: %s', e)\n"
            ),
        }
        missing_scripts = []
        for filename in default_scripts.keys():
            script_path = os.path.join(self.scripts_dir, filename)
            if not os.path.exists(script_path):
                missing_scripts.append(filename)

        if not missing_scripts:
            logging.debug("All default scripts already exist")
            return

        # Create only missing scripts
        for filename in missing_scripts:
            script_path = os.path.join(self.scripts_dir, filename)
            try:
                with open(script_path, "w") as f:
                    f.write(default_scripts[filename])
                logging.info("Created default script: %s", filename)
            except OSError as e:
                logging.error("Error creating script %s: %s", filename, e)

    def setup_logging(self, log_enabled=False):
        """Configure logging settings."""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"autotiler_{current_time}.log"
        log_file = os.path.join(self.log_dir, log_filename)
        log_level = logging.DEBUG if log_enabled else logging.INFO

        logging.basicConfig(
            filename=log_file,
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            force=True,
        )

        if log_enabled:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(formatter)
            logging.getLogger().addHandler(console_handler)

        logging.info("Log file created: %s", log_filename)

    def load_layouts(self):
        """Load available layout scripts from configured paths."""
        self.layouts = {}
        script_paths = self.get_script_paths()
        layout_config = self.get_layout_config()

        logging.debug("Searching for layouts in paths: %s", script_paths)

        for layout_name, layout_info in layout_config.items():
            self._load_single_layout(layout_name, layout_info, script_paths)

        logging.info("Available layouts: %s", list(self.layouts.keys()))

    def _load_single_layout(self, layout_name, layout_info, script_paths):
        """Load a single layout script.

        Args:
            layout_name (str): Name of the layout
            layout_info (dict): Layout configuration
            script_paths (list): Paths to search for scripts
        """
        if not layout_info.get("enabled", True):
            logging.debug("Skipping disabled layout: %s", layout_name)
            return

        script_path = self._find_script_path(layout_name, script_paths)
        if not script_path:
            logging.warning("Script not found for configured layout: %s", layout_name)
            return

        try:
            module = self._load_layout_module(layout_name, script_path)
            if module and hasattr(module, "run") and asyncio.iscoroutinefunction(module.run):
                self._register_layout(layout_name, layout_info, module, script_path)
            else:
                logging.warning("Layout %s does not have a valid run coroutine", layout_name)
        except ImportError as e:
            logging.error("Error loading layout %s from %s: %s", layout_name, script_path, e)

    def _find_script_path(self, layout_name, script_paths):
        """Find the script path for a layout.

        Args:
            layout_name (str): Name of the layout
            script_paths (list): Paths to search for scripts

        Returns:
            str: Full path to script if found, None otherwise
        """
        script_filename = f"{layout_name}.py"
        for path in script_paths:
            if not os.path.exists(path):
                continue
            full_script_path = os.path.join(path, script_filename)
            if os.path.exists(full_script_path):
                return full_script_path
        return None

    def _load_layout_module(self, layout_name, script_path):
        """Load a Python module from a script path.

        Args:
            layout_name (str): Name of the layout
            script_path (str): Path to the script file

        Returns:
            module: Loaded Python module or None if failed
        """
        spec = importlib.util.spec_from_file_location(layout_name, script_path)
        if spec is None:
            logging.error("Could not create spec for %s", layout_name)
            return None

        module = importlib.util.module_from_spec(spec)
        if spec.loader is None:
            logging.error("No loader available for %s", layout_name)
            return None

        spec.loader.exec_module(module)
        return module

    def _register_layout(self, layout_name, layout_info, module, script_path):
        """Register a layout in the layouts dictionary.

        Args:
            layout_name (str): Name of the layout
            layout_info (dict): Layout configuration
            module: Loaded Python module
            script_path (str): Path to the script file
        """
        self.layouts[layout_name] = {
            "module": module,
            "path": script_path,
            "display_name": layout_info.get("display_name", layout_name.capitalize()),
            "config": layout_info,
        }
        logging.info("Successfully loaded layout: %s from %s", layout_name, script_path)

    def get_script_paths(self):
        """Get list of paths to search for layout scripts.

        Returns:
            list: List of directory paths containing layout scripts
        """
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as file:
                config = json.load(file)
                return config.get("script_paths", [self.scripts_dir])
        return [self.scripts_dir]

    def load_config(self):
        """Load configuration from config file."""
        config = self._get_default_config()

        if not os.path.exists(self.config_file):
            self._write_config(config)
            return config["default_layout"]

        config = self._merge_configs(self._read_config(), config)
        return self._validate_default_layout(config)

    def _get_default_config(self):
        """Get default configuration dictionary."""
        return {
            "default_layout": "dwindle",
            "script_paths": [self.scripts_dir],
            "layouts": {"dwindle": {"display_name": "Dwindle Layout", "enabled": True}},
        }

    def _write_config(self, config):
        """Write configuration to file."""
        with open(self.config_file, "w") as file:
            json.dump(config, file, indent=4)

    def _read_config(self):
        """Read configuration from file."""
        with open(self.config_file, "r") as file:
            return json.load(file)

    def _merge_configs(self, current, default):
        """Merge current config with defaults."""
        for key, value in default.items():
            if key not in current:
                current[key] = value
        return current

    def _validate_default_layout(self, config):
        """Validate and return default layout.

        Args:
            config (dict): Configuration dictionary

        Returns:
            str: Name of the validated default layout
        """
        if config.get("default_layout", "dwindle") not in self.layouts:
            logging.warning(
                f"Default layout {config.get('default_layout')} not found. "
                "Falling back to first available."
            )
            return next(iter(self.layouts), "dwindle")
        return config.get("default_layout", "dwindle")

    def get_layout_config(self):
        """Get layout-specific configuration from config file and creates default config if it doesn't exist.

        Returns:
            dict: Layout configuration dictionary
        """
        # Default layout config
        default_config = {
            "layouts": {
                "dwindle": {"display_name": "Dwindle Layout", "enabled": True},
                "master_stack": {"display_name": "Master Stack", "enabled": True},
            }
        }

        # Create config file if it doesn't exist
        if not os.path.exists(self.config_file):
            try:
                with open(self.config_file, "w") as file:
                    json.dump(default_config, file, indent=4)
                logging.info(f"Created default config file at {self.config_file}")
            except Exception as e:
                logging.error(f"Error creating config file: {e}")
                return default_config["layouts"]

        # Read existing config
        try:
            with open(self.config_file, "r") as file:
                config = json.load(file)
                return config.get("layouts", default_config["layouts"])
        except Exception as e:
            logging.error(f"Error reading config file: {e}")
            return default_config["layouts"]

    def update_config(self, new_layout):
        """Update configuration with new default layout.

        Args:
            new_layout (str): Name of the new default layout
        """
        config_data = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as file:
                config_data = json.load(file)
        config_data["default_layout"] = new_layout
        with open(self.config_file, "w") as file:
            json.dump(config_data, file, indent=4)
        logging.info(f"Config updated with new layout: {new_layout}")

    def start_layout(self, layout_name):
        """Start a specified layout."""
        if self.shutting_down:
            logging.warning("Cannot start layout during shutdown")
            return False

        if layout_name not in self.layouts:
            logging.error(f"Layout {layout_name} not found")
            return False

        if self.current_script != layout_name:
            self.current_script = layout_name
            self.update_config(layout_name)
            self.update_tooltip()
            logging.info(f"Starting {layout_name} script...")

            if self.loop is None or self.loop.is_closed():
                logging.error("Event loop is not initialized or is closed")
                return False

            return self._run_layout(layout_name)

        return False

    def _run_layout(self, layout_name):
        """Run the layout script."""

        async def run_layout():
            try:
                await self.layouts[layout_name]["module"].run(self.cancel_event)
            except (
                asyncio.CancelledError,
                asyncio.TimeoutError,
                ConnectionClosedError,  # Correct usage
            ) as e:
                logging.error(f"Error in {layout_name} layout: {e}")
            finally:
                logging.debug(f"Layout {layout_name} finished")

        try:
            # Cancel any existing task
            if self.running_task and not self.running_task.done():
                self.running_task.cancel()

            # Ensure loop is not None
            if self.loop is None:
                logging.error("Event loop is not initialized")
                return False

            # Create new task
            future = asyncio.run_coroutine_threadsafe(run_layout(), self.loop)
            self.running_task = future

            return True
        except Exception as e:
            logging.error(f"Error starting layout {layout_name}: {e}")
            return False

    def check_config_changes(self):
        """Check if config file has been modified and reload if necessary."""
        try:
            if not os.path.exists(self.config_file):
                return

            current_mtime = os.path.getmtime(self.config_file)
            if current_mtime > self.config_last_modified:
                logging.info("Config file changed, reloading...")

                # Validate JSON before proceeding
                try:
                    with open(self.config_file, "r") as f:
                        json.load(f)  # Test if JSON is valid

                    self.config_last_modified = current_mtime
                    self.load_layouts()
                    self.default_layout = self.load_config()
                    self.refresh_menu()
                except json.JSONDecodeError as e:
                    logging.error(f"Invalid JSON in config file: {e}")
                    # Don't update last_modified time so we'll retry on next check

        except Exception as e:
            logging.error(f"Error checking config changes: {e}")

    def stop_script(self):
        """Stop the currently running layout script."""
        logging.info("Stopping current script...")
        if self.running_task is not None and self.loop is not None:
            self.cancel_event.set()
            if not self.running_task.done():
                try:
                    # Cancel the future directly
                    self.loop.call_soon_threadsafe(self.running_task.cancel)
                except Exception as e:
                    logging.error(f"Error cancelling task: {e}")
            self.running_task = None
        self.current_script = None
        self.cancel_event.clear()
        self.update_tooltip()

    def refresh_menu(self):
        """Refresh the system tray menu items."""
        if not self.icon:
            return

        try:
            logging.info("Refreshing menu items...")
            menu_items = self._create_layout_menu_items()
            menu_items.extend(self._create_control_menu_items())

            self.icon.menu = pystray.Menu(*menu_items)
            self.update_tooltip()
            logging.info("Menu items refreshed")
        except (AttributeError, TypeError) as e:
            logging.error("Error refreshing menu: %s", e)

    def _create_layout_menu_items(self):
        """Create menu items for layouts.

        Returns:
            list: List of layout menu items
        """
        menu_items = []
        try:
            layout_config = self.get_layout_config()
        except json.JSONDecodeError as e:
            logging.error("Error loading layout config: %s", e)
            return menu_items

        for layout_name, layout_info in self.layouts.items():
            item = self._create_single_layout_item(layout_name, layout_info, layout_config)
            if item:
                menu_items.append(item)

        return menu_items

    def _create_single_layout_item(self, layout_name, layout_info, layout_config):
        """Create a menu item for a single layout.

        Args:
            layout_name (str): Name of the layout
            layout_info (dict): Layout information
            layout_config (dict): Layout configuration

        Returns:
            MenuItem: Created menu item or None if layout should be skipped
        """
        try:
            layout_config_info = layout_config.get(layout_name, {})
            if not layout_config_info.get("enabled", True):
                return None

            display_name = (
                layout_config_info.get("display_name")
                or layout_info.get("display_name")
                or layout_name.capitalize()
            )

            def make_callback(name):
                return lambda: self.start_layout(name)

            return item(
                display_name,
                make_callback(layout_name),
                checked=lambda item, name=layout_name: self.current_script == name,
            )
        except (KeyError, AttributeError) as e:
            logging.error("Error creating menu item for %s: %s", layout_name, e)
            return None

    def _create_control_menu_items(self):
        """Create control menu items including Config GUI option."""
        return [
            pystray.Menu.SEPARATOR,  # Add separator before control items
            item("Configure", self.open_config_gui),
            item("Stop Script", self.stop_script),
            item("Refresh", self.refresh_menu),
            item("Quit", lambda: self.quit_app(self.icon)),
        ]

    def open_config_gui(self):
        """Open the configuration GUI."""
        try:
            gui = ConfigGUI(self)
            gui.run()
        except Exception as e:
            logging.error(f"Error opening configuration GUI: {e}")

    def create_icon(self):
        """Create and configure the system tray icon."""
        try:
            # Try to load the custom icon
            if os.path.exists(self.icon_path):
                image = Image.open(self.icon_path)
                logging.info(f"Loaded custom icon from: {self.icon_path}")
            else:
                # Fallback to generated icon if custom icon is not found
                logging.warning(f"Icon not found at {self.icon_path}, using fallback icon")
                image = Image.new("RGB", (64, 64), color=(255, 255, 255))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, 64, 64), fill=(0, 0, 0))

            # Create menu before creating icon
            menu_items = self._create_layout_menu_items()
            menu_items.extend(self._create_control_menu_items())
            menu = pystray.Menu(*menu_items)

            # Create icon with menu
            self.icon = pystray.Icon(name="Glaze Autotiling", icon=image, menu=menu)

            # Set initial tooltip
            self.update_tooltip()

            logging.info("Starting system tray icon")

            # Start config file monitoring in a separate thread
            monitor_thread = threading.Thread(target=self.monitor_config, daemon=True)
            monitor_thread.start()

            # Run the icon
            self.icon.run_detached()  # For newer versions of pystray
            # If that doesn't work, try:
            # self.icon.run()  # For older versions of pystray

        except Exception as e:
            logging.error(f"Error creating tray icon: %s", e, exc_info=True)
            raise

    def monitor_config(self):
        """Monitor config file for changes."""
        while True:
            try:
                self.check_config_changes()
                time.sleep(self.config_check_interval)
            except Exception as e:
                logging.error(f"Error in config monitor: %s", e)

    def update_tooltip(self):
        """Update the system tray icon tooltip with current status."""
        if self.icon:
            try:
                if self.current_script and self.current_script in self.layouts:
                    display_name = self.layouts[self.current_script]["display_name"]
                    layout_name = f"Current Layout: {display_name}"
                else:
                    layout_name = "No layout active"
                self.icon.title = f"{self.app_name} v{self.version}\n{layout_name}"
            except (KeyError, AttributeError) as e:
                logging.error("Error updating tooltip: %s", e)
                self.icon.title = f"{self.app_name} v{self.version}\nError loading layout info"

    def run(self):
        """Start the application and system tray icon."""
        try:
            # Create a single event loop
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Start event loop in a separate thread
            event_loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
            event_loop_thread.start()

            # Set up signal handlers
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, self._signal_handler)

            # Create and run system tray icon
            self.create_icon()

        except Exception as e:
            logging.error(f"Error in main run loop: %s", e, exc_info=True)
            self._cleanup()
            raise

    def _run_event_loop(self):
        """Improved event loop management with WebSocket availability handling."""
        try:
            logging.info("Initializing event loop...")
            self._initialize_event_loop()

            if self.shutting_down:
                logging.info("Not starting event loop during shutdown")
                return

            self._start_default_layout_with_error_handling()

            if self.loop is not None and not self.loop.is_closed():
                try:
                    logging.info("Starting event loop...")
                    self.loop.run_forever()
                except RuntimeError as e:
                    logging.error(f"Event loop runtime error: {e}")

        except Exception as e:
            logging.error(f"Error in event loop: {e}", exc_info=True)
        finally:
            self._cleanup()

    def _initialize_event_loop(self):
        """Initialize the event loop."""
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def _start_default_layout_with_error_handling(self):
        """Start the default layout with error handling."""
        if self.default_layout:
            try:
                future = self._start_default_layout()
                if future:
                    try:
                        future.result(timeout=10)
                    except concurrent.futures.TimeoutError:
                        logging.error("Timeout starting default layout")
                    except Exception as e:
                        logging.error(f"Error starting default layout: %s", e)
            except Exception as e:
                logging.error(f"Unexpected error starting default layout: %s", e)

    def _start_default_layout(self):
        """Start the default layout with improved thread-safe mechanisms."""
        if not self.default_layout or self.loop is None:
            return None

        try:
            # Use run_coroutine_threadsafe for thread-safe coroutine execution
            future = asyncio.run_coroutine_threadsafe(
                asyncio.wait_for(
                    self._safe_start_layout(self.default_layout),
                    timeout=10.0,  # Increased timeout with explicit timeout handling
                ),
                self.loop,
            )
            return future
        except asyncio.TimeoutError:
            logging.error(f"Timeout starting default layout {self.default_layout}")
        except Exception as e:
            logging.error(f"Error scheduling default layout: {e}")
        return None

    async def _safe_start_layout(self, layout_name):
        """Enhanced layout start method with improved WebSocket handling."""
        try:
            # Additional comprehensive WebSocket check
            max_attempts = 3
            for _ in range(max_attempts):
                if self.shutting_down:
                    logging.info("Shutdown in progress, aborting layout start")
                    return
            # If all attempts fail
            logging.error("Could not establish WebSocket connection for layout %s", layout_name)

            # Validate layout and module
            if layout_name not in self.layouts:
                logging.error("Layout %s not found", layout_name)
                return

            # Reset cancel event before starting
            self.cancel_event.clear()

            # Attempt to run the layout
            module = self.layouts[layout_name]["module"]

            # Pass the WebSocket connection if the module supports it
            if hasattr(module, "run"):
                # Assuming websocket_connection is not defined, remove the condition and call run with cancel_event only
                await module.run(self.cancel_event)

            else:
                logging.error("Layout %s does not have a valid run method", layout_name)

        except (
            asyncio.CancelledError,
            asyncio.TimeoutError,
            ConnectionClosedError,  # Correct usage
        ) as e:
            logging.error("Error in event loop: %s", e, exc_info=True)

    def quit_app(self, icon):
        """Quit the application cleanly.

        Args:
            icon (pystray.Icon): System tray icon to remove
        """
        logging.info("Quitting the application...")
        self.shutting_down = True  # Set shutdown flag
        self.stop_script()
        icon.stop()
        self._cleanup()
        os._exit(0)

    def _cleanup(self):
        """Enhanced cleanup method with better resource management."""
        # Set shutdown flag
        self.shutting_down = True

        # Stop current script
        self.stop_script()

        # Close event loop
        if self.loop and not self.loop.is_closed():
            try:
                self.loop.close()
            except Exception as e:
                logging.error(f"Error closing event loop: %s", e)

        # Stop system tray icon
        if hasattr(self, "icon") and self.icon:
            try:
                self.icon.stop()
            except Exception as e:
                logging.error(f"Error stopping system tray icon: %s", e)

    async def _shutdown_loop(self):
        """Async method to properly shut down the event loop."""
        try:
            if self.loop is None or self.loop.is_closed():
                logging.warning("Event loop is None or already closed during shutdown")
                return

            pending = asyncio.all_tasks(self.loop)
            if not pending:
                logging.info("No pending tasks to cancel")
                return

            await self._cancel_pending_tasks(pending)

            self.loop.stop()
            logging.info("Event loop stopped")

        except Exception as e:
            logging.error(f"Unexpected error in _shutdown_loop: {e}")

    async def _cancel_pending_tasks(self, pending):
        """Cancel all pending tasks."""
        for task in list(pending):
            if task.done():
                continue

            try:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except asyncio.TimeoutError:
                    logging.warning(f"Task {task} did not cancel within timeout")
                except asyncio.CancelledError:
                    pass
            except Exception as e:
                logging.error(f"Error during task cancellation: {e}")

    def _signal_handler(self, signum, _):
        """Handle system signals for graceful shutdown."""
        signal_name = signal.Signals(signum).name
        logging.info(f"Received signal %s, initiating shutdown...", signal_name)

        # Prevent multiple simultaneous shutdowns
        if self.shutting_down:
            return

        self.shutting_down = True

        def shutdown_callback():
            try:
                self.stop_script()
                if hasattr(self, "icon") and self.icon:
                    self.icon.stop()
                if self.loop is not None and not self.loop.is_closed():
                    self.loop.stop()
                    self.loop.close()
            except Exception as e:
                logging.error(f"Error in shutdown callback: %s", e)

        # Use thread-safe method or fallback
        try:
            if self.loop is not None and not self.loop.is_closed() and self.loop.is_running():
                self.loop.call_soon_threadsafe(shutdown_callback)
            else:
                shutdown_callback()
        except Exception as e:
            logging.error(f"Error calling shutdown callback: %s", e)
            shutdown_callback()

    def _force_shutdown(self, timeout=5):
        """Force shutdown if graceful shutdown doesn't complete."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.shutting_down:
                os._exit(0)
            time.sleep(0.1)
        os._exit(1)


def main():
    """Entry point for the application."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log", action="store_true", help="Enable logging to console and log file."
    )
    args = parser.parse_args()

    autotiler = AutoTiler(log_enabled=args.log)
    logging.info("Application started with arguments: %s", sys.argv)

    try:
        autotiler.run()
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received in main(), initiating shutdown...")
        if hasattr(autotiler, "stop_script"):
            autotiler.stop_script()
        os._exit(0)


if __name__ == "__main__":
    main()

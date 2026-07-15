"""Glaze Autotiler - A window management automation tool for Glaze WM.

This application provides automatic window tiling functionality.
"""

import argparse
import asyncio
import datetime
import gc
import importlib.util
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import sys
import threading
import time
import traceback

# For CPU monitoring - will be imported conditionally if available

import pystray
from PIL import Image, ImageDraw, PngImagePlugin, IcoImagePlugin
from pystray import MenuItem as item

APP_NAME = "Glaze Autotiler"
APP_VERSION = "1.0.3"


class AutoTiler:
    """Main class for handling window tiling automation in Glaze WM."""

    def __init__(self, log_enabled=False, monitor_cpu=False):
        """Initialize the AutoTiler."""
        # Use HOME for Linux/Mac compatibility along with USERPROFILE for Windows
        user_profile = os.getenv("USERPROFILE") or os.getenv("HOME")
        if user_profile is None:
            raise ValueError("Neither USERPROFILE nor HOME environment variable found")
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
        self.config_monitor_thread = None
        self.cpu_monitor_thread = None
        self.cpu_monitor_running = False
        self.high_cpu_detected = False
        self.psutil_available = False
        self.monitor_cpu = monitor_cpu

        # Check if psutil is available
        try:
            import psutil
            self.psutil_available = True
        except ImportError:
            self.psutil_available = False

        # Pre-emptive garbage collection to start with a clean slate
        gc.collect()

        self.pre_package_default_scripts()
        self.setup_logging(log_enabled)
        self.load_layouts()
        self.default_layout = self.load_config()

        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.res_dir = os.path.join(self.app_dir, "res")
        self.icon_path = os.path.join(self.res_dir, "icon.png")
        self.icon = None
        self.app_name = APP_NAME
        self.version = APP_VERSION

        self.config_last_modified = (
            os.path.getmtime(self.config_file) if os.path.exists(self.config_file) else 0
        )
        self.config_check_interval = 5  # Increased from 2 to 5 seconds

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
                "                logging.debug(f\"Event subscription: {json_response['success']}\")\n"
                '            elif json_response["messageType"] == "event_subscription":\n'
                "                # Check if managedWindow exists in the data\n"
                "                if 'managedWindow' in json_response['data']:\n"
                "                    tiling_size = json_response['data']['managedWindow']['tilingSize']\n"
                '                    logging.debug(f"Tiling Size: {tiling_size}")\n'
                "                    if tiling_size is not None and tiling_size <= 0.5:\n"
                "                        await websocket.send('c toggle-tiling-direction')\n"
                "        except asyncio.TimeoutError:\n"
                "            # Just continue on timeout\n"
                "            continue\n"
                "        except asyncio.CancelledError:\n"
                "            break\n"
                "        except Exception as e:\n"
                '            logging.error(f"Dwindle script error: {e}")\n'
                "            # Sleep to prevent CPU spinning on repeated errors\n"
                "            await asyncio.sleep(0.5)\n\n"
                "async def run(cancel_event):\n"
                '    uri = "ws://localhost:6123"\n'
                "    reconnect_delay = 2\n"
                "    while not cancel_event.is_set():\n"
                "        try:\n"
                "            async with websockets.connect(uri) as websocket:\n"
                "                await dwindle_layout(websocket, cancel_event)\n"
                "            # If we get here, connection closed normally\n"
                "            if not cancel_event.is_set():\n"
                "                logging.warning('Connection closed, reconnecting...')\n"
                "        except Exception as e:\n"
                '            logging.error(f"Connection error: {e}")\n'
                "            if not cancel_event.is_set():\n"
                "                # Sleep to prevent CPU spinning on repeated connection errors\n"
                "                logging.info(f'Reconnecting in {reconnect_delay} seconds...')\n"
                "                await asyncio.sleep(reconnect_delay)\n"
                "                # Increase reconnect delay up to 10 seconds\n"
                "                reconnect_delay = min(10, reconnect_delay * 1.5)\n"
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
                "            # No timeout needed, recv() will wait for messages\n"
                "            response = await websocket.recv()\n"
                "            json_response = json.loads(response)\n"
                '            if json_response["messageType"] == "client_response":\n'
                "                logging.debug(f\"Event subscription: {json_response['success']}\")\n"
                '            elif json_response["messageType"] == "event_subscription":\n'
                "                window_data = (\n"
                "                    json_response['data'].get('managedWindow') or\n"
                "                    json_response['data'].get('focusedContainer')\n"
                "                )\n"
                "                if not window_data:\n"
                "                    continue\n\n"
                "                tiling_size = window_data.get('tilingSize')\n"
                "                if tiling_size is not None:\n"
                "                    # Query only when we have a valid tiling_size to reduce traffic\n"
                '                    await websocket.send("query tiling-direction")\n'
                "                    direction_response = await websocket.recv()\n"
                "                    direction_json = json.loads(direction_response)\n"
                "                    current_direction = direction_json.get('data', {}).get('tilingDirection')\n\n"
                '                    if tiling_size > 0.5 and current_direction != "horizontal":\n'
                "                        await websocket.send('c set-tiling-direction horizontal')\n"
                '                    elif tiling_size <= 0.5 and current_direction != "vertical":\n'
                "                        await websocket.send('c set-tiling-direction vertical')\n"
                "        except asyncio.CancelledError:\n"
                "            break\n"
                "        except Exception as e:\n"
                '            logging.error(f"Master stack script error: {e}")\n'
                "            # Sleep to prevent CPU spinning on repeated errors\n"
                "            await asyncio.sleep(0.5)\n\n"
                "async def run(cancel_event):\n"
                '    uri = "ws://localhost:6123"\n'
                "    reconnect_delay = 2\n"
                "    while not cancel_event.is_set():\n"
                "        try:\n"
                "            async with websockets.connect(uri) as websocket:\n"
                "                await master_stack_layout(websocket, cancel_event)\n"
                "        except Exception as e:\n"
                '            logging.error(f"Connection error: {e}")\n'
                "            # Sleep to prevent CPU spinning on repeated connection errors\n"
                "            await asyncio.sleep(reconnect_delay)\n"
                "            # Increase reconnect delay up to 30 seconds\n"
                "            reconnect_delay = min(30, reconnect_delay * 1.5)\n"
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
        log_level = logging.DEBUG if log_enabled else logging.INFO

        # Create a logger
        logger = logging.getLogger()
        logger.setLevel(log_level)

        if log_enabled:
            # Create console handler and set level to debug
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

            current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_filename = f"autotiler_{current_time}.log"
            log_file = os.path.join(self.log_dir, log_filename)

            file_handler = RotatingFileHandler(
                log_file, maxBytes=10*1024*1024, backupCount=5
            )
            file_handler.setLevel(log_level)
            file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

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
        """Load a single layout script."""
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
        """Find the script path for a layout."""
        script_filename = f"{layout_name}.py"
        for path in script_paths:
            if not os.path.exists(path):
                continue
            full_script_path = os.path.join(path, script_filename)
            if os.path.exists(full_script_path):
                return full_script_path
        return None

    def _load_layout_module(self, layout_name, script_path):
        """Load a Python module from a script path."""
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
        """Register a layout in the layouts dictionary."""
        self.layouts[layout_name] = {
            "module": module,
            "path": script_path,
            "display_name": layout_info.get("display_name", layout_name.capitalize()),
            "config": layout_info,
        }
        logging.info("Successfully loaded layout: %s from %s", layout_name, script_path)

    def get_script_paths(self):
        """Get list of paths to search for layout scripts."""
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
        """Validate and return default layout."""
        if config.get("default_layout", "dwindle") not in self.layouts:
            logging.warning(
                f"Default layout {config.get('default_layout')} not found. "
                "Falling back to first available."
            )
            return next(iter(self.layouts), "dwindle")
        return config.get("default_layout", "dwindle")

    def get_layout_config(self):
        """Get layout-specific configuration from config file and creates default config if it doesn't exist."""
        default_config = {
            "layouts": {
                "dwindle": {"display_name": "Dwindle Layout", "enabled": True},
                "master_stack": {"display_name": "Master Stack", "enabled": True},
            }
        }

        if not os.path.exists(self.config_file):
            try:
                with open(self.config_file, "w") as file:
                    json.dump(default_config, file, indent=4)
                logging.info(f"Created default config file at {self.config_file}")
            except Exception as e:
                logging.error(f"Error creating config file: {e}")
                return default_config["layouts"]

        try:
            with open(self.config_file, "r") as file:
                config = json.load(file)
                return config.get("layouts", default_config["layouts"])
        except Exception as e:
            logging.error(f"Error reading config file: {e}")
            return default_config["layouts"]

    def update_config(self, new_layout):
        """Update configuration with new default layout."""
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
        if layout_name not in self.layouts:
            logging.error(f"Layout {layout_name} not found")
            return False

        if self.current_script != layout_name:
            self.stop_script()
            self.current_script = layout_name
            self.update_config(layout_name)
            self.update_tooltip()
            logging.info(f"Starting {layout_name} script...")

            if self.loop is None:
                logging.error("Event loop is not initialized")
                return False

            async def run_layout():
                try:
                    # Set a timeout for the layout to prevent infinite loops or hangs
                    await asyncio.wait_for(
                        self.layouts[layout_name]["module"].run(self.cancel_event),
                        timeout=None  # No timeout, but we can handle cancellation
                    )
                except asyncio.CancelledError:
                    logging.info(f"Layout {layout_name} was cancelled")
                except Exception as e:
                    logging.error(f"Error in {layout_name} layout: {e}")
                    # Add a sleep to prevent CPU spinning on repeated errors
                    await asyncio.sleep(1)
                finally:
                    logging.debug(f"Layout {layout_name} finished")

            try:
                # Cancel any previous task first to ensure clean start
                if self.running_task and not self.running_task.done():
                    self.running_task.cancel()

                self.running_task = asyncio.run_coroutine_threadsafe(run_layout(), self.loop)
            except Exception as e:
                logging.error(f"Error starting layout {layout_name}: {e}")
                self.current_script = None  # Reset current script on failure
                return False

            return True
        return False

    def check_config_changes(self):
        """Check if config file has been modified and reload if necessary."""
        try:
            if not os.path.exists(self.config_file):
                return

            current_mtime = os.path.getmtime(self.config_file)
            if current_mtime > self.config_last_modified:
                logging.info("Config file changed, reloading...")

                try:
                    with open(self.config_file, "r") as f:
                        json.load(f)

                    self.config_last_modified = current_mtime
                    self.load_layouts()
                    self.default_layout = self.load_config()
                    self.refresh_menu()
                except json.JSONDecodeError as e:
                    logging.error(f"Invalid JSON in config file: {e}")

        except Exception as e:
            logging.error(f"Error checking config changes: {e}")

    def stop_script(self):
        """Stop the currently running layout script."""
        logging.info("Stopping current script...")
        if self.running_task is not None and self.loop is not None:
            # Signal the script to stop
            self.cancel_event.set()

            # Give a short grace period for tasks to clean up
            time.sleep(0.1)

            # Force cancel if still running
            if not self.running_task.done():
                try:
                    self.loop.call_soon_threadsafe(self.running_task.cancel)
                    # Wait briefly for the cancellation to take effect
                    start_time = time.time()
                    while not self.running_task.done() and time.time() - start_time < 1.0:
                        time.sleep(0.1)

                    if not self.running_task.done():
                        logging.warning("Task didn't cancel properly, may cause resource leaks")
                        # Get a traceback for debugging
                        if logging.getLogger().level <= logging.DEBUG:
                            for thread in threading.enumerate():
                                logging.debug(f"Active thread: {thread.name}")
                except Exception as e:
                    logging.error(f"Error cancelling task: {e}")
                    logging.debug(f"Cancellation error details: {traceback.format_exc()}")

            self.running_task = None

        self.current_script = None
        self.cancel_event.clear()
        self.update_tooltip()
        # Force garbage collection to clean up resources
        gc.collect()

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
        """Create menu items for layouts."""
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
        """Create a menu item for a single layout."""
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
            """Create control menu items (Stop, Refresh, Quit)."""
            items = [
                item("Stop Script", self.stop_script),
                item("Refresh", self.refresh_menu),
            ]

            # Add CPU usage info if available
            if self.psutil_available:
                try:
                    import psutil
                    cpu_percent = psutil.Process(os.getpid()).cpu_percent(interval=0.1)
                    items.append(item(f"CPU: {cpu_percent:.1f}%", lambda: None, enabled=False))
                except:
                    pass

            # Always add quit at the end
            items.append(item("Quit", lambda: self.quit_app(self.icon)))

            return items

    def create_icon(self):
        """Create and configure the system tray icon."""
        try:
            # Try to load the custom icon - use with statement to ensure file is closed properly
            if os.path.exists(self.icon_path):
                with Image.open(self.icon_path) as img:
                    # Create a copy to ensure the file handle is released
                    image = img.copy()
                logging.info(f"Loaded custom icon from: {self.icon_path}")
            else:
                # Fallback to generated icon if custom icon is not found
                logging.warning(f"Icon not found at {self.icon_path}, using fallback icon")
                image = Image.new("RGB", (64, 64), color=(255, 255, 255))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, 64, 64), fill=(0, 0, 0))
                del draw  # Explicitly release the drawing context

            # Set a smaller icon size to reduce memory usage
            if max(image.size) > 64:
                image.thumbnail((64, 64), Image.Resampling.BICUBIC)

            icon = pystray.Icon("Glaze Autotiling")
            self.icon = icon

            # Set initial tooltip
            self.update_tooltip()

            # Create initial menu
            self.refresh_menu()

            # Force garbage collection before starting the icon
            gc.collect()

            icon.icon = image
            logging.info("Starting system tray icon")

            # We don't need to start a new monitor thread here, we already start one in run()
            # This prevents duplicate monitoring threads which can cause high CPU usage

            icon.run()
        except Exception as e:
            logging.error(f"Error creating tray icon: {e}")
            # Clean up in case of error
            if hasattr(self, 'icon') and self.icon:
                try:
                    self.icon.stop()
                except:
                    pass
                self.icon = None

    def monitor_config(self):
        """Monitor config file for changes."""
        last_check_time = time.time()

        # Log that monitoring has started
        print(f"Config monitor started, checking every {self.config_check_interval}s", file=sys.stderr)
        logging.info(f"Config monitor started, checking every {self.config_check_interval}s")

        while True:
            try:
                # Only check if enough time has passed since last check
                current_time = time.time()
                if current_time - last_check_time >= self.config_check_interval:
                    self.check_config_changes()
                    last_check_time = current_time

                # Sleep for a shorter time but check less frequently
                # This makes the thread more responsive to shutdown
                time.sleep(1)
            except Exception as e:
                error_msg = f"Error in config monitor: {e}"
                print(error_msg, file=sys.stderr)
                logging.error(error_msg)
                # Sleep to prevent CPU spinning on repeated errors
                time.sleep(2)

    def quit_app(self, icon):
        """Quit the application cleanly."""
        logging.info("Quitting application...")
        self.stop_script()

        # Signal CPU monitoring to stop if running
        self.cpu_monitor_running = False
        if self.cpu_monitor_thread and self.cpu_monitor_thread.is_alive():
            self.cpu_monitor_thread.join(timeout=1.0)

        # Force garbage collection before exit
        gc.collect()

        icon.visible = False
        icon.stop()
        sys.exit(0)  # Use sys.exit instead of os._exit for cleaner shutdown

    def update_tooltip(self):
        """Update the system tray icon tooltip with current status."""
        if self.icon:
            try:
                # Build tooltip components
                tooltip_parts = [f"{self.app_name} v{self.version}"]

                if self.current_script and self.current_script in self.layouts:
                    display_name = self.layouts[self.current_script]["display_name"]
                    tooltip_parts.append(f"Current Layout: {display_name}")
                else:
                    tooltip_parts.append("No layout active")

                # Add CPU usage info if monitoring is enabled and psutil is available
                if self.psutil_available and self.cpu_monitor_running:
                    try:
                        import psutil
                        cpu_percent = psutil.Process(os.getpid()).cpu_percent(interval=0.1)
                        tooltip_parts.append(f"CPU: {cpu_percent:.1f}%")

                        # Also log to console for easier debugging
                        logging.debug(f"Current CPU usage: {cpu_percent:.1f}%")

                        if self.high_cpu_detected:
                            tooltip_parts.append("⚠ HIGH CPU USAGE DETECTED ⚠")
                            logging.warning("High CPU usage detected!")
                    except Exception as e:
                        # Log the error but continue
                        logging.debug(f"Error getting CPU info: {e}")
                        pass

                # Set the tooltip with all parts
                self.icon.title = "\n".join(tooltip_parts)
            except (KeyError, AttributeError) as e:
                error_msg = f"Error updating tooltip: {e}"
                print(error_msg, file=sys.stderr)
                logging.error(error_msg)
                self.icon.title = f"{self.app_name} v{self.version}\nError loading layout info"

    def run_event_loop(self):
        """Run the asyncio event loop in a separate thread."""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Add a periodic CPU usage check task (optional)
            async def check_cpu_usage():
                while True:
                    try:
                        # Check if psutil is available and use it if so
                        if self.psutil_available:
                            import psutil
                            process = psutil.Process(os.getpid())
                            cpu_percent = process.cpu_percent(interval=1)
                            if cpu_percent > 20:  # Arbitrary threshold
                                logging.warning(f"High CPU usage detected: {cpu_percent}%")
                                self.high_cpu_detected = True

                                # Get top consuming functions if possible
                                # This requires the tracemalloc module to be enabled
                                try:
                                    import tracemalloc
                                    if tracemalloc.is_tracing():
                                        snapshot = tracemalloc.take_snapshot()
                                        top_stats = snapshot.statistics('lineno')
                                        logging.warning("Top 5 memory allocations:")
                                        for stat in top_stats[:5]:
                                            logging.warning(f"{stat}")
                                except (ImportError, AttributeError):
                                    logging.debug("tracemalloc not available for memory profiling")
                            else:
                                self.high_cpu_detected = False
                        else:
                            # Skip CPU monitoring if psutil is not available
                            pass
                    except Exception as e:
                        logging.error(f"Error in CPU usage check: {e}")
                    await asyncio.sleep(10)  # Check every 10 seconds

            # Uncomment if psutil is added to requirements
            # self.loop.create_task(check_cpu_usage())

            # Start the default layout
            self.start_layout(self.default_layout)

            # Run the event loop with improved error handling
            self.loop.run_forever()
        except Exception as e:
            logging.error(f"Error in event loop: {e}")
        finally:
            if self.loop and not self.loop.is_closed():
                # Cancel all running tasks
                try:
                    for task in asyncio.all_tasks(self.loop):
                        task.cancel()

                    # Run the event loop until all tasks are canceled
                    self.loop.run_until_complete(asyncio.sleep(0.1))
                except Exception as e:
                    logging.error(f"Error cleaning up tasks: {e}")
                finally:
                    self.loop.close()
                    gc.collect()  # Force garbage collection after closing loop

    def _update_tooltip_periodically(self):
        """Update the tooltip periodically to show current CPU usage."""
        logging.info("Tooltip updater started")
        print("Tooltip updater thread started", file=sys.stderr)

        while self.cpu_monitor_running:
            try:
                self.update_tooltip()
                time.sleep(2)  # Update every 2 seconds
            except Exception as e:
                error_msg = f"Error updating tooltip: {e}"
                print(error_msg, file=sys.stderr)
                logging.error(error_msg)
                time.sleep(5)  # Longer pause on error

    def monitor_cpu_usage(self):
        """Monitor CPU usage and log if it exceeds thresholds.

        This function requires psutil to be installed.
        """
        if not self.cpu_monitor_running or not self.psutil_available:
            print("CPU monitoring disabled (psutil not available or not requested)", file=sys.stderr)
            return

        try:
            import psutil
            process = psutil.Process(os.getpid())
            print(f"CPU monitoring started for PID {os.getpid()}", file=sys.stderr)

            # Variables to track consecutive high CPU readings
            high_cpu_count = 0
            consecutive_threshold = 3  # Number of consecutive readings to confirm high CPU

            # Print directly to stderr for visibility
            print(f"CPU monitoring started for PID {os.getpid()}", file=sys.stderr)
            logging.info(f"CPU monitoring started for PID {os.getpid()}")

            while self.cpu_monitor_running:
                try:
                    # Get CPU usage as a percentage - shorter interval for more accuracy
                    cpu_percent = process.cpu_percent(interval=1)

                    # Output every reading in debug mode
                    logging.debug(f"Current CPU usage: {cpu_percent:.1f}%")

                    # Update the high CPU detected flag based on consecutive readings
                    if cpu_percent > 25:
                        high_cpu_count += 1
                        if high_cpu_count >= consecutive_threshold:
                            if not self.high_cpu_detected:
                                self.high_cpu_detected = True
                                self.update_tooltip()  # Update the tooltip to show high CPU
                                # Print to stderr to make sure it's visible
                                print(f"⚠ HIGH CPU DETECTED: {cpu_percent:.1f}%", file=sys.stderr)
                    else:
                        high_cpu_count = 0
                        if self.high_cpu_detected:
                            self.high_cpu_detected = False
                            self.update_tooltip()  # Update tooltip to remove high CPU warning
                            print("CPU usage returned to normal", file=sys.stderr)

                    # Log based on severity
                    if cpu_percent > 50:
                        logging.warning(f"Critical CPU usage: {cpu_percent}%")
                        print(f"CRITICAL CPU USAGE: {cpu_percent:.1f}%", file=sys.stderr)

                        # Get thread info for debugging
                        active_threads = threading.enumerate()
                        logging.warning(f"Active threads: {len(active_threads)}")
                        for thread in active_threads:
                            logging.warning(f"Thread: {thread.name}, Daemon: {thread.daemon}")

                        # Suggest garbage collection
                        gc.collect()
                    elif cpu_percent > 25:
                        logging.info(f"High CPU usage: {cpu_percent}%")

                    # Adaptive sleep - sleep longer when CPU usage is lower
                    # This reduces the monitoring overhead when things are running smoothly
                    sleep_time = 5 if cpu_percent < 15 else 2
                    time.sleep(sleep_time)
                except Exception as e:
                    logging.error(f"Error in CPU monitoring: {e}")
                    print(f"Error in CPU monitoring: {e}", file=sys.stderr)
                    time.sleep(10)  # Longer pause on error
        except Exception as e:
            logging.error(f"CPU monitoring failed to start: {e}")
            print(f"CPU monitoring failed to start: {e}", file=sys.stderr)

    def run(self):
        """Start the application and system tray icon."""
        # Start event loop in a daemon thread
        event_loop_thread = threading.Thread(target=self.run_event_loop, daemon=True, name="EventLoopThread")
        event_loop_thread.start()

        # Log that we're starting
        logging.info("Starting event loop thread...")

        # Start config monitor in a daemon thread with a name for easier debugging
        self.config_monitor_thread = threading.Thread(
            target=self.monitor_config, daemon=True, name="ConfigMonitorThread"
        )
        self.config_monitor_thread.start()
        logging.info("Starting config monitor thread...")

        # Start CPU monitor in a daemon thread if psutil is available and monitoring is requested
        if self.psutil_available and self.monitor_cpu:
            print("Starting CPU monitoring...", file=sys.stderr)
            self.cpu_monitor_running = True
            self.cpu_monitor_thread = threading.Thread(
                target=self.monitor_cpu_usage,
                daemon=True,
                name="CPUMonitorThread"
            )
            self.cpu_monitor_thread.start()
            logging.info("CPU monitoring started (psutil available)")

            # Update tooltip more frequently when CPU monitoring is active
            threading.Thread(
                target=self._update_tooltip_periodically,
                daemon=True,
                name="TooltipUpdateThread"
            ).start()
        else:
            self.cpu_monitor_running = False
            if self.monitor_cpu and not self.psutil_available:
                msg = "CPU monitoring requested but psutil not available. Install with: pip install psutil"
                print(msg, file=sys.stderr)
                logging.warning(msg)
            else:
                logging.info("CPU monitoring disabled")

        # Force garbage collection before creating the system tray icon
        gc.collect()

        # Create system tray icon in main thread
        self.create_icon()


def main():
    """Entry point for the application."""
    # Print directly to stderr to ensure visibility in console
    print("Glaze Autotiler starting...", file=sys.stderr)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l", "--log", action="store_true", help="Enable logging to console and log file."
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug mode with additional logging."
    )
    parser.add_argument(
        "--gc-debug", action="store_true", help="Enable garbage collection debug output."
    )
    parser.add_argument(
        "-m", "--monitor-cpu", action="store_true", help="Enable CPU usage monitoring (requires psutil)."
    )
    args = parser.parse_args()

    # Set garbage collection thresholds to be more aggressive
    gc.set_threshold(700, 10, 5)  # Default is (700, 10, 10)

    if args.gc_debug:
        gc.set_debug(gc.DEBUG_STATS | gc.DEBUG_LEAK)

    # Check if psutil is available for CPU monitoring
    psutil_available = False
    try:
        import psutil
        psutil_available = True
        logging.info("psutil available for CPU monitoring")
    except ImportError:
        logging.info("psutil not available - CPU monitoring will be disabled")

    # Enable memory profiling with tracemalloc if monitoring CPU
    if args.monitor_cpu and psutil_available:
        # Try to enable tracemalloc for memory profiling
        try:
            import tracemalloc
            tracemalloc.start()
            logging.info("Memory profiling enabled with tracemalloc")
        except ImportError:
            logging.warning("tracemalloc module not available for memory profiling")
    elif args.monitor_cpu and not psutil_available:
        logging.warning("CPU monitoring requested but psutil is not installed. Install with: pip install psutil")

    # Force stderr to be unbuffered before anything else
    try:
        sys.stderr.reconfigure(write_through=True)
    except (AttributeError, ValueError):
        # Python < 3.7 doesn't have reconfigure
        import os
        try:
            sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 0)  # 0 = unbuffered
        except ValueError:
            # In some environments, unbuffered mode might not be supported
            sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)  # 1 = line buffered

    # Set up basic console logging before creating AutoTiler
    log_enabled = args.log or args.debug
    log_level = logging.DEBUG if args.debug else (logging.INFO if log_enabled else logging.WARNING)

    # Configure root logger to ensure output appears
    handlers = [logging.StreamHandler(sys.stderr)]
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True
    )

    if args.debug:
        print("Debug mode enabled - verbose logging activated", file=sys.stderr)
        logging.debug("Debug mode enabled")
    elif log_enabled:
        print("Logging enabled", file=sys.stderr)

    autotiler = AutoTiler(log_enabled=log_enabled, monitor_cpu=args.monitor_cpu)
    logging.info("Application started with arguments: %s", sys.argv)
    print(f"Application started with arguments: {sys.argv}", file=sys.stderr)

    def signal_handler(_, __):  # Use underscores for unused arguments
        """Handle keyboard interrupt signal."""
        logging.info("KeyboardInterrupt received, shutting down...")
        if hasattr(autotiler, "stop_script"):
            autotiler.stop_script()
        # Force garbage collection before exit
        gc.collect()
        # Use a clean exit instead of os._exit
        # to allow for proper resource cleanup
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        autotiler.run()
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, shutting down...")
        if hasattr(autotiler, "stop_script"):
            autotiler.stop_script()
        # Force garbage collection before exit
        gc.collect()
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unhandled exception in main: {e}")
        gc.collect()
        sys.exit(1)


if __name__ == "__main__":
    # Ensure stderr output is flushed immediately
    try:
        sys.stderr.reconfigure(write_through=True)
        sys.stdout.reconfigure(write_through=True)
    except AttributeError:
        # Python < 3.7 doesn't have reconfigure
        import os
        try:
            sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 0)  # 0 = unbuffered
            sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)  # 0 = unbuffered
        except ValueError:
            # In some environments, unbuffered mode might not be supported
            sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)  # 1 = line buffered
            sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)  # 1 = line buffered

    # Print directly to ensure visibility in the executable
    print("Glaze Autotiler is launching...", file=sys.stderr)
    print("Output should appear in this console window", file=sys.stderr)

    try:
        main()
    except Exception as e:
        import traceback
        error_msg = f"FATAL ERROR: {e}"
        print(error_msg, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        input("Press Enter to exit...")  # Keep window open on error
        sys.exit(1)

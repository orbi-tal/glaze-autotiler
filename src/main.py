"""Glaze Autotiler - A window management automation tool for Glaze WM.

This application provides automatic window tiling functionality.
"""

import argparse
import asyncio
import datetime
import importlib.util
import json
import logging
import os
import sys
import threading

import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item

APP_NAME = "Glaze Autotiler"
APP_VERSION = "1.0.1"


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
                "                tiling_size = json_response['data']['managedWindow']['tilingSize']\n"
                '                logging.debug(f"Tiling Size: {tiling_size}")\n'
                "                if tiling_size is not None and tiling_size <= 0.5:\n"
                "                    await websocket.send('c toggle-tiling-direction')\n"
                "        except asyncio.TimeoutError:\n"
                "            continue\n"
                "        except Exception as e:\n"
                '            logging.error(f"Dwindle script error: {e}")\n\n'
                "async def run(cancel_event):\n"
                '    uri = "ws://localhost:6123"\n'
                "    try:\n"
                "        async with websockets.connect(uri) as websocket:\n"
                "            await dwindle_layout(websocket, cancel_event)\n"
                "    except Exception as e:\n"
                '        logging.error(f"Connection error: {e}")\n'
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
                "                logging.debug(f\"Event subscription: {json_response['success']}\")\n"
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
                '            logging.error(f"Master stack script error: {e}")\n\n'
                "async def run(cancel_event):\n"
                '    uri = "ws://localhost:6123"\n'
                "    try:\n"
                "        async with websockets.connect(uri) as websocket:\n"
                "            await master_stack_layout(websocket, cancel_event)\n"
                "    except Exception as e:\n"
                '        logging.error(f"Connection error: {e}")\n'
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
                logging.info(f"Created default script: {filename}")
            except Exception as e:
                logging.error(f"Error creating script {filename}: {e}")

    def setup_logging(self, log_enabled=False):
        """Configure logging settings.

        Args:
            log_enabled (bool): Whether to enable detailed logging
        """
        # Create log filename with current date-time
        current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"autotiler_{current_time}.log"
        log_file = os.path.join(self.log_dir, log_filename)
        log_level = logging.DEBUG if log_enabled else logging.INFO

        # Add datetime import at the top of the file
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

        logging.info(f"Log file created: {log_filename}")

    def load_layouts(self):
        """Load available layout scripts from configured paths.

        Searches for and loads Python scripts that implement tiling layouts.
        Each layout must have a run() coroutine function.
        """
        self.layouts = {}
        script_paths = self.get_script_paths()
        layout_config = self.get_layout_config()

        logging.debug(f"Searching for layouts in paths: {script_paths}")

        for path in script_paths:
            if not os.path.exists(path):
                logging.warning(f"Script path does not exist: {path}")
                continue

            files = os.listdir(path)
            logging.debug(f"Found files in {path}: {files}")

            for filename in files:
                if filename.endswith(".py"):
                    layout_name = os.path.splitext(filename)[0]
                    full_script_path = os.path.join(path, filename)

                    # Check if there's a custom configuration for this layout
                    custom_config = layout_config.get(layout_name, {})
                    display_name = custom_config.get("display_name", layout_name.capitalize())

                    try:
                        spec = importlib.util.spec_from_file_location(layout_name, full_script_path)
                        if spec is None:
                            logging.error(f"Could not create spec for {filename}")
                            continue

                        module = importlib.util.module_from_spec(spec)
                        if spec.loader is None:
                            logging.error(f"No loader available for {filename}")
                            continue

                        spec.loader.exec_module(module)

                        if hasattr(module, "run") and asyncio.iscoroutinefunction(module.run):
                            self.layouts[layout_name] = {
                                "module": module,
                                "path": full_script_path,
                                "display_name": display_name,
                                "config": custom_config,
                            }
                            logging.info(
                                f"Successfully loaded layout: {layout_name} from {full_script_path}"
                            )
                        else:
                            logging.warning(
                                f"Layout {layout_name} does not have a valid run coroutine"
                            )
                    except Exception as e:
                        logging.error(
                            f"Error loading layout {layout_name} from {full_script_path}: {e}"
                        )

        logging.info(f"Available layouts: {list(self.layouts.keys())}")

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
        """Start a specified layout.

        Args:
            layout_name (str): Name of the layout to start

        Returns:
            bool: True if layout started successfully, False otherwise
        """
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
                    await self.layouts[layout_name]["module"].run(self.cancel_event)
                except asyncio.CancelledError:
                    logging.info(f"Layout {layout_name} was cancelled")
                except Exception as e:
                    logging.error(f"Error in {layout_name} layout: {e}")
                finally:
                    logging.debug(f"Layout {layout_name} finished")

            try:
                self.running_task = asyncio.run_coroutine_threadsafe(run_layout(), self.loop)
            except Exception as e:
                logging.error(f"Error starting layout {layout_name}: {e}")
                return False

            return True
        return False

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

            icon = pystray.Icon("Glaze Autotiling")
            self.icon = icon

            # Set initial tooltip
            self.update_tooltip()

            def make_callback(layout_name):
                return lambda: self.start_layout(layout_name)

            menu_items = []
            for layout_name, layout_info in self.layouts.items():
                menu_items.append(
                    item(
                        layout_info["display_name"],
                        make_callback(layout_name),
                        checked=lambda item, name=layout_name: self.current_script == name,
                    )
                )

            menu_items.extend(
                [
                    item("Stop Script", lambda: self.stop_script()),
                    item("Quit", lambda: self.quit_app(icon)),
                ]
            )

            icon.menu = pystray.Menu(*menu_items)
            icon.icon = image
            logging.info(f"Starting system tray icon with {len(menu_items)} menu items")
            icon.run()
        except Exception as e:
            logging.error(f"Error creating tray icon: {e}")

    def quit_app(self, icon):
        """Quit the application cleanly.

        Args:
            icon (pystray.Icon): System tray icon to remove
        """
        logging.info("Quitting the application...")
        self.stop_script()
        icon.stop()
        os._exit(0)

    def update_tooltip(self):
        """Update the system tray icon tooltip with current status."""
        if self.icon:
            layout_name = (
                f"Current Layout: {self.layouts[self.current_script]['display_name']}"
                if self.current_script
                else "No layout active"
            )
            self.icon.title = f"{self.app_name} v{self.version}\n{layout_name}"

    def run_event_loop(self):
        """Run the asyncio event loop in a separate thread."""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.start_layout(self.default_layout)
            self.loop.run_forever()
        except Exception as e:
            logging.error(f"Error in event loop: {e}")
        finally:
            if self.loop:
                self.loop.close()

    def run(self):
        """Start the application and system tray icon."""
        event_loop_thread = threading.Thread(target=self.run_event_loop, daemon=True)
        event_loop_thread.start()
        self.create_icon()


def main():
    """Entry point for the application."""
    import signal

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log", action="store_true", help="Enable logging to console and log file."
    )
    args = parser.parse_args()

    autotiler = AutoTiler(log_enabled=args.log)
    logging.info(f"Application started with arguments: {sys.argv}")

    def signal_handler(sig, frame):
        logging.info("KeyboardInterrupt received, shutting down...")
        if hasattr(autotiler, "stop_script"):
            autotiler.stop_script()
        # Force exit since the tray icon might prevent clean shutdown
        os._exit(0)

    # Register the signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    try:
        autotiler.run()
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, shutting down...")
        if hasattr(autotiler, "stop_script"):
            autotiler.stop_script()
        # Force exit since the tray icon might prevent clean shutdown
        os._exit(0)


if __name__ == "__main__":
    main()

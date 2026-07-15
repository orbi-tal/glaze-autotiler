"""Glaze Autotiler: tray-based window layout manager driving GlazeWM via websockets."""

import argparse
import asyncio
import datetime
import gc
import importlib.util
import io
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

from tray_win32 import MenuItem, TrayIcon


def _reconfigure_unbuffered(stream):
    if isinstance(stream, io.TextIOWrapper):
        try:
            stream.reconfigure(write_through=True)
        except ValueError:
            try:
                stream = os.fdopen(stream.fileno(), "w", 0)
            except ValueError:
                stream = os.fdopen(stream.fileno(), "w", 1)
    return stream


APP_NAME = "Glaze Autotiler"
APP_VERSION = "1.0.4"
LAYOUT_SCRIPT_VERSION = 1


class AutoTiler:
    def __init__(self, log_enabled=False, monitor_cpu=False):
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
        self.current_async_task = None
        self.cancel_event = threading.Event()
        self.loop = None
        self.layouts = {}
        self.running_task = None
        self.config_monitor_thread = None
        self.cpu_monitor_thread = None
        self.cpu_monitor_running = False
        self.high_cpu_detected = False
        self.last_cpu_percent = None
        self.psutil_available = PSUTIL_AVAILABLE
        self.monitor_cpu = monitor_cpu

        gc.collect()

        self.setup_logging(log_enabled)
        self.pre_package_default_scripts()
        self.load_layouts()
        self.default_layout = self.load_config()

        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.res_dir = os.path.join(self.app_dir, "res")
        self.icon_path = os.path.join(self.res_dir, "icon.ico")
        self.icon = None
        self.app_name = APP_NAME
        self.version = APP_VERSION

        self.config_last_modified = (
            os.path.getmtime(self.config_file) if os.path.exists(self.config_file) else 0
        )
        self.config_check_interval = 5

    def pre_package_default_scripts(self):
        default_scripts = {
            "dwindle.py": (
                "import asyncio\n"
                "import json\n"
                "import logging\n"
                "import websockets\n\n"
                "async def dwindle_layout(websocket, cancel_event):\n"
                '    await websocket.send("sub -e window_managed")\n'
                '    await websocket.send("sub -e focus_changed")\n'
                '    await websocket.send("sub -e focused_container_moved")\n'
                "    last_direction = None\n"
                "    while not cancel_event.is_set():\n"
                "        try:\n"
                "            response = await asyncio.wait_for(websocket.recv(), timeout=1.0)\n"
                "            json_response = json.loads(response)\n\n"
                '            if json_response["messageType"] == "client_response":\n'
                "                logging.debug(f\"Event subscription: {json_response['success']}\")\n"
                '            elif json_response["messageType"] == "event_subscription":\n'
                "                window_data = (\n"
                "                    json_response['data'].get('managedWindow') or\n"
                "                    json_response['data'].get('focusedContainer')\n"
                "                )\n"
                "                if not window_data:\n"
                "                    continue\n\n"
                "                width = window_data.get('width')\n"
                "                height = window_data.get('height')\n\n"
                "                if width is not None and height is not None and width != height:\n"
                "                    direction = 'horizontal' if width > height else 'vertical'\n"
                "                    if direction != last_direction:\n"
                "                        await websocket.send(f'c set-tiling-direction {direction}')\n"
                "                        last_direction = direction\n"
                "        except asyncio.TimeoutError:\n"
                "            continue\n"
                "        except asyncio.CancelledError:\n"
                "            break\n"
                "        except Exception as e:\n"
                '            logging.error(f"Dwindle script error: {e}")\n'
                "            if isinstance(e, websockets.exceptions.ConnectionClosed):\n"
                "                raise e\n"
                "            await asyncio.sleep(0.5)\n\n"
                "async def run(cancel_event):\n"
                '    uri = "ws://localhost:6123"\n'
                "    reconnect_delay = 2\n"
                "    while not cancel_event.is_set():\n"
                "        try:\n"
                "            async with websockets.connect(uri) as websocket:\n"
                "                await dwindle_layout(websocket, cancel_event)\n"
                "            if not cancel_event.is_set():\n"
                "                logging.warning('Connection closed, reconnecting...')\n"
                "                await asyncio.sleep(reconnect_delay)\n"
                "        except Exception as e:\n"
                '            logging.error(f"Connection error: {e}")\n'
                "            if not cancel_event.is_set():\n"
                "                logging.info(f'Reconnecting in {reconnect_delay} seconds...')\n"
                "                await asyncio.sleep(reconnect_delay)\n"
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
                '    await websocket.send("sub -e focused_container_moved")\n'
                "    last_direction = None\n"
                "    while not cancel_event.is_set():\n"
                "        try:\n"
                "            response = await asyncio.wait_for(websocket.recv(), timeout=1.0)\n"
                "            json_response = json.loads(response)\n\n"
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
                "                    direction = 'horizontal' if tiling_size > 0.5 else 'vertical'\n"
                "                    if direction != last_direction:\n"
                "                        await websocket.send(f'c set-tiling-direction {direction}')\n"
                "                        last_direction = direction\n"
                "        except asyncio.TimeoutError:\n"
                "            continue\n"
                "        except asyncio.CancelledError:\n"
                "            break\n"
                "        except Exception as e:\n"
                '            logging.error(f"Master stack script error: {e}")\n'
                "            if isinstance(e, websockets.exceptions.ConnectionClosed):\n"
                "                raise e\n"
                "            await asyncio.sleep(0.5)\n\n"
                "async def run(cancel_event):\n"
                '    uri = "ws://localhost:6123"\n'
                "    reconnect_delay = 2\n"
                "    while not cancel_event.is_set():\n"
                "        try:\n"
                "            async with websockets.connect(uri) as websocket:\n"
                "                await master_stack_layout(websocket, cancel_event)\n"
                "            if not cancel_event.is_set():\n"
                "                logging.warning('Connection closed, reconnecting...')\n"
                "                await asyncio.sleep(reconnect_delay)\n"
                "        except Exception as e:\n"
                '            logging.error(f"Connection error: {e}")\n'
                "            await asyncio.sleep(reconnect_delay)\n"
                "            reconnect_delay = min(30, reconnect_delay * 1.5)\n"
            ),
        }

        version_marker = f"# glaze-autotiler script version: {LAYOUT_SCRIPT_VERSION}\n"
        default_scripts = {
            filename: version_marker + content for filename, content in default_scripts.items()
        }

        for filename, script_content in default_scripts.items():
            script_path = os.path.join(self.scripts_dir, filename)
            self._write_default_script_if_needed(
                filename, script_path, script_content, version_marker
            )

        default_scripts.clear()
        gc.collect()

    def _is_script_outdated(self, filename, script_path, version_marker):
        """Return True if script_path is missing its current version marker."""
        if not os.path.exists(script_path):
            return False  # caller treats "missing" separately via os.path.exists
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                first_line = f.readline()
                return first_line != version_marker
        except OSError as e:
            logging.warning(
                "Could not read %s to check if it's outdated (%s); will attempt to rewrite it",
                filename,
                e,
            )
            return True

    def _write_script_with_retry(self, script_path, script_content, attempts=3):
        """Write script_content to script_path, verifying it, up to `attempts` times.

        Returns (written_ok, last_error).
        """
        last_error = None
        for attempt in range(attempts):
            try:
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(script_content)
                with open(script_path, "r", encoding="utf-8") as f:
                    if f.read() == script_content:
                        return True, None
                last_error = "content mismatch after write"
            except OSError as e:
                last_error = e
            if attempt < attempts - 1:
                time.sleep(0.3)
        return False, last_error

    def _write_default_script_if_needed(
        self, filename, script_path, script_content, version_marker
    ):
        exists = os.path.exists(script_path)
        outdated = exists and self._is_script_outdated(filename, script_path, version_marker)

        if exists and not outdated:
            return

        written_ok, last_error = self._write_script_with_retry(script_path, script_content)

        if written_ok:
            logging.info("Created or updated script: %s", filename)
        else:
            logging.error(
                "Failed to create or update script %s after 3 attempts: %s. "
                "The existing (possibly outdated) script on disk will be used instead.",
                filename,
                last_error,
            )

    def setup_logging(self, log_enabled=False):
        log_level = logging.DEBUG if log_enabled else logging.INFO
        logger = logging.getLogger()
        logger.setLevel(log_level)

        always_on_log_file = os.path.join(self.log_dir, "autotiler_errors.log")
        always_on_handler = None
        try:
            always_on_handler = RotatingFileHandler(
                always_on_log_file, maxBytes=2 * 1024 * 1024, backupCount=2
            )
            always_on_handler.setLevel(logging.WARNING)
            always_on_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            )
            logger.addHandler(always_on_handler)
        except OSError:
            pass

        if log_enabled:
            for handler in logger.handlers[:]:
                if handler is not always_on_handler:
                    logger.removeHandler(handler)

            if isinstance(sys.stdout, io.TextIOWrapper):
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(log_level)
                console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
                console_handler.setFormatter(console_formatter)
                logger.addHandler(console_handler)

            current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_filename = f"autotiler_{current_time}.log"
            log_file = os.path.join(self.log_dir, log_filename)

            file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
            file_handler.setLevel(log_level)
            file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

            logging.info("Log file created: %s", log_filename)

    def load_layouts(self):
        self.layouts = {}
        script_paths = self.get_script_paths()
        layout_config = self.get_layout_config()

        logging.debug("Searching for layouts in paths: %s", script_paths)

        for layout_name, layout_info in layout_config.items():
            self._load_single_layout(layout_name, layout_info, script_paths)

        logging.info("Available layouts: %s", list(self.layouts.keys()))

    def _load_single_layout(self, layout_name, layout_info, script_paths):
        if not layout_info.get("enabled", True):
            logging.debug("Skipping disabled layout: %s", layout_name)
            return

        script_path = self._find_script_path(layout_name, script_paths)
        if not script_path:
            logging.warning("Script not found for configured layout: %s", layout_name)
            return

        self._register_layout(layout_name, layout_info, None, script_path)

    def _find_script_path(self, layout_name, script_paths):
        script_filename = f"{layout_name}.py"
        for path in script_paths:
            if not os.path.exists(path):
                continue
            full_script_path = os.path.join(path, script_filename)
            if os.path.exists(full_script_path):
                return full_script_path
        return None

    def _load_layout_module(self, layout_name, script_path):
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
        self.layouts[layout_name] = {
            "module": module,
            "path": script_path,
            "display_name": layout_info.get("display_name", layout_name.capitalize()),
            "config": layout_info,
        }
        logging.info("Registered layout: %s (script: %s)", layout_name, script_path)

    def get_script_paths(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as file:
                config = json.load(file)
                return config.get("script_paths", [self.scripts_dir])
        return [self.scripts_dir]

    def load_config(self):
        config = self._get_default_config()

        if not os.path.exists(self.config_file):
            self._write_config(config)
            return config["default_layout"]

        config = self._merge_configs(self._read_config(), config)
        return self._validate_default_layout(config)

    def _get_default_config(self):
        return {
            "default_layout": "dwindle",
            "script_paths": [self.scripts_dir],
            "layouts": {"dwindle": {"display_name": "Dwindle Layout", "enabled": True}},
        }

    def _write_config(self, config):
        with open(self.config_file, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=4)
        try:
            self.config_last_modified = os.path.getmtime(self.config_file)
        except OSError:
            pass

    def _read_config(self):
        with open(self.config_file, "r", encoding="utf-8") as file:
            return json.load(file)

    def _merge_configs(self, current, default):
        for key, value in default.items():
            if key not in current:
                current[key] = value
        return current

    def _validate_default_layout(self, config):
        if config.get("default_layout", "dwindle") not in self.layouts:
            logging.warning(
                "Default layout %s not found. Falling back to first available.",
                config.get("default_layout"),
            )
            return next(iter(self.layouts), "dwindle")
        return config.get("default_layout", "dwindle")

    def get_layout_config(self):
        default_config = {
            "layouts": {
                "dwindle": {"display_name": "Dwindle Layout", "enabled": True},
                "master_stack": {"display_name": "Master Stack", "enabled": True},
            }
        }

        if not os.path.exists(self.config_file):
            try:
                with open(self.config_file, "w", encoding="utf-8") as file:
                    json.dump(default_config, file, indent=4)
                logging.info("Created default config file at %s", self.config_file)
                try:
                    self.config_last_modified = os.path.getmtime(self.config_file)
                except OSError:
                    pass
            except Exception as e:
                logging.error("Error creating config file: %s", e)
                return default_config["layouts"]

        try:
            with open(self.config_file, "r", encoding="utf-8") as file:
                config = json.load(file)
                return config.get("layouts", default_config["layouts"])
        except Exception as e:
            logging.error("Error reading config file: %s", e)
            return default_config["layouts"]

    def update_config(self, new_layout):
        config_data = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as file:
                config_data = json.load(file)
        config_data["default_layout"] = new_layout
        with open(self.config_file, "w", encoding="utf-8") as file:
            json.dump(config_data, file, indent=4)
        try:
            self.config_last_modified = os.path.getmtime(self.config_file)
        except OSError:
            pass
        logging.info("Config updated with new layout: %s", new_layout)

    def _ensure_layout_module_loaded(self, layout_name, entry):
        """Load and validate the layout's module if not already loaded.

        Returns True if entry["module"] is ready to use, False on failure
        (already logged).
        """
        if entry["module"] is not None:
            return True

        logging.info("Loading layout module: %s", layout_name)
        try:
            module = self._load_layout_module(layout_name, entry["path"])
        except ImportError as e:
            logging.error("Error loading layout %s from %s: %s", layout_name, entry["path"], e)
            return False

        if not module or not hasattr(module, "run") or not asyncio.iscoroutinefunction(module.run):
            logging.warning("Layout %s does not have a valid run coroutine", layout_name)
            return False

        entry["module"] = module
        return True

    def _schedule_layout_task(self, layout_name, loop):
        """Cancel any previous running task and schedule run_layout() on loop.

        Returns True on success, False on failure (already logged).
        """

        async def run_layout():
            self.current_async_task = asyncio.current_task()
            try:
                await asyncio.wait_for(
                    self.layouts[layout_name]["module"].run(self.cancel_event), timeout=None
                )
            except asyncio.CancelledError:
                logging.info("Layout %s was cancelled", layout_name)
            except Exception as e:
                logging.error("Error in %s layout: %s", layout_name, e)
                await asyncio.sleep(1)
            finally:
                logging.debug("Layout %s finished", layout_name)
                self.current_async_task = None

        try:
            if self.running_task and not self.running_task.done():
                self.running_task.cancel()
            self.running_task = asyncio.run_coroutine_threadsafe(run_layout(), loop)
        except Exception as e:
            logging.error("Error starting layout %s: %s", layout_name, e)
            self.current_script = None
            return False
        return True

    def start_layout(self, layout_name):
        if layout_name not in self.layouts:
            logging.error("Layout %s not found", layout_name)
            return False

        if self.current_script == layout_name:
            return False

        entry = self.layouts[layout_name]
        if not self._ensure_layout_module_loaded(layout_name, entry):
            return False

        self.stop_script()
        self.current_script = layout_name
        self.update_config(layout_name)
        self.update_tooltip()
        logging.info("Starting %s script...", layout_name)

        loop = self.loop
        if loop is None:
            logging.error("Event loop is not initialized")
            return False

        return self._schedule_layout_task(layout_name, loop)

    def check_config_changes(self):
        try:
            if not os.path.exists(self.config_file):
                return

            current_mtime = os.path.getmtime(self.config_file)
            if current_mtime > self.config_last_modified:
                logging.info("Config file changed, reloading...")

                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        json.load(f)

                    self.config_last_modified = current_mtime
                    self.load_layouts()
                    self.default_layout = self.load_config()
                    self.refresh_menu()
                except json.JSONDecodeError as e:
                    logging.error("Invalid JSON in config file: %s", e)

        except Exception as e:
            logging.error("Error checking config changes: %s", e)

    def stop_script(self):
        logging.info("Stopping current script...")
        if self.running_task is not None and self.loop is not None:
            self.cancel_event.set()

            if hasattr(self, "current_async_task") and self.current_async_task:
                try:
                    self.loop.call_soon_threadsafe(self.current_async_task.cancel)
                except Exception as e:
                    logging.error("Error cancelling asyncio task: %s", e)

            try:
                self.running_task.result(timeout=1.5)
            except Exception:
                pass

            self.running_task = None

        self.current_script = None
        self.cancel_event.clear()
        self.update_tooltip()
        gc.collect()

    def refresh_menu(self):
        if not self.icon:
            return
        logging.info("Refreshing menu items...")
        self.update_tooltip()
        logging.info("Menu items refreshed")

    def _build_menu_items(self):
        menu_items = self._create_layout_menu_items()
        menu_items.extend(self._create_control_menu_items())
        return menu_items

    def _create_layout_menu_items(self):
        menu_items = []
        try:
            layout_config = self.get_layout_config()
        except json.JSONDecodeError as e:
            logging.error("Error loading layout config: %s", e)
            return menu_items

        for layout_name, layout_info in self.layouts.items():
            menu_item = self._create_single_layout_item(layout_name, layout_info, layout_config)
            if menu_item:
                menu_items.append(menu_item)

        return menu_items

    def _create_single_layout_item(self, layout_name, layout_info, layout_config):
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

            return MenuItem(
                display_name,
                make_callback(layout_name),
                checked=lambda name=layout_name: self.current_script == name,
            )
        except (KeyError, AttributeError) as e:
            logging.error("Error creating menu item for %s: %s", layout_name, e)
            return None

    def _create_control_menu_items(self):
        items = [
            MenuItem("Stop Script", self.stop_script),
            MenuItem("Refresh", self.refresh_menu),
        ]

        if self.psutil_available:
            if self.last_cpu_percent is not None:
                items.append(MenuItem(f"CPU: {self.last_cpu_percent:.1f}%", None, enabled=False))
            elif not self.monitor_cpu:
                pass

        items.append(MenuItem("Quit", self.quit_app))
        return items

    def create_icon(self):
        try:
            if not os.path.exists(self.icon_path):
                logging.error("Icon not found at %s; cannot start tray icon", self.icon_path)
                return

            self.icon = TrayIcon("Glaze Autotiling", self.icon_path, self._build_menu_items)
            logging.info("Loaded custom icon from: %s", self.icon_path)
            gc.collect()
            logging.info("Starting system tray icon")
            self.icon.run()
        except Exception as e:
            logging.error("Error creating tray icon: %s", e)
            if hasattr(self, "icon") and self.icon:
                try:
                    self.icon.stop()
                except Exception:
                    pass
                self.icon = None

    def monitor_config(self):
        last_check_time = time.time()
        print(
            f"Config monitor started, checking every {self.config_check_interval}s",
            file=sys.stderr,
        )
        logging.info("Config monitor started, checking every %ss", self.config_check_interval)

        while True:
            try:
                current_time = time.time()
                if current_time - last_check_time >= self.config_check_interval:
                    self.check_config_changes()
                    last_check_time = current_time
                time.sleep(1)
            except Exception as e:
                error_msg = f"Error in config monitor: {e}"
                print(error_msg, file=sys.stderr)
                logging.error(error_msg)
                time.sleep(2)

    def quit_app(self):
        logging.info("Quitting application...")
        self.stop_script()
        self.cpu_monitor_running = False
        if self.cpu_monitor_thread and self.cpu_monitor_thread.is_alive():
            self.cpu_monitor_thread.join(timeout=1.0)
        gc.collect()

        if self.icon:
            self.icon.stop()
        else:
            sys.exit(0)

    def update_tooltip(self):
        if self.icon:
            try:
                tooltip_parts = [f"{self.app_name} v{self.version}"]

                if self.current_script and self.current_script in self.layouts:
                    display_name = self.layouts[self.current_script]["display_name"]
                    tooltip_parts.append(f"Current Layout: {display_name}")
                else:
                    tooltip_parts.append("No layout active")

                if self.psutil_available and self.cpu_monitor_running:
                    if self.last_cpu_percent is not None:
                        tooltip_parts.append(f"CPU: {self.last_cpu_percent:.1f}%")
                        if self.high_cpu_detected:
                            tooltip_parts.append("⚠ HIGH CPU USAGE DETECTED ⚠")
                            logging.warning("High CPU usage detected!")

                tooltip_text = "\n".join(tooltip_parts)[:127]
                self.icon.set_tooltip(tooltip_text)
            except (KeyError, AttributeError) as e:
                error_msg = f"Error updating tooltip: {e}"
                print(error_msg, file=sys.stderr)
                logging.error(error_msg)
                self.icon.set_tooltip(
                    f"{self.app_name} v{self.version}\nError loading layout info"
                )

    def run_event_loop(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.start_layout(self.default_layout)
            self.loop.run_forever()
        except Exception as e:
            logging.error("Error in event loop: %s", e)
        finally:
            if self.loop and not self.loop.is_closed():
                try:
                    for task in asyncio.all_tasks(self.loop):
                        task.cancel()
                    self.loop.run_until_complete(asyncio.sleep(0.1))
                except Exception as e:
                    logging.error("Error cleaning up tasks: %s", e)
                finally:
                    self.loop.close()
                    gc.collect()

    def _update_tooltip_periodically(self):
        logging.info("Tooltip updater started")
        print("Tooltip updater thread started", file=sys.stderr)

        while self.cpu_monitor_running:
            try:
                self.update_tooltip()
                time.sleep(2)
            except Exception as e:
                error_msg = f"Error updating tooltip: {e}"
                print(error_msg, file=sys.stderr)
                logging.error(error_msg)
                time.sleep(5)

    def _handle_high_cpu_transition(self, cpu_percent, high_cpu_count, consecutive_threshold):
        """Update high_cpu_detected state on a >25% sample; return updated high_cpu_count."""
        high_cpu_count += 1
        if high_cpu_count >= consecutive_threshold and not self.high_cpu_detected:
            self.high_cpu_detected = True
            self.update_tooltip()
            print(f"⚠ HIGH CPU DETECTED: {cpu_percent:.1f}%", file=sys.stderr)
        return high_cpu_count

    def _handle_normal_cpu_transition(self):
        """Clear high_cpu_detected state on a normal (<=25%) sample."""
        if self.high_cpu_detected:
            self.high_cpu_detected = False
            self.update_tooltip()
            print("CPU usage returned to normal", file=sys.stderr)

    def _log_cpu_severity(self, cpu_percent):
        if cpu_percent > 50:
            logging.warning("Critical CPU usage: %s%%", cpu_percent)
            print(f"CRITICAL CPU USAGE: {cpu_percent:.1f}%", file=sys.stderr)
            active_threads = threading.enumerate()
            logging.warning("Active threads: %s", len(active_threads))
            for thread in active_threads:
                logging.warning("Thread: %s, Daemon: %s", thread.name, thread.daemon)
            gc.collect()
        elif cpu_percent > 25:
            logging.info("High CPU usage: %s%%", cpu_percent)

    def _cpu_monitor_tick(self, process, high_cpu_count, consecutive_threshold):
        """Run one CPU-monitoring sample/sleep cycle; return updated high_cpu_count."""
        cpu_percent = process.cpu_percent(interval=1)
        self.last_cpu_percent = cpu_percent
        rss_mb = process.memory_info().rss / (1024 * 1024)

        logging.debug("Current CPU usage: %.1f%%", cpu_percent)
        logging.debug("Current memory usage (RSS): %.1f MB", rss_mb)

        if cpu_percent > 25:
            high_cpu_count = self._handle_high_cpu_transition(
                cpu_percent, high_cpu_count, consecutive_threshold
            )
        else:
            high_cpu_count = 0
            self._handle_normal_cpu_transition()

        self._log_cpu_severity(cpu_percent)

        sleep_time = 5 if cpu_percent < 15 else 2
        time.sleep(sleep_time)
        return high_cpu_count

    def monitor_cpu_usage(self):
        if not self.cpu_monitor_running or not self.psutil_available:
            print(
                "CPU monitoring disabled (psutil not available or not requested)", file=sys.stderr
            )
            return

        try:
            assert psutil is not None
            process = psutil.Process(os.getpid())
            high_cpu_count = 0
            consecutive_threshold = 3

            print(f"CPU monitoring started for PID {os.getpid()}", file=sys.stderr)
            logging.info("CPU monitoring started for PID %s", os.getpid())

            while self.cpu_monitor_running:
                try:
                    high_cpu_count = self._cpu_monitor_tick(
                        process, high_cpu_count, consecutive_threshold
                    )
                except Exception as e:
                    logging.error("Error in CPU monitoring: %s", e)
                    print(f"Error in CPU monitoring: {e}", file=sys.stderr)
                    time.sleep(10)
        except Exception as e:
            logging.error("CPU monitoring failed to start: %s", e)
            print(f"CPU monitoring failed to start: {e}", file=sys.stderr)

    def run(self):
        event_loop_thread = threading.Thread(
            target=self.run_event_loop, daemon=True, name="EventLoopThread"
        )
        event_loop_thread.start()
        logging.info("Starting event loop thread...")

        self.config_monitor_thread = threading.Thread(
            target=self.monitor_config, daemon=True, name="ConfigMonitorThread"
        )
        self.config_monitor_thread.start()
        logging.info("Starting config monitor thread...")

        if self.psutil_available and self.monitor_cpu:
            print("Starting CPU monitoring...", file=sys.stderr)
            self.cpu_monitor_running = True
            self.cpu_monitor_thread = threading.Thread(
                target=self.monitor_cpu_usage, daemon=True, name="CPUMonitorThread"
            )
            self.cpu_monitor_thread.start()
            logging.info("CPU monitoring started (psutil available)")

            threading.Thread(
                target=self._update_tooltip_periodically, daemon=True, name="TooltipUpdateThread"
            ).start()
        else:
            self.cpu_monitor_running = False
            if self.monitor_cpu and not self.psutil_available:
                msg = (
                    "CPU monitoring requested but psutil not available. "
                    "Install with: pip install psutil"
                )
                print(msg, file=sys.stderr)
                logging.warning(msg)
            else:
                logging.info("CPU monitoring disabled")

        gc.collect()
        self.create_icon()


def _build_arg_parser():
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
        "-m",
        "--monitor-cpu",
        action="store_true",
        help="Enable CPU usage monitoring (requires psutil).",
    )
    return parser


def _maybe_enable_gc_debug(args):
    if not args.gc_debug:
        return
    gc.set_debug(gc.DEBUG_STATS | gc.DEBUG_LEAK)
    try:
        import tracemalloc

        tracemalloc.start()
        logging.info("Memory profiling enabled with tracemalloc")
    except ImportError:
        logging.warning("tracemalloc module not available for memory profiling")


def _configure_logging(args):
    """Compute log_enabled/log_level, configure the root logger, and print status.

    Returns log_enabled.
    """
    log_enabled = args.log or args.debug
    log_level = logging.DEBUG if args.debug else (logging.INFO if log_enabled else logging.WARNING)

    handlers = [logging.StreamHandler(sys.stderr)]
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
        force=True,
    )

    if args.debug:
        print("Debug mode enabled - verbose logging activated", file=sys.stderr)
        logging.debug("Debug mode enabled")
    elif log_enabled:
        print("Logging enabled", file=sys.stderr)

    return log_enabled


def _run_autotiler(autotiler):
    """Install SIGINT handler and run autotiler.run(), handling shutdown/errors."""

    def signal_handler(_, __):
        logging.info("KeyboardInterrupt received, shutting down...")
        if hasattr(autotiler, "stop_script"):
            autotiler.stop_script()
        gc.collect()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        autotiler.run()
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, shutting down...")
        if hasattr(autotiler, "stop_script"):
            autotiler.stop_script()
        gc.collect()
        sys.exit(0)
    except Exception as e:
        logging.error("Unhandled exception in main: %s", e)
        gc.collect()
        sys.exit(1)


def main():
    print("Glaze Autotiler starting...", file=sys.stderr)

    args = _build_arg_parser().parse_args()

    gc.set_threshold(700, 10, 5)

    psutil_available = PSUTIL_AVAILABLE
    if psutil_available:
        logging.info("psutil available for CPU monitoring")
    else:
        logging.info("psutil not available - CPU monitoring will be disabled")

    _maybe_enable_gc_debug(args)

    sys.stderr = _reconfigure_unbuffered(sys.stderr)

    log_enabled = _configure_logging(args)

    autotiler = AutoTiler(log_enabled=log_enabled, monitor_cpu=args.monitor_cpu)
    logging.info("Application started with arguments: %s", sys.argv)
    print(f"Application started with arguments: {sys.argv}", file=sys.stderr)

    _run_autotiler(autotiler)


class _NullStream:
    def write(self, *args, **kwargs):
        pass

    def flush(self, *args, **kwargs):
        pass

    def fileno(self):
        raise OSError("no console attached")


def _setup_console_streams():
    """Reconfigure stdout/stderr for console output, or install null streams if no console.

    Returns has_console.
    """
    has_console = sys.stderr is not None

    if has_console:
        sys.stderr = _reconfigure_unbuffered(sys.stderr)
        sys.stdout = _reconfigure_unbuffered(sys.stdout)
        print("Glaze Autotiler is launching...", file=sys.stderr)
        print("Output should appear in this console window", file=sys.stderr)
    else:
        sys.stdout = _NullStream()
        sys.stderr = _NullStream()

    return has_console


def _write_crash_log(error_msg, tb_text):
    """Best-effort crash log write to ~/.config/glaze-autotiler/logs (no console case)."""
    try:
        logging.error(error_msg)
        logging.error(tb_text)
    except Exception:
        pass
    try:
        user_profile = os.getenv("USERPROFILE") or os.getenv("HOME")
        if user_profile:
            crash_dir = os.path.join(user_profile, ".config", "glaze-autotiler", "logs")
            os.makedirs(crash_dir, exist_ok=True)
            crash_file = os.path.join(crash_dir, "autotiler_crash.log")
            with open(crash_file, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat()} - {error_msg}\n{tb_text}\n")
    except Exception:
        pass


if __name__ == "__main__":
    HAS_CONSOLE = _setup_console_streams()

    try:
        main()
    except Exception as e:
        ERROR_MSG = f"FATAL ERROR: {e}"
        TB_TEXT = traceback.format_exc()

        if HAS_CONSOLE:
            print(ERROR_MSG, file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            input("Press Enter to exit...")
        else:
            _write_crash_log(ERROR_MSG, TB_TEXT)
        sys.exit(1)

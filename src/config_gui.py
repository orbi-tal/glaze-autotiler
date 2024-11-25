"""Glaze Autotiler's Configuration GUI.

This application provides a GUI to configure config.json.
"""

import json
import os
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Tuple

import customtkinter as ctk
from PIL import Image


class ConfigGUI:
    """Glaze Autotiler's Configuration GUI."""

    def __init__(self, autotiler):
        """Handles GUI for Configuration."""
        self.autotiler = autotiler
        self.window = ctk.CTk()
        self.window.title("Glaze Autotiler Configuration")
        self.window.geometry("800x600")

        # Load resource directory
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.res_dir = os.path.join(self.app_dir, "res")

        if os.name == "nt":  # Windows
            self.window.iconbitmap(os.path.join(self.res_dir, "icon.ico"))
        else:  # Other platforms
            self.window.iconphoto(True, tk.PhotoImage(file=os.path.join(self.res_dir, "icon.png")))

        # Initialize selected row and rows_data
        self.selected_row = None
        self.rows_data = []

        # Sort direction for columns
        self.sort_direction = {"script": False, "display": False, "status": False}

        # Load images
        self.load_images()

        # Load saved theme
        self.theme_file = os.path.join(self.autotiler.config_dir, "theme.json")
        self.load_theme()

        # Create main container
        self.main_container = ctk.CTkFrame(self.window, fg_color=("#ffffff", "#1a1b24"))
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Create theme switcher frame
        self.create_theme_switcher()

        # Create status message label
        self.status_label = ctk.CTkLabel(
            self.main_container, text="", font=ctk.CTkFont(family="Inter", weight="bold")
        )
        self.status_label.pack(side=tk.BOTTOM, anchor=tk.W, padx=10, pady=5)

        # Create table frame
        self.create_table_frame()

        # Create bottom section
        self.create_bottom_section()

        # Load and display data
        self.load_data()

    def load_images(self):
        """Load all required images with high DPI support."""

        def load_image(filename: str, size: Tuple[int, int] = (24, 24)):
            image_path = os.path.join(self.res_dir)

            filepath = os.path.join(image_path, filename)
            try:
                # Convert SVG filename to PNG if needed
                if filename.endswith(".svg"):
                    filename = filename.replace(".svg", ".png")
                    filepath = os.path.join(image_path, filename)

                img = Image.open(filepath)

                # Return the image with the specified size
                return ctk.CTkImage(light_image=img, dark_image=img, size=size)

            except Exception as e:
                print(f"Failed to load image {filename}: {e}")
                # Create a fallback colored square
                img = Image.new("RGBA", size, (128, 128, 128, 255))
                return ctk.CTkImage(light_image=img, dark_image=img, size=size)

        # Define sizes for different types of icons
        ICON_SIZE = (24, 24)
        SWITCH_SIZE = (70, 30)

        # Load all images with appropriate sizes
        self.images = {
            "light": load_image("light.png", ICON_SIZE),
            "dark": load_image("dark.png", ICON_SIZE),
            "plus": load_image("plus.png", ICON_SIZE),
            "minus": load_image("minus.png", ICON_SIZE),
            "switch_on": load_image("switch_on.png", SWITCH_SIZE),
            "switch_off": load_image("switch_off.png", SWITCH_SIZE),
            "switch_on_dark": load_image("switch_on_dark.png", SWITCH_SIZE),
            "switch_off_dark": load_image("switch_off_dark.png", SWITCH_SIZE),
            "icon": load_image("icon.png", ICON_SIZE),
        }

    def on_theme_changed(self, event):
        """Handle theme change event."""
        self.refresh_ui()

    def load_theme(self):
        """Load saved theme preference."""
        try:
            if os.path.exists(self.theme_file):
                with open(self.theme_file, "r") as f:
                    theme_data = json.load(f)
                    ctk.set_appearance_mode(theme_data.get("theme", "light"))
                return
            ctk.set_appearance_mode("light")
        except Exception as e:
            print(f"Error loading theme: {e}")
            ctk.set_appearance_mode("light")

    def save_theme(self):
        """Save current theme preference."""
        try:
            theme_data = {"theme": ctk.get_appearance_mode().lower()}
            with open(self.theme_file, "w") as f:
                json.dump(theme_data, f)
        except Exception as e:
            print(f"Error saving theme: {e}")

    def get_switch_image(self, status, theme=None):
        """Get the correct switch image based on status and theme."""
        if theme is None:
            theme = ctk.get_appearance_mode().lower()

        if status == "Enabled":
            return self.images["switch_on_dark" if theme == "dark" else "switch_on"]
        return self.images["switch_off_dark" if theme == "dark" else "switch_off"]

    def create_theme_switcher(self):
        """Create a dedicated frame for the theme switcher."""
        theme_container = ctk.CTkFrame(
            self.main_container, fg_color=("#ffffff", "#1a1b24"), height=50
        )
        theme_container.pack(fill=tk.X, padx=10, pady=(10, 0))

        # Make the frame maintain its height
        theme_container.pack_propagate(False)

        # Add icon on the left
        icon_label = ctk.CTkLabel(
            theme_container, image=self.images["icon"], text=""  # No text, just the icon
        )
        icon_label.pack(side=tk.LEFT, padx=10, pady=10)

        # Create the theme switcher button
        self.theme_button = ctk.CTkButton(
            theme_container,
            image=self.images["light" if ctk.get_appearance_mode().lower() == "dark" else "dark"],
            text="",
            width=30,
            height=30,
            command=self.toggle_theme,
            hover_color=("#ffffff", "#1a1b24"),
            fg_color="transparent",
        )
        self.theme_button.pack(side=tk.RIGHT, padx=10, pady=10)

    def create_table_frame(self):
        """Create table frame with headers and content."""
        outer_table_frame = ctk.CTkFrame(self.main_container, fg_color=("#f2f1fa", "#312e3f"))
        outer_table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Table header
        header_frame = ctk.CTkFrame(outer_table_frame, fg_color=("#f2f1fa", "#312e3f"))
        header_frame.pack(fill=tk.X, padx=5, pady=5)

        headers = [("Script Name", "script"), ("Display Name", "display"), ("Status", "status")]
        for i, (text, key) in enumerate(headers):
            header_frame.grid_columnconfigure(i, weight=1, uniform="col")
            btn = ctk.CTkButton(
                header_frame,
                text=text,
                command=lambda k=key: self.sort_table(k),
                fg_color=("#ffffff", "#1a1b24"),
                text_color=("#1a1b24", "#ffffff"),
                hover_color=("#f2f1fa", "#312e3f"),
                anchor="w",
                font=ctk.CTkFont(family="Inter", weight="bold"),
                width=240,
            )
            btn.grid(row=0, column=i, sticky="ew", padx=5)

        # Table content
        self.table_frame = ctk.CTkScrollableFrame(
            outer_table_frame, fg_color=("#f2f1fa", "#312e3f")
        )
        self.table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def display_table(self):
        """Display the table with current data."""
        for widget in self.table_frame.winfo_children():
            widget.destroy()

        for _i, row in enumerate(self.rows_data):
            row_frame = ctk.CTkFrame(
                self.table_frame, fg_color=("#f2f1fa", "#312e3f"), corner_radius=5
            )
            row_frame.pack(fill=tk.X, padx=5, pady=2)

            # Bind events
            for widget in [row_frame] + list(row_frame.winfo_children()):
                widget.bind("<Enter>", lambda e, rf=row_frame: self.on_row_hover(rf, True))
                widget.bind("<Leave>", lambda e, rf=row_frame: self.on_row_hover(rf, False))
                widget.bind("<Button-1>", lambda e, r=row: self.on_row_select(r))

            for j, key in enumerate(["script", "display", "status"]):
                row_frame.grid_columnconfigure(j, weight=1, uniform="col")
                label = ctk.CTkLabel(
                    row_frame,
                    text=row[key],
                    font=ctk.CTkFont(family="Inter", weight="bold"),
                    text_color=("#1a1b24", "#ffffff"),
                    anchor="w",
                )
                label.grid(row=0, column=j, sticky="w", padx=10, pady=5)

            # If this is the selected row, apply the hover color
            if self.selected_row and self.selected_row == row:
                row_frame.configure(fg_color=("#ffffff", "#1a1b24"))

    def create_bottom_section(self):
        """Create bottom section with controls."""
        bottom_frame = ctk.CTkFrame(self.main_container, fg_color=("#ffffff", "#1a1b24"))
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # Control buttons frame
        control_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        control_frame.pack(fill=tk.X, pady=5)

        # Plus and minus buttons
        button_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        button_frame.pack(side=tk.RIGHT, padx=5)

        ctk.CTkButton(
            button_frame,
            image=self.images["plus"],
            text="",
            width=30,
            height=30,
            fg_color=("#f2f1fa", "#312e3f"),
            hover_color=("#ffffff", "#1a1b24"),
            command=self.add_script,
        ).pack(side=tk.LEFT, padx=2)

        ctk.CTkButton(
            button_frame,
            image=self.images["minus"],
            text="",
            width=30,
            height=30,
            fg_color=("#f2f1fa", "#312e3f"),
            hover_color=("#ffffff", "#1a1b24"),
            command=self.remove_script,
        ).pack(side=tk.LEFT, padx=2)

        # Input frame
        input_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.grid_columnconfigure(1, weight=1)

        # Display Name input
        ctk.CTkLabel(
            input_frame, text="DISPLAY NAME:", font=ctk.CTkFont(family="Inter", weight="bold")
        ).grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.display_entry = ctk.CTkEntry(
            input_frame,
            fg_color=("#f2f1fa", "#312e3f"),
            border_width=0,
            font=ctk.CTkFont(family="Inter", weight="bold"),
        )
        self.display_entry.grid(
            row=0, column=1, padx=(5, 5), pady=5, sticky="ew"
        )  # Adjusted padding

        # Enable/Disable switch
        current_theme = ctk.get_appearance_mode().lower()
        initial_image = self.images["switch_off_dark" if current_theme == "dark" else "switch_off"]

        self.status_switch = ctk.CTkButton(
            input_frame,
            image=initial_image,
            text="",
            width=60,
            height=20,
            command=self.toggle_status,
            hover_color=("#ffffff", "#1a1b24"),
            fg_color="transparent",
        )
        self.status_switch.grid(row=0, column=2, padx=5, pady=5)

        # Default Layout frame
        layout_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        layout_frame.pack(fill=tk.X, pady=5)
        layout_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            layout_frame, text="DEFAULT LAYOUT:", font=ctk.CTkFont(family="Inter", weight="bold")
        ).grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.default_var = tk.StringVar()
        self.default_dropdown = ctk.CTkOptionMenu(
            layout_frame,
            variable=self.default_var,
            values=[],
            fg_color=("#f2f1fa", "#312e3f"),
            button_color=("#f2f1fa", "#312e3f"),
            button_hover_color=("#ffffff", "#1a1b24"),
            dropdown_fg_color=("#f2f1fa", "#312e3f"),
            font=ctk.CTkFont(family="Inter", weight="bold"),
            text_color=("#1a1b24", "#ffffff"),
        )
        self.default_dropdown.grid(
            row=0, column=1, padx=(5, 5), pady=5, sticky="ew"
        )  # Changed from "ew" to "w" and adjusted padding

        # Buttons frame
        buttons_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        buttons_frame.pack(fill=tk.X, pady=5)

        ctk.CTkButton(
            buttons_frame,
            text="SAVE AND EXIT",
            command=self.save_and_exit,
            fg_color=("#f2f1fa", "#312e3f"),
            text_color=("#1a1b24", "#ffffff"),
            font=ctk.CTkFont(family="Inter", weight="bold"),
        ).pack(side=tk.RIGHT, padx=5)

        ctk.CTkButton(
            buttons_frame,
            text="APPLY",
            command=self.apply_changes,
            fg_color=("#f2f1fa", "#312e3f"),
            text_color=("#1a1b24", "#ffffff"),
            font=ctk.CTkFont(family="Inter", weight="bold"),
        ).pack(side=tk.RIGHT, padx=5)

    def on_row_select(self, row):
        """Handle row selection."""
        if self.selected_row and self.selected_row == row:
            self.selected_row = None
            self.display_entry.delete(0, tk.END)
            current_theme = ctk.get_appearance_mode().lower()
            switch_image = self.images[
                "switch_off_dark" if current_theme == "dark" else "switch_off"
            ]
            self.status_switch.configure(image=switch_image)
            self.display_table()
            return

        self.selected_row = row
        self.display_entry.delete(0, tk.END)
        self.display_entry.insert(0, row["display"])
        current_theme = ctk.get_appearance_mode().lower()
        switch_image = (
            self.images["switch_on_dark" if current_theme == "dark" else "switch_on"]
            if row["status"] == "Enabled"
            else self.images["switch_off_dark" if current_theme == "dark" else "switch_off"]
        )
        self.status_switch.configure(image=switch_image)
        self.display_table()

    def on_row_hover(self, row_frame, entering):
        """Handle row hover effects."""
        is_selected = self.selected_row and any(
            child.cget("text") == self.selected_row["script"]
            for child in row_frame.winfo_children()
        )

        if entering:
            row_frame.configure(fg_color=("#ffffff", "#1a1b24"))
        elif is_selected:
            row_frame.configure(fg_color=("#ffffff", "#1a1b24"))
        else:
            row_frame.configure(fg_color=("#f2f1fa", "#312e3f"))

    def toggle_status(self):
        """Toggle status of selected row."""
        if self.selected_row:
            new_status = "Disabled" if self.selected_row["status"] == "Enabled" else "Enabled"
            self.selected_row["status"] = new_status
            current_theme = ctk.get_appearance_mode().lower()
            switch_image = (
                self.images["switch_on_dark" if current_theme == "dark" else "switch_on"]
                if new_status == "Enabled"
                else self.images["switch_off_dark" if current_theme == "dark" else "switch_off"]
            )
            self.status_switch.configure(image=switch_image)
            self.display_table()

    def add_script(self):
        """Add new script."""
        # Implement script addition logic
        self.show_status("Adding new script...")

    def remove_script(self):
        """Remove selected script."""
        if self.selected_row:
            # Implement script removal logic
            self.show_status(f"Removing script: {self.selected_row['script']}")

    def show_status(self, message, duration=3000):
        """Show status message."""
        self.status_label.configure(text=message)
        self.window.after(duration, lambda: self.status_label.configure(text=""))

    def toggle_theme(self):
        """Toggle between light and dark theme."""
        current_theme = ctk.get_appearance_mode().lower()
        new_theme = "light" if current_theme == "dark" else "dark"
        ctk.set_appearance_mode(new_theme)

        # Update the button image to show the opposite theme icon
        self.theme_button.configure(image=self.images["light" if new_theme == "dark" else "dark"])

        self.save_theme()
        self.refresh_ui()

    def refresh_ui(self):
        """Refresh UI with updated colors"""
        self.display_table()
        if self.selected_row:
            current_theme = ctk.get_appearance_mode().lower()
            switch_image = (
                self.images["switch_on_dark" if current_theme == "dark" else "switch_on"]
                if self.selected_row["status"] == "Enabled"
                else self.images["switch_off_dark" if current_theme == "dark" else "switch_off"]
            )
            self.status_switch.configure(image=switch_image)
        else:
            current_theme = ctk.get_appearance_mode().lower()
            switch_image = self.images[
                "switch_off_dark" if current_theme == "dark" else "switch_off"
            ]
            self.status_switch.configure(image=switch_image)

    def load_data(self):
        """Load data from config file and populate the table."""
        try:
            config = self.autotiler.get_layout_config()
            default_layout = self.autotiler.default_layout

            # Clear existing table content
            for widget in self.table_frame.winfo_children():
                widget.destroy()

            # Populate dropdown values
            layout_names = list(config.keys())
            self.default_dropdown.configure(values=layout_names)
            self.default_var.set(default_layout)

            # Create table rows
            self.rows_data = []
            for script_name, layout_info in config.items():
                row_data = {
                    "script": script_name,
                    "display": layout_info.get("display_name", script_name.capitalize()),
                    "status": "Enabled" if layout_info.get("enabled", True) else "Disabled",
                }
                self.rows_data.append(row_data)

            self.display_table()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")

    def sort_table(self, key: str):
        """Sort table by specified column."""
        reverse = self.sort_direction[key]
        self.rows_data.sort(key=lambda x: x[key].lower(), reverse=reverse)
        self.sort_direction[key] = not reverse
        self.display_table()

    def update_status(self, row: Dict, value: str):
        """Update status of a layout."""
        row["status"] = value

    def apply_changes(self):
        """Apply changes to configuration."""
        try:
            config = {}
            for row in self.rows_data:
                config[row["script"]] = {
                    "display_name": row["display"],
                    "enabled": row["status"] == "Enabled",
                }

            # Update config file
            current_config = self.autotiler.get_layout_config()
            current_config.update(config)

            with open(self.autotiler.config_file, "r+") as f:
                full_config = json.load(f)
                full_config["layouts"] = current_config
                full_config["default_layout"] = self.default_var.get()
                f.seek(0)
                json.dump(full_config, f, indent=4)
                f.truncate()

            # Refresh tray menu
            self.autotiler.refresh_menu()

            messagebox.showinfo("Success", "Configuration saved successfully!")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration: {e}")

    def save_and_exit(self):
        """Save changes and close the window."""
        self.apply_changes()
        self.window.destroy()

    def run(self):
        """Start the GUI."""
        self.window.mainloop()

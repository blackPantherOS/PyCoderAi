import logging
import sys
import os
import json
import cups
import subprocess
import re
import socket
from PySide6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QPushButton, QSystemTrayIcon, QMenu, QApplication, QMessageBox
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QAction
from PySide6.QtCore import QTimer, Qt, QSize, QRect, QByteArray
from PySide6.QtSvg import QSvgRenderer
import gettext

gettext.install("printer-states", "/usr/share/locale")

# Konfigurációs fájl útvonala
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "printer-states")
CONFIG_FILE = os.path.join(CONFIG_DIR, "watched.conf")

# CUPS kapcsolat
conn = cups.Connection()

# Logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class PrinterMonitor(QSystemTrayIcon):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.setToolTip(_("Nyomtató állapotok"))
        self.setIcon(QIcon(":/printer.png"))
        self.menu = QMenu(None)
        self.menu.addAction(_("Nyomtató beállítások"), self.open_settings)
        self.menu.addAction(_("Kilépés"), QApplication.quit)
        self.setContextMenu(self.menu)
        self.show()

    def load_config(self):
        """Konfiguráció betöltása"""
        if not os.path.exists(CONFIG_FILE):
            return {}
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            logger.error("Konfiguráció betöltési hiba")
            return {}

    def save_config(self):
        """Konfiguráció mentése"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info("Konfiguráció mentve: %s", CONFIG_FILE)
        except IOError as e:
            logger.error("Konfiguráció mentési hiba: %s", e)

    def open_settings(self):
        """Nyomtató beállítások ablak megnyitása"""
        dialog = PrinterSettingsDialog(self.config)
        dialog.setWindowTitle(_("Nyomtató beállítások"))
        dialog.setWindowIcon(QIcon(":/printer.png"))
        dialog.setMinimumSize(480, 360)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_config = dialog.get_selected_printers()
            if updated_config != self.config:
                self.config = updated_config
                self.save_config()
                self.update_printer_status()

    def update_printer_status(self):
        """Nyomtató állapot frissítése"""
        printers = self.get_printers()
        status_messages = []
        problem_detected = False
        printing_detected = False

        for printer_name, printer in printers.items():
            if printer_name not in self.config:
                self.config[printer_name] = True
                self.save_config()
            else:
                pass

            state = printer["printer-state"]
            state_message = printer["printer-state-message"]

            if not self.is_printer_connected(printer):
                status_messages.append(f"{printer_name}: "+_("Kapcsolat nincs"))
                problem_detected = True
            elif state == 5:  # Paused
                status_messages.append(f"{printer_name}: "+_("Pausában"))
                problem_detected = True
            elif state == 3:  # Ready
                status_messages.append(f"{printer_name}: "+_("Készen"))
            else:
                status_messages.append(f"{printer_name}: {state_message}")
                printing_detected = True

        if problem_detected:
            self.setIcon(QIcon(":/warning.png"))
        elif printing_detected:
            self.setIcon(QIcon(":/printing.png"))
        else:
            self.setIcon(QIcon(":/printer.png"))

        self.setToolTip("\n".join(status_messages))

    def get_printers(self):
        """Nyomtatók lekérdezése"""
        try:
            return self.conn.getPrinters()
        except cups.IPPError as e:
            logger.error("CUPS hiba: %s", e)
            return {}

    def is_printer_connected(self, printer):
        """Nyomtató kapcsolat ellenőrzése"""
        device_uri = printer["device-uri"]
        if device_uri.startswith("usb") or device_uri.startswith("hp:/usb"):
            try:
                lsusb_output = subprocess.check_output(["lsusb"], stderr=subprocess.STDOUT, text=True)
                printer_name = printer["printer-name"]
                printer_name_words = printer_name.lower().split()
                for word in printer_name_words:
                    if not re.search(rf'\b{word}\b', lsusb_output, re.IGNORECASE):
                        return False
                return True
            except subprocess.CalledProcessError:
                return False
        return True

class PrinterSettingsDialog(QDialog):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.setWindowTitle(_("Nyomtató beállítások"))
        layout = QVBoxLayout()
        self.checkboxes = {}
        for printer_name, is_checked in self.config.items():
            checkbox = QCheckBox(printer_name)
            checkbox.setChecked(is_checked)
            layout.addWidget(checkbox)
            self.checkboxes[printer_name] = checkbox

        ok_button = QPushButton(_("Mentés"))
        ok_button.clicked.connect(self.save_and_close)
        layout.addWidget(ok_button)

        self.setLayout(layout)

    def save_and_close(self):
        """Mentés és bezárás"""
        self.config = self.get_selected_printers()
        self.save_config()
        self.close()  # Ez a sor zárja be az ablakot
        
    def save_config(self):
        """Konfiguráció mentése"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info("Konfiguráció mentve: %s", CONFIG_FILE)
        except IOError as e:
            logger.error("Konfiguráció mentési hiba: %s", e)

    def get_selected_printers(self):
        """Kiválasztott nyomtatók állapotának lekérdezése"""
        return {printer_name: checkbox.isChecked() for printer_name, checkbox in self.checkboxes.items()}

if __name__ == "__main__":
    app = QApplication(sys.argv)
    tray_icon = PrinterMonitor()
    tray_icon.show()
    sys.exit(app.exec())
    
import sys
from PyQt5.QtWidgets import QApplication
from tecancavro.pump_gui import PumpGUI

def main():
    app = QApplication(sys.argv)
    window = PumpGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

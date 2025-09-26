#!/usr/bin/env python3
import sys
from time import sleep

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QMessageBox, QSpinBox, QComboBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QHeaderView
)
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QColor, QBrush


# Replace these with the real library imports you use for the pump.
# They were present in your original snippet so I'm referencing them the same way.
from tecancavro.models import XCaliburD
from tecancavro.transport import TecanAPISerial

#########################################################################
# Worker for background threading of pump actions                       #
#########################################################################

class PumpWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
#########################################################################
# Main PumpGUI class                                                    #
#########################################################################
class PumpGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tecan XCaliburD Pump GUI")
        self.resize(800, 700)
        self.com_link = None
        self.pump = None

        # Defaults
        self.default_port = 'COM11'
        self.default_baud = 9600

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Connection controls
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(False)
        self.port_combo.setMinimumWidth(140)
        conn_layout.addWidget(self.port_combo)

        self.refresh_btn = QPushButton("Refresh Ports")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        conn_layout.addWidget(self.refresh_btn)

        conn_layout.addWidget(QLabel("Baud:"))
        self.baud_input = QLineEdit(str(self.default_baud))
        self.baud_input.setFixedWidth(90)
        conn_layout.addWidget(self.baud_input)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connectPump)
        conn_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.disconnectPump)
        self.disconnect_btn.setEnabled(False)
        conn_layout.addWidget(self.disconnect_btn)

        layout.addLayout(conn_layout)

        # Speed and slope controls
        sp_layout = QHBoxLayout()
        sp_layout.addWidget(QLabel("Start (v):"))
        self.start_speed_edit = QLineEdit()
        self.start_speed_edit.setFixedWidth(80)
        sp_layout.addWidget(self.start_speed_edit)

        sp_layout.addWidget(QLabel("Top (V):"))
        self.top_speed_edit = QLineEdit()
        self.top_speed_edit.setFixedWidth(80)
        sp_layout.addWidget(self.top_speed_edit)

        sp_layout.addWidget(QLabel("Cutoff (c):"))
        self.cutoff_speed_edit = QLineEdit()
        self.cutoff_speed_edit.setFixedWidth(80)
        sp_layout.addWidget(self.cutoff_speed_edit)

        sp_layout.addWidget(QLabel("Slope (L):"))
        self.slope_edit = QLineEdit()
        self.slope_edit.setFixedWidth(60)
        sp_layout.addWidget(self.slope_edit)

        apply_speeds_btn = QPushButton("Apply Speeds/Slope")
        apply_speeds_btn.clicked.connect(self.apply_speeds_and_slope)
        read_speeds_btn = QPushButton("Read Speeds")
        read_speeds_btn.clicked.connect(self.read_speeds)
        sp_layout.addWidget(read_speeds_btn)
        sp_layout.addWidget(apply_speeds_btn)

        layout.addLayout(sp_layout)

        # Speed control (S)
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed Code (0-40):0 FAST, 40 SLOW"))
        self.speed_input = QLineEdit()
        self.speed_input.setFixedWidth(60)
        self.speed_btn = QPushButton("Set Speed")
        self.speed_btn.clicked.connect(self.set_speed)
        speed_layout.addWidget(self.speed_input)
        speed_layout.addWidget(self.speed_btn)
        layout.addLayout(speed_layout)

        # Plunger position control
        pos_layout = QHBoxLayout()
        self.get_pos_btn = QPushButton("Get Plunger Position")
        self.get_pos_btn.clicked.connect(self.get_plunger_pos)
        self.pos_display = QLabel("Unknown")
        pos_layout.addWidget(self.get_pos_btn)
        pos_layout.addWidget(self.pos_display)
        layout.addLayout(pos_layout)

        # Change port selector
        cp_layout = QHBoxLayout()
        cp_layout.addWidget(QLabel("Change to Port:"))
        self.change_port_spin = QSpinBox()
        self.change_port_spin.setRange(1, 6)  # adjust to your valve
        self.change_port_spin.setValue(1)
        self.change_port_btn = QPushButton("Change Port")
        self.change_port_btn.clicked.connect(self.change_port)
        cp_layout.addWidget(self.change_port_spin)
        cp_layout.addWidget(self.change_port_btn)
        layout.addLayout(cp_layout)
        # NEW: Separate behavior controls for dispense/extract speeds
        io_speed_layout = QHBoxLayout()
        io_speed_layout.addWidget(QLabel("Dispense flow (µL/min):"))
        self.dispense_flow_input = QLineEdit("300")  # default example
        self.dispense_flow_input.setFixedWidth(90)
        io_speed_layout.addWidget(self.dispense_flow_input)

        io_speed_layout.addWidget(QLabel("Extract speed code (0–40):"))
        self.extract_speed_code_input = QLineEdit("0")  # 0 = fastest in SPEED_CODES
        self.extract_speed_code_input.setFixedWidth(60)
        io_speed_layout.addWidget(self.extract_speed_code_input)

        layout.addLayout(io_speed_layout)

        # Flow rate controls
        flow_layout = QHBoxLayout()
        flow_layout.addWidget(QLabel("Set Flow Rate:"))
        self.flow_rate_input = QLineEdit()
        self.flow_rate_input.setFixedWidth(100)
        flow_layout.addWidget(self.flow_rate_input)
        flow_layout.addWidget(QLabel("µL/min"))
        self.set_flow_btn = QPushButton("Set Flow Rate")
        self.set_flow_btn.clicked.connect(self.set_flow_rate)
        flow_layout.addWidget(self.set_flow_btn)
        layout.addLayout(flow_layout)


        # Extract controls
        ex_layout = QHBoxLayout()
        ex_layout.addWidget(QLabel("Extract from port:"))
        self.extract_port_spin = QSpinBox()
        self.extract_port_spin.setRange(1, 6)
        self.extract_port_spin.setValue(1)
        ex_layout.addWidget(self.extract_port_spin)

        ex_layout.addWidget(QLabel("Volume (µL):"))
        self.extract_vol_input = QLineEdit()
        self.extract_vol_input.setFixedWidth(80)
        ex_btn = QPushButton("Extract")
        ex_btn.clicked.connect(self.extract_volume)
        ex_layout.addWidget(self.extract_vol_input)
        ex_layout.addWidget(ex_btn)
        layout.addLayout(ex_layout)

        # Dispense controls
        di_layout = QHBoxLayout()
        di_layout.addWidget(QLabel("Dispense to port:"))
        self.dispense_port_spin = QSpinBox()
        self.dispense_port_spin.setRange(1, 6)
        self.dispense_port_spin.setValue(1)
        di_layout.addWidget(self.dispense_port_spin)

        di_layout.addWidget(QLabel("Volume (µL):"))
        self.dispense_vol_input = QLineEdit()
        self.dispense_vol_input.setFixedWidth(80)
        di_btn = QPushButton("Dispense")
        di_btn.clicked.connect(self.dispense_volume)
        di_layout.addWidget(self.dispense_vol_input)
        di_layout.addWidget(di_btn)
        layout.addLayout(di_layout)


        # Extract to Waste (smart)
        etw_layout = QHBoxLayout()
        etw_layout.addWidget(QLabel("Extract-to-Waste in-port:"))
        self.etw_in_port = QSpinBox()
        self.etw_in_port.setRange(1, 6)
        self.etw_in_port.setValue(1)
        etw_layout.addWidget(self.etw_in_port)

        etw_layout.addWidget(QLabel("Volume (µL):"))
        self.etw_vol_edit = QLineEdit()
        self.etw_vol_edit.setFixedWidth(80)
        etw_layout.addWidget(self.etw_vol_edit)

        etw_layout.addWidget(QLabel("Speed Code (opt):"))
        self.etw_speed_edit = QLineEdit()
        self.etw_speed_edit.setFixedWidth(60)
        etw_layout.addWidget(self.etw_speed_edit)

        self.etw_flush_chk = QCheckBox("Flush after")
        self.etw_flush_chk.setChecked(False)
        etw_layout.addWidget(self.etw_flush_chk)

        etw_btn = QPushButton("Extract to Waste")
        etw_btn.clicked.connect(self.extract_to_waste)
        etw_layout.addWidget(etw_btn)

        layout.addLayout(etw_layout)

        # Dump to Waste
        dump_layout = QHBoxLayout()
        self.dump_retain_chk = QCheckBox("Return to previous port")
        self.dump_retain_chk.setChecked(True)
        dump_btn = QPushButton("Dump to Waste")
        dump_btn.clicked.connect(self.dump_to_waste)
        dump_layout.addWidget(dump_btn)
        dump_layout.addWidget(self.dump_retain_chk)
        layout.addLayout(dump_layout)

        # Absolute plunger move
        abs_layout = QHBoxLayout()
        abs_layout.addWidget(QLabel("Plunger Abs Pos:"))
        self.abs_pos_spin = QSpinBox()
        self.abs_pos_spin.setRange(0, 24000)  # adjusted by microstep
        self.abs_pos_spin.setValue(0)
        abs_move_btn = QPushButton("Move Abs")
        abs_move_btn.clicked.connect(self.move_abs)
        abs_layout.addWidget(self.abs_pos_spin)
        abs_layout.addWidget(abs_move_btn)
        layout.addLayout(abs_layout)

        # Relative plunger move
        rel_layout = QHBoxLayout()
        rel_layout.addWidget(QLabel("Plunger Rel Move (±steps):"))
        self.rel_pos_spin = QSpinBox()
        self.rel_pos_spin.setRange(-24000, 24000)  # adjusted by microstep
        self.rel_pos_spin.setValue(0)
        rel_move_btn = QPushButton("Move Rel")
        rel_move_btn.clicked.connect(self.move_rel)
        rel_layout.addWidget(self.rel_pos_spin)
        rel_layout.addWidget(rel_move_btn)
        layout.addLayout(rel_layout)



        # Microstep toggle
        micro_layout = QHBoxLayout()
        self.micro_chk = QCheckBox("Microstep")
        self.micro_chk.setChecked(True)
        micro_apply_btn = QPushButton("Apply Microstep")
        micro_apply_btn.clicked.connect(self.apply_microstep)
        micro_layout.addWidget(self.micro_chk)
        micro_layout.addWidget(micro_apply_btn)
        layout.addLayout(micro_layout)



        # Initialize options
        ip_layout = QHBoxLayout()
        init_btn = QPushButton("Initialize")
        init_btn.clicked.connect(self.initialize_pump)
        ip_layout.addWidget(init_btn)

        ip_layout.addWidget(QLabel("Direction:"))
        self.init_dir_combo = QComboBox()
        self.init_dir_combo.addItems(["CW", "CCW"])
        ip_layout.addWidget(self.init_dir_combo)

        ip_layout.addWidget(QLabel("Init force:"))
        self.init_force_spin = QSpinBox()
        self.init_force_spin.setRange(0, 40)
        self.init_force_spin.setValue(0)
        ip_layout.addWidget(self.init_force_spin)

        ip_layout.addWidget(QLabel("In-port:"))
        self.init_in_port = QSpinBox()
        self.init_in_port.setRange(1, 6)  # init in_port may be 0
        self.init_in_port.setValue(0)
        ip_layout.addWidget(self.init_in_port)

        ip_layout.addWidget(QLabel("Out-port:"))
        self.init_out_port = QSpinBox()
        self.init_out_port.setRange(1, 6)
        self.init_out_port.setValue(6)
        ip_layout.addWidget(self.init_out_port)

        layout.addLayout(ip_layout)

        # Wash controls (raw implementation; avoids Python 2 xrange in model)
        prime_layout = QHBoxLayout()
        prime_layout.addWidget(QLabel("Prime in-port:"))
        self.prime_port_spin = QSpinBox()
        self.prime_port_spin.setRange(1, 6)
        self.prime_port_spin.setValue(1)
        prime_layout.addWidget(self.prime_port_spin)

        prime_layout.addWidget(QLabel("Prime volume (µL):"))
        self.prime_vol_input = QLineEdit()
        self.prime_vol_input.setFixedWidth(80)
        prime_layout.addWidget(self.prime_vol_input)

        prime_layout.addWidget(QLabel("Speed Code (opt):"))
        self.prime_speed_edit = QLineEdit()
        self.prime_speed_edit.setFixedWidth(60)
        prime_layout.addWidget(self.prime_speed_edit)

        prime_layout.addWidget(QLabel("Waste port:"))
        self.prime_waste_spin = QSpinBox()
        self.prime_waste_spin.setRange(1, 6)
        self.prime_waste_spin.setValue(6)
        prime_layout.addWidget(self.prime_waste_spin)

        prime_btn = QPushButton("Prime")
        prime_btn.clicked.connect(self.prime_port)
        prime_layout.addWidget(prime_btn)
        layout.addLayout(prime_layout)

        # Status panel
        status_layout = QHBoxLayout()
        self.status_plunger = QLabel("Plunger: -")
        self.status_port = QLabel("Port: -")
        self.status_encoder = QLabel("Encoder: -")
        self.status_buffer = QLabel("Buffer: -")
        status_refresh_btn = QPushButton("Refresh Status")
        status_refresh_btn.clicked.connect(self.refresh_status)
        status_layout.addWidget(self.status_plunger)
        status_layout.addWidget(self.status_port)
        status_layout.addWidget(self.status_encoder)
        status_layout.addWidget(self.status_buffer)
        status_layout.addWidget(status_refresh_btn)
        layout.addLayout(status_layout)

        # Terminate command button
        self.terminate_btn = QPushButton("Terminate Command")
        self.terminate_btn.clicked.connect(self.terminate_command)
        layout.addWidget(self.terminate_btn)

        # Output log area
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        layout.addWidget(self.output_area)

        # Custom Protocol Editor with Action and Multi-Port
        proto_group = QVBoxLayout()
        proto_group.addWidget(QLabel("Custom Protocol Editor (step-by-step):"))

        self.protocol_table = QTableWidget(0, 5)
        self.protocol_table.setHorizontalHeaderLabels(
            ["Action", "Source Port", "Destination Port", "Volume (µL)", "Repeat"])
        self.protocol_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        proto_group.addWidget(self.protocol_table)

        # Add protocol repeat spinbox
        proto_repeat_layout = QHBoxLayout()
        proto_repeat_layout.addWidget(QLabel("Protocol Repeat:"))
        self.proto_repeat_spin = QSpinBox()
        self.proto_repeat_spin.setMinimum(1)
        self.proto_repeat_spin.setMaximum(1000)
        self.proto_repeat_spin.setValue(1)
        proto_repeat_layout.addWidget(self.proto_repeat_spin)
        proto_group.addLayout(proto_repeat_layout)

        # Add/Edit/Remove Controls
        proto_btns = QHBoxLayout()
        self.proto_add_btn = QPushButton("Add Step")
        self.proto_add_btn.clicked.connect(self.add_protocol_step)
        proto_btns.addWidget(self.proto_add_btn)

        self.proto_remove_btn = QPushButton("Remove Step")
        self.proto_remove_btn.clicked.connect(self.remove_protocol_step)
        proto_btns.addWidget(self.proto_remove_btn)

        # NEW: Clear All button
        self.proto_clear_btn = QPushButton("Clear All")
        self.proto_clear_btn.clicked.connect(self.clear_protocol_table)
        proto_btns.addWidget(self.proto_clear_btn)

        self.proto_run_btn = QPushButton("Run Protocol")
        self.proto_run_btn.clicked.connect(self.run_custom_protocol)
        proto_btns.addWidget(self.proto_run_btn)

        proto_group.addLayout(proto_btns)

        layout.addLayout(proto_group)

        # --- Gradient Generator UI ---
        gradient_group = QVBoxLayout()
        gradient_group.addWidget(QLabel("Binary Gradient Protocol Generator"))
        ggrid = QHBoxLayout()

        ggrid.addWidget(QLabel("Port A:"))
        self.grad_port_A = QSpinBox()
        self.grad_port_A.setRange(1, 6)
        self.grad_port_A.setValue(1)
        ggrid.addWidget(self.grad_port_A)

        ggrid.addWidget(QLabel("Port B:"))
        self.grad_port_B = QSpinBox()
        self.grad_port_B.setRange(1, 6)
        self.grad_port_B.setValue(2)
        ggrid.addWidget(self.grad_port_B)

        ggrid.addWidget(QLabel("Output Port:"))
        self.grad_output_port = QSpinBox()
        self.grad_output_port.setRange(1, 6)
        self.grad_output_port.setValue(3)
        ggrid.addWidget(self.grad_output_port)

        ggrid.addWidget(QLabel("Flow rate (µL/min):"))
        self.grad_flowrate = QLineEdit("300")
        self.grad_flowrate.setFixedWidth(80)
        ggrid.addWidget(self.grad_flowrate)

        ggrid.addWidget(QLabel("Step size (µL):"))
        self.grad_stepsize = QLineEdit("500")
        self.grad_stepsize.setFixedWidth(80)
        ggrid.addWidget(self.grad_stepsize)

        gradient_group.addLayout(ggrid)

        # Table for segments: Start(min), End(min), %A start, %A end
        seg_layout = QHBoxLayout()
        self.gradient_seg_table = QTableWidget(0, 4)
        self.gradient_seg_table.setHorizontalHeaderLabels(
            ["Start (min)", "End (min)", "%A Start", "%A End"]
        )
        self.gradient_seg_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        seg_layout.addWidget(self.gradient_seg_table)
        gradient_group.addLayout(seg_layout)

        seg_btns = QHBoxLayout()
        grad_add_btn = QPushButton("Add Segment")
        grad_add_btn.clicked.connect(self.gradient_add_segment)
        seg_btns.addWidget(grad_add_btn)
        grad_remove_btn = QPushButton("Remove Segment")
        grad_remove_btn.clicked.connect(self.gradient_remove_segment)
        seg_btns.addWidget(grad_remove_btn)
        gradient_group.addLayout(seg_btns)

        fill_proto_btn = QPushButton("Auto Fill Protocol Table")
        fill_proto_btn.clicked.connect(self.gradient_autofill_protocol)
        gradient_group.addWidget(fill_proto_btn)

        layout.addLayout(gradient_group)

        # --- Matplotlib canvas for gradient preview ---
        self.gradient_fig = Figure(figsize=(5,2))
        self.gradient_canvas = FigureCanvas(self.gradient_fig)
        gradient_group.addWidget(self.gradient_canvas)



        # Finalize UI
        self.setLayout(layout)
        self.refresh_ports()
    #########################################################################
    # Utility and thread helpers                                            #
    #########################################################################

    def _run_worker(self, fn, *args, **kwargs):
        self._disable_actions(True)
        self.worker = PumpWorker(fn, *args, **kwargs)
        self.worker.finished.connect(self._on_action_finished)
        self.worker.error.connect(self._on_action_error)
        self.worker.start()

    def _on_action_finished(self, result):
        if result:
            self.log(str(result))
        self.refresh_status()
        self._disable_actions(False)

    def _on_action_error(self, error):
        self.show_error(error)
        self._disable_actions(False)

    #########################################################################
    # Connection / Serial helpers                                           #
    #########################################################################

    def connectPump(self):
        try:
            port = (self.port_combo.currentText().strip() or self.default_port)
            baud = int(self.baud_input.text().strip() or self.default_baud)

            self.log(f"Connecting to {port} @ {baud}...")
            self.disconnectPump(silent=True)

            # Address 0 is typical default
            self.com_link = TecanAPISerial(0, port, baud)
            self.pump = XCaliburD(self.com_link)

            # Probe responsiveness
            try:
                fw = self.pump.sendRcv('&')
            except Exception:
                fw = None

            pos = None
            try:
                pos = self.pump.getPlungerPos()
            except Exception:
                pos = "Unknown"

            # Sync microstep UI and ranges to current pump state (default True if missing)
            micro = bool(getattr(self.pump, "microstep", True))
            self.micro_chk.setChecked(micro)
            self._apply_microstep_ranges(micro)

            self.log(f"Connected. Plunger pos: {pos}" + (f" | FW: {fw}" if fw else ""))
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
        except PermissionError as e:
            msg = f"Permission error opening {port}: {e}"
            self.show_error(self._friendly_port_error(msg, port))
            self.disconnectPump(silent=True)
        except OSError as e:
            if getattr(e, "errno", None) in (5, 13):
                msg = f"Access denied on {port}: {e}"
                self.show_error(self._friendly_port_error(msg, port))
                self.disconnectPump(silent=True)
            else:
                self.show_error(f"Failed to connect: {e}")
                self.disconnectPump(silent=True)
        except Exception as e:
            self.show_error(f"Failed to connect: {e}")
            self.disconnectPump(silent=True)

    def disconnectPump(self, silent=False):
        try:
            if self.com_link and hasattr(self.com_link, 'close'):
                try:
                    self.com_link.close()
                except Exception:
                    pass
            # If pump has a disconnect method, call it
            try:
                if self.pump and hasattr(self.pump, "disconnect"):
                    self.pump.disconnect()
            except Exception:
                pass
            self.com_link = None
            self.pump = None
            if not silent:
                self.log("Disconnected.")
        except Exception as e:
            if not silent:
                self.show_error(f"Failed to disconnect: {e}")
        finally:
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)

    #########################################################################
    # Basic actions                                                         #
    #########################################################################

    def set_speed(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            speed_code = int(self.speed_input.text())
            if speed_code < 0 or speed_code > 40:
                raise ValueError("Speed code must be between 0 and 40")
            # Convert code to pulses/sec and send top speed command
            pps = XCaliburD.SPEED_CODES.get(speed_code)
            if pps is None:
                raise ValueError(f"Unknown speed code: {speed_code}")
            self._send(f"V{pps}")
            self.log(f"Set top speed to {pps} pulses/sec (code S{speed_code})")
        except Exception as e:
            self.show_error(str(e))

    def get_plunger_pos(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            pos = self.pump.getPlungerPos()
            self.pos_display.setText(str(pos))
            self.log(f"Plunger Position: {pos}")
        except Exception as e:
            self.show_error(str(e))

    def change_port(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            to_port = int(self.change_port_spin.value())
            self._disable_actions(True)
            self._send(f"I{to_port}")
            self.log(f"Changed to port {to_port}")
        except Exception as e:
            self.show_error(str(e))
        finally:
            self._disable_actions(False)
    #########################################################################
    # Threaded pump actions (all long/blocking pump tasks!)                 #
    #########################################################################

    def extract_to_waste(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            in_port = int(self.etw_in_port.value())
            vol_txt = self.etw_vol_edit.text().strip()
            if not vol_txt:
                raise ValueError("Enter a volume in µL")
            volume = int(vol_txt)
            if volume <= 0:
                raise ValueError("Volume must be positive")
            speed_code = None
            if self.etw_speed_edit.text().strip():
                sc = int(self.etw_speed_edit.text().strip())
                if not (0 <= sc <= 40):
                    raise ValueError("Speed code must be 0–40")
                speed_code = sc
            flush = self.etw_flush_chk.isChecked()
            self._run_worker(self._extract_to_waste_worker, in_port, volume, speed_code, flush)
        except Exception as e:
            self.show_error(str(e))
            self._disable_actions(False)

    def _extract_to_waste_worker(self, in_port, volume, speed_code, flush):
        # Multi-pull logic
        syringe_ul = getattr(self.pump, "syringe_ul", 500)
        pulls = []
        full_pulls = volume // syringe_ul
        remainder = volume % syringe_ul

        msg_parts = []
        for _ in range(full_pulls):
            self.pump.extractToWaste(
                in_port, syringe_ul, speed_code=speed_code, flush=flush
            )
            self.pump.waitReady()
            msg_parts.append(f"{syringe_ul}µL")

        if remainder > 0:
            self.pump.extractToWaste(
                in_port, remainder, speed_code=speed_code, flush=flush
            )
            self.pump.waitReady()
            msg_parts.append(f"{remainder}µL")

        msg = (f"Extract-to-waste complete: {volume} µL from in-port {in_port} "
               f"in {full_pulls + (1 if remainder > 0 else 0)} transfer(s)"
               + (f", speed={speed_code}" if speed_code is not None else "")
               + (", flushed" if flush else "")
               + f" [{', '.join(msg_parts)}]")

        return msg

    def extract_volume(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            from_port = int(self.extract_port_spin.value())
            volume_txt = self.extract_vol_input.text().strip()
            if not volume_txt:
                raise ValueError("Enter a volume in µL")
            volume = int(volume_txt)
            if volume <= 0:
                raise ValueError("Volume must be positive")
            steps = self._volume_to_steps(volume)
            self._run_worker(self._extract_worker, from_port, steps, volume)
        except Exception as e:
            self.show_error(str(e))
            self._disable_actions(False)

    def _extract_worker(self, from_port, steps, volume):
        # Apply a fast (or user-selected) extract speed code BEFORE the move, as its own executed command
        try:
            sc_txt = (self.extract_speed_code_input.text().strip()
                      if hasattr(self, "extract_speed_code_input") else "")
            if sc_txt != "":
                sc = int(sc_txt)
                if not (0 <= sc <= 40):
                    raise ValueError("Extract speed code must be 0–40")
                # Send S{code} as an executed command so it takes effect immediately and won't be chained
                try:
                    # Use the model's helper for S code (maps internal state correctly)
                    self.pump.setSpeed(sc, execute=True)
                    self.pump.waitReady()
                except Exception:
                    # Fallback to direct top-speed pulses/sec if needed
                    from tecancavro.models import XCaliburD
                    pps = XCaliburD.SPEED_CODES.get(sc)
                    if pps:
                        self._send(f"V{pps}")  # executed by _send
        except Exception:
            # If invalid input or device error, continue with current speed
            pass

        # Now do the actual extract
        self._send(f"I{from_port}")
        self._send(f"P{steps}")
        return f"Extracted {volume} µL from port {from_port} ({steps} steps)."

    def dispense_volume(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            to_port = int(self.dispense_port_spin.value())
            volume_txt = self.dispense_vol_input.text().strip()
            if not volume_txt:
                raise ValueError("Enter a volume in µL")
            volume = int(volume_txt)
            if volume <= 0:
                raise ValueError("Volume must be positive")
            steps = self._volume_to_steps(volume)
            self._run_worker(self._dispense_worker, to_port, steps, volume)
        except Exception as e:
            self.show_error(str(e))
            self._disable_actions(False)

    def _dispense_worker(self, to_port, steps, volume):
        # Apply desired dispense flow as top speed
        try:
            flow_txt = (self.dispense_flow_input.text().strip()
                        if hasattr(self, "dispense_flow_input") else "")
            if flow_txt:
                pps = self._pps_for_flow(float(flow_txt))
                self._send(f"V{pps}")
        except Exception:
            # If any issue, silently continue with current speed
            pass
        self._send(f"I{to_port}")
        self._send(f"D{steps}")
        return f"Dispensed {volume} µL to port {to_port} ({steps} steps)."

    def dump_to_waste(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            retain = self.dump_retain_chk.isChecked()
            try:
                orig_port = self.pump.getCurPort()
            except Exception:
                orig_port = None
            waste_port = getattr(self.pump, "waste_port", 6)
            self._run_worker(self._dump_worker, waste_port, orig_port, retain)
        except Exception as e:
            self.show_error(str(e))
            self._disable_actions(False)

    def _dump_worker(self, waste_port, orig_port, retain):
        self._send(f"I{waste_port}")
        self._send("A0")
        msg = f"Dumped contents to waste port {waste_port}"
        if retain and orig_port:
            self._send(f"I{orig_port}")
            msg += f" and returned to port {orig_port}"
        return msg

    def move_abs(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            pos = int(self.abs_pos_spin.value())
            self._run_worker(self._move_abs_worker, pos)
        except Exception as e:
            self.show_error(str(e))
            self._disable_actions(False)

    def _move_abs_worker(self, pos):
        self._send(f"A{pos}")
        return f"Moved plunger to absolute position {pos}"

    def move_rel(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            rel = int(self.rel_pos_spin.value())
            self._run_worker(self._move_rel_worker, rel)
        except Exception as e:
            self.show_error(str(e))
            self._disable_actions(False)

    def _move_rel_worker(self, rel):
        if rel == 0:
            return "Relative move of 0 steps ignored."
        elif rel > 0:
            self._send(f"P{rel}")
            return f"Extracted {rel} steps (relative)."
        else:
            steps = abs(rel)
            self._send(f"D{steps}")
            return f"Dispensed {steps} steps (relative)."

    def prime_port(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            in_port = int(self.prime_port_spin.value())
            volume_txt = self.prime_vol_input.text().strip()
            if not volume_txt:
                raise ValueError("Enter a prime volume in µL")
            volume = int(volume_txt)
            if volume <= 0:
                raise ValueError("Volume must be positive")
            speed_code = None
            if self.prime_speed_edit.text().strip():
                sc = int(self.prime_speed_edit.text().strip())
                if not (0 <= sc <= 40):
                    raise ValueError("Speed code must be 0-40")
                speed_code = sc
            waste_port = int(self.prime_waste_spin.value())
            # No need to compute steps; let model handle volume chunking
            self._run_worker(self._prime_worker, in_port, volume, speed_code, waste_port)
        except Exception as e:
            self.show_error(str(e))
            self._disable_actions(False)

    def _prime_worker(self, in_port, volume, speed_code, waste_port):
        """
        Use a single high-level primePort call. primePort internally handles:
        - large volumes by splitting into syringe-sized cycles,
        - command chaining and executeChain(),
        - and waitReady() between cycles.
        """
        # Extra safety: ensure any previous command finished
        try:
            self.pump.waitReady()
        except Exception:
            pass

        # One call handles everything internally (including multi-pulls)
        self.pump.primePort(in_port, volume, speed_code=speed_code, out_port=waste_port)

        # Block until pump is ready for new commands
        self.pump.waitReady()

        return (f"Prime complete: in={in_port}, vol={volume} µL"
                + (f", speed={speed_code}" if speed_code is not None else "")
                + f", waste={waste_port}")

        self._send(f"I{waste_port}")
        self._send("A0")
        self._send(f"I{in_port}")
        self._send(f"A{steps}")
        self._send(f"I{waste_port}")
        self._send("A0")
        return (f"Prime complete: in={in_port}, vol={volume} µL"
                + (f", speed={speed_code}" if speed_code is not None else "")
                + f", waste={waste_port}")

    #########################################################################
    # Operational workflows                                                 #
    #########################################################################

    def initialize_pump(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            self._disable_actions(True)
            direction = self.init_dir_combo.currentText()
            init_force = int(self.init_force_spin.value())
            in_port = int(self.init_in_port.value())
            out_port = int(self.init_out_port.value())
            self.log(f"Initializing pump (dir={direction}, force={init_force}, in={in_port}, out={out_port})...")
            self.pump.init(init_force=init_force, direction=direction, in_port=in_port, out_port=out_port)
            self.pump.waitReady()
            # Sync microstep ranges and status after init
            micro = bool(getattr(self.pump, "microstep", True))
            self._apply_microstep_ranges(micro)
            self.refresh_status()
            self.log("Initialization complete.")
        except Exception as e:
            self.show_error(str(e))
        finally:
            self._disable_actions(False)


    #########################################################################
    # Microstep / speeds / status                                           #
    #########################################################################

    def apply_speeds_and_slope(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            cmds = []
            # Validate and queue commands
            if self.start_speed_edit.text().strip():
                start = int(self.start_speed_edit.text().strip())
                if not (50 <= start <= 1000):
                    raise ValueError("Start speed must be 50–1000 pulses/sec")
                cmds.append(f"v{start}")
            if self.top_speed_edit.text().strip():
                top = int(self.top_speed_edit.text().strip())
                if not (5 <= top <= 6000):
                    raise ValueError("Top speed must be 5–6000 pulses/sec")
                cmds.append(f"V{top}")
            if self.cutoff_speed_edit.text().strip():
                cutoff = int(self.cutoff_speed_edit.text().strip())
                if not (50 <= cutoff <= 2700):
                    raise ValueError("Cutoff speed must be 50–2700 pulses/sec")
                cmds.append(f"c{cutoff}")
            if self.slope_edit.text().strip():
                slope = int(self.slope_edit.text().strip())
                if not (1 <= slope <= 20):
                    raise ValueError("Slope code must be 1–20")
                cmds.append(f"L{slope}")

            if not cmds:
                self.log("No speed/slope changes to apply.")
                return

            self._disable_actions(True)
            for c in cmds:
                self._send(c)
            self.log("Applied speeds/slope: " + ", ".join(cmds))
        except Exception as e:
            self.show_error(str(e))
        finally:
            self._disable_actions(False)

    def read_speeds(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            start = self.pump.getStartSpeed()
            top = self.pump.getTopSpeed()
            cutoff = self.pump.getCutoffSpeed()
            self.start_speed_edit.setText(str(start))
            self.top_speed_edit.setText(str(top))
            self.cutoff_speed_edit.setText(str(cutoff))
            self.log(f"Speeds: start={start}, top={top}, cutoff={cutoff}")
        except Exception as e:
            self.show_error(str(e))

    def apply_microstep(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            on = self.micro_chk.isChecked()
            self._disable_actions(True)
            self.pump.setMicrostep(on=on)
            self._apply_microstep_ranges(on)
            self.log(f"Microstep {'ON' if on else 'OFF'} applied.")
        except Exception as e:
            self.show_error(str(e))
        finally:
            self._disable_actions(False)

    def refresh_status(self):
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            pl = self.pump.getPlungerPos()
            try:
                port = self.pump.getCurPort()
            except Exception:
                port = "-"
            try:
                enc = self.pump.getEncoderPos()
            except Exception:
                enc = "-"
            try:
                buf = self.pump.getBufferStatus()
                buf_str = "Non-empty" if buf else "Empty"
            except Exception:
                buf_str = "-"
            self.status_plunger.setText(f"Plunger: {pl}")
            self.status_port.setText(f"Port: {port}")
            self.status_encoder.setText(f"Encoder: {enc}")
            self.status_buffer.setText(f"Buffer: {buf_str}")
            self.pos_display.setText(str(pl))
        except Exception as e:
            self.show_error(str(e))
    #########################################################################
    # New: Set Flow Rate                                                    #
    #########################################################################
    def set_flow_rate(self):
        """
        Set the pump speed to achieve the target flow rate in µL/min.
        """
        try:
            if not self.pump:
                raise RuntimeError("Not connected")
            flowrate_txt = self.flow_rate_input.text().strip()
            if not flowrate_txt:
                raise ValueError("Enter a flow rate in µL/min")
            flow_ul_min = float(flowrate_txt)
            if flow_ul_min <= 0:
                raise ValueError("Flow rate must be positive")

            # Calculation: µL/min -> pulses/sec (pps)
            # Steps:
            #   1. Calculate steps/sec for the desired flow rate.
            #   2. 1 step = syringe_ul/full_scale µL
            #   3. steps/sec = [flow_ul_min / 60] / [syringe_ul/full_scale]
            syringe_ul = getattr(self.pump, "syringe_ul", 500)
            micro = getattr(self.pump, "microstep", True)
            full_scale = 24000 if micro else 3000

            # [steps/sec] = (flowrate [uL/min]/60) * (full_scale/syringe_ul)
            steps_per_sec = (flow_ul_min / 60.0) * (full_scale / syringe_ul)
            pps = int(round(steps_per_sec))

            # Clamp to allowed pump limits
            if pps < 5:
                pps = 5
            if pps > 6000:
                pps = 6000

            self._send(f"V{pps}")
            self.log(
                f"Set top speed to {pps} pulses/sec for flow {flow_ul_min} µL/min "
                f"({'microstep' if micro else 'normal'}, syringe {syringe_ul} µL)"
            )
        except Exception as e:
            self.show_error(str(e))

    #########################################################################
    # Protocol                                                              #
    #########################################################################
    def add_protocol_step(self):
        row = self.protocol_table.rowCount()
        self.protocol_table.insertRow(row)
        # Action Dropdown
        action_combo = QComboBox()
        action_combo.addItems(["Extract", "Dispense", "Flush", "Wash Syringe"])
        self.protocol_table.setCellWidget(row, 0, action_combo)
        # Source Port Dropdown
        src_port_combo = QComboBox()
        src_port_combo.addItems([str(i) for i in range(1, 7)])
        self.protocol_table.setCellWidget(row, 1, src_port_combo)
        # Destination Port Dropdown
        dest_port_combo = QComboBox()
        dest_port_combo.addItems([str(i) for i in range(1, 7)] + ["waste"])
        self.protocol_table.setCellWidget(row, 2, dest_port_combo)
        # Volume
        self.protocol_table.setItem(row, 3, QTableWidgetItem("10"))

        # Repeat
        self.protocol_table.setItem(row, 5, QTableWidgetItem("1"))

    def remove_protocol_step(self):
        row = self.protocol_table.currentRow()
        if row >= 0:
            self.protocol_table.removeRow(row)

    def run_custom_protocol(self):
        steps = []
        for row in range(self.protocol_table.rowCount()):
            action = self.protocol_table.cellWidget(row, 0).currentText().strip().lower()
            src_port = self.protocol_table.cellWidget(row, 1).currentText()
            dest_port = self.protocol_table.cellWidget(row, 2).currentText()
            vol = int(self.protocol_table.item(row, 3).text())
            speed_code = int(self.protocol_table.cellWidget(row, 4).currentText())
            repeat = int(self.protocol_table.item(row, 5).text())
            steps.append({
                "action": action,
                "src_port": src_port,
                "dest_port": dest_port,
                "vol": vol,
                "repeat": repeat,
            })
        protocol_repeat = self.proto_repeat_spin.value() if hasattr(self, "proto_repeat_spin") else 1
        self._run_worker(self._execute_custom_protocol, steps, protocol_repeat)

    def _execute_custom_protocol(self, steps, protocol_repeat=1):
        waste_port = str(getattr(self.pump, "waste_port", 6))

        # Reset all rows to 'normal' at the start (if you added row highlight)
        try:
            for r in range(self.protocol_table.rowCount()):
                self._set_protocol_row_state(r, 'normal')
        except Exception:
            pass

        # Cache last applied speeds to minimize redundant commands
        last_pps = None
        last_extract_sc = None

        for proto_num in range(protocol_repeat):
            self.log(f"=== Starting Protocol Run {proto_num+1} of {protocol_repeat} ===")
            for idx, step in enumerate(steps, 1):
                # Highlight current row (if you added row highlight)
                try:
                    self._set_protocol_row_state(idx-1, 'active')
                except Exception:
                    pass

                for _ in range(step['repeat']):
                    action = step['action']
                    src_port = step["src_port"]
                    dest_port = step["dest_port"]
                    vol_steps = self._volume_to_steps(step["vol"])

                    # Apply speeds by ACTION, not by protocol column
                    if action == "extract":
                        # Use Extract speed code from the GUI
                        try:
                            sc_txt = (self.extract_speed_code_input.text().strip()
                                      if hasattr(self, "extract_speed_code_input") else "")
                            if sc_txt != "":
                                sc = int(sc_txt)
                                if 0 <= sc <= 40 and sc != last_extract_sc:
                                    # Use model helper (S{code}) and wait
                                    try:
                                        self.pump.setSpeed(sc, execute=True)
                                        self.pump.waitReady()
                                    except Exception:
                                        # Fallback to V pps mapping if needed
                                        XCaliburD = type(self.pump)
                                        pps = XCaliburD.SPEED_CODES.get(sc)
                                        if pps:
                                            self._send(f"V{pps}")
                                    last_extract_sc = sc
                                    # Invalidate pps cache because S changes top speed
                                    last_pps = None
                        except Exception:
                            pass

                    elif action == "dispense":
                        # Use Dispense flow (µL/min) from the GUI
                        try:
                            flow_txt = (self.dispense_flow_input.text().strip()
                                        if hasattr(self, "dispense_flow_input") else "")
                            if flow_txt:
                                pps = self._pps_for_flow(float(flow_txt))
                                if pps and pps != last_pps:
                                    self._send(f"V{pps}")
                                    last_pps = pps
                                    # Invalidate last extract S cache since V changed top speed
                                    last_extract_sc = None
                        except Exception:
                            pass

                    # Execute the action after setting correct speed
                    if action == "extract":
                        self._send(f"I{src_port}")
                        self._send(f"P{vol_steps}")
                    elif action == "dispense":
                        self._send(f"I{dest_port}")
                        self._send(f"D{vol_steps}")
                    elif action == "flush":
                        # For flush, keep extract speed policy for the P move, and dispense at flow
                        # Extract phase
                        try:
                            sc_txt = (self.extract_speed_code_input.text().strip()
                                      if hasattr(self, "extract_speed_code_input") else "")
                            if sc_txt != "":
                                sc = int(sc_txt)
                                if 0 <= sc <= 40 and sc != last_extract_sc:
                                    try:
                                        self.pump.setSpeed(sc, execute=True)
                                        self.pump.waitReady()
                                    except Exception:
                                        XCaliburD = type(self.pump)
                                        pps = XCaliburD.SPEED_CODES.get(sc)
                                        if pps:
                                            self._send(f"V{pps}")
                                    last_extract_sc = sc
                                    last_pps = None
                        except Exception:
                            pass
                        self._send(f"I{src_port}")
                        self._send(f"P{vol_steps}")
                        # Dispense phase
                        try:
                            flow_txt = (self.dispense_flow_input.text().strip()
                                        if hasattr(self, "dispense_flow_input") else "")
                            if flow_txt:
                                pps = self._pps_for_flow(float(flow_txt))
                                if pps and pps != last_pps:
                                    self._send(f"V{pps}")
                                    last_pps = pps
                                    last_extract_sc = None
                        except Exception:
                            pass
                        self._send(f"I{dest_port if dest_port != 'waste' else waste_port}")
                        self._send("A0")
                    elif action == "wash syringe":
                        full_vol = getattr(self.pump, "syringe_ul", 500)
                        # Extract speed for fill
                        try:
                            sc_txt = (self.extract_speed_code_input.text().strip()
                                      if hasattr(self, "extract_speed_code_input") else "")
                            if sc_txt != "":
                                sc = int(sc_txt)
                                if 0 <= sc <= 40 and sc != last_extract_sc:
                                    try:
                                        self.pump.setSpeed(sc, execute=True)
                                        self.pump.waitReady()
                                    except Exception:
                                        XCaliburD = type(self.pump)
                                        pps = XCaliburD.SPEED_CODES.get(sc)
                                        if pps:
                                            self._send(f"V{pps}")
                                    last_extract_sc = sc
                                    last_pps = None
                        except Exception:
                            pass
                        self._send(f"I{src_port}")
                        self._send(f"P{self._volume_to_steps(full_vol)}")
                        # Dispense at flow
                        try:
                            flow_txt = (self.dispense_flow_input.text().strip()
                                        if hasattr(self, "dispense_flow_input") else "")
                            if flow_txt:
                                pps = self._pps_for_flow(float(flow_txt))
                                if pps and pps != last_pps:
                                    self._send(f"V{pps}")
                                    last_pps = pps
                                    last_extract_sc = None
                        except Exception:
                            pass
                        self._send(f"I{dest_port if dest_port != 'waste' else waste_port}")
                        self._send("A0")
                    else:
                        self.log(f"Unknown protocol action: {action}")

                # Mark row done after its repeats complete (if row highlighting exists)
                try:
                    self._set_protocol_row_state(idx-1, 'done')
                except Exception:
                    pass

                self.log(f"Step {idx}: {step}")
        return f"Custom protocol execution complete. Repeated {protocol_repeat} time(s)."

    def clear_protocol_table(self):
        try:
            self.protocol_table.setRowCount(0)
            self.log("Protocol table cleared.")
        except Exception as e:
            self.show_error(f"Failed to clear protocol table: {e}")

    def _set_protocol_row_state(self, row: int, state: str):
        """
        Visual state for a protocol row.
        state: 'active', 'done', or 'normal'
        """
        if row < 0 or row >= self.protocol_table.rowCount():
            return
        colors = {
            'active': QColor(255, 255, 200),   # light yellow
            'done': QColor(220, 255, 220),     # light green
            'normal': QColor(255, 255, 255),   # white
        }
        bg = QBrush(colors.get(state, colors['normal']))
        for col in range(self.protocol_table.columnCount()):
            item = self.protocol_table.item(row, col)
            if item is None:
                # Ensure there is an item to color (for empty cells like volume)
                item = QTableWidgetItem("")
                self.protocol_table.setItem(row, col, item)
            item.setBackground(bg)
        # Auto-scroll to the row when active
        if state == 'active':
            try:
                self.protocol_table.scrollToItem(self.protocol_table.item(row, 0))
                self.protocol_table.setCurrentCell(row, 0)
            except Exception:
                pass

    def _pps_for_flow(self, flow_ul_min: float) -> int:
        """
        Convert a target flow in µL/min into pulses/sec for the current syringe and microstep state.
        """
        if flow_ul_min <= 0:
            raise ValueError("Flow rate must be positive")
        syringe_ul = getattr(self.pump, "syringe_ul", 500)
        micro = getattr(self.pump, "microstep", True)
        full_scale = 24000 if micro else 3000
        steps_per_sec = (flow_ul_min / 60.0) * (full_scale / syringe_ul)
        pps = int(round(steps_per_sec))
        if pps < 5:    pps = 5
        if pps > 6000: pps = 6000
        return pps

    def gradient_add_segment(self):
        row = self.gradient_seg_table.rowCount()
        self.gradient_seg_table.insertRow(row)
        for i, val in enumerate(["0", "1", "95", "95" if row == 0 else "0"]):
            self.gradient_seg_table.setItem(row, i, QTableWidgetItem(val))

    def gradient_remove_segment(self):
        row = self.gradient_seg_table.currentRow()
        if row >= 0:
            self.gradient_seg_table.removeRow(row)

    def gradient_autofill_protocol(self):
        try:
            # Read segment table
            segment_rows = []
            for row in range(self.gradient_seg_table.rowCount()):
                t1 = float(self.gradient_seg_table.item(row, 0).text())
                t2 = float(self.gradient_seg_table.item(row, 1).text())
                a1 = float(self.gradient_seg_table.item(row, 2).text()) / 100.0
                a2 = float(self.gradient_seg_table.item(row, 3).text()) / 100.0
                segment_rows.append((t1, t2, a1, a2))
            flowrate = float(self.grad_flowrate.text())
            port_A = int(self.grad_port_A.value())
            port_B = int(self.grad_port_B.value())
            out_port = int(self.grad_output_port.value())
            step_ul = int(float(self.grad_stepsize.text()))
            syringe_ul = getattr(self.pump, "syringe_ul", 500) if self.pump else 500

            protocol_steps = generate_binary_gradient_protocol(
                segments=segment_rows,
                flow_rate_ul_min=flowrate,
                port_A=port_A,
                port_B=port_B,
                output_port=out_port,
                step_ul=step_ul,
                syringe_ul=syringe_ul,
            )
            self.protocol_table.setRowCount(0)
            for step in protocol_steps:
                row = self.protocol_table.rowCount()
                self.protocol_table.insertRow(row)
                action = step['action'].capitalize()
                action_combo = QComboBox()
                action_combo.addItems(["Extract", "Dispense", "Flush", "Wash Syringe"])
                action_idx = 0 if action.lower() == "extract" else 1 if action.lower() == "dispense" else 0
                action_combo.setCurrentIndex(action_idx)
                self.protocol_table.setCellWidget(row, 0, action_combo)
                src_val = str(step['src_port']) if step['src_port'] else ""
                src_combo = QComboBox()
                src_combo.addItems([""] + [str(i) for i in range(1, 7)])
                if src_val:
                    src_combo.setCurrentText(src_val)
                self.protocol_table.setCellWidget(row, 1, src_combo)
                dest_val = str(step['dest_port']) if step['dest_port'] else ""
                dest_combo = QComboBox()
                dest_combo.addItems([""] + [str(i) for i in range(1, 7)] + ["waste"])
                if dest_val:
                    dest_combo.setCurrentText(dest_val)
                self.protocol_table.setCellWidget(row, 2, dest_combo)
                self.protocol_table.setItem(row, 3, QTableWidgetItem(str(step['vol'])))

                self.protocol_table.setItem(row, 5, QTableWidgetItem("1"))

            # Plot the gradient composition (preview)
            self.gradient_fig.clear()
            ax = self.gradient_fig.add_subplot(111)
            # Rebuild gradient profiles
            times = []
            a_fracs = []
            b_fracs = []
            elapsed = 0
            for seg in segment_rows:
                t1, t2, a1, a2 = seg
                span = t2 - t1
                n = max(2, int(span * 10))  # at least two points, more if longer segment
                for i in range(n):
                    frac = i / (n - 1) if n > 1 else 0
                    time = t1 + span * frac
                    aa = a1 + (a2 - a1) * frac
                    bb = 1.0 - aa
                    times.append(time)
                    a_fracs.append(100 * aa)
                    b_fracs.append(100 * bb)
            ax.plot(times, a_fracs, label="A (%)", color='blue')
            ax.plot(times, b_fracs, label="B (%)", color='orange')
            ax.set_xlabel("Time (min)")
            ax.set_ylabel("Composition (%)")
            ax.set_ylim(0, 100)
            ax.set_xlim(min(times), max(times) if times else 1)
            ax.legend()
            ax.grid(True)
            self.gradient_canvas.draw()

            self.log(f"Gradient protocol created with {len(protocol_steps)} steps.")
        except Exception as e:
            self.show_error(f"Gradient generator error: {e}")


    #########################################################################
    # Helpers                                                               #
    #########################################################################

    def terminate_command(self):
        try:
            if hasattr(self, 'worker') and self.worker.isRunning():
                self.log("Signaling worker abort (GUI will stay responsive)")
                # For real aborts: you can add a stop flag to your worker logic!
            if self.pump:
                resp = self.pump.terminateCmd()
                self.log(f"Terminate command sent. Response: {resp}")
        except Exception as e:
            self.show_error(str(e))

    def refresh_ports(self):
        """Scan available pumps and populate the port dropdown."""
        try:
            self.log("Scanning for serial pumps...")
            found = []
            try:
                pump_list = TecanAPISerial.findSerialPumps()
                # Expected: [(ser_port, addr, baud), ...]
                if pump_list:
                    found = [p[0] for p in pump_list if p and len(p) >= 1]
            except Exception as e:
                self.log(f"Port scan error: {e}")

            self.port_combo.blockSignals(True)
            self.port_combo.clear()
            if found:
                for p in found:
                    self.port_combo.addItem(p)
                # Prefer default port if present
                idx = self.port_combo.findText(self.default_port)
                if idx >= 0:
                    self.port_combo.setCurrentIndex(idx)
                self.log(f"Ports found: {found}")
            else:
                # No devices detected; still provide a default option
                self.port_combo.addItem(self.default_port)
                self.log("No devices detected. Using default port entry.")
            self.port_combo.blockSignals(False)
        except Exception as e:
            self.show_error(f"Failed to refresh ports: {e}")

    def _send(self, cmd: str, execute: bool = True, wait: bool = True, timeout: float = 10.0, poll: float = 0.1):
        """
        Send a raw command and optionally wait until the pump is ready for the next one.
        This prevents command buffer overflow (error 15).
        """
        if not self.pump:
            raise RuntimeError("Not connected")
        data = self.pump.sendRcv(cmd, execute=execute)
        if wait:
            try:
                self.pump.waitReady(timeout=timeout, polling_interval=poll)
            except Exception:
                # As a fallback, small sleep to reduce burstiness
                sleep(0.15)
        return data

    def _friendly_port_error(self, base_msg, port):
        tips = [
            f"Make sure {port} exists and is correct (check Device Manager).",
            "Close any program that may have the port open (Arduino/VS Code Serial Monitor, PuTTY, NI MAX, other Python/Jupyter kernels, vendor tools).",
            "If you ran previous code that used the port, restart that kernel/app so it releases the handle.",
            "Unplug/replug the USB-to-serial adapter and try again (COM port number can change).",
            "Try a different COM port from the dropdown.",
            "You usually don't need admin rights, but if IT restricts ports, try running the app as Administrator.",
        ]
        return base_msg + "\n\nTroubleshooting:\n- " + "\n- ".join(tips)

    def _volume_to_steps(self, volume_ul: int) -> int:
        """
        Convert µL to steps using pump.syringe_ul and microstep if available.
        Falls back to 500 µL syringe and microstep=True.
        """
        syringe_ul = getattr(self.pump, "syringe_ul", 500) if self.pump else 500
        micro = getattr(self.pump, "microstep", True) if self.pump else True
        full_scale = 24000 if micro else 3000
        steps = int(round(volume_ul * (full_scale / float(syringe_ul))))
        if steps < 0:
            steps = 0
        return steps

    def _apply_microstep_ranges(self, micro: bool):
        """
        Update the absolute/relative spin ranges to match microstep mode.
        micro=True => abs 0..24000, rel -24000..24000
        micro=False => abs 0..3000, rel -3000..3000
        """
        try:
            self.abs_pos_spin.setRange(0, 24000 if micro else 3000)
            lim = 24000 if micro else 3000
            self.rel_pos_spin.setRange(-lim, lim)
        except Exception as e:
            self.log(f"Could not update microstep ranges: {e}")

    def _disable_actions(self, disable: bool):
        widgets = [
            self.connect_btn, self.disconnect_btn, self.refresh_btn,
            self.speed_btn, self.get_pos_btn, self.change_port_btn,
            self.micro_chk,  # self.terminate_btn removed from this list!
            # ... other widgets
        ]
        for w in widgets:
            try:
                if w is not None:
                    w.setEnabled(not disable)
            except Exception:
                pass
        self.terminate_btn.setEnabled(True)  # Always keep enabled

    def log(self, message: str):
        if hasattr(self, "output_area") and self.output_area is not None:
            self.output_area.append(message)
        else:
            print(message)

    def show_error(self, message: str):
        QMessageBox.critical(self, "Error", message)
        self.log(f"ERROR: {message}")

    def closeEvent(self, event):
        # Ensure serial handles are released cleanly
        try:
            self.disconnectPump(silent=True)
        except Exception:
            pass
        event.accept()

def generate_binary_gradient_protocol(
    segments, flow_rate_ul_min, port_A, port_B, output_port,
    step_ul=500, syringe_ul=500, min_protocol_step_ul=None
):
    if min_protocol_step_ul is None:
        min_protocol_step_ul = step_ul
    protocol_steps = []
    for seg in segments:
        t_start, t_end, a0, a1 = seg
        seg_time_min = t_end - t_start
        total_seg_vol = flow_rate_ul_min * seg_time_min
        n_proto_steps = max(1, int(round(total_seg_vol / min_protocol_step_ul)))
        for i in range(n_proto_steps):
            frac = i / (n_proto_steps - 1) if n_proto_steps > 1 else 0
            frac_A = a0 + (a1 - a0) * frac
            frac_B = 1.0 - frac_A
            this_step_ul = total_seg_vol / n_proto_steps
            vol_A = int(round(this_step_ul * frac_A))
            vol_B = int(round(this_step_ul * frac_B))
            vA, vB = vol_A, vol_B
            while vA > 0 or vB > 0:
                draw_A = min(vA, syringe_ul) if vA > 0 else 0
                draw_B = min(vB, syringe_ul - draw_A) if vB > 0 else 0
                if draw_A > 0:
                    protocol_steps.append(
                        {'action': 'extract', 'src_port': port_A, 'dest_port': output_port, 'vol': draw_A}
                    )
                    vA -= draw_A
                if draw_B > 0:
                    protocol_steps.append(
                        {'action': 'extract', 'src_port': port_B, 'dest_port': output_port, 'vol': draw_B}
                    )
                    vB -= draw_B
                mixture_vol = draw_A + draw_B
                if mixture_vol > 0:
                    protocol_steps.append(
                        {'action': 'dispense', 'src_port': None, 'dest_port': output_port, 'vol': mixture_vol}
                    )
    return protocol_steps

if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = PumpGUI()
    gui.show()
    sys.exit(app.exec_())

from __future__ import print_function

from flask import Flask, render_template, request
from flask_bootstrap import Bootstrap

app = Flask(__name__)
app.config.from_object(__name__)
Bootstrap(app)

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

try:
    from tecancavro.models import XCaliburD
    from tecancavro.transport import TecanAPISerial, TecanAPINode
except ImportError:  # Support direct import from package
    import sys
    import os
    dirn = os.path.dirname
    LOCAL_DIR = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(dirn(dirn(LOCAL_DIR)))
    from tecancavro.models import XCaliburD
    from tecancavro.transport import TecanAPISerial, TecanAPINode

device_dict = {}

def findSerialPumps():
    return TecanAPISerial.findSerialPumps()

def getSerialPumps():
    pump_list = findSerialPumps()
    return [(ser_port, XCaliburD(com_link=TecanAPISerial(0, ser_port, 9600))) for ser_port, _, _ in pump_list]

# Initialize devices at startup
devices = getSerialPumps()
device_dict = {ser_port: XCaliburD(com_link=TecanAPISerial(0, ser_port, 9600)) for ser_port, _ in devices}
print("Devices initialized:", device_dict)

@app.route('/')
def index():
    valves = list(range(1, 10))
    return render_template('index.html', params={'valves': valves, 'devices': device_dict})

@app.route('/Simple_Commands')
def Simple_Commands():
    valves = list(range(1, 10))
    return render_template('Simple_Commands.html', params={'valves': valves, 'devices': device_dict})

@app.route('/Protocol')
def Protocol():
    valves = list(range(1, 10))
    return render_template('Protocol.html', params={'valves': valves, 'devices': device_dict})

@app.route('/extract')
def extract_call():
    volume = int(request.args.get('volume', 0))
    port = int(request.args.get('port', 0))
    sp = request.args.get('serial_port', '')
    print(f"Received extract for: {volume} ul from port {port} on serial port {sp}")
    if sp in device_dict:
        device_dict[sp].extract(port, volume)
    return ('', 204)

@app.route('/dispense')
def dispense_call():
    volume = int(request.args.get('volume', 0))
    port = int(request.args.get('port', 0))
    sp = request.args.get('serial_port', '')
    print(f"Received dispense for: {volume} ul from port {port} on serial port {sp}")
    if sp in device_dict:
        device_dict[sp].dispense(port, volume)
    return ('', 204)

@app.route('/execute')
def execute_call():
    sp = request.args.get('serial_port', '')
    print("Executing chain")
    if sp in device_dict:
        device_dict[sp].executeChain()
    return ('', 204)

@app.route('/tables')
def tables():
    return render_template('tables.html')

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)

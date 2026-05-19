import logging
import time
import argparse
import socket
import os
import re

# --- PLC communicatie (Snap7) ---
try:
    import snap7
    from snap7.util import get_bool, set_bool, get_int, set_int, get_real, set_real
except ImportError:
    snap7 = None

class PLCCommunication:
    def __init__(self, ip='192.168.0.1', rack=0, slot=1, timeout=5.0):
        if not snap7:
            raise ImportError('snap7 niet geïnstalleerd')
        self.plc = snap7.client.Client()
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.connected = False
        self.plc.set_param(snap7.types.PingTimeout, int(timeout * 1000))
        self.plc.set_param(snap7.types.SendTimeout, int(timeout * 1000))
        self.plc.set_param(snap7.types.RecvTimeout, int(timeout * 1000))
    def connect(self):
        try:
            self.plc.connect(self.ip, self.rack, self.slot)
            self.connected = True
            return True
        except Exception:
            self.connected = False
            return False
    def disconnect(self):
        try:
            self.plc.disconnect()
            self.connected = False
        except: pass
    def is_connected(self):
        try:
            return self.plc.get_connected()
        except:
            return False
    def read_db(self, db, start, size):
        if not self.connected: self.connect()
        try:
            return self.plc.db_read(db, start, size)
        except: return None
    def write_db(self, db, start, data):
        if not self.connected: self.connect()
        try:
            self.plc.db_write(db, start, data)
            return True
        except: return False
    def read_bool(self, db, start, bit):
        data = self.read_db(db, start, 1)
        if data: return get_bool(data, 0, bit)
        return None
    def write_bool(self, db, start, bit, value):
        data = self.read_db(db, start, 1)
        if data:
            set_bool(data, 0, bit, value)
            return self.write_db(db, start, data)
        return False

# --- Modbus wrapper ---
try:
    from pymodbus.client.sync import ModbusTcpClient
except ImportError:
    ModbusTcpClient = None

class ModbusWrapper:
    def __init__(self, host, port=502, unit=1, timeout=3.0):
        if not ModbusTcpClient:
            raise ImportError('pymodbus niet geïnstalleerd')
        self.client = ModbusTcpClient(host, port=port, timeout=timeout)
        self.unit = unit
    def read_coils(self, addr, count=1):
        rr = self.client.read_coils(addr, count, unit=self.unit)
        return rr.bits if not rr.isError() else None
    def write_coil(self, addr, value):
        rr = self.client.write_coil(addr, value, unit=self.unit)
        return not rr.isError()

# --- OPC UA communicatie ---
try:
    from asyncua import Client as UAClient, ua
except ImportError:
    UAClient = None

import asyncio
class OPCUACommunication:
    def __init__(self, url):
        if not UAClient:
            raise ImportError('asyncua niet geïnstalleerd')
        self.url = url
        self.client = UAClient(url=url)
    async def connect(self):
        await self.client.connect()
    async def disconnect(self):
        await self.client.disconnect()
    async def read_node(self, node_id):
        node = self.client.get_node(node_id)
        return await node.read_value()
    async def write_node(self, node_id, value):
        node = self.client.get_node(node_id)
        await node.write_value(value)
        return True
    async def pulse_bool_node(self, node_id, duration_ms=100):
        node = self.client.get_node(node_id)
        await node.write_value(ua.Variant(True, ua.VariantType.Boolean))
        await asyncio.sleep(duration_ms/1000)
        await node.write_value(ua.Variant(False, ua.VariantType.Boolean))
        return True

# --- Dummy Auth (voor demo, niet veilig) ---
def check_user(user, pwd):
    return user == 'admin' and pwd == 'admin'

# --- Eenvoudige Flask API voor demo ---
try:
    from flask import Flask, request, jsonify
except ImportError:
    Flask = None

def scan_plcs(subnet='192.168.0.', start=1, end=20, timeout=0.2):
    """
    Scan het netwerk op PLC-poorten (Snap7: 102, Modbus: 502, OPC UA: 4840).
    Return: lijst van dicts met ip, type, open_ports
    """
    found = []
    ports = [(102, 'Snap7'), (502, 'Modbus'), (4840, 'OPC UA')]
    for i in range(start, end+1):
        ip = f'{subnet}{i}'
        open_types = []
        for port, typ in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            try:
                s.connect((ip, port))
                open_types.append(typ)
            except:
                pass
            finally:
                s.close()
        if open_types:
            found.append({'ip': ip, 'types': open_types})
    return found

def show_plc_selector():
    import threading
    import tkinter as tk
    from tkinter import messagebox

    def do_scan():
        scan_btn.config(state='disabled')
        result = scan_plcs()
        listbox.delete(0, tk.END)
        for plc in result:
            listbox.insert(tk.END, f"{plc['ip']} ({', '.join(plc['types'])})")
        scan_btn.config(state='normal')
        if not result:
            messagebox.showinfo('Scan', 'Geen PLC\'s gevonden.')

    def select_plc():
        sel = listbox.curselection()
        if sel:
            val = listbox.get(sel[0])
            ip = val.split(' ')[0]
            root.clipboard_clear()
            root.clipboard_append(ip)
            messagebox.showinfo('Geselecteerd', f'IP {ip} gekopieerd naar klembord!')
            root.destroy()

    root = tk.Tk()
    root.title('PLC Selecteren')
    tk.Label(root, text='Beschikbare PLC\'s op netwerk:').pack(pady=5)
    listbox = tk.Listbox(root, width=30, height=10)
    listbox.pack(padx=10, pady=5)
    scan_btn = tk.Button(root, text='Scan opnieuw', command=lambda: threading.Thread(target=do_scan).start())
    scan_btn.pack(pady=2)
    select_btn = tk.Button(root, text='Selecteer', command=select_plc)
    select_btn.pack(pady=2)
    threading.Thread(target=do_scan).start()
    root.mainloop()

if Flask:
    app = Flask(__name__)
    PLC_STORE = {}
    IO_STORE = {}

    S7_AREA_CODES = {
        'I': 0x81,
        'Q': 0x82,
        'M': 0x83,
    }

    def resolve_snap7_area(area):
        area_key = str(area or '').strip().upper()
        if area_key not in S7_AREA_CODES:
            return None
        if not snap7:
            return S7_AREA_CODES[area_key]
        try:
            areas_enum = getattr(snap7.types, 'Areas', None)
            if areas_enum is not None:
                mapping = {
                    'I': areas_enum.PE,
                    'Q': areas_enum.PA,
                    'M': areas_enum.MK,
                }
                return mapping.get(area_key)
        except Exception:
            pass
        return S7_AREA_CODES[area_key]

    def infer_io_type(tag):
        prefix = str(tag or '').strip()[:1].upper()
        return 'Output' if prefix == 'Q' else 'Input'

    def is_tag_writable(tag):
        prefix = str(tag or '').strip()[:1].upper()
        return prefix in {'M', 'V'}

    def normalize_point_definition(point):
        tag = str((point or {}).get('tag') or '').strip().upper()
        if not tag:
            return None
        name = str((point or {}).get('name') or tag).strip() or tag
        return {
            'name': name,
            'tag': tag,
            'io_type': infer_io_type(tag),
            'value': 1 if int((point or {}).get('value', 0)) else 0,
            'writable': bool((point or {}).get('writable', is_tag_writable(tag))),
        }

    def ensure_io_store(ip, configured_points=None):
        current = IO_STORE.get(ip, [])
        by_tag = {str(item.get('tag') or '').upper(): dict(item) for item in current}
        if configured_points is None:
            configured_points = current
        reconciled = []
        for point in configured_points:
            normalized = normalize_point_definition(point)
            if not normalized:
                continue
            existing = by_tag.get(normalized['tag'])
            if existing is not None:
                normalized['value'] = 1 if int(existing.get('value', 0)) else 0
            reconciled.append(normalized)
        IO_STORE[ip] = reconciled
        return IO_STORE[ip]

    def virtual_input_area():
        area = str(os.environ.get('PLC_VIRTUAL_INPUT_AREA') or 'M').strip().upper()
        return area if area in S7_AREA_CODES else 'M'

    def parse_s7_bit_tag(tag):
        raw = str(tag or '').strip().upper()
        match = re.fullmatch(r'([IQMV])(\d+)\.(\d+)', raw)
        if not match:
            return None
        prefix = match.group(1)
        area = virtual_input_area() if prefix == 'V' else prefix
        byte_index = int(match.group(2))
        bit_index = int(match.group(3))
        if bit_index < 0 or bit_index > 7:
            return None
        return prefix, area, byte_index, bit_index

    def get_write_areas(prefix, resolved_area):
        clean_prefix = str(prefix or '').strip().upper()
        clean_area = str(resolved_area or '').strip().upper()
        if clean_prefix in {'M', 'V'} and clean_area in S7_AREA_CODES:
            return [clean_area]

        primary_area = str(os.environ.get('PLC_INPUT_WRITE_AREA') or 'I').strip().upper()
        fallback_area = str(os.environ.get('PLC_INPUT_FALLBACK_AREA') or '').strip().upper()
        write_areas = [area for area in [primary_area, fallback_area] if area in S7_AREA_CODES]
        return write_areas or ['I']

    def read_s7_bit(ip, area, byte_index, bit_index):
        if not snap7:
            return None, 'snap7 niet beschikbaar'
        client = snap7.client.Client()
        rack = int(os.environ.get('PLC_S7_RACK', '0'))
        slot = int(os.environ.get('PLC_S7_SLOT', '1'))
        timeout_ms = int(float(os.environ.get('PLC_S7_TIMEOUT', '2.0')) * 1000)
        try:
            try:
                client.set_param(snap7.types.PingTimeout, timeout_ms)
                client.set_param(snap7.types.SendTimeout, timeout_ms)
                client.set_param(snap7.types.RecvTimeout, timeout_ms)
            except Exception:
                pass
            client.connect(ip, rack, slot)
            if not client.get_connected():
                return None, 'PLC verbinding mislukt'
            area_code = resolve_snap7_area(area)
            if area_code is None:
                return None, f'Onbekende area {area}'
            data = bytearray(client.read_area(area_code, 0, byte_index, 1))
            value = 1 if get_bool(data, 0, bit_index) else 0
            return value, None
        except Exception as exc:
            return None, str(exc)
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    def write_s7_bit(ip, area, byte_index, bit_index, value):
        if not snap7:
            return False, 'snap7 niet beschikbaar'
        client = snap7.client.Client()
        rack = int(os.environ.get('PLC_S7_RACK', '0'))
        slot = int(os.environ.get('PLC_S7_SLOT', '1'))
        timeout_ms = int(float(os.environ.get('PLC_S7_TIMEOUT', '2.0')) * 1000)
        try:
            try:
                client.set_param(snap7.types.PingTimeout, timeout_ms)
                client.set_param(snap7.types.SendTimeout, timeout_ms)
                client.set_param(snap7.types.RecvTimeout, timeout_ms)
            except Exception:
                pass
            client.connect(ip, rack, slot)
            if not client.get_connected():
                return False, 'PLC verbinding mislukt'
            area_code = resolve_snap7_area(area)
            if area_code is None:
                return False, f'Onbekende area {area}'
            data = bytearray(client.read_area(area_code, 0, byte_index, 1))
            set_bool(data, 0, bit_index, bool(value))
            client.write_area(area_code, 0, byte_index, data)
            return True, None
        except Exception as exc:
            return False, str(exc)
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

    def refresh_io_from_live(ip):
        ios = ensure_io_store(ip)
        any_live = False
        for io in ios:
            parsed = parse_s7_bit_tag(io.get('tag'))
            if not parsed:
                continue
            _, area, byte_index, bit_index = parsed
            value, error = read_s7_bit(ip, area, byte_index, bit_index)
            if error is None and value is not None:
                io['value'] = int(value)
                any_live = True
        return any_live

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
        return response

    @app.route('/plcs/scan', methods=['GET'])
    def scan_available_plcs():
        subnet = request.args.get('subnet', '192.168.0.')
        start = int(request.args.get('start', 1))
        end = int(request.args.get('end', 20))
        timeout = float(request.args.get('timeout', 0.2))
        result = scan_plcs(subnet=subnet, start=start, end=end, timeout=timeout)
        return jsonify(result)

    @app.route('/plcs', methods=['GET'])
    def list_plcs():
        return jsonify(list(PLC_STORE.values()))

    @app.route('/plcs', methods=['POST'])
    def add_plc():
        data = request.get_json(silent=True) or {}
        ip = data.get('ip')
        name = data.get('name', f'PLC {ip}') if ip else None
        plc_type = data.get('type', 'Onbekend')
        if not ip:
            return jsonify({'error': 'IP vereist'}), 400
        if ip in PLC_STORE:
            return jsonify({'error': 'PLC bestaat al'}), 400
        PLC_STORE[ip] = {'ip': ip, 'name': name, 'type': plc_type}
        IO_STORE[ip] = []
        return jsonify(PLC_STORE[ip]), 201

    @app.route('/plcs/<ip>', methods=['DELETE'])
    def delete_plc(ip):
        if ip in PLC_STORE:
            PLC_STORE.pop(ip)
            IO_STORE.pop(ip, None)
            return jsonify({'success': True})
        return jsonify({'error': 'Niet gevonden'}), 404

    @app.route('/plcs/<ip>/io', methods=['GET'])
    def get_io(ip):
        refresh_io_from_live(ip)
        return jsonify(ensure_io_store(ip))

    @app.route('/plcs/<ip>/io/config', methods=['POST'])
    def configure_io(ip):
        payload = request.get_json(silent=True) or {}
        points = payload.get('points') if isinstance(payload, dict) else None
        if not isinstance(points, list):
            return jsonify({'error': 'points lijst vereist'}), 400
        configured = ensure_io_store(ip, points)
        return jsonify({'ok': True, 'count': len(configured), 'io': configured})

    @app.route('/plcs/<ip>/io/<tag>/toggle', methods=['POST'])
    def toggle_io(ip, tag):
        ios = ensure_io_store(ip)
        requested_tag = str(tag or '').strip().upper()
        for io in ios:
            io_tag = str(io.get('tag') or '').strip().upper()
            if io_tag == requested_tag and io['io_type'] == 'Input' and bool(io.get('writable', False)):
                parsed = parse_s7_bit_tag(io.get('tag'))
                if not parsed:
                    return jsonify({'ok': False, 'live': False, 'error': 'Ongeldig tagformaat'}), 400

                prefix, resolved_area, byte_index, bit_index = parsed
                current_value, read_error = read_s7_bit(ip, resolved_area, byte_index, bit_index)
                if read_error is None and current_value is not None:
                    current_bit = int(current_value)
                else:
                    current_bit = 1 if int(io.get('value', 0)) else 0
                target_value = 0 if current_bit else 1

                write_areas = get_write_areas(prefix, resolved_area)

                write_error = None
                used_area = None
                for area in write_areas:
                    ok, error = write_s7_bit(ip, area, byte_index, bit_index, bool(target_value))
                    if ok:
                        used_area = area
                        break
                    write_error = error or 'onbekende fout'

                if not used_area:
                    return jsonify({
                        'ok': False,
                        'live': False,
                        'error': f'Live PLC-write mislukt ({write_error or "geen verbinding"})'
                    }), 502

                io['value'] = target_value
                refresh_io_from_live(ip)
                return jsonify({
                    'ok': True,
                    'live': True,
                    'tag': io.get('tag'),
                    'value': target_value,
                    'write_area': used_area,
                })
        return jsonify({'ok': False, 'live': False, 'error': 'IO niet gevonden of niet schrijfbaar'}), 404

    @app.route('/plcs/<ip>/io/<tag>/set', methods=['POST'])
    def set_io(ip, tag):
        ios = ensure_io_store(ip)
        requested_tag = str(tag or '').strip().upper()
        payload = request.get_json(silent=True) or {}

        if 'value' not in payload:
            return jsonify({'ok': False, 'live': False, 'error': 'Waarde ontbreekt'}), 400

        raw_value = payload.get('value')
        if isinstance(raw_value, str):
            lowered = raw_value.strip().lower()
            if lowered in {'1', 'true', 'aan', 'on'}:
                target_value = 1
            elif lowered in {'0', 'false', 'uit', 'off'}:
                target_value = 0
            else:
                return jsonify({'ok': False, 'live': False, 'error': 'Ongeldige waarde'}), 400
        else:
            target_value = 1 if bool(raw_value) else 0

        for io in ios:
            io_tag = str(io.get('tag') or '').strip().upper()
            if io_tag == requested_tag and io['io_type'] == 'Input' and bool(io.get('writable', False)):
                parsed = parse_s7_bit_tag(io.get('tag'))
                if not parsed:
                    return jsonify({'ok': False, 'live': False, 'error': 'Ongeldig tagformaat'}), 400

                prefix, resolved_area, byte_index, bit_index = parsed

                write_areas = get_write_areas(prefix, resolved_area)

                write_error = None
                used_area = None
                for area in write_areas:
                    ok, error = write_s7_bit(ip, area, byte_index, bit_index, bool(target_value))
                    if ok:
                        used_area = area
                        break
                    write_error = error or 'onbekende fout'

                if not used_area:
                    return jsonify({
                        'ok': False,
                        'live': False,
                        'error': f'Live PLC-write mislukt ({write_error or "geen verbinding"})'
                    }), 502

                io['value'] = target_value
                refresh_io_from_live(ip)
                return jsonify({
                    'ok': True,
                    'live': True,
                    'tag': io.get('tag'),
                    'value': target_value,
                    'write_area': used_area,
                })

        return jsonify({'ok': False, 'live': False, 'error': 'IO niet gevonden of niet schrijfbaar'}), 404


def run_demo_tests():
    print('Demo PLC all-in-one')
    try:
        plc = PLCCommunication()
        if plc.connect():
            print('PLC verbonden:', plc.is_connected())
            print('Lees DB1:', plc.read_db(1, 0, 4))
            plc.disconnect()
    except Exception as exc:
        print('Snap7 niet beschikbaar:', exc)

    try:
        modbus = ModbusWrapper('127.0.0.1')
        print('Lees coils:', modbus.read_coils(0, 4))
    except Exception as exc:
        print('Modbus niet beschikbaar:', exc)

    try:
        async def test_opcua():
            comm = OPCUACommunication('opc.tcp://localhost:4840')
            await comm.connect()
            print('Lees node:', await comm.read_node('ns=2;s=Demo.Static.Scalar.Boolean'))
            await comm.disconnect()
        asyncio.run(test_opcua())
    except Exception as exc:
        print('OPC UA niet beschikbaar:', exc)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PLC all-in-one utility')
    parser.add_argument('--mode', choices=['api', 'demo', 'gui'], default='api')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()

    if args.mode == 'demo':
        run_demo_tests()
    elif args.mode == 'gui':
        show_plc_selector()
    else:
        if not Flask:
            raise ImportError('Flask niet geïnstalleerd. Installeer met: pip install flask')
        print(f'--- Flask API gestart op http://{args.host}:{args.port} ---')
        app.run(host=args.host, port=args.port, debug=True)

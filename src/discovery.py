#!/usr/bin/env python3
"""
Descoberta de equipamentos Rigol na rede e USB
"""

import pyvisa
import socket
import time
import subprocess
import re
from typing import List, Tuple, Dict


class RigolDiscovery:
    """Descoberta de osciloscópios Rigol"""
    
    RIGOL_PORTS = [5555, 5025, 111]
    
    def discover_network(self, timeout: float = 2.0) -> List[Dict]:
        """Descobre Rigol na rede"""
        found = []
        subnets = ['192.168.1.', '192.168.0.', '192.168.68.', '10.0.0.', '172.16.0.', '172.31.0.']
        
        for subnet in subnets:
            for i in range(1, 255):
                ip = f'{subnet}{i}'
                for port in self.RIGOL_PORTS:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(timeout)
                        result = sock.connect_ex((ip, port))
                        if result == 0:
                            sock.sendall(b'*IDN?\n')
                            time.sleep(0.3)
                            resp = sock.recv(512).decode(errors='ignore').strip()
                            if resp and 'RIGOL' in resp.upper():
                                found.append({
                                    'ip': ip,
                                    'port': port,
                                    'idn': resp,
                                    'type': 'network'
                                })
                                print(f'[DISCOVER] Found {resp} at {ip}:{port}')
                            sock.close()
                            break
                    except Exception:
                        pass
                    finally:
                        try:
                            sock.close()
                        except:
                            pass
        
        return found
    
    def discover_usb(self) -> List[Dict]:
        """Descobre Rigol via USB"""
        found = []
        try:
            rm = pyvisa.ResourceManager('@py')
            resources = rm.list_resources()
            for r in resources:
                if 'USB' in r.upper() or 'RIGOL' in r.upper():
                    try:
                        inst = rm.open_resource(r)
                        inst.timeout = 3000
                        idn = inst.query('*IDN?').strip()
                        if 'RIGOL' in idn.upper():
                            found.append({
                                'resource': r,
                                'idn': idn,
                                'type': 'usb'
                            })
                            print(f'[DISCOVER] Found {idn} at {r}')
                        inst.close()
                    except Exception as e:
                        print(f'[DISCOVER] USB {r}: {e}')
            rm.close()
        except Exception as e:
            print(f'[DISCOVER] USB error: {e}')
        return found
    
    def discover_all(self) -> Dict:
        """Descobre todos os dispositivos"""
        results = {
            'network': self.discover_network(timeout=0.5),
            'usb': self.discover_usb(),
            'total': 0
        }
        results['total'] = len(results['network']) + len(results['usb'])
        return results


def discover_rigol_comprehensive() -> Dict:
    """Função wrapper para descoberta abrangente"""
    disc = RigolDiscovery()
    return disc.discover_all()

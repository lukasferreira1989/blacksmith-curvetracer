#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.scope_xy import RigolScopeXY, discover_rigol
import numpy as np

if __name__ == '__main__':
    all_res, rigol_res = discover_rigol()
    print("All resources:", all_res)
    print("Possible Rigol:", rigol_res)
    
    if not rigol_res and len(sys.argv) < 2:
        print("\nNenhum recurso encontrado. Passe o endereço manualmente.")
        print("Ex: python examples/rigol_xy_capture.py TCPIP::192.168.1.150::INSTR")
        sys.exit(1)
    
    addr = sys.argv[1] if len(sys.argv) > 1 else (rigol_res[0] if rigol_res else None)
    print(f"\nConectando em {addr}")
    
    scope = RigolScopeXY(addr)
    vx, vy = scope.capture_xy(ch_x='CHAN1', ch_y='CHAN2', probe_x=1.0, probe_y=1.0, y_is_direct_current=True)
    scope.run()
    scope.close()
    
    np.savetxt('curve_xy.csv', np.column_stack([vx, vy]), delimiter=',', header='V_X(V),I_Y(A_or_V)', comments='')
    print(f"Salvo: curve_xy.csv ({len(vx)} pontos)")

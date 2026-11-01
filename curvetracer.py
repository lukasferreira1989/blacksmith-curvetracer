#!/usr/bin/env python3
"""Ponto de entrada para empacotamento (PyInstaller) e execução direta."""

import multiprocessing
import os
import sys


def _ensure_std_streams() -> None:
    """Garante sys.stdout/sys.stderr válidos no executável sem console.

    No build ``console=False`` do PyInstaller os streams padrão são ``None``;
    qualquer ``print()`` (usado para diagnóstico em scope_xy/gui) falharia com
    "lost sys.stdout" e derrubaria o programa. Redireciona para um log no
    perfil do usuário e, se não for possível, para ``os.devnull``.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return

    stream = None
    try:
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
        log_dir = os.path.join(base, 'CurveTracer')
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'curvetracer.log')
        stream = open(log_path, 'a', encoding='utf-8', buffering=1)
    except Exception:
        stream = None

    if stream is None:
        stream = open(os.devnull, 'w', encoding='utf-8')

    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


# Antes de importar a GUI: os imports condicionais dela usam print().
_ensure_std_streams()

from src.gui import main  # noqa: E402  (após ajustar os streams)


def _run_self_check() -> int:
    """Valida o executável congelado sem abrir a janela principal.

    Usado pelo ``build_windows.bat`` logo após o PyInstaller. Verifica se os
    módulos empacotados (Qt, Matplotlib, NumPy/SciPy, PyVISA, pyusb) e a
    ``libusb-1.0.dll`` conseguem ser carregados. Retorna 0 em caso de sucesso.
    """
    import importlib

    problemas = []
    print("Blacksmith CurveTracer self-check")

    modulos = [
        "numpy",
        "scipy",
        "matplotlib",
        "matplotlib.backends.backend_qt5agg",
        "pyvisa",
        "pyvisa.ctwrapper",
        "pyvisa_py",
        "usb.core",
        "usb.backend.libusb1",
    ]
    for nome in modulos:
        try:
            importlib.import_module(nome)
            print(f"  [ok] {nome}")
        except Exception as exc:
            problemas.append(f"{nome}: {exc}")
            print(f"  [FALHA] {nome}: {exc}")

    # Qt + Matplotlib: cria a aplicação no backend offscreen para validar o
    # plugin de plataforma e a integração do canvas.
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        app = QApplication.instance() or QApplication([])
        canvas = FigureCanvasQTAgg(Figure())
        print(f"  [ok] Qt ({app.platformName()}) + Matplotlib canvas")
        canvas.close()
    except Exception as exc:
        problemas.append(f"Qt/Matplotlib: {exc}")
        print(f"  [FALHA] Qt/Matplotlib: {exc}")

    # Valida o carregamento do backend VISA (NI-VISA no Windows ou pyvisa-py).
    try:
        import pyvisa

        rm = pyvisa.ResourceManager()
        try:
            print(f"  [ok] VISA ResourceManager ({type(rm.visalib).__name__})")
        finally:
            rm.close()
    except Exception as exc:
        problemas.append(f"VISA ResourceManager: {exc}")
        print(f"  [FALHA] VISA ResourceManager: {exc}")

    # O fallback puro Python é usado no Windows quando o NI-VISA não está
    # instalado; precisa conseguir importar pyvisa_py em tempo de execução.
    try:
        rm_py = pyvisa.ResourceManager('@py')
        try:
            print("  [ok] pyvisa-py backend")
        finally:
            rm_py.close()
    except Exception as exc:
        problemas.append(f"pyvisa-py backend: {exc}")
        print(f"  [FALHA] pyvisa-py backend: {exc}")

    # libusb é opcional (NI-VISA pode ser usado), mas se o pacote foi
    # empacotado a DLL precisa carregar.
    try:
        import libusb_package
    except ImportError:
        print("  [aviso] libusb_package ausente (use NI-VISA para USB)")
    else:
        try:
            backend = libusb_package.get_libusb1_backend()
        except Exception as exc:
            print(f"  [FALHA] libusb: {exc}")
            problemas.append(f"libusb: {exc}")
        else:
            if backend is None:
                print("  [FALHA] libusb-1.0.dll não pôde ser carregada")
                problemas.append("libusb-1.0.dll não pôde ser carregada")
            else:
                print("  [ok] libusb-1.0.dll")

    if problemas:
        print("SELF-CHECK FALHOU")
        return 1

    print("SELF-CHECK OK")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--self-check" in sys.argv:
        sys.exit(_run_self_check())
    main()
    sys.exit(0)

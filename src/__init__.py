"""CurveTracer OSS - Rigol DHO Edition"""

__version__ = "2.0.0"

from .driver import RigolDHODriver, RigolDriverError, ConnectionError, CommunicationError, AcquisitionError
from .scope_xy import RigolScopeXY, discover_rigol, compute_channel_screen_range
from .discovery import RigolDiscovery, discover_rigol_comprehensive

__all__ = [
    'RigolDHODriver',
    'RigolDriverError',
    'ConnectionError',
    'CommunicationError',
    'AcquisitionError',
    'RigolScopeXY',
    'discover_rigol',
    'compute_channel_screen_range',
    'RigolDiscovery',
    'discover_rigol_comprehensive',
]


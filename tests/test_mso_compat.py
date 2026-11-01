#!/usr/bin/env python3
"""Compatibilidade DHO800/DHO900 x MSO5000 (ex.: MSO5074).

Baseado nos guias de programação em ``docs/``:

* DHO800900_ProgrammingGuide_EN.pdf
  - ``:TIMebase:XY:ENABle``, ``:TIMebase:XY:X/Y``
  - ``:CHANnel<n>:SCALe?`` / ``:OFFSet?``
* MSO5_programming_guide.pdf
  - ``:TIMebase:MODE {MAIN|XY|ROLL}``
  - sem ``:TIMebase:XY:*`` (fontes X-Y fixas em CH1/CH2)
  - ``:CHANnel<n>:SCALe?`` / ``:OFFSet?``
  - ``:WAVeform:MODE NORMal`` lê os 1.000 pontos exibidos na tela; é o modo
    usado no MSO para reproduzir a curva X-Y do display
  - ``:WAVeform:MODE RAW`` exige ``:WAVeform:STARt`` / ``:STOP``
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from src.scope_xy import RigolScopeXY


class FakeScope(RigolScopeXY):
    """Scope sem hardware: registra escritas e responde queries mapeadas."""

    def __init__(self, model='', idn='', responses=None):
        self.model = model
        self.idn = idn
        self.connected = True
        self.writes = []
        self.queries = []
        self.responses = responses or {}

    def _write(self, cmd):
        self.writes.append(cmd)

    def _query(self, cmd):
        self.queries.append(cmd)
        if cmd in self.responses:
            value = self.responses[cmd]
            if callable(value):
                return value(cmd)
            return value
        raise AssertionError(f"unexpected query: {cmd}")


MSO_IDN = (
    'RIGOL TECHNOLOGIES,MSO5074,MS5A261500717,00.01.03.03.00'
)
DHO_IDN = (
    'RIGOL TECHNOLOGIES,DHO924S,DHO9S261401341,00.01.04'
)


class TestModelDetection(unittest.TestCase):
    def test_mso_family_detected_from_model(self):
        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        self.assertTrue(scope._is_mso_family())

    def test_mso_family_detected_from_idn_without_model(self):
        scope = FakeScope(idn=MSO_IDN)
        self.assertTrue(scope._is_mso_family())

    def test_dho_is_not_mso(self):
        scope = FakeScope(model='DHO924S', idn=DHO_IDN)
        self.assertFalse(scope._is_mso_family())

    def test_unknown_model_keeps_dho_behaviour(self):
        scope = FakeScope()
        self.assertFalse(scope._is_mso_family())

    def test_set_identity_parses_idn(self):
        scope = FakeScope()
        scope._set_identity(MSO_IDN)
        self.assertEqual(scope.idn, MSO_IDN)
        self.assertEqual(scope.model, 'MSO5074')

    def test_screen_divisions_are_eight_by_eight(self):
        self.assertEqual(
            FakeScope(model='MSO5074', idn=MSO_IDN).get_screen_divisions(),
            (8.0, 8.0),
        )
        self.assertEqual(
            FakeScope(model='DHO924S', idn=DHO_IDN).get_screen_divisions(),
            (8.0, 8.0),
        )

    def test_mso_capture_config_sets_and_restores_mdepth(self):
        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        scope.configure_for_capture()
        self.assertIn(':ACQ:MDEP 10k', scope.writes)
        scope.restore_acquisition_config()
        self.assertIn(':ACQ:MDEP AUTO', scope.writes)

    def test_dho_capture_config_is_a_noop(self):
        scope = FakeScope(model='DHO924S', idn=DHO_IDN)
        scope.configure_for_capture()
        self.assertEqual(scope.writes, [])


class TestXYMode(unittest.TestCase):
    def test_mso_enable_uses_timebase_mode(self):
        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        scope.set_xy_enabled(True)
        scope.set_xy_enabled(False)
        self.assertEqual(scope.writes, [':TIM:MODE XY', ':TIM:MODE MAIN'])

    def test_dho_enable_uses_xy_enable(self):
        scope = FakeScope(model='DHO924S', idn=DHO_IDN)
        scope.set_xy_enabled(True)
        scope.set_xy_enabled(False)
        self.assertEqual(
            scope.writes,
            [':TIM:XY:ENABle ON', ':TIM:XY:ENABle OFF'],
        )

    def test_mso_is_xy_enabled_queries_timebase_mode(self):
        scope = FakeScope(
            model='MSO5074', idn=MSO_IDN,
            responses={':TIM:MODE?': 'XY'},
        )
        self.assertTrue(scope.is_xy_enabled())
        self.assertEqual(scope.queries, [':TIM:MODE?'])

    def test_mso_is_xy_disabled(self):
        scope = FakeScope(
            model='MSO5074', idn=MSO_IDN,
            responses={':TIM:MODE?': 'MAIN'},
        )
        self.assertFalse(scope.is_xy_enabled())

    def test_dho_is_xy_enabled_queries_xy_enable(self):
        scope = FakeScope(
            model='DHO924S', idn=DHO_IDN,
            responses={':TIM:XY:ENABle?': '1'},
        )
        self.assertTrue(scope.is_xy_enabled())
        self.assertEqual(scope.queries, [':TIM:XY:ENABle?'])

    def test_dho_accepts_on_off_strings(self):
        scope = FakeScope(
            model='DHO924S', idn=DHO_IDN,
            responses={':TIM:XY:ENABle?': 'ON'},
        )
        self.assertTrue(scope.is_xy_enabled())
        scope.responses[':TIM:XY:ENABle?'] = 'OFF'
        self.assertFalse(scope.is_xy_enabled())

    def test_mso_xy_sources_are_fixed(self):
        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        self.assertEqual(scope.get_xy_sources(), ('CHAN1', 'CHAN2'))
        self.assertEqual(scope.queries, [])

    def test_mso_xy_sources_cannot_be_changed(self):
        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        self.assertFalse(scope.set_xy_sources('CHAN2', 'CHAN1'))
        self.assertEqual(scope.writes, [])
        self.assertEqual(scope.queries, [])


class TestMSOChannels(unittest.TestCase):
    def test_scale_uses_documented_long_command(self):
        scope = FakeScope(
            model='MSO5074', idn=MSO_IDN,
            responses={':CHANnel1:SCALe?': '1.000000E-01'},
        )
        self.assertAlmostEqual(scope.get_channel_scale('CHAN1'), 0.1)
        self.assertEqual(scope.queries, [':CHANnel1:SCALe?'])

    def test_offset_uses_documented_long_command(self):
        scope = FakeScope(
            model='MSO5074', idn=MSO_IDN,
            responses={':CHANnel2:OFFSet?': '2.500000E-01'},
        )
        self.assertAlmostEqual(scope.get_channel_offset('CHANnel2'), 0.25)
        self.assertEqual(scope.queries, [':CHANnel2:OFFSet?'])

    def test_invalid_channel_returns_default(self):
        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        self.assertEqual(scope.get_channel_scale('CHAN'), 1.0)
        self.assertEqual(scope.get_channel_offset('CHAN'), 0.0)


class TestWaveformConfiguration(unittest.TestCase):
    def test_raw_sets_start_and_stop(self):
        scope = FakeScope(
            model='MSO5074', idn=MSO_IDN,
            responses={
                ':ACQ:MDEP?': '1.000000E+06',
                ':WAV:PRE?': '0,2,1000000,1,1E-6,0,0,4E-3,0,128',
            },
        )
        scope._configure_waveform('CHAN1', 'RAW')

        self.assertIn(':WAV:SOUR CHAN1', scope.writes)
        self.assertIn(':WAV:MODE RAW', scope.writes)
        self.assertIn(':WAV:FORM BYTE', scope.writes)
        self.assertIn(':WAV:STAR 1', scope.writes)
        self.assertIn(
            f':WAV:STOP {RigolScopeXY.WAVEFORM_MAX_POINTS}', scope.writes
        )

    def test_raw_stop_is_clamped_to_memory_depth(self):
        scope = FakeScope(
            model='MSO5074', idn=MSO_IDN,
            responses={
                ':ACQ:MDEP?': '5.000000E+03',
                ':WAV:PRE?': '0,2,5000,1,1E-6,0,0,4E-3,0,128',
            },
        )
        scope._configure_waveform('CHAN2', 'RAW')
        self.assertIn(':WAV:STOP 5000', scope.writes)

    def test_raw_stop_falls_back_when_depth_unknown(self):
        scope = FakeScope(
            model='MSO5074', idn=MSO_IDN,
            responses={
                ':WAV:PRE?': '0,2,1000,1,1E-6,0,0,4E-3,0,128',
            },
        )
        scope._configure_waveform('CHAN1', 'RAW')
        self.assertIn(
            f':WAV:STOP {RigolScopeXY.WAVEFORM_MAX_POINTS}', scope.writes
        )

    def test_normal_mode_uses_1000_points(self):
        scope = FakeScope(
            model='MSO5074', idn=MSO_IDN,
            responses={
                ':WAV:PRE?': '0,0,1000,1,1E-6,0,0,4E-3,0,128',
            },
        )
        scope._configure_waveform('CHAN1', 'NORM')
        self.assertIn(':WAV:STAR 1', scope.writes)
        self.assertIn(':WAV:STOP 1000', scope.writes)


class TestMSOCapture(unittest.TestCase):
    def _capture_scope(self, model, idn, xy_mode='MAIN'):
        responses = {':TIM:MODE?': xy_mode}

        class CaptureScope(FakeScope):
            def stop(self):
                pass

            def run(self):
                self.ran = True

            def _read_waveform_pair(self, *args, **kwargs):
                return (
                    np.array([0.0, 1.0]),
                    np.array([0.0, 2.0]),
                    {'yorig': 0, 'yinc': 1},
                    {'yorig': 0, 'yinc': 1},
                    'RAW',
                )

            def _query(self, cmd):
                if cmd.endswith(':DISP?'):
                    self.queries.append(cmd)
                    return '1'
                return super()._query(cmd)

        return CaptureScope(model=model, idn=idn, responses=responses)

    def test_mso_capture_enters_xy_with_timebase_mode(self):
        scope = self._capture_scope('MSO5074', MSO_IDN)
        vx, vy = scope.capture_xy('CHAN1', 'CHAN2')
        np.testing.assert_allclose(vx, [0.0, 1.0])
        np.testing.assert_allclose(vy, [0.0, 2.0])
        self.assertIn(':TIM:MODE XY', scope.writes)
        self.assertFalse(
            any(':TIM:XY:' in cmd for cmd in scope.writes),
            'MSO5000 não suporta :TIMebase:XY:*',
        )
        self.assertNotIn(':TIM:XY:ENABle?', scope.queries)

    def test_dho_capture_keeps_xy_enable_command(self):
        scope = self._capture_scope(
            'DHO924S', DHO_IDN, xy_mode='MAIN'
        )
        # O DHO usa a query XY:ENABle?; sem ela no mapa, is_xy_enabled()
        # devolve False e o driver liga o modo pelo comando do DHO.
        scope.responses[':TIM:XY:ENABle?'] = '0'
        scope.capture_xy('CHAN1', 'CHAN2')
        self.assertIn(':TIM:XY:ENABle ON', scope.writes)
        self.assertNotIn(':TIM:MODE XY', scope.writes)


class TestWaveformModeFallback(unittest.TestCase):
    def _scope(self, model, idn, fail_modes):
        class ModeScope(FakeScope):
            def __init__(self):
                super().__init__(model=model, idn=idn)
                self.modes = []

            def _read_channel_waveform(self, channel, probe=1.0, mode='NORM'):
                self.modes.append(mode)
                if mode in fail_modes:
                    raise Exception(f'{mode} unavailable')
                return (np.array([0.0, 1.0]), {'yorig': 0, 'yinc': 1})

        return ModeScope()

    def test_mso_prefers_normal_screen_mode(self):
        """No MSO o NORM reproduz a tela; RAW lê só o início da memória."""
        scope = self._scope('MSO5074', MSO_IDN, set())
        _, _, _, _, mode = scope._read_waveform_pair('CHAN1', 'CHAN2')
        self.assertEqual(mode, 'NORM')
        self.assertEqual(scope.modes[:2], ['NORM', 'NORM'])

    def test_dho_can_fall_back_to_normal_mode(self):
        scope = self._scope('DHO924S', DHO_IDN, {'RAW', 'MAX'})
        _, _, _, _, mode = scope._read_waveform_pair('CHAN1', 'CHAN2')
        self.assertEqual(mode, 'NORM')
        self.assertEqual(scope.modes[-2:], ['NORM', 'NORM'])

    def test_large_memory_prefers_screen_mode(self):
        scope = self._scope('MSO5074', MSO_IDN, set())
        scope.responses[':ACQ:MDEP?'] = '2.5000E+07'
        _, _, _, _, mode = scope._read_waveform_pair('CHAN1', 'CHAN2')
        self.assertEqual(mode, 'NORM')

    def test_small_memory_prefers_raw_mode(self):
        scope = self._scope('MSO5074', MSO_IDN, set())
        scope.responses[':ACQ:MDEP?'] = '1.0000E+04'
        _, _, _, _, mode = scope._read_waveform_pair('CHAN1', 'CHAN2')
        self.assertEqual(mode, 'RAW')


class TestPyUSBTMCQuery(unittest.TestCase):
    """A query via PyUSBTMC precisa usar TermChar (MSO5074)."""

    class FakeUSBTMC:
        def __init__(self, responses):
            self.responses = list(responses)
            self.writes = []
            self.reads = []

        def write(self, cmd):
            self.writes.append(cmd)

        def read(self, requestSize=0, io_timeout=0, flag=False,
                 termChar='\x00'):
            self.reads.append((flag, termChar))
            if not self.responses:
                return b''
            return self.responses.pop(0)

    def _scope(self, responses):
        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        scope.use_socket = False
        scope.inst = None
        scope.sock = None
        scope.usbtmc_file = None
        scope.usbtmc_inst = self.FakeUSBTMC(responses)
        return scope

    def test_query_enables_termination_character(self):
        scope = self._scope([b'1E-1\n'])
        self.assertEqual(
            RigolScopeXY._query(scope, ':CHANnel1:SCALe?'), '1E-1'
        )
        self.assertEqual(scope.usbtmc_inst.reads, [(True, '\n')])

    def test_timeout_is_not_retried(self):
        """Reenviar após timeout empilharia uma transferência USBTMC pendente."""
        class TimeoutUSBTMC(self.FakeUSBTMC):
            def read(self, *args, **kwargs):
                self.reads.append((kwargs.get('flag'), kwargs.get('termChar')))
                raise Exception('usb timeout')

        scope = self._scope([])
        scope.usbtmc_inst = TimeoutUSBTMC([])
        with self.assertRaises(Exception):
            RigolScopeXY._query(scope, ':CHANnel1:SCALe?')
        self.assertEqual(len(scope.usbtmc_inst.writes), 1)
        self.assertEqual(len(scope.usbtmc_inst.reads), 1)

    def test_empty_response_is_retried(self):
        scope = self._scope([b'\n', b'2.5E-1\n'])
        self.assertEqual(
            RigolScopeXY._query(scope, ':CHANnel2:OFFSet?'), '2.5E-1'
        )
        self.assertEqual(len(scope.usbtmc_inst.reads), 2)
        self.assertEqual(scope.usbtmc_inst.writes,
                         [':CHANnel2:OFFSet?', ':CHANnel2:OFFSet?'])

    def test_resync_discards_stale_response(self):
        scope = self._scope([
            b'#9000010000|||',
            b'RIGOL TECHNOLOGIES,MSO5074,SER,1.0\n',
        ])
        self.assertTrue(scope._resync_pyusbtmc())
        self.assertEqual(scope.usbtmc_inst.writes, ['*IDN?'])
        self.assertEqual(len(scope.usbtmc_inst.reads), 2)


class TestMSOCaptureSequence(unittest.TestCase):
    """Executa a captura completa contra um MSO5000 simulado."""

    def test_full_capture_only_uses_mso_commands(self):
        class MSOSimulator(RigolScopeXY):
            def __init__(self):
                self.model = 'MSO5074'
                self.idn = MSO_IDN
                self.connected = True
                self.mode = 'MAIN'
                self.mdepth = '2.5000E+07'
                self.writes = []
                self.queries = []

            def _write(self, cmd):
                self.writes.append(cmd)
                if cmd == ':TIM:MODE XY':
                    self.mode = 'XY'
                elif cmd == ':TIM:MODE MAIN':
                    self.mode = 'MAIN'
                elif cmd.startswith(':ACQ:MDEP 10k'):
                    self.mdepth = '1.0000E+04'
                elif cmd.startswith(':ACQ:MDEP'):
                    self.mdepth = '2.5000E+07'
                elif cmd.startswith(':TIM:XY:') or cmd.startswith(':WAVeform:XY'):
                    raise AssertionError(f'comando DHO-only no MSO: {cmd}')

            def _query(self, cmd):
                self.queries.append(cmd)
                if cmd == ':TIM:MODE?':
                    return self.mode
                if cmd.startswith(':CHAN') and cmd.endswith(':DISP?'):
                    return '1'
                if cmd == ':ACQ:MDEP?':
                    return self.mdepth
                if cmd == ':WAV:PRE?':
                    return '0,2,10000,1,1E-06,0,0,4E-03,0,128'
                if cmd.startswith(':TIM:XY'):
                    raise AssertionError(f'comando DHO-only no MSO: {cmd}')
                raise AssertionError(f'query inesperada: {cmd}')

            def _query_binary(self, cmd):
                if cmd == ':WAV:DATA?':
                    return np.arange(10000, dtype=np.uint8)
                raise AssertionError(f'query binária inesperada: {cmd}')

            def stop(self):
                pass

            def run(self):
                pass

        scope = MSOSimulator()
        vx, vy = scope.capture_xy('CHAN1', 'CHAN2')

        self.assertEqual(len(vx), 10000)
        self.assertEqual(len(vy), 10000)
        self.assertIn(':TIM:MODE XY', scope.writes)
        self.assertIn(':ACQ:MDEP 10k', scope.writes)
        self.assertIn(':WAV:MODE RAW', scope.writes)
        self.assertIn(':WAV:STAR 1', scope.writes)
        self.assertIn(':WAV:STOP 10000', scope.writes)
        self.assertFalse(
            any(cmd.startswith(':TIM:XY') for cmd in scope.writes),
            'MSO5000 não aceita :TIMebase:XY:*',
        )
        self.assertFalse(
            any(cmd.startswith(':TIM:XY') for cmd in scope.queries),
            'MSO5000 não aceita :TIMebase:XY:*',
        )


class TestDiscoveryDoesNotClaimUSB(unittest.TestCase):
    """A descoberta deve usar os descritores USB, sem abrir o USBTMC."""

    def test_pyusbtmc_device_is_not_opened(self):
        from contextlib import ExitStack
        from unittest.mock import patch
        import src.scope_xy as scope_mod

        if not getattr(scope_mod, 'USBTMC_AVAILABLE', False):
            self.skipTest('PyUSBTMC not installed')

        class FakeDevice:
            idVendor = 0x1AB1
            idProduct = 0x0515
            serial_number = 'MS5A261500717'
            product = 'MSO5074'
            manufacturer = 'Rigol'

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                scope_mod.PyUSBTMC, 'find_tmc_devices',
                return_value=[FakeDevice()]))
            stack.enter_context(patch.object(
                scope_mod.PyUSBTMC, 'USBTMC_device',
                side_effect=AssertionError('USBTMC opened during discovery')))
            stack.enter_context(patch.object(
                scope_mod, '_open_visa_resource_manager',
                side_effect=Exception('no VISA in tests')))
            stack.enter_context(patch.object(
                scope_mod.glob, 'glob', return_value=[]))
            all_res, rigol = scope_mod.discover_rigol()

        self.assertIn('PyUSBTMC::1ab1:0515', all_res)
        self.assertEqual(
            rigol,
            (('PyUSBTMC::1ab1:0515',
              'RIGOL TECHNOLOGIES,MSO5074,MS5A261500717,'),),
        )


class TestPyUSBTMCLiteInit(unittest.TestCase):
    """O MSO5074 pode falhar no GET_CAPABILITIES e ainda funcionar em bulk."""

    def test_lite_init_does_not_use_control_requests(self):
        from array import array

        class FakeEndpoint:
            def __init__(self, address, attributes):
                self.bEndpointAddress = address
                self.bmAttributes = attributes
                self.wMaxPacketSize = 512

        class FakeInterface:
            bInterfaceNumber = 0
            bInterfaceClass = 0xFE
            bInterfaceSubClass = 3
            bNumEndpoints = 3

            def __init__(self):
                self.endpoints = [
                    FakeEndpoint(0x81, 0x02),
                    FakeEndpoint(0x01, 0x02),
                    FakeEndpoint(0x82, 0x03),
                ]

            def __iter__(self):
                return iter(self.endpoints)

        class FakeConfig:
            def __init__(self):
                self.interfaces = [FakeInterface()]

            def __iter__(self):
                return iter(self.interfaces)

        class FakeDevice:
            def __init__(self):
                self.config = FakeConfig()
                self.calls = []

            def is_kernel_driver_active(self, interface):
                return False

            def set_configuration(self, *args):
                self.calls.append('set_configuration')

            def set_interface_altsetting(self, *args):
                self.calls.append('set_interface_altsetting')

            def ctrl_transfer(self, *args, **kwargs):
                raise AssertionError('GET_CAPABILITIES não deve ser chamado')

            def __iter__(self):
                return iter([self.config])

        device = FakeDevice()
        inst = RigolScopeXY._open_pyusbtmc_lite(device)

        self.assertIs(inst.device, device)
        self.assertEqual(inst.bulk_in.bEndpointAddress, 0x81)
        self.assertEqual(inst.bulk_out.bEndpointAddress, 0x01)
        self.assertEqual(inst.intr_in.bEndpointAddress, 0x82)
        self.assertIn('set_configuration', device.calls)

        # Evita o __del__ do PyUSBTMC tentar liberar um device falso.
        inst.device = None


class TestPyUSBTMCBinaryRead(unittest.TestCase):
    def test_short_usb_packets_are_joined(self):
        from array import array

        class FakeResp:
            TransferSize = 10012
            data = array('B', b'#9000010000' + b'A' * 8169)

        class FakeBulkIn:
            def __init__(self):
                self.chunks = [b'B' * 1832]

            def read(self, size, timeout=0):
                if not self.chunks:
                    raise Exception('timeout')
                return self.chunks.pop(0)

        class FakeUSBTMC:
            def __init__(self):
                self.writes = []
                self.bulk_in = FakeBulkIn()

            def write(self, cmd):
                self.writes.append(cmd)

            def device_read(self, size, timeout=0):
                self.requested = size
                return FakeResp()

        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        scope.usbtmc_inst = FakeUSBTMC()

        payload = scope._pyusbtmc_read_binary(':WAV:DATA?')
        self.assertEqual(len(payload), 10012)
        self.assertTrue(payload.startswith(b'#9000010000'))
        self.assertEqual(scope.usbtmc_inst.writes, [':WAV:DATA?'])
        self.assertGreaterEqual(scope.usbtmc_inst.requested, 65536)

    def test_query_binary_parses_tmc_block(self):
        block = b'#9000010000' + bytes(range(256)) * 39 + bytes(16)
        self.assertEqual(len(block), 11 + 10000)

        scope = FakeScope(model='MSO5074', idn=MSO_IDN)
        scope.use_socket = False
        scope.inst = None
        scope.sock = None
        scope.usbtmc_file = None
        scope.usbtmc_inst = object()
        scope._pyusbtmc_read_binary = lambda cmd: block

        raw = RigolScopeXY._query_binary(scope, ':WAV:DATA?')
        self.assertEqual(len(raw), 10000)
        self.assertEqual(int(raw[0]), 0)
        self.assertEqual(int(raw[255]), 255)


if __name__ == '__main__':
    unittest.main()

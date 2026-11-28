"""Read-only RAM observations; never infer free VRAM or allocation guarantees."""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path


def _linux_ram(proc=Path('/proc'), cgroup=Path('/sys/fs/cgroup')):
    """Bound MemAvailable by every visible cgroup v2 ancestor's headroom."""
    lines = (proc / 'meminfo').read_text(encoding='ascii').splitlines()
    fields = {}
    for line in lines:
        key, _, value = line.partition(':')
        if key in ('MemTotal', 'MemAvailable'):
            parts = value.split()
            if key in fields or len(parts) != 2 or parts[1] != 'kB':
                raise ValueError('Invalid meminfo')
            fields[key] = int(parts[0]) * 1024
    total, available = fields['MemTotal'], fields['MemAvailable']
    if not 0 <= available <= total or total <= 0:
        raise ValueError('Invalid memory observation')
    groups = (proc / 'self/cgroup').read_text(encoding='utf-8').splitlines()
    if len(groups) != 1 or not groups[0].startswith('0::/'):
        raise ValueError('Unsupported cgroup layout')
    raw = groups[0][3:]
    if any(p in ('.', '..') for p in raw.split('/')):
        raise ValueError('Invalid cgroup path')
    # A non-root mount may hide ancestor limits. Do not treat that as unlimited.
    mounts = (proc / 'self/mountinfo').read_text(encoding='utf-8').splitlines()
    if not any(len(line.split()) >= 10 and line.split()[3:5] == ['/', str(cgroup)]
               and ' - cgroup2 ' in line for line in mounts):
        raise ValueError('Unsupported cgroup mount')
    node = cgroup / raw.lstrip('/')
    while True:
        limit = (node / 'memory.max').read_text(encoding='ascii').strip()
        current = int((node / 'memory.current').read_text(encoding='ascii').strip())
        if current < 0:
            raise ValueError('Invalid cgroup usage')
        if limit != 'max':
            maximum = int(limit)
            if maximum < 0:
                raise ValueError('Invalid cgroup limit')
            available = min(available, max(0, maximum - current))
        if node == cgroup:
            break
        node = node.parent
    return available


def _windows_ram():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
            (name, ctypes.c_uint64) for name in ('total_phys', 'avail_phys', 'total_page',
                                                'avail_page', 'total_virtual', 'avail_virtual',
                                                'avail_extended')]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    query = ctypes.WinDLL('kernel32', use_last_error=True).GlobalMemoryStatusEx
    query.argtypes = [ctypes.POINTER(MemoryStatus)]
    query.restype = ctypes.c_int
    if not query(ctypes.byref(status)):
        raise OSError('GlobalMemoryStatusEx failed')
    if not 0 <= status.avail_phys <= status.total_phys or status.total_phys == 0:
        raise ValueError('Invalid memory observation')
    return status.avail_phys


def snapshot():
    source = 'unsupported'
    available = None
    try:
        if sys.platform == 'win32':
            source = 'GlobalMemoryStatusEx'
            available = _windows_ram()
        elif sys.platform.startswith('linux'):
            source = 'MemAvailable_and_visible_cgroup_v2'
            available = _linux_ram()
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    return {'schema': 'nscp/resource-snapshot/v1',
            'capacity': {'ram_bytes': available, 'vram_bytes': None},
            'ram_source': source, 'ram_status': 'unknown' if available is None else 'observed',
            'vram_status': 'unknown', 'allocation_guaranteed': False}


def cap_live_ram(capacity, observation):
    """Never increase a caller's explicit RAM cap; failed sampling stays unknown."""
    from context_route_policy import _resource_pair
    result = _resource_pair(capacity, unknown=True)
    live = _resource_pair(observation['capacity'], unknown=True)['ram_bytes']
    previous = result['ram_bytes']
    result['ram_bytes'] = None if live is None else live if previous is None else min(live, previous)
    return result

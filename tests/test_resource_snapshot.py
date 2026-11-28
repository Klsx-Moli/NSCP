import pytest

import resource_snapshot as rs


def fixture(tmp_path, *, available=100, groups='0::/child', limit='80000', current='30000'):
    proc, root = tmp_path / 'proc', tmp_path / 'cg'
    (proc / 'self').mkdir(parents=True)
    (root / 'child').mkdir(parents=True)
    (proc / 'meminfo').write_text(f'MemTotal: 200 kB\nMemAvailable: {available} kB\n')
    (proc / 'self/cgroup').write_text(groups + '\n')
    (proc / 'self/mountinfo').write_text(f'1 2 0:3 / {root} ro - cgroup2 cgroup rw\n')
    (root / 'memory.max').write_text(limit)
    (root / 'memory.current').write_text(current)
    (root / 'child/memory.max').write_text('max')
    (root / 'child/memory.current').write_text('10000')
    return proc, root


def test_parent_limit_and_child_limit(tmp_path):
    proc, root = fixture(tmp_path)
    assert rs._linux_ram(proc, root) == 50000
    (root / 'child/memory.max').write_text('12000')
    assert rs._linux_ram(proc, root) == 2000
    (root / 'child/memory.current').write_text('13000')
    assert rs._linux_ram(proc, root) == 0


def test_unlimited_cgroup_still_uses_available_not_total(tmp_path):
    proc, root = fixture(tmp_path, limit='max')
    assert rs._linux_ram(proc, root) == 102400


@pytest.mark.parametrize('kw', [{'available': -1}, {'available': 201}, {'groups': '0::/../other'},
                                {'groups': '1:memory:/'}, {'limit': '-1'}, {'current': '-1'}])
def test_malformed_observations_fail(tmp_path, kw):
    with pytest.raises(ValueError):
        rs._linux_ram(*fixture(tmp_path, **kw))


def test_hidden_mount_rejected(tmp_path):
    proc, root = fixture(tmp_path)
    (proc / 'self/mountinfo').write_text(f'1 2 0:3 /hidden {root} ro - cgroup2 cgroup rw\n')
    with pytest.raises(ValueError, match='mount'):
        rs._linux_ram(proc, root)


def test_sampling_failure_is_unknown(monkeypatch):
    def fail():
        raise OSError('not accessible')
    monkeypatch.setattr(rs.sys, 'platform', 'linux')
    monkeypatch.setattr(rs, '_linux_ram', fail)
    result = rs.snapshot()
    assert result['capacity'] == {'ram_bytes': None, 'vram_bytes': None}
    assert result['ram_status'] == 'unknown'
    assert result['allocation_guaranteed'] is False


@pytest.mark.parametrize('previous,live,expected', [(100, 50, 50), (50, 100, 50),
                                                   (None, 50, 50), (100, None, None), (0, 50, 0)])
def test_live_cap_preserves_explicit_lower_bound(previous, live, expected):
    capacity = {'ram_bytes': previous, 'vram_bytes': 20}
    observation = {'capacity': {'ram_bytes': live, 'vram_bytes': None}}
    assert rs.cap_live_ram(capacity, observation) == {'ram_bytes': expected, 'vram_bytes': 20}
    assert capacity['ram_bytes'] == previous


def test_windows_api_shape_and_physical_not_pagefile(monkeypatch):
    class Query:
        def __call__(self, pointer):
            status = pointer._obj
            assert status.length == 64
            status.total_phys = 16000
            status.avail_phys = 4000
            status.avail_page = 90000
            return 1
    class Kernel:
        GlobalMemoryStatusEx = Query()
    monkeypatch.setattr(rs.ctypes, 'WinDLL', lambda *a, **k: Kernel(), raising=False)
    assert rs._windows_ram() == 4000
    monkeypatch.setattr(rs.sys, 'platform', 'win32')
    assert rs.snapshot()['capacity'] == {'ram_bytes': 4000, 'vram_bytes': None}

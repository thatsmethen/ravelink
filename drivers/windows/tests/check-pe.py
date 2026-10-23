#!/usr/bin/env python3
"""Validate a built x64 kernel PE and emit reviewable evidence; never loads it."""
import argparse
import hashlib
import json
import pathlib
import struct


def inspect(path):
    data = pathlib.Path(path).read_bytes()
    def u16(offset): return struct.unpack_from('<H', data, offset)[0]
    def u32(offset): return struct.unpack_from('<I', data, offset)[0]
    assert data[:2] == b'MZ', 'missing DOS header'
    pe = u32(0x3c)
    assert data[pe:pe + 4] == b'PE\0\0', 'missing PE header'
    assert u16(pe + 4) == 0x8664, 'expected AMD64'
    optional = pe + 24
    assert u16(optional) == 0x20b, 'expected PE32+'
    assert u16(optional + 68) == 1, 'expected native subsystem'
    flags = u16(optional + 70)
    assert flags & 0x1c0 == 0x1c0, 'ASLR, NX and integrity checking required'
    sections = []
    start = optional + u16(pe + 20)
    for index in range(u16(pe + 6)):
        offset = start + index * 40
        name = data[offset:offset + 8].rstrip(b'\0').decode('ascii')
        virtual_size, rva, raw_size, raw = struct.unpack_from('<IIII', data, offset + 8)
        characteristics = u32(offset + 36)
        assert characteristics & 0xa0000000 != 0xa0000000, f'writable executable section: {name}'
        sections.append((name, rva, virtual_size, raw, raw_size, characteristics))
    def locate(rva):
        for _, base, size, raw, raw_size, _ in sections:
            if base <= rva < base + max(size, raw_size):
                relative = rva - base
                assert relative < raw_size, 'RVA has no file bytes'
                return raw + relative
        raise AssertionError(f'unmapped RVA {rva:x}')
    def string(rva):
        at = locate(rva)
        return data[at:data.index(b'\0', at)].decode('ascii')
    def directory(index): return struct.unpack_from('<II', data, optional + 112 + index * 8)
    entry = u32(optional + 16)
    assert any(rva <= entry < rva + size and char & 0x20000000 for _, rva, size, _, _, char in sections), 'entry is not executable'
    assert directory(5)[1] > 0, 'base relocations required'
    assert directory(9) == (0, 0), 'TLS callbacks are forbidden'
    imports = {}
    import_rva, _ = directory(1)
    cursor = locate(import_rva)
    while any(data[cursor:cursor + 20]):
        thunk, _, _, name_rva, iat = struct.unpack_from('<IIIII', data, cursor)
        name = string(name_rva).lower()
        assert name in {'ntoskrnl.exe', 'hal.dll', 'portcls.sys'}, f'non-kernel import: {name}'
        functions = []
        position = locate(thunk or iat)
        while (value := struct.unpack_from('<Q', data, position)[0]):
            assert value < 1 << 63, 'ordinal imports forbidden'
            functions.append(string(value + 2))
            position += 8
        imports[name] = functions
        cursor += 20
    assert 'DriverEntry' not in sum(imports.values(), []), 'entry must be implemented'
    assert 'PcInitializeAdapterDriver' in imports.get('portcls.sys', []), 'missing PortCls initialization'
    assert 'PcRegisterSubdevice' in imports.get('portcls.sys', []), 'missing endpoint registration'
    exports = {}
    export_rva, _ = directory(0)
    export = locate(export_rva)
    function_count, name_count, addresses, names, ordinals = struct.unpack_from('<IIIII', data, export + 20)
    for index in range(name_count):
        name = string(u32(locate(names) + index * 4))
        ordinal = u16(locate(ordinals) + index * 2)
        assert ordinal < function_count
        exports[name] = u32(locate(addresses) + ordinal * 4)
    assert exports.get('DriverEntry') == entry, 'entry must match exported DriverEntry'
    checksum_offset = optional + 64
    stored = u32(checksum_offset)
    total = 0
    padded = data + b'\0' * (len(data) % 2)
    for offset in range(0, len(padded), 2):
        if checksum_offset <= offset < checksum_offset + 4:
            continue
        total += struct.unpack_from('<H', padded, offset)[0]
        total = (total & 0xffff) + (total >> 16)
    total = ((total & 0xffff) + (total >> 16)) + len(data)
    assert stored == total, f'invalid PE checksum: {stored:x} != {total:x}'
    return {
        'file': pathlib.Path(path).name, 'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(), 'machine': 'AMD64',
        'subsystem': 'native', 'entry_rva': entry, 'checksum': stored,
        'imports': imports, 'exports': exports,
        'sections': [name for name, *_ in sections],
        'signed': directory(4)[1] > 0,
        'qualification': 'PE structure only; no kernel load or endpoint runtime test',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('image')
    parser.add_argument('--output')
    arguments = parser.parse_args()
    report = json.dumps(inspect(arguments.image), indent=2) + '\n'
    if arguments.output:
        pathlib.Path(arguments.output).write_text(report)
    print(report, end='')

# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild

from pkg_resources import parse_version
from kaitaistruct import __version__ as ks_version, KaitaiStruct, KaitaiStream, BytesIO


if parse_version(ks_version) < parse_version('0.7'):
    raise Exception("Incompatible Kaitai Struct Python API: 0.7 or later is required, but you have %s" % (ks_version))

class AupHeader(KaitaiStruct):
    def __init__(self, _io, _parent=None, _root=None):
        self._io = _io
        self._parent = _parent
        self._root = _root if _root else self
        self._read()

    def _read(self):
        self.magic = (self._io.read_bytes(16)).decode(u"UTF-8")
        self.fmt_ver = self._io.read_u4le()
        _on = self.fmt_ver
        if _on == 0:
            self.header_data = self._root.Aup0(self._io, self, self._root)
        elif _on == 1:
            self.header_data = self._root.Aup1(self._io, self, self._root)
        elif _on == 2:
            self.header_data = self._root.Aup2(self._io, self, self._root)

    class Aup2(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            self._io = _io
            self._parent = _parent
            self._root = _root if _root else self
            self._read()

        def _read(self):
            self.payload_len = self._io.read_u4le()
            self.firmware_ver = (self._io.read_bytes(64)).decode(u"UTF-8")
            self.payload_crc = self._io.read_u4le()
            self.hw_list_count = self._io.read_u4le()
            self.sw_list_count = self._io.read_u4le()
            self.hw_list = [None] * (self.hw_list_count)
            for i in range(self.hw_list_count):
                self.hw_list[i] = self._root.Fixed32Str(self._io, self, self._root)

            self.sw_list = [None] * (self.sw_list_count)
            for i in range(self.sw_list_count):
                self.sw_list[i] = self._root.Fixed32Str(self._io, self, self._root)



    class Aup1(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            self._io = _io
            self._parent = _parent
            self._root = _root if _root else self
            self._read()

        def _read(self):
            self.header_len = self._io.read_u4le()
            self._raw_hw_list = self._io.read_bytes(128)
            io = KaitaiStream(BytesIO(self._raw_hw_list))
            self.hw_list = self._root.CommaSeperatedStrList(io, self, self._root)
            self.payload_len = self._io.read_u4le()
            self.firmware_ver = (self._io.read_bytes(64)).decode(u"UTF-8")
            self.payload_crc = self._io.read_u4le()


    class Aup0(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            self._io = _io
            self._parent = _parent
            self._root = _root if _root else self
            self._read()

        def _read(self):
            self.payload_len = self._io.read_u4le()
            self.firmware_ver = (self._io.read_bytes(64)).decode(u"UTF-8")
            self.payload_crc = self._io.read_u4le()


    class CommaSeperatedStrList(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            self._io = _io
            self._parent = _parent
            self._root = _root if _root else self
            self._read()

        def _read(self):
            self.hw_str_list = []
            i = 0
            while not self._io.is_eof():
                self.hw_str_list.append((self._io.read_bytes_term(44, False, True, False)).decode(u"UTF-8"))
                i += 1



    class Fixed32Str(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            self._io = _io
            self._parent = _parent
            self._root = _root if _root else self
            self._read()

        def _read(self):
            self.str_value = (KaitaiStream.bytes_terminate(self._io.read_bytes(32), 0, False)).decode(u"UTF-8")



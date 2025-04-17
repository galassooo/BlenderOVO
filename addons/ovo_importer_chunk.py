# --------------------------------------------------------
#  OVO IMPORTER CHUNK
# --------------------------------------------------------
# This module defines the OVOChunk class, which encapsulates one chunk
# of data from an OVO file. Each chunk consists of:
#   - A header of 8 bytes (4 bytes for chunk_id, 4 bytes for chunk_size)
#   - The actual binary data of length chunk_size.
#
# The static method read_chunk() reads these values from a binary file
# (or file-like object) and returns an OVOChunk instance, or None if
# the end of the file is reached.
# ================================================================

import struct


class OVOChunk:
    """
    Represents a single chunk of data read from the .ovo file.

    Attributes:
        chunk_id (int): The ID indicating the type of data in this chunk.
        chunk_size (int): The number of bytes in the data portion.
        data (bytes): The raw binary data of the chunk.
    """

    def __init__(self, chunk_id, chunk_size, data):
        self.chunk_id = chunk_id
        self.chunk_size = chunk_size
        self.data = data

    @staticmethod
    def read_chunk(file_obj):
        """
        Reads one chunk from the given binary file.

        The chunk header consists of 8 bytes:
          - 4 bytes: Unsigned integer for chunk_id (little-endian)
          - 4 bytes: Unsigned integer for chunk_size (little-endian)

        After the header, the function reads chunk_size bytes for the chunk data.

        :param file_obj: A binary file-like object open for reading.
        :return: An OVOChunk instance if successful, or None when end-of-file is reached.
        """
        header = file_obj.read(8)
        if len(header) < 8:
            return None
        # Unpack the header: two unsigned integers (chunk_id and chunk_size)
        cid, csize = struct.unpack("<II", header)
        cdata = file_obj.read(csize)
        return OVOChunk(cid, csize, cdata)

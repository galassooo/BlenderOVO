"""
ovo_texture_flipper.py
Classe per il flipping verticale di file DDS compressi.

Supporta i formati di compressione:
- DXT1 (BC1)
- DXT5 (BC3)
- BC5 (ATI2, BC5U, BC5S)
- Header DX10 con tutti i formati DXGI
"""

import os
import struct
import math
import shutil
import tempfile

class OVOTextureFlipper:
    """
    Classe per il flipping verticale di file DDS, specificamente progettata
    per l'esportatore e importatore OVO.

    Supporta i formati DXT1, DXT5, BC5 e formati con header DX10.
    """

    # Costanti per i formati di compressione
    DXT1_FOURCC = b'DXT1'  # 8 byte per blocco
    DXT5_FOURCC = b'DXT5'  # 16 byte per blocco
    BC5_FOURCC = b'ATI2'   # 16 byte per blocco (ATI2 è il codice usato per BC5)
    BC5U_FOURCC = b'BC5U'  # Altro codice usato per BC5
    BC5S_FOURCC = b'BC5S'  # Altro codice usato per BC5
    DX10_FOURCC = b'DX10'  # Marker per header DX10 esteso

    # Dict per la dimensione dei blocchi in base al formato
    BLOCK_SIZE = {
        DXT1_FOURCC: 8,     # 8 byte per blocco
        DXT5_FOURCC: 16,    # 16 byte per blocco
        BC5_FOURCC: 16,     # 16 byte per blocco
        BC5U_FOURCC: 16,    # 16 byte per blocco
        BC5S_FOURCC: 16     # 16 byte per blocco
    }

    # DXGI_FORMAT values per i formati comuni
    DXGI_FORMAT = {
        71: 'BC1_TYPELESS',    # 8 byte per blocco
        72: 'BC1_UNORM',       # 8 byte per blocco (DXT1)
        73: 'BC1_UNORM_SRGB',  # 8 byte per blocco (DXT1)
        74: 'BC2_TYPELESS',    # 16 byte per blocco
        75: 'BC2_UNORM',       # 16 byte per blocco (DXT3)
        76: 'BC2_UNORM_SRGB',  # 16 byte per blocco
        77: 'BC3_TYPELESS',    # 16 byte per blocco
        78: 'BC3_UNORM',       # 16 byte per blocco (DXT5)
        79: 'BC3_UNORM_SRGB',  # 16 byte per blocco
        80: 'BC4_TYPELESS',    # 8 byte per blocco
        81: 'BC4_UNORM',       # 8 byte per blocco (BC4, 1 canale)
        82: 'BC4_SNORM',       # 8 byte per blocco
        83: 'BC5_TYPELESS',    # 16 byte per blocco
        84: 'BC5_UNORM',       # 16 byte per blocco (BC5, 2 canali, ideal per normal maps)
        85: 'BC5_SNORM',       # 16 byte per blocco (BC5 signed)
        86: 'BC6H_TYPELESS',   # 16 byte per blocco
        87: 'BC6H_UF16',       # 16 byte per blocco (BC6H, HDR)
        88: 'BC6H_SF16',       # 16 byte per blocco
        89: 'BC7_TYPELESS',    # 16 byte per blocco
        90: 'BC7_UNORM',       # 16 byte per blocco (BC7, high quality)
        91: 'BC7_UNORM_SRGB'   # 16 byte per blocco
    }

    # DXGI Block Sizes (numero di byte per blocco compresso)
    DXGI_BLOCK_SIZE = {
        # BC1 (DXT1)
        71: 8, 72: 8, 73: 8,
        # BC2 (DXT3)
        74: 16, 75: 16, 76: 16,
        # BC3 (DXT5)
        77: 16, 78: 16, 79: 16,
        # BC4
        80: 8, 81: 8, 82: 8,
        # BC5
        83: 16, 84: 16, 85: 16,
        # BC6H
        86: 16, 87: 16, 88: 16,
        # BC7
        89: 16, 90: 16, 91: 16
    }

    # Posizioni nell'header DDS
    HEIGHT_OFFSET = 12
    WIDTH_OFFSET = 16
    MIPMAP_COUNT_OFFSET = 28
    PITCH_OR_LINEAR_SIZE_OFFSET = 20
    FLAGS_OFFSET = 8  # dwFlags
    PIXEL_FORMAT_OFFSET = 76
    FOURCC_OFFSET = 84

    # Flag values
    DDSD_CAPS = 0x1
    DDSD_HEIGHT = 0x2
    DDSD_WIDTH = 0x4
    DDSD_PITCH = 0x8
    DDSD_PIXELFORMAT = 0x1000
    DDSD_MIPMAPCOUNT = 0x20000
    DDSD_LINEARSIZE = 0x80000

    # Pixel format flags
    DDPF_ALPHAPIXELS = 0x1
    DDPF_ALPHA = 0x2
    DDPF_FOURCC = 0x4
    DDPF_RGB = 0x40

    # Dimensione standard degli header
    HEADER_SIZE = 128
    DX10_HEADER_SIZE = 20  # Dimensione dell'header aggiuntivo DX10

    # ---------------------------------------------------------- ### PATCH
    #  Helpers per ribaltare i 4×4 pixel interni a un blocco      #
    # ---------------------------------------------------------- #
    @staticmethod
    def _flip_bc1_block(block: bytes) -> bytes:
        """Flip verticale di un blocco BC1 / DXT1 (8 byte)."""
        # byte 0-3 = color0 & color1 (rimangono invariati)
        colour_hdr = block[:4]
        # byte 4-7 = 16 indici da 2 bit (row-major, little-endian)
        idx = int.from_bytes(block[4:], 'little')
        # separa le 4 righe da 8 bit e inverti l’ordine
        r0 = (idx >>  0) & 0xFF
        r1 = (idx >>  8) & 0xFF
        r2 = (idx >> 16) & 0xFF
        r3 = (idx >> 24) & 0xFF
        flipped = (r3      |
                  (r2 <<  8) |
                  (r1 << 16) |
                  (r0 << 24))
        return colour_hdr + flipped.to_bytes(4, 'little')

    @staticmethod
    def _flip_bc3_alpha(block: bytes) -> bytes:
        """Flip dei 6 byte di indici alpha usati da DXT5/BC3/BC4/BC5."""
        a_idx = int.from_bytes(block, 'little')        # 48 bit
        rows = [(a_idx >> (12 * i)) & 0xFFF for i in range(4)]
        flipped = sum(rows[i] << (12 * (3 - i)) for i in range(4))
        return flipped.to_bytes(6, 'little')

    @staticmethod
    def _flip_bc3_block(block: bytes) -> bytes:
        """Flip verticale di un blocco BC3 / DXT5 (16 byte)."""
        # 0-1 alpha0/alpha1 | 2-7 indici alpha (48 bit)
        a0a1 = block[0:2]
        a_idx = OVOTextureFlipper._flip_bc3_alpha(block[2:8])
        # 8-15 = BC1 colour part
        colour = OVOTextureFlipper._flip_bc1_block(block[8:])
        return a0a1 + a_idx + colour

    @staticmethod
    def _flip_bc5_block(block: bytes) -> bytes:
        """Flip verticale di un blocco BC5 (16 byte = R-channel + G-channel)."""
        # 0-7   = canale R  (BC4 ≃ alpha-part di BC3)
        # 8-15  = canale G
        r_part = block[:8]
        g_part = block[8:]
        r_flipped = r_part[:2] + OVOTextureFlipper._flip_bc3_alpha(r_part[2:])
        g_flipped = g_part[:2] + OVOTextureFlipper._flip_bc3_alpha(g_part[2:])
        return r_flipped + g_flipped
    # ---------------------------------------------------------- ### END PATCH

    @staticmethod
    def flip_dds_texture(input_path, output_path=None):
        """
        Flippa verticalmente un file DDS, supportando formati standard e DX10.

        Args:
            input_path (str): Percorso del file DDS da flippare
            output_path (str, opzionale): Percorso di output. Se None, sovrascrive il file originale

        Returns:
            str: Percorso del file DDS flippato o del file originale in caso di errore
        """
        # Verifica che il file di input esista
        if not os.path.exists(input_path):
            print(f"Il file {input_path} non esiste")
            return input_path

        # Se non è specificato un output, usa lo stesso file di input
        if output_path is None:
            # Crea un file temporaneo invece di sovrascrivere direttamente
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, f"temp_{os.path.basename(input_path)}")
            final_output = input_path
        else:
            temp_file = output_path
            final_output = output_path

        try:
            # Leggi il file completo in memoria
            with open(input_path, 'rb') as f:
                data = f.read()

            # Verifica che sia un file DDS
            if len(data) < OVOTextureFlipper.HEADER_SIZE or data[:4] != b'DDS ':
                raise ValueError(f"Il file {input_path} non è un file DDS valido")

            # Estrai informazioni dall'header
            header = data[:OVOTextureFlipper.HEADER_SIZE]
            width = struct.unpack('<I', data[OVOTextureFlipper.WIDTH_OFFSET:OVOTextureFlipper.WIDTH_OFFSET+4])[0]
            height = struct.unpack('<I', data[OVOTextureFlipper.HEIGHT_OFFSET:OVOTextureFlipper.HEIGHT_OFFSET+4])[0]
            flags = struct.unpack('<I', data[OVOTextureFlipper.FLAGS_OFFSET:OVOTextureFlipper.FLAGS_OFFSET+4])[0]
            has_mipmap = (flags & OVOTextureFlipper.DDSD_MIPMAPCOUNT) != 0
            mipmap_count = struct.unpack('<I', data[OVOTextureFlipper.MIPMAP_COUNT_OFFSET:OVOTextureFlipper.MIPMAP_COUNT_OFFSET+4])[0] if has_mipmap else 1

            # Estrai informazioni sul formato pixel
            pixel_format_flags = struct.unpack('<I', data[OVOTextureFlipper.PIXEL_FORMAT_OFFSET:OVOTextureFlipper.PIXEL_FORMAT_OFFSET+4])[0]
            four_cc = data[OVOTextureFlipper.FOURCC_OFFSET:OVOTextureFlipper.FOURCC_OFFSET+4]

            print(f"Flipping DDS: {os.path.basename(input_path)}")
            print(f"  Dimensioni: {width}x{height}")
            print(f"  Mipmaps: {mipmap_count}")
            print(f"  FourCC: {four_cc.decode('ascii', errors='replace')}")

            # Determine se è un header DX10 e imposta la dimensione dell'header
            header_size = OVOTextureFlipper.HEADER_SIZE
            dxgi_format = None
            is_dx10 = False

            # Check per header DX10
            if four_cc == OVOTextureFlipper.DX10_FOURCC:
                is_dx10 = True
                header_size += OVOTextureFlipper.DX10_HEADER_SIZE  # Aggiungi dimensione header DX10

                # Estrai DXGI_FORMAT dall'header DX10
                dxgi_format = struct.unpack('<I', data[OVOTextureFlipper.HEADER_SIZE:OVOTextureFlipper.HEADER_SIZE+4])[0]
                print(f"  DX10 header trovato. DXGI_FORMAT: {dxgi_format} ({OVOTextureFlipper.DXGI_FORMAT.get(dxgi_format, 'Unknown')})")

            # Determina la dimensione del blocco in base al formato
            block_size = None

            if is_dx10:
                # Usa DXGI_FORMAT per determinare la dimensione del blocco
                if dxgi_format in OVOTextureFlipper.DXGI_BLOCK_SIZE:
                    block_size = OVOTextureFlipper.DXGI_BLOCK_SIZE[dxgi_format]
                    print(f"  Usando dimensione blocco di {block_size} byte per DXGI_FORMAT: {OVOTextureFlipper.DXGI_FORMAT.get(dxgi_format, 'Unknown')}")
                else:
                    raise ValueError(f"DXGI_FORMAT non supportato: {dxgi_format}")
            else:
                # Usa FourCC per formati standard
                if four_cc in OVOTextureFlipper.BLOCK_SIZE:
                    block_size = OVOTextureFlipper.BLOCK_SIZE[four_cc]
                    print(f"  Usando dimensione blocco di {block_size} byte per formato: {four_cc.decode('ascii', errors='replace')}")
                else:
                    # Per formati non compressi o non gestiti, prova a guardare il pitch
                    if flags & OVOTextureFlipper.DDSD_PITCH:
                        raise ValueError(f"Formato non compresso con pitch non supportato")
                    elif flags & OVOTextureFlipper.DDSD_LINEARSIZE:
                        # Possiamo provare a capire la dimensione del blocco dalla dimensione lineare
                        linear_size = struct.unpack('<I', data[OVOTextureFlipper.PITCH_OR_LINEAR_SIZE_OFFSET:OVOTextureFlipper.PITCH_OR_LINEAR_SIZE_OFFSET+4])[0]
                        width_blocks = (width + 3) // 4
                        height_blocks = (height + 3) // 4
                        total_blocks = width_blocks * height_blocks
                        if total_blocks > 0:
                            estimated_block_size = linear_size / total_blocks
                            # Arrotonda al valore più vicino (8 o 16)
                            if estimated_block_size <= 12:  # Soglia tra 8 e 16
                                block_size = 8
                            else:
                                block_size = 16
                            print(f"  Dimensione blocco stimata: {estimated_block_size} -> arrotondata a {block_size}")
                        else:
                            raise ValueError(f"Impossibile determinare la dimensione del blocco")
                    else:
                        raise ValueError(f"Formato non supportato: {four_cc}")

            # Prepara il nuovo file
            with open(temp_file, 'wb') as f:
                # Scrivi l'header originale (incluso DX10 se presente)
                f.write(data[:header_size])

                # Posizione corrente nei dati
                pos = header_size

                # Per ogni livello di mipmap
                current_width, current_height = width, height

                for level in range(mipmap_count):
                    # Calcola dimensioni in blocchi
                    width_blocks = max(1, (current_width + 3) // 4)
                    height_blocks = max(1, (current_height + 3) // 4)

                    # Calcola la dimensione di questo livello
                    mipmap_size = width_blocks * height_blocks * block_size

                    # Assicurati che ci siano abbastanza dati
                    if pos + mipmap_size > len(data):
                        print(f"  Attenzione: i dati per mipmap {level} sembrano incompleti")
                        # Copia il resto dei dati e esci
                        f.write(data[pos:])
                        break

                    # Estrai dati della mipmap
                    mipmap_data = data[pos:pos+mipmap_size]

                    # Calcola dimensione di una riga di blocchi
                    row_size = width_blocks * block_size

                    # Dividi i dati in righe
                                        # -------------------------------------------------- ### PATCH
                    # Flip per‐blocco + flip delle righe
                    flipped_rows = []
                    for row in range(height_blocks):           # dal top al bottom
                        start = row * row_size
                        end   = start + row_size
                        row_data = mipmap_data[start:end]
                        new_row  = bytearray()

                        # percorri tutti i blocchi di quella riga
                        for col in range(width_blocks):
                            b_start = col * block_size
                            b_end   = b_start + block_size
                            blk = row_data[b_start:b_end]

                            # scegli la routine adatta
                            if block_size == 8:
                                blk = OVOTextureFlipper._flip_bc1_block(blk)
                            else:  # 16 byte
                                if four_cc in (OVOTextureFlipper.DXT5_FOURCC,) or \
                                   dxgi_format in (77, 78, 79):          # BC3 / DXT5
                                    blk = OVOTextureFlipper._flip_bc3_block(blk)
                                elif four_cc in (OVOTextureFlipper.BC5_FOURCC,
                                                  OVOTextureFlipper.BC5U_FOURCC,
                                                  OVOTextureFlipper.BC5S_FOURCC) or \
                                     dxgi_format in (83, 84, 85):        # BC5
                                    blk = OVOTextureFlipper._flip_bc5_block(blk)
                                # altri formati 16 byte (BC7, BC6H, …) non necessitano flip intra-blocco
                            new_row.extend(blk)

                        flipped_rows.append(bytes(new_row))

                    # ora capovolgi l’ordine delle righe di blocchi
                    flipped_mipmap = b''.join(reversed(flipped_rows))
                    # -------------------------------------------------- ### END PATCH

                    # Scrivi la mipmap flippata
                    f.write(flipped_mipmap)

                    # Log dettagliato solo per il primo livello
                    if level == 0:
                        print(f"  Mipmap base: {width_blocks}x{height_blocks} blocchi ({row_size} byte/riga)")

                    # Aggiorna posizione per il prossimo livello
                    pos += mipmap_size

                    # Dimezza le dimensioni per il prossimo livello
                    current_width = max(1, current_width // 2)
                    current_height = max(1, current_height // 2)

                # Se ci sono dati aggiuntivi dopo i mipmaps, copiali tali e quali
                if pos < len(data):
                    remaining_data = data[pos:]
                    f.write(remaining_data)
                    print(f"  Copiati {len(remaining_data)} byte di dati aggiuntivi dopo i mipmaps")

            # Se stiamo sovrascrivendo il file originale, sposta il file temporaneo
            if temp_file != final_output:
                shutil.move(temp_file, final_output)

            print(f"Texture flippata salvata in: {final_output}")
            return final_output

        except (IOError, ValueError) as e:
            print(f"ERRORE durante il flipping della texture: {str(e)}")
            # In caso di errore, se stiamo sovrascrivendo, assicuriamoci che il file originale rimanga intatto
            if temp_file != input_path and output_path is None:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
            return input_path
        except Exception as e:
            print(f"ERRORE non previsto durante il flipping: {str(e)}")
            # In caso di errore generico, torna al file originale
            return input_path

    @staticmethod
    def is_dds_file(filepath):
        """
        Controlla se un file è un DDS valido.

        Args:
            filepath (str): Percorso del file da controllare

        Returns:
            bool: True se è un file DDS valido, False altrimenti
        """
        try:
            with open(filepath, 'rb') as f:
                magic = f.read(4)
            return magic == b'DDS '
        except:
            return False

    @staticmethod
    def get_dds_info(filepath):
        """
        Estrae informazioni di base da un file DDS.

        Args:
            filepath (str): Percorso del file DDS

        Returns:
            dict: Dizionario con informazioni (width, height, mipmap_count, format, dxgi_format)
            None: Se il file non è un DDS valido
        """
        try:
            with open(filepath, 'rb') as f:
                data = f.read(148)  # Leggi header DDS standard + header DX10

            if data[:4] != b'DDS ':
                return None

            width = struct.unpack('<I', data[OVOTextureFlipper.WIDTH_OFFSET:OVOTextureFlipper.WIDTH_OFFSET+4])[0]
            height = struct.unpack('<I', data[OVOTextureFlipper.HEIGHT_OFFSET:OVOTextureFlipper.HEIGHT_OFFSET+4])[0]
            flags = struct.unpack('<I', data[OVOTextureFlipper.FLAGS_OFFSET:OVOTextureFlipper.FLAGS_OFFSET+4])[0]
            has_mipmap = (flags & OVOTextureFlipper.DDSD_MIPMAPCOUNT) != 0
            mipmap_count = struct.unpack('<I', data[OVOTextureFlipper.MIPMAP_COUNT_OFFSET:OVOTextureFlipper.MIPMAP_COUNT_OFFSET+4])[0] if has_mipmap else 1
            four_cc = data[OVOTextureFlipper.FOURCC_OFFSET:OVOTextureFlipper.FOURCC_OFFSET+4]

            result = {
                'width': width,
                'height': height,
                'mipmap_count': mipmap_count,
                'format': four_cc
            }

            # Se è un formato DX10, estrai anche il DXGI_FORMAT
            if four_cc == OVOTextureFlipper.DX10_FOURCC and len(data) >= OVOTextureFlipper.HEADER_SIZE + 4:
                dxgi_format = struct.unpack('<I', data[OVOTextureFlipper.HEADER_SIZE:OVOTextureFlipper.HEADER_SIZE+4])[0]
                result['dxgi_format'] = dxgi_format
                result['dxgi_format_name'] = OVOTextureFlipper.DXGI_FORMAT.get(dxgi_format, 'Unknown')

            return result
        except Exception as e:
            print(f"Errore durante l'analisi del file DDS: {str(e)}")
            return None

    @staticmethod
    def safe_flip_dds_texture(input_path, output_path=None):
        """
        Versione sicura di flip_dds_texture che non solleva eccezioni.

        Args:
            input_path (str): Percorso del file DDS da flippare
            output_path (str, opzionale): Percorso di output. Se None, sovrascrive il file originale

        Returns:
            tuple: (bool, str) Indica se il flipping è riuscito e il percorso del file risultante
        """
        # Se i percorsi non sono validi, esci subito
        if not input_path or not os.path.exists(input_path):
            return False, input_path

        try:
            # Tenta di flippare la texture
            result_path = OVOTextureFlipper.flip_dds_texture(input_path, output_path)

            # Verifica che il file risultante esista
            if result_path != input_path and os.path.exists(result_path):
                return True, result_path
            elif os.path.exists(input_path):
                # Se il flip non è riuscito ma l'originale è ok, torna quello
                return False, input_path
            else:
                # Se qualcosa è andato storto e l'originale è sparito, è un errore
                return False, None
        except Exception as e:
            print(f"Eccezione durante il flipping sicuro: {str(e)}")
            return False, input_path


# Esempio di utilizzo
if __name__ == "__main__":
    # Questo codice viene eseguito solo se il file viene eseguito direttamente
    import sys

    if len(sys.argv) < 2:
        print("Utilizzo: python ovo_texture_flipper.py <percorso_file_dds> [percorso_output]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    flipper = OVOTextureFlipper()

    if flipper.is_dds_file(input_file):
        info = flipper.get_dds_info(input_file)
        if info:
            print(f"Texture: {input_file}")
            print(f"  Dimensioni: {info['width']}x{info['height']}")
            print(f"  Mipmaps: {info['mipmap_count']}")
            format_str = info['format'].decode('ascii', errors='replace')
            print(f"  Formato: {format_str}")

            if 'dxgi_format' in info:
                print(f"  DXGI_FORMAT: {info['dxgi_format']} ({info['dxgi_format_name']})")

        success, flipped_path = flipper.safe_flip_dds_texture(input_file, output_file)
        if success:
            print(f"Texture flippata con successo: {flipped_path}")
        else:
            print(f"Non è stato possibile flippare la texture: {flipped_path}")
    else:
        print(f"Il file {input_file} non è un file DDS valido.")
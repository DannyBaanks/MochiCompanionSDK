"""MochiCompanionSDK: crear animaciones del DASAI Mega Mochi desde arte de Companion.

El unico contrato que importa es el que el firmware ya acepta, y eso se midio en
los 62 videos factory (profiles/mochi-factory-v1.json). Ningun numero de este
paquete se invento: sale de ese profile.
"""
from .container import AviAsset, AviError, load_avi, parse_avi
from .writer import AUDIO_BYTES_PER_FRAME, build_avi, load_template

__all__ = ['AviAsset', 'AviError', 'load_avi', 'parse_avi', 'build_avi', 'load_template',
           'AUDIO_BYTES_PER_FRAME', 'container', 'writer', 'profile', 'playlist',
           'deploy', 'spec', 'render', 'bridge', 'cli', '__version__']
__version__ = '0.1.0'

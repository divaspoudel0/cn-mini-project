"""pktbuilder -- generate Cisco Packet Tracer .pkt files from YAML topologies.

Public API:
    load_topology(path)            parse + validate a topology file
    build_topology(spec)           render the PACKETTRACER5 XML
    encrypt_pka(xml_bytes)         seal XML into a .pkt payload
    decrypt_pka(data)              open a .pkt/.pka back to XML bytes

CLI: `pktbuild build|validate|example|decrypt` (see cli.py).
"""

from pktbuilder.model import TopologyError, load_topology
from pktbuilder.builder import build_topology
from pktbuilder.pka2xml import encrypt_pka, decrypt_pka

__all__ = ["TopologyError", "load_topology", "build_topology",
           "encrypt_pka", "decrypt_pka"]
__version__ = "1.0.0"
